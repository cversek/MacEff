"""
Document extractors for hybrid search indexing.

Extractors handle document-specific field extraction and embedding text generation.
"""

try:
    from .base import AbstractExtractor
    from .policy_extractor import PolicyExtractor
except ImportError:
    # Graceful degradation if optional deps missing
    AbstractExtractor = None
    PolicyExtractor = None

__all__ = [
    "AbstractExtractor",
    "PolicyExtractor",
]
