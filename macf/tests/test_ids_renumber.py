"""``macf_tools ids renumber``: the one-time move of a running deployment onto its declared ids.

The mapping is derived by name from the live tables (faked here); files are planned from
a real temporary tree owned by the test's own uid, and re-owning goes through a recorder,
since a test is not root."""
import os
from argparse import Namespace

import pytest

from macf.ids import renumber as rn
from macf.ids import renumber_cli
from macf.models.agent_spec import AgentsConfig

ME = os.getuid()
MY_GID = os.getgid()


def config(agents=(("pa_a", 21100), ("pa_b", 21101))):
    return AgentsConfig(ids={"base": 21000}, subagents={}, agents={
        n: {"username": n, "uid": u, "personality": "p.md"} for n, u in agents})


LIVE_USERS = {"admin": 1001, "pa_a": 1002, "pa_b": 1003, "amail_broker": 998, "amail_ingest": 999}
LIVE_GROUPS = {"admin": 1001, "agents_all": 1002, "sa_all": 1003, "policyeditors": 1007,
               "pa_a": 1004, "pa_b": 1005, "amail_broker": 998, "amail_ingest": 999}


def lookups(users=None, groups=None):
    users = LIVE_USERS if users is None else users
    groups = LIVE_GROUPS if groups is None else groups
    return (lambda n: users[n]), (lambda n: groups[n])


# --- deriving the mapping ---------------------------------------------------------------------


def test_every_framework_name_maps_from_its_live_number_to_its_declared_one():
    gp, gg = lookups()
    m = rn.derive(config(), {}, gp, gg)
    assert m.uid == {1001: 21000, 1002: 21100, 1003: 21101, 998: 21998, 999: 21999}
    assert m.gid == {1001: 21000, 1002: 21001, 1003: 21002, 1007: 21003,
                     1004: 21100, 1005: 21101, 998: 21998, 999: 21999}
    assert m.uid_names[1002] == "pa_a" and m.gid_names[1002] == "agents_all"


def test_a_name_absent_from_the_live_tables_has_nothing_to_move():
    users = dict(LIVE_USERS)
    del users["pa_b"]
    gp, gg = lookups(users=users)
    assert 1003 not in rn.derive(config(), {}, gp, gg).uid


def test_a_name_already_at_its_number_is_not_moved():
    users = dict(LIVE_USERS, pa_a=21100)
    gp, gg = lookups(users=users)
    assert 21100 not in rn.derive(config(), {}, gp, gg).uid


def test_two_names_on_one_old_number_are_refused():
    users = dict(LIVE_USERS, pa_b=1002)
    gp, gg = lookups(users=users)
    with pytest.raises(rn.RenumberRefused, match="both hold 1002"):
        rn.derive(config(), {}, gp, gg)


def test_an_old_number_that_is_a_declared_number_is_refused():
    """A half-moved container: files already at 21101 may be pa_b's new ones."""
    users = dict(LIVE_USERS, pa_a=21101, pa_b=1003)
    gp, gg = lookups(users=users)
    with pytest.raises(rn.RenumberRefused, match="another name's declared number"):
        rn.derive(config(), {}, gp, gg)


def test_a_service_is_mapped_and_must_sit_in_the_block():
    users = dict(LIVE_USERS, indexer=997)
    groups = dict(LIVE_GROUPS, indexer=997)
    gp, gg = lookups(users, groups)
    assert rn.derive(config(), {"indexer": 21900}, gp, gg).uid[997] == 21900
    with pytest.raises(rn.RenumberRefused, match="outside the block"):
        rn.derive(config(), {"indexer": 22900}, gp, gg)


def test_a_service_on_an_agent_number_is_refused():
    gp, gg = lookups(dict(LIVE_USERS, indexer=997), dict(LIVE_GROUPS, indexer=997))
    with pytest.raises(rn.RenumberRefused, match="both declared at 21100"):
        rn.derive(config(), {"indexer": 21100}, gp, gg)


# --- planning and applying ----------------------------------------------------------------------


