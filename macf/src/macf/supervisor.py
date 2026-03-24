"""Auto-restarting process supervisor with multi-process management.

Manages multiple supervised processes, each in its own terminal window.
Provides pm2-style process listing with stats.

Usage:
    macf_tools auto-restart launch -- claude -c
    macf_tools auto-restart launch --name manny -- ssh pa_manny@localhost
    macf_tools auto-restart list                 # ps-style listing
    macf_tools auto-restart restart <pid>        # trigger restart
    macf_tools auto-restart disable <pid>        # stop auto-restart
    macf_tools auto-restart status <pid>         # detailed status

Architecture:
    launch → opens new terminal → runs supervisor loop in that terminal
    supervisor loop → spawns command as child, restarts on exit
    registry → /tmp/macf/auto-restart/*.json (one per supervised process)
    signals → SIGUSR1 (restart child), SIGUSR2 (disable loop)
"""

import json
import os
import platform
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REGISTRY_DIR = Path("/tmp/macf/auto-restart")


def _registry_file(pid: int) -> Path:
    return REGISTRY_DIR / f"{pid}.json"


def _write_registry(pid: int, data: dict):
    """Write process stats to registry."""
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    _registry_file(pid).write_text(json.dumps(data, indent=2))


def _read_registry(pid: int) -> dict:
    f = _registry_file(pid)
    if not f.exists():
        return {}
    return json.loads(f.read_text())


def _update_registry(pid: int, **kwargs):
    data = _read_registry(pid)
    data.update(kwargs)
    _write_registry(pid, data)


def _cleanup_registry(pid: int):
    f = _registry_file(pid)
    if f.exists():
        f.unlink()


def _notify_telegram(message: str, prefix: str = ""):
    try:
        from macf.channels.telegram import send_telegram_notification
        send_telegram_notification(message, prefix=prefix)
    except Exception:
        pass


def _is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    remaining = minutes % 60
    if hours < 24:
        return f"{hours}h{remaining}m"
    days = hours // 24
    remaining_h = hours % 24
    return f"{days}d{remaining_h}h"


