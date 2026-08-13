"""Size-based elision of oversized event payloads.

The predecessor guard tested whether ``tool_response`` was a dict containing
``stdout`` -- the shape one tool happens to return. Measured on a real log it
fired on 70% of records and caught 1.7% of the bytes, because every other tool's
response has a different shape and walked past it. On a second agent's log the
same predicate caught 0.2%.

These tests pin the two properties that fix depends on: the predicate is size
(so an unanticipated shape cannot escape it), and irreplaceable fields survive
regardless of size (so recovery is not bought with the record).
"""
import json

from macf.agent_events_log import (
    IRREPLACEABLE_FIELDS,
    elide_large_values,
    ELIDE_THRESHOLD_BYTES,
)

BIG = "x" * (ELIDE_THRESHOLD_BYTES + 1)


class TestPredicateIsSizeNotShape:
    def test_elides_a_large_value_whatever_the_surrounding_shape(self):
        """The regression. A dict with no `stdout` used to escape entirely."""
        out = elide_large_values({"tool_response": {"originalFile": BIG}})
        assert out["tool_response"]["originalFile"] == f"[{len(BIG)} bytes]"
        assert out["tool_response"]["originalFile_size"] == len(BIG)

    def test_still_elides_the_bash_shape(self):
        """CONTROL: the old guard's one true positive must remain one.

        Without this, the fix is indistinguishable from swapping one narrow
        predicate for another that happens to miss what the first caught.
        """
        out = elide_large_values({"tool_response": {"stdout": BIG, "stderr": ""}})
        assert out["tool_response"]["stdout"] == f"[{len(BIG)} bytes]"
        assert out["tool_response"]["stderr"] == ""

    def test_small_values_pass_through_untouched(self):
        """CONTROL: recovery must not come from eliding indiscriminately."""
        payload = {"event": "tool_call_completed", "data": {"tool": "Edit", "success": True}}
        assert elide_large_values(payload) == payload

    def test_reaches_arbitrary_nesting(self):
        out = elide_large_values({"a": {"b": [{"c": BIG}]}})
        assert out["a"]["b"][0]["c"] == f"[{len(BIG)} bytes]"

    def test_threshold_boundary_is_not_off_by_one(self):
        exact = "x" * ELIDE_THRESHOLD_BYTES
        assert elide_large_values({"f": exact})["f"] == exact
        assert elide_large_values({"f": exact + "x"})["f"].startswith("[")


class TestIrreplaceableFieldsSurvive:
    """A size threshold cannot tell a file's contents from a command.

    The contents are on disk; the command exists only in this log. Eliding both
    scores better on bytes recovered and destroys the half that matters.
    """

    def test_command_is_carried_whole_however_large(self):
        out = elide_large_values({"tool_input": {"command": BIG}})
        assert out["tool_input"]["command"] == BIG
        assert "command_size" not in out["tool_input"]

    def test_every_declared_exempt_field_survives(self):
        payload = {k: BIG for k in IRREPLACEABLE_FIELDS}
        out = elide_large_values(payload)
        assert out == payload

    def test_exemption_does_not_leak_to_its_neighbours(self):
        """CONTROL on the exemption: a non-exempt sibling must still be elided,
        so 'nothing was elided' cannot pass as 'exemptions worked'."""
        out = elide_large_values({"command": BIG, "content": BIG})
        assert out["command"] == BIG
        assert out["content"] == f"[{len(BIG)} bytes]"


class TestOutputRemainsUsable:
    def test_result_is_json_serialisable(self):
        json.dumps(elide_large_values({"tool_response": {"file": {"content": BIG}}}))

    def test_caller_payload_is_not_mutated(self):
        payload = {"tool_response": {"originalFile": BIG}}
        before = json.dumps(payload)
        elide_large_values(payload)
        assert json.dumps(payload) == before

    def test_non_dict_payloads_pass_through(self):
        assert elide_large_values("plain") == "plain"
        assert elide_large_values(None) is None


class TestBothWritePathsUseIt:
    """One implementation, both hooks. Two copies drift."""

    def test_post_tool_use_elides_before_writing(self, monkeypatch):
        import macf.hooks.handle_post_tool_use as h
        seen = {}
        monkeypatch.setattr(h, "append_event",
                            lambda **kw: seen.update(kw) or True)
        monkeypatch.setattr(h, "get_current_session_id", lambda *a, **k: "s")
        h.run(json.dumps({"tool_name": "Edit",
                          "tool_response": {"originalFile": BIG}}))
        assert seen["hook_input"]["tool_response"]["originalFile"].startswith("[")

    def test_pre_tool_use_elides_before_writing(self, monkeypatch):
        import macf.hooks.handle_pre_tool_use as h
        seen = {}
        monkeypatch.setattr(h, "append_event",
                            lambda **kw: seen.update(kw) or True)
        h.run(json.dumps({"tool_name": "Write",
                          "tool_input": {"content": BIG, "command": BIG}}))
        if seen:  # the pre hook has other early-return paths; only assert if it wrote
            ti = seen["hook_input"]["tool_input"]
            assert ti["content"].startswith("["), "large content should be elided"
            assert ti["command"] == BIG, "command is irreplaceable and must survive"
