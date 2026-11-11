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
    # The judge is exactly one of a file or a probe (#977).
    ["--within", "30", "--", "true"],
    ["--fresh", "x", "--probe", "http://127.0.0.1:1/", "--within", "30", "--pidfile", "p", "--", "true"],
    # A probe has no file to record the child beside, so it names its own.
    ["--probe", "http://127.0.0.1:1/", "--within", "30", "--", "true"],
    # And it never leaves loopback.
    ["--probe", "http://192.0.2.7/", "--within", "30", "--pidfile", "p", "--", "true"],
])
def test_a_wrapper_with_no_program_or_no_bound_is_refused(argv):
    with pytest.raises(SystemExit) as refused:
        wu.main(argv)
    assert refused.value.code == 2


# --- the HTTP probe (#977): a server that writes no heartbeat file -----------------------------

@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/health", "http://[::1]:3000/",
                                 "https://localhost/", "http://127.9.9.9/"])
def test_a_loopback_url_is_accepted(url):
    assert wu.loopback_url(url) == url


@pytest.mark.parametrize("url", ["http://192.0.2.7/", "http://example.org/", "http://10.0.0.1:80/",
                                 "ftp://127.0.0.1/", "http:///nohost"])
def test_a_probe_that_would_leave_loopback_is_refused(url):
    with pytest.raises(ValueError, match="loopback only|http"):
        wu.loopback_url(url)


@pytest.fixture
def server():
    """A loopback HTTP server whose answer the test sets: a status, or None to stop serving."""
    import http.server
    import threading

    state = {"status": 200}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(state["status"])
            self.end_headers()

        def log_message(self, *_):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{httpd.server_address[1]}/health"
    state["stop"] = lambda: (httpd.shutdown(), httpd.server_close())
    yield state
    if thread.is_alive():
        state["stop"]()


def test_a_server_answering_below_500_is_an_answer(server):
    assert wu.answers(server["url"], 2.0) is True
    server["status"] = 404
    assert wu.answers(server["url"], 2.0) is True, "a 4xx is a server that is up and answering"
    server["status"] = 503
    assert wu.answers(server["url"], 2.0) is False, "a 5xx is no answer"


def test_a_stopped_server_is_no_answer(server):
    url = server["url"]
    server["stop"]()
    assert wu.answers(url, 1.0) is False


def test_the_probe_beats_until_the_server_has_failed_for_longer_than_the_bound(server):
    clock = {"t": 100.0}
    probe = wu.Probe(server["url"], 30.0, now=lambda: clock["t"])
    assert probe() is True
    server["status"] = 503
    clock["t"] = 120.0
    assert probe() is True, "one bad answer within the bound doesn't drop the unit"
    clock["t"] = 131.0
    assert probe() is False, "no good answer for longer than the bound: the beats stop"
    server["status"] = 200
    assert probe() is True, "it beats again once the server answers"


def test_a_server_that_never_answered_is_not_alive_yet():
    probe = wu.Probe("http://127.0.0.1:1/", 30.0, ask=lambda _url, _t: False)
    assert probe() is False


def test_the_probe_bounds_each_request():
    asked = []
    probe = wu.Probe("http://127.0.0.1:1/", 120.0, ask=lambda url, t: asked.append(t) or True)
    probe()
    assert asked == [wu.PROBE_TIMEOUT_S], "a hung server can't hold the loop past the next beat"


def test_the_wrapper_with_a_probe_runs_the_program_and_records_it(tmp_path, monkeypatch):
    import macf.pd.liveness as liveness
    beat = _Beat()
    monkeypatch.setattr(liveness, "heartbeat_from_env", lambda: beat)
    pidfile = tmp_path / "child.pid"
    code = wu.main(["--probe", "http://127.0.0.1:1/", "--within", "30", "--pidfile", str(pidfile), "--",
                    sys.executable, "-c", "import sys; sys.exit(4)"])
    assert code == 4
    assert beat.stopped
    assert pidfile.read_text().split()[0].isdigit()
