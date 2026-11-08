"""A program that isn't MacEff code, declared as a unit through its own heartbeat file (#934)."""
import os
import sys
import time

import pytest

from macf.pd import watched_unit as wu
from macf.pd.broker_unit import run


def test_a_file_is_fresh_only_within_the_bound(tmp_path):
    f = tmp_path / "beat"
    assert wu.fresh(f, 60) is False, "a missing file is never fresh"
    f.write_text("")
    os.utime(f, (1000.0, 1000.0))
    assert wu.fresh(f, 60, now=lambda: 1059.0) is True
    assert wu.fresh(f, 60, now=lambda: 1061.0) is False


def test_a_stale_heartbeat_file_stops_the_beats(tmp_path):
    """The program runs on but stops touching its file: the wrapper stops beating, so the
    daemon sees the unit go overdue while the process still exists."""
    f = tmp_path / "beat"
    child = [sys.executable, "-c",
             "import pathlib, sys, time\n"
             "p = pathlib.Path(sys.argv[1])\n"
             "end = time.time() + 0.5\n"
             "while time.time() < end:\n"
             "    p.touch(); time.sleep(0.05)\n"
             "time.sleep(1.5)\n"
             "sys.exit(5)\n", str(f)]
    ticks = []
    started = time.monotonic()
    code = run(child, 0, lambda: ticks.append(time.monotonic() - started), poll_s=0.05,
               probe=lambda _port: wu.fresh(f, 0.2))
    assert code == 5, "the wrapper ends with the program's own status"
    assert ticks, "while the file was being touched, the unit beat"
    assert max(ticks) < 0.5 + 0.2 + 0.4, f"beats went on after the file went stale: {ticks}"


class _Beat:
    interval_s = 0.2

    def __init__(self):
        self.ticks = 0
        self.stopped = False

    def tick(self):
        self.ticks += 1

    def stop(self):
        self.stopped = True


def test_the_wrapper_runs_the_program_after_the_separator_and_records_it(tmp_path, monkeypatch):
    import macf.pd.liveness as liveness
    beat = _Beat()
    monkeypatch.setattr(liveness, "heartbeat_from_env", lambda: beat)
    f = tmp_path / "beat"
    code = wu.main(["--fresh", str(f), "--within", "30", "--",
                    sys.executable, "-c", "import sys; sys.exit(3)"])
    assert code == 3
    assert beat.stopped
    recorded = wu.pidfile_for(f).read_text().split()
    assert len(recorded) >= 2 and recorded[0].isdigit(), "the child is recorded for the next wrapper"


@pytest.mark.parametrize("argv", [
    ["--fresh", "x", "--within", "30"],
    ["--fresh", "x", "--within", "30", "--"],
    ["--fresh", "x", "--within", "0", "--", "true"],
])
def test_a_wrapper_with_no_program_or_no_bound_is_refused(argv):
    with pytest.raises(SystemExit) as refused:
        wu.main(argv)
    assert refused.value.code == 2
