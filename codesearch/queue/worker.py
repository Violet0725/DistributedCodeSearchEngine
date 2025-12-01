"""
Worker process for consuming and processing indexing jobs.
"""

import json
import signal
import sys
from pathlib import Path
from typing import Optional, Callable
import structlog
import pika
from pika.exceptions import AMQPConnectionError

from ..models import IndexingJob, Repository
from ..config import settings

logger = structlog.get_logger()


class IndexingWorker:
    """
    Worker that consumes indexing jobs from RabbitMQ and processes them.
    
    Features:
    - Graceful shutdown handling
    - Automatic reconnection
    - Job acknowledgment/rejection
    - Prefetch control for load balancing
    """
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        queue_name: Optional[str] = None,
        prefetch_count: int = 1
    ):
        """
        Initialize the worker.
        
        Args:
            host: RabbitMQ host
            port: RabbitMQ port
            queue_name: Name of the job queue
            prefetch_count: Number of messages to prefetch
        """
        self.host = host or settings.rabbitmq_host
        self.port = port or settings.rabbitmq_port
        self.queue_name = queue_name or settings.rabbitmq_queue
        self.prefetch_count = prefetch_count
        
        self._connection: Optional[pika.BlockingConnection] = None
        self._channel: Optional[pika.channel.Channel] = None
        self._job_handler: Optional[Callable[[IndexingJob], bool]] = None
        self._should_stop = False
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info("Received shutdown signal", signal=signum)
        self._should_stop = True
        if self._connection and not self._connection.is_closed:
            self._connection.close()
    
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
            
            # Set QoS for fair dispatch
            self._channel.basic_qos(prefetch_count=self.prefetch_count)
            
            # Ensure queue exists
            self._channel.queue_declare(
                queue=self.queue_name,
                durable=True,
                arguments={
                    'x-max-priority': 10,
                    'x-dead-letter-exchange': f'{self.queue_name}_dlx'
                }
            )
            
            logger.info("Worker connected to RabbitMQ", host=self.host)
            
        except AMQPConnectionError as e:
            logger.error("Worker failed to connect", error=str(e))
            raise
    
    def set_handler(self, handler: Callable[[IndexingJob], bool]) -> None:
        """
        Set the job processing handler.
        
        Args:
            handler: Function that takes an IndexingJob and returns True on success
        """
        self._job_handler = handler
    
    def _process_message(
        self,
        channel: pika.channel.Channel,
        method: pika.spec.Basic.Deliver,
        properties: pika.spec.BasicProperties,
        body: bytes
    ) -> None:
        """Process a single message from the queue."""
        job_id = properties.message_id or "unknown"
        
        try:
            # Parse job
            job_data = json.loads(body.decode('utf-8'))
            job = IndexingJob(**job_data)
            
            logger.info(
                "Processing job",
                job_id=job.id,
                repo=job.repo_name
            )
            
            # Call handler
            if self._job_handler:
                success = self._job_handler(job)
            else:
                logger.warning("No job handler set, acknowledging anyway")
                success = True
            
            if success:
                channel.basic_ack(delivery_tag=method.delivery_tag)
                logger.info("Job completed successfully", job_id=job.id)
            else:
                # Reject and don't requeue (goes to DLQ)
                channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
                logger.warning("Job failed, sent to DLQ", job_id=job.id)
                
        except json.JSONDecodeError as e:
            logger.error("Invalid job format", error=str(e))
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=False)
            
        except Exception as e:
            logger.error("Job processing error", job_id=job_id, error=str(e))
            # Requeue for retry
            channel.basic_reject(delivery_tag=method.delivery_tag, requeue=True)
    
    def start(self) -> None:
        """Start consuming jobs from the queue."""
        if not self._connection:
            self.connect()
        
        logger.info("Worker starting", queue=self.queue_name)
        
        self._channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self._process_message,
            auto_ack=False
        )
        
        try:
            while not self._should_stop:
                self._connection.process_data_events(time_limit=1)
        except Exception as e:
            if not self._should_stop:
                logger.error("Worker error", error=str(e))
                raise
        finally:
            if self._connection and not self._connection.is_closed:
                self._connection.close()
            logger.info("Worker stopped")
    
    def run_once(self) -> bool:
        """
        Process a single job and return.
        
        Returns:
            True if a job was processed, False if queue was empty
        """
        if not self._connection:
            self.connect()
        
        method, properties, body = self._channel.basic_get(
            queue=self.queue_name,
            auto_ack=False
        )
        
        if method is None:
            return False
        
        self._process_message(self._channel, method, properties, body)
        return True


def create_indexing_handler():
    """
    Create the default indexing job handler.
    
    This handler:
    1. Clones/updates the repository
    2. Parses all supported files
    3. Generates embeddings
    4. Stores in vector database
    """
    from ..indexer import RepoIndexer
    
    indexer = RepoIndexer()
    
    def handler(job: IndexingJob) -> bool:
        try:
            result = indexer.index_repo(
                repo_url=job.repo_url,
                repo_name=job.repo_name,
                branch=job.branch
            )
            return result.success
        except Exception as e:
            logger.error(
                "Indexing failed",
                repo=job.repo_name,
                error=str(e)
            )
            return False
    
    return handler

