"""The two channels' names and identifiers, and the clean break from the old one (MIS-0008 R01 to R03, R54)."""
import json
from pathlib import Path

import macf.channels.marketplace as marketplace
from macf.pd import taint
from macf.utils import input_origin

PLUGINS = Path(marketplace.__file__).parent / "maceff_marketplace" / "plugins"


def test_notification_channel_name_and_id():
    assert marketplace.CHANNEL_PLUGIN == "maceff-notification-channel"
    assert input_origin.NOTIFICATION_CHANNEL_SOURCE == "plugin:maceff-notification-channel:maceff"
    manifest = json.loads((PLUGINS / "maceff-notification-channel" / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "maceff-notification-channel"
    assert "MacEff Notification Channel" in manifest["description"]


def test_voice_input_channel_name_and_id():
    """R02: the plugin, its manifest, its catalog entry and its launch flag all carry the one name."""
    assert marketplace.VOICE_PLUGIN == "maceff-voice-input-channel"
    assert marketplace.VOICE_FLAG == "plugin:maceff-voice-input-channel@maceff"
    manifest = json.loads((PLUGINS / "maceff-voice-input-channel" / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "maceff-voice-input-channel"
    assert "MacEff Voice Input Channel" in manifest["description"]
    catalog = json.loads((PLUGINS.parent / ".claude-plugin" / "marketplace.json").read_text())
    assert "maceff-voice-input-channel" in {p["name"] for p in catalog["plugins"]}


def test_the_classifier_and_the_taint_check_share_one_source():
    assert taint._OWN_CHANNEL is input_origin.NOTIFICATION_CHANNEL_SOURCE, \
        "a rename must not leave the two readers disagreeing"


def test_old_source_refused_by_name(capsys, monkeypatch):
    monkeypatch.setattr(input_origin, "_OLD_SOURCE_RECORDED", [True])   # not this test's subject
    assert input_origin.from_notification_channel("plugin:maceff-notification-channel:maceff") is True
    assert input_origin.from_notification_channel("plugin:maceff-channel:maceff") is False
    err = capsys.readouterr().err
    assert "plugin:maceff-channel:maceff" in err and "plugin:maceff-notification-channel:maceff" in err


def test_refused_old_source_recorded(monkeypatch, capsys):
    recorded = []
    import macf.agent_events_log as log
    monkeypatch.setattr(log, "append_event", lambda name, data: recorded.append((name, data)) or True)
    monkeypatch.setattr(input_origin, "_OLD_SOURCE_RECORDED", [])
    for _ in range(3):
        input_origin.from_notification_channel("plugin:maceff-channel:maceff")
    assert recorded == [("channel_source_refused", {"source": "plugin:maceff-channel:maceff",
                                                    "expected": "plugin:maceff-notification-channel:maceff"})], \
        "recorded once per process, however many notices arrive"
    assert capsys.readouterr().err.count("refused a notice") == 3, "said every time"


def test_a_refused_old_source_shows_in_pd_status(isolated_events_log, capsys):
    """R54, the status half: a refused old-source notice is said where status is read, with the fix."""
    from macf.agent_events_log import append_event
    from macf.pd import cli as pd_cli
    pd_cli._say_refused_sources()
    assert capsys.readouterr().out == ""
    append_event("channel_source_refused", {"source": "plugin:maceff-channel:maceff"})
    pd_cli._say_refused_sources()
    out = capsys.readouterr().out
    assert "notices from the old channel source were refused (recorded 1 time(s)" in out and "agent init --update" in out
