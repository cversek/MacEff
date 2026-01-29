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
    """Tests for BaseIndexer LanceDB indexing.

    NOTE: Refactored in v0.4.0 from SQLite FTS5 to LanceDB.
    Tests now verify LanceDB directory creation and stats structure.
    """

    @pytest.fixture
    def mock_extractor(self):
        """Create a mock extractor for testing."""
        extractor = Mock()
        extractor.name = "test_extractor"
        extractor.get_fts_columns.return_value = ["policy_name", "content"]
        extractor.should_index.return_value = True
        extractor.extract_document.return_value = {
            "policy_name": "test_doc",
            "tier": "CORE",
            "category": "Testing",
        }
        extractor.generate_embedding_text.return_value = "Test content for embedding"
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

    def test_build_index_creates_lancedb_directory(self, mock_extractor, test_docs_dir, tmp_path):
        """build_index should create LanceDB directory with documents table."""
        from macf.hybrid_search.base_indexer import BaseIndexer
        import lancedb

        indexer = BaseIndexer(mock_extractor)
        db_path = tmp_path / "test_index.lance"

        # Build index
        stats = indexer.build_index(test_docs_dir, db_path)

        # Verify LanceDB directory created
        assert db_path.exists()
        assert db_path.is_dir()  # LanceDB creates a directory, not a file

        # Verify documents table exists
        db = lancedb.connect(str(db_path))
        assert "documents" in db.table_names()

        # Verify stats structure
        assert "documents_indexed" in stats
        assert "embedding_time" in stats
        assert "total_time" in stats
        assert stats["documents_indexed"] == 1

    def test_build_index_with_policy_extractor(self, test_docs_dir, tmp_path):
        """build_index with PolicyExtractor should index policy metadata."""
        from macf.hybrid_search.extractors.policy_extractor import PolicyExtractor
        from macf.hybrid_search.base_indexer import BaseIndexer
        import lancedb

        extractor = PolicyExtractor()
        indexer = BaseIndexer(extractor)
        db_path = tmp_path / "test_index_policy.lance"

        # Create a policy file with metadata
        policy_file = test_docs_dir / "test_policy.md"
        policy_file.write_text('''# Test Policy

**Tier**: CORE
**Category**: Testing
**Status**: ACTIVE

## Purpose

This is a test policy for unit testing.
''', encoding="utf-8")

        # Build index
        stats = indexer.build_index(test_docs_dir, db_path)

        # Verify LanceDB created and has documents
        db = lancedb.connect(str(db_path))
        table = db.open_table("documents")

        # Verify at least one document indexed
        assert stats["documents_indexed"] >= 1
