# 🔍 CodeSearch

**Distributed Code Search Engine with Semantic Understanding**

Find code by *what it does*, not just syntax matching. CodeSearch uses AI-powered embeddings to understand the semantic meaning of code, enabling natural language queries like "function to parse JSON" or "async HTTP client implementation".

## ✨ Features

- **Semantic Search**: Search code using natural language queries
- **Multi-Language Support**: Python, JavaScript/TypeScript, Go, Rust
- **Hybrid Search**: Combines semantic understanding with BM25 keyword matching
- **Distributed Processing**: Scale indexing across multiple workers with RabbitMQ
- **Vector Database**: Store millions of code embeddings with Qdrant
- **Beautiful CLI**: Rich terminal interface with syntax highlighting
- **REST API**: Easy integration with other tools and services

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CLI / API     │────▶│  Search Engine  │────▶│  Qdrant Vector  │
│                 │     │  (Hybrid BM25+  │     │    Database     │
│                 │     │   Semantic)     │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │                       │
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   RabbitMQ      │     │  CodeBERT       │
│   Job Queue     │     │  Embeddings     │
└─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐
│  Index Workers  │
│  (Distributed)  │
└─────────────────┘
```

## 🖥️ GUI Options

### Web GUI (Built-in)

Launch the API server and access the modern web interface:

```bash
codesearch serve
# Open http://localhost:8000
```

**Features:**
- 🎨 Beautiful dark theme with syntax highlighting
- ⚡ Real-time search with filters
- 📊 Index statistics dashboard
- 🔍 Expandable source code previews
- 🗂️ **Local Search Mode** - Search local directories without Docker/Qdrant (checkbox in GUI)
- 🧠 Smart hybrid search - Auto-detects quality and optimizes results

**Local Search Mode:**
- ✅ Works without Docker/Qdrant
- ✅ Search any local directory instantly
- ✅ Uses BM25 keyword search (fast and accurate)
- ✅ Perfect for quick code exploration

### Gradio GUI

Alternative interface using Gradio (great for quick demos):

```bash
pip install gradio
codesearch gui
# Open http://localhost:7860
```

Features:
- 🎯 Simple, clean interface
- 📁 Local directory search without indexing
- 🌐 Optional public sharing link
- 📱 Mobile-friendly

## 🚀 Quick Start

### Option A: Quick Start (No Docker - Local Search Only)

```bash
# Install
pip install -r requirements.txt
pip install -e .

# Search local code immediately (no setup needed!)
codesearch search "your query" --local ./your-project

# Or use the web GUI
codesearch serve
# Open http://localhost:8000 and enable "Local Search Mode"
```

### Option B: Full Setup (With Docker - Semantic Search)

```bash
# Install
pip install -r requirements.txt
pip install -e .

# Start Qdrant
docker run -d -p 8001:6333 --name qdrant qdrant/qdrant

# Index a repo
$env:QDRANT_PORT=8001  # Windows
codesearch index https://github.com/psf/requests

# Search with semantic understanding
codesearch search "send HTTP request"
```

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/codesearch.git
cd codesearch

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install tree-sitter parsers (optional but recommended for better parsing)
pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-go tree-sitter-rust

# Install the package
pip install -e .
```

### Start Infrastructure

**Option 1: With Docker (Full Semantic Search)**

```bash
# Using Docker Compose (recommended)
docker-compose up -d qdrant rabbitmq

# Or manually:
# Qdrant (if port 6333 is blocked, use alternative port)
docker run -d -p 8001:6333 --name qdrant qdrant/qdrant
# Then set: $env:QDRANT_PORT=8001  (Windows) or export QDRANT_PORT=8001 (Linux/Mac)

# RabbitMQ
docker run -d -p 5672:5672 -p 15672:15672 rabbitmq:management
```

**Option 2: Without Docker (Local Search Only)**

No setup needed! Use `--local` flag for CLI or enable "Local Search Mode" in the web GUI.

### Index Your First Repository

```bash
# Index a GitHub repository
codesearch index https://github.com/pallets/flask

# Or index a local directory
codesearch index ./my-project --name my-project
```

### Search!

```bash
# Natural language search
codesearch search "function to handle HTTP requests"

# Filter by language
codesearch search "async database query" --lang python

# Show source code
codesearch search "JSON parser" --code

# Search local directory only (no server needed)
codesearch search "sort algorithm" --local ./algorithms
```

## 📖 CLI Commands

### `codesearch search`

Search for code using natural language.

```bash
codesearch search "function to validate email" [OPTIONS]

Options:
  -n, --limit INTEGER    Number of results (default: 10)
  -l, --lang TEXT        Filter by language (python, js, go, rust)
  -r, --repo TEXT        Filter by repository name
  -t, --type TEXT        Filter by type (function, class, method)
  -c, --code             Show source code
  --local PATH           Search local directory instead
  --hybrid/--semantic-only  Toggle hybrid search (default: hybrid)
```

### `codesearch index`

Index a repository or local directory.

```bash
codesearch index <URL_OR_PATH> [OPTIONS]

Options:
  -n, --name TEXT      Repository name
  -b, --branch TEXT    Git branch (default: main)
  -f, --force          Force re-clone
```

### `codesearch worker`

Start an indexing worker.

```bash
codesearch worker [OPTIONS]

Options:
  -w, --workers INTEGER  Number of workers (default: 1)
```

### `codesearch queue`

Queue a repository for background indexing.

```bash
codesearch queue <REPO_URL> [OPTIONS]

Options:
  -n, --name TEXT        Repository name
  -p, --priority INTEGER Job priority 0-10 (default: 5)
```

