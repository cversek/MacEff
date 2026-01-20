"""
Policy-specific indexer combining BaseIndexer + PolicyExtractor.

Convenience wrapper for indexing MacEff framework policies.
"""

from pathlib import Path
from typing import Any

from ..base_indexer import BaseIndexer
from ..extractors.policy_extractor import PolicyExtractor


class PolicyIndexer:
    """Convenience indexer for MacEff policies."""

    def __init__(self, manifest_path: Path = None, embedding_model: str = "all-MiniLM-L6-v2"):
        """Initialize policy indexer.

        Args:
            manifest_path: Path to manifest.json for keyword extraction
            embedding_model: Sentence-transformer model name
        """
        extractor = PolicyExtractor(manifest_path=manifest_path)
        self.indexer = BaseIndexer(extractor, embedding_model)

    def build_index(
        self,
        policies_dir: Path,
        db_path: Path,
        skip_embeddings: bool = False
    ) -> dict[str, Any]:
        """Build policy index from policies directory.

        Args:
            policies_dir: Directory containing policy .md files
            db_path: Output database path
            skip_embeddings: Skip embedding generation (FTS5 only)

        Returns:
            Stats dict with counts and timing
        """
        return self.indexer.build_index(
            docs_dir=policies_dir,
            db_path=db_path,
            skip_embeddings=skip_embeddings,
            enable_questions=True  # Policies always have questions
        )
