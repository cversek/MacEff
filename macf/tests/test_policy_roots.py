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


def test_a_symlink_out_of_the_root_is_never_read_and_the_rest_of_the_root_is(roots, monkeypatch, tmp_path, capsys):
    """The swap through a link (#592 review): the link's target is this user's and not
    writable, but its directory is open and not sticky, so any account could unlink the
    target and put its own file there. A root's policies are the files in the root. That
    reason covers the linked file, so it is the file that's refused, by every way of reading."""
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
        assert [r.name for r in mf.extra_policy_roots()] == ["agentcad"]
        assert mf.find_policy_file("agentcad-usage") is not None
        assert mf.find_policy_file("linked") is None
        assert mf.find_policy_file("agentcad:linked") is None
        assert not [p for p in mf.list_policy_files() if p.get("name") == "linked"]
        err = capsys.readouterr().err
        assert f"policy {a / 'linked.md'} skipped: a symlink to {target.resolve()}" in err
        assert "policy root 'agentcad' skipped" not in err
    finally:
        open_dir.chmod(0o755)


def test_search_and_the_index_leave_out_a_symlink_out_of_the_root(roots, monkeypatch, tmp_path):
    """The reach this branch adds must not read what the root refuses: the linked text is
    someone else's to change, and search and recommend would put it in front of the agent."""
    from macf.hybrid_search.policy_indexer import PolicyIndexer
    target = tmp_path / "elsewhere.md"
    target.write_text("# kept elsewhere\nquokkaword\n")
    (roots.a / "linked.md").symlink_to(target)
    _set(monkeypatch, f"agentcad={roots.a}")
    assert mf.policy_content_matches("quokkaword") == []
    indexer = PolicyIndexer.__new__(PolicyIndexer)
    indexer.extractor = type("All", (), {"should_index": staticmethod(lambda p: True)})()
    names = [n for _, n in indexer._sources(tmp_path / "no_framework", [("agentcad", roots.a)])]
    assert "agentcad:linked" not in names and names, names


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


# --- an agent declares its own triggers ------------------------------------------------------------


def _declare(root, *entries):
    import json
    (root / "manifest.json").write_text(json.dumps({"personal_policies": list(entries)}))


def test_a_manifest_in_another_shape_is_reported_naming_what_it_found(roots, capsys):
    """Read as empty it would look exactly like an agent that declared nothing."""
    import json
    root = _personal()
    (root / "manifest.json").write_text(json.dumps({"version": "1", "policies": [{"file": "merging.md"}]}))
    assert mf.personal_task_policies("TASK") == []
    err = capsys.readouterr().err
    assert "declares no triggers" in err and "policies" in err and "task_types" in err


def test_a_manifest_of_metadata_alone_is_quiet(roots, capsys):
    import json
    (_personal() / "manifest.json").write_text(json.dumps({"version": "1", "description": "mine"}))
    assert mf.personal_task_policies("TASK") == []
    assert "MACF" not in capsys.readouterr().err


def test_an_older_template_entry_declares_no_trigger_and_is_quiet_at_task_start(roots, capsys):
    """It would otherwise report on every task start, since each CLI call is a new process."""
    _declare(_personal(), {"path": "merging.md", "CEP_triggers": ["merge"]},
             {"name": "merging", "task_types": ["TASK"]})
    assert mf.personal_task_policies("TASK") == ["personal:merging"]
    assert "MACF" not in capsys.readouterr().err


def test_a_manifest_linked_out_of_the_root_declares_nothing(roots, tmp_path, capsys):
    """A manifest says what gets surfaced, and whoever can write the target could change that."""
    import json
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps({"personal_policies": [{"name": "merging", "task_types": ["TASK"]}]}))
    (_personal() / "manifest.json").symlink_to(elsewhere)
    assert mf.personal_task_policies("TASK") == []
    assert "symlink out of its root" in capsys.readouterr().err


