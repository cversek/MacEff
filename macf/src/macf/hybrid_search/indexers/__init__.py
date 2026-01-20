"""
Pre-configured indexers for specific document types.

Combines BaseIndexer with domain-specific extractors.
"""

try:
    from .policy_indexer import PolicyIndexer
except ImportError:
    PolicyIndexer = None

__all__ = [
    "PolicyIndexer",
]
