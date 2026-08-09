"""Channel forwarding classifier for the Transcript Monitor (#093).

`extract_forwardable(entry)` decides what a *remote* operator should see mirrored to
the channel: the agent's narrative + CLI-typed user messages, but NOT tool results,
meta/compaction entries, or channel-origin user messages (echoing those back would
show the operator their own words). It is pure, so it is tested without the daemon.
"""

from macf.transcript_monitor.daemon import extract_forwardable


def test_assistant_text_string_forwards_with_agent_prefix():
    assert extract_forwardable({"type": "assistant", "message": {"content": "hello there"}}) == ("💬", "hello there")


def test_assistant_text_blocks_joined():
    entry = {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "thinking..."},
        {"type": "tool_use", "name": "Bash", "input": {}},
        {"type": "text", "text": "done"},
    ]}}
    assert extract_forwardable(entry) == ("💬", "thinking...\ndone")


def test_assistant_with_no_text_is_skipped():
    entry = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Bash"}]}}
    assert extract_forwardable(entry) is None


def test_direct_user_message_forwards_with_cli_prefix():
    assert extract_forwardable({"type": "user", "message": {"content": "do the thing"}}) == ("👤 CLI", "do the thing")


def test_channel_origin_user_message_is_not_echoed_back():
    entry = {"type": "user", "message": {"content": "from telegram"},
             "origin": {"kind": "channel", "server": "telegram"}}
    assert extract_forwardable(entry) is None


def test_tool_result_user_entry_is_skipped():
    entry = {"type": "user", "toolUseResult": {"stdout": "x"},
             "message": {"content": [{"type": "tool_result", "content": "x"}]}}
    assert extract_forwardable(entry) is None


def test_tool_result_blocks_without_flag_still_skipped():
    entry = {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}}
    assert extract_forwardable(entry) is None


def test_meta_and_compaction_entries_skipped():
    assert extract_forwardable({"type": "user", "isMeta": True, "message": {"content": "m"}}) is None
    assert extract_forwardable({"type": "user", "isCompactSummary": True, "message": {"content": "c"}}) is None


def test_non_message_types_skipped():
    assert extract_forwardable({"type": "system", "subtype": "api_error"}) is None
    assert extract_forwardable({"type": "queue-operation", "operation": "enqueue"}) is None
    assert extract_forwardable({}) is None
