"""The zone watch as a fleet daemon's unit (prototype, phase B1): memory from the fleet's own log,
a first start that reads back the dataset's retention, alerts through the outside watch's path,
and the edge checked against the declared addresses, with tokens masked everywhere."""
import json
from datetime import datetime, timedelta, timezone

from macf.fleet.zone_watch import (Config, contact_pass, edge_findings, edge_pass, remember)

NOW = datetime(2026, 11, 8, 5, 0, tzinfo=timezone.utc)
FAKE_PART = "0123456789abcdef"
REAL = f"wrentuba_3c9d1e_{FAKE_PART}@zone.example"


def cfg(**over):
    return Config(**{"zone_id": "z", "zone_domain": "zone.example", "token_file": "/nonexistent",
                     "alert_command": ["true"], "readback_days": 3, **over})


def row(minutes_ago, sender="probe@outside.example", to="nobody@zone.example", msg="m"):
    at = (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"datetime": at, "from": f"Probe <{sender}>", "to": to, "messageId": f"{msg}{minutes_ago}",
            "action": "drop", "status": "dropped", "dmarc": "none", "isSpam": False}


class Harness:
    """The unit's surroundings: the fleet's log as a list, and an alert path that may fail."""

    def __init__(self, rows_by_window=None, push_ok=True):
        self.events, self.pushed, self.fetched = [], [], []
        self.rows_by_window = rows_by_window or (lambda s, e: [])
        self.push_ok = push_ok

    def record(self, event, data):
        self.events.append({"event": event, "data": data})

    def push(self, text):
        self.pushed.append(text)
        return self.push_ok

    def fetch(self, start, end):
        self.fetched.append((start, end))
        return self.rows_by_window(start, end)

    def run(self, config, now=NOW):
        return contact_pass(config, now, events=list(self.events), fetch_rows=self.fetch,
                            record=self.record, push=self.push)


def seeded(h, *rows_):
    """A log that already holds a contact, so the pass is not a first start."""
    for r in rows_:
        h.record("zone_contact", {"at": r["datetime"], "key": f"{r['datetime']}|{r['messageId']}|{r['to']}",
                                  "sender": r["from"].split("<")[1].rstrip(">")})


def test_a_first_start_reads_back_the_retention_with_one_summary_alert():
    rows = [row(60 * 24 * 2, sender="a@x.example"), row(30, sender="b@x.example")]
    h = Harness(lambda s, e: [r for r in rows if s.strftime("%Y-%m-%dT%H:%M:%SZ") <= r["datetime"] <= e.strftime("%Y-%m-%dT%H:%M:%SZ")])
    out = h.run(cfg())
    assert out["readback"] and len(h.fetched) == 3, "one window per day of retention"
    assert out["new"] == 2 and [e["event"] for e in h.events].count("zone_contact") == 2
    assert len(h.pushed) == 1 and "Read back 3 days: 2 attempts from 2 senders" in h.pushed[0]


def test_a_restarted_unit_records_each_attempt_exactly_once():
    """B1's restart criterion: the unit's memory is the fleet's log, so a restart (a new process
    reading the same log) never records an attempt twice."""
    seen_before = row(200, sender="old@x.example")
    h = Harness(lambda s, e: [row(10), row(20)])
    seeded(h, seen_before)
    h.run(cfg())
    first = [e for e in h.events if e["event"] == "zone_contact"]
    h.run(cfg())                                     # the restart: same log, same window
    assert [e for e in h.events if e["event"] == "zone_contact"] == first
    assert len(first) == 3, "the seeded one and the two new ones, once each"


def test_a_new_sender_alerts_once_and_a_known_one_does_not():
    h = Harness(lambda s, e: [row(5, sender="old@x.example", msg="later")])
    seeded(h, row(300, sender="old@x.example"))
    h.run(cfg())
    assert h.pushed == [], "a sender already in the log is not news"
    h.rows_by_window = lambda s, e: [row(4, sender="new@x.example")]
    h.run(cfg())
    assert len(h.pushed) == 1 and "First contact from:\n- " in h.pushed[0] and "new@x.example" in h.pushed[0]


