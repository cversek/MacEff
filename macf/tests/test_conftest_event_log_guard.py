"""The live event log guard names what was written, not only which module's window saw it (#933).

Under pytest-xdist every worker shares the environment's one event log, so a module-scoped
size check in one worker can see a write made by a module in another, and named the wrong
test. Its report now carries the appended events, which name the writer.
"""
import json

from conftest import _appended


def test_the_report_names_each_appended_event_and_no_data(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text(json.dumps({"event": "old", "breadcrumb": "s_1"}) + "\n")
    before = log.stat().st_size
    with log.open("a") as fh:
        fh.write(json.dumps({"event": "session_started", "breadcrumb": "s_a/c_1",
                             "data": {"marker": "do-not-quote"}}) + "\n")
        fh.write("not json\n")
    said = _appended(log, before, log.stat().st_size)
    assert said.startswith("session_started at s_a/c_1")
    assert "isn't JSON" in said
    assert "old" not in said, "only the window's own bytes"
    assert "do-not-quote" not in said, "the event's data stays out of the report"


def test_a_long_append_is_cut_short_with_a_count(tmp_path):
    log = tmp_path / "log.jsonl"
    log.write_text("".join(json.dumps({"event": f"e{i}"}) + "\n" for i in range(8)))
    said = _appended(log, 0, log.stat().st_size, limit=3)
    assert said.count(" at ") == 3 and said.endswith("and 5 more")
