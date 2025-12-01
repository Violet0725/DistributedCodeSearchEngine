"""
Main CLI application for CodeSearch.

A powerful code search engine with semantic understanding.
"""

import sys
from pathlib import Path
from typing import Optional, List
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.markdown import Markdown
from rich import box

from ..models import Language, CodeEntityType
from ..config import settings

app = typer.Typer(
    name="codesearch",
    help="🔍 Semantic Code Search Engine - Find code by what it does, not just syntax",
    add_completion=False
)
console = Console()

# Language mapping for CLI
LANGUAGE_MAP = {
    'python': Language.PYTHON,
    'py': Language.PYTHON,
    'javascript': Language.JAVASCRIPT,
    'js': Language.JAVASCRIPT,
    'typescript': Language.TYPESCRIPT,
    'ts': Language.TYPESCRIPT,
    'go': Language.GO,
    'golang': Language.GO,
    'rust': Language.RUST,
    'rs': Language.RUST,
}


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    limit: int = typer.Option(10, "-n", "--limit", help="Number of results"),
    language: Optional[str] = typer.Option(None, "-l", "--lang", help="Filter by language"),
    repo: Optional[str] = typer.Option(None, "-r", "--repo", help="Filter by repository"),
    entity_type: Optional[str] = typer.Option(None, "-t", "--type", help="Filter by type (function/class/method)"),
    local: Optional[str] = typer.Option(None, "--local", help="Search local directory instead"),
    show_code: bool = typer.Option(False, "-c", "--code", help="Show source code"),
    hybrid: bool = typer.Option(True, "--hybrid/--semantic-only", help="Use hybrid search"),
):
    """
    Search for code using natural language.
    
    Examples:
    
        codesearch search "function to parse JSON"
        
        codesearch search "async HTTP client" --lang python
        
        codesearch search "sort algorithm" --local ./my-project
    """
    console.print()
    
    # Parse language filter
    lang_filter = None
    if language:
        lang_filter = LANGUAGE_MAP.get(language.lower())
        if not lang_filter:
            console.print(f"[yellow]Unknown language: {language}[/yellow]")
            console.print(f"Supported: {', '.join(LANGUAGE_MAP.keys())}")
            raise typer.Exit(1)
    
    # Parse entity type filter
    type_filter = None
    if entity_type:
        try:
            type_filter = CodeEntityType(entity_type.lower())
        except ValueError:
            console.print(f"[yellow]Unknown type: {entity_type}[/yellow]")
            console.print(f"Supported: function, method, class, struct, interface, enum")
            raise typer.Exit(1)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    ) as progress:
        
        if local:
            # Local directory search
            progress.add_task("Indexing local directory...", total=None)
            
            from ..search.engine import LocalSearchEngine
            engine = LocalSearchEngine()
            
            try:
                entity_count = engine.index_directory(local)
                progress.update(progress.task_ids[0], description=f"Indexed {entity_count} entities")
            except FileNotFoundError as e:
                console.print(f"[red]Error: {e}[/red]")
                raise typer.Exit(1)
            
            results = engine.search(query, limit=limit)
        else:
            # Full search with vector database
            progress.add_task("Searching...", total=None)
            
            from ..search.engine import HybridSearchEngine
            engine = HybridSearchEngine()
            
            results = engine.search(
                query=query,
                limit=limit,
                language=lang_filter,
                entity_type=type_filter,
                repo_filter=repo,
                use_hybrid=hybrid
            )
    
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        console.print("\nTips:")
        console.print("  • Try a more general query")
        console.print("  • Remove language/type filters")
        console.print("  • Index more repositories with 'codesearch index'")
        raise typer.Exit(0)
    
    # Display results
    _display_results(results, show_code)


