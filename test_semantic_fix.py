"""Test if semantic search is fixed."""
from codesearch.search.engine import HybridSearchEngine

print("=== TESTING FIXED SEMANTIC SEARCH ===\n")

engine = HybridSearchEngine()

queries = [
    "send HTTP request",
    "HTTP GET POST",
    "parse JSON response",
]

for query in queries:
    print(f"Query: '{query}'")
    results = engine.search(query, limit=5, use_hybrid=True)
    
    for i, r in enumerate(results, 1):
        # Check relevance
        keywords = ["http", "request", "get", "post", "json", "send", "parse"]
        is_relevant = any(
            keyword in r.entity.name.lower() or 
            keyword in (r.entity.docstring or "").lower() or
            keyword in (r.entity.signature or "").lower()
            for keyword in keywords
        )
        relevance = "✅" if is_relevant else "❌"
        
        print(f"   {i}. {relevance} {r.entity.name:30} | Sem: {r.semantic_score:.4f} | BM25: {r.bm25_score:.4f} | Combined: {r.score:.4f}")
    print()

