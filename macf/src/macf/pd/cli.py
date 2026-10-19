"""``macf_tools pd``: the agent's primal daemon, from the command line.

``status`` reads; ``install`` and ``uninstall`` put the daemon under this platform's service
manager and take it out. Starting, stopping and restarting a unit over the control socket
must name who asks (MIS-0002-R52 (control_act_MUST_name_who_asked)), and which asker a
command line typed in a session claims is still an open question, so no unit act is here.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple


def add_pd_parser(sub) -> None:
    pd = sub.add_parser("pd", help="the agent's primal daemon and its units (policy: persistent_layer)")
    pd_sub = pd.add_subparsers(dest="pd_cmd")
    show = pd_sub.add_parser(
        "status", help="each declared unit's state: from the daemon when it checks out, "
                       "else from the event log, saying which")
    show.add_argument("--json", action="store_true", help="one JSON object")
    show.set_defaults(func=cmd_pd_status)
    inst = pd_sub.add_parser(
        "install", help="put this agent's primal daemon under the platform's service manager and "
                        "start it; a declaration that fails installs nothing")
    inst.add_argument("--plan", action="store_true", help="print the unit it would install, and change nothing")
    inst.add_argument("--force", action="store_true", help="replace an installed unit that differs")
    inst.set_defaults(func=cmd_pd_install)
    rm = pd_sub.add_parser(
        "uninstall", help="stop this agent's primal daemon and remove its unit; the units it "
                          "supervises keep running, for a later daemon to adopt")
    rm.set_defaults(func=cmd_pd_uninstall)
    alive = pd_sub.add_parser(
        "alive", help="write one liveness event for the unit this process runs as (for shell "
                      "units, once per pass); does nothing outside a primal daemon (MIS-0002-R14)")
    alive.add_argument("--pid", type=int, default=None,
                       help="the unit's own process (default: the parent of this command, the loop "
                            "that runs it; the daemon credits only the process it started)")
    alive.add_argument("--in-flight", type=int, default=None, metavar="N",
                       help="work started and not finished, which the daemon checks before a restart")
    alive.set_defaults(func=cmd_pd_alive)


def cmd_pd_alive(args: argparse.Namespace) -> int:
    """0 when written, or when the environment names no unit (run outside a daemon); 1 when it
    names one unusably or the event log refused the write."""
    from macf.pd import liveness
    if not (os.environ.get(liveness.ENV_UNIT) or os.environ.get(liveness.ENV_INTERVAL)):
        return 0
    found = liveness.unit_from_env()
    if found is None:
        return 1
    pid = args.pid or os.getppid()
    return 0 if liveness.emit(found.card, found.unit, found.interval_s, args.in_flight, pid=pid) else 1


def _when(epoch: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(epoch)) if epoch else "never"


def cmd_pd_status(args: argparse.Namespace) -> int:
    # Every macf_tools call builds the parser, so what only this command needs
    # (pydantic, through the interface) is imported when it runs.
    from dataclasses import asdict

    from macf.pd.client import status
    from macf.pd.core import POLICY_POINTER, DeclarationRefused
    from macf.pd.daemon import card_for_home
    from macf.utils.paths import find_agent_home

    home = find_agent_home()
    try:
        card = card_for_home(home)
    except DeclarationRefused as e:
        print(f"maceff_pd: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    report = status(home, card)
    if args.json:
        print(json.dumps(asdict(report), default=str))
        return 0
    if report.source == "none":
        print(f"{card}: {report.why}")
        _say_tray(report)
        return 0
    print(f"{card}: from the {report.source} ({report.why})")
    for unit in report.units:
        line = f"  {unit['unit']}: {unit.get('state') or 'no state recorded'}"
        if unit.get("pid"):
            line += f", pid {unit['pid']}"
        line += f", since {_when(unit.get('since'))}"
        if unit.get("restart_held_until"):
            line += f"; restart held until {unit['restart_held_until']} (quiet window)"
        if "liveness" in unit:
            line += f"; liveness {unit['liveness']}: {unit['detail']}"
        print(line)
    for s in report.schedules:
        print(f"  schedule {s['schedule']}: {s['verdict']}: {s['detail']}")
    if report.runs:
        print(f"  runs: {report.runs}")
    _say_tray(report)
    return 0


def _say_tray(report) -> None:
    # Whether this host can show the tray, and why not (MIS-0002-R73
    # (readout_MUST_say_tray_unavailable)). A report built without it says nothing.
    if report.tray:
        print(report.tray)


def _this_agent():
    """The agent home, resolved, and the card its own files name, or the refusal's reason."""
    from pathlib import Path

    from macf.pd.daemon import card_for_home
    from macf.utils.paths import find_agent_home

    home = Path(find_agent_home()).resolve()
    return home, card_for_home(home)