### `codesearch serve`

Start the REST API server with built-in web GUI.

```bash
codesearch serve [OPTIONS]

Options:
  --host TEXT   Host to bind (default: 127.0.0.1)
  --port INTEGER  Port (default: 8000)
```

### `codesearch gui`

Launch the Gradio GUI (alternative interface).

```bash
codesearch gui [OPTIONS]

Options:
  --host TEXT      Host to bind (default: 127.0.0.1)
  --port INTEGER   Port (default: 7860)
  --share          Create public Gradio link
```

## 🌐 REST API

### Search

```bash
# POST /search
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "async HTTP client", "language": "python", "limit": 10}'

# GET /search (convenience)
curl "http://localhost:8000/search?q=parse+JSON&limit=5"
```

### Index

```bash
# Queue for indexing
curl -X POST http://localhost:8000/index \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/user/repo"}'

# Synchronous indexing (blocking)
curl -X POST http://localhost:8000/index/sync \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/user/repo"}'
```

### Local Search (No Docker Needed)

```bash
# Search local directory via API
curl -X POST "http://localhost:8000/search/local?query=parse+JSON&path=./my-project&limit=10"
```

### Stats

```bash
curl http://localhost:8000/stats
```

## 🐳 Docker Deployment

### Full Stack

```bash
# Start all services
docker-compose up -d

# Scale workers
docker-compose up -d --scale worker=4
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | REST API server + Web GUI |
| Qdrant | 6333 (or 8001) | Vector database (use 8001 if 6333 blocked) |
| RabbitMQ | 5672, 15672 | Message queue (15672 = management UI) |
| Worker | - | Indexing workers |
| Gradio GUI | 7860 | Alternative GUI interface |

## ⚙️ Configuration

Configuration via environment variables or `.env` file:

```bash
# Copy example config
cp env.example .env
```

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | localhost | Qdrant host |
| `QDRANT_PORT` | 6333 | Qdrant port (use 8001 if 6333 is blocked on Windows) |
| `RABBITMQ_HOST` | localhost | RabbitMQ host |
| `EMBEDDING_MODEL` | microsoft/codebert-base | Model for embeddings (default uses CodeBERT) |
| `BATCH_SIZE` | 32 | Embedding batch size |
| `GITHUB_TOKEN` | - | GitHub API token (optional) |

**Note:** On Windows, if port 6333 is blocked, start Qdrant on port 8001 and set `QDRANT_PORT=8001`:
```bash
docker run -d -p 8001:6333 --name qdrant qdrant/qdrant
# Windows PowerShell:
$env:QDRANT_PORT=8001
codesearch index https://github.com/user/repo
```

### Embedding Models

Recommended models:

| Model | Size | Speed | Quality |
|-------|------|-------|---------|
| `sentence-transformers/all-MiniLM-L6-v2` | 80MB | Fast | Good |
| `microsoft/codebert-base` | 500MB | Medium | Best for code |
| `Salesforce/codet5-base` | 900MB | Slow | Excellent |

## 🔧 Supported Languages

| Language | Extensions | Entity Types |
|----------|------------|--------------|
| Python | `.py` | functions, methods, classes |
| JavaScript | `.js`, `.jsx`, `.mjs` | functions, classes, methods |
| TypeScript | `.ts`, `.tsx` | functions, classes, methods, interfaces |
| Go | `.go` | functions, methods, structs, interfaces |
| Rust | `.rs` | functions, methods, structs, enums, traits |

## 📊 How It Works

1. **Indexing Pipeline**:
   - Clone/scan repository
   - Parse source files using tree-sitter ASTs
   - Extract code entities (functions, classes, etc.)
   - Generate embeddings using transformer models
   - Store vectors in Qdrant + build BM25 index

2. **Search Pipeline**:
   - Enhance natural language query with context
   - Convert query to embedding using CodeBERT
   - Perform vector similarity search (semantic)
   - Perform BM25 keyword search (lexical)
   - Auto-detect semantic search quality
   - Merge results using Reciprocal Rank Fusion (with smart weighting)
   - Return ranked results with scores

## 🧪 Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black codesearch/
isort codesearch/

# Type checking
mypy codesearch/
```

## 🔧 Troubleshooting

### Port Issues on Windows

If Qdrant port 6333 is blocked:
```bash
# Use alternative port
docker run -d -p 8001:6333 --name qdrant qdrant/qdrant

# Set environment variable
$env:QDRANT_PORT=8001  # PowerShell
export QDRANT_PORT=8001  # Bash
```

### Tree-sitter Not Installed

Parser will use fallback regex parsing (works but less accurate):
```bash
pip install tree-sitter tree-sitter-python tree-sitter-javascript tree-sitter-go tree-sitter-rust
```

### Semantic Search Returns Irrelevant Results

The hybrid search automatically detects this and prioritizes BM25 keyword search. For best results:
- Use specific queries: "HTTP GET request" instead of "request"
- Try BM25-only mode: Uncheck "Hybrid Search" in GUI
- Use local search mode for instant keyword-based results

### Search Returns Empty Results

1. **Check if indexed**: Run `codesearch stats`
2. **Index a repo**: `codesearch index https://github.com/user/repo`
3. **Use local search**: `codesearch search "query" --local ./path`

## 🙏 Acknowledgments

- [Qdrant](https://qdrant.tech/) - Vector database
- [sentence-transformers](https://www.sbert.net/) - Embedding models
- [tree-sitter](https://tree-sitter.github.io/) - AST parsing
- [Rich](https://rich.readthedocs.io/) - Beautiful terminal output
- [Typer](https://typer.tiangolo.com/) - CLI framework

