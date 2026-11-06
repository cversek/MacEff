"""MIS-0004's flow rows: one agent's trouble stays its own, and nothing is dropped unseen.

- R17 (queue_MUST_be_per_agent): an entry that keeps failing doesn't hold back the
  mail spooled after it for other agents.
- R18 (refusal_MUST_reach_the_sender): a refused submission comes back to its sender
  with the reason, and is audited.
- R20 (broker_MUST_quarantine_repeated_failure): an entry that can't be parsed is set
  aside at once; one that fails unexpectedly is set aside after a declared number of
  tries, with its last error, and reported.

The unexpected failure is planted by making `process_entry` raise for one named
entry, so the test controls exactly which entry fails and how often.
"""
import hashlib
import json

import pytest

pytest.importorskip("cryptography", reason="amail requires the crypto extra")

from conftest import _addressing

from macf.amail import inbound
from macf.amail.broker import Broker, BrokerConfig
from macf.amail.inbound import HANDED_OFF, QUARANTINED, InboundConfig
from macf.amail.models import Message

AUTHORITY = "mx.test.example"
HUMAN = "human@example.org"
DOMAIN = "agents.test"


def _raw(to_agent, body):
    return (f"Authentication-Results: {AUTHORITY}; dmarc=pass header.from=example.org; spf=pass\r\n"
            f"From: Someone <{HUMAN}>\r\nTo: {to_agent}@{DOMAIN}\r\nSubject: flow\r\n\r\n{body}").encode()


def _spool(cfg, name, to_agent, body="hello"):
    """Write one spool entry named *name*; return its .eml path."""
    raw = _raw(to_agent, body)
    eml = cfg.spool_dir / f"{name}.eml"
    eml.write_bytes(raw)
    eml.with_suffix(".json").write_text(json.dumps({
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "observed": {"trusted": False, "envelope_to": f"{to_agent}@{DOMAIN}"},
    }))
    return eml


@pytest.fixture
def cfg(tmp_path):
    """Two agents who both list the human, each with a provisioned box."""
    contacts = tmp_path / "contacts.json"
    contacts.write_text(_addressing({"alpha": [HUMAN], "beta": [HUMAN]}, domain=DOMAIN))
    homes = {}
    for a in ("alpha", "beta"):
        homes[a] = tmp_path / "home" / a
        (homes[a] / "Maildir").mkdir(parents=True)
    c = InboundConfig(
        broker_config=BrokerConfig(domain=DOMAIN, agent_homes=homes, contacts_path=contacts,
                                   audit_path=tmp_path / "audit.jsonl"),
        spool_dir=tmp_path / "spool", quarantine_dir=tmp_path / "quarantine",
        handoff_dir=tmp_path / "handoff", verdict_authority=AUTHORITY)
    c.spool_dir.mkdir()
    for a in ("alpha", "beta"):
        (c.handoff_dir / a).mkdir(mode=0o2770, parents=True)
    return c


@pytest.fixture
def poisoned(cfg, monkeypatch):
    """`process_entry` raises for any entry whose name starts with "poison"."""
    real = inbound.process_entry

    def flaky(c, eml, sidecar):
        if eml.name.startswith("poison"):
            raise RuntimeError("planted: handling fails for this entry")
        return real(c, eml, sidecar)

    monkeypatch.setattr(inbound, "process_entry", flaky)
    return cfg


def _audit(cfg):
    return [json.loads(l) for l in cfg.broker_config.audit_path.read_text().splitlines()]


def test_queues_per_agent(poisoned):
    """alpha's failing entry sorts first, and beta's mail behind it still lands."""
    _spool(poisoned, "poison-0001", "alpha")
    _spool(poisoned, "zz-0002", "beta", body="for beta")
    results = inbound.process_spool(poisoned)
    by_entry = {r["entry"]: r for r in results}
    assert by_entry["poison-0001.eml"]["disposition"] == "failed"
    assert by_entry["zz-0002.eml"]["disposition"] == HANDED_OFF
    assert len(list((poisoned.handoff_dir / "beta").glob("*.eml"))) == 1


def test_quarantine(poisoned):
    """An unexpected failure is retried up to the declared limit, then set aside
    with its last error and audited; a corrupt entry is set aside at once."""
    poison = _spool(poisoned, "poison-0001", "alpha")
    corrupt = _spool(poisoned, "corrupt-0002", "beta")
    corrupt.with_suffix(".json").write_text("{not json")
    first = {r["entry"]: r for r in inbound.process_spool(poisoned)}
    assert first["corrupt-0002.eml"]["disposition"] == QUARANTINED, "unparseable: set aside at once"
    assert first["poison-0001.eml"]["failures"] == 1 and poison.exists()
    second = {r["entry"]: r for r in inbound.process_spool(poisoned)}
    assert second["poison-0001.eml"]["failures"] == 2 and poison.exists()
    third = {r["entry"]: r for r in inbound.process_spool(poisoned)}
    assert third["poison-0001.eml"]["disposition"] == QUARANTINED
    assert not poison.exists()
    reason = (poisoned.quarantine_dir / "poison-0001.reason").read_text()
    assert "failed 3 times" in reason and "planted" in reason
    assert any(r.get("decision") == QUARANTINED and "failed 3 times" in (r.get("reason") or "")
               for r in _audit(poisoned))
    assert not list((poisoned.quarantine_dir / ".failures").glob("*.json")), "the count is cleared"


