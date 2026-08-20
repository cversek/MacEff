"""The pre-send OPSEC scrub: text-level entry point and the six categories.

BOTH POLARITIES THROUGHOUT. A corpus made only of leaks scores perfectly
against a gate that refuses everything, so every planted case has a clean
control beside it. That is the amail spec O5e.3
"the-gate-must-pass-a-clean-control", and it is the difference between a gate
and a wall.

NO REAL ENVIRONMENT VALUES APPEAR HERE. Every test passes an explicit `env`,
because a test that used this host's real name to check the hostname rule would
be committing the disclosure the rule exists to prevent -- and it would leak it
into a public repo, where the rule cannot reach.
"""
import pytest

from macf import opsec

ENV = {
    "hostname": "buildbox42.internal",
    "username": "deployer",
    "agent_home": "/home/deployer",
    "moniker": "TheQuartermaster",
}


def scan(text, **kw):
    return opsec.scan_text(text, env=ENV, **kw)


# ---- the entry point that did not exist ------------------------------------

def test_the_gate_accepts_a_composed_message_not_only_a_diff():
    """amail spec O5e.1 "the-gate-must-accept-a-composed-message". Before this
    the matching logic existed only as a STRING written into a git hook: it
    could not be imported, called, or pointed at a message at all."""
    from macf.amail.models import Message
    m = Message(sender="a@x.test", to=["b@y.test"], subject="s", body="clean")
    assert opsec.scan_message(m, env=ENV).clean is True


@pytest.mark.parametrize("planted,label", [
    ("please ssh to buildbox42.internal tonight", "hostname"),
    ("it broke on buildbox42 again", "hostname"),
    ("run it as deployer", "local username"),
    ("logs are in /home/deployer/agent/logs", "agent home path"),
    ("see /Users/someone.else/notes.md", "filesystem path"),
    ("signed off by TheQuartermaster", "agent moniker"),
    ("from TheHarbourMaster@a1b2c3 earlier", "agent uuid"),
    ("api_key = 8f3a9c2b7e1d4a6f0b5c", "credential assignment"),
    ("-----BEGIN OPENSSH PRIVATE KEY-----", "private key material"),
    ("AKIAIOSFODNN7EXAMPLE", "aws access key id"),
    ("ghp_abcdefghijklmnopqrstuvwxyz0123456789", "github token"),
    ("id 3f2504e0-4f89-11d3-9a0c-0305e82c3301", "uuid"),
])
def test_planted_material_is_caught(planted, label):
    """THE SIX CATEGORIES the amail spec O5e.4 recorded as uncovered, plus the
    secret shapes. Each asserts its OWN label -- a test that only checked
    `clean is False` would pass on a gate that matched for the wrong reason."""
    r = scan(planted)
    assert r.clean is False
    assert label in [f.label for f in r.findings], \
        f"caught, but as {[f.label for f in r.findings]} rather than {label}"


@pytest.mark.parametrize("innocent", [
    "the deploy finished and the tests are green",
    "see the roadmap for the transport decision",
    "meeting at 14:00 to discuss the schema",
    "dep",                                  # too short to be the username
    "relative/path/to/file.txt",            # not absolute: not a disclosure
    "the box42 build",                      # substring, not the hostname
])
def test_a_clean_control_passes(innocent):
    """A gate that refuses everything scores perfectly against a corpus made
    only of leaks. These are the messages that MUST get through."""
    r = scan(innocent)
    assert r.clean is True, f"false positive: {r.reason()}"


def test_short_values_are_dropped_rather_than_matched():
    """A three-letter username makes every scan a wall of false positives, and
    a gate whose output is noise is muted within a week -- which leaves the
    real leak unreviewed."""
    pats = opsec.environment_patterns({"hostname": "b", "username": "ci",
                                       "moniker": "Q"})
    labels = [lab for _, lab in pats]
    assert "hostname" not in labels and "local username" not in labels
    assert "agent moniker" not in labels
    # ...but the always-on categories survive, or "drop the short ones" would
    # have quietly disabled the whole rule set.
    assert "filesystem path" in labels and "agent uuid" in labels


