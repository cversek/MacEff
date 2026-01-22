"""
LanceDB Policy Search - Production implementation.

Provides semantic and hybrid search capabilities using LanceDB.

Breadcrumb: s_77270981/c_356/g_a76f3cd/p_0c1e0209/t_1768946900
"""

import time
from pathlib import Path
from typing import Optional

import lancedb
from sentence_transformers import SentenceTransformer


class LanceDBPolicySearch:
    """Policy search using LanceDB with lazy model loading."""

    def __init__(self, db_path: Path, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize LanceDB search.

        Args:
            db_path: Path to LanceDB directory
            model_name: SentenceTransformer model name (lazy loaded)
        """
        self.db_path = db_path
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._db = None
        self._table = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load embedding model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def table(self):
        """Lazy load LanceDB table."""
        if self._table is None:
            self._db = lancedb.connect(str(self.db_path))
            self._table = self._db.open_table("policies")
        return self._table

    def semantic_search(self, query: str, limit: int = 5) -> dict:
        """
        Pure vector similarity search.

        Args:
            query: Search query text
            limit: Maximum number of results

        Returns:
            Dict with query, results list, and latency_ms
        """
        start = time.time()
        query_embedding = self.model.encode(query)

        results = (
            self.table.search(query_embedding)
            .limit(limit)
            .to_list()
        )

        latency_ms = (time.time() - start) * 1000

        return {
            'query': query,
            'results': [
                {
                    'policy_name': r['policy_name'],
                    'distance': r['_distance'],
                    'similarity': 1 - r['_distance'],  # Convert to similarity
                    'tier': r.get('tier', ''),
                    'category': r.get('category', ''),
                }
                for r in results
            ],
            'latency_ms': latency_ms,
        }

    def hybrid_search(self, query: str, limit: int = 5) -> dict:
        """
        Hybrid search combining vector similarity with FTS.

        LanceDB native hybrid search uses both vector and FTS if available.
        Falls back to semantic-only if FTS index doesn't exist.

        Args:
            query: Search query text
            limit: Maximum number of results

        Returns:
            Dict with query, search_type, results list, and latency_ms
        """
        start = time.time()
        query_embedding = self.model.encode(query)

        # Try hybrid search with FTS
        try:
            # LanceDB hybrid: vector + FTS reranking
            results = (
                self.table.search(query_embedding, query_type="hybrid")
                .limit(limit)
                .to_list()
            )
            search_type = "hybrid"
        except (AttributeError, Exception):
            # Fallback to semantic-only if FTS not available
            results = (
                self.table.search(query_embedding)
                .limit(limit)
                .to_list()
            )
            search_type = "semantic"

        latency_ms = (time.time() - start) * 1000

        return {
            'query': query,
            'search_type': search_type,
            'results': [
                {
                    'policy_name': r['policy_name'],
                    'distance': r['_distance'],  # Lower = closer = better match
                    'similarity': 1 - r['_distance'],
                    'tier': r.get('tier', ''),
                    'category': r.get('category', ''),
                }
                for r in results
            ],
            'latency_ms': latency_ms,
        }

    def check_fts_support(self) -> dict:
        """
        Check if LanceDB FTS is available and create index if needed.

        Returns:
            Dict with fts_available bool and message string
        """
        try:
            # LanceDB 0.4+ has create_fts_index
            self.table.create_fts_index("content", replace=True)
            return {'fts_available': True, 'message': 'FTS index created'}
        except AttributeError:
            return {'fts_available': False, 'message': 'FTS not available in this version'}
        except Exception as e:
            return {'fts_available': False, 'message': str(e)}


def run_test_queries(searcher: LanceDBPolicySearch) -> list[dict]:
    """Run standard test queries for validation."""
    test_queries = [
        "How do I backup TODOs?",
        "What is the git commit protocol?",
        "When should I create checkpoints?",
        "How do experiments differ from observations?",
        "What are the delegation guidelines?",
    ]

    results = []
    for query in test_queries:
        result = searcher.semantic_search(query, limit=5)
        results.append(result)
        print(f"\nQuery: {query}")
        print(f"Latency: {result['latency_ms']:.1f}ms")
        for i, r in enumerate(result['results'][:3], 1):
            print(f"  {i}. {r['policy_name']} (similarity: {r['similarity']:.3f})")

    return results


if __name__ == "__main__":
    from .utils.paths import find_agent_home

    agent_home = find_agent_home()
    db_path = agent_home / ".maceff" / "policy_index.lance"

    if not db_path.exists():
        print(f"Index not found: {db_path}")
        print("Run: python -m macf.hybrid_search.lancedb_indexer")
        exit(1)

    print("Loading LanceDB search...")
    load_start = time.time()
    searcher = LanceDBPolicySearch(db_path)
    load_time = (time.time() - load_start) * 1000
    print(f"Loaded in {load_time:.0f}ms")

    # Check FTS support
    print("\nChecking FTS support...")
    fts_status = searcher.check_fts_support()
    print(f"FTS: {fts_status}")

    # Run test queries
    print("\n=== Running Test Queries ===")
    results = run_test_queries(searcher)

    # Calculate average latency
    avg_latency = sum(r['latency_ms'] for r in results) / len(results)
    print(f"\n=== Summary ===")
    print(f"Average query latency: {avg_latency:.1f}ms")
    print(f"Model load time: {load_time:.0f}ms")
