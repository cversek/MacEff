"""Extra policy roots (#592): a package's own policy set, read where it lives.

MACEFF_POLICY_ROOTS names directories searched after the framework's root. The framework's
own policies always resolve to the framework, an extra root's copy of one is reported, not
used, and a name only extra roots carry, in more than one, is refused as ambiguous.
"""
import os
import subprocess
import sys
from pathlib import Path

from dataclasses import dataclass

import pytest

from macf.utils import manifest as mf


@dataclass(frozen=True, kw_only=True)
class Roots:
    fw: Path
    a: Path
    b: Path


@pytest.fixture
def roots(tmp_path, monkeypatch):
    fw = tmp_path / "framework" / "policies"
    (fw / "base" / "development").mkdir(parents=True)
    (fw / "base" / "development" / "task_management.md").write_text("# Task Management\n")
    a = tmp_path / "agentcad_pkg" / "policies"
    (a / "cad").mkdir(parents=True)
    (a / "agentcad-usage.md").write_text("# agentcad usage\n")
    (a / "cad" / "agentcad-export.md").write_text("# agentcad export\n")
    b = tmp_path / "other"
    b.mkdir()
    monkeypatch.setattr(mf, "get_framework_policies_path", lambda maceff_root=None: fw)
    monkeypatch.delenv(mf.POLICY_ROOTS_ENV, raising=False)
    mf._reported.clear()
    return Roots(fw=fw, a=a, b=b)


def _set(monkeypatch, *entries):
    monkeypatch.setenv(mf.POLICY_ROOTS_ENV, os.pathsep.join(str(e) for e in entries))


def test_without_the_variable_only_the_framework_is_read(roots):
    fw = roots.fw
    assert [r.name for r in mf.policy_roots()] == ["framework"]
    assert mf.find_policy_file("task_management") == fw / "base" / "development" / "task_management.md"
    assert mf.find_policy_file("agentcad-usage") is None


def test_an_extra_root_is_found_listed_and_named(roots, monkeypatch):
    fw, a = roots.fw, roots.a
    _set(monkeypatch, f"agentcad={a}")
    assert mf.find_policy_file("agentcad-usage") == a / "agentcad-usage.md"
    assert mf.find_policy_file("agentcad:agentcad-usage") == a / "agentcad-usage.md"
    assert mf.find_policy_file("agentcad-export", parents=["cad"]) == a / "cad" / "agentcad-export.md"
    listed = {p["name"]: p for p in mf.list_policy_files()}
    assert listed["agentcad-usage"]["root"] == "agentcad"
    assert listed["agentcad-usage"]["category"] == "agentcad"
    assert listed["agentcad-export"]["category"] == "agentcad/cad"
    assert listed["agentcad-export"]["relative_path"] == "agentcad:cad/agentcad-export.md"
    assert listed["task_management"]["root"] == "framework"


def test_a_root_without_a_name_is_named_by_its_directory(roots, monkeypatch):
    a = roots.a
    _set(monkeypatch, a)
    assert [r.name for r in mf.extra_policy_roots()] == ["policies"]


def test_a_qualified_name_split_on_slash_by_the_cli_still_names_its_root(roots, monkeypatch):
    """The CLI splits 'agentcad:cad/agentcad-export' on '/', so the root arrives on the
    first parent."""
    a = roots.a
    _set(monkeypatch, f"agentcad={a}")
    assert mf.find_policy_file("agentcad-export", parents=["agentcad:cad"]) == a / "cad" / "agentcad-export.md"


def test_the_framework_keeps_its_own_names_and_says_a_copy_was_ignored(roots, monkeypatch, capsys):
    fw, b = roots.fw, roots.b
    (b / "task_management.md").write_text("# a package's copy\n")
    _set(monkeypatch, f"other={b}")
    assert mf.find_policy_file("task_management") == fw / "base" / "development" / "task_management.md"
    mf.find_policy_file("task_management")
    err = capsys.readouterr().err
    assert err.count("also in root(s) other") == 1, "the shadowed copy is reported once per process"
    assert mf.find_policy_file("other:task_management") == b / "task_management.md"
    assert mf.find_policy_file("framework:task_management") == fw / "base" / "development" / "task_management.md"


