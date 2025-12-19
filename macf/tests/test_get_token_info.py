"""
Pragmatic tests for token info implementation.

Tests core functionality of get_token_info() and macf_tools context CLI.
Focus: Happy path + key edge cases, not exhaustive permutations.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from macf.utils import get_token_info
from macf.cli import cmd_context


class TestGetTokenInfo:
    """Test suite for get_token_info() function (4-6 focused tests)."""

    def test_returns_correct_structure(self):
        """
        Test return dict has required keys.

        Should return dict with:
        - tokens_used, tokens_remaining
        - percentage_used, percentage_remaining
        - cluac_level, source
        """
        result = get_token_info()

        required_keys = [
            'tokens_used', 'tokens_remaining',
            'percentage_used', 'percentage_remaining',
            'cluac_level', 'source'
        ]

        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

        # Verify types
        assert isinstance(result['tokens_used'], int)
        assert isinstance(result['tokens_remaining'], int)
        assert isinstance(result['cluac_level'], int)
        assert isinstance(result['source'], str)

    def test_max_tokens_enforced(self):
        """
        Test max_tokens is 200000 (CC 2.0 transparent accounting).

        Critical: CLUAC calculations depend on correct max_tokens value.
        CC 2.0 shows 200k total (155k usable + 45k autocompact buffer).
        """
        # Mock to force default fallback (no session data)
        with patch('macf.utils.tokens.get_current_session_id', return_value='unknown'):
            with patch('macf.utils.tokens.get_session_transcript_path', return_value=None):
                with patch('macf.utils.tokens.find_project_root') as mock_root:
                    mock_root.return_value = Path('/tmp/nonexistent')

                    result = get_token_info()

        # Verify max_tokens constant is 200000 (CC 2.0 transparent accounting)
        assert result['tokens_remaining'] == 200000
        assert result['percentage_remaining'] == 100.0

    def test_cluac_calculation_accuracy(self):
        """
        Test CLUAC = round(percentage_remaining).

        Formula: percentage_remaining = (tokens_remaining / 200000) * 100
        CLUAC = round(percentage_remaining)
        """
        # Mock JSONL with known token values (including output_tokens)
        mock_jsonl_content = json.dumps({
            "type": "assistant",
            "message": {
                "usage": {
                    "cache_read_input_tokens": 50000,
                    "cache_creation_input_tokens": 10000,
                    "input_tokens": 30000,
                    "output_tokens": 10000
                }
            }
        })

        with patch('macf.utils.get_current_session_id', return_value='test-session'):
            with patch('macf.utils.get_session_transcript_path', return_value='/fake/path.jsonl'):
                with patch('pathlib.Path.exists', return_value=True):
                    with patch('builtins.open', create=True) as mock_open:
                        # Setup mock file
                        mock_file = MagicMock()
                        mock_file.__enter__.return_value = mock_file
                        mock_file.read.return_value = mock_jsonl_content.encode('utf-8')
                        mock_file.seek.return_value = 0
                        mock_file.__iter__.return_value = [mock_jsonl_content.encode('utf-8') + b'\n']
                        mock_open.return_value = mock_file

                        result = get_token_info()

        # Verify calculation: 100000 actual tokens used
        expected_tokens_used = 100000  # actual tokens from JSONL
        expected_tokens_remaining = 200000 - 100000  # 100000
        expected_percentage_remaining = (100000 / 200000) * 100  # 50%
        expected_cluac = round(expected_percentage_remaining)  # 50

        assert result['tokens_used'] == expected_tokens_used
        assert result['cluac_level'] == expected_cluac

    def test_fallback_when_jsonl_unavailable(self):
        """
        Test graceful fallback when JSONL unavailable.

        Should return default values without crashing.
        """
        with patch('macf.utils.tokens.get_current_session_id', return_value='unknown'):
            with patch('macf.utils.tokens.get_session_transcript_path', return_value=None):
                with patch('macf.utils.tokens.find_project_root') as mock_root:
                    mock_root.return_value = Path('/tmp/nonexistent')

                    result = get_token_info()

        # Should return default values (CC 2.0: 200k total)
        # NOTE: cluac_level=100 means 100% remaining (full context available)
        # hooks_state fallback removed - event-first architecture
        assert result['tokens_used'] == 0
        assert result['tokens_remaining'] == 200000
        assert result['percentage_used'] == 0.0
        assert result['percentage_remaining'] == 100.0
        assert result['cluac_level'] == 100
        assert result['source'] == 'default'

    def test_with_valid_session_id_parameter(self):
        """
        Test get_token_info(session_id='specific-session').

        Should use provided session_id instead of auto-detection.
        """
        test_session_id = 'test-session-12345'

        with patch('macf.utils.tokens.get_session_transcript_path') as mock_path:
            mock_path.return_value = None  # Simulate not found

            result = get_token_info(session_id=test_session_id)

            # Verify session_id was used
            mock_path.assert_called_once_with(test_session_id)

        # Should still return valid structure on failure
        assert 'tokens_used' in result
        assert 'cluac_level' in result

    def test_tokens_used_reflects_actual_jsonl(self):
        """
        Test that tokens_used reflects actual JSONL usage without any buffer added.

        NOTE: tokens_used returns the actual token count from JSONL parsing.
        Any buffer considerations are handled at display layer, not in raw data.
        """
        # Mock JSONL with 80k actual usage
        mock_jsonl = json.dumps({
            "type": "assistant",
            "message": {
                "usage": {
                    "cache_read_input_tokens": 40000,
                    "cache_creation_input_tokens": 20000,
                    "input_tokens": 15000,
                    "output_tokens": 5000
                }
            }
        })

        with patch('macf.utils.get_current_session_id', return_value='test'):
            with patch('macf.utils.get_session_transcript_path', return_value='/fake.jsonl'):
                with patch('pathlib.Path.exists', return_value=True):
                    with patch('builtins.open', create=True) as mock_open:
                        mock_file = MagicMock()
                        mock_file.__enter__.return_value = mock_file
                        mock_file.read.return_value = mock_jsonl.encode('utf-8')
                        mock_file.seek.return_value = 0
                        mock_file.__iter__.return_value = [mock_jsonl.encode('utf-8') + b'\n']
                        mock_open.return_value = mock_file

                        result = get_token_info()

        # tokens_used reflects actual JSONL tokens (no buffer added)
        assert result['tokens_used'] == 80000, "tokens_used should be actual tokens"
        assert result['tokens_remaining'] == 120000, "Remaining = 200k - 80k actual"


class TestContextCLI:
    """Test suite for macf_tools context CLI command (2-4 tests)."""

    def test_human_readable_output(self, capsys):
        """
        Test macf_tools context default output format.

        Should display:
        - Token Usage: X / 152,576 (Y%)
        - Remaining: Z tokens
        - CLUAC Level: N
        - Source: [source]
        """
        # Create mock args
        args = Mock()
        args.session = None
        args.json_output = False

        # Mock get_token_info return (CC 2.0: 200k total)
        mock_token_info = {
            'tokens_used': 100000,
            'tokens_remaining': 100000,
            'percentage_used': 50.0,
            'percentage_remaining': 50.0,
            'cluac_level': 50,
            'source': 'jsonl'
        }

        with patch('macf.cli.get_token_info', return_value=mock_token_info):
            result = cmd_context(args)

        # Capture output
        captured = capsys.readouterr()

        # Verify return code
        assert result == 0

        # Verify output format (CC 2.0: shows /200,000)
        assert "Token Usage: 100,000 / 200,000" in captured.out
        assert "Remaining: 100,000" in captured.out
        assert "CLUAC Level: 50" in captured.out
        assert "Source: jsonl" in captured.out

    def test_json_output_format(self, capsys):
        """
        Test macf_tools context --json output.

        Should output valid JSON with all token fields.
        """
        args = Mock()
        args.session = None
        args.json_output = True

        mock_token_info = {
            'tokens_used': 75000,
            'tokens_remaining': 77576,
            'percentage_used': 49.2,
            'percentage_remaining': 50.8,
            'cluac_level': 51,
            'source': 'hooks_state'
        }

        with patch('macf.cli.get_token_info', return_value=mock_token_info):
            result = cmd_context(args)

        captured = capsys.readouterr()

        assert result == 0

        # Parse JSON output
        output_json = json.loads(captured.out)

        assert output_json['tokens_used'] == 75000
        assert output_json['cluac_level'] == 51
        assert output_json['source'] == 'hooks_state'

    def test_with_session_parameter(self):
        """
        Test macf_tools context --session <id>.

        Should pass session_id to get_token_info().
        """
        args = Mock()
        args.session = 'custom-session-789'
        args.json_output = False

        with patch('macf.cli.get_token_info') as mock_get_info:
            mock_get_info.return_value = {
                'tokens_used': 50000,
                'tokens_remaining': 102576,
                'percentage_used': 32.8,
                'percentage_remaining': 67.2,
                'cluac_level': 67,
                'source': 'jsonl'
            }

            result = cmd_context(args)

            # Verify session_id was passed
            mock_get_info.assert_called_once_with(session_id='custom-session-789')

        assert result == 0

    def test_error_handling_graceful_failure(self, capsys):
        """
        Test cmd_context handles errors without crashing.

        Should print error message and return exit code 1.
        """
        args = Mock()
        args.session = None
        args.json_output = False

        # Simulate exception in get_token_info
        with patch('macf.cli.get_token_info', side_effect=Exception('Test error')):
            result = cmd_context(args)

        captured = capsys.readouterr()

        # Should return error code
        assert result == 1

        # Should show error message
        assert "Error getting token info" in captured.out


# Edge Cases Test
class TestTokenInfoEdgeCases:
    """Additional edge case tests (optional - only if critical)."""

    def test_zero_tokens_used(self):
        """Test behavior when no tokens used yet (fresh session)."""
        # Mock to force default fallback (zero tokens used)
        with patch('macf.utils.tokens.get_current_session_id', return_value='unknown'):
            with patch('macf.utils.tokens.get_session_transcript_path', return_value=None):
                with patch('macf.utils.tokens.find_project_root') as mock_root:
                    mock_root.return_value = Path('/tmp/nonexistent')

                    result = get_token_info()

        # Fresh session should have CLUAC = 0 or 100 for zero tokens
        assert result['cluac_level'] in [0, 100]
        assert result['tokens_used'] == 0

    def test_near_compaction_tokens(self):
        """Test CLUAC calculation near compaction threshold."""
        # Mock near-compaction scenario (160k tokens used including output)
        mock_jsonl = json.dumps({
            "type": "assistant",
            "message": {
                "usage": {
                    "cache_read_input_tokens": 70000,
                    "cache_creation_input_tokens": 40000,
                    "input_tokens": 30000,
                    "output_tokens": 20000
                }
            }
        })

        with patch('macf.utils.get_current_session_id', return_value='test'):
            with patch('macf.utils.get_session_transcript_path', return_value='/fake.jsonl'):
                with patch('pathlib.Path.exists', return_value=True):
                    with patch('builtins.open', create=True) as mock_open:
                        mock_file = MagicMock()
                        mock_file.__enter__.return_value = mock_file
                        mock_file.read.return_value = mock_jsonl.encode('utf-8')
                        mock_file.seek.return_value = 0
                        mock_file.__iter__.return_value = [mock_jsonl.encode('utf-8') + b'\n']
                        mock_open.return_value = mock_file

                        result = get_token_info()

        # 160k actual tokens used (no buffer added)
        # tokens_remaining = 200k - 160k = 40k
        # percentage_remaining = (40k / 200k) * 100 = 20%
        assert result['tokens_used'] == 160000  # actual tokens from JSONL
        assert result['cluac_level'] == 20  # 20% remaining
