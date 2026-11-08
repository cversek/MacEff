"""MIS-0004 R41: each MacEff agent signs every message, with a key only its own account can read.

The declare step (MIS-0004 section 12.4): an agent with a key signs; an agent
declared to sign refuses to send without one; any other agent sends unsigned and
is told. Nothing here changes how a receiver classifies mail.
"""
import os
import stat
import subprocess

import pytest

pytest.importorskip("cryptography")

from macf.amail import (  # noqa: E402
    Message, SigningError, generate_keypair, key_custody, load_private_key,
    sign_for_submission, verify,
)


def _msg():
    return Message(sender="alpha@test.example", to=["beta@test.example"],
                   subject="s", body="the signed text")


def test_agent_signs_every_message(tmp_path):
    """MIS-0004 R41 (agent_MUST_sign_its_messages): with a key, the submission is signed."""
    key = tmp_path / "keys" / "signing.pem"
    public = generate_keypair(key)
    m = _msg()
    signature = sign_for_submission(m, key, required=True)
    assert signature and verify(m, signature, [public]) is True


def test_declared_signer_without_a_key_refuses_to_send(tmp_path):
    with pytest.raises(SigningError, match="declared to sign"):
        sign_for_submission(_msg(), tmp_path / "keys" / "absent.pem", required=True)


def test_undeclared_agent_without_a_key_sends_unsigned_and_is_told(tmp_path, capsys):
    assert sign_for_submission(_msg(), tmp_path / "absent.pem") is None
    assert "sending unsigned" in capsys.readouterr().err