def test_a_name_in_two_extra_roots_is_refused_naming_both(roots, monkeypatch):
    a, b = roots.a, roots.b
    (b / "agentcad-usage.md").write_text("# a second copy\n")
    _set(monkeypatch, f"agentcad={a}", f"other={b}")
    with pytest.raises(mf.PolicyAmbiguous) as e:
        mf.find_policy_file("agentcad-usage")
    assert "agentcad:agentcad-usage" in str(e.value) and "other:agentcad-usage" in str(e.value)
    assert mf.find_policy_file("other:agentcad-usage") == b / "agentcad-usage.md"


def test_bad_roots_are_reported_once_and_left_out(roots, monkeypatch, capsys, tmp_path):
    a, b = roots.a, roots.b
    _set(monkeypatch, f"agentcad={a}", f"agentcad={b}", f"gone={tmp_path / 'missing'}",
         f"framework={b}", f"a/b={b}")
    assert [r.name for r in mf.extra_policy_roots()] == ["agentcad"]
    mf.extra_policy_roots()
    err = capsys.readouterr().err
    assert err.count("already taken") == 1
    assert err.count("is not a directory") == 1
    assert err.count("may not be empty") == 2


def test_an_ambiguous_name_does_not_break_the_hook_injection(roots, monkeypatch, capsys):
    """Policy injection runs inside hooks; a refusal must be said, not raised."""
    from macf.policy import injection
    a, b = roots.a, roots.b
    (b / "agentcad-usage.md").write_text("# a second copy\n")
    _set(monkeypatch, f"agentcad={a}", f"other={b}")
    monkeypatch.setattr(mf, "get_policies_for_task_type", lambda t: ["agentcad-usage", "task_management"])
    monkeypatch.setattr("macf.agent_events_log.append_event", lambda *a, **k: True)
    emitted = injection.emit_policy_injections_for_tasks({"7": "TASK"}, source="test")
    assert emitted == ["task_management"]
    assert "more than one root" in capsys.readouterr().err


def test_the_cli_reads_and_lists_an_extra_root(roots, monkeypatch, tmp_path):
    """End to end through macf_tools, as an agent would run it."""
    a = roots.a
    src = Path(mf.__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(src), MACF_EVENTS_LOG_PATH=str(tmp_path / "events.jsonl"))
    env[mf.POLICY_ROOTS_ENV] = f"agentcad={a}"
    run = lambda *argv: subprocess.run([sys.executable, "-m", "macf.cli", *argv],
                                       capture_output=True, text=True, env=env, timeout=120)
    listed = run("policy", "list")
    assert listed.returncode == 0, listed.stderr
    assert f"root agentcad: {a}" in listed.stdout and "agentcad-usage" in listed.stdout
    read = run("policy", "read", "agentcad:agentcad-usage")
    assert read.returncode == 0, read.stderr
    assert "agentcad usage" in read.stdout


# --- who can write a root (#592 review): a root's policies become the agent's instructions ----

def test_a_root_writable_by_every_account_is_refused_by_name(roots, monkeypatch, capsys):
    a = roots.a
    a.chmod(0o777)
    _set(monkeypatch, f"agentcad={a}")
    assert mf.extra_policy_roots() == []
    assert mf.find_policy_file("agentcad-usage") is None
    err = capsys.readouterr().err
    assert "policy root 'agentcad' skipped" in err and "writable by every account" in err


def test_a_policy_file_writable_by_others_refuses_its_root(roots, monkeypatch, capsys):
    a = roots.a
    (a / "cad" / "agentcad-export.md").chmod(0o666)
    _set(monkeypatch, f"agentcad={a}")
    assert mf.extra_policy_roots() == []
    assert "agentcad-export.md is writable by every account" in capsys.readouterr().err


def test_group_write_counts_only_when_the_group_has_someone_else(roots, monkeypatch, capsys):
    """A user-private group's write bit grants nobody else anything; a shared group's does."""
    a = roots.a
    a.chmod(0o775)
    _set(monkeypatch, f"agentcad={a}")
    monkeypatch.setattr(mf, "_private_group", lambda gid, uid: True)
    assert [r.name for r in mf.extra_policy_roots()] == ["agentcad"]
    mf._reported.clear()
    monkeypatch.setattr(mf, "_private_group", lambda gid, uid: False)
    assert mf.extra_policy_roots() == []
    assert "which has other members" in capsys.readouterr().err