# ---- fail closed on the SCAN, not on the message ---------------------------

def test_undecodable_input_is_unscanned_never_clean():
    """amail spec O5e.6 "fail-closed-applies-to-the-scan-not-the-message".
    "Nothing found" and "nothing looked at" are different facts and only one
    of them is safe to treat as clean."""
    r = scan(b"\xff\xfe\x00 not utf-8")
    assert r.clean is False
    assert r.unscanned == ["body"]
    assert r.findings == [], "it was not scanned, so it cannot have findings"


def test_non_text_is_not_stringified_into_a_false_pass():
    """`str(b"...")` scans the REPR: a scan that looks like it ran, reports
    clean, and examined a string the sender never wrote. That is the dead
    instrument this gate is most at risk of becoming."""
    r = opsec.scan_text(object(), env=ENV)
    assert r.clean is False and r.unscanned == ["body"]


def test_none_is_unscanned_not_clean():
    assert opsec.scan_text(None, env=ENV).clean is False


# ---- the enumerated surface ------------------------------------------------

def test_a_leak_in_the_subject_is_caught():
    """amail spec O5e.5 "the-gate's-scope-is-enumerated". A gate reading only
    the body passes a leak in a subject line and still satisfies a rule that
    says "scan the message"."""
    from macf.amail.models import Message
    m = Message(sender="a@x.test", to=["b@y.test"],
                subject="notes from buildbox42", body="nothing here")
    r = opsec.scan_message(m, env=ENV)
    assert r.clean is False
    assert [f.part for f in r.findings] == ["header:subject"]


def test_a_leak_in_an_attachment_filename_is_caught():
    from macf.amail.models import Message
    m = Message(sender="a@x.test", to=["b@y.test"], subject="s", body="b")
    r = opsec.scan_message(m, attachments={"deployer-keys.txt": {"size": 12}},
                           env=ENV)
    assert r.clean is False
    assert any(f.part.startswith("attachment:name:") for f in r.findings)


def test_unreadable_attachment_metadata_is_unscanned_not_clean():
    from macf.amail.models import Message
    m = Message(sender="a@x.test", to=["b@y.test"], subject="s", body="b")
    r = opsec.scan_message(m, attachments={"blob.bin": object()}, env=ENV)
    assert r.clean is False
    assert any(u.startswith("attachment:meta:") for u in r.unscanned)


# ---- the finding must not become the leak ----------------------------------

def test_a_finding_carries_no_matched_text():
    """A finding travels into logs, refusal messages and operator alerts -- all
    outward-facing surfaces. A gate that quotes the secret it caught has
    relocated the disclosure into the record of having prevented it.

    THIS PROPERTY IS STRUCTURAL, AND THE MUTATION SWEEP CANNOT VERIFY IT.
    Recorded here rather than left as an unexplained green: the matched text
    never enters the Finding at all -- `scan_text` passes only the span -- so
    no single-line change reintroduces the leak, and every mutant attempting it
    is unfaithful (it plants a constant, and the test rightly ignores a
    constant that is not the secret).

    So the test asserts the SHAPE as well as the behaviour. The shape assertion
    is the one with teeth: it fails the moment someone widens the model to
    carry the text, which is the only way this defect can actually return."""
    secret = "buildbox42.internal"
    r = scan(f"host is {secret}")

    # Behavioural: nothing rendered anywhere quotes it.
    blob = repr(r.findings) + r.reason() + repr(r.as_dict())
    assert secret not in blob
    assert "buildbox42" not in blob
    # ...while still saying enough to act on. A redaction that also removed the
    # category would leave a refusal nobody can act on, which is its own defect.
    assert "hostname" in r.reason()

    # Structural: the text has nowhere to live. This is what actually holds the
    # property, and it is asserted so a future widening trips a test rather
    # than a review.
    assert "text" not in opsec.Finding.__slots__
    assert "matched" not in opsec.Finding.__slots__
    assert set(r.findings[0].as_dict()) == {"part", "label", "start", "end", "length"}


