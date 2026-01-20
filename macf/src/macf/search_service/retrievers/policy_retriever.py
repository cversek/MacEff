"""
PolicyRetriever - Policy-specific RRF hybrid search.

Wraps the existing recommend.py logic (4-retriever RRF fusion) for use
with the SearchService daemon. Reuses all existing search infrastructure.

This is a thin adapter - the heavy lifting is done by macf.utils.recommend.
"""

import time
from typing import Optional

from .base import AbstractRetriever, SearchResult


class PolicyRetriever(AbstractRetriever):
    """Policy search using RRF fusion with 4 retrievers.

    Uses existing infrastructure from macf.utils.recommend:
    - FTS5 BM25 on policies_fts
    - FTS5 BM25 on questions_fts
    - Cosine similarity on policy_embeddings
    - Cosine similarity on question_embeddings

    The embedding model is loaded lazily on first search (or via warmup).
    """

    def __init__(self):
        self._recommend_func: Optional[callable] = None
        self._warmed_up = False

    @property
    def namespace(self) -> str:
        return "policy"

    def warmup(self) -> None:
        """Pre-load the recommendation function and model.

        This triggers the heavy imports (sentence-transformers, sqlite-vec)
        so they're ready for fast queries.
        """
        if self._warmed_up:
            return

        # Import here to defer heavy loading
        from macf.utils.recommend import get_recommendations
        self._recommend_func = get_recommendations

        # Do a warmup query to ensure model is loaded
        self._recommend_func("warmup query")
        self._warmed_up = True

    def search(self, query: str, limit: int = 5) -> SearchResult:
        """Execute policy search with RRF fusion.

        Args:
            query: User query string
            limit: Maximum results (note: recommend.py has internal MAX_RESULTS=5)

        Returns:
            SearchResult with formatted output and explanations
        """
        # Ensure warmed up
        if not self._warmed_up:
            self.warmup()

        start = time.perf_counter()

        try:
            formatted, explanations = self._recommend_func(query)
            search_time = (time.perf_counter() - start) * 1000

            return SearchResult(
                formatted=formatted,
                explanations=explanations,
                search_time_ms=search_time,
            )

        except Exception as e:
            search_time = (time.perf_counter() - start) * 1000
            return SearchResult(
                formatted="",
                explanations=[],
                search_time_ms=search_time,
                error=str(e),
            )