def test_a_sticky_directory_above_the_root_is_allowed(roots, monkeypatch, tmp_path):
    """/tmp is writable by everyone but sticky: no one else can rename or replace the root."""
    a = roots.a
    sticky = a.parent
    sticky.chmod(0o1777)
    _set(monkeypatch, f"agentcad={a}")
    try:
        assert [r.name for r in mf.extra_policy_roots()] == ["agentcad"]
    finally:
        sticky.chmod(0o755)


def test_a_non_sticky_directory_above_the_root_writable_by_all_is_refused(roots, monkeypatch, capsys):
    a = roots.a
    a.parent.chmod(0o777)
    _set(monkeypatch, f"agentcad={a}")
    try:
        assert mf.extra_policy_roots() == []
        assert f"{a.parent} is writable by every account" in capsys.readouterr().err
    finally:
        a.parent.chmod(0o755)


def test_a_symlink_out_of_the_root_into_an_open_directory_refuses_the_root(roots, monkeypatch, tmp_path, capsys):
    """The swap through a link (#592 review): the link's target is this user's and not
    writable, but its directory is open and not sticky, so any account could unlink the
    target and put its own file there. A root's policies are the files in the root."""
    open_dir = tmp_path / "open"
    open_dir.mkdir()
    target = open_dir / "target.md"
    target.write_text("# a policy kept elsewhere\n")
    target.chmod(0o644)
    open_dir.chmod(0o777)
    a = roots.a
    (a / "linked.md").symlink_to(target)
    _set(monkeypatch, f"agentcad={a}")
    try:
        assert mf.extra_policy_roots() == []
        assert mf.find_policy_file("agentcad-usage") is None
        err = capsys.readouterr().err
        assert "policy root 'agentcad' skipped" in err
        assert f"{a / 'linked.md'} is a symlink to {target.resolve()}, outside the root" in err
    finally:
        open_dir.chmod(0o755)


def test_a_symlink_that_stays_inside_the_root_is_allowed(roots, monkeypatch):
    a = roots.a
    (a / "alias.md").symlink_to(a / "cad" / "agentcad-export.md")
    _set(monkeypatch, f"agentcad={a}")
    assert [r.name for r in mf.extra_policy_roots()] == ["agentcad"]


def test_a_group_is_asked_about_once_per_walk(roots, monkeypatch):
    """Accounts from a directory service can make each getpwall slow: one answer per gid."""
    a = roots.a
    for p in (a, a / "cad", a / "agentcad-usage.md", a / "cad" / "agentcad-export.md"):
        p.chmod(p.stat().st_mode | 0o020)
    asked = []
    monkeypatch.setattr(mf, "_private_group", lambda gid, uid: asked.append(gid) or True)
    _set(monkeypatch, f"agentcad={a}")
    assert [r.name for r in mf.extra_policy_roots()] == ["agentcad"]
    assert len(asked) == len(set(asked)) == 1, asked


# --- the agent's own root: personal policies, with no configuration ------------------------------


def _personal(home_name="merging"):
    """A policy in this test's agent home, the place every agent's own policies live."""
    root = mf.find_agent_home() / "agent" / "policies" / "personal"
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{home_name}.md").write_text("# Mine\n")
    return root


def test_an_agents_own_policies_are_a_root_with_no_configuration(roots):
    root = _personal()
    assert [r.name for r in mf.policy_roots()] == ["framework", "personal"]
    assert mf.find_policy_file("personal:merging") == root / "merging.md"
    assert mf.find_policy_file("merging") == root / "merging.md"
    assert {p["name"]: p["root"] for p in mf.list_policy_files()}["merging"] == "personal"


def test_no_policies_means_no_root_and_no_noise(roots, capsys):
    assert [r.name for r in mf.policy_roots()] == ["framework"]    # no directory
    root = mf.find_agent_home() / "agent" / "policies" / "personal"
    root.mkdir(parents=True)
    (root / "manifest.json").write_text("{}")
    (root / "README.md").write_text("# The template provisioning installs\n")
    root.chmod(0o777)              # unsafe, and it doesn't matter: nothing here to read
    assert [r.name for r in mf.policy_roots()] == ["framework"]
    root.chmod(0o755)
    assert capsys.readouterr().err == ""


def test_an_unsafe_personal_root_is_refused_once_saying_why(roots, capsys):
    root = _personal()
    root.chmod(0o777)
    try:
        assert [r.name for r in mf.policy_roots()] == ["framework"]
        mf.policy_roots()
        err = capsys.readouterr().err
        assert err.count("personal policy root skipped") == 1 and "writable by every account" in err
        assert mf.find_policy_file("personal:merging") is None
    finally:
        root.chmod(0o755)


