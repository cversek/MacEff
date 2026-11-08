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
    assert reg.card_of_account("exampleagent_0a1b2c") == "ExampleAgent_0a1b2c"
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
