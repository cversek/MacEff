"""The macOS rendering of a primal daemon: a per-user LaunchAgent.

MIS-0002-R05 (macos_MUST_render_LaunchAgent). A LaunchDaemon would run as root,
without the user's keychain or privacy grants, and its failures look like ordinary
network or authentication errors. A LaunchAgent in the user's GUI session holds what
the user holds. On macOS launchd is the outer tier: KeepAlive restarts the daemon
whenever it exits (MIS-0002-R03 (outer_tier_MUST_restart_pd)).

Rendering, then install and removal as plans: ``install_plan`` and ``uninstall_plan`` say
what would be written and run, and only ``apply_plan`` does it. A LaunchAgent persists on
the host, so a plan is shown before it is applied.
"""
import os
import plistlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

from macf.pd.interface import launchd_label
from macf.pd.names import PD_IDENTIFIER
from macf.utils.atomic import write_text_atomic

_VERBS = ("bootstrap", "bootout", "kickstart", "print", "enable", "disable")

#: launchctl's exit status for a boot-out of a service the domain does not have, measured on
#: macOS 15 as "Boot-out failed: 3: No such process". Removal's goal is met, so it goes on.
BOOTOUT_NOT_LOADED = 3

#: How long a reload waits for a booted-out job to leave launchd before bootstrapping it.
#: ``bootout`` returns while the job is still stopping, and a bootstrap in that window fails
#: with "Bootstrap failed: 5" (measured on macOS 15 with a job that takes 3 s to exit).
RELOAD_WAIT_S = 30.0
#: How often that wait looks.
RELOAD_POLL_S = 0.25


def pd_label(card: str) -> str:
    """The launchd label for one agent's primal daemon, as the step-1 interface names it
    (``launchd_label``): ``maceff_pd.<pd_id>``, so ``IraMacEff@ee9a78`` becomes
    ``maceff_pd.IraMacEff_ee9a78``. MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd); the
    card comes from the identity file, never the environment (MIS-0002-R02). A string
    that is not a calling card is refused here rather than rendered into a label.
    """
    if not card or "@" not in card or "/" in card:
        raise ValueError(f"not a calling card: {card!r} (expected Name@hexid)")
    return launchd_label(card)


def render_pd_launch_agent(card: str, program_argv: List[str], home: str,
                           log_dir: str) -> Tuple[str, bytes]:
    """The plist for one agent's primal daemon, and where it belongs.

    *program_argv* starts the daemon; the plist carries no declaration and no agent
    configuration (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)), and no
    identity in its environment.

    launchd runs its first element, the interpreter, as ``Program``, with ``maceff_pd`` in
    its place as ``argv[0]``. macOS has no call that renames a running process, so this is
    where the daemon gets the name ``ps`` and ``pgrep`` show
    (MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)). The kernel's own name, which ``top``
    shows, stays the interpreter's. A framework-build interpreter is run through its
    Python.app directly (``framework_app``), since its launcher's re-exec would rename it.
    """
    if not program_argv:
        raise ValueError("program_argv is empty")
    if not os.path.isabs(program_argv[0]):
        raise ValueError(f"launchd runs a program by its absolute path, not {program_argv[0]!r}")
    label = pd_label(card)
    app = framework_app(program_argv[0])
    plist = {
        "Label": label,
        "Program": app or program_argv[0],
        "ProgramArguments": [PD_IDENTIFIER, *program_argv[1:]],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "LimitLoadToSessionType": "Aqua",
        # The managed units outlive the daemon's exit (the operator's decision, 2026-10-10):
        # launchd would otherwise kill the job's process group when the daemon dies, taking
        # the session with it. The daemon stops its units itself, in order, on SIGTERM, and
        # a restarted daemon re-adopts the ones still running. Linux renders the same with
        # KillMode=process.
        "AbandonProcessGroup": True,
        "ProcessType": "Background",
        "StandardOutPath": f"{log_dir}/{label}.out.log",
        "StandardErrorPath": f"{log_dir}/{label}.err.log",
    }
    if app:
        # What the build's own launcher would have told Python.app: the path it was started
        # as, so a venv survives the direct start. An internal of CPython's macOS build, which
        # a test pins, so a release that drops it fails there rather than losing the name.
        plist["EnvironmentVariables"] = {"__PYVENV_LAUNCHER__": program_argv[0]}
    path = f"{home}/Library/LaunchAgents/{label}.plist"
    return path, plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True)


