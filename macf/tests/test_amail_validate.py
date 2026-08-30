"""`inbound validate` — check the config the deployment obeys, before it obeys it.

Validating the INSTALLED file tells you what the broker is already enforcing;
by then a bad edit has been live since it was saved. The candidate path is the
whole point, so most of these tests are about a file that is not installed.
"""
import json
from types import SimpleNamespace

import pytest

from macf.amail.daemons import inbound as daemon


@pytest.fixture
def cfg(tmp_path):
    installed = tmp_path / "addressing.yaml"
    installed.write_text(
        "agents:\n"
        "  thom:\n"
        "    address: thom@example.test\n"
        "    contacts:\n"
        "      - address: peer@example.test\n"
        "        direction: both\n"
    )
    return SimpleNamespace(broker_config=SimpleNamespace(
        domain="example.test",
        contacts_path=installed,
        agent_homes={"thom": tmp_path / "home"},
    ))


def _run(capsys, cfg, candidate=None):
    rc = daemon.validate(cfg, candidate)
    return rc, json.loads(capsys.readouterr().out)


class TestItValidatesWhatIsInstalled:
    def test_a_good_config_passes(self, cfg, capsys):
        rc, out = _run(capsys, cfg)
        assert rc == 0 and out["valid"] is True

    def test_a_malformed_contacts_file_fails_without_raising(self, cfg, capsys, tmp_path):
        """The command must REPORT the malformation, not die of it — an
        operator running a validator on a broken file is the expected case,
        not the exceptional one."""
        cfg.broker_config.contacts_path.write_text("{not: [valid")
        rc, out = _run(capsys, cfg)
        assert rc == 1 and out["valid"] is False
        assert any(c["check"] == "contacts_parse" and not c["ok"]
                   for c in out["checks"])

    def test_an_absent_contacts_path_is_a_failure_not_an_empty_pass(self, cfg, capsys):
        """No policy is not a permissive policy. The broker refuses every send
        with no contact list, so a validator reporting green here would be
        describing a deployment that cannot send."""
        cfg.broker_config.contacts_path = None
        rc, out = _run(capsys, cfg)
        assert rc == 1 and out["valid"] is False


class TestTheCandidateIsThePoint:
    def test_a_candidate_is_validated_instead_of_the_installed_file(
            self, cfg, capsys, tmp_path):
        cand = tmp_path / "candidate.yaml"
        cand.write_text("{not: [valid")
        rc, out = _run(capsys, cfg, candidate=str(cand))
        assert rc == 1 and out["candidate"] is True
        assert out["contacts_path"] == str(cand)

    def test_a_broken_installed_file_does_not_fail_a_good_candidate(
            self, cfg, capsys, tmp_path):
        """THE WORKFLOW THIS EXISTS FOR: the live file is broken and the
        operator is checking the fix before installing it."""
        cfg.broker_config.contacts_path.write_text("{broken")
        cand = tmp_path / "fixed.yaml"
        cand.write_text(
            "agents:\n"
            "  thom:\n"
            "    address: thom@example.test\n"
            "    contacts:\n"
            "      - address: peer@example.test\n"
            "        direction: outbound\n"
        )
        rc, out = _run(capsys, cfg, candidate=str(cand))
        assert rc == 0 and out["valid"] is True


class TestTwoPolicyStoresMustAgree:
    def test_a_contact_naming_an_undefined_agent_fails(self, cfg, capsys):
        """Contacts and the roster are BOTH operator-authored, so disagreement
        is a configuration error — declare, compare, refuse. (Contrast a policy
        store against a STATE store, where disagreement is the signal.)"""
        cfg.broker_config.contacts_path.write_text(
            "agents:\n"
            "  ghost:\n"
            "    address: ghost@example.test\n"
            "    contacts:\n"
            "      - address: peer@example.test\n"
            "        direction: both\n"
        )
        rc, out = _run(capsys, cfg)
        assert rc == 1
        row = next(c for c in out["checks"]
                   if c["check"] == "contacts_roster_agreement")
        assert not row["ok"] and "ghost" in row["detail"]

    def test_an_empty_roster_reports_absence_not_a_pass(self, cfg, capsys):
        """Nothing to compare against is not the same as agreement, and the
        detail has to say so or a green line implies a check that never ran."""
        cfg.broker_config.agent_homes = {}
        rc, out = _run(capsys, cfg)
        row = next(c for c in out["checks"]
                   if c["check"] == "contacts_roster_agreement")
        assert "NOT a pass, an absence" in row["detail"]


class TestRevocationsAreSurfaced:
    def test_a_withdrawn_contact_is_reported_and_is_not_a_fault(self, cfg, capsys):
        """`neither` is a revocation RECORD. It must be visible when reading a
        config back, and must not be mistaken for a broken entry."""
        cfg.broker_config.contacts_path.write_text(
            "agents:\n"
            "  thom:\n"
            "    address: thom@example.test\n"
            "    contacts:\n"
            "      - address: gone@example.test\n"
            "        direction: neither\n"
        )
        rc, out = _run(capsys, cfg)
        assert rc == 0
        row = next(c for c in out["checks"] if c["check"] == "contacts_revocations")
        assert row["ok"] and "thom/gone@example.test" in row["detail"]


class TestItTouchesNothing:
    def test_validation_does_not_modify_the_file_it_reads(self, cfg, capsys):
        before = cfg.broker_config.contacts_path.read_bytes()
        mtime = cfg.broker_config.contacts_path.stat().st_mtime_ns
        _run(capsys, cfg)
        assert cfg.broker_config.contacts_path.read_bytes() == before
        assert cfg.broker_config.contacts_path.stat().st_mtime_ns == mtime
