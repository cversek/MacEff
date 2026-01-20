"""
AbstractRetriever - Base interface for domain-specific search strategies.

Mirrors the AbstractExtractor pattern from hybrid_search:
- AbstractExtractor defines how to INDEX documents
- AbstractRetriever defines how to SEARCH indexed documents

Each retriever handles a specific namespace (policy, learnings, cas, etc.)
and can use any combination of FTS5, semantic search, or custom logic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SearchResult:
    """Result from a retriever search.

    Designed for JSON serialization over socket protocol.
    """
    formatted: str  # Human-readable output for hooks
    explanations: list[dict] = field(default_factory=list)  # Detailed breakdown
    search_time_ms: float = 0.0  # Timing for diagnostics
    error: Optional[str] = None  # Error message if search failed

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        result = {
            "formatted": self.formatted,
            "explanations": self.explanations,
            "search_time_ms": round(self.search_time_ms, 1),
        }
        if self.error:
            result["error"] = self.error
        return result


class AbstractRetriever(ABC):
    """Base class for domain-specific search retrievers.

    Implement this interface to add search support for a new knowledge base.
    The SearchService daemon will route queries to retrievers by namespace.

    Design Philosophy:
    - Retriever owns its database connection and search logic
    - Retriever may share the embedding model with other retrievers
    - Retriever produces formatted output suitable for hook injection

    Example Implementation:
        class LearningsRetriever(AbstractRetriever):
            @property
            def namespace(self) -> str:
                return "learnings"

            def search(self, query: str, limit: int = 5) -> SearchResult:
                # Semantic search over learnings_index.db
                ...
    """

    @property
    @abstractmethod
    def namespace(self) -> str:
        """Unique namespace identifier for routing.

        Examples: "policy", "learnings", "cas"
        """
        pass

    @abstractmethod
    def search(self, query: str, limit: int = 5) -> SearchResult:
        """Execute search and return results.

        Args:
            query: User query string
            limit: Maximum results to return

        Returns:
            SearchResult with formatted output and optional explanations
        """
        pass

    def warmup(self) -> None:
        """Optional warmup to pre-load resources.

        Called once when retriever is registered with SearchService.
        Use to pre-load models, open database connections, etc.
        Default: no-op
        """
        pass

    def shutdown(self) -> None:
        """Optional cleanup when service stops.

        Called when SearchService is shutting down.
        Use to close database connections, release resources, etc.
        Default: no-op
        """
        pass