def framework_app(interpreter: str) -> Optional[str]:
    """The Python.app binary a framework-build interpreter re-execs itself through, or None
    for a plain build.

    A framework build's ``bin/python3`` (Homebrew's, python.org's) is a launcher: it re-execs
    ``Resources/Python.app/Contents/MacOS/Python``, which names the process, and passes the
    path it was started as in ``__PYVENV_LAUNCHER__``. Read from the interpreter's resolved
    path, so a venv's ``python3`` leads to its base build.
    """
    real = os.path.realpath(interpreter)
    bin_dir = os.path.dirname(real)
    version_dir = os.path.dirname(bin_dir)
    versions = os.path.dirname(version_dir)
    if (os.path.basename(bin_dir) != "bin" or os.path.basename(versions) != "Versions"
            or not os.path.basename(os.path.dirname(versions)).endswith(".framework")):
        return None
    app = os.path.join(version_dir, "Resources", "Python.app", "Contents", "MacOS", "Python")
    return app if os.path.isfile(app) else None


def launchctl_argv(verb: str, label: str, uid: int, plist_path: Optional[str] = None) -> List[str]:
    """The launchctl command for *verb* on this user's GUI domain.

    Only the domain-target verbs are offered; the legacy load/unload are not. ``disable``
    keeps a job from loading at the next login and ``enable`` lifts that, so a job booted out
    and disabled is stopped the way systemd's ``disable --now`` stops a unit.
    """
    if verb not in _VERBS:
        raise ValueError(f"unsupported launchctl verb {verb!r}; use one of {', '.join(_VERBS)}")
    domain = f"gui/{uid}"
    if verb == "bootstrap":
        if not plist_path:
            raise ValueError("bootstrap needs the plist path")
        return ["launchctl", "bootstrap", domain, plist_path]
    if verb == "kickstart":
        return ["launchctl", "kickstart", "-k", f"{domain}/{label}"]
    return ["launchctl", verb, f"{domain}/{label}"]


# ---------------------------------------------------------------------------
# Install, remove and status: plans first, applied only when asked
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Step:
    """One thing an install or removal does: write or remove a file, or run launchctl.

    ``not_loaded_ok`` marks a boot-out whose service may already be gone: launchd's
    not-loaded answer then counts as done instead of stopping the plan.
    """

    what: str
    path: Optional[str] = None
    content: Optional[bytes] = None
    argv: Optional[List[str]] = None
    not_loaded_ok: bool = False
    #: For an ``unloaded`` step: how long to wait for the label to leave launchd.
    wait_s: float = 0.0

    def describe(self) -> str:
        if self.what == "launchctl":
            return " ".join(self.argv or [])
        if self.what == "unloaded":
            return f"wait up to {self.wait_s:g} s for {(self.argv or [''])[-1]} to leave launchd"
        return f"{self.what} {self.path}"


def check_socket_path(path: str) -> None:
    """MIS-0002-R129 (adapter_MUST_check_socket_path_length), through the interface's own
    check, so the limit lives in one place. Raises ``OSError`` with the path and the limit."""
    from macf.pd.interface import check_socket_path as _check
    from pathlib import Path
    _check(Path(path))


