"""Session start states its context's size and says loudly when it's past the inline limit (#802).

Claude Code shows a hook's additionalContext inline up to about 10,000 characters and keeps a
longer one in a file, showing the model a preview. The recovery message runs to tens of thousands
of characters, so what the model reads is only its start. The hook now records each size in its
own log and warns past the limit, so an overrun is seen instead of inferred.
"""
import macf.hooks.handle_session_start as hss


def _logged(monkeypatch):
    seen = []
    monkeypatch.setattr(hss, "log_hook_event", lambda event, raw_input=None: seen.append(event))
    return seen


def test_every_context_is_measured_in_the_hooks_log(monkeypatch, capsys):
    seen = _logged(monkeypatch)
    context = "x" * 500 + "🏗️"          # one emoji: three different counts
    assert hss._measured(context, "startup", "s1") == context
    [event] = [e for e in seen if e["event_type"] == "CONTEXT_SIZE"]
    assert (event["path"], event["chars"], event["over_inline_limit"]) == ("startup", 502, False)
    assert (event["utf8_bytes"], event["utf16_units"]) == (507, 503)
    assert "inline" not in capsys.readouterr().err


def test_a_context_past_the_inline_limit_is_said_loudly(monkeypatch, capsys):
    seen = _logged(monkeypatch)
    big = "y" * (hss.OBSERVED_INLINE_LIMIT_CHARS + 1)
    assert hss._measured(big, "compaction", "s1") == big
    assert seen[-1]["over_inline_limit"] is True
    err = capsys.readouterr().err
    assert "compaction session-start context" in err and "preview" in err


def test_a_failing_log_never_breaks_session_start(monkeypatch, capsys):
    def broken(event, raw_input=None):
        raise OSError("disk full")
    monkeypatch.setattr(hss, "log_hook_event", broken)
    assert hss._measured("z", "resume") == "z"
    assert "could not measure" in capsys.readouterr().err
