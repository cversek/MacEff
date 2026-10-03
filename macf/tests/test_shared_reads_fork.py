"""A process forked inside shared_event_reads leaves the context (#492).

The transcript monitor is forked from the SessionStart hook, which runs inside
shared_event_reads, and never returns through the wrapper that clears it. It
stayed in the context for its whole life and kept a window of parsed events, and
often an open reader, for every read after another process wrote to the log:
5 GB resident and about 800 descriptors on the log after three days.

These tests fork for real and report from the child through a pipe.
"""
import json
import os
import time

import pytest

import macf.agent_events_log as ael
from macf.agent_events_log import read_events, shared_event_reads

pytestmark = pytest.mark.skipif(not hasattr(os, "fork") or not os.path.isdir("/proc/self/fd"),
                                reason="needs fork and /proc")


def _seed(log, n=500):
    with open(log, "w") as f:
        for i in range(n):
            f.write(json.dumps({"timestamp": time.time(), "event": "seed",
                                "data": {"i": i, "pad": "x" * 200}}) + "\n")


def _other_process_appends(log, k):
    with open(log, "a") as f:
        f.write(json.dumps({"timestamp": time.time(), "event": "other", "data": {"k": k}}) + "\n")


def _deep():
    for _ in read_events(scope="all"):
        pass


def _shallow():
    next(read_events(scope="all"), None)


def _fds_on(path):
    n = 0
    for fd in os.listdir("/proc/self/fd"):
        try:
            if os.readlink(f"/proc/self/fd/{fd}") == str(path):
                n += 1
        except OSError:
            continue
    return n


def _in_child(report):
    """Fork; run ``report`` in the child and return its dict to the parent."""
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:  # child
        os.close(r)
        try:
            out = report()
        except BaseException as e:  # report every failure, then leave without running the parent's cleanup
            out = {"error": f"{type(e).__name__}: {e}"}
        os.write(w, json.dumps(out).encode())
        os._exit(0)
    os.close(w)
    data = b""
    while chunk := os.read(r, 65536):
        data += chunk
    os.close(r)
    os.waitpid(pid, 0)
    return json.loads(data)


def test_a_child_forked_inside_the_context_is_outside_it(isolated_events_log):
    _seed(isolated_events_log)

    def parent():
        for k in range(5):
            _other_process_appends(isolated_events_log, k)
            _shallow()
        before = len(ael._shared.windows)
        child = _in_child(lambda: {
            "active": bool(getattr(ael._shared, "active", False)),
            "windows": len(getattr(ael._shared, "windows", None) or []),
            "fds": _fds_on(isolated_events_log),
        })
        return {"before": before, "child": child, "after": len(ael._shared.windows),
                "parent_fds": _fds_on(isolated_events_log)}

    got = shared_event_reads(parent)()
    assert got["before"] == 5 and got["parent_fds"] >= 1   # the parent held windows and open readers
    assert got["child"] == {"active": False, "windows": 0, "fds": 0}
    assert got["after"] == got["before"]                    # the parent's context is untouched


def test_a_child_that_keeps_reading_does_not_grow(isolated_events_log):
    """The monitor's pattern: another process writes, then this one reads, over and over."""
    _seed(isolated_events_log)

    def child_loop():
        for k in range(100):
            _other_process_appends(isolated_events_log, k)
            _deep()
            _shallow()
        return {"windows": len(getattr(ael._shared, "windows", None) or []),
                "fds": _fds_on(isolated_events_log)}

    child = shared_event_reads(lambda: _in_child(child_loop))()
    assert child == {"windows": 0, "fds": 0}


def test_reads_in_the_child_still_see_every_event(isolated_events_log):
    _seed(isolated_events_log, n=50)

    def count():
        _other_process_appends(isolated_events_log, 0)
        return {"n": sum(1 for _ in read_events(scope="all"))}

    child = shared_event_reads(lambda: (_shallow(), _in_child(count))[1])()
    assert child == {"n": 51}


def test_a_read_in_progress_at_the_fork_does_not_hold_the_log_open_in_the_child(isolated_events_log):
    """A reader suspended mid-iteration keeps its window alive in the child's copied
    stack, so dropping the window list frees nothing there; the reader must be closed."""
    _seed(isolated_events_log)

    def parent():
        _other_process_appends(isolated_events_log, 0)
        reading = read_events(scope="all")
        next(reading)  # suspended mid-read: the window and its open reader stay referenced
        child = _in_child(lambda: {"fds": _fds_on(isolated_events_log)})
        reading.close()
        return child

    assert shared_event_reads(parent)() == {"fds": 0}