# ---- the PATH test ---------------------------------------------------------
# The corpus above certifies the SCANNER. Only this certifies the GATE. They
# are different claims, and the amail spec O5e.1 is about the second: a scrub
# that exists, passes every corpus test, and that no submission path calls is
# the reader-with-no-writer defect wearing a control's clothing.

import json

pytest.importorskip("cryptography", reason="amail requires the crypto extra")


def _gated_broker(tmp_path, **cfg_kw):
    from macf.amail.broker import Broker, BrokerConfig
    peer_home = tmp_path / "peer"
    (peer_home / "Maildir").mkdir(parents=True)
    contacts = tmp_path / "contacts.json"
    contacts.write_text(json.dumps({"alpha": ["peer@agents.test"]}))
    return Broker(BrokerConfig(
        domain="agents.test", contacts_path=contacts,
        dispositions_dir=tmp_path / "disp",
        inbound_handoff=tmp_path / "handoff",
        agent_homes={"alpha": tmp_path / "alpha", "peer": peer_home},
        opsec_scan=lambda m: opsec.scan_message(m, env=ENV),
        **cfg_kw))


def _msg(body="ordinary text", subject="s"):
    from macf.amail.models import Message
    return Message(sender="alpha@agents.test", to=["peer@agents.test"],
                   subject=subject, body=body)


def test_planted_material_is_refused_through_the_real_submission_path(tmp_path):
    """The gate is ON the path, demonstrated by driving the path."""
    b = _gated_broker(tmp_path)
    result = b.submit("alpha", _msg(body="deploy notes from buildbox42.internal"))
    assert result["ok"] is False
    assert any("pre-send gate" in r for r in result["refused"])


def test_a_clean_message_still_gets_through_the_same_path(tmp_path):
    """The paired green. Without it, the refusal above is equally consistent
    with a gate that refuses everything."""
    b = _gated_broker(tmp_path)
    assert b.submit("alpha", _msg())["ok"] is True


def test_a_gate_refusal_is_a_terminal_fate_and_is_recorded(tmp_path):
    """`gate-refused` is in the closed terminal set (amail spec O5d.7), so a
    scrubbed message is accounted for rather than vanishing from the ledger."""
    from macf.amail.client import sent_disposition, derive_message_state
    b = _gated_broker(tmp_path)
    result = b.submit("alpha", _msg(subject="ping from buildbox42"))
    rec = sent_disposition(tmp_path / "disp", result["message_id"])
    assert rec is not None
    assert derive_message_state(rec) == "gate-refused"


def test_the_refusal_message_does_not_quote_the_secret(tmp_path):
    """The refusal travels to the sender and into the audit log. If it carried
    the matched text, the gate would publish what it caught."""
    b = _gated_broker(tmp_path)
    result = b.submit("alpha", _msg(body="host buildbox42.internal down"))
    assert "buildbox42" not in json.dumps(result)


def test_a_scrub_that_raises_refuses_rather_than_passing(tmp_path, capsys):
    """A gate that fails open is not a gate, and an exception is where the pull
    to continue is strongest: everything else about the send worked."""
    def exploding(_m):
        raise RuntimeError("scanner is broken")
    b = _gated_broker(tmp_path)
    b.config.opsec_scan = exploding
    result = b.submit("alpha", _msg())
    assert result["ok"] is False
    assert "scrub failed to run" in " ".join(result["refused"])
    assert "refusing" in capsys.readouterr().err


def test_an_absent_gate_is_announced_on_every_send(tmp_path, capsys):
    """A deployment with no scrub is a legitimate choice for a closed fleet and
    an alarming one anywhere else, and the only thing separating them is
    whether anyone knows. Silence would make an unconfigured gate look exactly
    like a passing one."""
    b = _gated_broker(tmp_path)
    b.config.opsec_scan = None
    assert b.submit("alpha", _msg())["ok"] is True
    assert "UNSCANNED" in capsys.readouterr().err