def install_plan(card: str, program_argv: List[str], home: str, log_dir: str, uid: int,
                 socket_paths: List[str], reload: bool = False) -> List[Step]:
    """What installing one agent's primal daemon does, in order, without doing it.

    Every socket path the daemon will bind is checked first, so a path that cannot work
    stops the install before anything is written (R129).

    ``reload`` replaces a job that may already be loaded. launchd refuses to bootstrap a
    label it has loaded, and ``kickstart -k`` restarts a job from the definition read at its
    bootstrap, not from the plist on disk. So the job is booted out first, then bootstrapped
    from the new plist. The boot-out ends the daemon; ``AbandonProcessGroup`` keeps its units
    running, and the daemon the bootstrap starts adopts them (persistent_layer 12.6).
    """
    for sp in socket_paths:
        check_socket_path(sp)
    path, data = render_pd_launch_agent(card, program_argv, home, log_dir)
    label = pd_label(card)
    steps = [Step("write", path=path, content=data)]
    if reload:
        steps.append(Step("launchctl", argv=launchctl_argv("bootout", label, uid), not_loaded_ok=True))
        # bootout returns while the job is still stopping; a bootstrap before it's gone fails.
        steps.append(Step("unloaded", argv=launchctl_argv("print", label, uid), wait_s=RELOAD_WAIT_S))
    steps.append(Step("launchctl", argv=launchctl_argv("bootstrap", label, uid, plist_path=path)))
    return steps


def uninstall_plan(card: str, home: str, uid: int) -> List[Step]:
    """What removing one agent's primal daemon does: boot it out, then remove its plist.

    The boot-out may find nothing loaded: after an install whose bootstrap failed, after a
    reboot outside the GUI session, or on a second removal. The plist goes either way.
    """
    label = pd_label(card)
    return [Step("launchctl", argv=launchctl_argv("bootout", label, uid), not_loaded_ok=True),
            Step("remove", path=f"{home}/Library/LaunchAgents/{label}.plist")]


def apply_plan(steps: List[Step], run=None, force: bool = False) -> List[str]:
    """Carry out a plan. A plist that exists and differs is not overwritten without ``force``.

    Returns one line per step. Stops at the first launchctl failure and raises with its
    output, so a half-done install is said, not hidden. A boot-out marked ``not_loaded_ok``
    that finds nothing loaded is not a failure.
    """
    import os
    import subprocess
    run = run or (lambda argv: subprocess.run(argv, capture_output=True, text=True))
    for s in steps:
        if s.what == "write" and os.path.exists(s.path) and not force:
            with open(s.path, "rb") as fh:
                if fh.read() != s.content:
                    raise FileExistsError(f"{s.path} exists and differs from the rendered plist; "
                                          f"review it, then apply with force")
    done = []
    booted_out = None
    for s in steps:
        if s.what == "unloaded":
            deadline = _clock() + s.wait_s
            while run(s.argv).returncode == 0:
                if _clock() >= deadline:
                    raise RuntimeError(f"{s.argv[-1]} was booted out but is still loaded after {s.wait_s:g} s, so "
                                       f"it wasn't bootstrapped again; the daemon isn't running" + _reload_hint(steps))
                _sleep(RELOAD_POLL_S)
            done.append(s.describe())
            continue
        if s.what == "write":
            os.makedirs(os.path.dirname(s.path), exist_ok=True)
            # Whole or not at all: a full disk must not leave a half-written plist.
            write_text_atomic(s.path, s.content.decode("utf-8"))
        elif s.what == "remove":
            if os.path.exists(s.path):
                os.unlink(s.path)
        elif s.what == "launchctl":
            r = run(s.argv)
            if r.returncode == BOOTOUT_NOT_LOADED and s.not_loaded_ok:
                done.append(f"{s.describe()} (not loaded)")
                continue
            if r.returncode != 0:
                said = f"{s.describe()} failed ({r.returncode}): {(r.stderr or r.stdout).strip()}"
                if booted_out and s.argv[1:2] == ["bootstrap"]:
                    # The job is gone from launchd now: say so, and how to load it again.
                    said += f"; {booted_out} was booted out and isn't loaded now" + _reload_hint(steps)
                raise RuntimeError(said)
            if s.argv[1:2] == ["bootout"]:
                booted_out = s.argv[-1]
        done.append(s.describe())
    return done


