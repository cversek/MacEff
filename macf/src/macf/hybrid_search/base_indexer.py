"""
Generic LanceDB indexer using pluggable extractors.

Provides infrastructure for:
- Document metadata extraction via AbstractExtractor
- Batch embedding generation
- LanceDB table creation with full-text + vector search

Domain-agnostic: knows nothing about policies, questions, or CEP.
"""

import sys
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
            print(f"Loading embedding model: {self.embedding_model_name}...", file=sys.stderr)
            try:  # the weight-loading report and progress bar are noise on a CLI
                from transformers.utils import logging as _tl
                _tl.set_verbosity_error()
                _tl.disable_progress_bar()
            except (ImportError, AttributeError) as e:  # older transformers: report stays, model still loads
                print(f"⚠️ MACF: could not quiet transformers logging: {e}", file=sys.stderr)
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

        print(f"Creating LanceDB at {db_path}", file=sys.stderr)
        stats = self.index_documents(documents, str(db_path), progress=True)
        stats.pop('db'); stats.pop('table')  # keep this method's return JSON-serialisable, as before
        stats['total_time'] = time.time() - start_time
        return stats

    def index_documents(self, documents: list[dict[str, Any]], db_uri: str = "memory://",
                        progress: bool = False) -> dict[str, Any]:
        """Embed already-extracted documents and write them to a LanceDB ``documents`` table.

        Each document must carry a ``content`` key (the text to embed). With the
        default ``memory://`` URI nothing is written to disk: the table lives only
        in the returned connection, which is what callers holding data that must
        not rest in plaintext (the gmail cache) rely on.

        Returns the stats dict plus ``db`` (the connection) and ``table``.
        """
        embed_start = time.time()
        texts = [doc['content'] for doc in documents]
        embeddings = self.model.encode(texts, show_progress_bar=progress)
        embedding_time = time.time() - embed_start
        for i, doc in enumerate(documents):
            doc['embedding'] = embeddings[i].tolist()

        db = lancedb.connect(db_uri)
        if "documents" in db.table_names():
            db.drop_table("documents")
        table = db.create_table("documents", documents)

        return {
            'documents_indexed': len(documents),
            'embedding_time': embedding_time,
            'total_time': embedding_time,
            'db': db,
            'table': table,
        }