def test_an_unscannable_part_refuses_when_the_deployment_says_so(tmp_path):
    """amail spec O5e.6: the deployment decides, and BOTH settings are
    exercised -- a knob with one tested position is a constant."""
    b = _gated_broker(tmp_path)
    b.config.opsec_scan = lambda m: opsec.scan_message(
        m, attachments={"blob.bin": object()}, env=ENV)

    b.config.refuse_unscanned = True
    assert b.submit("alpha", _msg())["ok"] is False

    b.config.refuse_unscanned = False
    assert b.submit("alpha", _msg())["ok"] is True


# ---- the SCOPE test --------------------------------------------------------

def test_the_gate_is_scoped_by_path_not_by_authorship(tmp_path):
    """amail spec O5e.0a "the-scrub-is-scoped-to-the-act-of-emission".

    The round-2 finding was that scoping the outbound controls by AUTHORSHIP
    let broker-originated notices out from under all of them at once. So the
    scrub must refuse a message the BROKER composed exactly as it refuses an
    agent's -- the gate protects a credential and a reputation, and neither
    cares who typed the message."""
    from macf.amail.models import Message
    b = _gated_broker(tmp_path)
    broker_originated = Message(
        sender="postmaster@agents.test", to=["stranger@example.org"],
        subject="Delivery Status Notification",
        body="your message to buildbox42.internal was not delivered")
    assert b._scrub(broker_originated) is not None, \
        "a broker-composed message must face the same gate as an agent's"
    clean = Message(sender="postmaster@agents.test", to=["stranger@example.org"],
                    subject="Delivery Status Notification",
                    body="your message was not delivered")
    assert b._scrub(clean) is None


# ---- the deployment actually carries it ------------------------------------
# Found while wiring this phase: `to_broker_config` silently DROPPED
# dispositions_dir, so the whole of the previous phase was inert in any real
# deployment while every unit test stayed green. A field declared on disk and
# dropped on the way to the broker is worse than an absent one -- the operator
# writes it, the config validates, the broker starts, and it does nothing.

def test_every_declared_field_reaches_the_broker(tmp_path):
    """The generic guard, so the next dropped field fails a test instead of
    shipping. Compares the on-disk contract against the in-memory shape by
    NAME rather than checking the fields someone remembered to list."""
    from macf.amail.deploy_config import BrokerDeployConfig
    from macf.amail.broker import BrokerConfig
    import dataclasses

    declared = set(BrokerDeployConfig.model_fields)
    carried = {f.name for f in dataclasses.fields(BrokerConfig)}

    # Deliberately TRANSFORMED rather than copied through. Each entry names
    # what it becomes, and each is covered by a behavioural test below -- an
    # exemption list that only needs a NAME added is a guard that whoever trips
    # it can neuter, which would make this check worse than absent.
    TRANSFORMED = {
        "agents": "-> agent_homes + agent_uids",
        "rate_limit_dir": "-> rate_limiter (RateLimiter state dir)",
        "rate_limit_per_agent": "-> rate_limiter (per-agent RateLimit)",
        "rate_limit_broker": "-> rate_limiter (broker-principal RateLimit)",
        "rate_limit_window_seconds": "-> rate_limiter (window on each RateLimit)",
        "transport_endpoint": "-> transport (HttpTransport endpoint)",
        "transport_timeout": "-> transport (HttpTransport timeout)",
    }
    missing = declared - carried - set(TRANSFORMED)
    assert not missing, (
        f"declared in the deployment file and absent from BrokerConfig: "
        f"{sorted(missing)} -- an operator could set these and nothing would read them")


