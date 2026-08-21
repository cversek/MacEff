#!/opt/maceff-venv/bin/python
"""Inbound spool consumer -- the deployment entry point for macf.amail.inbound.

Runs UNPRIVILEGED as the broker's dedicated uid (amail_broker). The
pickup-box model removes every root requirement from the mail path: the
consumer reads the spool via group membership (the receiver stays sole
WRITER), authorizes, and hands accepted mail into a per-recipient pickup
box it owns; the RECIPIENT ingests into its own store as itself, so no
component ever writes across a uid boundary. Configuration is a JSON file,
not flags, so what the consumer will do is inspectable before it does it.

Verbs, deliberately separated so the real-mail acceptance battery can be
driven step by step by the OPERATOR rather than fired as a side effect:

    check      load config, validate push-grant eligibility, verify the
               spool is CONSUMABLE, report what WOULD be processed.
               Touches nothing.
    process    drain the spool once: verify, authorize, deliver or
               quarantine, audit. THE OPERATOR CALLS WHEN THIS RUNS during
               an acceptance battery, and it stays exactly as it was so
               that cadence remains available.
    watch      unattended mode: `process` on an interval, plus the aged
               sweep on its own cadence, publishing a heartbeat an outside
               observer can age out. Running it is a deliberate deployment
               act, never a default.
    sweep      the orphan sweep alone: quarantine aged spool entries, alert
               on pickup entries nobody drained. Exits NON-ZERO on any alert, so
               a scheduler treats a stuck message as a failure rather than
               as output nobody read. Schedule this even when a watcher
               runs -- it is what notices the watcher died.
    reconcile  the conservation check: spooled == terminals + in-flight.

Config (/etc/amail/inbound_config.json):
    domain             mail domain for local agents
    agents             {agent_name: {"home": path}}
                       agent_name is the ADDRESS LOCAL PART; the home may
                       belong to a differently-named account
    contacts_path      the inbound contacts/allowlist file
    audit_path         broker audit log (jsonl)
    spool_dir          the receiver's spool (group-readable to the broker)
    quarantine_dir     broker-owned quarantine
    handoff_dir        broker-owned pickup boxes, handoff_dir/<agent>/ with
                       the agent's group and setgid set by provisioning
    verdict_authority  the authserv-id this deployment trusts
    push_wake_enabled  optional, default false (the wake mechanism is not
                       built; a granted sender delivers as pull, visibly)
"""
import json
import os
import signal
import sys
import time
from pathlib import Path

CONFIG_PATH = Path("/etc/amail/inbound_config.json")


def load_config():
    """Load through the VALIDATED model, exactly as the broker daemon does.

    This function used to parse the file by hand and build a BrokerConfig from
    four fields. The broker half therefore arrived with no scrubber, no rate
    limiter and no transport, so a non-delivery notice was never scrubbed, was
    charged against no budget, and could not be sent -- while the code
    implementing all three was correct and fully tested. Two entry points to
    one deployment, one validated and one by hand.

    It also re-declared domain, agents, contacts and audit, all of which the
    broker config already carries, so the two could drift apart and did.
    """
    from macf.amail.deploy_config import (InboundDeployConfig, ConfigError,
                                          load_declarative_config)
    from pydantic import ValidationError
    try:
        raw = load_declarative_config(CONFIG_PATH)
    except ConfigError as e:
        print(f"refusing to run: {e}", file=sys.stderr)
        raise SystemExit(2)
    try:
        return InboundDeployConfig.model_validate(raw).to_inbound_config()
    except ValidationError as e:
        # An unknown key refuses to start rather than being ignored: an ignored
        # key in a security config silently changes what the broker enforces.
        print(f"refusing to run: {CONFIG_PATH} did not validate: {e}",
              file=sys.stderr)
        raise SystemExit(2)
    except ConfigError as e:
        # SEPARATE, because this one is about a DIFFERENT FILE. to_inbound_config
        # reads the broker config too, so a failure here is not a fault in the
        # file named above -- and the old handler caught it alongside
        # ValidationError and reported it as "{CONFIG_PATH} did not validate",
        # naming the wrong file to whoever had to fix it.
        print(f"refusing to run: {CONFIG_PATH} is valid, but the broker config "
              f"it references could not be loaded: {e}", file=sys.stderr)
        raise SystemExit(2)



#: Where the watcher stamps its liveness. A watcher that dies silently is the
#: exact failure this project keeps finding, so it publishes a heartbeat an
#: outside observer can age out -- the watcher cannot be the thing that
#: notices it has stopped.
HEARTBEAT = Path(os.environ.get("AMAIL_WATCH_HEARTBEAT",
                                "/var/lib/amail_broker/watch.heartbeat"))