#: What the service manager passes the daemon's interpreter: who and where it is, and none of the
#: installing shell's Python settings (``PYTHONPATH``, ``PYTHONHOME``, a virtualenv's), which the
#: unit doesn't carry.
_SERVICE_ENV_KEEP = ("HOME", "USER", "LOGNAME", "SHELL", "TMPDIR", "LANG")
_SERVICE_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def daemon_macf(python: str) -> Tuple[Optional[Path], str]:
    """The macf that ``python -m macf.pd`` imports when the service manager runs it, or None and
    why not. Asked of the interpreter itself, from ``/`` and without the installing shell's Python
    settings, because the unit carries neither (#650)."""
    env = {k: os.environ[k] for k in _SERVICE_ENV_KEEP if k in os.environ}
    env["PATH"] = _SERVICE_PATH
    try:
        out = subprocess.run([python, "-c", "import macf.pd, macf; print(macf.__file__)"],
                             cwd="/", env=env, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    if out.returncode != 0:
        lines = out.stderr.strip().splitlines()
        return None, lines[-1] if lines else f"exit {out.returncode}"
    return Path(out.stdout.strip()).resolve().parent, ""


def cmd_pd_install(args: argparse.Namespace) -> int:
    from macf.pd import adapter as adapters
    from macf.pd.core import POLICY_POINTER, DeclarationRefused, load_declaration

    from macf.pd import allowlist

    try:
        home, card = _this_agent()
        declaration = load_declaration(home, card)
        tier = adapters.adapter_for(sys.platform)
    except (DeclarationRefused, LookupError) as e:
        print(f"maceff_pd: nothing installed: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    try:
        mismatch = allowlist.findings(declaration, allowlist.managed_allowlist())
    except (OSError, ValueError) as e:
        mismatch = [f"the managed settings can't be read, so the organization allowlist can't be "
                    f"compared with the declaration: {e}"]
    if mismatch:
        # A channel the allowlist leaves out stops loading at the daemon's first unattended
        # restart, so the install stops here, where a person reads the reason.
        print("maceff_pd: nothing installed:\n" + "\n".join(f"- {m}" for m in mismatch)
              + f"\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    import macf
    planned = Path(macf.__file__).resolve().parent
    daemon, why = daemon_macf(sys.executable)
    if daemon != planned:
        # The unit runs this interpreter with no environment of the shell's, so the macf it
        # names must be the one the daemon will import, or the daemon runs other code, or none.
        found = f"imports macf from {daemon}" if daemon else f"can't import macf.pd ({why})"
        print(f"maceff_pd: nothing {'planned' if args.plan else 'installed'}: run as the service manager "
              f"runs it, {sys.executable} {found}, not the macf this command runs ({planned}). Install "
              f"from an interpreter whose own macf is the one the daemon should run, such as a virtual "
              f"environment it is installed in.\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    runs = f"it runs {sys.executable}, with macf from {planned}"
    if args.plan:
        print(f"# {card}: the outer tier for {home} on {sys.platform}, not installed (--plan); {runs}")
        print(tier.render(card, home))
        return 0
    # Recorded before the service manager can start the daemon: launchd starts it at load
    # (RunAtLoad), and a daemon that read no record would refuse every schedule.
    _record_schedules(card, declaration, home)
    # Before the install too: the daemon reads the newest grant probe when it starts, and
    # launchd starts it at load, so a probe recorded after would wait for its next start.
    _probe_grants(tier, card, declaration, home)
    try:
        where = tier.install(card, home, force=args.force)
    except (OSError, RuntimeError) as e:
        print(f"maceff_pd: install stopped: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    print(f"{card}: installed at {where}; {runs}; the service manager says: {tier.status(card)}")
    if sys.platform.startswith("linux"):
        import os
        import pwd

        from macf.platform.systemd import linger_enabled
        if linger_enabled(pwd.getpwuid(os.getuid()).pw_name) is False:
            print("note: linger is off, so the daemon stops at your last logout; "
                  "`loginctl enable-linger` keeps it running, and is the host operator's call")
    return 0


#: The event each grant's verdict at install is recorded as; the daemon reads the newest
#: at start and raises a notice for each denied one (MIS-0002-R65).
EVENT_GRANT_PROBE = "pd_grant_probe"


def _probe_grants(tier, card: str, declaration, home: Path) -> None:
    """Test each unit's declared grants from the service manager's context, once, now that a
    person ran the install (MIS-0002-R64 (adapter_MUST_test_grants_at_install)). A probe can
    raise a permission dialog, so it runs only here, never at an unattended start."""
    from macf.agent_events_log import append_event
    wanted = {u.name: list(u.privacy_grants) for u in declaration.units if u.privacy_grants}
    probe = getattr(tier, "probe_grants", None)
    if not wanted or probe is None:
        return                         # nothing declared, or a platform with no grants to test
    grants = sorted({g for gs in wanted.values() for g in gs})
    print(f"testing the declared grants from the service manager's context: {', '.join(grants)}. "
          f"macOS may ask you to allow one; answer it at this Mac.")
    try:
        verdicts = probe(card, home, grants)
    except (OSError, RuntimeError) as e:
        print(f"⚠️ MACF: pd: the grants weren't tested: {e}", file=sys.stderr)
        append_event(EVENT_GRANT_PROBE, {"agent": card, "tested": False, "why": str(e)})
        return
    for unit, unit_grants in sorted(wanted.items()):
        for grant in unit_grants:
            verdict = verdicts.get(grant, "untested: the probe gave no answer")
            print(f"  {unit}: {grant}: {verdict}")
    append_event(EVENT_GRANT_PROBE, {"agent": card, "tested": True, "units": wanted, "verdicts": verdicts})
    denied = sorted(g for g, v in verdicts.items() if v == "denied")
    if denied:
        print(f"⚠️ MACF: pd: denied: {', '.join(denied)}. Grant each in System Settings, Privacy & "
              f"Security, to {sys.executable}, then run pd install again; until then the daemon "
              f"notices it at each start.", file=sys.stderr)


def _record_schedules(card: str, declaration, home: Path) -> None:
    """Record each schedule's digest as installed, the record a host's daemon checks its
    declaration against at start (MIS-0002-R33 (run_MUST-NOT_change_schedules))."""
    from macf.agent_events_log import append_event
    from macf.pd.names import rendered_declaration_path
    from macf.pd.scheduler import EVENT_INSTALLED, schedule_digests
    if rendered_declaration_path(home).exists():
        return  # noqa: MACEFF003 - a rendered declaration is out of the agent's reach; nothing to check
    digests = schedule_digests(declaration, home)
    if not append_event(EVENT_INSTALLED, {"agent": card, "digests": digests}):
        print("⚠️ MACF: pd: the schedules were not recorded as installed, so the daemon won't run "
              "them; run pd install again", file=sys.stderr)
    elif digests:
        print(f"schedules recorded as installed: {', '.join(sorted(digests))}. A change to one "
              f"isn't run until pd install runs again, and the daemon reads it when it next starts.")


def cmd_pd_uninstall(args: argparse.Namespace) -> int:
    from macf.pd import adapter as adapters
    from macf.pd.core import POLICY_POINTER, DeclarationRefused

    try:
        _home, card = _this_agent()
        tier = adapters.adapter_for(sys.platform)
        tier.uninstall(card)
    except (DeclarationRefused, LookupError, OSError, RuntimeError) as e:
        print(f"maceff_pd: uninstall stopped: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 1
    # The service manager can return before the service is gone (launchctl bootout does),
    # so the line waits briefly for it rather than reporting a state that's already ending.
    deadline = time.monotonic() + UNINSTALL_WAIT_S
    said = tier.status(card)
    while not _gone(said) and time.monotonic() < deadline:
        time.sleep(0.2)
        said = tier.status(card)
    if _gone(said):
        print(f"{card}: uninstalled; the service manager no longer has it")
    else:
        print(f"{card}: uninstalled, but after {UNINSTALL_WAIT_S:g} s the service manager still says: {said}")
    return 0


#: How long uninstall waits for the service manager to let the daemon's service go.
UNINSTALL_WAIT_S = 5.0


def _gone(said: str) -> bool:
    """Whether a status line says the service is no longer loaded: launchd's "not loaded",
    or systemd's LoadState=not-found."""
    return said.startswith("not loaded") or "LoadState=not-found" in said
