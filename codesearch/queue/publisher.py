"""
Job publisher for distributing indexing tasks to workers.
"""

import json
from typing import Optional, Dict, Any
import structlog
import pika
from pika.exceptions import AMQPConnectionError

from ..models import IndexingJob, Repository
from ..config import settings

logger = structlog.get_logger()


class JobPublisher:
    """
    Publishes indexing jobs to RabbitMQ for distributed processing.
    
    Supports:
    - Priority queues for urgent jobs
    - Dead letter queues for failed jobs
    - Job deduplication
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        queue_name: Optional[str] = None
    ):
        """
        Initialize the job publisher.
        
        Args:
            host: RabbitMQ host
            port: RabbitMQ port  
            queue_name: Name of the job queue
        """
        self.host = host or settings.rabbitmq_host
        self.port = port or settings.rabbitmq_port
        self.queue_name = queue_name or settings.rabbitmq_queue
        
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
    
    def connect(self) -> None:
        """Establish connection to RabbitMQ."""
        try:
            credentials = pika.PlainCredentials(
                settings.rabbitmq_user,
                settings.rabbitmq_password
            )
            
            parameters = pika.ConnectionParameters(
                host=self.host,
                port=self.port,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            
            self._connection = pika.BlockingConnection(parameters)
            self._channel = self._connection.channel()
            
            # Declare main queue with priority support
            self._channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                arguments={
                    'x-max-priority': 10,
                    'x-dead-letter-exchange': f'{self.queue_name}_dlx'
                }
            )
            
            # Declare dead letter exchange and queue
            self._channel.exchange_declare(
                exchange=f'{self.queue_name}_dlx',
                exchange_type='direct',
                durable=True
            )
            self._channel.queue_declare(
                queue=f'{self.queue_name}_failed',
                durable=True
            )
            self._channel.queue_bind(
                queue=f'{self.queue_name}_failed',
                exchange=f'{self.queue_name}_dlx',
                routing_key=self.queue_name
            )
            
            logger.info("Connected to RabbitMQ", host=self.host, queue=self.queue_name)
            
        except AMQPConnectionError as e:
            logger.error("Failed to connect to RabbitMQ", error=str(e))
            raise
    
    def disconnect(self) -> None:
        """Close RabbitMQ connection."""
        if self._connection and not self._connection.is_closed:
            self._connection.close()
            logger.info("Disconnected from RabbitMQ")
    
    def publish_job(self, job: IndexingJob) -> bool:
        """
        Publish an indexing job to the queue.
        
        Args:
            job: The indexing job to publish
            
        Returns:
            True if published successfully
        """
        if not self._channel:
            self.connect()
        
        try:
            message = job.model_dump_json()
            
            properties = pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type='application/json',
                priority=job.priority,
                message_id=job.id
            )
            
            self._channel.basic_publish(
                exchange='',
                routing_key=self.queue_name,
                body=message,
                properties=properties
            )
            
            logger.info(
                "Published indexing job",
                job_id=job.id,
                repo=job.repo_name,
                priority=job.priority
            )
            return True
            
        except Exception as e:
            logger.error("Failed to publish job", job_id=job.id, error=str(e))
            return False
    
    def publish_repo(
        self, 
        repo_url: str, 
        repo_name: Optional[str] = None,
        branch: str = "main",
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> IndexingJob:
        """
        Convenience method to create and publish a repo indexing job.
        
        Args:
            repo_url: URL of the repository
            repo_name: Optional name (extracted from URL if not provided)
            branch: Git branch to index
            priority: Job priority (0-10)
            metadata: Additional metadata
            
        Returns:
            The created IndexingJob
        """
        # Extract repo name from URL if not provided
        if not repo_name:
            repo_name = repo_url.rstrip('/').split('/')[-1]
            if repo_name.endswith('.git'):
                repo_name = repo_name[:-4]
        
        job = IndexingJob(
            repo_url=repo_url,
            repo_name=repo_name,
            branch=branch,
            priority=min(max(priority, 0), 10),
            metadata=metadata or {}
        )
        
        self.publish_job(job)
        return job
    
    def get_queue_length(self) -> int:
        """Get the current number of jobs in the queue."""
        if not self._channel:
            self.connect()
        
        try:
            result = self._channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                passive=True  # Don't create, just check
            )
            return result.method.message_count
        except Exception:
            return 0
    
    def purge_queue(self) -> int:
        """Remove all jobs from the queue."""
        if not self._channel:
            self.connect()
        
        result = self._channel.queue_purge(self.queue_name)
        count = result.method.message_count
        logger.warning("Purged queue", queue=self.queue_name, count=count)
        return count
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

