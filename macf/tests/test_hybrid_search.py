"""
Tests for macf.hybrid_search subpackage.

Covers:
- AbstractExtractor interface contract
- PolicyExtractor field extraction
- BaseIndexer FTS5 indexing
- Graceful degradation when optional deps missing

Philosophy: 6-8 focused tests covering public API, not exhaustive permutations.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

# Test graceful import behavior first
def test_graceful_import_without_optional_deps():
    """Module imports work even if optional dependencies missing."""
    with patch.dict('sys.modules', {
        'sqlite_vec': None,
        'sentence_transformers': None
    }):
        # Should not raise ImportError
        import macf.hybrid_search as hs

        # Core models always available
        assert hs.RetrieverScore is not None
        assert hs.ExplainedRecommendation is not None
        assert hs.BaseIndexer is not None

        # Optional components gracefully None
        assert hs.AbstractExtractor is None or hasattr(hs.AbstractExtractor, '__name__')


class TestAbstractExtractor:
    """Tests for AbstractExtractor interface contract."""

    def test_interface_defines_required_methods(self):
        """AbstractExtractor must define abstract methods."""
        from macf.hybrid_search.extractors.base import AbstractExtractor

        # Verify abstract methods exist
        assert hasattr(AbstractExtractor, 'name')
        assert hasattr(AbstractExtractor, 'get_fts_columns')
        assert hasattr(AbstractExtractor, 'extract_document')
        assert hasattr(AbstractExtractor, 'generate_embedding_text')

    def test_cannot_instantiate_directly(self):
        """AbstractExtractor cannot be instantiated (abstract class)."""
        from macf.hybrid_search.extractors.base import AbstractExtractor

        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            AbstractExtractor()


class TestPolicyExtractor:
    """Tests for PolicyExtractor document extraction."""

    @pytest.fixture
    def sample_policy_content(self):
        """Sample policy markdown for testing."""
        return '''# Test Policy

**Tier**: CORE
**Category**: Testing
**Status**: ACTIVE

## Purpose

This is a test policy for unit testing the hybrid search extraction.

## CEP Navigation Guide

**1 Basic Testing**
- What is unit testing?
- When should I test?

**2 Advanced Topics**
- How do I mock dependencies?
- What are fixtures?
'''

    @pytest.fixture
    def sample_policy_file(self, tmp_path, sample_policy_content):
        """Create a temporary policy file."""
        policy_file = tmp_path / "test_policy.md"
        policy_file.write_text(sample_policy_content, encoding="utf-8")
        return policy_file

    def test_should_index_skips_underscored_files(self):
        """Files starting with _ should be skipped."""
        from macf.hybrid_search.extractors.policy_extractor import PolicyExtractor

        extractor = PolicyExtractor()
        assert extractor.should_index(Path("normal.md")) is True
        assert extractor.should_index(Path("_internal.md")) is False
        assert extractor.should_index(Path("README.md")) is False
        assert extractor.should_index(Path("test.txt")) is False

    def test_extract_document_parses_metadata(self, sample_policy_file):
        """Extract should parse tier, category, status from frontmatter."""
        from macf.hybrid_search.extractors.policy_extractor import PolicyExtractor

        extractor = PolicyExtractor()
        result = extractor.extract_document(sample_policy_file)

        # Verify required fields exist
        assert result["policy_name"] == "test_policy"
        assert result["tier"] == "CORE"
        assert result["category"] == "Testing"
        assert "test policy for unit testing" in result["description"].lower()

    def test_extract_questions_parses_cep_guide(self, sample_policy_file, sample_policy_content):
        """Extract questions should parse CEP Navigation Guide."""
        from macf.hybrid_search.extractors.policy_extractor import PolicyExtractor

        extractor = PolicyExtractor()
        questions = extractor.extract_questions(sample_policy_content, "test_policy")

        # Verify questions extracted
        assert len(questions) == 4
        assert questions[0]["question_text"] == "What is unit testing?"
        assert questions[0]["section_header"] == "Basic Testing"
        assert questions[0]["section_number"] == "1"
        assert questions[0]["policy_name"] == "test_policy"
        assert questions[1]["question_text"] == "When should I test?"
        assert questions[2]["question_text"] == "How do I mock dependencies?"
        assert questions[2]["section_number"] == "2"

    def test_generate_embedding_text_combines_fields(self, sample_policy_file):
        """Generate embedding text should combine name, description, keywords."""
        from macf.hybrid_search.extractors.policy_extractor import PolicyExtractor

        extractor = PolicyExtractor()
        doc_data = extractor.extract_document(sample_policy_file)
        embedding_text = extractor.generate_embedding_text(doc_data)

        # Verify key components included
        assert "test policy" in embedding_text.lower()
        assert "Policy:" in embedding_text
        assert "Description:" in embedding_text


class TestBaseIndexer:
    """Tests for BaseIndexer FTS5 + vec0 indexing."""

    @pytest.fixture
    def mock_extractor(self):
        """Create a mock extractor for testing."""
        extractor = Mock()
        extractor.get_fts_columns.return_value = [
            ("doc_name", "TEXT"),
            ("content", "TEXT"),
        ]
        extractor.should_index.return_value = True
        extractor.extract_document.return_value = {
            "doc_name": "test_doc",
            "content": "Test content for indexing",
        }
        extractor.generate_embedding_text.return_value = "Test content for embedding"
        extractor.extract_questions.return_value = []
        return extractor

    @pytest.fixture
    def test_docs_dir(self, tmp_path):
        """Create a temporary directory with test documents."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()

        # Create a test markdown file
        test_file = docs_dir / "test_doc.md"
        test_file.write_text("# Test Document\n\nTest content.", encoding="utf-8")

        return docs_dir

    def test_build_index_creates_fts_tables(self, mock_extractor, test_docs_dir, tmp_path):
        """build_index should create FTS5 virtual tables."""
        from macf.hybrid_search.base_indexer import BaseIndexer

        indexer = BaseIndexer(mock_extractor)
        db_path = tmp_path / "test_index.db"

        # Build index without embeddings (fast unit test)
        stats = indexer.build_index(
            test_docs_dir,
            db_path,
            skip_embeddings=True,
            enable_questions=False
        )

        # Verify database created
        assert db_path.exists()

        # Verify FTS5 table exists
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

        # Verify stats
        assert stats["documents_indexed"] == 1
        assert stats["document_embeddings"] == 0  # Skipped
        assert stats["errors"] == 0
        assert stats["build_time_ms"] > 0

    def test_build_index_with_questions_table(self, test_docs_dir, tmp_path):
        """build_index should create questions_fts table when enabled."""
        from macf.hybrid_search.extractors.policy_extractor import PolicyExtractor
        from macf.hybrid_search.base_indexer import BaseIndexer

        extractor = PolicyExtractor()
        indexer = BaseIndexer(extractor)
        db_path = tmp_path / "test_index_questions.db"

        # Create a policy file with CEP guide
        policy_file = test_docs_dir / "test_policy.md"
        policy_file.write_text('''# Test Policy

**Tier**: CORE
**Category**: Testing

## CEP Navigation Guide

**1 Testing**
- What is a test?
- How do I test?
''', encoding="utf-8")

        # Build index with questions enabled
        stats = indexer.build_index(
            test_docs_dir,
            db_path,
            skip_embeddings=True,
            enable_questions=True
        )

        # Verify questions table exists
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='questions_fts'"
        )
        assert cursor.fetchone() is not None

        # Verify questions indexed
        cursor.execute("SELECT COUNT(*) FROM questions_fts")
        question_count = cursor.fetchone()[0]
        assert question_count == 2  # Two questions in CEP guide

        conn.close()

        # Verify stats
        assert stats["questions_indexed"] == 2
