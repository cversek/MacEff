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
    assert wu.answer_failure(server["url"], 2.0) is None
    server["status"] = 404
    assert wu.answer_failure(server["url"], 2.0) is None, "a 4xx is a server that is up and answering"
    server["status"] = 503
    assert wu.answer_failure(server["url"], 2.0) == f"{server['url']} answered 503", \
        "a 5xx is no answer, and the reason names the status"


def _serve(status, location=None):
    """A loopback server answering *status* (with *location*, if given), counting its requests."""
    import http.server
    import threading

    hits = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(status)
            if location:
                self.send_header("Location", location)
            self.end_headers()

        def log_message(self, *_):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return {"httpd": httpd, "url": f"http://127.0.0.1:{httpd.server_address[1]}/", "hits": hits}


def test_a_redirect_is_an_answer_and_is_never_followed():
    """A probe follows nowhere: a Location naming another host would take it off loopback."""
    target = _serve(200)
    first = _serve(302, location=target["url"] + "elsewhere")
    try:
        assert wu.answer_failure(first["url"], 2.0) is None, "a 3xx is a server up and replying"
        assert first["hits"] == ["/"]
        assert target["hits"] == [], "the probe followed the redirect"
    finally:
        for served in (first, target):
            served["httpd"].shutdown()
            served["httpd"].server_close()


def test_localhost_that_resolves_off_loopback_is_refused(monkeypatch):
    monkeypatch.setattr(wu, "_resolve", lambda name: ["127.0.0.1", "192.0.2.7"])
    with pytest.raises(ValueError, match="loopback only"):
        wu.loopback_url("http://localhost:8000/")
    monkeypatch.setattr(wu, "_resolve", lambda name: [])
    with pytest.raises(ValueError, match="loopback only"):
        wu.loopback_url("http://localhost:8000/")
    monkeypatch.setattr(wu, "_resolve", lambda name: ["127.0.0.1", "::1"])
    assert wu.loopback_url("http://localhost:8000/") == "http://localhost:8000/"


def test_a_listener_that_does_not_speak_http_is_no_answer_with_a_reason():
    """Something else on the port (an SSH banner, say) makes http.client raise, not OSError."""
    import socket
    import threading
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()

    def banner():
        conn, _ = listener.accept()
        conn.sendall(b"SSH-2.0-not-http\r\n")
        conn.close()
    threading.Thread(target=banner, daemon=True).start()
    url = f"http://127.0.0.1:{listener.getsockname()[1]}/"
    try:
        why = wu.answer_failure(url, 2.0)
    finally:
        listener.close()
    assert why is not None and why.startswith(f"{url} gave no answer: "), why


def test_an_ask_that_raises_is_a_failed_attempt_with_its_reason():
    def ask(_u, _t):
        raise RuntimeError("boom")
    clock = {"t": 0.0}
    said = []
    probe = wu.Probe("http://127.0.0.1:8000/", 30.0, ask=ask, now=lambda: clock["t"], say=said.append)
    assert probe() is False
    clock["t"] = 31.0
    probe()
    assert said == [("http://127.0.0.1:8000/ has not answered within 30 s; "
                     "last: the attempt raised RuntimeError: boom")]


def test_a_stopped_server_is_no_answer(server):
    url = server["url"]
    server["stop"]()
    why = wu.answer_failure(url, 1.0)
    assert why.startswith(f"{url} gave no answer: ") and "Error" in why, \
        "a refusal says it was one, with the error, not just that it failed"


def test_the_probe_beats_until_the_server_has_failed_for_longer_than_the_bound(server):
    clock = {"t": 100.0}
    probe = wu.Probe(server["url"], 30.0, now=lambda: clock["t"], say=lambda _line: None)
    assert probe() is True
    server["status"] = 503
    clock["t"] = 120.0
    assert probe() is True, "one bad answer within the bound doesn't drop the unit"
    clock["t"] = 131.0
    assert probe() is False, "no good answer for longer than the bound: the beats stop"
    server["status"] = 200
    assert probe() is True, "it beats again once the server answers"