def test_the_framework_keeps_a_name_and_the_prefix_reaches_the_agents_copy(roots):
    root = _personal("task_management")
    fw = roots.fw
    assert mf.find_policy_file("task_management") == fw / "base" / "development" / "task_management.md"
    assert mf.find_policy_file("personal:task_management") == root / "task_management.md"


def test_an_explicit_root_takes_the_place_of_the_default(roots, monkeypatch):
    root = _personal()
    a = roots.a
    _set(monkeypatch, f"mine={root}")          # the same directory, renamed: not listed twice
    assert [r.name for r in mf.policy_roots()] == ["framework", "mine"]
    assert mf.find_policy_file("merging") == root / "merging.md"       # and never ambiguous with itself
    _set(monkeypatch, f"personal={a}")         # the name, elsewhere: the operator's word wins
    assert [(r.name, r.path) for r in mf.policy_roots()] == [("framework", roots.fw), ("personal", a)]


def test_the_cli_lists_and_reads_the_agents_own_root(roots, tmp_path):
    root = _personal()
    src = Path(mf.__file__).resolve().parents[2]
    env = dict(os.environ, PYTHONPATH=str(src), MACF_EVENTS_LOG_PATH=str(tmp_path / "events.jsonl"),
               MACEFF_AGENT_HOME_DIR=str(mf.find_agent_home()))
    env.pop(mf.POLICY_ROOTS_ENV, None)
    run = lambda *argv: subprocess.run([sys.executable, "-m", "macf.cli", *argv],
                                       capture_output=True, text=True, env=env, timeout=120)
    listed = run("policy", "list")
    assert listed.returncode == 0, listed.stderr
    assert f"root personal: {root}" in listed.stdout and "this agent's home" in listed.stdout
    read = run("policy", "read", "personal:merging")
    assert read.returncode == 0, read.stderr
    assert "Mine" in read.stdout


# --- search and the index reach every root, and only this agent's ----------------------------------


def test_search_finds_a_word_in_any_root_and_names_it_so_it_can_be_pasted(roots, monkeypatch):
    a = roots.a
    (a / "agentcad-usage.md").write_text("# agentcad usage\nPin the head: Match-Head-Commit\n")
    _set(monkeypatch, f"agentcad={a}")
    (roots.fw / "base" / "development" / "task_management.md").write_text("no such word\n")
    matches = mf.policy_content_matches("match-head-commit")
    assert [m["name"] for m in matches] == ["agentcad:agentcad-usage"]
    assert matches[0]["count"] == 1 and "Pin the head" in matches[0]["line"]
    assert mf.find_policy_file(matches[0]["name"]) == a / "agentcad-usage.md"


def test_search_ranks_by_mentions_and_finds_framework_words_too(roots):
    root = _personal()
    (root / "merging.md").write_text("pin\npin\n")
    (roots.fw / "base" / "development" / "task_management.md").write_text("pin\n")
    assert [m["name"] for m in mf.policy_content_matches("pin")] == ["personal:merging", "task_management"]


def test_another_agents_policies_are_not_searched_or_found(roots, tmp_path):
    """Search reads this agent's roots. Another agent's home is not one of them."""
    _personal()
    other = tmp_path / "other_agent" / "agent" / "policies" / "personal"
    other.mkdir(parents=True)
    (other / "secret.md").write_text("# the other agents rule: zebra\n")
    assert mf.policy_content_matches("zebra") == []
    assert mf.find_policy_file("secret") is None
    assert mf.find_policy_file("personal:secret") is None


def test_policies_newer_than_the_index_are_named(roots, tmp_path):
    root = _personal()
    db = tmp_path / "index.lance"
    assert mf.policies_newer_than_index(db) == []          # no index: not this function's report
    (db / "documents.lance").mkdir(parents=True)
    built = (db / "documents.lance").stat().st_mtime
    for f in [root / "merging.md", roots.fw / "base" / "development" / "task_management.md"]:
        os.utime(f, (built - 10, built - 10))
    assert mf.policies_newer_than_index(db) == []
    os.utime(root / "merging.md", (built + 10, built + 10))
    assert mf.policies_newer_than_index(db) == ["personal:merging"]


