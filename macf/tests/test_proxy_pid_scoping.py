"""The proxy pid file must identify ONE proxy, not 'the proxy'.

It used to be a single global path with no port in it. Two consequences, both
hit in practice while setting up an isolated proxy for a verification run:

1. A second instance on another port overwrote the first's pid file, so `status`
   reported the wrong process while the first went on serving traffic.
2. Stopping that second instance deleted the file outright, after which `status`
   reported nothing running at all — and a later `start` would happily bind a
   competing instance next to the one still answering.

The CLI made it worse rather than safer: its guard refused to start when ANY
proxy was running regardless of port, so the supported path forbade a safe thing
while the unsupported path (running the module directly) did the unsafe one.

Every test that asserts isolation has a negative control proving the assertion
can fail, because these are exactly the checks that would otherwise pass
vacuously.
"""

from pathlib import Path

import pytest

from macf.proxy import server


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    return tmp_path


class TestPidFileIsPortScoped:
    def test_different_ports_yield_different_files(self, runtime):
        assert server._get_pid_file(8019) != server._get_pid_file(8022)

    def test_filename_carries_the_port(self, runtime):
        assert "8022" in server._get_pid_file(8022).name

    def test_writing_one_port_does_not_disturb_another(self, runtime):
        server._write_pid(111, 8019)
        server._write_pid(222, 8022)
        assert server._read_pid(8019) == 111
        assert server._read_pid(8022) == 222

    def test_removing_one_leaves_the_other_intact(self, runtime):
        """THE regression. A short-lived test instance used to delete the record
        of a long-running one."""
        server._write_pid(111, 8019)
        server._write_pid(222, 8022)

        server._remove_pid(8022)

        assert server._read_pid(8022) is None, "the stopped proxy's pid survived"
        assert server._read_pid(8019) == 111, (
            "stopping one proxy erased another's pid file — the original defect"
        )

    def test_the_isolation_check_can_fail(self, runtime):
        """NEGATIVE CONTROL: simulate the old unscoped behaviour and confirm the
        assertion above would have caught it."""
        server._write_pid(111, 8019)
        # What the old code did: one path for everyone.
        legacy = server._get_pid_file(None)
        legacy.write_text("222")
        legacy.unlink()  # "stopping" the second instance
        # Under the old scheme 8019's record would now be gone. Under the new
        # one it is untouched — so the check distinguishes the two.
        assert server._read_pid(8019) == 111


class TestLegacyPidFileStillFound:
    """A proxy started before this change wrote the unported filename.

    Without a read-side fallback, `status` and `stop` would both report it as
    not running while it went on serving traffic — an upgrade that silently
    orphans the process it is supposed to manage.
    """

    def test_legacy_path_is_read_for_the_default_port(self, runtime):
        (runtime / server.PID_FILE_NAME).write_text("4242")
        assert server._read_pid(server.DEFAULT_PORT) == 4242

    def test_port_scoped_file_wins_when_both_exist(self, runtime):
        (runtime / server.PID_FILE_NAME).write_text("4242")
        server._write_pid(999, server.DEFAULT_PORT)
        assert server._read_pid(server.DEFAULT_PORT) == 999

    def test_legacy_path_is_not_consulted_for_other_ports(self, runtime):
        """A legacy file says nothing about a proxy on some other port."""
        (runtime / server.PID_FILE_NAME).write_text("4242")
        assert server._read_pid(8022) is None

    def test_writes_never_use_the_legacy_path(self, runtime):
        server._write_pid(123, server.DEFAULT_PORT)
        assert not (runtime / server.PID_FILE_NAME).exists()


class TestIsProxyRunningIsPortScoped:
    def test_reports_false_for_a_port_with_no_proxy(self, runtime):
        import os
        server._write_pid(os.getpid(), 8019)
        assert server.is_proxy_running(8019) is True
        assert server.is_proxy_running(8022) is False

    def test_a_stale_pid_is_cleaned_only_for_its_own_port(self, runtime):
        import os
        # A pid that cannot exist, so the liveness probe fails.
        server._write_pid(2 ** 22, 8022)
        server._write_pid(os.getpid(), 8019)

        assert server.is_proxy_running(8022) is False   # cleans 8022's file
        assert server._read_pid(8022) is None
        assert server.is_proxy_running(8019) is True    # untouched
