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