def _display_results(results: List, show_code: bool):
    """Display search results in a beautiful format."""
    console.print(f"\n[bold green]Found {len(results)} results[/bold green]\n")
    
    for i, result in enumerate(results, 1):
        entity = result.entity
        
        # Build header
        type_icon = _get_type_icon(entity.entity_type)
        lang_badge = f"[cyan]{entity.language.value}[/cyan]"
        
        header = f"{type_icon} [bold]{entity.name}[/bold] {lang_badge}"
        
        if entity.parent_class:
            header += f" [dim]({entity.parent_class})[/dim]"
        
        # Score info
        score_info = f"Score: {result.score:.3f}"
        if result.semantic_score > 0 and result.bm25_score > 0:
            score_info += f" [dim](semantic: {result.semantic_score:.3f}, bm25: {result.bm25_score:.3f})[/dim]"
        
        # Location
        location = f"[dim]{entity.repo_name}:{entity.file_path}:{entity.start_line}[/dim]"
        
        # Signature
        sig = entity.signature or f"{entity.entity_type.value} {entity.name}"
        
        # Build panel content
        content_parts = [
            f"[bold blue]{sig}[/bold blue]",
            "",
            location,
            score_info
        ]
        
        if entity.docstring:
            doc_preview = entity.docstring[:200]
            if len(entity.docstring) > 200:
                doc_preview += "..."
            content_parts.insert(2, f"\n[italic]{doc_preview}[/italic]")
        
        content = "\n".join(content_parts)
        
        panel = Panel(
            content,
            title=f"[{i}] {header}",
            title_align="left",
            border_style="blue",
            box=box.ROUNDED
        )
        console.print(panel)
        
        if show_code and entity.source_code:
            # Determine syntax lexer
            lexer = {
                Language.PYTHON: "python",
                Language.JAVASCRIPT: "javascript",
                Language.TYPESCRIPT: "typescript",
                Language.GO: "go",
                Language.RUST: "rust",
            }.get(entity.language, "text")
            
            code = entity.source_code
            if len(code) > 1500:
                code = code[:1500] + "\n... (truncated)"
            
            syntax = Syntax(
                code,
                lexer,
                theme="monokai",
                line_numbers=True,
                start_line=entity.start_line
            )
            console.print(syntax)
        
        console.print()


def _get_type_icon(entity_type: CodeEntityType) -> str:
    """Get an icon for the entity type."""
    icons = {
        CodeEntityType.FUNCTION: "⚡",
        CodeEntityType.METHOD: "🔧",
        CodeEntityType.CLASS: "📦",
        CodeEntityType.STRUCT: "🏗️",
        CodeEntityType.INTERFACE: "📋",
        CodeEntityType.ENUM: "📊",
        CodeEntityType.MODULE: "📁",
    }
    return icons.get(entity_type, "•")


