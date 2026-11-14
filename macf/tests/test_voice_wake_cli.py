"""``macf_tools voice wake``: define, train, status, test (MIS-0008 6.5)."""
from types import SimpleNamespace

import numpy as np

from macf.voice.wake import cli as wake_cli
from macf.voice.wake import train as wake_train
from macf.voice.wake.model import WakeModel

from test_voice_wake import band_embed, recorded_set


def test_define_refuses_a_phrase_that_cannot_work_and_names_why(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wake_cli, "_home", lambda: tmp_path)
    assert wake_cli.cmd_define(SimpleNamespace(phrase="Tom")) == 1
    assert "refused" in capsys.readouterr().out and not (tmp_path / ".maceff").exists()


def test_define_says_what_to_declare(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wake_cli, "_home", lambda: tmp_path)
    assert wake_cli.cmd_define(SimpleNamespace(phrase="Yo, Harbor!")) == 0
    out = capsys.readouterr().out
    assert '"wake_phrase": "yo harbor"' in out and '"wake_model": ".maceff/voice/wake/yo_harbor/model.npz"' in out


def test_train_then_status_then_test_report_the_held_out_numbers(tmp_path, monkeypatch, capsys):
    """From an empty home to a measured model: train writes it with its report, status reads it
    back, and test measures it again without retraining."""
    monkeypatch.setattr(wake_cli, "_home", lambda: tmp_path)
    monkeypatch.setattr(wake_train, "openwakeword_embed", lambda: band_embed)
    wake = recorded_set(tmp_path, np.random.default_rng(2))
    assert wake_cli.cmd_train(SimpleNamespace(phrase="yo harbor")) == 0
    trained = capsys.readouterr().out
    assert "of 5 held-out phrases" in trained and "false alarms per hour" in trained
    weights = WakeModel.load(wake.model_path).weights.copy()
    assert wake_cli.cmd_status(SimpleNamespace(phrase="yo harbor")) == 0
    status = capsys.readouterr().out
    assert "phrase: 15 to train on, 5 held out" in status and "model trained 0.0 h ago" in status
    assert wake_cli.cmd_test(SimpleNamespace(phrase="yo harbor")) == 0
    again = WakeModel.load(wake.model_path)
    assert np.array_equal(again.weights, weights) and again.report["trained_on"], "test must not retrain"


def test_status_with_no_phrase_anywhere_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(wake_cli, "_home", lambda: tmp_path)
    monkeypatch.setattr(wake_cli, "_wake_set", lambda phrase: (_ for _ in ()).throw(
        wake_cli.PhraseRefused("no phrase given and the voice section names none")))
    assert wake_cli.cmd_status(SimpleNamespace(phrase=None)) == 1
    assert "no phrase given" in capsys.readouterr().out


def test_the_wake_commands_are_on_the_cli():
    from macf.cli import _build_parser
    parser = _build_parser()
    for words, func in ((["define", "yo tom"], wake_cli.cmd_define), (["record", "phrase"], wake_cli.cmd_record),
                        (["train"], wake_cli.cmd_train), (["test"], wake_cli.cmd_test),
                        (["status"], wake_cli.cmd_status)):
        assert parser.parse_args(["voice", "wake", *words]).func is func


def _no_voice_section(monkeypatch, home):
    """An agent whose declaration has no voice section yet, as before Phase 8 declares one."""
    from macf.pd import core, interface
    monkeypatch.setattr(wake_cli, "_home", lambda: home)
    monkeypatch.setattr(interface, "agent_card", lambda h: "Tester_abc123")
    monkeypatch.setattr(core, "load_declaration", lambda h, card: SimpleNamespace(voice=None))


def test_the_step_define_prints_works_with_no_voice_section(tmp_path, monkeypatch, capsys):
    """Before a voice section names the phrase, the one phrase defined in the home is the one meant, so
    the next step define prints ("voice wake record phrase", no --phrase) works for the agent that ran it."""
    from macf.voice.wake.dataset import WakeSet
    _no_voice_section(monkeypatch, tmp_path)
    WakeSet(tmp_path, "yo tom").define()
    assert wake_cli._wake_set(None).phrase == "yo tom"


def test_with_several_phrases_defined_the_command_asks_which(tmp_path, monkeypatch):
    import pytest
    from macf.voice.wake.dataset import WakeSet
    _no_voice_section(monkeypatch, tmp_path)
    WakeSet(tmp_path, "yo tom").define()
    WakeSet(tmp_path, "hey bravo").define()
    with pytest.raises(wake_cli.PhraseRefused, match="several are defined"):
        wake_cli._wake_set(None)


def test_with_nothing_defined_the_command_still_refuses(tmp_path, monkeypatch):
    import pytest
    _no_voice_section(monkeypatch, tmp_path)
    with pytest.raises(wake_cli.PhraseRefused, match="define one first"):
        wake_cli._wake_set(None)
