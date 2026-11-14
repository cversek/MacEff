"""The capture unit's entry point: what it refuses to run with, and what it logs (MIS-0008 6.3)."""
import pytest

from macf.pd.interface import Declaration, Unit, VoiceSection, declaration_path
from macf.voice.capture import __main__ as entry
from macf.voice.capture.unit import Utterance

from test_primal_daemon import CARD, ME, base, make_home, run_daemon  # noqa: F401 - fixtures


def _home(tmp_path, voice=True):
    unit = Unit(name="capture", command=["true"], account=ME, restart="never", liveness_interval_s=60.0,
                memory_limit_mb=64)
    home = make_home(tmp_path, [unit])
    declaration_path(home).write_text(Declaration(
        version=1, agent=CARD, units=[unit],
        voice=VoiceSection(capture_unit="capture") if voice else None).model_dump_json())
    return home


def test_a_home_without_a_voice_section_is_refused_with_its_reason(tmp_path, capsys):
    assert entry.main([str(_home(tmp_path, voice=False))]) == entry.EX_CONFIG
    assert "declares no voice section" in capsys.readouterr().err


def test_a_unit_the_voice_section_does_not_name_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("MACF_PD_UNIT", "someone-else")
    assert entry.main([str(_home(tmp_path))]) == entry.EX_CONFIG
    assert "names 'capture' as its capture unit" in capsys.readouterr().err


def test_no_home_is_a_usage_error(tmp_path, capsys):
    assert entry.main([str(tmp_path / "nowhere")]) == entry.EX_CONFIG
    assert "usage" in capsys.readouterr().err


def test_a_receipt_is_logged_by_id_and_outcome_never_by_words(tmp_path, base, run_daemon, monkeypatch, capsys,
                                                             isolated_events_log):
    """The unit's own log, like the daemon's (R10), says which utterance ended how, and not what was said."""
    import macf.pd.interface as interface
    daemon = run_daemon(_home(tmp_path), base)
    monkeypatch.setattr(interface, "control_socket", lambda card: daemon.control_path)
    entry.deliver(CARD, Utterance(trigger="hold_key", spoken_at=1794600000.0, screen="unlocked",
                                  text="the secret plan for Friday"))
    err = capsys.readouterr().err
    assert "hold_key utterance utt-" in err and "refused" in err
    assert "secret plan" not in err


def test_an_unreachable_daemon_drops_the_utterance_and_says_so(tmp_path, monkeypatch, capsys):
    import macf.pd.interface as interface
    monkeypatch.setattr(interface, "control_socket", lambda card: tmp_path / "no.sock")
    entry.deliver(CARD, Utterance(trigger="wake_phrase", spoken_at=1.0, screen="unknown", text="hello there"))
    err = capsys.readouterr().err
    assert "could not reach the daemon, so it was dropped" in err and "hello there" not in err


def test_whisper_is_primed_with_the_declared_vocabulary_then_the_phrase():
    """The operator's curated names and terms come first, the wake phrase stays whole at the end, and a
    vocabulary too long for Whisper's budget is cut, never the phrase."""
    from macf.voice.capture.__main__ import PROMPT_CHARS, whisper_prompt
    assert whisper_prompt("yo tom", "Ada works on Widgets with Bob.") == "Ada works on Widgets with Bob. Yo tom,"
    assert whisper_prompt("yo tom", None) == "Yo tom, " and whisper_prompt(None, None) is None
    assert whisper_prompt(None, "  Cy, Dee.  ") == "Cy, Dee."
    long = whisper_prompt("yo tom", "x" * 5000)
    assert len(long) <= PROMPT_CHARS and long.endswith("Yo tom,")


def test_the_voice_section_carries_a_transcription_prompt():
    from macf.pd.interface import VoiceSection
    assert VoiceSection(capture_unit="voice-capture", transcription_prompt="Ada, Bob, Cy.").transcription_prompt == "Ada, Bob, Cy."
