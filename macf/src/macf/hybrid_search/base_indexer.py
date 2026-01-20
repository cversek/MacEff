"""
Generic hybrid FTS5 + sqlite-vec indexer.

Uses pluggable extractors for document-specific logic while providing
common infrastructure for:
- FTS5 full-text search with BM25
- sqlite-vec semantic embeddings
- Batch embedding generation
- Question-level indexing (optional)
"""

import struct
import time
from pathlib import Path
from typing import Any, Optional

try:
    import sqlite3
    import sqlite_vec
    from sentence_transformers import SentenceTransformer
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

from .extractors.base import AbstractExtractor


# Constants
EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension


def serialize_f32(vector: list[float]) -> bytes:
    """Serialize a float32 vector for sqlite-vec storage."""
    return struct.pack(f'{len(vector)}f', *vector)


class BaseIndexer:
    """Generic FTS5 + sqlite-vec indexer using pluggable extractors."""

    def __init__(self, extractor: AbstractExtractor, embedding_model: str = "all-MiniLM-L6-v2"):
        """Initialize indexer with extractor and embedding model.

        Args:
            extractor: Document-specific extractor implementing AbstractExtractor
            embedding_model: Sentence-transformer model name
        """
        if not DEPS_AVAILABLE:
            raise ImportError(
                "Optional dependencies not available. Install with: "
                "pip install sqlite-vec sentence-transformers"
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
        docs_dir: Path,
        db_path: Path,
        skip_embeddings: bool = False,
        enable_questions: bool = True
    ) -> dict[str, Any]:
        """Build hybrid FTS5 + vector index from documents directory.

        Args:
            docs_dir: Directory containing documents to index
            db_path: Output database path
            skip_embeddings: Skip embedding generation (FTS5 only)
            enable_questions: Enable question-level indexing if extractor supports it

        Returns:
            Stats dict with counts and timing
        """
        stats = {
            "documents_indexed": 0,
            "questions_indexed": 0,
            "document_embeddings": 0,
            "question_embeddings": 0,
            "errors": 0,
            "build_time_ms": 0,
        }

        start_time = time.time()

        # Ensure output directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing database
        if db_path.exists():
            db_path.unlink()

        # Create database and enable sqlite-vec
        conn = sqlite3.connect(str(db_path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        cursor = conn.cursor()

        # Create FTS5 table from extractor schema
        self._create_fts_table(cursor, self.extractor.get_fts_columns())

        # Create question table if enabled
        if enable_questions:
            self._create_questions_table(cursor)

        # Create vector tables for semantic search (unless skipped)
        if not skip_embeddings:
            self._create_vector_tables(cursor, enable_questions)

        # Walk documents and collect data
        doc_files = list(docs_dir.glob("**/*.md"))
        docs_to_embed = []
        questions_to_embed = []
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

                # Insert into FTS5 table
                self._insert_document(cursor, doc_data)
                stats["documents_indexed"] += 1

                # Collect for embedding
                if not skip_embeddings:
                    embed_text = self.extractor.generate_embedding_text(doc_data)
                    docs_to_embed.append((doc_name, embed_text))

                # Extract and index questions if enabled
                if enable_questions:
                    content = doc_path.read_text(encoding="utf-8")
                    questions = self.extractor.extract_questions(content, doc_name)

                    for q in questions:
                        self._insert_question(cursor, q)
                        stats["questions_indexed"] += 1

                        # Collect for embedding
                        if not skip_embeddings:
                            questions_to_embed.append((
                                q["question_id"],
                                q["policy_name"],
                                q["question_text"]
                            ))

            except (IOError, KeyError) as e:
                print(f"Error indexing {doc_path}: {e}")
                stats["errors"] += 1

        # Generate and store embeddings in batch
        if not skip_embeddings and docs_to_embed:
            self._embed_documents(cursor, docs_to_embed, stats)

        if not skip_embeddings and enable_questions and questions_to_embed:
            self._embed_questions(cursor, questions_to_embed, stats)

        conn.commit()
        conn.close()

        stats["build_time_ms"] = int((time.time() - start_time) * 1000)
        return stats

    # =========================================================================
    # Internal helper methods
    # =========================================================================

    def _create_fts_table(self, cursor: sqlite3.Cursor, columns: list[tuple[str, str]]) -> None:
        """Create FTS5 virtual table from extractor column schema."""
        col_defs = ", ".join(name for name, _ in columns)

        cursor.execute(f"""
            CREATE VIRTUAL TABLE documents_fts USING fts5(
                {col_defs},
                tokenize='porter'
            )
        """)

    def _create_questions_table(self, cursor: sqlite3.Cursor) -> None:
        """Create FTS5 table for question-level indexing."""
        cursor.execute("""
            CREATE VIRTUAL TABLE questions_fts USING fts5(
                question_id,
                policy_name,
                section_header,
                section_number,
                question_text,
                tokenize='porter'
            )
        """)

    def _create_vector_tables(self, cursor: sqlite3.Cursor, enable_questions: bool) -> None:
        """Create vec0 tables and mapping tables for embeddings."""
        # Document embeddings
        cursor.execute(f"""
            CREATE VIRTUAL TABLE document_embeddings USING vec0(
                embedding float[{EMBEDDING_DIM}]
            )
        """)

        cursor.execute("""
            CREATE TABLE document_embedding_map (
                rowid INTEGER PRIMARY KEY,
                document_name TEXT UNIQUE
            )
        """)

        # Question embeddings (optional)
        if enable_questions:
            cursor.execute(f"""
                CREATE VIRTUAL TABLE question_embeddings USING vec0(
                    embedding float[{EMBEDDING_DIM}]
                )
            """)

            cursor.execute("""
                CREATE TABLE question_embedding_map (
                    rowid INTEGER PRIMARY KEY,
                    question_id TEXT UNIQUE,
                    policy_name TEXT
                )
            """)

    def _insert_document(self, cursor: sqlite3.Cursor, doc_data: dict) -> None:
        """Insert document into FTS5 table."""
        columns = [name for name, _ in self.extractor.get_fts_columns()]
        placeholders = ", ".join("?" * len(columns))
        values = [doc_data.get(col, "") for col in columns]

        cursor.execute(
            f"INSERT INTO documents_fts ({', '.join(columns)}) VALUES ({placeholders})",
            values
        )

    def _insert_question(self, cursor: sqlite3.Cursor, question: dict) -> None:
        """Insert question into questions_fts table."""
        cursor.execute("""
            INSERT INTO questions_fts (
                question_id, policy_name, section_header,
                section_number, question_text
            ) VALUES (?, ?, ?, ?, ?)
        """, (
            question["question_id"],
            question["policy_name"],
            question["section_header"],
            question["section_number"],
            question["question_text"],
        ))

    def _embed_documents(
        self,
        cursor: sqlite3.Cursor,
        docs_to_embed: list[tuple[str, str]],
        stats: dict
    ) -> None:
        """Generate and store document embeddings in batch."""
        print(f"Generating embeddings for {len(docs_to_embed)} documents...")
        doc_texts = [text for _, text in docs_to_embed]
        embeddings = self.model.encode(doc_texts, show_progress_bar=True)

        for (doc_name, _), embedding in zip(docs_to_embed, embeddings):
            # Insert embedding into vec0 table
            cursor.execute(
                "INSERT INTO document_embeddings (embedding) VALUES (?)",
                (serialize_f32(embedding.tolist()),)
            )
            rowid = cursor.lastrowid

            # Map rowid to document_name
            cursor.execute(
                "INSERT INTO document_embedding_map (rowid, document_name) VALUES (?, ?)",
                (rowid, doc_name)
            )
            stats["document_embeddings"] += 1

    def _embed_questions(
        self,
        cursor: sqlite3.Cursor,
        questions_to_embed: list[tuple[str, str, str]],
        stats: dict
    ) -> None:
        """Generate and store question embeddings in batch."""
        print(f"Generating embeddings for {len(questions_to_embed)} questions...")
        question_texts = [text for _, _, text in questions_to_embed]
        embeddings = self.model.encode(question_texts, show_progress_bar=True)

        for (qid, policy_name, _), embedding in zip(questions_to_embed, embeddings):
            # Insert embedding into vec0 table
            cursor.execute(
                "INSERT INTO question_embeddings (embedding) VALUES (?)",
                (serialize_f32(embedding.tolist()),)
            )
            rowid = cursor.lastrowid

            # Map rowid to question_id and policy_name
            cursor.execute(
                "INSERT INTO question_embedding_map (rowid, question_id, policy_name) VALUES (?, ?, ?)",
                (rowid, qid, policy_name)
            )
            stats["question_embeddings"] += 1
