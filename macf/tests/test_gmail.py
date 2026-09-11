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


class TestQueryCompiler:
    """A pure function, so the tests are a table. Equality with a hand-written query is the point."""

    @pytest.mark.parametrize("kwargs,expected", [
        (dict(from_="sridhar", since="7d"), "from:sridhar newer_than:7d"),
        (dict(text="consent reissue", has_attachment=True), "has:attachment consent reissue"),
        (dict(since="2026-09-01", until="2026-09-10"), "after:2026/09/01 before:2026/09/10"),
        (dict(subject="two words", unread=True, label="Work"), 'subject:"two words" label:Work is:unread'),
        (dict(), ""),
    ])
    def test_flags_compile_to_the_query_a_person_would_type(self, kwargs, expected):
        text = kwargs.pop("text", "")
        assert gmail.compile_query(text, **kwargs) == expected

    def test_a_malformed_date_is_refused_not_passed_through(self):
        with pytest.raises(gmail.GmailError, match="date must be"):
            gmail.compile_query(since="last tuesday")

    def test_saved_query_is_a_name_that_expands_and_flags_layer_on_top(self, home):
        gmail.save_query("irb", "from:northeastern.edu subject:IRB")
        assert gmail.resolve_query("", "irb", since="30d") == "from:northeastern.edu subject:IRB newer_than:30d"
        assert gmail.delete_query("irb") and not gmail.delete_query("irb")
        with pytest.raises(gmail.GmailError, match="no saved query"):
            gmail.resolve_query("", "irb")

    def test_saved_queries_file_holds_names_and_never_results(self, home):
        gmail.save_query("q", "from:x")
        raw = (home / ".maceff" / "gmail_queries.json").read_text()
        assert raw.strip() == '{\n  "q": "from:x"\n}'


class TestAttachments:
    def _seed(self, home):
        _fake_grant(home)
        gmail.cache_put("T1", {"thread_id": "T1", "fetched_at": "now", "messages": [
            {"message_id": "M1", "date": "d", "from": "a@x", "to": "", "cc": "", "subject": "s",
             "body": "", "attachments": [{"filename": "report.txt", "mime": "text/plain",
                                          "size": 5, "attachment_id": "ATT1"}]}]})

    def test_list_reads_the_cached_record_without_a_network_call(self, home, monkeypatch):
        self._seed(home)
        monkeypatch.setattr(gmail, "api", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
        rows = gmail.list_attachments("T1")
        assert [(r["filename"], r["message_id"]) for r in rows] == [("report.txt", "M1")]

    def test_get_refuses_the_agent_home_and_the_cache_before_touching_the_network(self, home, monkeypatch):
        self._seed(home)
        monkeypatch.setattr(gmail, "api", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))
        with pytest.raises(gmail.GmailError, match="agent home"):
            gmail.get_attachment("T1", "ATT1", home / "agent" / "private" / "x.txt")
        with pytest.raises(gmail.GmailError, match="encrypted cache"):
            gmail.get_attachment("T1", "ATT1", gmail.cache_root() / "x.txt")

    def test_get_writes_where_named_and_the_receipt_hashes_what_was_written(self, home, tmp_path, monkeypatch):
        import base64, hashlib
        self._seed(home)
        payload = b"hello"
        monkeypatch.setattr(gmail, "api", lambda m, p, t, **k: (200, {"data": base64.urlsafe_b64encode(payload).decode()}))
        dest = tmp_path / "downloads"
        dest.mkdir()
        r = gmail.get_attachment("T1", "ATT1", dest)
        assert Path(r["path"]) == dest / "report.txt"
        assert Path(r["path"]).read_bytes() == payload
        assert r["sha256"] == hashlib.sha256(payload).hexdigest() and r["bytes"] == 5


def _plant(home, threads):
    """Put thread records straight into the encrypted cache, as fetch_thread would."""
    _fake_grant(home)
    idx = {}
    for tid, subject, body in threads:
        msg = {"message_id": tid + "m", "date": "Thu, 10 Sep 2026 09:00:00 -0400", "from": "a@example.org",
               "to": "b@example.org", "cc": "", "subject": subject, "rfc_message_id": "<x>", "body": body,
               "attachments": []}
        gmail.cache_put(tid, {"thread_id": tid, "fetched_at": "2026-09-10T09:00:00-0400", "messages": [msg]})
        idx[tid] = {"fetched_at": "2026-09-10T09:00:00-0400", "messages": 1, "date": msg["date"],
                    "from": msg["from"], "subject": subject}
    gmail._index_put(idx)


