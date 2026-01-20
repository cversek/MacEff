"""
Integration tests for macf.search_service module.

Tests focus on:
1. Import resilience (stdlib-only client)
2. AbstractRetriever interface compliance
3. Client graceful degradation (service unavailable)
4. SearchResult serialization
5. Basic retriever lifecycle

Following testing.md 4-6 test principle - test reality, not possibilities.
No socket communication tests (flaky) - test interfaces and data structures.
"""

import pytest
from unittest.mock import MagicMock, patch

from macf.search_service import (
    AbstractRetriever,
    SearchResult,
    PolicyRetriever,
    query_search_service,
    get_policy_injection,
)


class TestImportResilience:
    """Test that imports work without heavy dependencies."""

    def test_client_imports_without_heavy_deps(self):
        """Client module uses stdlib only - safe for hooks."""
        # This test passes if imports don't raise ImportError
        from macf.search_service import query_search_service, get_policy_injection

        # Client should be importable without sentence-transformers
        assert callable(query_search_service)
        assert callable(get_policy_injection)

    def test_base_classes_importable(self):
        """Base classes importable without heavy deps."""
        from macf.search_service import AbstractRetriever, SearchResult

        assert AbstractRetriever is not None
        assert SearchResult is not None


class TestSearchResultSerialization:
    """Test SearchResult data structure and JSON serialization."""

    def test_search_result_to_dict_minimal(self):
        """SearchResult.to_dict() produces valid JSON with minimal data."""
        result = SearchResult(
            formatted="Test output",
            explanations=[],
            search_time_ms=45.2,
        )

        data = result.to_dict()

        assert data["formatted"] == "Test output"
        assert data["explanations"] == []
        assert data["search_time_ms"] == 45.2
        assert "error" not in data

    def test_search_result_to_dict_with_error(self):
        """SearchResult includes error field when present."""
        result = SearchResult(
            formatted="",
            explanations=[],
            search_time_ms=0.0,
            error="connection_refused",
        )

        data = result.to_dict()

        assert data["formatted"] == ""
        assert data["error"] == "connection_refused"

    def test_search_result_to_dict_rounds_timing(self):
        """SearchResult rounds timing to 1 decimal place."""
        result = SearchResult(
            formatted="Test",
            search_time_ms=45.23456789,
        )

        data = result.to_dict()

        assert data["search_time_ms"] == 45.2


class TestAbstractRetrieverInterface:
    """Test that retrievers implement required interface."""

    def test_policy_retriever_implements_namespace(self):
        """PolicyRetriever implements namespace property."""
        retriever = PolicyRetriever()

        assert retriever.namespace == "policy"
        assert isinstance(retriever.namespace, str)

    def test_policy_retriever_implements_search(self):
        """PolicyRetriever implements search method signature."""
        retriever = PolicyRetriever()

        # Check method exists and is callable
        assert hasattr(retriever, "search")
        assert callable(retriever.search)

    def test_policy_retriever_implements_optional_methods(self):
        """PolicyRetriever implements optional warmup/shutdown."""
        retriever = PolicyRetriever()

        # Optional methods should exist and be callable
        assert hasattr(retriever, "warmup")
        assert hasattr(retriever, "shutdown")
        assert callable(retriever.warmup)
        assert callable(retriever.shutdown)


class TestClientGracefulDegradation:
    """Test client behavior when service unavailable."""

    def test_query_service_returns_empty_on_connection_refused(self):
        """Client returns empty result when service not running."""
        # No service running on port 9999
        result = query_search_service(
            namespace="policy",
            query="test query",
            port=9999,
            timeout_s=0.1,
        )

        # Should return graceful degradation response
        assert result["formatted"] == ""
        assert result["explanations"] == []
        assert "error" in result
        assert result["error"] in ["connection_refused", "timeout"]

    def test_query_service_returns_empty_on_timeout(self):
        """Client returns empty result on timeout."""
        # Use aggressive timeout to force timeout condition
        result = query_search_service(
            namespace="policy",
            query="test query",
            port=9999,
            timeout_s=0.001,  # 1ms - will timeout
        )

        # Should return graceful degradation response
        assert result["formatted"] == ""
        assert "error" in result

    def test_get_policy_injection_returns_empty_for_short_prompts(self):
        """get_policy_injection skips very short prompts."""
        # Less than 10 characters
        result = get_policy_injection("test")

        assert result == ""

    def test_get_policy_injection_handles_unavailable_service(self):
        """get_policy_injection returns empty string when service down."""
        # Service not running on port 9999
        result = get_policy_injection(
            "This is a longer prompt that should be processed",
            port=9999,
            timeout_s=0.1,
        )

        # Should return empty string (graceful degradation)
        assert result == ""


class TestRetrieverLifecycle:
    """Test retriever registration and lifecycle patterns."""

    def test_policy_retriever_warmup_is_idempotent(self):
        """Calling warmup multiple times is safe."""
        retriever = PolicyRetriever()

        # Mock the heavy import to avoid loading sentence-transformers
        with patch("macf.utils.recommend.get_recommendations") as mock_rec:
            mock_rec.return_value = ("Test output", [])

            # Warmup twice
            retriever.warmup()
            retriever.warmup()

            # Should not raise, _warmed_up flag prevents double loading
            assert retriever._warmed_up is True

    def test_policy_retriever_lazy_warmup_on_search(self):
        """PolicyRetriever warms up lazily on first search."""
        retriever = PolicyRetriever()

        # Initially not warmed up
        assert retriever._warmed_up is False

        # Mock the heavy import
        with patch("macf.utils.recommend.get_recommendations") as mock_rec:
            mock_rec.return_value = ("Test output", [])

            # First search triggers warmup
            result = retriever.search("test query")

            # Should be warmed up now
            assert retriever._warmed_up is True
            assert isinstance(result, SearchResult)
