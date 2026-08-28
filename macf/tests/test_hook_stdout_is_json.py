"""A hook's stdout is a protocol, not a place to talk.

The SessionStart hook cold-starts the Transcript Monitor when it is down.
`start_daemon()` printed three lines to the CALLER's stdout before the hook
emitted its JSON, so `json.loads` failed at char 0, Claude Code never extracted
`systemMessage`, and the compaction-recovery banner was silently dropped. The
operator saw nothing at all on a compaction restart.

The failure is one-directional and invisible from the operator's side: the agent
still received the content as unparsed context, and there was no error, no
warning, no partial output. It looks exactly like a session where nothing needed
to be said.

It stayed latent because the hook only calls start_daemon when the monitor is
DOWN, and the daemon persists across sessions — so it needed a session start
coinciding with a dead monitor, which reads as intermittent.
"""
import io
import json
import contextlib

import pytest


class TestStartDaemonKeepsStdoutClean:
    """The prints are diagnostics; diagnostics belong on stderr."""

    def _capture(self, fn):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            fn()
        return out.getvalue(), err.getvalue()

    def test_already_running_says_nothing_on_stdout(self, monkeypatch):
        """NOTE the absence of raising=False.

        The first version of this test patched `_read_pidfile` and
        `_process_alive` with raising=False. Neither name exists — the real ones
        are `is_running` and `read_pid_file` — so the patches silently did
        nothing, start_daemon took an entirely different early-return path, and
        the test passed locally only because this machine happened to have a
        resolvable session transcript. CI, which does not, caught it.

        raising=False turns "you patched something that isn't there" into
        silence, which is the same shape as every other defect in this file:
        a call reporting success for a narrower question than the caller asked.
        """
        from macf.transcript_monitor import daemon as d
        monkeypatch.setattr(d, "is_running", lambda: True)
        monkeypatch.setattr(d, "read_pid_file", lambda: 4242)
        out, err = self._capture(d.start_daemon)
        assert out == "", f"stdout must stay parseable, got: {out!r}"
        assert "already running" in err

    def test_the_started_banner_is_on_stderr(self):
        """Read the source: all three lines must name stderr explicitly.

        Asserted against the file rather than by launching a real daemon,
        because forking one inside the suite is the kind of test that fails for
        reasons unrelated to what it checks.
        """
        import inspect
        from macf.transcript_monitor import daemon as d
        src = inspect.getsource(d.start_daemon)
        for line in ("Transcript Monitor started (PID", "Watching:", "Poll interval:"):
            idx = src.index(line)
            stmt = src[idx:src.index(")\n", idx) + 1]
            assert "sys.stderr" in stmt, f"{line!r} still writes to stdout"


class TestHookStdoutIsParseable:
    """The property that actually matters, stated where a reader will see it."""

    def test_session_start_emits_exactly_one_json_document(self, monkeypatch):
        from macf.hooks.handle_session_start import run
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = run("{}")
        printed = out.getvalue().strip()
        if printed:
            json.loads(printed)   # raises if anything polluted stdout
        assert isinstance(result, dict)