def test_keygen_makes_a_private_directory_and_refuses_a_loose_one(tmp_path):
    fresh = tmp_path / "new" / "keys" / "signing.pem"
    generate_keypair(fresh)
    assert stat.S_IMODE(fresh.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(fresh.stat().st_mode) == 0o600

    loose = tmp_path / "shared"
    loose.mkdir()
    os.chmod(loose, 0o755)
    with pytest.raises(SigningError, match="must be 700"):
        generate_keypair(loose / "signing.pem")
    assert not (loose / "signing.pem").exists()


@pytest.mark.parametrize("where", ["Dropbox", "repo"])
def test_keygen_refuses_a_synced_folder_or_a_work_tree(tmp_path, where):
    base = tmp_path / where
    base.mkdir()
    if where == "repo":
        subprocess.run(["git", "init", "-q", str(base)], check=True)
    with pytest.raises(SigningError, match="synced folder|git work tree"):
        generate_keypair(base / "keys" / "signing.pem")


def test_keygen_allows_a_path_git_ignores(tmp_path):
    """An agent home that is itself a repository, with `.maceff` ignored, can hold its key."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text(".maceff/\n")
    generate_keypair(tmp_path / ".maceff" / "keys" / "signing.pem")
    assert (tmp_path / ".maceff" / "keys" / "signing.pem").exists()


def test_a_key_in_a_directory_others_can_write_is_refused(tmp_path):
    key = tmp_path / "keys" / "signing.pem"
    generate_keypair(key)
    os.chmod(key.parent, 0o755)
    report = key_custody(key)
    assert report["usable"] and report["warnings"]     # readable dir: still signs, with a warning
    assert "BEGIN" not in str(report)                  # the secret is never in the report
    os.chmod(key.parent, 0o777)
    with pytest.raises(SigningError, match="can write"):
        load_private_key(key)
    assert key_custody(key)["usable"] is False


def test_key_status_warns_but_a_key_in_a_tracked_place_still_signs(tmp_path):
    """Keygen refuses a tracked location; a key already there still signs, and key-status warns."""
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    key = repo / "keys" / "signing.pem"
    key.parent.mkdir(mode=0o700)
    os.chmod(key.parent, 0o700)
    with pytest.raises(SigningError, match="git work tree"):
        generate_keypair(key)
    public = generate_keypair(tmp_path / "outside" / "k.pem")
    os.replace(tmp_path / "outside" / "k.pem", key)
    report = key_custody(key)
    assert report["usable"] and any("git work tree" in w for w in report["warnings"])
    assert verify(_msg(), sign_for_submission(_msg(), key), [public])


# --- MIS-0004 R42: the keys live in a registry only the operator can write ----------------------

def _public_line(tmp_path, name="k"):
    from macf.amail.crypto import public_key_line
    generate_keypair(tmp_path / name)
    return public_key_line(load_private_key(tmp_path / name))


def _registry(tmp_path, text, mode=0o644):
    """A registry in a directory of its own, owned (in the test) by the trusted uid."""
    d = tmp_path / "etc"
    d.mkdir(mode=0o755, exist_ok=True)
    p = d / "registry.yaml"
    p.write_text(text)
    os.chmod(p, mode)
    return p


def test_keys_declared_by_operator(tmp_path):
    """The operator declares each agent's key with its account; the broker and the receiver read
    them from there, by card in any case, and never from the agent's own declarations."""
    from macf.amail.registry import Registry
    key = _public_line(tmp_path)
    p = _registry(tmp_path, f"agents:\n  ExampleAgent_0a1b2c:\n    account: exampleagent_0a1b2c\n"
                            f"    keys: ['{key}']\n")
    reg = Registry(p, root_uid=os.getuid())
    assert reg.keys_for("ExampleAgent_0a1b2c") == [key]
    assert reg.keys_for("exampleagent_0A1B2C") == [key]
    assert reg.account_of("ExampleAgent_0a1b2c") == "exampleagent_0a1b2c"
    assert reg.cards_of_account("exampleagent_0a1b2c") == ["ExampleAgent_0a1b2c"]
    assert reg.keys_for("OtherAgent_0a1b2c") == []


def test_a_registry_anyone_but_root_could_write_is_refused(tmp_path):
    from macf.amail.registry import Registry, RegistryError
    key = _public_line(tmp_path)
    text = f"agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys: ['{key}']\n"
    p = _registry(tmp_path, text)
    with pytest.raises(RegistryError, match="not root"):
        Registry(p, root_uid=os.getuid() + 1).keys_for("ExampleAgent_0a1b2c")
    os.chmod(p, 0o664)
    with pytest.raises(RegistryError, match="writable by group or others"):
        Registry(p, root_uid=os.getuid()).keys_for("ExampleAgent_0a1b2c")
    os.chmod(p, 0o644)
    os.chmod(p.parent, 0o777)
    with pytest.raises(RegistryError, match="could replace the file"):
        Registry(p, root_uid=os.getuid()).keys_for("ExampleAgent_0a1b2c")
    os.chmod(p.parent, 0o755)
    link = p.parent / "link.yaml"
    link.symlink_to(p)
    with pytest.raises(RegistryError, match="not a regular file"):
        Registry(link, root_uid=os.getuid()).keys_for("ExampleAgent_0a1b2c")


@pytest.mark.parametrize("body, why", [
    ("agents:\n  ExampleAgent@0a1b2c:\n    account: a\n    keys: ['{k}']\n", "old calling-card form"),
    ("agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys: ['{k}']\n"
     "  exampleagent_0a1b2c:\n    account: b\n    keys: ['{k}']\n", "same card"),
    ("agents:\n  ExampleAgent_0a1b2c:\n    keys: ['{k}']\n", "account"),
    ("agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys: []\n", "keys"),
    ("agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys: ['rsa:AAAA']\n", "ed25519"),
    ("certificates:\n  - {{name: a, serial: '3f', not_after: 2036-11-08, key: secret}}\n", "key"),
])
def test_a_malformed_registry_is_refused(tmp_path, body, why):
    from macf.amail.registry import Registry, RegistryError
    p = _registry(tmp_path, body.format(k=_public_line(tmp_path)))
    with pytest.raises(RegistryError, match=why):
        Registry(p, root_uid=os.getuid()).load()


def test_a_certificate_is_recorded_by_name_serial_and_expiry(tmp_path):
    import datetime
    from macf.amail.registry import Registry
    p = _registry(tmp_path, "certificates:\n  - {name: exampleagent_0a1b2c, serial: '3f9a01', "
                            "not_after: 2036-11-08}\n")
    (cert,) = Registry(p, root_uid=os.getuid()).certificates()
    assert (cert.name, cert.serial, cert.not_after) == ("exampleagent_0a1b2c", "3f9a01",
                                                        datetime.date(2036, 11, 8))


def test_a_key_has_a_validity_window_and_a_retired_key_never_signs(tmp_path):
    """R45 reads the dates here: a retired key verifies only inside its window and never signs."""
    import datetime as dt
    from macf.amail.registry import Registry
    old, new = _public_line(tmp_path, "old"), _public_line(tmp_path, "new")
    p = _registry(tmp_path, "agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys:\n"
                            f"      - key: '{old}'\n        valid_from: 2026-01-01T00:00:00Z\n"
                            "        valid_until: 2026-11-08T00:00:00Z\n"
                            f"      - '{new}'\n")
    reg = Registry(p, root_uid=os.getuid())
    utc = dt.timezone.utc
    assert reg.keys_for("ExampleAgent_0a1b2c", at=dt.datetime(2026, 6, 1, tzinfo=utc)) == [old, new]
    assert reg.keys_for("ExampleAgent_0a1b2c", at=dt.datetime(2026, 12, 1, tzinfo=utc)) == [new]
    assert reg.signing_keys("ExampleAgent_0a1b2c", at=dt.datetime(2026, 6, 1, tzinfo=utc)) == [new]
    assert [k.retired for k in reg.key_entries("ExampleAgent_0a1b2c")] == [True, False]


@pytest.mark.parametrize("window, why", [
    ("valid_from: 2026-01-01T00:00:00", "timezone"),
    ("valid_from: 2026-11-08T00:00:00Z\n        valid_until: 2026-01-01T00:00:00Z", "after valid_from"),
])
def test_a_bad_window_is_refused(tmp_path, window, why):
    from macf.amail.registry import Registry, RegistryError
    k = _public_line(tmp_path)
    p = _registry(tmp_path, f"agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys:\n"
                            f"      - key: '{k}'\n        {window}\n")
    with pytest.raises(RegistryError, match=why):
        Registry(p, root_uid=os.getuid()).load()


def test_the_same_key_twice_is_refused(tmp_path):
    from macf.amail.registry import Registry, RegistryError
    k = _public_line(tmp_path)
    p = _registry(tmp_path, f"agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys: ['{k}', '{k}']\n")
    with pytest.raises(RegistryError, match="declared twice"):
        Registry(p, root_uid=os.getuid()).load()


def test_a_shared_login_shows_every_card_on_its_account(tmp_path):
    """R46's case: two cards declare one account, and both are seen."""
    from macf.amail.registry import Registry
    a, b = _public_line(tmp_path, "a"), _public_line(tmp_path, "b")
    p = _registry(tmp_path, f"agents:\n  ExampleAgent_0a1b2c:\n    account: shared\n    keys: ['{a}']\n"
                            f"  OtherAgent_d4e5f6:\n    account: shared\n    keys: ['{b}']\n")
    assert Registry(p, root_uid=os.getuid()).cards_of_account("shared") == [
        "ExampleAgent_0a1b2c", "OtherAgent_d4e5f6"]


def test_a_writable_ancestor_is_refused(tmp_path):
    """Whoever can write any directory above the registry can swap the path beneath it."""
    from macf.amail.registry import Registry, RegistryError
    k = _public_line(tmp_path)
    open_dir = tmp_path / "open"
    open_dir.mkdir()
    os.chmod(open_dir, 0o777)
    d = open_dir / "etc"
    d.mkdir(mode=0o755)
    p = d / "registry.yaml"
    p.write_text(f"agents:\n  ExampleAgent_0a1b2c:\n    account: a\n    keys: ['{k}']\n")
    os.chmod(p, 0o644)
    with pytest.raises(RegistryError, match="above the registry"):
        Registry(p, root_uid=os.getuid()).load()
    os.chmod(open_dir, 0o1777)          # sticky: no one can rename another's entry
    Registry(p, root_uid=os.getuid()).load()


# --- R45 and R46: rotation against the broker's own acceptance time, and shared logins -------

def _signed(key_path, card="Alice_0a1b2c"):
    from macf.amail.crypto import sign
    m = Message(sender=f"{card.lower()}@example.test", to=["bob@example.test"], subject="s", body="b")
    m.signature = sign(m, load_private_key(key_path))
    return m


def _utc(*a):
    import datetime
    return datetime.datetime(*a, tzinfo=datetime.timezone.utc)


def test_rotation_keeps_old_signatures_verifiable(tmp_path):
    """MIS-0004 R45: a retired key verifies only what the receiving broker accepted inside its
    window, by that broker's own record, and never signs. A backdated message id is no record."""
    from macf.amail.attest import acceptance_time, may_sign, registry_verdict
    from macf.amail.registry import Registry
    old, new = _public_line(tmp_path, "old"), _public_line(tmp_path, "new")
    reg = Registry(_registry(tmp_path, f"""
agents:
  Alice_0a1b2c:
    account: alice
    keys:
      - key: "{old}"
        valid_from: 2026-01-01T00:00:00Z
        valid_until: 2026-06-01T00:00:00Z
      - key: "{new}"
        valid_from: 2026-06-01T00:00:00Z
"""), root_uid=os.getuid())
    m = _signed(tmp_path / "old")
    # Accepted inside the old key's window: still attested after it retired.
    assert registry_verdict(m, "Alice_0a1b2c", reg, accepted_at=_utc(2026, 3, 1))["trust"] == "attested"
    # The thief's case: a new message signed with the retired key, accepted after retirement.
    late = registry_verdict(m, "Alice_0a1b2c", reg, accepted_at=_utc(2026, 7, 1))
    assert late["trust"] == "suspect"
    # No record of acceptance: current signing keys only, never a retired one, and a message id
    # dated inside the old window (a peer's mint, or anyone's) changes nothing.
    m.message_id = "msg-1772000000-0123456789ab"      # 2026-02-25, inside the old window
    assert registry_verdict(m, "Alice_0a1b2c", reg, accepted_at=None)["trust"] == "suspect"
    assert registry_verdict(_signed(tmp_path / "new"), "Alice_0a1b2c", reg, accepted_at=None)["trust"] == "attested"
    # A retired key never signs; the current one does.
    assert may_sign("Alice_0a1b2c", old, reg) is False and may_sign("Alice_0a1b2c", new, reg) is True
    # The acceptance time is the receiving broker's own hand-off record, and only its own.
    own = {"rung": "local", "origin_domain": "here.test", "handed_off_at": "2026-03-01T12:00:00+00:00"}
    assert acceptance_time(own, "here.test") == _utc(2026, 3, 1, 12)
    assert acceptance_time({**own, "origin_domain": "peer.test"}, "here.test") is None
    assert acceptance_time({**own, "rung": "shared"}, "here.test") is None
    assert acceptance_time({**own, "handed_off_at": "yesterday"}, "here.test") is None
    assert acceptance_time({**own, "handed_off_at": "2026-03-01T12:00:00"}, "here.test") is None   # naive


def test_shared_login_attestation_labelled(tmp_path):
    """MIS-0004 R46: where the signing key's account also holds another agent's key, a verified
    message attests the login, and the receiver says so and names who shares it."""
    from macf.amail.attest import registry_verdict
    from macf.amail.registry import Registry
    a, b, c = (_public_line(tmp_path, n) for n in "abc")
    reg = Registry(_registry(tmp_path, f"""
agents:
  Alice_0a1b2c: {{account: shared, keys: ["{a}"]}}
  Bob_1b2c3d: {{account: shared, keys: ["{b}"]}}
  Carol_2c3d4e: {{account: carol, keys: ["{c}"]}}
"""), root_uid=os.getuid())
    shared = registry_verdict(_signed(tmp_path / "a"), "Alice_0a1b2c", reg, accepted_at=None)
    assert shared["trust"] == "attested" and shared["attests"] == "login"
    assert shared["shared_with"] == ["Bob_1b2c3d"] and "shared login" in shared["reason"]
    alone = registry_verdict(_signed(tmp_path / "c", "Carol_2c3d4e"), "Carol_2c3d4e", reg, accepted_at=None)
    assert alone["trust"] == "attested" and alone["attests"] == "agent" and alone["shared_with"] == []
    # Only a verified message is labelled: a failed one attests nothing.
    forged = registry_verdict(_signed(tmp_path / "c"), "Alice_0a1b2c", reg, accepted_at=None)
    assert forged["trust"] == "suspect" and forged["attests"] is None


def test_a_verdict_reads_the_registry_once(tmp_path):
    """One snapshot per verdict: a registry that turns untrustworthy between reads can't raise
    into ingest or mix two versions of the file (CTB on #928)."""
    from macf.amail.attest import registry_verdict
    from macf.amail.registry import Registry, RegistryError
    a, b = _public_line(tmp_path, "a"), _public_line(tmp_path, "b")
    reg = Registry(_registry(tmp_path, f"""
agents:
  Alice_0a1b2c: {{account: shared, keys: ["{a}"]}}
  Bob_1b2c3d: {{account: shared, keys: ["{b}"]}}
"""), root_uid=os.getuid())
    real, calls = reg.load, []

    def once_then_refuse():
        calls.append(1)
        if len(calls) > 1:
            raise RegistryError("the registry changed hands between reads")
        return real()
    reg.load = once_then_refuse
    verdict = registry_verdict(_signed(tmp_path / "a"), "Alice_0a1b2c", reg, accepted_at=None)
    assert verdict["trust"] == "attested" and verdict["shared_with"] == ["Bob_1b2c3d"] and len(calls) == 1
    reg.load = lambda: (_ for _ in ()).throw(RegistryError("not root's"))
    assert registry_verdict(_signed(tmp_path / "a"), "Alice_0a1b2c", reg, accepted_at=None)["trust"] == "unverified"
