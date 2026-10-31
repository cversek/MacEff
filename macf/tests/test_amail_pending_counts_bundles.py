"""MIS-0004 R32: the broker's pending count includes agent bundles, and says how long the oldest
has waited.

A container experiment (2026-10-30) held a recipient's receiver with two agent bundles waiting,
and status read `pending_pickup: 0`, because only internet mail (*.eml) was counted.
"""
import os
import time

from macf.amail.broker import Broker, BrokerConfig


def _broker(tmp_path):
    handoff = tmp_path / "handoff"
    (handoff / "alpha").mkdir(parents=True)
    cfg = BrokerConfig(domain="proto.local", agent_homes={"alpha": tmp_path / "alpha"},
                       inbound_handoff=handoff)
    return Broker(cfg), handoff / "alpha"


def _waiting(box, name, age_s):
    for ext in (name.rsplit(".", 1)[1], "json"):
        p = box / f"{name.rsplit('.', 1)[0]}.{ext}"
        p.write_text("x")
        t = time.time() - age_s
        os.utime(p, (t, t))


def test_agent_bundles_and_internet_mail_both_count_and_the_oldest_age_is_given(tmp_path):
    broker, box = _broker(tmp_path)
    assert broker.status_counts("alpha")["pending_pickup"] == 0
    assert broker.status_counts("alpha")["oldest_pending_s"] is None
    _waiting(box, "1-msg-a.amsg", 600)
    _waiting(box, "2-msg-b.amsg", 30)
    _waiting(box, "3-inet.eml", 120)
    counts = broker.status_counts("alpha")
    assert counts["pending_pickup"] == 3          # sidecars are not messages
    assert 595 <= counts["oldest_pending_s"] <= 605


def test_a_refused_entry_set_aside_by_the_recipient_is_not_pending(tmp_path):
    broker, box = _broker(tmp_path)
    _waiting(box, "1-msg-a.amsg", 10)
    os.rename(box / "1-msg-a.amsg", box / "1-msg-a.amsg.refused")
    assert broker.status_counts("alpha")["pending_pickup"] == 0
