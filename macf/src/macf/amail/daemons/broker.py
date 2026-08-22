#!/opt/maceff-venv/bin/python
"""amail broker daemon -- unprivileged entry point (pickup-box model).

Replaces the hand-launched testbed broker (/opt/amail_testbed_broker.py), whose
docstring required root "because the broker delivers into homes it does not
own". That requirement was inherited from one design choice, not derived from
an operation; the pickup-box model deleted the choice. This broker writes only
its OWN stores (audit, quarantine, pickup boxes) and reads the ingest spool by
group. Root appears nowhere on the mail path -- and this entry point REFUSES
to run as root, so a deployment cannot quietly regress to the old model.

Configuration is declarative: /etc/amail/broker_config.json, validated by
macf.amail.deploy_config.BrokerDeployConfig (Pydantic, extra="forbid" -- a
misspelled key refuses to start rather than silently changing what the broker
enforces). The file is root-owned and read-only to the broker uid: the broker
must not be able to rewrite its own authority. See the model's field
descriptions for the schema; there is deliberately no copy of it here to
drift.

Deployment prerequisites (root, at provision time -- setup is not the mail
path, so privilege there does not violate the no-privilege property):
  - the broker uid exists and owns the audit/quarantine/handoff stores and
    the socket directory (serve() must be able to bind there);
  - each pickup box handoff/<agent>/ is broker-owned, group = the
    recipient's group, mode 2770 (the inbound consumer also creates these
    on demand).

Run:  su -s /bin/sh amail_broker -c 'python -m macf.amail.daemons.broker'
"""
import json
import os
import signal
import sys
from pathlib import Path

from pydantic import ValidationError

from macf.amail import Broker, serve
from macf.amail.deploy_config import (BrokerDeployConfig, ConfigError,
                                      load_declarative_config)

CONFIG_PATH = Path(os.environ.get("AMAIL_BROKER_CONFIG",
                                  "/etc/amail/broker_config.yaml"))


def main() -> int:
    if os.geteuid() == 0:
        print("refusing to run as root: the pickup-box model needs no privilege "
              "anywhere on the mail path, so a root broker is a regression, not "
              "a convenience. Run as the dedicated broker uid.", file=sys.stderr)
        return 1
    try:
        raw = load_declarative_config(CONFIG_PATH)
    except ConfigError as e:
        # The loader distinguishes absent / unreadable / malformed / empty and
        # says which -- each sends the reader somewhere different, and
        # collapsing them to "config error" makes them check all four.
        print(f"refusing to start: {e}", file=sys.stderr)
        return 1
    try:
        cfg = BrokerDeployConfig.model_validate(raw).to_broker_config()
    except ValidationError as e:
        # Pydantic names every offending key and why; that is the whole message.
        print(f"refusing to start: config at {CONFIG_PATH} is invalid:\n{e}",
              file=sys.stderr)
        return 1

    try:
        server = serve(Broker(cfg))  # binds the socket, chmods 0666, serves in a thread
    except PermissionError as e:
        # serve() refuses on exposed credentials, writable contact lists, and
        # an empty uid table. Each message names its own remedy; pass it through.
        print(f"refusing to start: {e}", file=sys.stderr)
        return 1

    print(f"amail broker (unprivileged, uid {os.geteuid()}) serving on "
          f"{cfg.socket_path}", flush=True)
    print(f"  domain: {cfg.domain}", flush=True)
    print("  agents: " + ", ".join(
        f"{n}(uid {u})" for u, n in sorted(cfg.agent_uids.items())), flush=True)
    print(f"  handoff: {cfg.inbound_handoff}  quarantine: {cfg.inbound_quarantine}",
          flush=True)

    stop = signal.sigwait({signal.SIGTERM, signal.SIGINT})
    print(f"shutting down on {signal.Signals(stop).name}", flush=True)
    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
