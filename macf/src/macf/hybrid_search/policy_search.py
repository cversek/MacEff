"""
Policy Search - Production implementation.

Provides semantic and hybrid search capabilities for MacEff policies.
Includes document search and CEP question search for section targeting.
"""

import time
from pathlib import Path
from typing import Optional

import lancedb
from sentence_transformers import SentenceTransformer

from .models import MatchedQuestion


class PolicySearch:
    """Policy search with lazy model loading and question support."""

    def __init__(self, db_path: Path, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize policy search.

        Args:
            db_path: Path to LanceDB directory
            model_name: SentenceTransformer model name (lazy loaded)
        """
        self.db_path = db_path
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self._db = None
        self._documents_table = None
        self._questions_table = None

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load embedding model."""
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def db(self):
        """Lazy load LanceDB connection."""
        if self._db is None:
            self._db = lancedb.connect(str(self.db_path))
        return self._db

    @property
    def documents_table(self):
        """Lazy load documents table."""
        if self._documents_table is None:
            self._documents_table = self.db.open_table("documents")
        return self._documents_table

    @property
    def questions_table(self):
        """Lazy load questions table (may not exist)."""
        if self._questions_table is None:
            try:
                self._questions_table = self.db.open_table("questions")
            except Exception:
                # Questions table doesn't exist - graceful degradation
                self._questions_table = False  # Sentinel for "tried and failed"
        return self._questions_table if self._questions_table is not False else None

    def semantic_search(self, query: str, limit: int = 5) -> dict:
        """
        Pure vector similarity search on documents.

        Args:
            query: Search query text
            limit: Maximum number of results

        Returns:
            Dict with query, results list, and latency_ms
        """
        start = time.time()
        query_embedding = self.model.encode(query)

        results = (
            self.documents_table.search(query_embedding)
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
                self.documents_table.search(query_embedding, query_type="hybrid")
                .limit(limit)
                .to_list()
            )
            search_type = "hybrid"
        except (AttributeError, Exception):
            # Fallback to semantic-only if FTS not available
            results = (
                self.documents_table.search(query_embedding)
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

    def search_questions(self, query: str, limit: int = 10) -> list[MatchedQuestion]:
        """
        Search CEP questions for section targeting.

        Finds questions semantically similar to the query, enabling
        fine-grained section recommendations (e.g., "→ §5 'How do I...'").

        Args:
            query: Search query text
            limit: Maximum number of questions to return

        Returns:
            List of MatchedQuestion objects, sorted by distance (best first).
            Returns empty list if questions table doesn't exist.
        """
        if self.questions_table is None:
            # Graceful degradation - no questions indexed
            return []

        query_embedding = self.model.encode(query)

        results = (
            self.questions_table.search(query_embedding)
            .limit(limit)
            .to_list()
        )

        return [
            MatchedQuestion(
                question_text=r['question_text'],
                section_number=r['section_number'],
                section_header=r['section_header'],
                policy_name=r['policy_name'],
                distance=r['_distance'],
            )
            for r in results
        ]

    def check_fts_support(self) -> dict:
        """
        Check if LanceDB FTS is available and create index if needed.

        Returns:
            Dict with fts_available bool and message string
        """
        try:
            # LanceDB 0.4+ has create_fts_index
            self.documents_table.create_fts_index("content", replace=True)
            return {'fts_available': True, 'message': 'FTS index created'}
        except AttributeError:
            return {'fts_available': False, 'message': 'FTS not available in this version'}
        except Exception as e:
            return {'fts_available': False, 'message': str(e)}


def run_test_queries(searcher: PolicySearch) -> list[dict]:
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

        # Also test question search
        questions = searcher.search_questions(query, limit=3)
        if questions:
            print("  Questions:")
            for q in questions:
                print(f"    → §{q.section_number} \"{q.question_text[:50]}...\" (dist: {q.distance:.3f})")

    return results


if __name__ == "__main__":
    from ..utils.paths import find_agent_home

    agent_home = find_agent_home()
    db_path = agent_home / ".maceff" / "policy_index.lance"

    if not db_path.exists():
        print(f"Index not found: {db_path}")
        print("Run: macf_tools policy build_index")
        exit(1)

    print("Loading policy search...")
    load_start = time.time()
    searcher = PolicySearch(db_path)
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
