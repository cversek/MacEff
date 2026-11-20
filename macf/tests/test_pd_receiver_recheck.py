"""A receiver that was refused access to its pickup box looks again on a slow interval, so a fixed group
or grant takes effect without a daemon restart, and the clearing is recorded (#872)."""
from types import SimpleNamespace

from macf.pd import receiver as receiver_mod
from macf.pd.receiver import EVENT_REFUSAL_CLEARED, RECHECK_S, Receiver


def _receiver(tmp_path, monkeypatch, answers):
    """A receiver whose access answers come from `answers` (a refusal text, or None for fine)."""
    box = tmp_path / "box"
    box.mkdir()
    events, notices, ingests = [], [], []
    r = Receiver("a_abc123", tmp_path / "home", box, "agent", tmp_path / "contacts",
                 lambda name, data: events.append((name, data)), lambda src, key: notices.append(key))
    seen = []

    def access():
        seen.append(1)
        return answers.pop(0) if len(answers) > 1 else answers[0]

    monkeypatch.setattr(r, "_access", access)
    monkeypatch.setattr(r, "ingest", lambda: ingests.append(1))
    return SimpleNamespace(r=r, events=events, notices=notices, ingests=ingests, seen=seen)


def test_a_refused_box_is_looked_at_again_after_the_interval(tmp_path, monkeypatch):
    h = _receiver(tmp_path, monkeypatch, ["the box can't be listed", None])
    h.r.tick(0.0)
    assert h.r.refused and h.ingests == [] and len(h.seen) == 1
    h.r.tick(RECHECK_S - 5)                       # too soon: no second look, nothing ingested
    assert len(h.seen) == 1 and h.ingests == []
    h.r.tick(RECHECK_S + 5)                       # the interval has passed and the grant is fixed
    assert h.r.refused is None and len(h.ingests) == 1


def test_the_clearing_is_recorded_once(tmp_path, monkeypatch, capsys):
    h = _receiver(tmp_path, monkeypatch, ["denied", None])
    h.r.tick(0.0)
    h.r.tick(RECHECK_S + 5)
    h.r.tick(RECHECK_S + 10)
    cleared = [e for e in h.events if e[0] == EVENT_REFUSAL_CLEARED]
    assert len(cleared) == 1 and cleared[0][1]["agent"] == "a_abc123"
    assert "can ingest agent's mail again" in capsys.readouterr().err


def test_a_box_that_stays_refused_is_re_checked_not_re_announced(tmp_path, monkeypatch, capsys):
    h = _receiver(tmp_path, monkeypatch, ["denied"])
    h.r.tick(0.0)
    first = capsys.readouterr().err
    h.r.tick(RECHECK_S + 5)
    h.r.tick(2 * RECHECK_S + 10)
    assert h.r.refused == "denied" and len(h.seen) == 3 and h.ingests == []
    assert "denied" in first and capsys.readouterr().err == ""    # said once, not on every look
    assert len(h.notices) == 1


def test_the_interval_is_minutes_not_passes():
    assert RECHECK_S >= 60 and RECHECK_S > receiver_mod.INGEST_S * 10
