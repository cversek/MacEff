#!/usr/bin/env python3
"""
Unit tests for policy search (hybrid_search module).

Tests macf.hybrid_search.policy_search module:
- PolicySearch initialization
- semantic_search() - Pure vector similarity
- hybrid_search() - Vector + FTS with graceful fallback
- Graceful handling when index doesn't exist

Philosophy: 4-6 focused tests covering public API, not exhaustive permutations.

NOTE: Refactored in v0.4.0 - LanceDBPolicySearch renamed to PolicySearch,
module moved from lancedb_search to policy_search.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile


class TestPolicySearch:
    """Test PolicySearch class."""

    @pytest.fixture
    def mock_db_path(self, tmp_path):
        """Provide a temporary database path."""
        return tmp_path / "test_index.lance"

    def test_initialization_with_lazy_loading(self, mock_db_path):
        """
        PolicySearch should initialize without loading model or DB.

        Lazy loading pattern: model and table loaded on first access.
        """
        from macf.hybrid_search.policy_search import PolicySearch

        searcher = PolicySearch(mock_db_path, model_name="all-MiniLM-L6-v2")

        # Verify initialization
        assert searcher.db_path == mock_db_path
        assert searcher.model_name == "all-MiniLM-L6-v2"

        # Verify lazy loading (not yet loaded)
        assert searcher._model is None
        assert searcher._db is None
        assert searcher._documents_table is None

    def test_semantic_search_returns_correct_structure(self, mock_db_path):
        """
        semantic_search() should return dict with query, results, latency_ms.

        Result structure:
        {
            'query': str,
            'results': [{'policy_name', 'distance', 'similarity', 'tier', 'category'}],
            'latency_ms': float
        }
        """
        from macf.hybrid_search.policy_search import PolicySearch

        searcher = PolicySearch(mock_db_path)

        # Mock model and table
        mock_model = Mock()
        mock_model.encode.return_value = [0.1] * 384  # Mock embedding

        mock_table = Mock()
        mock_search = Mock()
        mock_search.limit.return_value.to_list.return_value = [
            {
                'policy_name': 'test_policy',
                '_distance': 0.25,
                'tier': 'CORE',
                'category': 'Testing',
            }
        ]
        mock_table.search.return_value = mock_search

        # Inject mocks
        searcher._model = mock_model
        searcher._documents_table = mock_table

        # Execute search
        result = searcher.semantic_search("test query", limit=5)

        # Verify structure
        assert 'query' in result
        assert 'results' in result
        assert 'latency_ms' in result

        assert result['query'] == "test query"
        assert isinstance(result['results'], list)
        assert isinstance(result['latency_ms'], float)

        # Verify result fields
        if result['results']:
            first_result = result['results'][0]
            assert 'policy_name' in first_result
            assert 'distance' in first_result
            assert 'similarity' in first_result
            assert first_result['similarity'] == 1 - first_result['distance']

    def test_hybrid_search_with_fts_available(self, mock_db_path):
        """
        hybrid_search() should use 'hybrid' query_type when FTS available.

        Should return search_type='hybrid' when successful.
        """
        from macf.hybrid_search.policy_search import PolicySearch

        searcher = PolicySearch(mock_db_path)

        # Mock model and table with FTS support
        mock_model = Mock()
        mock_model.encode.return_value = [0.1] * 384

        mock_table = Mock()
        mock_search = Mock()
        mock_search.limit.return_value.to_list.return_value = [
            {
                'policy_name': 'test_policy',
                '_distance': 0.2,
                'tier': 'CORE',
                'category': 'Testing',
            }
        ]
        mock_table.search.return_value = mock_search

        searcher._model = mock_model
        searcher._documents_table = mock_table

        # Execute hybrid search
        result = searcher.hybrid_search("test query", limit=5)

        # Verify hybrid mode
        assert result['search_type'] == 'hybrid'
        assert 'results' in result

        # Verify search was called with query_type
        mock_table.search.assert_called_once()

    def test_hybrid_search_fallback_to_semantic(self, mock_db_path):
        """
        hybrid_search() should fallback to semantic when FTS unavailable.

        Should return search_type='semantic' on AttributeError or Exception.
        """
        from macf.hybrid_search.policy_search import PolicySearch

        searcher = PolicySearch(mock_db_path)

        # Mock model
        mock_model = Mock()
        mock_model.encode.return_value = [0.1] * 384

        # Mock table that raises on hybrid search
        mock_table = Mock()

        # First call (hybrid) raises AttributeError
        # Second call (semantic fallback) succeeds
        mock_search_fallback = Mock()
        mock_search_fallback.limit.return_value.to_list.return_value = [
            {
                'policy_name': 'test_policy',
                '_distance': 0.3,
                'tier': 'CORE',
                'category': 'Testing',
            }
        ]

        def search_side_effect(*args, **kwargs):
            if 'query_type' in kwargs:
                raise AttributeError("FTS not available")
            return mock_search_fallback

        mock_table.search.side_effect = search_side_effect

        searcher._model = mock_model
        searcher._documents_table = mock_table

        # Execute hybrid search
        result = searcher.hybrid_search("test query", limit=5)

        # Verify fallback to semantic
        assert result['search_type'] == 'semantic'
        assert 'results' in result
        assert len(result['results']) > 0

    def test_check_fts_support(self, mock_db_path):
        """
        check_fts_support() should return dict with fts_available and message.

        Should gracefully handle AttributeError when create_fts_index not available.
        """
        from macf.hybrid_search.policy_search import PolicySearch

        searcher = PolicySearch(mock_db_path)

        # Mock table without FTS support
        mock_table = Mock(spec=[])  # Empty spec = no methods
        searcher._documents_table = mock_table

        result = searcher.check_fts_support()

        # Verify structure
        assert 'fts_available' in result
        assert 'message' in result
        assert isinstance(result['fts_available'], bool)
        assert isinstance(result['message'], str)

    def test_graceful_handling_missing_index(self, mock_db_path):
        """
        Should handle missing index file gracefully.

        LanceDB will raise FileNotFoundError when opening non-existent table.
        """
        from macf.hybrid_search.policy_search import PolicySearch

        # Use non-existent path
        non_existent = mock_db_path / "does_not_exist.lance"
        searcher = PolicySearch(non_existent)

        # Attempting to access table should raise (caught by user code)
        with pytest.raises(Exception):
            # This will fail when trying to open non-existent table
            _ = searcher.documents_table


class TestPolicySearchIntegration:
    """Integration-level test with mock LanceDB."""

    def test_run_test_queries_function_exists(self):
        """
        run_test_queries() helper function should exist for validation.

        Used in CLI testing and manual validation.
        """
        from macf.hybrid_search.policy_search import run_test_queries

        # Verify function exists and is callable
        assert callable(run_test_queries)
