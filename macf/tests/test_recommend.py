#!/usr/bin/env python3
"""
Unit tests for policy recommendation (hybrid RRF search).

Tests macf.utils.recommend module:
- get_policy_db_path() - Portable path resolution
- ExplainedRecommendation dataclass - Structure validation
- RetrieverScore dataclass - Structure validation
- get_recommendations() - Return tuple structure
- Warning when DB not found
- Short query filtering
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

        Should NOT use hardcoded Path.home(), must use portable resolution.
        """
        with patch('macf.utils.recommend.find_agent_home') as mock_find_home:
            mock_find_home.return_value = Path('/mock/agent/home')

            result = get_policy_db_path()

            # Verify find_agent_home was called
            mock_find_home.assert_called_once()

            # Verify path structure
            assert result == Path('/mock/agent/home/.maceff/policy_index.db')
            assert result.name == 'policy_index.db'
            assert result.parent.name == '.maceff'


class TestDataclassStructures:
    """Test dataclass field requirements."""

    def test_retriever_score_has_required_fields(self):
        """
        RetrieverScore dataclass should have required fields.

        Required: retriever, rank, raw_score, rrf_contribution, matched_text
        """
        score = RetrieverScore(
            retriever="policies_fts",
            rank=1,
            raw_score=0.85,
            rrf_contribution=0.016,
            matched_text="test query"
        )

        # Verify all required fields exist
        assert score.retriever == "policies_fts"
        assert score.rank == 1
        assert score.raw_score == 0.85
        assert score.rrf_contribution == 0.016
        assert score.matched_text == "test query"

        # Verify dataclass has exactly these fields
        field_names = {f.name for f in fields(RetrieverScore)}
        expected = {'retriever', 'rank', 'raw_score', 'rrf_contribution', 'matched_text'}
        assert field_names == expected

    def test_explained_recommendation_has_required_fields(self):
        """
        ExplainedRecommendation dataclass should have required fields.

        Required: policy_name, rrf_score, confidence_tier, retriever_contributions
        """
        rec = ExplainedRecommendation(
            policy_name="test_policy",
            rrf_score=0.045,
            confidence_tier="HIGH",
        )

        # Verify required fields
        assert rec.policy_name == "test_policy"
        assert rec.rrf_score == 0.045
        assert rec.confidence_tier == "HIGH"

        # Verify default factories work
        assert isinstance(rec.retriever_contributions, dict)
        assert isinstance(rec.keywords_matched, list)
        assert isinstance(rec.questions_matched, list)

        # Verify all expected fields exist
        field_names = {f.name for f in fields(ExplainedRecommendation)}
        expected = {
            'policy_name', 'rrf_score', 'confidence_tier',
            'retriever_contributions', 'keywords_matched', 'questions_matched'
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
            mock_db.__str__.return_value = '/fake/path/policy_index.db'
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
        short_queries = [
            "",
            "a",
            "short",
            "123456789",  # 9 chars (just below threshold)
        ]

        for query in short_queries:
            result = get_recommendations(query)
            formatted_output, explanations = result

            # Should return empty for short queries
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

    def test_graceful_failure_on_db_exception(self):
        """
        Should handle DB exceptions gracefully without crashing.

        Should return empty tuple on any exception.
        """
        with patch('macf.utils.recommend._get_db_path') as mock_path:
            mock_db = MagicMock(spec=Path)
            mock_db.exists.return_value = True
            mock_path.return_value = mock_db

            # Simulate DB connection failure
            with patch('sqlite3.connect', side_effect=Exception('DB error')):
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
            retriever="policies_fts",
            rank=1,
            raw_score=0.85,
            rrf_contribution=0.016,
            matched_text="test"
        )

        rec = ExplainedRecommendation(
            policy_name="test_policy",
            rrf_score=0.045,
            confidence_tier="HIGH",
            retriever_contributions={"policies_fts": score},
            keywords_matched=[("keyword", 1.0)],
            questions_matched=["test question"],
        )

        result = rec.to_dict()

        # Verify structure
        assert isinstance(result, dict)
        assert result['policy_name'] == "test_policy"
        assert result['rrf_score'] == 0.045
        assert result['confidence_tier'] == "HIGH"

        # Verify nested structures
        assert 'retriever_contributions' in result
        assert 'policies_fts' in result['retriever_contributions']
        assert result['retriever_contributions']['policies_fts']['retriever'] == "policies_fts"

        assert result['keywords_matched'] == [("keyword", 1.0)]
        assert result['questions_matched'] == ["test question"]