def mine_to(new_uid=21100, new_gid=21001):
    return rn.Mapping(uid={ME: new_uid}, gid={MY_GID: new_gid},
                      uid_names={ME: "pa_a"}, gid_names={MY_GID: "agents_all"})


def tree(tmp_path):
    root = tmp_path / "home"
    (root / "pa_a" / "sub").mkdir(parents=True)
    (root / "pa_a" / "f.txt").write_text("x")
    (root / "pa_a" / "sub" / "g.txt").write_text("y")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("z")
    (root / "pa_a" / "link").symlink_to(outside)
    return root, outside


def test_the_plan_lists_every_entry_on_an_old_number_root_included(tmp_path):
    root, _ = tree(tmp_path)
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda _: False)
    paths = {c[0] for c in p.changes}
    assert {str(root), str(root / "pa_a" / "f.txt"), str(root / "pa_a" / "sub" / "g.txt")} <= paths
    assert all(c[3:] == (21100, 21001) for c in p.changes)


def test_a_symlink_is_re_owned_itself_and_never_followed(tmp_path):
    root, outside = tree(tmp_path)
    paths = {c[0] for c in rn.plan(mine_to(), [str(root)], has_acl=lambda _: False).changes}
    link = str(root / "pa_a" / "link")
    assert link in paths
    assert not any(p.startswith(link + "/") or p.startswith(str(outside)) for p in paths), \
        "a symlink was followed: files outside the root would be re-owned"


def test_nothing_is_planned_when_nothing_holds_an_old_number(tmp_path):
    root, _ = tree(tmp_path)
    assert rn.plan(rn.Mapping(uid={ME + 1: 21100}), [str(root)], has_acl=lambda _: False).changes == []


def test_a_missing_root_is_reported_not_silently_skipped(tmp_path):
    p = rn.plan(mine_to(), [str(tmp_path / "nope")], has_acl=lambda _: False)
    assert p.missing_roots == [str(tmp_path / "nope")]


def test_files_with_an_access_list_are_named(tmp_path):
    root, _ = tree(tmp_path)
    target = str(root / "pa_a" / "f.txt")
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda path: path == target)
    assert p.acl_files == [target]
    assert "access list" in rn.render(mine_to(), p, [])


def test_apply_re_owns_each_planned_path_to_its_new_numbers(tmp_path):
    root, _ = tree(tmp_path)
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda _: False)
    done = []
    assert rn.apply(p, chown=lambda path, u, g: done.append((path, u, g))) == (len(p.changes), [])
    assert done == [(c[0], c[3], c[4]) for c in p.changes]


def test_a_bind_mount_root_carries_the_host_account_warning(tmp_path):
    root, _ = tree(tmp_path)
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda _: False)
    text = rn.render(mine_to(), p, [str(root)])
    assert "BIND MOUNT" in text and "host account" in text


def test_render_says_when_there_is_nothing_to_move():
    assert "nothing to move" in rn.render(rn.Mapping(), rn.Plan(), [])


# --- the command line ---------------------------------------------------------------------------


def args(tmp_path, **kw):
    cfg = tmp_path / "agents.yaml"
    cfg.write_text("ids: {base: 21000}\nsubagents: {}\nagents:\n"
                   "  a: {username: pa_no_such_account, uid: 21100, personality: p.md}\n")
    base = dict(config=str(cfg), service=[], root=[], listing=None, apply=False)
    base.update(kw)
    return Namespace(**base)


