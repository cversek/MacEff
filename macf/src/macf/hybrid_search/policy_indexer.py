"""
Policy-specific indexer extending BaseIndexer with CEP questions table.

Builds on generic BaseIndexer infrastructure to add policy-specific features:
- Questions table for CEP section targeting
- Policy metadata preservation

Domain-specific: knows about policies, CEP Navigation Guides, and questions.
Uses BaseIndexer for the generic documents table.
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

from .base_indexer import BaseIndexer
from .extractors.policy_extractor import PolicyExtractor


class PolicyIndexer:
    """Policy-specific indexer with CEP question support.

    Composes BaseIndexer for documents table, adds questions table
    for CEP section targeting. Follows layered extensibility pattern:
    - Generic layer: BaseIndexer handles documents
    - Domain layer: PolicyIndexer adds questions
    """

    def __init__(
        self,
        manifest_path: Optional[Path] = None,
        embedding_model: str = "all-MiniLM-L6-v2",
    ):
        """Initialize policy indexer.

        Args:
            manifest_path: Optional path to manifest.json for keywords
            embedding_model: Sentence-transformer model name
        """
        if not DEPS_AVAILABLE:
            raise ImportError(
                "Optional dependencies not available. Install with: "
                "pip install lancedb sentence-transformers"
            )

        self.manifest_path = manifest_path
        self.embedding_model_name = embedding_model
        self._model: Optional["SentenceTransformer"] = None

        # Create policy extractor with manifest
        self.extractor = PolicyExtractor(manifest_path=manifest_path)

        # Create base indexer for documents table
        self.base_indexer = BaseIndexer(
            extractor=self.extractor,
            embedding_model=embedding_model,
        )

    @property
    def model(self) -> "SentenceTransformer":
        """Lazy-load embedding model (shared with base indexer)."""
        if self._model is None:
            # Reuse base indexer's model to avoid loading twice
            self._model = self.base_indexer.model
        return self._model

    def build_index(
        self,
        policies_dir: Path,
        db_path: Path,
    ) -> dict[str, Any]:
        """Build complete policy index with documents and questions tables.

        Args:
            policies_dir: Directory containing policy markdown files
            db_path: Output LanceDB directory path

        Returns:
            Stats dict with:
            - documents_indexed: Number of policy documents
            - questions_indexed: Number of CEP questions
            - embedding_time: Time for embeddings (seconds)
            - total_time: Total build time (seconds)
        """
        start_time = time.time()

        # Step 1: Use BaseIndexer for documents table
        print("=== Phase 1: Building documents table (via BaseIndexer) ===")
        doc_stats = self.base_indexer.build_index(policies_dir, db_path)

        # Step 2: Build questions table (policy-specific)
        print("\n=== Phase 2: Building questions table (policy-specific) ===")
        questions_stats = self._build_questions_table(policies_dir, db_path)

        total_time = time.time() - start_time

        stats = {
            'documents_indexed': doc_stats['documents_indexed'],
            'questions_indexed': questions_stats['questions_indexed'],
            'embedding_time': doc_stats['embedding_time'] + questions_stats.get('embedding_time', 0),
            'total_time': total_time,
            'index_path': str(db_path),
        }

        print(f"\n=== Index Build Complete ===")
        print(f"Documents: {stats['documents_indexed']}")
        print(f"Questions: {stats['questions_indexed']}")
        print(f"Total time: {stats['total_time']:.2f}s")

        return stats

    def _build_questions_table(
        self,
        policies_dir: Path,
        db_path: Path,
    ) -> dict[str, Any]:
        """Build questions table for CEP section targeting.

        Extracts questions from CEP Navigation Guides and creates
        a separate LanceDB table for fine-grained section search.

        Args:
            policies_dir: Directory containing policy markdown files
            db_path: LanceDB directory path (must already exist from build_index)

        Returns:
            Stats dict with questions_indexed count
        """
        start_time = time.time()

        # Find all policy files
        policy_files = list(policies_dir.glob("**/*.md"))
        policy_files = [f for f in policy_files if self.extractor.should_index(f)]

        # Extract questions from all policies
        all_questions = []
        for pf in policy_files:
            content = pf.read_text(encoding="utf-8")
            policy_name = pf.stem

            # Use extractor's question extraction
            questions = self.extractor.extract_questions(content, policy_name)
            all_questions.extend(questions)

        if not all_questions:
            print("No questions found in policies")
            return {'questions_indexed': 0, 'embedding_time': 0}

        print(f"Found {len(all_questions)} questions across {len(policy_files)} policies")

        # Generate embeddings for questions
        print("Generating question embeddings...")
        embed_start = time.time()
        question_texts = [q['question_text'] for q in all_questions]
        embeddings = self.model.encode(question_texts, show_progress_bar=True)
        embedding_time = time.time() - embed_start

        # Add embeddings to questions
        for i, q in enumerate(all_questions):
            q['embedding'] = embeddings[i].tolist()

        # Create questions table in existing LanceDB
        db = lancedb.connect(str(db_path))

        # Drop existing questions table if present
        if "questions" in db.table_names():
            db.drop_table("questions")

        db.create_table("questions", all_questions)
        print(f"Created questions table with {len(all_questions)} entries")

        return {
            'questions_indexed': len(all_questions),
            'embedding_time': embedding_time,
        }


def build_policy_index(
    policies_dir: Path,
    output_path: Path,
    model_name: str = "all-MiniLM-L6-v2",
    manifest_path: Optional[Path] = None,
) -> dict:
    """Convenience function for building policy index.

    Args:
        policies_dir: Directory containing policy markdown files
        output_path: Path to LanceDB directory (will be created)
        model_name: SentenceTransformer model name
        manifest_path: Optional path to manifest.json for keywords

    Returns:
        Stats dict with timing and counts
    """
    indexer = PolicyIndexer(
        manifest_path=manifest_path,
        embedding_model=model_name,
    )
    return indexer.build_index(policies_dir, output_path)


if __name__ == "__main__":
    from ..utils.paths import find_agent_home

    agent_home = find_agent_home()
    policies_dir = agent_home / ".maceff" / "framework" / "policies"
    output_path = agent_home / ".maceff" / "policy_index.lance"
    manifest_path = policies_dir / "manifest.json"

    if not policies_dir.exists():
        print(f"Policies directory not found: {policies_dir}")
        exit(1)

    print(f"Policies dir: {policies_dir}")
    print(f"Output path: {output_path}")

    stats = build_policy_index(
        policies_dir,
        output_path,
        manifest_path=manifest_path if manifest_path.exists() else None,
    )

    print(f"\nIndex ready at: {output_path}")