@app.command()
def index(
    source: str = typer.Argument(..., help="Git URL or local directory path"),
    name: Optional[str] = typer.Option(None, "-n", "--name", help="Repository name"),
    branch: str = typer.Option("main", "-b", "--branch", help="Git branch"),
    force: bool = typer.Option(False, "-f", "--force", help="Force re-clone"),
):
    """
    Index a repository or local directory.
    
    Examples:
    
        codesearch index https://github.com/user/repo
        
        codesearch index ./my-project --name my-project
        
        codesearch index https://github.com/user/repo -b develop
    """
    from ..indexer import RepoIndexer
    
    console.print()
    indexer = RepoIndexer()
    
    # Determine if it's a URL or local path
    is_url = source.startswith('http://') or source.startswith('https://') or source.startswith('git@')
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        console=console
    ) as progress:
        task = progress.add_task("Indexing...", total=100)
        
        if is_url:
            progress.update(task, description="Cloning repository...")
            result = indexer.index_repo(
                repo_url=source,
                repo_name=name,
                branch=branch,
                force_reclone=force,
                show_progress=False
            )
        else:
            progress.update(task, description="Indexing local directory...")
            result = indexer.index_directory(
                directory=source,
                repo_name=name or Path(source).name,
                show_progress=False
            )
        
        progress.update(task, completed=100)
    
    if result.success:
        # Create summary table
        table = Table(title="✅ Indexing Complete", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Repository", result.repo_name)
        table.add_row("Files Processed", str(result.files_processed))
        table.add_row("Entities Found", str(result.entities_found))
        table.add_row("Entities Indexed", str(result.entities_indexed))
        table.add_row("Duration", f"{result.duration_seconds:.1f}s")
        
        if result.languages:
            langs = ", ".join(f"{k}: {v}" for k, v in result.languages.items())
            table.add_row("Languages", langs)
        
        console.print(table)
    else:
        console.print(f"[red]❌ Indexing failed: {result.error}[/red]")
        raise typer.Exit(1)


@app.command()
def stats():
    """
    Show index statistics.
    """
    console.print()
    
    try:
        from ..storage import QdrantStore, BM25Index
        
        vector_store = QdrantStore()
        bm25_index = BM25Index()
        bm25_index.load()
        
        stats = vector_store.get_stats()
        
        table = Table(title="📊 Index Statistics", box=box.ROUNDED)
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        table.add_row("Total Vectors", str(stats.get("total_points", 0)))
        table.add_row("Indexed Vectors", str(stats.get("indexed_vectors", 0)))
        table.add_row("BM25 Documents", str(bm25_index.count()))
        table.add_row("Collection Status", stats.get("status", "unknown"))
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[yellow]Could not get stats: {e}[/yellow]")
        console.print("Make sure Qdrant is running and the collection exists.")


@app.command()
def worker(
    workers: int = typer.Option(1, "-w", "--workers", help="Number of workers"),
):
    """
    Start an indexing worker to process queued jobs.
    
    This connects to RabbitMQ and processes indexing jobs from the queue.
    """
    from ..queue import IndexingWorker
    from ..queue.worker import create_indexing_handler
    
    console.print(f"[bold green]Starting {workers} indexing worker(s)...[/bold green]")
    console.print(f"Queue: {settings.rabbitmq_queue}")
    console.print(f"RabbitMQ: {settings.rabbitmq_host}:{settings.rabbitmq_port}")
    console.print("\nPress Ctrl+C to stop\n")
    
    worker = IndexingWorker()
    worker.set_handler(create_indexing_handler())
    
    try:
        worker.start()
    except KeyboardInterrupt:
        console.print("\n[yellow]Worker stopped[/yellow]")


@app.command()
def queue(
    repo_url: str = typer.Argument(..., help="Repository URL to queue"),
    name: Optional[str] = typer.Option(None, "-n", "--name", help="Repository name"),
    priority: int = typer.Option(5, "-p", "--priority", help="Job priority (0-10)"),
):
    """
    Queue a repository for indexing.
    
    Jobs will be processed by workers running 'codesearch worker'.
    """
    from ..queue import JobPublisher
    
    console.print()
    
    try:
        with JobPublisher() as publisher:
            job = publisher.publish_repo(
                repo_url=repo_url,
                repo_name=name,
                priority=priority
            )
            
            queue_length = publisher.get_queue_length()
            
            console.print(f"[green]✅ Job queued successfully[/green]")
            console.print(f"   Job ID: {job.id}")
            console.print(f"   Repository: {job.repo_name}")
            console.print(f"   Priority: {job.priority}")
            console.print(f"   Queue length: {queue_length}")
            
    except Exception as e:
        console.print(f"[red]Failed to queue job: {e}[/red]")
        console.print("\nMake sure RabbitMQ is running:")
        console.print("  docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:management")
        raise typer.Exit(1)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to bind to"),
    port: int = typer.Option(8000, "--port", help="Port to bind to"),
):
    """
    Start the web API server with built-in GUI.
    """
    console.print(f"[bold green]Starting CodeSearch server on http://{host}:{port}[/bold green]")
    console.print("🌐 Web GUI: http://{host}:{port}/")
    console.print("📚 API docs: http://{host}:{port}/docs")
    
    try:
        import uvicorn
        from ..api import create_app
        
        api_app = create_app()
        uvicorn.run(api_app, host=host, port=port)
    except ImportError:
        console.print("[red]FastAPI/uvicorn not installed. Install with:[/red]")
        console.print("  pip install fastapi uvicorn")
        raise typer.Exit(1)


@app.command()
def version():
    """Show version information."""
    from .. import __version__
    
    console.print(f"\n[bold blue]CodeSearch[/bold blue] v{__version__}")
    console.print("Semantic Code Search Engine\n")


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()

