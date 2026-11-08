"""``python -m macf.pd <agent home>``: run one agent's primal daemon.

The agent home is the only argument (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)).
It is also made this process's own agent home, so everything the daemon writes lands in
that agent's event log whatever the service manager's working directory is; a unit
still gets only its declared environment.

A signal ends the daemon and leaves its units running for the next daemon to adopt, so
a restart through the outer tier restarts the daemon alone.

Exit codes: 0 after a clean stop, 75 when the agent's daemon already runs (another
start will not help), 78 when the home or its declaration is unusable (nothing a
restart can fix).

A start that ends with 75 or 78 holds for ``MACF_PD_REFUSED_HOLD_S`` seconds (60 by default)
before it exits. launchd's KeepAlive relaunches a job whatever its exit status, every
ThrottleInterval, so without the hold a refused daemon was started again every ten seconds,
each time writing the same refusal (#921). The hold paces any outer tier the same way.
"""
import argparse
import os
import signal
import sys
import time
from pathlib import Path

#: How long a refused start waits before exiting, unless the environment says otherwise.
REFUSED_HOLD_S = 60.0


def refused_hold_s(environ=os.environ) -> float:
    try:
        return max(0.0, float(environ.get("MACF_PD_REFUSED_HOLD_S", REFUSED_HOLD_S)))
    except ValueError:
        return REFUSED_HOLD_S

from macf.pd.core import POLICY_POINTER, DeclarationRefused
from macf.pd.daemon import AlreadyRunning, Daemon
from macf.pd.names import name_this_process


def main(argv=None, hold=time.sleep) -> int:
    parser = argparse.ArgumentParser(prog="python -m macf.pd",
                                     description="Run an agent's primal daemon.")
    parser.add_argument("agent_home", type=Path, help="the agent's home directory")
    args = parser.parse_args(argv)
    home = args.agent_home.resolve()
    # A process listing shows maceff_pd, not the interpreter (MIS-0002-R06); Linux only.
    name_this_process()

    os.environ["MACEFF_AGENT_HOME_DIR"] = str(home)
    # A log path inherited from whatever started us would send this agent's events
    # elsewhere; the home decides.
    os.environ.pop("MACF_EVENTS_LOG_PATH", None)

    try:
        daemon = Daemon(home)
        daemon.start()
    except AlreadyRunning as e:
        print(f"maceff_pd: {e}\n{POLICY_POINTER}", file=sys.stderr)
        hold(refused_hold_s())
        return 75
    except (DeclarationRefused, OSError) as e:
        print(f"maceff_pd: cannot start for {home}: {e}\n{POLICY_POINTER}", file=sys.stderr)
        hold(refused_hold_s())
        return 78

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: daemon.stop())
    daemon.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
