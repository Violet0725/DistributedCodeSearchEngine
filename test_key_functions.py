"""Test if key functions are findable."""
from codesearch.storage import BM25Index

idx = BM25Index()
idx.load()

print("=== KEY FUNCTIONS SEARCH TEST ===\n")

# Test direct searches
test_cases = [
    ("get", "get function HTTP"),
    ("post", "post function HTTP"),
    ("send", "send request"),
    ("request", "make request"),
]

for func_name, query in test_cases:
    results = idx.search(query, limit=5)
    found = [r for r in results if func_name in r[0].name.lower() and ("api.py" in r[0].file_path or "sessions.py" in r[0].file_path)]
    if found:
        print(f"✅ '{query}' → Found: {found[0][0].name} (score: {found[0][1]:.2f})")
    else:
        print(f"❌ '{query}' → Not found")
        print(f"   Top result: {results[0][0].name if results else 'None'}")

