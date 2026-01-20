"""
Hybrid Search - Reusable search infrastructure combining FTS5 + semantic embeddings.

Design Principle: Lightweight indices with rich metadata, NO content storage
(content stays in filesystem).

Use Cases:
1. Policy search (primary)
2. Learnings knowledge base (future)
3. General CA knowledge base (future)

Architecture:
- BaseIndexer: Generic FTS5 + vec0 indexer with pluggable extractors
- AbstractExtractor: Interface for document-specific field extraction
- PolicyExtractor: Policy-specific metadata and CEP guide extraction
- PolicyIndexer: Convenience wrapper (BaseIndexer + PolicyExtractor)
"""

from .models import (
    RetrieverScore,
    ExplainedRecommendation,
)
from .base_indexer import BaseIndexer

# Conditional imports for optional components
try:
    from .extractors.base import AbstractExtractor
    from .extractors.policy_extractor import PolicyExtractor
    from .indexers.policy_indexer import PolicyIndexer
except ImportError:
    # Graceful degradation if optional deps missing
    AbstractExtractor = None
    PolicyExtractor = None
    PolicyIndexer = None

__all__ = [
    "RetrieverScore",
    "ExplainedRecommendation",
    "BaseIndexer",
    "AbstractExtractor",
    "PolicyExtractor",
    "PolicyIndexer",
]