def test_the_index_names_each_policy_by_its_root_and_holds_only_this_agents(roots):
    pytest.importorskip("lancedb")
    pytest.importorskip("sentence_transformers")
    from macf.hybrid_search.policy_indexer import PolicyIndexer
    root = _personal()
    (root / "task_management.md").write_text("# My own task rules\n")
    indexer = PolicyIndexer()
    names = [d["policy_name"] for d in indexer.collect_documents(roots.fw, [("personal", root)])]
    assert sorted(names) == ["personal:merging", "personal:task_management", "task_management"]
    assert all("content" in d for d in indexer.collect_documents(roots.fw, [("personal", root)]))
    assert [d["policy_name"] for d in indexer.collect_documents(roots.fw)] == ["task_management"]


def test_the_cli_search_prints_who_says_it(roots, capsys):
    from argparse import Namespace
    from macf import cli
    root = _personal()
    (root / "merging.md").write_text("Pin it with match-head-commit\n")
    assert cli.cmd_policy_search(Namespace(keyword="match-head-commit")) == 0
    out = capsys.readouterr().out
    assert "personal:merging (1): Pin it with match-head-commit" in out
    assert "No matches found" not in out


def test_recommend_says_when_the_index_is_older_than_a_policy(roots, monkeypatch, capsys):
    from argparse import Namespace
    from macf import cli
    from macf import search_service
    root = _personal()
    db = mf.find_agent_home() / ".maceff" / "policy_index.lance"
    (db / "documents.lance").mkdir(parents=True)
    built = (db / "documents.lance").stat().st_mtime
    os.utime(roots.fw / "base" / "development" / "task_management.md", (built - 10, built - 10))
    os.utime(root / "merging.md", (built + 10, built + 10))
    monkeypatch.setattr("macf.search_service.client.query_search_service",
                        lambda *a, **k: {"formatted": "ok", "explanations": []})
    cli.cmd_policy_recommend(Namespace(query="about to merge a pull request", limit=5, explain=False, json_output=False))
    err = capsys.readouterr().err
    assert "personal:merging" in err and "macf_tools policy build_index" in err


def test_build_index_passes_this_agents_roots_unless_a_directory_is_named(roots, monkeypatch, tmp_path):
    pytest.importorskip("lancedb")
    pytest.importorskip("sentence_transformers")
    import importlib
    from argparse import Namespace
    from macf import cli
    # By name, as cli's own imports resolve them: other tests clear sys.modules, so what this
    # file imported at the top may no longer be the module the command will see.
    hybrid_search = importlib.import_module("macf.hybrid_search")
    live = importlib.import_module("macf.utils.manifest")
    monkeypatch.setattr(live, "get_framework_policies_path", lambda maceff_root=None: roots.fw)
    root = _personal()
    seen = []

    class Fake:
        def __init__(self, manifest_path=None):
            pass

        def build_index(self, policies_dir, db_path, extra_roots=()):
            seen.append(list(extra_roots))
            return {}

    monkeypatch.setattr(hybrid_search, "PolicyIndexer", Fake)
    db = str(tmp_path / "x.lance")
    cli.cmd_policy_build_index(Namespace(policies_dir=None, db_path=db, json_output=True))
    cli.cmd_policy_build_index(Namespace(policies_dir=str(roots.fw), db_path=db, json_output=True))
    assert seen == [[("personal", root)], []]


def test_a_real_index_holds_both_tables_named_by_root(roots, tmp_path):
    pytest.importorskip("lancedb")
    pytest.importorskip("sentence_transformers")
    import lancedb
    from macf.hybrid_search.policy_indexer import PolicyIndexer
    root = _personal()
    (root / "merging.md").write_text(
        "# Merging\n\n## CEP Navigation Guide\n\n**1 Authority**\n- May I merge this?\n\n"
        "=== CEP_NAV_BOUNDARY ===\n\n## 1 Authority\n\nYes.\n")
    db_path = tmp_path / "index.lance"
    PolicyIndexer().build_index(roots.fw, db_path, extra_roots=[("personal", root)])
    db = lancedb.connect(str(db_path))
    docs = db.open_table("documents").to_arrow().column("policy_name").to_pylist()
    questions = db.open_table("questions").to_arrow().column("policy_name").to_pylist()
    assert "personal:merging" in docs and "task_management" in docs
    assert set(questions) == {"personal:merging"}