def test_a_count_that_cannot_be_recorded_still_lets_the_run_go_on(poisoned, monkeypatch):
    """The counting itself can fail; the run it protects must still go on."""
    def broken(*a, **k):
        raise OSError("planted: the failures directory can't be written")
    monkeypatch.setattr(inbound, "_entry_failed", broken)
    _spool(poisoned, "poison-0001", "alpha")
    _spool(poisoned, "zz-0002", "beta")
    by_entry = {r["entry"]: r for r in inbound.process_spool(poisoned)}
    assert "count not recorded" in by_entry["poison-0001.eml"]["reason"]
    assert by_entry["zz-0002.eml"]["disposition"] == HANDED_OFF


def test_a_failure_after_hand_off_does_not_deliver_twice(cfg, monkeypatch):
    """The window the reviewer named: the entry is handed off, then removing it from
    the spool fails. The retry must finish the removal, not hand it off again."""
    import os as _os
    eml = _spool(cfg, "late-0001", "alpha")
    real_unlink = _os.unlink
    calls = {"n": 0}

    def flaky_unlink(path, *a, **k):
        if str(path) == str(eml) and calls["n"] == 0:
            calls["n"] += 1
            raise PermissionError("planted: the spool entry can't be removed yet")
        return real_unlink(path, *a, **k)

    monkeypatch.setattr(inbound.os, "unlink", flaky_unlink)
    first = {r["entry"]: r for r in inbound.process_spool(cfg)}
    assert first["late-0001.eml"]["disposition"] == "failed"
    box = cfg.handoff_dir / "alpha"
    for p in box.glob("*.eml"):          # the recipient ingests between the runs
        p.unlink()
    second = {r["entry"]: r for r in inbound.process_spool(cfg)}
    assert second["late-0001.eml"]["disposition"] == HANDED_OFF
    assert not list(box.glob("*.eml")), "not handed off a second time"
    assert not eml.exists()


def test_a_success_clears_the_entrys_failure_count(cfg, monkeypatch):
    """A record of earlier failures goes once the entry succeeds."""
    eml = _spool(cfg, "once-0001", "alpha")
    real = inbound.process_entry
    calls = {"n": 0}

    def fails_once(c, e, s):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("planted: fails the first time only")
        return real(c, e, s)

    monkeypatch.setattr(inbound, "process_entry", fails_once)
    inbound.process_spool(cfg)
    assert list((cfg.quarantine_dir / ".failures").glob("*.json"))
    inbound.process_spool(cfg)
    assert not eml.exists()
    assert not list((cfg.quarantine_dir / ".failures").glob("*.json"))


def test_an_unwritable_failures_dir_does_not_repeat_a_clean_delivery(cfg):
    """The marker is best effort: with nowhere to write it, a clean delivery still
    completes once and isn't handed off again on the next run."""
    blocked = cfg.quarantine_dir / "blocked"
    blocked.mkdir(parents=True, mode=0o500)
    cfg.failures_dir = blocked / "failures"
    eml = _spool(cfg, "clean-0001", "beta")
    try:
        first = {r["entry"]: r for r in inbound.process_spool(cfg)}
        assert first["clean-0001.eml"]["disposition"] == HANDED_OFF
        assert not eml.exists()
        box = cfg.handoff_dir / "beta"
        assert len(list(box.glob("*.eml"))) == 1
        for p in box.glob("*.eml"):      # the recipient ingests between runs
            p.unlink()
        assert inbound.process_spool(cfg) == [], "nothing is left to hand off again"
    finally:
        blocked.chmod(0o700)


def test_a_failure_count_restarts_when_the_content_changes(poisoned):
    """The count belongs to the entry's content: a rewritten entry starts again."""
    poison = _spool(poisoned, "poison-0001", "alpha", body="one")
    inbound.process_spool(poisoned)
    inbound.process_spool(poisoned)
    _spool(poisoned, "poison-0001", "alpha", body="two")
    again = {r["entry"]: r for r in inbound.process_spool(poisoned)}
    assert again["poison-0001.eml"]["failures"] == 1 and poison.exists()


def test_refusal_reaches_sender(tmp_path):
    """A submission the contact book refuses comes back with its reason, and is audited."""
    contacts = tmp_path / "addressing.yaml"
    contacts.write_text(_addressing({"alpha": [f"beta@{DOMAIN}"], "beta": [f"alpha@{DOMAIN}"]},
                                    domain=DOMAIN))
    handoff = tmp_path / "handoff"
    for a in ("alpha", "beta"):
        (handoff / a).mkdir(mode=0o2770, parents=True)
        (tmp_path / "home" / a).mkdir(parents=True)
    broker = Broker(BrokerConfig(
        domain=DOMAIN, agent_homes={a: tmp_path / "home" / a for a in ("alpha", "beta")},
        contacts_path=contacts, audit_path=tmp_path / "audit.jsonl",
        dispositions_dir=tmp_path / "dispositions", inbound_quarantine=tmp_path / "q",
        inbound_handoff=handoff))
    r = broker.submit("alpha", Message(sender=f"alpha@{DOMAIN}", to=["stranger@elsewhere.test"],
                                       subject="no", body="refused"))
    assert r["ok"] is False
    assert r["refused"] and any("stranger@elsewhere.test" in x for x in r["refused"])
    recs = [json.loads(l) for l in (tmp_path / "audit.jsonl").read_text().splitlines()]
    assert any(x.get("decision") == "refused" for x in recs)
    assert not list((handoff / "beta").glob("*.amsg")), "nothing was delivered"
