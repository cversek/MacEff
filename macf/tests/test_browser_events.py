"""MIS-0009 6.5: one event per command, carrying no page content, and nothing written under the agent's home."""
import pytest

from macf.browser import events


@pytest.fixture
def captured(monkeypatch):
    seen = []
    monkeypatch.setattr(events, "_append", lambda name, data: seen.append((name, data)) or True)
    return seen


def test_one_event_per_command(captured):
    events.record("click", "allowed", backend="cdp", plugin="outlook", host="mail.example.com",
                  changed=True, operator_said="submit it")
    assert len(captured) == 1
    name, data = captured[0]
    assert name == "browser_act"
    assert data["verb"] == "click" and data["decision"] == "allowed" and data["host"] == "mail.example.com"
    assert data["operator_said"] == "submit it"


def test_event_carries_no_page_content(captured):
    for key in ("text", "body", "value", "html", "subject", "title_text", "content"):
        with pytest.raises(ValueError):
            events.record("read", "allowed", backend="cdp", host="mail.example.com", **{key: "secret"})
    assert captured == []


def test_no_content_written_under_agent_home(tmp_path, monkeypatch, captured):
    """Recording an act writes nothing to the agent's home: the event goes to the log through _append only."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MACF_AGENT_HOME", str(home))
    events.record("read", "allowed", backend="cdp", host="mail.example.com", count=12)
    assert list(home.rglob("*")) == []


def test_log_failure_is_said(monkeypatch, capsys):
    monkeypatch.setattr(events, "_append", lambda name, data: False)
    events.record("tabs", "allowed", backend="cdp", host="mail.example.com")
    assert "MACF" in capsys.readouterr().err
