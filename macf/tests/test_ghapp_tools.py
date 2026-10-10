"""The image's GitHub App tools (docker/ghapp/, git_discipline section 4).

Three defects a container agent found setting up its own app, each pinned here:
- the tools assumed one app name, so a second agent's helper looked in the wrong home;
- a token cache emptied by a full disk could not be parsed, so every call failed;
- a helper that could not mint a token stayed silent, and the command quietly ran as the
  operator.
``ghapp.py`` imports PyJWT at the top; nothing tested here signs, so a stub stands in.
"""
import errno
import importlib.util
import json
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[2] / "docker" / "ghapp"


@pytest.fixture
def ghapp(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "jwt", types.SimpleNamespace(encode=lambda *a, **k: "signed"))
    spec = importlib.util.spec_from_file_location("ghapp_under_test", TOOLS / "ghapp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path / "ghapp")
    monkeypatch.delenv("GHAPP_NAME", raising=False)
    return mod


def _app(mod, name, owner="acme"):
    d = mod.ROOT / name
    d.mkdir(parents=True)
    (d / "app.json").write_text(json.dumps({"id": 1, "slug": f"{name}-app", "owner": owner}))
    (d / "private-key.pem").write_text("key")
    return d


def test_the_app_is_named_given_then_env_then_the_only_one(ghapp, monkeypatch):
    _app(ghapp, "manny2")
    assert ghapp.resolve_name(None) == "manny2"
    monkeypatch.setenv("GHAPP_NAME", "other")
    assert ghapp.resolve_name(None) == "other"
    assert ghapp.resolve_name("given") == "given"


def test_several_apps_and_no_name_is_refused_not_guessed(ghapp):
    _app(ghapp, "manny1")
    _app(ghapp, "manny2")
    with pytest.raises(ghapp.NoApp, match="several apps"):
        ghapp.resolve_name(None)
    assert ghapp.main(["token", "--repo", "acme/x"]) == 2


def test_an_empty_token_cache_is_minted_anew(ghapp, monkeypatch, capsys):
    """A full disk left the cache at 0 bytes; the call must mint, not crash on parsing."""
    d = _app(ghapp, "manny2")
    (d / "token-acme.json").write_text("")
    later = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))

    def call(method, path, token="", bearer_jwt="", body=None):
        if path == "/app/installations":
            return [{"id": 7, "account": {"login": "acme"}}]
        if path.endswith("/access_tokens"):
            return {"token": "fresh", "expires_at": later}
        return {"repositories": [{"full_name": "acme/x"}]}
    monkeypatch.setattr(ghapp, "call", call)
    assert ghapp.main(["token", "--repo", "acme/x"]) == 0
    assert capsys.readouterr().out == "fresh"
    assert json.loads((d / "token-acme.json").read_text())["token"] == "fresh"


def test_a_secret_write_cut_short_leaves_the_old_file(ghapp, monkeypatch, tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    path = store / "token-acme.json"
    path.write_text('{"token": "old"}')

    def full(*a):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(ghapp.os, "fsync", full)
    with pytest.raises(OSError):
        ghapp.write_secret(path, '{"token": "new"}')
    assert json.loads(path.read_text()) == {"token": "old"}
    assert [p.name for p in store.iterdir()] == ["token-acme.json"]


def test_a_credential_helper_that_cannot_mint_says_so(tmp_path):
    """No app in this home: git will fall back to the next helper, so the helper speaks up."""
    r = subprocess.run([sys.executable, str(TOOLS / "git-credential-ghapp"), "get"],
                       input="protocol=https\nhost=github.com\npath=acme/x.git\n",
                       capture_output=True, text=True, env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"},
                       timeout=60)
    assert r.stdout == ""
    assert "git-credential-ghapp: no app token for acme/x" in r.stderr


def test_the_tools_run_from_the_image_venv():
    for name in ("ghapp.py", "git-credential-ghapp", "gh-app-identity"):
        assert (TOOLS / name).read_text().splitlines()[0] == "#!/opt/maceff-venv/bin/python3"


def _api(later, pages, calls):
    def call(method, path, token="", bearer_jwt="", body=None):
        calls.append(path)
        if path == "/app/installations":
            return [{"id": 7, "account": {"login": "acme"}}]
        if path.endswith("/access_tokens"):
            return {"token": "fresh", "expires_at": later}
        page = int(path.rsplit("page=", 1)[1]) if "page=" in path else 1
        return {"total_count": sum(len(p) for p in pages),
                "repositories": [{"full_name": n} for n in pages[page - 1]] if page <= len(pages) else []}
    return call


def _later():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 3600))


def test_a_repository_added_after_the_cache_is_minted_for_not_refused(ghapp, monkeypatch, capsys):
    """Review of this PR: a cached token's list predates a newly installed repository."""
    d = _app(ghapp, "manny2")
    (d / "token-acme.json").write_text(json.dumps(
        {"token": "old", "expires_epoch": time.time() + 3000, "repos": ["acme/x"]}))
    monkeypatch.setattr(ghapp, "call", _api(_later(), [["acme/x", "acme/new"]], []))
    assert ghapp.main(["token", "--repo", "acme/new"]) == 0
    assert capsys.readouterr().out == "fresh"


def test_every_page_of_repositories_is_read(ghapp, monkeypatch, capsys):
    _app(ghapp, "manny2")
    pages = [[f"acme/r{i}" for i in range(100)], [f"acme/r{i}" for i in range(100, 150)]]
    calls = []
    monkeypatch.setattr(ghapp, "call", _api(_later(), pages, calls))
    assert ghapp.main(["token", "--repo", "acme/r149"]) == 0
    assert sum("installation/repositories" in c for c in calls) == 2


def test_an_unknown_app_name_is_a_sentence_and_creates_nothing(ghapp, capsys):
    _app(ghapp, "manny2")
    assert ghapp.main(["--name", "nosuch", "token", "--repo", "acme/x"]) == 2
    assert "no app named 'nosuch'" in capsys.readouterr().err
    assert not (ghapp.ROOT / "nosuch").exists()


def test_the_state_lives_under_the_agents_home_when_one_is_named(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "jwt", types.SimpleNamespace(encode=lambda *a, **k: "signed"))
    monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path / "agent_home"))
    spec = importlib.util.spec_from_file_location("ghapp_home", TOOLS / "ghapp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.ROOT == tmp_path / "agent_home" / ".maceff" / "ghapp"


@pytest.mark.parametrize("args,expected", [
    (["api", "/repos/other/thing/issues"], "other/thing"),
    (["api", "repos/other/thing/pulls"], "other/thing"),
    (["pr", "view", "1", "-R", "https://github.com/Other/Thing.git"], "other/thing"),
    (["pr", "view", "1", "-R", "github.com/other/thing"], "other/thing"),
])
def test_the_wrapper_mints_for_the_repository_the_command_names(tmp_path, args, expected):
    """With no app in this home the token call fails, and the wrapper's message names the
    repository it decided on, which is what this checks."""
    r = subprocess.run([sys.executable, str(TOOLS / "gh-app-identity"), *args],
                       env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin", "GH_REAL": "/bin/true"},
                       capture_output=True, text=True, cwd=tmp_path, timeout=60)
    assert f"app token unavailable for {expected} " in r.stderr
