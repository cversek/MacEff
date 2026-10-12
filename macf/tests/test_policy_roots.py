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
