"""Regression tests for gh-version field drift in GH_PR/GH_ISSUE creation (GH #123).

Current `gh` rejects the whole `gh <view> --json <fields>` call with
`Unknown JSON field: X` if any single field is unsupported. That made a drifted
optional field (`closingIssuesReferences`) fatal, so GH_PR/GH_ISSUE tasks could
not be created at all. `_gh_view_json` degrades: it drops the field gh names and
retries, instead of taking the whole task down over one optional field.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from macf.task.create import _gh_view_json


def _result(returncode, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _requested_fields(cmd):
    return cmd[cmd.index("--json") + 1]


def test_drops_unsupported_field_and_retries():
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "closingIssuesReferences" in _requested_fields(cmd):
            return _result(1, stderr="unknown JSON field.\nUnknown JSON field: closingIssuesReferences")
        return _result(0, stdout=json.dumps({"title": "T", "state": "OPEN"}))

    with patch("subprocess.run", side_effect=fake_run):
        data = _gh_view_json(
            ["gh", "pr", "view", "1", "--repo", "o/r"],
            ["title", "state", "closingIssuesReferences"],
        )

    assert data == {"title": "T", "state": "OPEN"}
    assert len(calls) == 2  # failed once, retried without the drifted field
    assert "closingIssuesReferences" not in _requested_fields(calls[1])


def test_drops_multiple_drifted_fields_one_at_a_time():
    def fake_run(cmd, **kwargs):
        fields = _requested_fields(cmd)
        for bad in ("closingIssuesReferences", "reviewDecision"):
            if bad in fields:
                return _result(1, stderr=f"Unknown JSON field: {bad}")
        return _result(0, stdout=json.dumps({"title": "T"}))

    with patch("subprocess.run", side_effect=fake_run):
        data = _gh_view_json(
            ["gh", "pr", "view", "1", "--repo", "o/r"],
            ["title", "reviewDecision", "closingIssuesReferences"],
        )
    assert data == {"title": "T"}


def test_success_on_first_try_returns_all_fields():
    with patch("subprocess.run", return_value=_result(0, stdout=json.dumps({"title": "T", "url": "u"}))):
        data = _gh_view_json(["gh", "issue", "view", "1", "--repo", "o/r"], ["title", "url"])
    assert data == {"title": "T", "url": "u"}


def test_non_field_error_still_raises():
    with patch("subprocess.run", return_value=_result(1, stderr="gh: not authenticated")):
        with pytest.raises(ValueError, match="not authenticated"):
            _gh_view_json(["gh", "pr", "view", "1", "--repo", "o/r"], ["title"])
