"""Round-trip tests for the OPSEC pre-commit gate.

Real git repos, real commits: a staged leak must be rejected by the
installed hook; a clean commit must pass; --no-verify must bypass.
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from macf.opsec import DEFAULT_PROFILE, install_hook


def _git(repo, *args, check=True):
    return subprocess.run(
        ["git", "-C", str(repo)] + list(args),
        capture_output=True, text=True, check=check,
    )


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "scratch_repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "test@example.com")
    _git(r, "config", "user.name", "Test User")
    return r


@pytest.fixture
def profile(tmp_path):
    p = tmp_path / "profile.json"
    p.write_text(json.dumps(DEFAULT_PROFILE))
    return p


def test_install_reports_facts(repo, profile):
    facts = install_hook(repo, profile)
    assert facts["repo"] == str(repo)
    assert Path(facts["hooklet"]).exists()
    assert (repo / ".git" / "hooks" / "check_context_leakage.py").exists()


def test_clean_commit_passes(repo, profile):
    install_hook(repo, profile)
    (repo / "code.py").write_text("def add(a, b):\n    return a + b\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "-m", "add function", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_leaky_commit_rejected(repo, profile):
    install_hook(repo, profile)
    (repo / "code.py").write_text("# fixed in c25 after the bench session\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "-m", "leaky", check=False)
    assert r.returncode != 0
    assert "COMMIT REJECTED" in r.stdout + r.stderr


def test_non_ascii_rejected(repo, profile):
    install_hook(repo, profile)
    (repo / "notes.md").write_text("a thought — with an em-dash\n")
    _git(repo, "add", "notes.md")
    r = _git(repo, "commit", "-m", "unicode", check=False)
    assert r.returncode != 0


def test_no_verify_bypasses(repo, profile):
    install_hook(repo, profile)
    (repo / "code.py").write_text("# fixed in c25 after the bench session\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "--no-verify", "-m", "reviewed disclosure", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_profile_inside_repo_refused(repo):
    inside = repo / "profile.json"
    inside.write_text(json.dumps(DEFAULT_PROFILE))
    with pytest.raises(ValueError, match="inside the target repo"):
        install_hook(repo, inside)


def test_foreign_precommit_is_adopted_not_destroyed(repo, profile):
    """This used to RAISE, which was the right posture for a lone installer and
    the wrong shape for a second one: git offers a single pre-commit file, so
    refusing meant one of the two gates the framework wants simply did not
    exist. It now takes a numbered slot and adopts whatever was there."""
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\n# a hook the developer wrote\nexit 0\n")

    facts = install_hook(repo, profile)

    adopted = repo / ".git" / "hooks.local.d" / "pre-commit.d" / "00-local-preexisting"
    assert adopted.is_file(), "the developer's hook was not adopted"
    # Adopted by wrapping (#501): the developer's hook stays where it was, intact,
    # and the adopted slot runs it from there.
    assert "a hook the developer wrote" in hook.read_text(), "the developer's hook was destroyed"
    assert "../../hooks/pre-commit" in adopted.read_text(), "the adopted slot does not run the original"
    assert facts["adopted"], "adoption happened but was not reported"


def test_missing_profile_fails_closed(repo, profile):
    install_hook(repo, profile)
    profile.unlink()
    (repo / "code.py").write_text("clean line\n")
    _git(repo, "add", "code.py")
    r = _git(repo, "commit", "-m", "clean but no profile", check=False)
    assert r.returncode != 0
    assert "failing closed" in r.stdout + r.stderr


class TestCredentialSentinelScoping:
    """The gate must refuse a credential FILE without refusing the module that defines the marker.

    A bare-string rule for the sentinel matches both, which would make the
    guard unable to ship alongside its own definition -- and the only way past
    would be the bypass flag on a file that is no credential at all.
    """

    def _hits(self, text):
        import re
        from macf.opsec import DEFAULT_PROFILE
        secret = set(DEFAULT_PROFILE.get("secret_class", []))
        return [label for pat, label in DEFAULT_PROFILE["hard"]
                if label in secret and re.search(pat, text)]

    def test_grant_file_content_is_flagged(self):
        grant = '{\n  "_sentinel": "MACEFF-SECRET-SENTINEL:gmail_grant:must-not-leave-host",\n  "refresh_token": "1//0AAAAAAAAAAAAAAAAAAAAAAAAAA"\n}'
        labels = self._hits(grant)
        assert any("sentinel" in x for x in labels)
        assert any("refresh token" in x for x in labels)

    def test_module_defining_the_marker_is_not_flagged(self):
        source = 'SENTINEL = "MACEFF-SECRET-SENTINEL:gmail_grant:must-not-leave-host"\n'
        assert self._hits(source) == []


# --- The gate applies every source compiled_checks() names, not the profile alone ------
#
# For its whole life before these tests the installed hook compiled only the profile
# JSON. A hostname, a username, a home path and a provider token committed cleanly
# under the default profile, and "installed" was reported on write. These tests fix
# the contract: the hook refuses the environment categories and the secret shapes,
# and install_hook refuses to report success on a hook that would not.


def _env_decoy():
    import getpass
    import os
    import socket
    return ("deployed on %s by %s from %s/work\n"
            % (socket.gethostname(), getpass.getuser(), os.path.expanduser("~")))


def test_environment_identifiers_rejected_with_default_profile(repo, profile):
    install_hook(repo, profile)
    (repo / "notes.md").write_text(_env_decoy())
    _git(repo, "add", "notes.md")
    r = _git(repo, "commit", "-m", "env leak", check=False)
    out = r.stdout + r.stderr
    assert r.returncode != 0, out
    assert "COMMIT REJECTED" in out
    assert "[local username]" in out or "[hostname]" in out
    assert "[agent home path]" in out or "[filesystem path]" in out


def test_secret_shapes_rejected_and_withheld(repo, profile):
    install_hook(repo, profile)
    token = "ghp_" + "Q" * 36
    (repo / "conf.py").write_text("x = 1  # " + token + "\n")
    _git(repo, "add", "conf.py")
    r = _git(repo, "commit", "-m", "token", check=False)
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "[github token]" in out
    # The gate must not print what it refuses.
    assert token not in out
    assert "withheld as secret-class" in out


def test_install_self_test_reports_categories(repo, profile):
    facts = install_hook(repo, profile)
    fired = set(facts["self_test"]["fired"])
    assert {"local username", "filesystem path",
            "github token", "private key material"} <= fired


def test_install_refuses_inert_hook(repo, profile, monkeypatch):
    # Break the rendered hook's matcher source so no category can fire, and the
    # installer must refuse rather than report success.
    import macf.opsec as opsec
    broken = opsec.HOOK_TEMPLATE.replace("checks = all_checks(profile)",
                                         "checks = []")
    monkeypatch.setattr(opsec, "HOOK_TEMPLATE", broken)
    with pytest.raises(RuntimeError, match="INERT"):
        install_hook(repo, profile)



# ---- the interpreter that runs is the one the install certified (#429) ------------

def test_the_shim_runs_the_interpreter_the_install_certified(repo, profile):
    shim = Path(install_hook(repo, profile)["hooklet"]).read_text()
    assert f"PY={shlex.quote(sys.executable)}" in shim and "exec python3" not in shim


def test_a_checker_that_cannot_import_macf_refuses_unless_told_otherwise(repo, profile):
    install_hook(repo, profile)
    (repo / "clean.md").write_text("nothing private here\n")
    _git(repo, "add", "clean.md")
    # -I -S: no site-packages and no PYTHONPATH, so no macf, as under a stray python3.
    bare = [sys.executable, "-I", "-S", str(repo / ".git" / "hooks" / "check_context_leakage.py")]
    refused = subprocess.run(bare, cwd=repo, capture_output=True, text=True)
    assert refused.returncode == 1 and "cannot import macf" in refused.stderr
    opted = subprocess.run(bare, cwd=repo, capture_output=True, text=True,
                           env=dict(os.environ, MACF_OPSEC_STDLIB_ONLY="1"))
    assert opted.returncode == 0, opted.stderr


def test_the_moniker_is_required_where_there_is_one(repo, profile, tmp_path, monkeypatch):
    import macf.opsec as opsec
    from macf.utils.paths import find_agent_home
    home = tmp_path / "agent_home"
    (home / ".maceff").mkdir(parents=True)
    # The identity file as it really is: the UUID alone. The display name lives
    # where the calling card reads it, the agent's config. An earlier version of
    # this test wrote "Name@id" into the identity file, a format no real file
    # has, and so passed while the gate never saw a display name.
    (home / ".maceff_primary_agent.id").write_text("0f1e2d3c-4b5a-4978-8a9b-0c1d2e3f4a5b\n")
    (home / ".maceff" / "config.json").write_text(
        json.dumps({"agent_identity": {"calling_card": "Decoyagent"}}))
    monkeypatch.delenv("MACEFF_AGENT_NAME", raising=False)
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(home))
    find_agent_home.cache_clear()
    assert opsec.self_test_decoys() == ["reviewed and signed by Decoyagent"]
    assert "agent moniker" in install_hook(repo, profile)["self_test"]["fired"]
    # A checker that cannot see the moniker is not reported as installed.
    monkeypatch.setattr(opsec, "HOOK_TEMPLATE",
                        opsec.HOOK_TEMPLATE.replace("decoy.extend(self_test_decoys())", "pass"))
    with pytest.raises(RuntimeError, match="agent moniker"):
        install_hook(repo, profile)
    find_agent_home.cache_clear()


def test_a_shim_that_does_not_run_the_checker_is_refused_and_removed(repo, profile, monkeypatch):
    import macf.opsec as opsec
    monkeypatch.setattr(opsec, "SHIM_TEMPLATE", "#!/bin/sh\n# {python}\nexit 0\n")
    with pytest.raises(RuntimeError, match="through its shim"):
        install_hook(repo, profile)
    assert not (repo / ".git" / "hooks.local.d" / "pre-commit.d" / "10-opsec").exists()


def test_nothing_is_written_when_the_dispatcher_source_is_missing(repo, profile, tmp_path):
    with pytest.raises(ValueError, match=".githooks"):
        install_hook(repo, profile, source_root=tmp_path / "not_a_checkout")
    assert not (repo / ".git" / "hooks" / "check_context_leakage.py").exists()

class TestProfileExemptions:
    """A private deployment's own agents sign their review records with their
    calling cards; the built-in "agent uuid" rule is right for every public
    target and wrong for the one repository those agents are the subject of.
    `exempt` lists regexes matched against the CAUGHT text: one deployment's
    two cards and nothing else. A stranger's fragment still fires; a secret
    beside an exempt card still fires; the list is never a category waiver."""

    def _profile(self, tmp_path, exempt):
        p = tmp_path / "deploy_profile.json"
        d = dict(DEFAULT_PROFILE); d["exempt"] = exempt
        p.write_text(json.dumps(d))
        return p

    def test_named_cards_pass_a_strangers_fragment_does_not(self, repo, tmp_path):
        install_hook(repo, self._profile(tmp_path, ["@63e6b2", "@15b944"]))
        (repo / "reviews.md").write_text("reviewed by Alpha@63e6b2 and Beta@15b944\n")
        _git(repo, "add", "reviews.md")
        r = _git(repo, "commit", "-m", "record two reviews", check=False)
        assert r.returncode == 0, r.stdout + r.stderr
        (repo / "reviews.md").write_text("and a visitor, Gamma@abcdef\n")
        _git(repo, "add", "reviews.md")
        r = _git(repo, "commit", "-m", "a stranger", check=False)
        assert r.returncode != 0
        assert "[agent uuid] '@abcdef'" in r.stdout + r.stderr

    def test_an_exemption_never_covers_a_secret(self, repo, tmp_path):
        install_hook(repo, self._profile(tmp_path, ["@63e6b2", r"ghp_.*"]))
        (repo / "notes.md").write_text("Alpha@63e6b2 says token = ghp_" + "A" * 36 + "\n")
        _git(repo, "add", "notes.md")
        r = _git(repo, "commit", "-m", "secret beside a card", check=False)
        out = r.stdout + r.stderr
        assert r.returncode != 0 and "COMMIT REJECTED" in out
        assert "withheld as secret-class" in out

    def test_scan_text_applies_the_same_exemption(self):
        from macf.opsec import scan_text
        prof = {"hard": [], "soft": [], "exempt": ["@63e6b2"]}
        t = "Alpha@63e6b2 met Gamma@abcdef"
        labels = [(f.label, t[f.start:f.end]) for f in scan_text(t, profile=prof).findings]
        assert ("agent uuid", "@abcdef") in labels and ("agent uuid", "@63e6b2") not in labels


def _merge_in_a_leak_from_main(repo, profile, published=True):
    """main gains a line the profile refuses, committed past the gate as if
    under another profile; a feature branch has a commit of its own; the
    branch then merges main and stops before committing. With *published*,
    main is pushed to a bare remote and fetched first, as on a shared main."""
    install_hook(repo, profile)
    (repo / "base.txt").write_text("base\n")
    _git(repo, "add", "base.txt")
    _git(repo, "commit", "-q", "-m", "base")
    main = _git(repo, "branch", "--show-current").stdout.strip()
    _git(repo, "switch", "-q", "-c", "feature")
    (repo / "feature.txt").write_text("feature work\n")
    _git(repo, "add", "feature.txt")
    _git(repo, "commit", "-q", "-m", "feature")
    _git(repo, "switch", "-q", main)
    (repo / "upstream.txt").write_text("# fixed in c25 after the bench session\n")
    _git(repo, "add", "upstream.txt")
    _git(repo, "commit", "-q", "--no-verify", "-m", "upstream")
    if published:
        remote = repo.parent / "remote.git"
        _git(repo, "init", "-q", "--bare", str(remote))
        _git(repo, "remote", "add", "origin", str(remote))
        _git(repo, "push", "-q", "origin", main)
        _git(repo, "fetch", "-q", "origin")
    _git(repo, "switch", "-q", "feature")
    _git(repo, "merge", "--no-ff", "--no-commit", main)


def test_a_merge_is_not_refused_for_what_the_incoming_side_brings(repo, profile):
    """The incoming side's lines were scanned when they were committed there,
    under whoever committed them. A merge that only brings them in has written
    nothing for this gate to refuse, and says that it narrowed the scan."""
    _merge_in_a_leak_from_main(repo, profile)
    r = _git(repo, "commit", "-m", "merge main", check=False)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "only what the merge adds" in r.stdout + r.stderr


def test_an_unpublished_incoming_side_is_scanned_whole(repo, profile):
    """A side never pushed was never scanned on its way out: committed past the
    gate, or before it was installed. Merging it is how it would first become
    public, so the whole merge is scanned and its line is refused."""
    _merge_in_a_leak_from_main(repo, profile, published=False)
    r = _git(repo, "commit", "-m", "merge main", check=False)
    out = r.stdout + r.stderr
    assert r.returncode != 0
    assert "upstream.txt" in out
    assert "not on any remote" in out


def test_a_leak_written_while_merging_is_still_refused(repo, profile):
    _merge_in_a_leak_from_main(repo, profile)
    (repo / "resolution.txt").write_text("# settled in c25 during the merge\n")
    _git(repo, "add", "resolution.txt")
    r = _git(repo, "commit", "-m", "merge main", check=False)
    out = r.stdout + r.stderr  # git hands a hook's output to stderr
    assert r.returncode != 0
    assert "resolution.txt" in out
    assert "upstream.txt" not in out
