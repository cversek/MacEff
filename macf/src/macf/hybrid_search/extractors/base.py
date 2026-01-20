"""
Abstract base class for document extractors.

Extractors implement document-specific logic for:
1. Field extraction (metadata, content, structured sections)
2. Embedding text generation (what to vectorize)
3. Optional sub-document extraction (e.g., questions)
4. Document filtering (what to index)
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class AbstractExtractor(ABC):
    """Interface for document-specific field extraction."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Extractor name (e.g., 'policies', 'learnings')."""
        ...

    @abstractmethod
    def get_fts_columns(self) -> list[tuple[str, str]]:
        """Return FTS5 column definitions as (name, type) tuples.

        Example:
            [("name", "TEXT"), ("content", "TEXT"), ("keywords", "TEXT")]
        """
        ...

    @abstractmethod
    def extract_document(self, doc_path: Path) -> dict[str, Any]:
        """Extract fields from document. Keys must match FTS columns.

        Args:
            doc_path: Path to document file

        Returns:
            Dict with keys matching FTS column names
        """
        ...

    @abstractmethod
    def generate_embedding_text(self, doc_data: dict) -> str:
        """Generate text for embedding from extracted document data.

        Args:
            doc_data: Result from extract_document()

        Returns:
            Text string to vectorize
        """
        ...

    def extract_questions(self, content: str, doc_id: str) -> list[dict]:
        """Optional: Extract sub-document questions for separate indexing.

        Args:
            content: Full document content
            doc_id: Document identifier

        Returns:
            List of question dicts with keys: question_id, question_text, etc.
        """
        return []

    def should_index(self, doc_path: Path) -> bool:
        """Return True if this document should be indexed.

        Default: index .md files not starting with underscore.
        """
        return not doc_path.name.startswith("_") and doc_path.suffix == ".md"