def test_a_server_that_never_answered_is_not_alive_yet():
    probe = wu.Probe("http://127.0.0.1:1/", 30.0, ask=lambda _url, _t: "refused",
                     say=lambda _line: None)
    assert probe() is False


def test_the_probe_bounds_each_request():
    asked = []
    probe = wu.Probe("http://127.0.0.1:1/", 120.0, ask=lambda url, t: asked.append(t))
    probe()
    assert asked == [wu.PROBE_TIMEOUT_S], "a hung server can't hold the loop past the next beat"


def test_the_reason_is_said_once_when_the_unit_stops_answering_and_once_when_it_answers_again():
    clock = {"t": 0.0}
    answer = {"why": None}
    said = []
    probe = wu.Probe("http://127.0.0.1:8000/", 30.0, ask=lambda _u, _t: answer["why"],
                     now=lambda: clock["t"], say=said.append)
    assert probe() is True and said == []
    answer["why"] = "http://127.0.0.1:8000/ answered 503"
    for t in (10.0, 20.0, 31.0, 40.0, 50.0):
        clock["t"] = t
        probe()
    assert said == [("http://127.0.0.1:8000/ has not answered within 30 s; "
                     "last: http://127.0.0.1:8000/ answered 503")], \
        "one line, with the last reason, when the verdict turns; none on the passes after"
    answer["why"] = None
    probe()
    probe()
    assert said[1:] == ["http://127.0.0.1:8000/ is answering again"]


def test_a_program_that_never_answers_is_reported_once_its_bound_has_passed():
    clock = {"t": 0.0}
    said = []
    probe = wu.Probe("http://127.0.0.1:8000/", 30.0, ask=lambda _u, _t: "refused",
                     now=lambda: clock["t"], say=said.append)
    probe()
    assert said == [], "a program still starting isn't reported"
    clock["t"] = 31.0
    probe()
    probe()
    assert said == ["http://127.0.0.1:8000/ has not answered within 30 s; last: refused"]


def test_a_hung_ask_in_the_background_never_holds_the_loop():
    import threading
    import time
    release = threading.Event()
    probe = wu.Probe("http://127.0.0.1:8000/", 30.0, ask=lambda _u, _t: release.wait(5) and None,
                     say=lambda _line: None, background=True)
    began = time.monotonic()
    assert probe() is False
    assert probe() is False, "a second pass doesn't start a second ask beside the hung one"
    assert time.monotonic() - began < 1.0, "the loop waited on the ask"
    release.set()
    probe._asking.join(2)
    assert probe() is True, "the answer the thread got is the verdict on the next pass"


def test_a_hang_after_a_recovery_does_not_report_the_earlier_outage():
    clock = {"t": 0.0}
    answer = {"why": "http://127.0.0.1:8000/ answered 503"}
    said = []
    probe = wu.Probe("http://127.0.0.1:8000/", 30.0, ask=lambda _u, _t: answer["why"],
                     now=lambda: clock["t"], say=said.append)
    probe()                     # the outage: a 503
    answer["why"] = None
    probe()                     # it answers
    probe._ask_once = lambda: None   # from here every attempt hangs: none finishes
    clock["t"] = 31.0
    probe()
    assert said[-1].endswith("last: no attempt has finished yet"), \
        "the reason given was the outage before the recovery"


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


# --- a health-check command: a program that answers on no port, such as a job worker ---------

def test_a_check_that_exits_0_passes_and_any_other_ending_fails_saying_why():
    assert wu.Check([sys.executable, "-c", "pass"])(None, 5.0) is None
    why = wu.Check([sys.executable, "-c",
                    ("import sys; print('noise'); print('db: connection refused', file=sys.stderr); "
                     "sys.exit(3)")])(None, 5.0)
    assert why.startswith("the check python") and "exited 3" in why
    assert "db: connection refused" in why, "the check's own error is kept in the reason"
    why = wu.Check(["/nonexistent/health-check"])(None, 5.0)
    assert why.startswith("the check health-check could not start: "), "a check that can't start fails"
    why = wu.Check([sys.executable, "-c", "import time; time.sleep(5)"])(None, 0.3)
    assert why.endswith("did not finish within 0.3 s"), "a check that doesn't finish in time fails"