def test_a_deployment_carries_the_disposition_store_and_the_gate(tmp_path):
    """The specific case, because the generic guard above compares NAMES and
    would pass on a field that is carried as a constant."""
    from macf.amail.deploy_config import BrokerDeployConfig
    cfg = BrokerDeployConfig(
        domain="agents.test",
        agents={"alpha": {"home": tmp_path / "alpha", "uid": 1001}},
        dispositions_dir=tmp_path / "disp",
    ).to_broker_config()
    assert cfg.dispositions_dir == tmp_path / "disp"
    assert cfg.opsec_scan is not None, "the gate must be ON by default"
    assert cfg.refuse_unscanned is True


def test_the_gate_can_be_turned_off_deliberately(tmp_path):
    """The paired negative: a default that cannot be changed is not a default,
    and a knob with one tested position is a constant."""
    from macf.amail.deploy_config import BrokerDeployConfig
    cfg = BrokerDeployConfig(
        domain="agents.test",
        agents={"alpha": {"home": tmp_path / "alpha", "uid": 1001}},
        opsec_scan=False,
    ).to_broker_config()
    assert cfg.opsec_scan is None


# ------------------------------- addressing is not authorship (measured live)
#
# The first real send from a live deployment was refused by this gate on its
# own From header: agent addressing of the form <agent>@<container>.<domain>
# tripped a hard pattern twice, in the local part and in the domain, so NO
# message that deployment could compose could pass. A gate that refuses 100%
# of legitimate traffic is misaimed, and the only pressure it creates is to
# switch it off.
#
# The correction is on the AUTHORSHIP axis, not the header/body axis, and the
# second test below is the one that keeps it honest.


def _framework_addressed(subject="a plain subject", body="a plain body"):
    """A message whose ADDRESSING carries the framework name, as a real
    deployment's does by construction, with agent-authored text clean."""
    from macf.amail.models import Message
    # The address trips a HARD pattern in both the local part and the domain,
    # which is the structural property a real deployment's addressing has. The
    # particular pattern is irrelevant -- a synthetic one is used here because
    # writing a real account name into a public test is the disclosure this
    # module exists to prevent, and the gate caught exactly that on the first
    # attempt at this test.
    return Message(sender="MISSION@DETOUR.example.dev",
                   to=["someone@example.org"], subject=subject, body=body)


def test_the_senders_own_address_is_not_a_leak():
    """KNOWN-ANSWER GREEN. The return path is not private context appearing
    where it does not belong -- the recipient holds it by construction."""
    r = opsec.scan_message(_framework_addressed())
    assert not r.findings, f"clean message refused on: {r.findings}"


def test_the_subject_is_still_scanned():
    """THE PROPERTY THAT MUST SURVIVE THE FIX (amail spec O5e.5
    "the-gate's-scope-is-enumerated").

    Exempting headers WHOLESALE would satisfy the request that produced this
    change and reopen the exact attack that produced O5e.5. The subject is a
    header AND it is the agent's own text; the axis is who wrote it.
    """
    r = opsec.scan_message(_framework_addressed(subject="re: MISSION planning"))
    assert r.findings, "a leak planted in the subject was not caught"
    assert any(f.part == "header:subject" for f in r.findings)


def test_the_body_is_still_scanned():
    r = opsec.scan_message(_framework_addressed(body="see EXPERIMENT 008"))
    assert any(f.part == "body" for f in r.findings)


def test_full_surface_remains_available_for_outward_renderings():
    # THIS TEST IS ALSO THE SENSITIVITY CONTROL FOR THE THREE ABOVE. If the
    # fixture's addressing tripped nothing, "the clean message passes" would
    # pass on any implementation, exemption or not -- a dead control shaped
    # exactly like a live one. It earned its keep immediately: the first
    # rewrite of the fixture was inert and this assertion is what said so.
    """The capability is defaulted off, not deleted. An outward RENDERING of a
    message (an operator listing, a published directory entry) is exactly where
    the addresses DO leak -- amail spec O5e.0a/O5e.0b -- and that caller opts in.
    """
    r = opsec.scan_message(_framework_addressed(), include_addressing=True)
    assert any(f.part == "header:from" for f in r.findings)
