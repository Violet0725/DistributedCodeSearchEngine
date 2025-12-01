"""
Gradio-based GUI for CodeSearch.

A beautiful, interactive interface for semantic code search.
"""

from typing import Optional, List, Tuple
import structlog

logger = structlog.get_logger()


def create_gradio_app():
    """
    Create and return a Gradio app for CodeSearch.
    
    Requires gradio to be installed: pip install gradio
    """
    try:
        import gradio as gr
    except ImportError:
        raise RuntimeError(
            "Gradio not installed. Install with: pip install gradio"
        )
    
    from ..search.engine import HybridSearchEngine, LocalSearchEngine
    from ..models import Language, CodeEntityType
    
    # Initialize search engines
    _hybrid_engine = None
    _local_engine = None
    
    def get_hybrid_engine():
        nonlocal _hybrid_engine
        if _hybrid_engine is None:
            _hybrid_engine = HybridSearchEngine()
        return _hybrid_engine
    
    def get_local_engine():
        nonlocal _local_engine
        if _local_engine is None:
            _local_engine = LocalSearchEngine()
        return _local_engine
    
    def format_result(result, show_code: bool = False) -> str:
        """Format a search result as markdown."""
        entity = result.entity
        
        # Header with badges
        icon = {
            CodeEntityType.FUNCTION: "⚡",
            CodeEntityType.METHOD: "🔧",
            CodeEntityType.CLASS: "📦",
            CodeEntityType.STRUCT: "🏗️",
            CodeEntityType.INTERFACE: "📋",
            CodeEntityType.ENUM: "📊",
        }.get(entity.entity_type, "•")
        
        md = f"### {icon} `{entity.name}`"
        if entity.parent_class:
            md += f" · {entity.parent_class}"
        md += "\n\n"
        
        # Badges
        md += f"**{entity.language.value.upper()}** · **{entity.entity_type.value}** · "
        md += f"Score: **{result.score:.3f}**\n\n"
        
        # Signature
        if entity.signature:
            md += f"```\n{entity.signature}\n```\n\n"
        
        # Docstring
        if entity.docstring:
            md += f"*{entity.docstring[:300]}{'...' if len(entity.docstring) > 300 else ''}*\n\n"
        
        # Location
        md += f"📁 `{entity.repo_name}` · 📄 `{entity.file_path}:{entity.start_line}`\n\n"
        
        # Source code
        if show_code and entity.source_code:
            lang = entity.language.value
            code = entity.source_code[:2000]
            if len(entity.source_code) > 2000:
                code += "\n# ... (truncated)"
            md += f"<details>\n<summary>View Source Code</summary>\n\n```{lang}\n{code}\n```\n\n</details>\n"
        
        md += "---\n\n"
        return md
    
    def search(
        query: str,
        language: str,
        entity_type: str,
        limit: int,
        show_code: bool,
        use_hybrid: bool,
        local_dir: str
    ) -> str:
        """Perform search and return formatted results."""
        if not query.strip():
            return "Please enter a search query."
        
        try:
            # Parse filters
            lang_filter = None
            if language and language != "All":
                try:
                    lang_filter = Language(language.lower())
                except ValueError:
                    pass
            
            type_filter = None
            if entity_type and entity_type != "All":
                try:
                    type_filter = CodeEntityType(entity_type.lower())
                except ValueError:
                    pass
            
            # Choose engine
            if local_dir and local_dir.strip():
                # Local search
                engine = get_local_engine()
                try:
                    indexed = engine.index_directory(local_dir.strip())
                    results = engine.search(query, limit=limit)
                    header = f"## 🔍 Local Search Results\n\n"
                    header += f"*Indexed {indexed} entities from `{local_dir}`*\n\n"
                except FileNotFoundError:
                    return f"❌ Directory not found: `{local_dir}`"
            else:
                # Full search
                engine = get_hybrid_engine()
                results = engine.search(
                    query=query,
                    limit=limit,
                    language=lang_filter,
                    entity_type=type_filter,
                    use_hybrid=use_hybrid
                )
                header = f"## 🔍 Search Results\n\n"
            
            if not results:
                return header + "No results found. Try a different query or adjust filters."
            
            header += f"*Found **{len(results)}** results for \"{query}\"*\n\n---\n\n"
            
            # Format results
            output = header
            for result in results:
                output += format_result(result, show_code)
            
            return output
            
        except Exception as e:
            logger.error("Search error", error=str(e))
            return f"❌ Search error: {str(e)}"
    
    # Custom CSS for dark theme
    custom_css = """
    .gradio-container {
        font-family: 'Segoe UI', system-ui, sans-serif !important;
    }
    .dark {
        --body-background-fill: #0a0a0f !important;
        --block-background-fill: #12121a !important;
        --block-border-color: #2a2a3a !important;
        --input-background-fill: #1a1a25 !important;
        --button-primary-background-fill: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%) !important;
        --button-primary-background-fill-hover: linear-gradient(135deg, #7779f5 0%, #9d6ff9 100%) !important;
    }
    .result-container {
        max-height: 70vh;
        overflow-y: auto;
    }
    """
    
    # Build the interface
    with gr.Blocks(
        title="CodeSearch - Semantic Code Search",
        theme=gr.themes.Soft(
            primary_hue="indigo",
            secondary_hue="purple",
            neutral_hue="slate",
        ),
        css=custom_css
    ) as app:
        
        gr.Markdown("""
        # 🔍 CodeSearch
        ### Find code by what it does, not just syntax
        
        Enter a natural language query to search through indexed code semantically.
        """)
        
        with gr.Row():
            with gr.Column(scale=4):
                query_input = gr.Textbox(
                    label="Search Query",
                    placeholder="e.g., 'async HTTP client with retry logic'",
                    lines=1,
                    max_lines=1
                )
            with gr.Column(scale=1):
                search_btn = gr.Button("🔍 Search", variant="primary", size="lg")
        
        with gr.Row():
            with gr.Column():
                language_filter = gr.Dropdown(
                    choices=["All", "Python", "JavaScript", "TypeScript", "Go", "Rust"],
                    value="All",
                    label="Language"
                )
            with gr.Column():
                type_filter = gr.Dropdown(
                    choices=["All", "function", "method", "class", "struct", "interface", "enum"],
                    value="All",
                    label="Entity Type"
                )
            with gr.Column():
                limit_slider = gr.Slider(
                    minimum=5,
                    maximum=50,
                    value=10,
                    step=5,
                    label="Max Results"
                )
        
        with gr.Row():
            with gr.Column():
                show_code = gr.Checkbox(label="Show Source Code", value=False)
            with gr.Column():
                use_hybrid = gr.Checkbox(label="Hybrid Search (Semantic + BM25)", value=True)
        
        with gr.Accordion("🗂️ Local Directory Search", open=False):
            local_dir_input = gr.Textbox(
                label="Local Directory Path",
                placeholder="./my-project or C:\\path\\to\\code",
                lines=1
            )
            gr.Markdown("*Leave empty to search the main index. Fill in to search a local directory.*")
        
        gr.Markdown("---")
        
        results_output = gr.Markdown(
            value="""
            ## 💡 Search Tips
            
            - **Natural Language**: "function to parse JSON into dictionary"
            - **Be Specific**: "async HTTP POST request with authentication"
            - **Describe Behavior**: "validate email address format with regex"
            - **Implementation**: "sort array using quicksort algorithm"
            
            ---
            
            *Start by entering a query above!*
            """,
            elem_classes=["result-container"]
        )
        
        # Event handlers
        search_btn.click(
            fn=search,
            inputs=[
                query_input,
                language_filter,
                type_filter,
                limit_slider,
                show_code,
                use_hybrid,
                local_dir_input
            ],
            outputs=results_output
        )
        
        query_input.submit(
            fn=search,
            inputs=[
                query_input,
                language_filter,
                type_filter,
                limit_slider,
                show_code,
                use_hybrid,
                local_dir_input
            ],
            outputs=results_output
        )
        
        gr.Markdown("""
        ---
        
        **CodeSearch** - Semantic Code Search Engine | 
        [API Docs](/docs) | 
        Powered by Qdrant & Transformers
        """)
    
    return app


def launch_gui(
    server_name: str = "127.0.0.1",
    server_port: int = 7860,
    share: bool = False,
    **kwargs
):
    """
    Launch the Gradio GUI.
    
    Args:
        server_name: Host to bind to
        server_port: Port to bind to
        share: Create a public Gradio link
        **kwargs: Additional arguments passed to gr.Blocks.launch()
    """
    app = create_gradio_app()
    app.launch(
        server_name=server_name,
        server_port=server_port,
        share=share,
        **kwargs
    )

