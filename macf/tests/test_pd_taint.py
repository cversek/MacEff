"""Whether the session's context holds untrusted input (the scheduler design, 5.3)."""
import pytest

from macf.pd.taint import taint


def tool(name, command=None):
    event = {"event": "tool_call_started", "data": {"tool": name, "session_id": "s"}}
    if command is not None:
        event["hook_input"] = {"tool_input": {"command": command}}
    return event


def prompt(text):
    return {"event": "dev_drv_started", "data": {"session_id": "s", "prompt_preview": text}}


START = {"event": "session_started", "data": {"session_id": "s"}}
COMPACTED = {"event": "compaction_detected", "data": {"session_id": "s"}}


@pytest.mark.parametrize("event, says", [
    (tool("WebFetch"), "a web fetch"),
    (tool("mcp__claude_ai_Gmail__search"), "a read by mcp__claude_ai_Gmail__search"),
    (tool("Bash", "gh api repos/o/r/issues/552/comments"), "a Bash call that names a host"),
    (tool("Bash", "curl -s https://example.com/x"), "a Bash call that names a host"),
    (tool("Bash", "git -C repo fetch origin"), "a Bash call that names a host"),
    (tool("Bash", "ping manny.local"), "a Bash call that names a host"),
    (prompt('<channel source="telegram" chat_id="1">hello</channel>'), "a message by telegram"),
])
def test_each_kind_of_untrusted_input_taints_the_context(event, says):
    assert taint([event, START]) == [says]


@pytest.mark.parametrize("event", [
    tool("Read"),
    tool("Bash", "pytest macf/tests/test_pd_taint.py -q"),
    tool("Bash", "git -C repo log --oneline -3"),
    tool("mcp__plugin_telegram_telegram__reply"),
    prompt('<channel source="plugin:maceff-channel:maceff" notice_id="n">fixed words</channel>'),
    prompt("continue with the build"),
])
def test_what_reads_nothing_from_outside_leaves_it_clean(event):
    assert taint([event, START]) == []


def test_taint_runs_from_the_last_boundary_and_no_further():
    """Taint follows the context: a fetch before the last compaction is gone from it, and one
    after is still in it however many turns later. Each kind is said once."""
    fetched = tool("WebFetch")
    assert taint([tool("Read"), COMPACTED, fetched, START]) == []
    assert taint([tool("Read"), fetched, tool("Read"), fetched, COMPACTED]) == ["a web fetch"]


def test_a_context_no_boundary_bounds_reads_tainted():
    """With no session start or compaction in the log, nothing shows the context clean."""
    assert taint([tool("Read")])
    assert taint([])