def test_the_whole_tree_check_survives_a_file_it_cannot_read(roots, monkeypatch):
    """One unreadable file must not end the check, or the rest of the report goes with it."""
    from pathlib import Path
    root = _personal()
    bad = root / "merging.md"
    real = Path.read_text
    def read_text(self, *a, **k):
        if self == bad:
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", read_text)
    results = mf.check_policies()
    assert any("cannot be read" in f for f in results["personal:merging"])
    assert len(results) > 1


def test_the_check_says_once_what_an_older_manifest_entry_lacks(roots):
    _declare(_personal(), {"path": "merging.md", "CEP_triggers": ["merge"]},
             {"name": "merging", "task_types": ["TASK"]})
    found = mf.check_policies()["personal:manifest.json"]
    assert len(found) == 1 and "declares no trigger" in found[0] and "CEP_triggers" in found[0]


def _manifest(mapping):
    return {"task_type_policies": {"mappings": mapping}}


def test_a_declared_policy_surfaces_after_the_frameworks_for_its_task_type(roots):
    root = _personal()
    _declare(root, {"name": "merging", "task_types": ["GH_PR", "TASK"]})
    assert mf.get_policies_for_task_type("TASK", _manifest({"TASK": ["task_management"]})) == [
        "task_management", "personal:merging"]
    assert mf.get_policies_for_task_type("GH_PR", _manifest({})) == ["personal:merging"]  # no framework mapping
    assert mf.get_policies_for_task_type("BUG", _manifest({"BUG": ["x"]})) == ["x"]
    assert mf.find_policy_file("personal:merging") == root / "merging.md"


def test_a_bad_declaration_is_reported_not_dropped(roots, capsys):
    root = _personal()
    _declare(root, {"name": "not_here", "task_types": ["TASK"]}, {"task_types": ["TASK"]}, "nonsense",
             {"name": "merging", "task_types": ["TASK"]})
    assert mf.personal_task_policies("TASK") == ["personal:merging"]
    err = capsys.readouterr().err
    assert "declares 'not_here'" in err and "needs a name" in err and "nonsense" in err


def test_a_broken_manifest_is_reported_and_surfaces_nothing(roots, capsys):
    root = _personal()
    (root / "manifest.json").write_text("{ not json")
    assert mf.personal_task_policies("TASK") == []
    assert "can't be used" in capsys.readouterr().err
    mf._reported.clear()
    (root / "manifest.json").write_text('{"personal_policies": 5}')
    assert mf.personal_task_policies("TASK") == []
    assert "not a list" in capsys.readouterr().err


def test_no_manifest_or_no_root_surfaces_nothing_quietly(roots, capsys):
    assert mf.personal_task_policies("TASK") == []     # no root
    _personal()
    assert mf.personal_task_policies("TASK") == []     # a root, no manifest
    assert capsys.readouterr().err == ""


def test_a_manifest_others_can_write_refuses_the_root(roots, capsys):
    root = _personal()
    _declare(root, {"name": "merging", "task_types": ["TASK"]})
    (root / "manifest.json").chmod(0o666)
    try:
        assert mf.personal_task_policies("TASK") == []
        assert "writable by every account" in capsys.readouterr().err
    finally:
        (root / "manifest.json").chmod(0o644)


def test_a_renamed_root_keeps_its_triggers_under_its_name(roots, monkeypatch):
    root = _personal()
    _declare(root, {"name": "merging", "task_types": ["TASK"]})
    _set(monkeypatch, f"mine={root}")
    assert mf.personal_task_policies("TASK") == ["mine:merging"]


