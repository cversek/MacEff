"""``macf_tools ids audit``: uid and gid numbers held by more than one identity across a host and
its containers. A fake runner stands in for getent and docker, shaped like a measured host."""
import json
import subprocess

import pytest

from macf.ids import audit as ids

HOST_PASSWD = """root:x:0:0:root:/root:/bin/bash
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
systemd-network:x:998:998::/:/usr/sbin/nologin
operator:x:1000:1000::/home/operator:/bin/bash
alice:x:1001:1001::/home/alice:/bin/bash
"""
HOST_GROUP = """root:x:0:
nogroup:x:65534:
operator:x:1000:
alice:x:1001:
"""
SEAT_PASSWD = """root:x:0:0:root:/root:/bin/bash
nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin
amail_broker:x:998:998::/nonexistent:/usr/sbin/nologin
ubuntu:x:1000:1000::/home/ubuntu:/bin/bash
admin:x:1001:1001::/home/admin:/bin/bash
seat_a:x:1002:1004::/home/seat_a:/bin/bash
"""
SEAT_GROUP = """root:x:0:
nogroup:x:65534:
ubuntu:x:1000:
agents_all:x:1002:seat_a
"""


def fake(tables, fail=(), no_getent=()):
    """A runner: *tables* maps (place, kind) to text; *fail* places raise; *no_getent* places
    have no getent but do have /etc files."""
    def run(argv):
        argv = list(argv)
        if argv[:2] == ["docker", "ps"]:
            return "\n".join(sorted({p for p, _ in tables if p != ids.HOST} | set(fail))) + "\n"
        place, rest = (argv[2], argv[3:]) if argv[:2] == ["docker", "exec"] else (ids.HOST, argv)
        if place in fail:
            raise subprocess.CalledProcessError(1, argv, stderr="Error: No such container")
        if rest[0] == "getent":
            if place in no_getent:
                raise subprocess.CalledProcessError(127, argv, stderr="getent: not found")
            return tables[(place, rest[1])]
        if rest[0] == "cat":
            return tables[(place, rest[1].rsplit("/", 1)[1])]
        raise AssertionError(f"unexpected command {argv}")
    return run


def measured():
    return {(ids.HOST, "passwd"): HOST_PASSWD, (ids.HOST, "group"): HOST_GROUP,
            ("seat", "passwd"): SEAT_PASSWD, ("seat", "group"): SEAT_GROUP}


def test_numbers_two_identities_hold_are_named():
    report = ids.audit(run=fake(measured()))
    uids = report.overlaps("passwd")
    assert sorted(uids) == [1000, 1001]
    assert {(h.place, h.name) for h in uids[1000]} == {("host", "operator"), ("seat", "ubuntu")}
    assert sorted(report.overlaps("group")) == [1000]
    assert report.exit_code() == 1
    assert "OVERLAP" in ids.render(report)


def test_a_system_account_shared_by_name_is_not_an_overlap():
    """root 0 and nobody 65534 are the distribution's own accounts in every place."""
    report = ids.audit(run=fake(measured()))
    assert 0 not in report.overlaps("passwd") and 65534 not in report.overlaps("passwd")
    assert 65534 not in report.overlaps("group")


def test_a_shared_name_at_or_above_1000_is_still_two_identities():
    tables = measured()
    tables[("seat", "passwd")] += "alice:x:1001:1001::/home/alice:/bin/bash\n"
    tables[("seat", "passwd")] = tables[("seat", "passwd")].replace("admin:x:1001", "admin:x:1009")
    report = ids.audit(run=fake(tables))
    assert 1001 in report.overlaps("passwd")


def test_a_system_id_under_different_names_is_reported_apart():
    """998 is systemd-network on the host and the mail broker in the container: reported in its
    own section, and not among the overlaps that fail the audit."""
    report = ids.audit(run=fake(measured()))
    assert {h.name for h in report.system_overlaps("passwd")[998]} == {"systemd-network", "amail_broker"}
    assert 998 not in report.overlaps("passwd")
    assert "reported, not counted" in ids.render(report)


def test_system_overlaps_alone_leave_the_audit_clean():
    tables = measured()
    for place_kind in (("seat", "passwd"), ("seat", "group")):
        tables[place_kind] = tables[place_kind].replace(":1000:", ":21000:").replace(
            ":1001:", ":21001:").replace(":1002:", ":21002:")
    report = ids.audit(run=fake(tables))
    assert report.system_overlaps("passwd") and report.exit_code() == 0, ids.render(report)


def test_a_container_that_cannot_be_read_fails_the_audit():
    report = ids.audit(run=fake(measured(), fail=("gone",)))
    assert "gone" in report.unreadable
    assert report.exit_code() == 2
    assert "INCOMPLETE" in ids.render(report)


def test_an_unreadable_place_fails_even_when_the_rest_is_clean():
    tables = {(ids.HOST, "passwd"): HOST_PASSWD, (ids.HOST, "group"): HOST_GROUP}
    report = ids.audit(run=fake(tables, fail=("gone",)))
    assert not report.overlaps("passwd")
    assert report.exit_code() == 2


def test_docker_that_cannot_list_containers_fails_the_audit():
    def run(argv):
        if list(argv)[:2] == ["docker", "ps"]:
            raise FileNotFoundError("docker")
        return fake(measured())(argv)
    report = ids.audit(run=run)
    assert "docker" in report.unreadable and report.exit_code() == 2


def test_a_container_without_getent_is_read_from_its_files():
    report = ids.audit(run=fake(measured(), no_getent=("seat",)))
    assert not report.unreadable
    assert 1000 in report.overlaps("passwd")


def test_an_empty_table_is_unreadable_not_clean():
    tables = measured()
    tables[("seat", "passwd")] = ""
    report = ids.audit(run=fake(tables))
    assert "seat" in report.unreadable and report.exit_code() == 2


def test_clean_when_every_place_is_read_and_nothing_overlaps():
    tables = measured()
    for place_kind in (("seat", "passwd"), ("seat", "group")):
        tables[place_kind] = tables[place_kind].replace(":998:", ":21998:").replace(
            ":1000:", ":21000:").replace(":1001:", ":21001:").replace(":1002:", ":21002:")
    report = ids.audit(run=fake(tables))
    assert report.exit_code() == 0, ids.render(report)
    assert ids.render(report).endswith("CLEAN")


def test_named_containers_are_the_only_ones_read():
    tables = measured()
    tables[("other", "passwd")] = SEAT_PASSWD
    tables[("other", "group")] = SEAT_GROUP
    report = ids.audit(containers=["seat"], run=fake(tables))
    assert report.places == ["host", "seat"]


def test_json_names_overlaps_and_the_exit_code():
    data = json.loads(ids.render_json(ids.audit(run=fake(measured()))))
    assert data["exit_code"] == 1
    assert {o["name"] for o in data["overlaps"]["passwd"]["1000"]} == {"operator", "ubuntu"}
    assert "998" in data["system_overlaps"]["passwd"]


@pytest.mark.parametrize("line", ["", "# comment", "broken", "name:x:notanumber:0"])
def test_lines_that_are_not_entries_are_skipped(line):
    assert ids.parse_table(line + "\nroot:x:0:0::/:/bin/sh\n") == [("root", 0)]