def test_a_failed_alert_is_recorded_as_not_pushed():
    """B1's red criterion: with the alert credential absent the command fails, and the record
    says the alert was not sent, so nobody mistakes it for delivered."""
    h = Harness(lambda s, e: [row(3, sender="new@x.example")], push_ok=False)
    seeded(h, row(300, sender="old@x.example"))
    h.run(cfg())
    alerts = [e["data"] for e in h.events if e["event"] == "zone_contact_alert"]
    assert alerts == [{"new_senders": 1, "last_hour": 1, "burst": False, "sent": False}]


def test_a_burst_alerts():
    h = Harness(lambda s, e: [row(i, sender="old@x.example", msg=f"b{i}") for i in range(1, 13)])
    seeded(h, row(300, sender="old@x.example"))
    h.run(cfg(burst_per_hour=10))
    assert len(h.pushed) == 1 and "Burst: 12 attempts" in h.pushed[0]


def test_tokens_are_masked_in_every_record():
    h = Harness(lambda s, e: [row(2, to=REAL)])
    seeded(h, row(300))
    h.run(cfg())
    assert FAKE_PART not in json.dumps(h.events) and FAKE_PART not in json.dumps(h.pushed)


def doc(card, token=FAKE_PART, revoked=()):
    return {"zone": "zone.example", "domain": "aero.local", "revoked_zone_tokens": list(revoked),
            "agents": {"wren": {"card": card, "zone_token": token}}}


def rule(addr, enabled=True):
    return {"enabled": enabled, "matchers": [{"type": "literal", "field": "to", "value": addr}]}


DROP = {"enabled": True, "actions": [{"type": "drop"}]}


def test_the_edge_matches_new_form_cards_and_flags_each_difference():
    c = cfg(expected_routes=["dmarc@zone.example"])
    assert edge_findings(c, [("aero.local", doc("WrenTuba_3c9d1e"))], [rule(REAL), rule("dmarc@zone.example")], DROP) == []
    old_part = "fedcba9876543210"
    stale = f"wrentuba_3c9d1e_{old_part}@zone.example"
    found = edge_findings(c, [("aero.local", doc("WrenTuba_3c9d1e", revoked=[old_part]))],
                          [rule(REAL), rule(stale), rule("stray@zone.example")], {"enabled": False})
    assert found == sorted([f"REVOKED token still routed: wrentuba_3c9d1e_fedc…@zone.example",
                            "routed at the edge, declared by no system: stray@zone.example",
                            "catch-all is not an enabled drop: probes to unknown addresses are not logged"])
    assert old_part not in json.dumps(found)


def test_a_system_not_yet_cut_over_is_read_as_history_not_refused():
    """R166: an addressing file that still says Name@shortid is read in the current form, so the
    watch over several systems doesn't fail on the one that hasn't moved (seen live, Nov 8)."""
    c = cfg(expected_routes=["dmarc@zone.example"])
    old_form = "WrenTuba_3c9d1e".replace("_", "@")       # the fixture card, as history spells it
    assert edge_findings(c, [("aero.local", doc(old_form))], [rule(REAL), rule("dmarc@zone.example")], DROP) == []


def test_the_edge_is_recorded_and_alerted_only_when_it_changes():
    h = Harness()
    assert edge_pass(cfg(), ["x"], events=h.events, record=h.record, push=h.push) == ["x"]
    edge_pass(cfg(), ["x"], events=list(h.events), record=h.record, push=h.push)
    assert [e["event"] for e in h.events] == ["zone_edge_check"] and len(h.pushed) == 1
    edge_pass(cfg(), [], events=list(h.events), record=h.record, push=h.push)
    assert len(h.pushed) == 2 and "agree again" in h.pushed[1]


def test_memory_is_only_the_log():
    m = remember([{"event": "zone_contact", "data": {"at": "2026-11-08T04:00:00Z", "key": "k", "sender": "s"}},
                  {"event": "zone_edge_check", "data": {"findings": ["f"]}}], NOW, 48)
    assert (m.seen, m.senders, m.edge, m.empty) == ({"k": "2026-11-08T04:00:00Z"}, {"s"}, ["f"], False)
