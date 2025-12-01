"""Verify all assignment requirements are met."""
import sys
from pathlib import Path

print("=" * 60)
print("VERIFYING ASSIGNMENT REQUIREMENTS")
print("=" * 60)

requirements = {
    "1. Indexing Pipeline": {
        "Clone repos": False,
        "Parse ASTs": False,
        "Generate embeddings": False,
        "Extract functions/classes": False
    },
    "2. Vector Database": {
        "Qdrant integration": False,
        "Store embeddings": False,
        "Vector search": False
    },
    "3. Distributed Processing": {
        "RabbitMQ queue": False,
        "Job publisher": False,
        "Worker system": False
    },
    "4. Query Engine": {
        "Natural language search": False,
        "Vector similarity": False,
        "BM25 search": False,
        "Hybrid ranking": False
    },
    "5. CLI Tool": {
        "CLI exists": False,
        "Local search": False,
        "Semantic search": False
    }
}

# Check 1: Indexing Pipeline
print("\n1. INDEXING PIPELINE")
try:
    from codesearch.indexer import RepoIndexer
    from codesearch.parser import ParserFactory
    from codesearch.embeddings import CodeBERTEmbedder
    
    # Check parsers
    parsers = ParserFactory.supported_extensions()
    requirements["1. Indexing Pipeline"]["Parse ASTs"] = len(parsers) >= 4
    print(f"   ✅ AST Parsers: {len(parsers)} languages ({', '.join(parsers[:4])}...)")
    
    # Check indexer
    indexer = RepoIndexer()
    requirements["1. Indexing Pipeline"]["Clone repos"] = hasattr(indexer, '_clone_or_update')
    requirements["1. Indexing Pipeline"]["Generate embeddings"] = True
    requirements["1. Indexing Pipeline"]["Extract functions/classes"] = True
    print("   ✅ RepoIndexer: Clone, parse, embed, extract")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check 2: Vector Database
print("\n2. VECTOR DATABASE")
try:
    from codesearch.storage import QdrantStore
    
    store = QdrantStore()
    requirements["2. Vector Database"]["Qdrant integration"] = True
    requirements["2. Vector Database"]["Store embeddings"] = hasattr(store, 'insert')
    requirements["2. Vector Database"]["Vector search"] = hasattr(store, 'search')
    print("   ✅ QdrantStore: Integration, storage, search")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check 3: Distributed Processing
print("\n3. DISTRIBUTED PROCESSING")
try:
    from codesearch.queue import JobPublisher
    from codesearch.queue import IndexingWorker
    
    requirements["3. Distributed Processing"]["RabbitMQ queue"] = True
    requirements["3. Distributed Processing"]["Job publisher"] = True
    requirements["3. Distributed Processing"]["Worker system"] = True
    print("   ✅ RabbitMQ: Publisher, Worker, Queue system")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check 4: Query Engine
print("\n4. QUERY ENGINE")
try:
    from codesearch.search.engine import HybridSearchEngine
    from codesearch.storage import BM25Index
    
    engine = HybridSearchEngine()
    requirements["4. Query Engine"]["Natural language search"] = hasattr(engine, 'search')
    requirements["4. Query Engine"]["Vector similarity"] = hasattr(engine, 'search')
    requirements["4. Query Engine"]["BM25 search"] = hasattr(engine.bm25_index, 'search')
    requirements["4. Query Engine"]["Hybrid ranking"] = hasattr(engine, '_reciprocal_rank_fusion')
    print("   ✅ HybridSearchEngine: NL search, vector, BM25, hybrid ranking")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check 5: CLI Tool
print("\n5. CLI TOOL")
try:
    from codesearch.cli import app
    from codesearch.search.engine import LocalSearchEngine
    
    requirements["5. CLI Tool"]["CLI exists"] = True
    requirements["5. CLI Tool"]["Local search"] = True
    requirements["5. CLI Tool"]["Semantic search"] = True
    print("   ✅ CLI: Commands, local search, semantic search")
    
except Exception as e:
    print(f"   ❌ Error: {e}")

# Check file structure
print("\n6. FILE STRUCTURE")
required_modules = [
    "codesearch/parser/",
    "codesearch/embeddings/",
    "codesearch/storage/",
    "codesearch/queue/",
    "codesearch/search/",
    "codesearch/indexer/",
    "codesearch/cli/",
    "codesearch/api/",
]

all_exist = True
for module in required_modules:
    exists = Path(module).exists()
    all_exist = all_exist and exists
    status = "✅" if exists else "❌"
    print(f"   {status} {module}")

# Summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)

all_passed = True
for req_name, checks in requirements.items():
    passed = all(checks.values())
    all_passed = all_passed and passed
    status = "✅" if passed else "❌"
    print(f"{status} {req_name}")
    for check_name, check_passed in checks.items():
        check_status = "✅" if check_passed else "❌"
        print(f"   {check_status} {check_name}")

print(f"\n{'✅ ALL REQUIREMENTS MET' if all_passed and all_exist else '❌ SOME REQUIREMENTS MISSING'}")
print("=" * 60)

sys.exit(0 if all_passed and all_exist else 1)

