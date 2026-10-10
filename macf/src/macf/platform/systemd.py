"""The Linux rendering of a primal daemon: a systemd user unit, kept running by linger.

On Linux the user's systemd instance is the outer tier. ``Restart=always`` restarts the
daemon whenever it exits, clean exit included (MIS-0002-R03 (outer_tier_MUST_restart_pd)),
and ``StartLimitIntervalSec=0`` in ``[Unit]`` keeps systemd from giving up after a burst
of quick exits: in ``[Service]`` that key is ignored by current systemd, and the daemon
would stay down after its fifth fast crash. Linger keeps the user's instance, and so the
daemon, running with no login session; it is the operator's switch
(``loginctl enable-linger``), reported here and never flipped.

Rendering only, as ``launchd.py`` is for macOS. Nothing here runs systemctl; the argv it
builds is for the installer.
"""
import re
import subprocess
import sys
from typing import List, Optional, Tuple

from macf.pd import interface

_VERBS = ("daemon-reload", "enable", "disable", "start", "stop", "restart", "show")
_SAFE = re.compile(r"^[A-Za-z0-9_@%+=:,./-]+$")


def exec_quote(arg: str) -> str:
    """One argument as systemd's ExecStart parses it: ``%`` doubled (specifier), ``$``
    doubled (variable), and quoted in double quotes when it holds anything else."""
    escaped = arg.replace("%", "%%").replace("$", "$$")
    if escaped and _SAFE.match(escaped):
        return escaped
    return '"' + escaped.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_pd_user_unit(card: str, program_argv: List[str], home: str) -> Tuple[str, str]:
    """The user unit for one agent's primal daemon, and where it belongs.

    The unit's name comes from the step 1 interface (``maceff_pd-<id>.service``, MIS-0002-R06
    (pd_identifiers_MUST_use_maceff_pd)). *program_argv* starts the daemon and names the
    agent home; the unit carries no declaration, no agent configuration and no environment
    (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)), so the daemon reads everything
    from the home it is given (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)).
    """
    if not program_argv:
        raise ValueError("program_argv is empty")
    unit = interface.systemd_unit(card)
    text = (
        "[Unit]\n"
        f"Description=MacEff primal daemon of {card} (MIS-0002)\n"
        # In [Unit]: never stop restarting, however often it exits (R03).
        "StartLimitIntervalSec=0\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={' '.join(exec_quote(a) for a in program_argv)}\n"
        "Restart=always\n"
        "RestartSec=10\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )
    return f"{home}/.config/systemd/user/{unit}", text


def systemctl_argv(verb: str, unit: Optional[str] = None) -> List[str]:
    """The ``systemctl --user`` command for *verb*. ``enable`` also starts the unit."""
    if verb not in _VERBS:
        raise ValueError(f"unsupported systemctl verb {verb!r}; use one of {', '.join(_VERBS)}")
    if verb == "daemon-reload":
        return ["systemctl", "--user", "daemon-reload"]
    if not unit:
        raise ValueError(f"{verb} needs the unit")
    if verb == "enable":
        return ["systemctl", "--user", "enable", "--now", unit]
    if verb == "show":
        return ["systemctl", "--user", "show", "-p", "ActiveState,SubState,NRestarts,MainPID", unit]
    return ["systemctl", "--user", verb, unit]


def linger_enabled(user: str) -> Optional[bool]:
    """Whether *user*'s systemd instance outlives their logins, or None if it cannot be read.

    Without linger the daemon stops at the user's last logout and the outer tier is not
    one. Turning it on (``loginctl enable-linger``) is the operator's decision on the host.
    """
    try:
        done = subprocess.run(["loginctl", "show-user", user, "-p", "Linger"],
                              capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"⚠️ MACF: cannot read linger for {user}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    out, err = done.stdout.strip(), done.stderr.strip()
    if out == "Linger=yes":
        return True
    if out == "Linger=no":
        return False
    # A user with no session and no linger is answered as an error ("... is not logged in
    # or lingering", measured on systemd 259): that is a definite no, not unknown.
    if "not logged in or lingering" in err:
        return False
    print(f"⚠️ MACF: cannot read linger for {user}: loginctl said {err or out or 'nothing'!r}",
          file=sys.stderr)
    return None