def test_the_command_plans_by_default_and_changes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(rn, "FRAMEWORK_ROOTS", ())
    assert renumber_cli.cmd_ids_renumber(args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "planned only; nothing changed" in out


def test_apply_without_root_is_refused(tmp_path, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip("running as root")
    monkeypatch.setattr(rn, "FRAMEWORK_ROOTS", ())
    assert renumber_cli.cmd_ids_renumber(args(tmp_path, apply=True)) == 2


def test_a_malformed_service_is_refused(tmp_path):
    assert renumber_cli.cmd_ids_renumber(args(tmp_path, service=["indexer"])) == 2


def test_an_unreadable_declaration_is_refused(tmp_path):
    assert renumber_cli.cmd_ids_renumber(args(tmp_path, config=str(tmp_path / "missing.yaml"))) == 2


# --- what the move leaves behind (review of #697) ------------------------------------------

BLOCK = range(21000, 22000)


def test_files_left_on_a_number_nothing_maps_are_named(tmp_path):
    """The base image's ubuntu account maps to nothing, so files it owned are neither moved nor
    planned; after the recreate they belong to the host's holder of that number. Here the
    group is the unmapped number: the uid moves, the gid stays outside the block."""
    root, _ = tree(tmp_path)
    m = rn.Mapping(uid={ME: 21100}, uid_names={ME: "pa_a"})
    p = rn.plan(m, [str(root)], has_acl=lambda _: False, block=BLOCK)
    named = {path for path, _u, g in p.unmapped if g == MY_GID}
    assert str(root / "pa_a" / "f.txt") in named
    text = rn.render(m, p, [])
    assert "files left outside the block" in text and str(MY_GID) in text


def test_a_full_mapping_leaves_nothing_outside_the_block(tmp_path):
    root, _ = tree(tmp_path)
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda _: False, block=BLOCK)
    assert p.unmapped == []
    assert "outside the block" not in rn.render(mine_to(), p, [])


def test_root_owned_files_are_not_unmapped(tmp_path):
    """Root's own files are root's in every container and on the host: nothing to name."""
    root, _ = tree(tmp_path)
    m = rn.Mapping(uid={ME: 0}, gid={MY_GID: 0})
    assert rn.plan(m, [str(root)], has_acl=lambda _: False, block=BLOCK).unmapped == []


def test_setuid_and_setgid_files_to_re_own_are_named(tmp_path):
    """chown clears both bits on a regular file, even as root on Linux."""
    root, _ = tree(tmp_path)
    tool = root / "pa_a" / "tool"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o4755)
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda _: False, block=BLOCK)
    assert p.setid_files == [str(tool)]
    assert "setuid or setgid" in rn.render(mine_to(), p, [])


def test_setgid_on_a_file_nobody_can_execute_is_not_named(tmp_path):
    """Mode 2664, common on files under a shared group directory: the bit changes nothing, so
    the plan doesn't list thousands of them (measured on a seat container: 7,685, every one 2664)."""
    root, _ = tree(tmp_path)
    notes = root / "pa_a" / "notes.csv"
    notes.write_text("a,b\n")
    notes.chmod(0o2664)
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda _: False, block=BLOCK)
    assert str(notes) not in p.setid_files


def test_a_path_that_cannot_be_re_owned_is_recorded_and_the_rest_still_move(tmp_path):
    """One failure mid-move never leaves a traceback and a half-moved tree: the rest go, and the
    failure is named, so a rerun can finish it."""
    root, _ = tree(tmp_path)
    p = rn.plan(mine_to(), [str(root)], has_acl=lambda _: False)
    bad = p.changes[1][0]
    done = []

    def chown(path, u, g):
        if path == bad:
            raise PermissionError(1, "Operation not permitted")
        done.append(path)
    changed, failed = rn.apply(p, chown=chown)
    assert changed == len(p.changes) - 1 and len(done) == changed
    assert failed == [(bad, "Operation not permitted")]


def test_processes_still_running_as_a_moved_number_are_found(tmp_path):
    """--apply refuses while the amail services or an admin login still run as an old number."""
    proc = tmp_path / "proc"
    for pid, uid, comm in ((10, 998, "broker"), (11, 5000, "other"), (12, 1002, "bash")):
        (proc / str(pid)).mkdir(parents=True)
        (proc / str(pid) / "status").write_text(f"Name:\t{comm}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        (proc / str(pid) / "comm").write_text(comm + "\n")
    (proc / "self").mkdir()
    found = sorted(rn.processes_on({998, 1002}, proc=proc))
    assert found == [(10, 998, "broker"), (12, 1002, "bash")]

