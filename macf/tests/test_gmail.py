"""macf_tools gmail: grant custody, the private encrypted cache, and the CLI surface.

No test touches Google. HTTP is stubbed at ``gmail.api``/``gmail._post_form``;
the agent home is a tmp_path so nothing here can read or write a real grant.
"""
import json
import os
import stat
from argparse import Namespace
from pathlib import Path

import pytest

from macf import gmail


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A throwaway agent home and a throwaway temp root for the cache."""
    h = tmp_path / "home"
    (h / ".maceff").mkdir(parents=True)
    monkeypatch.setattr(gmail, "_agent_home", lambda: h)
    tmp_root = tmp_path / "tmp"
    tmp_root.mkdir()
    monkeypatch.setattr(gmail.tempfile, "gettempdir", lambda: str(tmp_root))
    return h


def _fake_grant(home, cache_id="cafe" * 8, profile="read"):
    g = {"_sentinel": gmail.SENTINEL, "profile": profile, "scopes": gmail.PROFILES[profile],
         "client_id": "x.apps.googleusercontent.com", "refresh_token": "1//0FAKEFAKEFAKEFAKEFAKEFAKEFAKE",
         "access_token": "at", "access_expires_at": 9_999_999_999, "issued_at": "2026-09-10T12:00:00-0400",
         "cache_id": cache_id}
    gmail._write_private(home / ".maceff" / "gmail_grant.json", g)
    return g


class TestGrantCustody:
    def test_no_grant_refuses_with_pointer(self, home):
        """Status without a grant names the missing path; list raises the refusal."""
        rc = __import__("macf.cli", fromlist=["cmd_gmail_status"]).cmd_gmail_status(Namespace(check=False, json=False))
        assert rc == 1
        with pytest.raises(gmail.GmailError, match="no Gmail grant"):
            gmail.list_threads("x")

    def test_grant_and_key_are_mode_600_and_carry_sentinel(self, home):
        """Every credential-class file is 0600 and greps for the sentinel."""
        _fake_grant(home)
        gmail._load_key()
        for name in ("gmail_grant.json", "gmail_cache_key"):
            p = home / ".maceff" / name
            assert stat.S_IMODE(p.stat().st_mode) == 0o600
            assert gmail.SENTINEL in p.read_text()

    def test_backup_excludes_every_credential_file(self, home):
        """The backup walker skips grant, client, and cache key by name, and a renamed grant by sentinel."""
        from macf.backup.paths import iter_backup_files
        _fake_grant(home)
        gmail._load_key()
        (home / ".maceff" / "gmail_client.json").write_text("{}")
        (home / ".maceff" / "renamed.json").write_text(gmail.SENTINEL)
        (home / ".maceff" / "config.json").write_text("{}")
        kept = {f.name for f in iter_backup_files(home / ".maceff")}
        assert kept == {"config.json"}


class TestPrivateCache:
    def test_cache_root_is_outside_the_agent_home(self, home):
        _fake_grant(home)
        root = gmail.cache_root()
        assert home not in root.parents and root != home
        assert stat.S_IMODE(root.stat().st_mode) == 0o700

    def test_cached_object_is_unreadable_without_the_key(self, home):
        """Bytes on disk carry neither the plaintext nor a decryptable payload under another key."""
        _fake_grant(home)
        gmail.cache_put("t1", {"thread_id": "t1", "messages": [{"body": "consent reissue secret phrase"}]})
        blobs = list(gmail.cache_root().iterdir())
        assert len(blobs) == 1
        raw = blobs[0].read_bytes()
        assert b"consent reissue" not in raw
        (home / ".maceff" / "gmail_cache_key").unlink()
        gmail._load_key()  # a fresh key
        with pytest.raises(gmail.GmailError, match="unreadable"):
            gmail.cache_get("t1")

    def test_purge_overwrites_and_removes_everything(self, home):
        _fake_grant(home)
        gmail.cache_put("t1", {"a": 1})
        gmail.cache_put("_index", {"t1": {}})
        root = gmail.cache_root()
        assert gmail.cache_purge()["purged"] == 2
        assert not root.exists()

    def test_pre_cache_grant_gets_a_cache_id_without_reauth(self, home):
        g = _fake_grant(home)
        del g["cache_id"]
        gmail._write_private(home / ".maceff" / "gmail_grant.json", g)
        gmail.cache_root()
        assert gmail.load_grant()["cache_id"]

    def test_nothing_is_written_under_the_agent_tree(self, home):
        """After a fetch, the only new files under the home are the credential files."""
        _fake_grant(home)
        gmail._load_key()
        before = {p for p in home.rglob("*") if p.is_file()}
        gmail.cache_put("t9", {"thread_id": "t9", "messages": []})
        after = {p for p in home.rglob("*") if p.is_file()}
        assert after - before == set()


class TestCliSurface:
    def _stub_api(self, monkeypatch, routes):
        def fake(method, path, token, payload=None, params=None):
            for prefix, resp in routes:
                if path.startswith(prefix):
                    return 200, resp(params, payload) if callable(resp) else resp
            return 404, {"error": {"message": "no route " + path}}
        monkeypatch.setattr(gmail, "api", fake)

    def test_list_prints_one_row_per_thread_and_no_bodies(self, home, monkeypatch, capsys):
        from macf import cli
        _fake_grant(home)
        thread = {"messages": [{"payload": {"headers": [
            {"name": "From", "value": "Alice <a@x.org>"}, {"name": "Subject", "value": "hello\x1b[31m"},
            {"name": "Date", "value": "Thu, 10 Sep 2026 12:00:00 -0400"}]}}]}
        self._stub_api(monkeypatch, [("/threads/", thread), ("/threads", {"threads": [{"id": "T1", "snippet": "body text"}]})])
        rc = cli.cmd_gmail_list(Namespace(query="from:alice", limit=5, json=False))
        out = capsys.readouterr().out
        assert rc == 0 and "id=T1" in out and "1 thread(s)" in out
        assert "\x1b" not in out and "\\x1b" in out  # escape neutralised, not stripped
        assert "body text" not in out

    def test_read_serves_from_cache_second_time(self, home, monkeypatch, capsys):
        from macf import cli
        _fake_grant(home)
        calls = []
        def full(params, payload):
            calls.append(1)
            return {"messages": [{"id": "M1", "payload": {"mimeType": "text/plain",
                    "headers": [{"name": "From", "value": "a@x"}, {"name": "Subject", "value": "s"}, {"name": "Date", "value": "d"}],
                    "body": {"data": "aGVsbG8="}}}]}
        self._stub_api(monkeypatch, [("/threads/T1", full)])
        assert cli.cmd_gmail_read(Namespace(thread_id="T1", json=False)) == 0
        assert "fetched" in capsys.readouterr().out
        assert cli.cmd_gmail_read(Namespace(thread_id="T1", json=False)) == 0
        out = capsys.readouterr().out
        assert "(cache" in out and "hello" in out and len(calls) == 1

    def test_draft_with_attachment_builds_multipart_and_refusal_is_reported(self, home, tmp_path, monkeypatch, capsys):
        from macf import cli
        _fake_grant(home, profile="draft")
        f = tmp_path / "report.txt"
        f.write_text("attached content")
        msg = gmail.build_draft(["b@x.org"], "subj", "hi", attach=[str(f)])
        parts = [p.get_filename() for p in msg.iter_attachments()]
        assert parts == ["report.txt"]
        self._stub_api(monkeypatch, [])  # POST /drafts -> 404 route -> refusal
        rc = cli.cmd_gmail_draft(Namespace(to=["b@x.org"], cc=None, subject="s", body="b", body_file=None,
                                           reply_to=None, attach=[str(f)], json=False))
        out = capsys.readouterr().out
        assert rc == 1 and out.startswith("❌")

    def test_status_json_reports_send_possibility_from_scopes(self, home, capsys):
        from macf import cli
        _fake_grant(home, profile="draft")
        assert cli.cmd_gmail_status(Namespace(check=False, json=True)) == 0
        info = json.loads(capsys.readouterr().out)
        assert info["can_send_at_google"] is True and info["sentinel"] is True
