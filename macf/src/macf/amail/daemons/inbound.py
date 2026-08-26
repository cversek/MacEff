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
    watchdog   `sweep` plus watcher liveness, on a cadence, IN ITS OWN
               PROCESS. The sweep that runs inside `watch` cannot report the
               watcher's death because it dies with it; this is the one that
               can. Alarms are appended to a durable file and never end the
               loop.
    health     one-shot verdict over both heartbeats and the aged sweep,
               NON-ZERO when unhealthy. The surface a scheduler or an operator
               outside the container calls -- the point where the supervision
               chain reaches something a human sees.
    validate   check the configuration the deployment OBEYS, touching nothing.
               `--contacts <path>` validates a CANDIDATE file that is not
               installed yet, so the operator's sequence is validate-then-
               replace and no window exists in which the deployment obeys
               something nobody checked. Exits non-zero on any failure.
    reconcile  the conservation check: spooled == terminals + in-flight.

Config (/etc/amail/inbound_config.yaml), validated by InboundDeployConfig,
which forbids unknown keys. Required:
    spool_dir          the receiver's spool; this consumer's input
    quarantine_dir     broker-owned quarantine for refused mail
Optional, with defaults:
    handoff_dir        pickup boxes, handoff_dir/<agent>/, broker-owned and
                       recipient-group readable
    verdict_authority  the authserv-id this deployment trusts in
                       Authentication-Results. A verdict stamped by anyone
                       else is treated as ABSENT, never as a failure.
    push_wake_enabled  default false while the wake mechanism is unbuilt
    broker_config_path the BROKER's deployment config, read through the same
                       validated model the broker daemon uses
    contacts_path      OPTIONAL override of the broker's contact list for
                       INBOUND authorization. Null means use the broker's.
    audit_path         OPTIONAL override of the broker's audit log