def test_closing_a_check_ends_a_run_still_under_way():
    import threading
    import time
    check = wu.Check([sys.executable, "-c", "import time; time.sleep(30)"])
    result = {}
    thread = threading.Thread(target=lambda: result.setdefault("why", check(None, 60.0)))
    thread.start()
    for _ in range(100):
        if check._running is not None:
            break
        time.sleep(0.05)
    check.close()
    thread.join(5)
    assert not thread.is_alive(), "a stopping wrapper left its check running"
    assert result["why"].startswith("the check python") and "exited" in result["why"]


def test_the_wrapper_with_a_check_judges_the_unit_by_it(tmp_path, monkeypatch):
    import macf.pd.liveness as liveness
    beat = _Beat()
    monkeypatch.setattr(liveness, "heartbeat_from_env", lambda: beat)
    seen = []
    monkeypatch.setattr(wu.Check, "__call__", lambda self, _w, t: seen.append((self.argv, t)))
    pidfile = tmp_path / "child.pid"
    code = wu.main(["--check", "arq --check workers.main.WorkerSettings", "--within", "120",
                    "--pidfile", str(pidfile), "--",
                    sys.executable, "-c", "import time; time.sleep(0.6)"])
    assert code == 0
    assert seen, "the check ran while the program did"
    argv, timeout = seen[0]
    assert argv == ["arq", "--check", "workers.main.WorkerSettings"], "the string is split as a shell would"
    assert timeout == wu.CHECK_TIMEOUT_S, "a check gets the check's cap, not the request's"


@pytest.mark.parametrize("argv", [
    ["--check", "true", "--within", "30", "--", "true"],               # no pidfile
    ["--check", "", "--within", "30", "--pidfile", "p", "--", "true"],  # no command
    ["--check", "true", "--probe", "http://127.0.0.1:1/", "--within", "30", "--pidfile", "p", "--", "true"],
])
def test_a_check_without_a_pidfile_a_command_or_alone_is_refused(argv):
    with pytest.raises(SystemExit) as refused:
        wu.main(argv)
    assert refused.value.code == 2


# --- a wrapper unit must be declared with more grace than the wrapper's stop path (#1001) -------

def _wrapper_unit(module, grace=None):
    from macf.pd.interface import Unit
    fields = {"name": "web", "command": [sys.executable, "-m", module, "--probe", "http://127.0.0.1:8000/",
                                         "--within", "60", "--pidfile", "/tmp/web.pid", "--", "web"],
              "account": "resident", "restart": "always", "liveness_interval_s": 60, "memory_limit_mb": 256}
    if grace is not None:
        fields["stop_grace_s"] = grace
    return Unit(**fields)


@pytest.mark.parametrize("module", ["macf.pd.watched_unit", "macf.pd.broker_unit"])
def test_a_wrapper_unit_with_less_grace_than_its_stop_path_is_refused_naming_the_fix(module):
    from pydantic import ValidationError
    from macf.pd.broker_unit import WRAPPER_UNIT_STOP_GRACE_S
    for grace in (None, WRAPPER_UNIT_STOP_GRACE_S - 1):      # the default of 10, and just under
        with pytest.raises(ValidationError, match=f"stop_grace_s: {WRAPPER_UNIT_STOP_GRACE_S:g} or more"):
            _wrapper_unit(module, grace)
    assert _wrapper_unit(module, WRAPPER_UNIT_STOP_GRACE_S).stop_grace_s == WRAPPER_UNIT_STOP_GRACE_S


def test_a_unit_that_only_names_a_wrapper_elsewhere_is_not_judged_by_it():
    from macf.pd.interface import Unit
    unit = Unit(name="notes", command=["cat", "macf.pd.watched_unit"], account="resident", restart="always",
                liveness_interval_s=60, memory_limit_mb=64)
    assert unit.stop_grace_s == 10.0, "only a command that runs the module with -m is a wrapper unit"
