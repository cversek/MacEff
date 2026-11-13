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
