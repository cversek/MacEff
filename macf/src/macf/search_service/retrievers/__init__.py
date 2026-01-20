"""
Search service retrievers - pluggable domain-specific search strategies.

Each retriever implements AbstractRetriever for a specific knowledge base.
The SearchService daemon routes queries to the appropriate retriever by namespace.
"""

from .base import AbstractRetriever, SearchResult

__all__ = ["AbstractRetriever", "SearchResult"]