def launch_in_terminal(cmd_args: list, name: str = "",
                       restart_delay: int = 2) -> int:
    """Launch a supervised process in a new terminal window.

    Args:
        cmd_args: Command and arguments to supervise
        name: Optional display name (defaults to command basename)
        restart_delay: Seconds between restarts

    Returns:
        Supervisor PID
    """
    if not cmd_args:
        print("Error: no command specified", file=sys.stderr)
        return 1

    if not name:
        name = os.path.basename(cmd_args[0])

    # Build the supervisor command that runs in the new terminal
    supervisor_cmd = [
        sys.executable, "-m", "macf.supervisor",
        "_run_loop",
        "--name", name,
        "--delay", str(restart_delay),
        "--",
    ] + cmd_args

    system = platform.system()
    if system == "Darwin":
        # macOS: open new Terminal.app window via osascript
        escaped_cmd = " ".join(
            arg.replace("\\", "\\\\").replace('"', '\\"')
            for arg in supervisor_cmd
        )
        osascript = f'''
            tell application "Terminal"
                activate
                do script "{escaped_cmd}"
            end tell
        '''
        subprocess.Popen(["osascript", "-e", osascript])
        # Wait briefly for the process to start and write registry
        time.sleep(1.5)

    elif system == "Linux":
        # Linux: try common terminal emulators
        for term in ["gnome-terminal", "xterm", "konsole"]:
            if subprocess.run(["which", term], capture_output=True).returncode == 0:
                if term == "gnome-terminal":
                    subprocess.Popen([term, "--", *supervisor_cmd])
                else:
                    subprocess.Popen([term, "-e", " ".join(supervisor_cmd)])
                time.sleep(1.5)
                break
        else:
            print("No terminal emulator found. Run directly:", file=sys.stderr)
            print(f"  {' '.join(supervisor_cmd)}", file=sys.stderr)
            return 1
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        return 1

    # Find the newly created registry entry
    if REGISTRY_DIR.exists():
        entries = sorted(REGISTRY_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if entries:
            data = json.loads(entries[0].read_text())
            pid = data.get("supervisor_pid", "?")
            print(f"[auto-restart] Launched '{name}' in new terminal (supervisor PID: {pid})")
            print(f"[auto-restart] Command: {' '.join(cmd_args)}")
            print(f"[auto-restart] Manage: macf_tools auto-restart list")
            return pid

    print(f"[auto-restart] Launched '{name}' in new terminal")
    return 0


def run_loop(cmd_args: list, name: str = "", restart_delay: int = 2):
    """Run the supervisor loop (called inside the new terminal).

    This is the actual supervisor process — manages the child.
    """
    pid = os.getpid()
    created = time.time()

    _write_registry(pid, {
        "supervisor_pid": pid,
        "name": name,
        "command": cmd_args,
        "created": created,
        "created_iso": datetime.fromtimestamp(created).isoformat(),
        "restart_count": 0,
        "status": "running",
        "last_restart": None,
        "child_pid": None,
    })

    child = None
    restart_count = 0

    def handle_restart(signum, frame):
        nonlocal child
        if child and child.poll() is None:
            _notify_telegram(
                f"Process: {name}\nRestart #{restart_count + 1}",
                prefix="\U0001f504 \u03bcC Triggered"
            )
            child.send_signal(signal.SIGINT)

    def handle_disable(signum, frame):
        _update_registry(pid, status="disabled")
        nonlocal child
        if child and child.poll() is None:
            child.send_signal(signal.SIGINT)

    signal.signal(signal.SIGUSR1, handle_restart)
    signal.signal(signal.SIGUSR2, handle_disable)

    print(f"[auto-restart] Supervisor PID: {pid}")
    print(f"[auto-restart] Name: {name}")
    print(f"[auto-restart] Command: {' '.join(cmd_args)}")
    print(f"[auto-restart] Restart delay: {restart_delay}s")
    print(f"[auto-restart] Remote restart: macf_tools auto-restart restart {pid}")
    print(f"[auto-restart] Disable: macf_tools auto-restart disable {pid}")
    print()

    _notify_telegram(
        f"Name: {name}\nCommand: {' '.join(cmd_args)}\nPID: {pid}",
        prefix="\U0001f680 Supervisor Started"
    )

    try:
        while True:
            reg = _read_registry(pid)
            if reg.get("status") == "disabled":
                print("[auto-restart] Disabled. Exiting.")
                break

            child = subprocess.Popen(cmd_args)
            _update_registry(pid, child_pid=child.pid, status="running")

            exit_code = child.wait()
            child = None
            restart_count += 1

            _update_registry(pid,
                             restart_count=restart_count,
                             last_restart=time.time(),
                             child_pid=None,
                             last_exit_code=exit_code)

            # Check if disabled during child run
            reg = _read_registry(pid)
            if reg.get("status") == "disabled":
                print(f"[auto-restart] Disabled. Not restarting.")
                break

            print(f"\n[auto-restart] Exited (code {exit_code}). Restart #{restart_count} in {restart_delay}s...")
            _notify_telegram(
                f"Process: {name}\nExit code: {exit_code}\nRestart #{restart_count}",
                prefix="\U0001f504 Auto-Restart"
            )

            try:
                time.sleep(restart_delay)
            except KeyboardInterrupt:
                print("\n[auto-restart] Interrupted. Exiting.")
                break

    except KeyboardInterrupt:
        if child and child.poll() is None:
            child.send_signal(signal.SIGINT)
            child.wait()
    finally:
        _update_registry(pid, status="stopped",
                         stopped=time.time(),
                         total_restarts=restart_count)
        _notify_telegram(
            f"Process: {name}\nRestarts: {restart_count}\nUptime: {_format_duration(time.time() - created)}",
            prefix="\U0001f6d1 Supervisor Stopped"
        )


def list_processes():
    """List all managed processes with stats."""
    if not REGISTRY_DIR.exists():
        print("No managed processes.")
        return

    entries = sorted(REGISTRY_DIR.glob("*.json"))
    if not entries:
        print("No managed processes.")
        return

    # Header
    print(f"{'PID':>8}  {'NAME':<20}  {'STATUS':<10}  {'RESTARTS':>8}  {'UPTIME':>8}  {'COMMAND'}")
    print("-" * 90)

    for entry in entries:
        data = json.loads(entry.read_text())
        pid = data.get("supervisor_pid", 0)
        name = data.get("name", "?")
        status = data.get("status", "?")
        restarts = data.get("restart_count", 0)
        created = data.get("created", 0)
        cmd = " ".join(data.get("command", []))

        # Check if actually alive
        alive = _is_alive(pid)
        if not alive and status == "running":
            status = "dead"

        uptime = _format_duration(time.time() - created) if created else "?"

        # Color status
        if status == "running" and alive:
            status_display = f"\033[32m{status}\033[0m"
        elif status == "disabled":
            status_display = f"\033[33m{status}\033[0m"
        else:
            status_display = f"\033[31m{status}\033[0m"

        print(f"{pid:>8}  {name:<20}  {status_display:<21}  {restarts:>8}  {uptime:>8}  {cmd[:40]}")

    # Clean up dead entries
    for entry in entries:
        data = json.loads(entry.read_text())
        pid = data.get("supervisor_pid", 0)
        if not _is_alive(pid) and data.get("status") != "running":
            pass  # Keep stopped entries for history; user can clean manually


def restart(pid: int):
    """Send restart signal to a supervised process."""
    if not _is_alive(pid):
        print(f"[auto-restart] Process {pid} is not running")
        return
    os.kill(pid, signal.SIGUSR1)
    print(f"[auto-restart] Restart signal sent to {pid}")


def disable(pid: int):
    """Disable auto-restart for a supervised process."""
    if not _is_alive(pid):
        print(f"[auto-restart] Process {pid} is not running")
        _update_registry(pid, status="disabled")
        return
    os.kill(pid, signal.SIGUSR2)
    print(f"[auto-restart] Disable signal sent to {pid}")


def kill_process(pid: int):
    """Nuclear option: kill supervisor and child processes."""
    data = _read_registry(pid)
    if not data:
        print(f"[auto-restart] No registry entry for PID {pid}")
        return

    child_pid = data.get("child_pid")
    killed = []

    # Kill child first
    if child_pid and _is_alive(child_pid):
        os.kill(child_pid, signal.SIGKILL)
        killed.append(f"child {child_pid}")

    # Kill supervisor
    if _is_alive(pid):
        os.kill(pid, signal.SIGKILL)
        killed.append(f"supervisor {pid}")

    # Clean up registry
    _update_registry(pid, status="killed")

    if killed:
        print(f"[auto-restart] Killed: {', '.join(killed)}")
        _notify_telegram(
            f"Process: {data.get('name', '?')}\nKilled: {', '.join(killed)}",
            prefix="\U0001f480 Process Killed"
        )
    else:
        print(f"[auto-restart] Process {pid} already dead")


def status(pid: int):
    """Show detailed status for a supervised process."""
    data = _read_registry(pid)
    if not data:
        print(f"[auto-restart] No registry entry for PID {pid}")
        return

    alive = _is_alive(pid)
    print(f"Supervisor PID:  {pid} ({'alive' if alive else 'dead'})")
    print(f"Name:            {data.get('name', '?')}")
    print(f"Command:         {' '.join(data.get('command', []))}")
    print(f"Status:          {data.get('status', '?')}")
    print(f"Child PID:       {data.get('child_pid', 'none')}")
    print(f"Created:         {data.get('created_iso', '?')}")
    print(f"Restarts:        {data.get('restart_count', 0)}")
    print(f"Last exit code:  {data.get('last_exit_code', 'N/A')}")
    created = data.get("created", 0)
    if created:
        print(f"Uptime:          {_format_duration(time.time() - created)}")


# Entry point for running inside new terminal
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Auto-restart supervisor")
    parser.add_argument("action", choices=["_run_loop"])
    parser.add_argument("--name", default="")
    parser.add_argument("--delay", type=int, default=2)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)

    args = parser.parse_args()
    # Strip leading -- from remainder
    cmd = [a for a in args.cmd if a != "--"]

    if args.action == "_run_loop":
        run_loop(cmd, name=args.name, restart_delay=args.delay)
