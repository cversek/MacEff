"""
Policy-specific indexer using LanceDB backend.

Convenience wrapper for indexing MacEff framework policies with LanceDB.
"""

from pathlib import Path
from typing import Any, Optional

from ..lancedb_indexer import build_lancedb_index
from ..extractors.policy_extractor import PolicyExtractor


class PolicyIndexer:
    """Convenience indexer for MacEff policies using LanceDB."""

    def __init__(self, manifest_path: Optional[Path] = None, embedding_model: str = "all-MiniLM-L6-v2"):
        """Initialize policy indexer.

        Args:
            manifest_path: Path to manifest.json for keyword extraction
            embedding_model: Sentence-transformer model name
        """
        self.manifest_path = manifest_path
        self.embedding_model = embedding_model
        self.extractor = PolicyExtractor(manifest_path=manifest_path)

    def build_index(
        self,
        policies_dir: Path,
        output_path: Path,
        skip_embeddings: bool = False
    ) -> dict[str, Any]:
        """Build policy index from policies directory using LanceDB.

        Args:
            policies_dir: Directory containing policy .md files
            output_path: Output LanceDB directory path
            skip_embeddings: Not supported with LanceDB (ignored for compatibility)

        Returns:
            Stats dict with counts and timing
        """
        if skip_embeddings:
            print("Warning: skip_embeddings not supported with LanceDB backend")

        return build_lancedb_index(
            policies_dir=policies_dir,
            output_path=output_path,
            model_name=self.embedding_model,
            manifest_path=self.manifest_path
        )
