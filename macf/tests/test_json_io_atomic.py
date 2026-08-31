"""`write_json_safely` — the replace a live reader can survive.

Another process reads these files while this one writes them: a supervisor
reading a heartbeat, a broker reading an authorization file. The properties
below are what make that safe, and each one was absent from the first version.
"""
import json
import os
import stat

import pytest

from macf.utils.json_io import write_json_safely


class TestModeIsPreserved:
    def test_a_0600_file_stays_0600(self, tmp_path):
        """THE SECURITY ONE. os.replace installs the TEMP file's permissions,
        so a helper creating its temp at the default umask silently widens
        every file it rewrites. In this codebase 0600-vs-0644 decides who may
        read a credential, and the widening has no symptom."""
        p = tmp_path / "secret.json"
        p.write_text("{}")
        os.chmod(p, 0o600)
        assert write_json_safely(p, {"a": 1})
        assert stat.S_IMODE(p.stat().st_mode) == 0o600

    def test_an_unusual_mode_is_carried_too(self, tmp_path):
        p = tmp_path / "odd.json"
        p.write_text("{}")
        os.chmod(p, 0o640)
        write_json_safely(p, {"a": 1})
        assert stat.S_IMODE(p.stat().st_mode) == 0o640

    def test_a_new_file_is_created_without_a_prior_mode(self, tmp_path):
        """No previous file means no mode to carry; the umask decides. This is
        distinguished from a failed stat on an existing file, which is real."""
        p = tmp_path / "new.json"
        assert write_json_safely(p, {"a": 1})
        assert json.loads(p.read_text()) == {"a": 1}


class TestTheReplaceIsClean:
    def test_the_content_is_the_new_content(self, tmp_path):
        p = tmp_path / "x.json"
        write_json_safely(p, {"first": True})
        write_json_safely(p, {"second": True})
        assert json.loads(p.read_text()) == {"second": True}

    def test_no_temp_file_is_left_behind(self, tmp_path):
        # Asserts the ABSENCE of temps rather than an exact listing: the shared
        # conftest puts isolation dirs in tmp_path, and a test that breaks when
        # unrelated fixtures add a file is testing the fixtures.
        p = tmp_path / "x.json"
        write_json_safely(p, {"a": 1})
        assert not list(tmp_path.glob("*.tmp"))
        assert not list(tmp_path.glob(".x.json*"))

    def test_the_temp_name_is_not_derived_from_the_target(self, tmp_path):
        """A predictable shared temp name means two writers of one path
        truncate each other's temp and the rename publishes the wreckage —
        reintroducing the tear the temp file exists to prevent. Observed
        indirectly: a second writer must not disturb the first's result."""
        p = tmp_path / "x.json"
        write_json_safely(p, {"a": 1})
        write_json_safely(p, {"a": 2})
        assert json.loads(p.read_text()) == {"a": 2}
        assert not list(tmp_path.glob("*.tmp"))


class TestItFailsWithoutRaising:
    def test_an_unserialisable_value_returns_false(self, tmp_path):
        """Callers branch on the return value; a raise here would take down a
        daemon loop that was only trying to publish liveness."""
        p = tmp_path / "x.json"
        assert write_json_safely(p, {"bad": object()}) is False

    def test_a_failed_write_leaves_no_temp_behind(self, tmp_path):
        p = tmp_path / "x.json"
        write_json_safely(p, {"bad": object()})
        assert not list(tmp_path.glob("*.tmp"))

    def test_an_unwritable_directory_returns_false(self, tmp_path):
        d = tmp_path / "ro"
        d.mkdir()
        os.chmod(d, 0o500)
        try:
            assert write_json_safely(d / "x.json", {"a": 1}) is False
        finally:
            os.chmod(d, 0o700)

    def test_a_failed_write_does_not_destroy_the_previous_file(self, tmp_path):
        """The reason to use a temp at all: a bad write must leave the old
        content intact rather than truncating it on the way to failing."""
        p = tmp_path / "x.json"
        write_json_safely(p, {"good": 1})
        write_json_safely(p, {"bad": object()})
        assert json.loads(p.read_text()) == {"good": 1}
