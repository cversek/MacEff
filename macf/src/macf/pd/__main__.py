"""``python -m macf.pd <agent home>``: run one agent's primal daemon.

The agent home is the only argument (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)).
It is also made this process's own agent home, so everything the daemon writes lands in
that agent's event log whatever the service manager's working directory is; a unit
still gets only its declared environment.

Exit codes: 0 after a clean stop, 75 when the agent's daemon already runs (another
start will not help), 78 when the home or its declaration is unusable (nothing a
restart can fix).
"""
import argparse
import os
import signal
import sys
from pathlib import Path

from macf.pd.core import POLICY_POINTER, DeclarationRefused
from macf.pd.daemon import AlreadyRunning, Daemon


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m macf.pd",
                                     description="Run an agent's primal daemon.")
    parser.add_argument("agent_home", type=Path, help="the agent's home directory")
    args = parser.parse_args(argv)
    home = args.agent_home.resolve()

    os.environ["MACEFF_AGENT_HOME_DIR"] = str(home)
    # A log path inherited from whatever started us would send this agent's events
    # elsewhere; the home decides.
    os.environ.pop("MACF_EVENTS_LOG_PATH", None)

    try:
        daemon = Daemon(home)
        daemon.start()
    except AlreadyRunning as e:
        print(f"maceff_pd: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 75
    except (DeclarationRefused, OSError) as e:
        print(f"maceff_pd: cannot start for {home}: {e}\n{POLICY_POINTER}", file=sys.stderr)
        return 78

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: daemon.stop())
    daemon.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