PLANTED = [
    ("t_irb", "Request to reissue participant consents",
     "The ethics office will send corrected consent forms for the study once the agreement is countersigned."),
    ("t_lunch", "Friday lunch", "Anyone want tacos on Friday? The place on the corner has a new menu."),
    ("t_scope", "Bench instrument", "The oscilloscope on the bench answers over the network again after a power cycle."),
]


def _deps():
    from macf.hybrid_search import base_indexer
    return base_indexer.DEPS_AVAILABLE


class TestLocalSearch:
    def test_refuses_without_local_flag(self, home, capsys):
        """`gmail search` is local-only; without --local it refuses and points at `gmail list`."""
        from macf.cli import cmd_gmail_search
        rc = cmd_gmail_search(Namespace(query="x", local=False, limit=10, keyword_only=False, json=False))
        assert rc == 1
        assert "❌" in capsys.readouterr().out

    def test_empty_query_and_empty_cache(self, home):
        with pytest.raises(gmail.GmailError, match="needs a query"):
            gmail.search_local("   ")
        _fake_grant(home)
        assert gmail.search_local("anything") == {"query": "anything", "mode": "none", "cached": 0, "results": []}

    def test_keyword_mode_ranks_planted_thread_first(self, home, monkeypatch):
        """With the search libraries simulated absent, term overlap still finds the planted thread."""
        _plant(home, PLANTED)
        from macf.hybrid_search import base_indexer
        monkeypatch.setattr(base_indexer, "DEPS_AVAILABLE", False)
        out = gmail.search_local("consent forms ethics")
        assert out["mode"] == "keyword"
        assert out["results"][0]["thread_id"] == "t_irb"
        assert all("body" not in r for r in out["results"])

    @pytest.mark.skipif(not _deps(), reason="lancedb / sentence-transformers not installed")
    def test_hybrid_finds_paraphrase_and_writes_nothing_to_disk(self, home, monkeypatch, tmp_path, capsys):
        """A paraphrase with no shared keywords ranks the planted thread first, and a walk of every
        writable root during and after the query finds no new file anywhere, inside or outside the cache."""
        _plant(home, PLANTED)
        box = tmp_path / "box"
        for d in ("tmp", "home", "cwd"):
            (box / d).mkdir(parents=True)
        monkeypatch.setenv("TMPDIR", str(box / "tmp"))
        monkeypatch.setenv("HOME", str(box / "home"))
        monkeypatch.chdir(box / "cwd")
        before = {str(p) for p in tmp_path.rglob("*")}
        seen_during = set()
        real_rrf = gmail._rrf

        def spy(rankings, k=60):  # the table is live at this moment
            seen_during.update(str(p) for p in tmp_path.rglob("*"))
            return real_rrf(rankings, k)
        monkeypatch.setattr(gmail, "_rrf", spy)
        out = gmail.search_local("review board paperwork for volunteers")  # no token overlap with t_irb
        assert out["mode"] == "hybrid"
        assert out["results"][0]["thread_id"] == "t_irb"
        after = {str(p) for p in tmp_path.rglob("*")}
        assert seen_during - before == set(), "index touched disk during the query"
        # the one permitted new file is the audit receipt (mode + counts, never mail); see the grep below
        assert {Path(x).name for x in after - before} <= {"gmail_audit.jsonl"}, "index left something on disk"
        # and the planted phrase rests nowhere in plaintext under the temp root
        for p in tmp_path.rglob("*"):
            if p.is_file():
                assert b"countersigned" not in p.read_bytes()
        assert "countersigned" not in capsys.readouterr().out

    def test_purge_after_search_leaves_nothing(self, home):
        _plant(home, PLANTED)
        gmail.search_local("tacos", keyword_only=True)
        root = gmail.cache_root()
        assert root.exists()
        gmail.cache_purge()
        assert not root.exists()
        assert gmail.search_local("tacos", keyword_only=True)["cached"] == 0

    def test_cli_rows_are_headers_only(self, home, capsys):
        from macf.cli import cmd_gmail_search
        _plant(home, PLANTED)
        rc = cmd_gmail_search(Namespace(query="oscilloscope", local=True, limit=10, keyword_only=True, json=True))
        assert rc == 0
        d = json.loads(capsys.readouterr().out)
        assert d["mode"] == "keyword" and d["results"][0]["thread_id"] == "t_scope"
        assert set(d["results"][0]) == {"thread_id", "date", "from", "subject", "messages", "score"}
