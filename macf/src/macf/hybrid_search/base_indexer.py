"""
Generic LanceDB indexer using pluggable extractors.

Provides infrastructure for:
- Document metadata extraction via AbstractExtractor
- Batch embedding generation
- LanceDB table creation with full-text + vector search

Domain-agnostic: knows nothing about policies, questions, or CEP.
"""

import time
from pathlib import Path
from typing import Any, Optional

try:
    import lancedb
    from sentence_transformers import SentenceTransformer
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

from .extractors.base import AbstractExtractor


class BaseIndexer:
    """Generic LanceDB indexer using pluggable extractors."""

    def __init__(self, extractor: AbstractExtractor, embedding_model: str = "all-MiniLM-L6-v2"):
        """Initialize indexer with extractor and embedding model.

        Args:
            extractor: Document-specific extractor implementing AbstractExtractor
            embedding_model: Sentence-transformer model name
        """
        if not DEPS_AVAILABLE:
            raise ImportError(
                "Optional dependencies not available. Install with: "
                "pip install lancedb sentence-transformers"
            )

        self.extractor = extractor
        self.embedding_model_name = embedding_model
        self._model: Optional["SentenceTransformer"] = None  # String annotation for optional dep

    @property
    def model(self) -> "SentenceTransformer":  # String annotation for optional dep
        """Lazy-load embedding model."""
        if self._model is None:
            print(f"Loading embedding model: {self.embedding_model_name}...")
            self._model = SentenceTransformer(self.embedding_model_name)
        return self._model

    def build_index(
        self,
        source_dir: Path,
        db_path: Path,
    ) -> dict[str, Any]:
        """Build LanceDB index from documents directory.

        Args:
            source_dir: Directory containing documents to index
            db_path: Output LanceDB directory path

        Returns:
            Stats dict with counts and timing:
            - documents_indexed: Number of documents processed
            - embedding_time: Time spent generating embeddings (seconds)
            - total_time: Total build time (seconds)
        """
        start_time = time.time()

        # Ensure output directory parent exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Walk documents and collect data
        doc_files = list(source_dir.glob("**/*.md"))
        documents = []
        seen_docs = set()  # Deduplicate by document name

        for doc_path in doc_files:
            # Skip if extractor says no
            if not self.extractor.should_index(doc_path):
                continue

            # Skip duplicates (same name from different paths)
            doc_name = doc_path.stem
            if doc_name in seen_docs:
                continue
            seen_docs.add(doc_name)

            try:
                # Extract document fields
                doc_data = self.extractor.extract_document(doc_path)

                # Generate embedding text
                embed_text = self.extractor.generate_embedding_text(doc_data)

                # Store document with content for embedding
                documents.append({
                    **doc_data,
                    'content': embed_text,  # Text to embed for semantic search
                })

            except (IOError, KeyError) as e:
                print(f"Error indexing {doc_path}: {e}")
                continue

        if not documents:
            raise ValueError(f"No documents found in {source_dir}")

        # Generate embeddings in batch
        print(f"Generating embeddings for {len(documents)} documents...")
        embed_start = time.time()
        texts = [doc['content'] for doc in documents]
        embeddings = self.model.encode(texts, show_progress_bar=True)
        embedding_time = time.time() - embed_start

        # Add embeddings to documents
        for i, doc in enumerate(documents):
            doc['embedding'] = embeddings[i].tolist()

        # Create LanceDB database and table
        print(f"Creating LanceDB at {db_path}")
        db = lancedb.connect(str(db_path))

        # Drop existing table if present, then create fresh
        if "documents" in db.table_names():
            db.drop_table("documents")

        db.create_table("documents", documents)

        total_time = time.time() - start_time

        return {
            'documents_indexed': len(documents),
            'embedding_time': embedding_time,
            'total_time': total_time,
        }
