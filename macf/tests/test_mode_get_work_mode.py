"""`mode get` reports the work mode beside the operational one (cversek/MacEff#846)."""
import json

import pytest


@pytest.fixture
def stance(monkeypatch):
    monkeypatch.setattr("macf.cli.get_current_session_id", lambda: "sess")
    monkeypatch.setattr("macf.modes.detect_auto_mode", lambda session_id: (False, "default"))

    def set_work_mode(value):
        monkeypatch.setattr("macf.modes.detection._get_current_work_mode", lambda: value)
    return set_work_mode


def _mode_get(*flags):
    from macf.cli import main
    with pytest.raises(SystemExit) as exited:
        main(["mode", "get", *flags])
    assert exited.value.code == 0


def test_the_text_reading_names_the_work_mode(stance, capsys):
    stance("DISCOVER")
    _mode_get()
    out = capsys.readouterr().out
    assert "Mode: MANUAL_MODE" in out and "Work mode: DISCOVER" in out


def test_an_unset_work_mode_is_reported_as_unset_not_left_out(stance, capsys):
    stance(None)
    _mode_get()
    assert "Work mode: (unset)" in capsys.readouterr().out


def test_the_json_reading_carries_the_work_mode(stance, capsys):
    stance("BUILD")
    _mode_get("--json")
    data = json.loads(capsys.readouterr().out)
    assert data["mode"] == "MANUAL_MODE" and data["work_mode"] == "BUILD"
