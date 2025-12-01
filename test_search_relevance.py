"""Test search result relevance."""
from codesearch.search.engine import HybridSearchEngine
from codesearch.storage import BM25Index

print("=== TESTING SEARCH RESULT RELEVANCE ===\n")

engine = HybridSearchEngine()

# Test queries
queries = [
    "send HTTP request",
    "HTTP GET POST",
    "parse JSON response",
    "handle authentication",
    "download file from URL"
]

print("1. HYBRID SEARCH RESULTS:\n")
for query in queries:
    print(f"Query: '{query}'")
    results = engine.search(query, limit=5)
    for i, r in enumerate(results, 1):
        keywords = ["http", "request", "get", "post", "json", "auth", "download", "url", "send"]
        is_relevant = any(
            keyword in r.entity.name.lower() or 
            keyword in (r.entity.docstring or "").lower() or
            keyword in (r.entity.signature or "").lower()
            for keyword in keywords
        )
        relevance = "✅" if is_relevant else "❌"
        print(f"   {i}. {relevance} {r.entity.name:30} | {r.entity.file_path.split(chr(92))[-1]:25} | Score: {r.score:.4f}")
    print()

print("\n2. BM25 KEYWORD SEARCH (for comparison):\n")
bm25_idx = BM25Index()
bm25_idx.load()
for query in queries[:2]:  # Test first 2
    print(f"Query: '{query}'")
    results = bm25_idx.search(query, limit=5)
    for i, (entity, score) in enumerate(results, 1):
        keywords = ["http", "request", "get", "post", "send"]
        is_relevant = any(
            keyword in entity.name.lower() or 
            keyword in (entity.docstring or "").lower()
            for keyword in keywords
        )
        relevance = "✅" if is_relevant else "❌"
        print(f"   {i}. {relevance} {entity.name:30} | {entity.file_path.split(chr(92))[-1]:25} | Score: {score:.2f}")
    print()

print("\n3. CHECKING KEY FUNCTIONS:\n")
key_functions = ['get', 'post', 'send', 'request', 'json', 'auth']
for func_name in key_functions:
    results = engine.search(f"{func_name} function", limit=3)
    found = [r for r in results if func_name in r.entity.name.lower()]
    if found:
        print(f"   ✓ '{func_name}': Found {found[0].entity.name} (score: {found[0].score:.4f})")
    else:
        print(f"   ✗ '{func_name}': Not in top 3 results")

