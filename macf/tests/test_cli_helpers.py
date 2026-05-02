"""Tests for shared CLI helpers (cli.py module-level utilities)."""

import pytest

from macf.cli import _parse_task_id_arg


class TestParseTaskIdArg:
    """Unifies task_id parsing across cmd_task_* handlers (GH issue #68)."""

    def test_plain_digit_returns_int(self):
        assert _parse_task_id_arg("42") == 42

    def test_hash_prefix_stripped(self):
        assert _parse_task_id_arg("#42") == 42

    def test_leading_zero_preserves_string(self):
        # The "000" sentinel and reserved hierarchy slots like "00X" must
        # keep their string identity; coercing them to int=0 silently breaks
        # lookup against the string-keyed sentinel.
        assert _parse_task_id_arg("000") == "000"
        assert _parse_task_id_arg("#000") == "000"

    def test_leading_zero_with_other_digits(self):
        assert _parse_task_id_arg("042") == "042"

    def test_non_numeric_pass_through(self):
        # Legacy / future non-numeric task IDs should pass through as-is
        # rather than raising; downstream lookup will return None if the ID
        # doesn't exist.
        assert _parse_task_id_arg("alpha") == "alpha"

    def test_empty_after_strip_raises(self):
        with pytest.raises(ValueError):
            _parse_task_id_arg("#")
        with pytest.raises(ValueError):
            _parse_task_id_arg("")

    def test_single_zero_returns_int_zero(self):
        # "0" is a single-character form (no leading-zero ambiguity); ints
        # are unambiguous here.
        assert _parse_task_id_arg("0") == 0
