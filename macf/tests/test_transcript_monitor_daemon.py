"""A started monitor is a process of its own, holding nothing of its starter (#54, #529).

#54: a monitor forked from a command whose stderr was a pipe kept the pipe open,
so `macf_tools mode set-work X 2>&1 | tail -50` hung until the monitor died.
#529: the forks also kept their starter's command line and code, so `ps` showed
them as the hook or command that started them and they ran that code for months.

Here a real monitor is started the way the hook starts one, from a process
whose stderr is a pipe, on a temporary transcript, for an owner the test
controls; then the owner ends, and so must the monitor.
"""
import json
import os
import signal
import subprocess
import sys
import time

from macf.transcript_monitor import daemon

STARTER = r'''
import os, sys
from pathlib import Path
from macf.transcript_monitor import daemon

transcript = Path(sys.argv[1])
daemon.find_current_transcript = lambda: transcript
os.environ["CLAUDE_PID"] = str(os.getpid())      # this process is the owner

saved = os.dup(1)
r, w = os.pipe()
os.dup2(w, 2)                                     # stderr is a pipe, as in `... 2>&1 | tail`
os.close(w)
code = daemon.start_daemon(poll_interval=0.05)
os.dup2(os.open(os.devnull, os.O_WRONLY), 2)      # let go of this process's own copy

os.set_blocking(r, False)
held = False
while True:                                       # drain what was printed, then look for a writer
    try:
        chunk = os.read(r, 65536)
    except BlockingIOError:
        held = True                               # empty, and someone still holds the write end
        break
    if not chunk:
        break                                     # end of file: no writer is left
os.write(saved, f"code={code} held={held}\n".encode())
sys.stdin.read()                                  # stay alive, as the owner, until told to end
'''


def test_a_started_monitor_is_named_holds_nothing_of_its_starter_and_ends_with_it(
        tmp_path, isolated_events_log):
    transcript = tmp_path / "s1.jsonl"
    transcript.write_text("")
    env = {k: v for k, v in os.environ.items() if k != daemon.DISABLE_ENV}  # a real start, by design
    env["XDG_RUNTIME_DIR"] = str(tmp_path)
    starter = subprocess.Popen([sys.executable, "-c", STARTER, str(transcript)],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env)
    monitor_pid = 0
    try:
        assert starter.stdout.readline().strip() == "code=0 held=False"

        found = [m for m in daemon.find_monitors() if m.transcript == transcript]
        assert [m.owner for m in found] == [starter.pid], found
        monitor_pid = found[0].pid

        starter.stdin.close()
        starter.wait(timeout=10)
        deadline = time.monotonic() + 10
        while daemon._alive(monitor_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not daemon._alive(monitor_pid), "the monitor outlived its owner"
    finally:
        if starter.poll() is None:
            starter.kill()
        if monitor_pid and daemon._alive(monitor_pid):
            os.kill(monitor_pid, signal.SIGKILL)

    records = [json.loads(line) for line in isolated_events_log.read_text().splitlines()]
    lifecycle = [(r["event"], r["data"]["pid"], r["data"].get("reason")) for r in records
                 if r["event"].startswith("transcript_monitor_")]
    assert lifecycle == [
        ("transcript_monitor_started", monitor_pid, None),
        ("transcript_monitor_stopped", monitor_pid, f"its Claude Code process {starter.pid} ended"),
    ]
    assert f"Watching: {transcript}" in (tmp_path / daemon.LOG_FILE_NAME).read_text()