def _reload_hint(steps: List[Step]) -> str:
    """The command that loads the job again, from the plan's own bootstrap step."""
    boot = next((s for s in steps if s.what == "launchctl" and s.argv[1:2] == ["bootstrap"]), None)
    return f". Load it again with: {' '.join(boot.argv)}" if boot else ""


def _clock() -> float:
    import time
    return time.monotonic()


def _sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


# ---------------------------------------------------------------------------
# The tray: one LaunchAgent per GUI user, outside every agent
# ---------------------------------------------------------------------------

#: The tray's label. One job for the user, not one per agent: a single icon stands for every
#: agent on the host (MIS-0002-R69), and the tray finds them by ``maceff_pd.*``, which this
#: label does not match.
TRAY_LABEL = "maceff_tray"


def render_tray_launch_agent(program_argv: List[str], home: str, log_dir: str) -> Tuple[str, bytes]:
    """The plist that keeps the operator's tray running, and where it belongs.

    The tray is its own job rather than a unit of an agent's primal daemon: it is how the
    operator sees a daemon in trouble, so it must not share that daemon's failure domain.
    launchd relaunches it when it crashes or is killed, and leaves it down after the
    operator picks Quit, which exits 0.
    """
    if not program_argv:
        raise ValueError("program_argv is empty")
    plist = {
        "Label": TRAY_LABEL,
        "ProgramArguments": list(program_argv),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ThrottleInterval": 10,
        "LimitLoadToSessionType": "Aqua",
        # A menu-bar app answers the person at the screen, so it isn't throttled as background.
        "ProcessType": "Interactive",
        "StandardOutPath": f"{log_dir}/{TRAY_LABEL}.out.log",
        "StandardErrorPath": f"{log_dir}/{TRAY_LABEL}.err.log",
    }
    path = f"{home}/Library/LaunchAgents/{TRAY_LABEL}.plist"
    return path, plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True)


def tray_install_plan(program_argv: List[str], home: str, log_dir: str, uid: int) -> List[Step]:
    """What installing the tray does, in order, without doing it."""
    path, data = render_tray_launch_agent(program_argv, home, log_dir)
    return [Step("write", path=path, content=data),
            Step("launchctl", argv=launchctl_argv("bootstrap", TRAY_LABEL, uid, plist_path=path))]


def tray_uninstall_plan(home: str, uid: int) -> List[Step]:
    """What removing the tray does: boot it out, whether or not it is loaded, then remove its plist."""
    return [Step("launchctl", argv=launchctl_argv("bootout", TRAY_LABEL, uid), not_loaded_ok=True),
            Step("remove", path=f"{home}/Library/LaunchAgents/{TRAY_LABEL}.plist")]


@dataclass(frozen=True)
class AgentStatus:
    """What launchd says about one agent's daemon."""

    loaded: bool
    running: bool
    pid: Optional[int] = None
    last_exit: Optional[str] = None


def parse_print(output: str) -> AgentStatus:
    """Read ``launchctl print gui/<uid>/<label>``: absent, loaded and stopped, or running."""
    if "Could not find service" in output:
        return AgentStatus(loaded=False, running=False)
    fields = {}
    for line in output.splitlines():
        key, sep, value = line.strip().partition(" = ")
        if sep and key in ("state", "pid", "last exit code") and key not in fields:
            fields[key] = value.strip()
    pid = int(fields["pid"]) if fields.get("pid", "").isdigit() else None
    return AgentStatus(loaded=True, running=fields.get("state") == "running", pid=pid,
                       last_exit=fields.get("last exit code"))


# ---------------------------------------------------------------------------
# The cutover job: one run of harness cutover, outside the session it ends
# ---------------------------------------------------------------------------

def cutover_label(card: str) -> str:
    """The label of the one-shot job that moves one agent's session onto its daemon:
    ``maceff_pd.<id>.cutover``. One per agent, so two moves can't overlap."""
    return pd_label(card) + ".cutover"


