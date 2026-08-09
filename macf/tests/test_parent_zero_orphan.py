"""Regression tests for the parent-zero orphan bug (GH cversek/MacEff#208).

`macf_tools task create ... --parent 0` used to be accepted verbatim: the string
``"0"`` is truthy, so ``parent_id if parent_id else SENTINEL_TASK_ID`` kept it,
and because the task tree is rendered by walking children down from ``"000"`` a
task parented to ``"0"`` (which ``!= "000"``) dropped out of the tree while
creation still reported success.

The fix normalizes every zero-equivalent spelling to the single canonical root
``"000"`` at the one chokepoint (`normalize_parent_id`) that all `create_*`
functions funnel through, so a zero-orphaned task can no longer be represented.
"""

import pytest

from macf.task.create import normalize_parent_id, SENTINEL_TASK_ID


class TestNormalizeParentId:
    """The chokepoint every create_* path uses to canonicalize --parent."""

    @pytest.mark.parametrize("raw", [
        None,          # --parent omitted (string paths pass None)
        0,             # sprint/play_time integer default
        "",            # empty string
        "   ",         # whitespace only
        "0",           # THE bug: explicit --parent 0 as a string
        "00",
        "000",         # already canonical root
        "0000",
        "#0",          # leading-# form
        "#000",
        "#",           # bare hash strips to empty → root
    ])
    def test_all_zero_spellings_collapse_to_root(self, raw):
        assert normalize_parent_id(raw) == SENTINEL_TASK_ID

    @pytest.mark.parametrize("raw,expected", [
        ("5", "5"),
        (5, "5"),
        ("#5", "5"),
        ("##7", "7"),   # lenient: extra hashes are stripped
        ("42", "42"),
        ("  42  ", "42"),
        ("#101", "101"),
    ])
    def test_nonzero_ids_kept_as_bare_digit_string(self, raw, expected):
        # Non-root IDs are stored unpadded (only the root is "000"), so the
        # bare digit string must be preserved for the tree walk to match.
        assert normalize_parent_id(raw) == expected

    @pytest.mark.parametrize("raw", ["abc", "1a", "-1", "3.0"])
    def test_non_digit_input_is_rejected(self, raw):
        with pytest.raises(ValueError):
            normalize_parent_id(raw)

    def test_root_is_never_orphaned(self):
        # The invariant the bug violated: no zero spelling may produce a value
        # other than the canonical root that the tree walk starts from.
        for raw in (0, "0", "00", "000", "0000", "#0"):
            assert normalize_parent_id(raw) == "000"
