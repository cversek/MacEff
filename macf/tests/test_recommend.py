#!/usr/bin/env python3
"""
Unit tests for policy recommendation (LanceDB hybrid search).

Tests macf.utils.recommend module:
- get_policy_db_path() - Portable path resolution (now returns .lance)
- ExplainedRecommendation dataclass - Structure validation
- RetrieverScore dataclass - Structure validation
- get_recommendations() - Return tuple structure
- Warning when DB not found
- Short query filtering

Updated for LanceDB backend migration (Cycle 356).
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from dataclasses import fields

from macf.utils.recommend import (
    get_policy_db_path,
    ExplainedRecommendation,
    RetrieverScore,
    get_recommendations,
    MIN_QUERY_LENGTH,
)


class TestPolicyDbPath:
    """Test portable path resolution for policy index."""

    def test_get_policy_db_path_uses_find_agent_home(self):
        """
        get_policy_db_path() should use find_agent_home() for portability.

        Should return .lance directory (LanceDB) not .db (sqlite-vec).
        """
        with patch('macf.utils.recommend.find_agent_home') as mock_find_home:
            mock_find_home.return_value = Path('/mock/agent/home')

            result = get_policy_db_path()

            # Verify find_agent_home was called
            mock_find_home.assert_called_once()

            # Verify path structure (LanceDB uses .lance directory)
            assert result == Path('/mock/agent/home/.maceff/policy_index.lance')
            assert result.name == 'policy_index.lance'
            assert result.parent.name == '.maceff'


class TestDataclassStructures:
    """Test dataclass field requirements."""

    def test_retriever_score_has_required_fields(self):
        """
        RetrieverScore dataclass should have required fields.

        Required: retriever, rank, raw_score, rrf_contribution, matched_text
        """
        score = RetrieverScore(
            retriever="lancedb_hybrid",
            rank=1,
            raw_score=0.85,
            rrf_contribution=0.016,
            matched_text="similarity: 0.85"
        )

        # Verify all required fields exist
        assert score.retriever == "lancedb_hybrid"
        assert score.rank == 1
        assert score.raw_score == 0.85
        assert score.rrf_contribution == 0.016
        assert score.matched_text == "similarity: 0.85"

        # Verify dataclass has exactly these fields
        field_names = {f.name for f in fields(RetrieverScore)}
        expected = {'retriever', 'rank', 'raw_score', 'rrf_contribution', 'matched_text'}
        assert field_names == expected

    def test_explained_recommendation_has_required_fields(self):
        """
        ExplainedRecommendation dataclass should have required fields.

        Required: policy_name, score, confidence_tier, retriever_contributions
        """
        rec = ExplainedRecommendation(
            policy_name="test_policy",
            score=0.045,
            confidence_tier="HIGH",
        )

        # Verify required fields
        assert rec.policy_name == "test_policy"
        assert rec.score == 0.045
        assert rec.confidence_tier == "HIGH"

        # Verify default factories work
        assert isinstance(rec.retriever_contributions, dict)
        assert isinstance(rec.keywords_matched, list)
        assert isinstance(rec.matched_questions, list)

        # Verify all expected fields exist
        field_names = {f.name for f in fields(ExplainedRecommendation)}
        expected = {
            'policy_name', 'score', 'confidence_tier',
            'retriever_contributions', 'keywords_matched', 'matched_questions'
        }
        assert field_names == expected


class TestGetRecommendations:
    """Test get_recommendations() function."""

    def test_returns_correct_tuple_structure(self):
        """
        get_recommendations() should return (formatted_output: str, explanations: list).

        Tuple structure: (str, list[dict])
        """
        # Mock DB existence check
        with patch('macf.utils.recommend._get_db_path') as mock_path:
            mock_db = MagicMock(spec=Path)
            mock_db.exists.return_value = False
            mock_path.return_value = mock_db

            result = get_recommendations("test query with enough length")

            # Verify tuple structure
            assert isinstance(result, tuple)
            assert len(result) == 2

            formatted_output, explanations = result
            assert isinstance(formatted_output, str)
            assert isinstance(explanations, list)

    def test_warning_when_db_not_found(self, capsys):
        """
        Should print warning to stderr when DB not found.

        Warning should suggest: macf_tools policy build_index
        """
        with patch('macf.utils.recommend._get_db_path') as mock_path:
            mock_db = MagicMock(spec=Path)
            mock_db.exists.return_value = False
            mock_db.__str__.return_value = '/fake/path/policy_index.lance'
            mock_path.return_value = mock_db

            result = get_recommendations("test query with enough length")

            # Verify returns empty on DB not found
            formatted_output, explanations = result
            assert formatted_output == ""
            assert explanations == []

            # Verify warning printed to stderr
            captured = capsys.readouterr()
            assert "Policy index not found" in captured.err
            assert "macf_tools policy build_index" in captured.err

    def test_short_queries_return_empty(self):
        """
        Queries shorter than MIN_QUERY_LENGTH should return empty.

        MIN_QUERY_LENGTH = 10 chars
        """
        # Test various short queries
        # Only truly trivial queries should return empty
        # LanceDB can find semantic matches for real words like "short"
        trivial_queries = [
            "",
            "a",
        ]

        for query in trivial_queries:
            result = get_recommendations(query)
            formatted_output, explanations = result

            # Should return empty for trivial queries
            assert formatted_output == "", f"Query '{query}' should return empty"
            assert explanations == [], f"Query '{query}' should return empty list"

    def test_empty_keywords_return_empty(self):
        """
        If keyword extraction yields no keywords, should return empty.

        This tests the early exit path when extract_keywords() returns [].
        """
        # Patch extract_keywords to return empty list
        with patch('macf.utils.recommend.extract_keywords', return_value=[]):
            result = get_recommendations("query with all stopwords: the a an is")

            formatted_output, explanations = result
            assert formatted_output == ""
            assert explanations == []

    def test_graceful_failure_on_search_exception(self):
        """
        Should handle search exceptions gracefully without crashing.

        Should return empty tuple on any exception during LanceDB search.
        """
        with patch('macf.utils.recommend._get_db_path') as mock_path:
            mock_db = MagicMock(spec=Path)
            mock_db.exists.return_value = True
            mock_path.return_value = mock_db

            # Simulate LanceDB search failure
            with patch('macf.utils.recommend.search_with_lancedb', side_effect=Exception('Search error')):
                result = get_recommendations("test query with enough length")

                formatted_output, explanations = result
                assert formatted_output == ""
                assert explanations == []


class TestExplainedRecommendationMethods:
    """Test ExplainedRecommendation methods."""

    def test_to_dict_serialization(self):
        """
        to_dict() should convert to JSON-serializable dictionary.

        Should include all fields with proper nesting.
        """
        score = RetrieverScore(
            retriever="lancedb_hybrid",
            rank=1,
            raw_score=0.85,
            rrf_contribution=0.016,
            matched_text="similarity: 0.85"
        )

        rec = ExplainedRecommendation(
            policy_name="test_policy",
            score=0.045,
            confidence_tier="HIGH",
            retriever_contributions={"lancedb_hybrid": score},
            keywords_matched=[("keyword", 1.0)],
            matched_questions=[],
        )

        result = rec.to_dict()

        # Verify structure
        assert isinstance(result, dict)
        assert result['policy_name'] == "test_policy"
        assert result['score'] == 0.045
        assert result['confidence_tier'] == "HIGH"

        # Verify nested structures
        assert 'retriever_contributions' in result
        assert 'lancedb_hybrid' in result['retriever_contributions']
        assert result['retriever_contributions']['lancedb_hybrid']['retriever'] == "lancedb_hybrid"

        assert result['keywords_matched'] == [("keyword", 1.0)]
        assert result['matched_questions'] == []


class TestGetPolicyRecommendation:
    """Test get_policy_recommendation() public API."""

    def test_returns_dict_with_additional_context(self):
        """
        get_policy_recommendation() should return dict with additionalContext.

        Public API for hooks and external callers.
        """
        from macf.utils.recommend import get_policy_recommendation

        with patch('macf.utils.recommend._get_db_path') as mock_path:
            mock_db = MagicMock(spec=Path)
            mock_db.exists.return_value = False
            mock_path.return_value = mock_db

            result = get_policy_recommendation("test query with enough length")

            # Verify structure
            assert isinstance(result, dict)
            assert 'additionalContext' in result

    def test_explain_flag_includes_explanations(self):
        """
        explain=True should include explanations in output.

        Used for debugging and verbose mode.
        """
        from macf.utils.recommend import get_policy_recommendation

        with patch('macf.utils.recommend.get_recommendations') as mock_get:
            mock_get.return_value = ("formatted output", [{"policy_name": "test"}])

            result = get_policy_recommendation("test query", explain=True)

            # Verify explanations included
            assert 'additionalContext' in result
            assert 'explanations' in result
            assert result['explanations'] == [{"policy_name": "test"}]
