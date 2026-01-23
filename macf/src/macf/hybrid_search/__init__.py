"""
Hybrid Search - LanceDB-based search infrastructure for policies and knowledge bases.

Architecture:
- BaseIndexer: Generic document indexer (domain-agnostic, creates 'documents' table)
- PolicyIndexer: Policy-specific indexer (uses BaseIndexer + adds 'questions' table)
- PolicySearch: Search with document + question support
- AbstractExtractor: Interface for document-specific field extraction
- PolicyExtractor: Policy metadata and CEP guide extraction

Design Principle: Layered extensibility - generic infrastructure (BaseIndexer) with
domain-specific extensions (PolicyIndexer, future LearningsIndexer, CAIndexer).
"""

from .models import (
    RetrieverScore,
    ExplainedRecommendation,
    MatchedQuestion,
)

# Conditional imports for optional LanceDB components
try:
    from .base_indexer import BaseIndexer
    from .policy_indexer import PolicyIndexer
    from .policy_search import PolicySearch
    from .extractors.base import AbstractExtractor
    from .extractors.policy_extractor import PolicyExtractor
except ImportError:
    # Graceful degradation if optional deps missing
    BaseIndexer = None
    PolicyIndexer = None
    PolicySearch = None
    AbstractExtractor = None
    PolicyExtractor = None

__all__ = [
    "RetrieverScore",
    "ExplainedRecommendation",
    "MatchedQuestion",
    "BaseIndexer",
    "PolicyIndexer",
    "PolicySearch",
    "AbstractExtractor",
    "PolicyExtractor",
]