def test_task_start_surfaces_a_declared_policy_once_a_cycle(roots):
    """The real cmd_task_start, as test_task_start_stale_resume drives it: the activation event is
    what the hook delivers from, so seeing it is seeing the trigger fire."""
    import argparse
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch
    from macf.cli import cmd_task_start
    root = _personal()
    _declare(root, {"name": "merging", "task_types": ["TASK"]})
    crumb = "s_abc12345/c_25/p_def67890/t_2000"
    task = MagicMock(status="pending")
    task.mtmd = SimpleNamespace(updates=[], started_breadcrumb=None, creation_breadcrumb=crumb,
                                task_type="TASK", plan_ca_ref=None)
    task.description_with_updated_mtmd.return_value = "<!-- updated -->"
    reader = MagicMock(session_path="/tmp/session")
    reader.read_task.return_value = task

    def activated(already):
        with patch("macf.task.TaskReader", return_value=reader), patch("macf.task.update_task_file"), \
             patch("macf.task.reader.unhide_task_file"), patch("macf.cli.append_event") as event, \
             patch("macf.utils.breadcrumbs.get_breadcrumb", return_value=crumb), \
             patch("macf.event_queries.get_policies_surfaced_this_cycle", return_value=already):
            assert cmd_task_start(argparse.Namespace(task_id="10")) == 0
        return [c.args[1]["policy_name"] for c in event.call_args_list if c.args[0] == "policy_injection_activated"]

    assert "personal:merging" in activated({})
    assert "personal:merging" not in activated({"personal:merging": "9"})


# --- the format check ------------------------------------------------------------------------------

GOOD_POLICY = """# Good

**Type**: Personal Policy
**Scope**: One agent
**Status**: ACTIVE

---

## Purpose

Why.

## CEP Navigation Guide

**1 First**
- What?

**1.1 Deeper**
- What else?

=== CEP_NAV_BOUNDARY ===

## 1 First

### 1.1 Deeper

## 2 Integration with Other Policies
"""


def test_a_well_formed_policy_has_no_findings():
    assert mf.policy_format_findings(GOOD_POLICY) == []
    assert mf.policy_format_findings(GOOD_POLICY.replace("## 1 First", "## 1. First")) == []
    plain = GOOD_POLICY.replace("**1 First**", "1 First").replace("**1.1 Deeper**", "1.1 Deeper")
    assert mf.policy_format_findings(plain) == []


@pytest.mark.parametrize("old,new,expected", [
    ("**Type**: Personal Policy\n", "", "no **Type**"),
    ("**Scope**: One agent\n", "", "no **Scope**"),
    ("**Status**: ACTIVE\n", "", "no **Status**"),
    ("=== CEP_NAV_BOUNDARY ===\n", "", "no === CEP_NAV_BOUNDARY"),
    ("## CEP Navigation Guide", "## A Guide", "no CEP Navigation Guide"),
    ("### 1.1 Deeper", "### 1.2 Deeper", "promises 1.1"),
    ("**1 First**\n- What?\n\n**1.1 Deeper**\n- What else?\n", "", "no numbered topics"),
])
def test_each_thing_a_policy_can_lack_is_found(old, new, expected):
    assert old in GOOD_POLICY
    assert any(expected in f for f in mf.policy_format_findings(GOOD_POLICY.replace(old, new)))


def test_check_covers_one_policy_or_every_root_and_skips_the_readme(roots):
    root = _personal()
    (root / "README.md").write_text("# not a policy\n")
    (root / "merging.md").write_text(GOOD_POLICY)
    assert mf.check_policies("personal:merging") == {"personal:merging": []}
    results = mf.check_policies()
    assert set(results) == {"task_management", "personal:merging"}
    assert results["task_management"] and results["personal:merging"] == []
    with pytest.raises(LookupError):
        mf.check_policies("personal:absent")


def test_the_cli_exit_code_says_whether_it_passed(roots, capsys):
    from argparse import Namespace
    from macf import cli
    root = _personal()
    (root / "merging.md").write_text(GOOD_POLICY)
    assert cli.cmd_policy_check(Namespace(policy_name="personal:merging")) == 0
    assert "1 of 1 pass" in capsys.readouterr().out
    (root / "merging.md").write_text("# Bare\n")
    assert cli.cmd_policy_check(Namespace(policy_name="personal:merging")) == 1
    assert "no **Type**" in capsys.readouterr().out
    assert cli.cmd_policy_check(Namespace(policy_name="personal:absent")) == 2
