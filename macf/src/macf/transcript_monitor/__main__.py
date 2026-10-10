"""One transcript monitor: ``python -m macf.transcript_monitor``.

Started by ``macf_tools transcript-monitor start``, and by the hook and commands
that call it. The module name is what ``ps`` shows for a monitor, and how
``daemon.find_monitors`` finds the monitors that run.
"""
import argparse
import sys
from pathlib import Path

from .daemon import DEFAULT_POLL_INTERVAL, run_monitor


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m macf.transcript_monitor",
        description="Watch one Claude Code transcript and record what it shows as events.",
    )
    parser.add_argument("--interval", type=float, default=DEFAULT_POLL_INTERVAL,
                        help="seconds between polls")
    parser.add_argument("--owner", type=int, default=0,
                        help="the Claude Code process served; the monitor stops when it ends "
                             "(0: run until stopped)")
    parser.add_argument("--transcript", type=Path, required=True,
                        help="the transcript to watch")
    args = parser.parse_args(argv)
    return run_monitor(args.transcript, args.interval, args.owner)


if __name__ == "__main__":
    sys.exit(main())