Domain, agents and the outbound contact authority are NOT here: they come from
the broker's own file via broker_config_path, so a control added there reaches
this entry point without being added in a second place.
"""
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from macf.amail import alerting
from macf.utils.json_io import write_json_safely

#: Overridable for the same reason the broker's is: a startup refusal that can
#: only be demonstrated by editing the file the live deployment obeys cannot be
#: demonstrated safely, so it does not get demonstrated.
CONFIG_PATH = Path(os.environ.get("AMAIL_INBOUND_CONFIG",
                                  "/etc/amail/inbound_config.yaml"))


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
                                          assert_package_current,
                                          explain_validation_error,
                                          load_declarative_config)
    from pydantic import ValidationError
    try:
        raw = load_declarative_config(CONFIG_PATH)
    except ConfigError as e:
        print(f"refusing to run: {e}", file=sys.stderr)
        raise SystemExit(2)
    try:
        # BEFORE the fields, deliberately. A package behind its config rejects
        # every newer key as unknown, and that refusal describes the wrong
        # thing -- checking the version afterwards would leave the misleading
        # error first, which is where the reader stops.
        assert_package_current(raw.get("requires_macf"), CONFIG_PATH)
    except ConfigError as e:
        print(f"refusing to run: {e}", file=sys.stderr)
        raise SystemExit(2)
    try:
        return InboundDeployConfig.model_validate(raw).to_inbound_config()
    except ValidationError as e:
        # An unknown key refuses to start rather than being ignored: an ignored
        # key in a security config silently changes what the broker enforces.
        print(f"refusing to run: {explain_validation_error(CONFIG_PATH, e)}",
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
    failures = 0
    # CUMULATIVE, because the consecutive count is a LEVEL and an observer only
    # samples it. A watcher that fails twice and recovers between every
    # watchdog pass reports zero forever and reads as perfectly healthy --
    # found by measuring rather than by reasoning: a live break/repair cleared
    # inside one watchdog interval and left no trace an observer could see.
    # Flapping is the failure a level cannot express, so publish a counter that
    # only ever goes up.
    failures_total = 0
    last_error = ""
    while not stop["now"]:
        cycle_started = time.time()
        # THE LOOP SURVIVES ITS INPUT. This call parses files the watcher does
        # not control -- a spool the receiver writes, and an authorization file
        # a human edits. A malformed contacts file used to raise here and end
        # the process permanently, while the receiver went on accepting mail
        # nothing would drain: an outage that ACCUMULATED and looked healthy
        # from outside, because the two live services were still answering.
        #
        # A loop-scoped failure has no caller waiting, so "report and return"
        # ends the service rather than answering anyone. Report and CONTINUE:
        # the file may be mid-edit, and the next cycle costs seconds.
        try:
            results = inbound.process_spool(cfg)
            if failures:
                print(f"✅ MACF: spool processing RECOVERED after {failures} "
                      f"consecutive failure(s)", file=sys.stderr, flush=True)
            failures, last_error = 0, ""
        except Exception as e:
            # Broad ON PURPOSE, and this is the one place in the subsystem
            # where that is right: any exception reaching here kills a service
            # no caller is waiting on. Narrowing it means the next unforeseen
            # parse error ends the watcher again, which is the exact defect.
            failures += 1
            failures_total += 1
            last_error = f"{type(e).__name__}: {e}"
            results = []
            print(f"⚠️ MACF: spool processing FAILED ({last_error}); this is "
                  f"consecutive failure {failures}. The watcher is STILL "
                  f"RUNNING and will retry in {interval}s -- mail is spooling "
                  f"and NOT being drained until this clears.",
                  file=sys.stderr, flush=True)
        for r in results:
            print(json.dumps(r, default=str), flush=True)
        if cycle_started - last_sweep >= sweep_every:
            # Same rule one level down: the sweep is the thing that reports
            # stuck mail, so losing it to an unreadable spool entry would
            # remove the alarm exactly when it applies.
            try:
                report = inbound.sweep_aged(cfg)
                if report["alerts"]:
                    print(json.dumps({"sweep": report}, default=str), flush=True)
            except Exception as e:
                print(f"⚠️ MACF: in-loop sweep failed ({type(e).__name__}: {e}); "
                      f"the watchdog's sweep is unaffected", file=sys.stderr,
                      flush=True)
            last_sweep = cycle_started
        # ATOMIC, because the whole point of this file is that ANOTHER process
        # reads it while this one writes. A plain write publishes a truncated
        # heartbeat for the width of the write, and a torn read is reported as
        # UNREADABLE -- which is correctly not-alive, and would page someone
        # about a perfectly healthy watcher.
        if not write_json_safely(HEARTBEAT, {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "epoch": int(cycle_started),
                "pid": os.getpid(),
                "processed_last_cycle": len(results),
                # ALIVE AND FAILING IS NOT ALIVE, and an observer that only
                # asks "is the stamp fresh" cannot tell them apart. Now that
                # the loop survives its input, a wedged watcher stamps a
                # perfectly healthy heartbeat forever while draining nothing --
                # so the fix for one silent failure would have created another
                # if this were not published alongside it.
                "consecutive_failures": failures,
                "failures_total": failures_total,
                "last_error": last_error,
                # PUBLISHED so the observer derives its staleness bound from
                # the real cadence instead of restating it. Two places
                # configuring one interval drift, and the drift is invisible
                # until the bound is wrong in the direction that stays quiet.
                "interval_s": interval,
        }):
            # A watcher that cannot publish liveness is a watcher nobody can
            # supervise. Say so every cycle rather than degrading quietly.
            print(f"⚠️ MACF: heartbeat write failed; this watcher is running "
                  f"UNSUPERVISED", file=sys.stderr, flush=True)
        slept = 0.0
        while slept < interval and not stop["now"]:
            time.sleep(0.5)
            slept += 0.5
    return 0


#: Where the watchdog records what it found. Durable because an alarm printed
#: to a stream nobody tails is the failure it is trying to report.
ALERTS = Path(os.environ.get("AMAIL_ALERTS",
                             "/var/lib/amail_broker/alerts.jsonl"))

#: Where the watchdog stamps its OWN liveness, so the chain does not simply
#: move one level up and stop there.
WD_HEARTBEAT = Path(os.environ.get("AMAIL_WATCHDOG_HEARTBEAT",
                                   "/var/lib/amail_broker/watchdog.heartbeat"))

#: Floor for the staleness bound, in seconds, when the heartbeat does not
#: publish a cadence. Only reached by a watcher predating `interval_s`.
HEARTBEAT_BOUND_FLOOR_S = 300


def _alert(kind: str, detail: str, **fields) -> Dict[str, Any]:
    """Record one alarm, durably and on stderr, and return it.

    Appending is best-effort on purpose: an unwritable alert file must not end
    the watchdog. It degrades to stderr and keeps checking, because the
    alternative is that the supervisor dies of the same class of fault it
    exists to survive.
    """
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "kind": kind,
           "detail": detail, **fields}
    print(f"⚠️ MACF: amail {kind}: {detail}", file=sys.stderr, flush=True)
    try:
        ALERTS.parent.mkdir(parents=True, exist_ok=True)
        with ALERTS.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
    except OSError as e:
        print(f"⚠️ MACF: alert could not be recorded to {ALERTS} ({e}); it "
              f"exists only in this stream", file=sys.stderr, flush=True)
    return rec


def heartbeat_verdict(now: Optional[float] = None) -> Dict[str, Any]:
    """Is the inbound watcher alive? Decided from ITS file, by ANOTHER process.

    Four outcomes and they are deliberately not two. A MISSING heartbeat means
    the watcher never started (or was never meant to); a STALE one means it
    started and stopped; an UNREADABLE one means liveness is unknown, which is
    not the same as healthy; and a FAILING one means it is running and stamping
    while draining nothing. Collapsing any pair sends the reader to the wrong
    remedy -- and FAILING in particular reports as ALIVE to anyone who only
    asks whether the stamp is fresh.
    """
    now = time.time() if now is None else now
    if not HEARTBEAT.exists():
        return {"state": "absent", "detail": f"no heartbeat at {HEARTBEAT}: "
                f"the inbound watcher has never run in this container"}
    try:
        data = json.loads(HEARTBEAT.read_text())
        epoch = float(data.get("epoch", 0))
    except (OSError, ValueError, TypeError) as e:
        return {"state": "unreadable", "detail": f"heartbeat at {HEARTBEAT} "
                f"could not be read ({e}); watcher liveness is UNKNOWN, which "
                f"is not the same as healthy"}
    published = data.get("interval_s")
    bound = max(HEARTBEAT_BOUND_FLOOR_S, int(published) * 10) if published \
        else HEARTBEAT_BOUND_FLOOR_S
    age = now - epoch
    if age > bound:
        return {"state": "stale", "age_s": int(age), "bound_s": bound,
                "pid": data.get("pid"),
                "detail": f"the inbound watcher last stamped {int(age)}s ago "
                          f"(bound {bound}s): it is DEAD, and mail is spooling "
                          f"with nothing draining it"}
    # A FOURTH STATE, added with the retry loop that made it possible. Once the
    # watcher survives a malformed input it keeps stamping a perfectly fresh
    # heartbeat while draining nothing -- so the repair for one silent failure
    # manufactures another unless the observer can see the difference. Fresh is
    # not the same as working.
    failures = int(data.get("consecutive_failures", 0) or 0)
    if failures:
        return {"state": "failing", "age_s": int(age), "bound_s": bound,
                "pid": data.get("pid"), "consecutive_failures": failures,
                "last_error": data.get("last_error", ""),
                "detail": f"the inbound watcher is ALIVE but has failed to "
                          f"process the spool {failures} time(s) in a row "
                          f"({data.get('last_error', 'no detail')}): mail is "
                          f"arriving and NOT being drained"}
    return {"state": "alive", "age_s": int(age), "bound_s": bound,
            "pid": data.get("pid"),
            # Carried on the ALIVE verdict too: a flapping watcher is alive at
            # every sampling instant, so this is the only place the flapping
            # is visible. An observer compares it across passes; a rise between
            # two healthy readings is failure the level could not report.
            "failures_total": int(data.get("failures_total", 0) or 0)}


def _edge_state_path(cfg) -> Path:
    """Where the edge ledger lives.

    Beside the spool rather than in a runtime directory: the ledger must outlive
    a container restart, or every restart re-raises every standing condition and
    level-triggered behaviour returns by the back door.
    """
    base = Path(cfg.spool_dir).parent if getattr(cfg, "spool_dir", None) else Path("/var/lib/amail")
    return base / "alert_edge_state.json"


def _check_once(cfg, inbound) -> List[Dict[str, Any]]:
    """One supervision pass: watcher liveness, then the orphan sweep.

    Returns the alarms raised. Sweep failure is itself an alarm rather than an
    exception out of the loop -- the sweep reads a spool an unprivileged uid
    may lose access to, and losing the sweep silently is the condition being
    guarded against.
    """
    alarms: List[Dict[str, Any]] = []
    hb = heartbeat_verdict()
    if hb["state"] != "alive":
        alarms.append(_alert(f"watcher_{hb['state']}", hb["detail"],
                             **{k: v for k, v in hb.items()
                                if k not in ("state", "detail")}))
    if cfg is None:
        alarms.append(_alert("sweep_unavailable",
                             "config did not load, so the orphan sweep cannot "
                             "run; watcher liveness is still being checked"))
        return alarms
    try:
        report = inbound.sweep_aged(cfg)
    except OSError as e:
        alarms.append(_alert("sweep_failed", f"the orphan sweep could not "
                                             f"complete ({e})"))
        return alarms
    # EDGE-TRIGGERED ON ARRIVAL, NEVER LEVEL-TRIGGERED ON STATE. Without this
    # the sweep re-raises every standing condition on every pass, which is how
    # two undrained messages became thirty-six pages in nine hours. Recovery is
    # a notice too: a reader told when something breaks and never when it heals
    # cannot learn the current state except by asking.
    edge = alerting.EdgeState(_edge_state_path(cfg))
    findings = report.get("findings") or []
    t = edge.transitions(findings)

    for key in t.recovered:
        alarms.append(_alert("cleared", f"resolved: {key}", resolved_key=key))

    if t.new:
        alarms.append(_alert("aged_entries",
                             f"{len(t.new)} new condition(s), "
                             f"{len(t.ongoing)} still standing: "
                             f"{len(report['aged_spool'])} in the spool, "
                             f"{len(report['aged_pickup'])} undrained in "
                             f"pickup boxes",
                             aged_spool=report["aged_spool"],
                             aged_pickup=report["aged_pickup"],
                             new_keys=[f.key for f in t.new],
                             ongoing_keys=[f.key for f in t.ongoing]))

    # Committed AFTER the alarms are built, so a crash between the two re-raises
    # rather than swallows. A lost notice is worse than a repeated one.
    edge.commit(findings)
    return alarms


def watchdog(cfg, inbound) -> int:
    """SUPERVISE THE WATCHER FROM OUTSIDE IT, and sweep on a cadence.

    This exists because the only scheduled sweep in this deployment ran inside
    the watcher's own loop -- co-located with the process whose death it was
    meant to detect, so the two died together, silently, and the receiver went
    on spooling mail nothing would drain. A supervisor must be visible at a
    HIGHER scope than the thing it watches; one that shares a process with it
    is not a supervisor, it is a second symptom.

    It never exits on an alarm. An alarm is the output, not a fault: the
    condition it reports is usually ongoing, and a supervisor that terminates
    on the first thing it finds stops reporting the second. It exits only on a
    stop signal.
    """
    interval = int(os.environ.get("AMAIL_WATCHDOG_INTERVAL", "300"))
    print(f"amail watchdog: every {interval}s, watching {HEARTBEAT}, "
          f"alerts to {ALERTS}", flush=True)

    stop = {"now": False}

    def _stop(signum, _frame):
        print(f"watchdog stopping on {signal.Signals(signum).name}", flush=True)
        stop["now"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not stop["now"]:
        started = time.time()
        alarms = _check_once(cfg, inbound)
        if not write_json_safely(WD_HEARTBEAT, {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "epoch": int(started), "pid": os.getpid(),
                "alarms_last_pass": len(alarms), "interval_s": interval,
        }):
            print(f"⚠️ MACF: watchdog heartbeat write failed; NOTHING can age "
                  f"this watchdog out", file=sys.stderr, flush=True)
        slept = 0.0
        while slept < interval and not stop["now"]:
            time.sleep(0.5)
            slept += 0.5
    return 0


def health(cfg, inbound) -> int:
    """One-shot verdict for a scheduler or a human. NON-ZERO when unhealthy.

    The watchdog reports continuously into a file; this is the surface that
    turns that into an exit code something outside the container can act on.
    Both watcher and watchdog liveness are reported, because a green watcher
    checked by a dead watchdog is a reading nobody should trust.
    """
    now = time.time()
    hb = heartbeat_verdict(now)
    report: Dict[str, Any] = {"watcher": hb}

    wd: Dict[str, Any] = {"state": "absent",
                          "detail": f"no watchdog heartbeat at {WD_HEARTBEAT}"}
    if WD_HEARTBEAT.exists():
        try:
            data = json.loads(WD_HEARTBEAT.read_text())
            age = now - float(data.get("epoch", 0))
            bound = max(HEARTBEAT_BOUND_FLOOR_S,
                        int(data.get("interval_s", 0)) * 3)
            wd = {"state": "alive" if age <= bound else "stale",
                  "age_s": int(age), "bound_s": bound, "pid": data.get("pid")}
        except (OSError, ValueError, TypeError) as e:
            wd = {"state": "unreadable", "detail": str(e)}
    report["watchdog"] = wd

    if cfg is not None:
        try:
            sweep = inbound.sweep_aged(cfg)
            report["aged"] = {"alerts": sweep["alerts"],
                              "spool": sweep["aged_spool"],
                              "pickup": sweep["aged_pickup"]}
        except OSError as e:
            report["aged"] = {"error": str(e)}
    else:
        report["aged"] = {"error": "config did not load"}

    healthy = (hb["state"] == "alive" and wd.get("state") == "alive"
               and report["aged"].get("alerts") == 0)
    report["healthy"] = healthy
    print(json.dumps(report, indent=1, default=str))
    return 0 if healthy else 1


def validate(cfg, candidate_contacts: Optional[str] = None) -> int:
    """Check the configuration a running deployment OBEYS, without touching it.

    THE POINT IS THE CANDIDATE. Validating the installed file tells you what
    the broker is already enforcing; by then a bad edit has been live since the
    moment it was saved. `--contacts <path>` validates a file that has not been
    installed yet, so the operator's sequence is validate-then-replace and there
    is no window in which the deployment obeys something nobody checked.

    Reports every check rather than stopping at the first failure: an operator
    fixing a config wants the whole list, and a validator that reveals problems
    one run at a time trains people to stop running it.

    Exits non-zero if ANY check fails.
    """
    from macf.amail.contacts import ContactBook, ContactListError

    checks: List[Dict[str, Any]] = []

    def record(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # The two configs already loaded through their validated models to get here.
    record("inbound_config", True, f"{CONFIG_PATH} parsed and validated")
    record("broker_config", True,
           f"referenced broker config parsed; domain={cfg.broker_config.domain!r}")

    contacts_path = Path(candidate_contacts) if candidate_contacts \
        else cfg.broker_config.contacts_path
    if not contacts_path:
        record("contacts", False, "no contacts path configured; the broker "
                                  "refuses every send with no policy")
    else:
        book = ContactBook(Path(contacts_path))
        try:
            parsed = book._load_full()
            record("contacts_parse", True,
                   f"{contacts_path} parsed; {len(parsed.by_agent)} agent(s), "
                   f"{sum(len(v) for v in parsed.by_agent.values())} contact(s)")

            # TWO POLICY STORES MUST AGREE. Contacts and the agent roster are
            # both operator-authored, so a contacts entry naming an agent the
            # deployment does not define is a CONFIGURATION ERROR rather than a
            # signal -- declare, compare, refuse. (Contrast a policy store
            # against a STATE store, where disagreement is the signal and
            # forcing agreement is the bug.)
            roster = set(cfg.broker_config.agent_homes or {})
            if roster:
                unknown = sorted(set(parsed.by_agent) - roster)
                record("contacts_roster_agreement", not unknown,
                       f"contacts name agent(s) the deployment does not define: "
                       f"{unknown}" if unknown
                       else f"every agent named in contacts is defined "
                            f"({len(roster)} in the roster)")
            else:
                record("contacts_roster_agreement", True,
                       "no roster declared in the broker config; nothing to "
                       "compare against — NOT a pass, an absence")

            # A direction of "neither" is a revocation RECORD, not a mistake.
            # Surfaced rather than counted as a fault, because it is the one
            # entry an operator most wants to see when reading a config back.
            revoked = [f"{a}/{c}" for (a, c), d in parsed.direction.items()
                       if d == "neither"]
            if revoked:
                record("contacts_revocations", True,
                       f"{len(revoked)} withdrawn contact(s) recorded: {revoked}")
        except ContactListError as e:
            record("contacts_parse", False, str(e))
        except (OSError, ValueError) as e:
            record("contacts_parse", False,
                   f"{type(e).__name__}: {e}")

    failed = [c for c in checks if not c["ok"]]
    print(json.dumps({"contacts_path": str(contacts_path) if contacts_path else None,
                      "candidate": bool(candidate_contacts),
                      "checks": checks,
                      "valid": not failed}, indent=1))
    if failed:
        print(f"VALIDATION FAILED: {len(failed)} check(s) — "
              f"{', '.join(c['check'] for c in failed)}", file=sys.stderr)
        return 1
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
    if verb == "validate":
        # `--contacts <path>` validates a file that is NOT installed yet.
        cand = None
        if "--contacts" in sys.argv:
            k = sys.argv.index("--contacts")
            if k + 1 >= len(sys.argv):
                print("validate: --contacts needs a path", file=sys.stderr)
                return 2
            cand = sys.argv[k + 1]
        return validate(cfg, cand)
    if verb == "watchdog":
        return watchdog(cfg, inbound)
    if verb == "health":
        return health(cfg, inbound)
    if verb == "reconcile":
        report = inbound.reconcile(cfg)
        print(json.dumps(report, indent=1))
        return 0 if report.get("balanced") else 1
    print(f"unknown verb {verb!r}: use check | validate | process | watch | "
          f"watchdog | health | sweep | reconcile", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
