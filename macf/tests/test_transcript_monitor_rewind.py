"""A rewind is told from the transcript's parent links, not from its size (#1003)."""
import json

from macf.transcript_monitor.rewind import RewindWatch


class Chat:
    """Builds transcript entries the way the client links them."""

    def __init__(self):
        self.n = 0
        self.entries = []

    def add(self, kind, parent, content, **extra):
        self.n += 1
        uuid = f"u{self.n}"
        entry = {"uuid": uuid, "parentUuid": parent, "type": kind,
                 "timestamp": f"2026-01-01T00:{self.n:02d}:00Z",
                 "message": {"content": content}, **extra}
        self.entries.append(entry)
        return uuid

    def prompt(self, parent, text="go on"):
        return self.add("user", parent, text)

    def turn(self, parent, command=None):
        """An assistant reply, optionally running a Bash command, and its result."""
        if command is None:
            return self.add("assistant", parent, [{"type": "text", "text": "ok"}])
        call = self.add("assistant", parent, [{"type": "tool_use", "name": "Bash",
                                               "input": {"command": command}}])
        return self.add("user", call, [{"type": "tool_result", "content": "done"}])


def feed(watch, entries):
    return [d for d in (watch(e) for e in entries) if d is not None]


def test_a_straight_conversation_reports_nothing():
    chat = Chat()
    at = chat.prompt(None)
    for _ in range(5):
        at = chat.turn(at)
        at = chat.prompt(at)
    assert feed(RewindWatch(), chat.entries) == []


def test_a_rewind_past_three_turns_is_reported_with_its_span_and_tools():
    chat = Chat()
    start = chat.turn(chat.prompt(None))
    at = chat.prompt(start)
    at = chat.turn(at, "PAGER=cat gh pr review 12 --approve")
    at = chat.turn(at, "# publish it\n(git push)")
    at = chat.turn(at)
    chat.prompt(start, "the second answer, please")       # the rewind
    [found] = feed(RewindWatch(), chat.entries)
    assert found.event_name == "context_rewind_detected"
    data = found.data
    assert data["branch_from"] == start
    assert data["dropped_assistant_entries"] == 3
    assert data["tools"] == {"Bash:gh": 1, "Bash:git": 1}
    assert data["dropped_from"] < data["dropped_to"] < data["prompt_time"]


def test_a_rewind_past_fewer_turns_than_the_threshold_is_not_reported():
    chat = Chat()
    start = chat.turn(chat.prompt(None))
    chat.turn(chat.prompt(start))
    chat.prompt(start)
    assert feed(RewindWatch(), chat.entries) == []


def test_each_rewind_to_the_same_point_reports_only_its_own_turns():
    chat = Chat()
    start = chat.turn(chat.prompt(None))
    for _ in range(2):
        at = chat.prompt(start)
        for _ in range(3):
            at = chat.turn(at)
    chat.prompt(start)
    found = feed(RewindWatch(), chat.entries)
    assert [d.data["dropped_assistant_entries"] for d in found] == [3, 3]


def test_the_chain_after_a_compaction_is_not_a_rewind():
    chat = Chat()
    at = chat.prompt(None)
    for _ in range(4):
        at = chat.turn(at)
    boundary = chat.add("system", None, "", subtype="compact_boundary")   # as the client writes it
    summary = chat.add("user", boundary, "summary of the earlier conversation", isCompactSummary=True)
    chat.turn(chat.prompt(summary))
    assert feed(RewindWatch(), chat.entries) == []


def test_priming_makes_a_rewind_to_before_the_monitor_started_visible(tmp_path):
    chat = Chat()
    start = chat.turn(chat.prompt(None))
    at = chat.prompt(start)
    for _ in range(3):
        at = chat.turn(at)
    transcript = tmp_path / "s.jsonl"
    transcript.write_text("".join(json.dumps(e) + "\n" for e in chat.entries))
    resumed = {"uuid": "late", "parentUuid": start, "type": "user",
               "timestamp": "2026-01-02T00:00:00Z", "message": {"content": "carry on"}}

    assert feed(RewindWatch(), [resumed]) == []           # unprimed: nothing to compare
    watch = RewindWatch()
    assert watch.prime(transcript) == len(chat.entries)
    [found] = feed(watch, [resumed])
    assert found.data["dropped_assistant_entries"] == 3


def test_a_session_monitor_watches_for_rewinds_from_the_transcripts_tail(tmp_path, isolated_events_log):
    from macf.transcript_monitor import daemon
    chat = Chat()
    start = chat.turn(chat.prompt(None))
    at = chat.prompt(start)
    for _ in range(3):
        at = chat.turn(at)
    transcript = tmp_path / "s.jsonl"
    transcript.write_text("".join(json.dumps(e) + "\n" for e in chat.entries))
    monitor, _ = daemon._session_monitor(transcript, 0.05, 0, {})
    [watch] = [d for d in monitor.detectors if isinstance(d, RewindWatch)]
    resumed = {"uuid": "late", "parentUuid": start, "type": "user",
               "timestamp": "2026-01-02T00:00:00Z", "message": {"content": "carry on"}}
    assert watch(resumed) is not None                     # primed from the file at build