def watch(cfg, inbound) -> int:
    """Drain the spool as mail arrives, and sweep aged entries periodically.

    AUTOSTART, WITH MANUAL PRESERVED. `process` remains exactly as it was: the
    operator-fired verb the acceptance battery depended on, and the one an
    outbound battery will depend on next. This verb is the unattended mode, and
    running it is a deliberate deployment act rather than a default that
    quietly took over.

    Why polling rather than inotify: the spool is a directory a different uid
    writes, entries are seconds-scale not milliseconds-scale, and a poll loop
    has no failure mode where a dropped watch descriptor silently stops
    delivering events forever. The cost is latency measured in seconds; the
    benefit is that the failure modes are the ones already understood.

    THREE THINGS THIS DOES NOT DO, each deliberate:
      - it does not swallow errors from process_spool. An unexpected exception
        propagates and the watcher EXITS, because a watcher that keeps looping
        while every drain fails is indistinguishable from a healthy one.
      - it does not shrink the conservation window silently: auto-draining
        makes in-flight rarer, which makes the aged-entry sweep MORE
        load-bearing, not less. The sweep therefore runs on its own cadence
        inside this loop.
      - it does not assume it is alive. Every cycle stamps the heartbeat, and
        an outside observer (the sweep, a cron check, an operator) ages that
        file out. Self-reported liveness from a hung process is worthless.
    """
    interval = int(os.environ.get("AMAIL_WATCH_INTERVAL", "15"))
    sweep_every = int(os.environ.get("AMAIL_WATCH_SWEEP_INTERVAL", "300"))
    print(f"amail inbound watcher: interval {interval}s, sweep every "
          f"{sweep_every}s, heartbeat {HEARTBEAT}", flush=True)

    stop = {"now": False}

    def _stop(signum, _frame):
        print(f"watcher stopping on {signal.Signals(signum).name}", flush=True)
        stop["now"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    last_sweep = 0.0
    while not stop["now"]:
        cycle_started = time.time()
        results = inbound.process_spool(cfg)
        for r in results:
            print(json.dumps(r, default=str), flush=True)
        if cycle_started - last_sweep >= sweep_every:
            report = inbound.sweep_aged(cfg)
            last_sweep = cycle_started
            if report["alerts"]:
                print(json.dumps({"sweep": report}, default=str), flush=True)
        try:
            HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
            HEARTBEAT.write_text(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "epoch": int(cycle_started),
                "pid": os.getpid(),
                "processed_last_cycle": len(results),
            }) + "\n")
        except OSError as e:
            # A watcher that cannot publish liveness is a watcher nobody can
            # supervise. Say so every cycle rather than degrading quietly.
            print(f"⚠️ MACF: heartbeat write failed ({e}); this watcher is "
                  f"running UNSUPERVISED", file=sys.stderr, flush=True)
        slept = 0.0
        while slept < interval and not stop["now"]:
            time.sleep(0.5)
            slept += 0.5
    return 0


def main() -> int:
    verb = sys.argv[1] if len(sys.argv) > 1 else "check"
    from macf.amail import inbound
    from macf.amail.contacts import ContactBook
    cfg = load_config()

    if verb == "check":
        # Validation only. The push-eligibility sweep is the same fatal gate
        # process would apply; running it here means a bad config is learned
        # from a check, not from a delivery run.
        inbound.assert_push_grants_eligible(
            ContactBook(cfg.broker_config.contacts_path), cfg.broker_config)
        entries = list(cfg.spool_dir.glob("*.eml")) if cfg.spool_dir.exists() else []
        # Consuming a spool requires WRITE on the spool directory (terminal
        # disposition removes the entry). The first live run proved that a
        # check which validates everything except the mutating permission
        # reports green on a consumer that cannot consume -- so probe it
        # here, where a staging mistake is learned from a check, not from a
        # delivery run failing mid-battery.
        spool_consumable = os.access(cfg.spool_dir, os.W_OK) \
            if cfg.spool_dir.exists() else False
        report = {
            "config": "valid", "push_grants": "eligible",
            "spool_entries_waiting": len(entries),
            "entries": [e.name for e in entries],
            "spool_consumable": spool_consumable,
            "push_wake_enabled": cfg.push_wake_enabled,
        }
        print(json.dumps(report, indent=1))
        if not spool_consumable:
            print("check FAILED: spool directory is not writable by this uid "
                  "-- entries can be read but never removed; fix the spool "
                  "dir group-write bit before running process.",
                  file=sys.stderr)
            return 1
        return 0
    if verb == "process":
        results = inbound.process_spool(cfg)
        print(json.dumps(results, indent=1, default=str))
        return 0
    if verb == "sweep":
        # The orphan sweep. Separate verb so it can be scheduled
        # independently of processing -- the sweep must run even when (especially
        # when) the consumer is not.
        report = inbound.sweep_aged(cfg)
        print(json.dumps(report, indent=1))
        # Non-zero on ANY alert: a sweep that found a stuck message and exited 0
        # is the silent-alarm failure this sweep exists to prevent.
        return 1 if report["alerts"] else 0
    if verb == "watch":
        return watch(cfg, inbound)
    if verb == "reconcile":
        report = inbound.reconcile(cfg)
        print(json.dumps(report, indent=1))
        return 0 if report.get("balanced") else 1
    print(f"unknown verb {verb!r}: use check | process | watch | sweep | "
          f"reconcile", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