def render_cutover_job(card: str, program_argv: List[str], log_path: str,
                       environment: Optional[dict] = None) -> bytes:
    """A one-shot LaunchAgent that runs ``harness cutover --execute`` once, in the user's GUI
    session and outside the session the move ends, the launchd counterpart of the transient
    systemd unit. ``RunAtLoad`` starts it when it is bootstrapped; there is no ``KeepAlive``,
    so launchd never runs it again, and the job removes its own plist when it finishes.
    Everything it prints goes to *log_path*."""
    if not program_argv or not os.path.isabs(program_argv[0]):
        raise ValueError(f"launchd runs a program by its absolute path, not {program_argv[:1]!r}")
    plist = {
        "Label": cutover_label(card),
        "ProgramArguments": list(program_argv),
        "RunAtLoad": True,
        "KeepAlive": False,
        "LimitLoadToSessionType": "Aqua",
        "StandardOutPath": log_path,
        "StandardErrorPath": log_path,
    }
    if environment:
        plist["EnvironmentVariables"] = dict(environment)
    return plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True)


# ---------------------------------------------------------------------------
# The grant probe: one run from the launchd context (MIS-0002-R64)
# ---------------------------------------------------------------------------

#: How long the probe may take, a permission dialog it raises included.
GRANT_PROBE_TIMEOUT_S = 120.0


def grant_probe_label(card: str) -> str:
    return pd_label(card) + ".grant_probe"


def render_grant_probe_agent(card: str, python: str, out: str, grants: List[str],
                             log_dir: str) -> bytes:
    """A one-shot LaunchAgent that runs the grant probe with the daemon's own interpreter.

    A grant attaches to the responsible process, which for a launchd job is the job's own
    program, so the probe runs as the daemon would: the same interpreter, started by launchd
    in the user's GUI session. A probe run from the terminal would test the terminal's grant.
    """
    label = grant_probe_label(card)
    plist = {
        "Label": label,
        # Run exactly as the daemon runs (no -I), so the probe imports the macf it imports.
        "ProgramArguments": [python, "-m", "macf.platform.grants", out, *grants],
        "RunAtLoad": True,
        "KeepAlive": False,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Interactive",
        "StandardOutPath": f"{log_dir}/{label}.out.log",
        "StandardErrorPath": f"{log_dir}/{label}.err.log",
    }
    return plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True)


def run_grant_probe(card: str, python: str, grants: List[str], work_dir: str, log_dir: str,
                    uid: int, run, timeout: float = GRANT_PROBE_TIMEOUT_S, sleep=None) -> dict:
    """Run the probe once under launchd and return each grant's verdict.

    The job is loaded from *work_dir*, never ~/Library/LaunchAgents, and booted out whatever
    happens, so nothing of it is left to start at the next login. Raises ``RuntimeError``
    with launchctl's words when it can't be loaded or doesn't answer in time.
    """
    import json
    import os
    import time
    sleep = sleep or time.sleep
    label = grant_probe_label(card)
    plist_path = os.path.join(work_dir, f"{label}.plist")
    out = os.path.join(work_dir, f"{label}.json")
    for stale in (out, plist_path):
        if os.path.exists(stale):
            os.unlink(stale)
    run(launchctl_argv("bootout", label, uid))          # a probe left from an interrupted run
    write_text_atomic(plist_path, render_grant_probe_agent(card, python, out, grants, log_dir).decode())
    try:
        loaded = run(launchctl_argv("bootstrap", label, uid, plist_path))
        if loaded.returncode != 0:
            raise RuntimeError(f"the grant probe wasn't loaded: "
                               f"{(loaded.stderr or '').strip() or f'launchctl exit {loaded.returncode}'}")
        deadline = time.monotonic() + timeout
        while not os.path.exists(out):
            if time.monotonic() > deadline:
                raise RuntimeError(f"the grant probe didn't answer within {timeout:g} s; see "
                                   f"{log_dir}/{label}.err.log")
            sleep(0.2)
        with open(out) as f:
            return json.load(f)
    finally:
        run(launchctl_argv("bootout", label, uid))
        for done in (plist_path, out):
            if os.path.exists(done):
                os.unlink(done)
