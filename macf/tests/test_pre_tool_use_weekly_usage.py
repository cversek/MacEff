"""The PreToolUse line carries the week's usage beside CL, and omits it when unknown."""
import json
from unittest.mock import patch


def _run():
    from macf.hooks.handle_pre_tool_use import run
    return json.dumps(run(json.dumps({
        "tool_name": "Bash", "tool_input": {"command": "true"}, "session_id": "s-wk"})))


def test_the_line_carries_the_weekly_usage_after_cl():
    with patch("macf.budget.weekly_usage", return_value="71%"):
        out = _run()
    assert "wk 71%" in out
    assert out.index("CL") < out.index("wk 71%")


def test_no_sample_this_week_omits_the_field():
    with patch("macf.budget.weekly_usage", return_value=None):
        out = _run()
    assert " wk " not in out
