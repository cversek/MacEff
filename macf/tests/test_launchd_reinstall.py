"""#749: a second install, of the daemon or the tray, neither fails at launchctl bootstrap nor
leaves the old job running. launchd refuses to bootstrap a label it has loaded; the stand-in here
does the same, so each plan is applied twice against one launchd state."""
import subprocess
from pathlib import Path

import pytest

from macf.platform import launchd


class FakeLaunchd:
    """launchctl as launchd answers it: one loaded set, bootstrap refused (5) for a loaded label,
    boot-out of a missing one 3, print 0 when loaded."""

    def __init__(self):
        self.loaded, self.calls = set(), []

    def __call__(self, argv):
        self.calls.append(argv[1])
        verb, target = argv[1], argv[-1]
        label = Path(target).stem if verb == "bootstrap" else target.rsplit("/", 1)[-1]
        code = 0
        if verb == "bootstrap":
            code = 5 if label in self.loaded else 0
            self.loaded.add(label)
        elif verb == "bootout":
            code = 0 if label in self.loaded else launchd.BOOTOUT_NOT_LOADED
            self.loaded.discard(label)
        elif verb == "print":
            code = 0 if label in self.loaded else 113
        return subprocess.CompletedProcess(argv, code, "", "" if code == 0 else f"failed: {code}")


def _pd_plan(tmp_path, reload=False, arg="x"):
    return launchd.install_plan("Tester_abc123", ["/usr/bin/python3", "-m", "macf.pd", arg], str(tmp_path),
                                str(tmp_path / "log"), 501, [], reload=reload)


def _tray_plan(tmp_path, reload=False, arg="x"):
    return launchd.tray_install_plan(["/usr/bin/python3", "-m", "macf.tray", arg], str(tmp_path),
                                     str(tmp_path / "log"), 501, reload=reload)


@pytest.mark.parametrize("plan", [_pd_plan, _tray_plan])
def test_installing_twice_finds_the_job_loaded_and_leaves_it(tmp_path, plan):
    fake = FakeLaunchd()
    launchd.apply_plan(plan(tmp_path), run=fake)
    done = launchd.apply_plan(plan(tmp_path), run=fake)          # the same plist: nothing to replace
    assert any("already loaded" in line for line in done), done
    assert fake.calls.count("bootstrap") == 1 and len(fake.loaded) == 1


@pytest.mark.parametrize("plan", [_pd_plan, _tray_plan])
def test_a_forced_install_replaces_the_loaded_job(tmp_path, plan):
    fake = FakeLaunchd()
    launchd.apply_plan(plan(tmp_path), run=fake)
    launchd.apply_plan(plan(tmp_path, reload=True, arg="y"), run=fake, force=True)
    assert fake.calls.count("bootout") == 1 and fake.calls.count("bootstrap") == 2 and len(fake.loaded) == 1


def test_the_tray_reload_is_boot_out_wait_then_bootstrap(tmp_path):
    steps = _tray_plan(tmp_path, reload=True)
    kinds = [s.what if s.what != "launchctl" else s.argv[1] for s in steps]
    assert kinds == ["write", "bootout", "unloaded", "bootstrap"]
    assert steps[1].not_loaded_ok


@pytest.mark.parametrize("plan", [_pd_plan, _tray_plan])
def test_a_new_plist_on_a_loaded_job_is_not_passed_off_as_installed(tmp_path, plan):
    """CTB on #944: a plist written fresh (the old file gone) while launchd still runs the old
    definition must not report success with the new one never loaded. It fails, naming --force."""
    import os
    fake = FakeLaunchd()
    first = plan(tmp_path)
    launchd.apply_plan(first, run=fake)
    os.unlink(first[0].path)                      # the old plist gone; the old job still loaded
    with pytest.raises(RuntimeError, match="--force"):
        launchd.apply_plan(plan(tmp_path, arg="y"), run=fake)
