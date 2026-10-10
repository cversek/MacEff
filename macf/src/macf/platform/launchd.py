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
import plistlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

PD_IDENTIFIER = "maceff_pd"
_VERBS = ("bootstrap", "bootout", "kickstart", "print")


def pd_label(card: str) -> str:
    """The launchd label for one agent's primal daemon: ``maceff_pd.<session identifier>``.

    MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd) names the identifier, and the
    calling card from the identity file makes it one per agent, never the environment
    (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)). The card maps to a name the
    same way every other surface of the daemon names it (the step-1 interface's
    ``session_identifier``), so ``IraMacEff@ee9a78`` becomes ``maceff_pd.IraMacEff_ee9a78``.
    """
    from macf.utils.identity import session_identifier
    if not card or "@" not in card:
        raise ValueError(f"not a calling card: {card!r} (expected Name@hexid)")
    ident = session_identifier(card)
    if not ident or "/" in ident:
        raise ValueError(f"not a calling card: {card!r}")
    return f"{PD_IDENTIFIER}.{ident}"


def render_pd_launch_agent(card: str, program_argv: List[str], home: str,
                           log_dir: str) -> Tuple[str, bytes]:
    """The plist for one agent's primal daemon, and where it belongs.

    *program_argv* starts the daemon; the plist carries no declaration and no agent
    configuration (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)), and no
    identity in its environment.
    """
    if not program_argv:
        raise ValueError("program_argv is empty")
    label = pd_label(card)
    plist = {
        "Label": label,
        "ProgramArguments": list(program_argv),
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 10,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Background",
        "StandardOutPath": f"{log_dir}/{label}.out.log",
        "StandardErrorPath": f"{log_dir}/{label}.err.log",
    }
    path = f"{home}/Library/LaunchAgents/{label}.plist"
    return path, plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True)


def launchctl_argv(verb: str, label: str, uid: int, plist_path: Optional[str] = None) -> List[str]:
    """The launchctl command for *verb* on this user's GUI domain.

    Only the domain-target verbs are offered; the legacy load/unload are not.
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
    """One thing an install or removal does: write or remove a file, or run launchctl."""

    what: str
    path: Optional[str] = None
    content: Optional[bytes] = None
    argv: Optional[List[str]] = None

    def describe(self) -> str:
        if self.what == "launchctl":
            return " ".join(self.argv or [])
        return f"{self.what} {self.path}"


def check_socket_path(path: str) -> None:
    """MIS-0002-R129 (adapter_MUST_check_socket_path_length): refuse, with the reason, a
    socket path the kernel would refuse at bind with a bare error."""
    from macf.amail.broker import SUN_PATH_MAX
    size = len(str(path).encode())
    if size > SUN_PATH_MAX:
        raise ValueError(f"socket path {path} is {size} bytes; this platform allows {SUN_PATH_MAX}. "
                         f"Use a shorter runtime directory.")


def install_plan(card: str, program_argv: List[str], home: str, log_dir: str, uid: int,
                 socket_paths: List[str]) -> List[Step]:
    """What installing one agent's primal daemon does, in order, without doing it.

    Every socket path the daemon will bind is checked first, so a path that cannot work
    stops the install before anything is written (R129).
    """
    for sp in socket_paths:
        check_socket_path(sp)
    path, data = render_pd_launch_agent(card, program_argv, home, log_dir)
    return [Step("write", path=path, content=data),
            Step("launchctl", argv=launchctl_argv("bootstrap", pd_label(card), uid, plist_path=path))]


def uninstall_plan(card: str, home: str, uid: int) -> List[Step]:
    """What removing one agent's primal daemon does: boot it out, then remove its plist."""
    label = pd_label(card)
    return [Step("launchctl", argv=launchctl_argv("bootout", label, uid)),
            Step("remove", path=f"{home}/Library/LaunchAgents/{label}.plist")]


def apply_plan(steps: List[Step], run=None, force: bool = False) -> List[str]:
    """Carry out a plan. A plist that exists and differs is not overwritten without ``force``.

    Returns one line per step. Stops at the first launchctl failure and raises with its
    output, so a half-done install is said, not hidden.
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
    for s in steps:
        if s.what == "write":
            os.makedirs(os.path.dirname(s.path), exist_ok=True)
            with open(s.path, "wb") as fh:
                fh.write(s.content)
        elif s.what == "remove":
            if os.path.exists(s.path):
                os.unlink(s.path)
        elif s.what == "launchctl":
            r = run(s.argv)
            if r.returncode != 0:
                raise RuntimeError(f"{s.describe()} failed ({r.returncode}): {(r.stderr or r.stdout).strip()}")
        done.append(s.describe())
    return done


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
