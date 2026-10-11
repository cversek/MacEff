"""The outside watch: every primal daemon checked from outside the agents.

MIS-0002-R74 (pd_MUST_have_outside_watch) and MIS-0002-R75
(outside_watch_MUST_alert_independently), under ``service_supervision``: a supervisor
that shares a fate with its subject is not a supervisor, so the watch is its own
process on its own timer, reads only what the agents wrote, and pushes an alert through
a command that holds its own credential, never an agent's channel.

What it reads, per agent home named in its rendered config:

- the declaration (``interface.declaration_path``), which says what must be running;
- the daemon's record (``interface.record_path``), probed by pid and start time;
- the last ``pd_unit_alive`` of each declared unit in the agent's own event log, aged
  against the cadence the unit itself published (``Liveness.interval_s``), never a
  bound kept here (MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)).

It keeps one record: the durable alert log, one line per pass that had something to
say, carrying each transition (a stretch opened or closed) and whether the push was
delivered. The open stretches are read back from the delivered lines, so an alert whose
push failed is sent again on the next pass, never lost; and there is no second file
that could disagree with the log. That log is the notifier's memory, not a record of
liveness (R16).

Verdicts per subject (``service_supervision`` section 2.1): ALIVE, STALE (stamped, then
stopped), GONE (the stamping process no longer exists), ABSENT (never stamped within
the lookback), UNREADABLE (present but unparseable). Per home, the external check's
states (section 4.2): UNREACHABLE when the home cannot be read at all, CHECK-FAILED when
the watch cannot tell what to check. Unknown is never healthy.
"""
import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Literal, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from macf.notify.session import verify_incarnation
from macf.pd import interface
from macf.pd.health import read_liveness
from macf.utils.streaming import iter_lines_reverse

#: How far back a unit's last stamp is looked for. Older than this reads ABSENT: the
#: verdict names the window, so it never claims more than was read.
LOOKBACK_S = 7 * 86400
#: How long an alert command may take before it counts as failed.
SEND_TIMEOUT_S = 30

Verdict = Literal["ALIVE", "STALE", "GONE", "ABSENT", "UNREADABLE", "UNREACHABLE", "CHECK-FAILED"]

#: Exit codes, worst wins (``service_supervision`` section 4.2): each state its own code.
EXIT_HEALTHY, EXIT_UNHEALTHY, EXIT_UNREACHABLE, EXIT_CHECK_FAILED = 0, 1, 2, 3
_EXIT_FOR = {"ALIVE": EXIT_HEALTHY, "STALE": EXIT_UNHEALTHY, "GONE": EXIT_UNHEALTHY,
             "ABSENT": EXIT_UNHEALTHY, "UNREACHABLE": EXIT_UNREACHABLE,
             "UNREADABLE": EXIT_CHECK_FAILED, "CHECK-FAILED": EXIT_CHECK_FAILED}

#: ``(pid, recorded start) -> is that process still the one recorded``, in the shape of
#: ``verify_incarnation``, which puts both starts through ``proc_start_key`` so a start
#: the client wrote and one read from /proc compare as the same value.
Probe = Callable[[int, str], bool]


@dataclass(frozen=True)
class Finding:
    """One subject's verdict, in the words of the check that made it."""

    agent: str      # the calling card, or the home's path when no card could be read
    subject: str    # "daemon", a unit's name, or "home"
    verdict: Verdict
    detail: str

    @property
    def key(self) -> str:
        return f"{self.agent}/{self.subject}"

    def line(self) -> str:
        return f"{self.agent} {self.subject}: {self.verdict}, {self.detail}"


# ============================================================================
# The check
# ============================================================================

def _age(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 120:
        return f"{seconds} s"
    if seconds < 7200:
        return f"{seconds // 60} min"
    return f"{seconds // 3600} h {seconds % 3600 // 60} min"


def check_daemon(card: str, base: Optional[Path], probe: Probe) -> Finding:
    """The daemon itself, from the record it writes after binding its sockets."""
    path = interface.record_path(card, base)
    try:
        text = path.read_text()
    except FileNotFoundError:
        return Finding(card, "daemon", "ABSENT", f"no record at {path.name}: the daemon is not running")
    except OSError as e:
        return Finding(card, "daemon", "UNREADABLE", f"record {path.name} unreadable: {e.strerror}")
    try:
        record = interface.DaemonRecord.model_validate_json(text)
    except ValidationError:
        return Finding(card, "daemon", "UNREADABLE", f"record {path.name} does not parse")
    if not probe(record.pid, record.proc_start):
        return Finding(card, "daemon", "GONE",
                       f"pid {record.pid} is not the process its record names: not running, or another process")
    return Finding(card, "daemon", "ALIVE", f"pid {record.pid}")


def last_liveness(log_path: Path, card: str, units: Sequence[str], now: float,
                  lookback_s: float = LOOKBACK_S) -> Dict[str, Optional[dict]]:
    """The newest ``pd_unit_alive`` record of each named unit of agent *card*, or None if
    there is none within the lookback. A log more than one agent writes to is read for
    this agent's events only. Reads newest first and stops at the first event older than
    the lookback or once every unit is found: bounded by meaning, not by a row count."""
    wanted = set(units)
    found: Dict[str, Optional[dict]] = dict.fromkeys(units)
    cutoff = now - lookback_s
    for line in iter_lines_reverse(log_path):
        if not wanted:
            break
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        stamp = event.get("timestamp")
        if isinstance(stamp, (int, float)) and stamp < cutoff:
            break
        if event.get("event") != interface.EVENT_LIVENESS:
            continue
        data = event.get("data")
        if not isinstance(data, dict) or data.get("agent") != card:
            continue
        unit = data.get("unit")
        if unit in wanted:
            found[unit] = event
            wanted.discard(unit)
    return found


def check_unit(card: str, unit: interface.Unit, event: Optional[dict], now: float,
               probe: Optional[Probe]) -> Finding:
    """A unit's verdict by the rule the readout uses (``health.read_liveness``): a unit is
    STALE past three of the intervals it published, the core's bound, so the watch and the
    daemon never disagree about when one is."""
    r = read_liveness(event, now, probe)
    if r.verdict == "ABSENT":
        return Finding(card, unit.name, "ABSENT", f"no liveness within {_age(LOOKBACK_S)}")
    if r.verdict == "UNREADABLE":
        return Finding(card, unit.name, "UNREADABLE", "its last liveness event does not parse")
    if r.verdict == "STALE":
        return Finding(card, unit.name, "STALE",
                       f"last liveness {_age(r.age)} ago, its interval is {_age(r.live.interval_s)}")
    if r.verdict == "GONE":
        return Finding(card, unit.name, "GONE", f"pid {r.live.pid} that stamped it {_age(r.age)} ago is gone")
    return Finding(card, unit.name, "ALIVE", f"last liveness {_age(r.age)} ago")


def check_home(home: Path, now: float, base: Optional[Path] = None,
               probe: Optional[Probe] = verify_incarnation) -> List[Finding]:
    """Every finding for one agent home. ``probe`` None skips the process probes, for a
    home whose processes run in a pid namespace this watch cannot see."""
    home = Path(home)
    if not home.is_dir():
        return [Finding(str(home), "home", "UNREACHABLE", "the agent home cannot be read; nothing was measured")]
    try:
        card = interface.agent_card(home)
    except (interface.IdentityError, OSError) as e:
        return [Finding(str(home), "home", "CHECK-FAILED", f"no calling card: {e}")]
    try:
        declaration = interface.Declaration.model_validate_json(interface.declaration_path(home).read_text())
    except FileNotFoundError:
        return [Finding(card, "home", "CHECK-FAILED", "the declaration is missing, so what to check is unknown")]
    except (OSError, ValidationError, ValueError) as e:
        reason = "does not validate" if isinstance(e, (ValidationError, ValueError)) else e.strerror
        return [Finding(card, "home", "CHECK-FAILED", f"the declaration {reason}, so what to check is unknown")]
    # A daemon's record holds a pid in its own namespace; where this watch cannot see
    # that namespace there is no daemon finding at all, never a guessed ALIVE. Its units'
    # liveness is still read, and a container's own watch checks its daemon.
    findings = [check_daemon(card, base, probe)] if probe is not None else []
    log_path = home / ".maceff" / "agent_events_log.jsonl"
    try:
        events = last_liveness(log_path, card, [u.name for u in declaration.units], now)
    except FileNotFoundError:
        events = {u.name: None for u in declaration.units}
    except OSError as e:
        return findings + [Finding(card, "home", "CHECK-FAILED", f"the event log cannot be read: {e.strerror}")]
    findings += [check_unit(card, u, events[u.name], now, probe) for u in declaration.units]
    return findings


def exit_code(findings: Sequence[Finding]) -> int:
    return max((_EXIT_FOR[f.verdict] for f in findings), default=EXIT_HEALTHY)


# ============================================================================
# Stretches: one alert when one begins, one line when it ends
# ============================================================================

def transitions(findings: Sequence[Finding], open_stretches: Dict[str, dict],
                now: float) -> Tuple[List[str], Dict[str, dict]]:
    """The lines to send, and the stretches open after this pass.

    A subject that turns bad opens a stretch and gives one alert; while it stays bad,
    whatever its verdict, nothing more; when it reads ALIVE again, one recovery line
    with the stretch's length. A subject no longer checked (its unit removed from the
    declaration, its home from the config) closes its stretch with a line that says so.
    """
    lines: List[str] = []
    after: Dict[str, dict] = {}
    seen = set()
    for f in findings:
        seen.add(f.key)
        was = open_stretches.get(f.key)
        if f.verdict == "ALIVE":
            if was is not None:
                lines.append(f"recovered: {f.line()} (after {_age(now - was['since'])})")
            continue
        if was is None:
            lines.append(f"ALERT: {f.line()}")
            after[f.key] = {"since": now, "verdict": f.verdict}
        else:
            after[f.key] = was
    for key, was in open_stretches.items():
        if key not in seen:
            lines.append(f"closed: {key} is no longer checked (was {was['verdict']} for {_age(now - was['since'])})")
    return lines, after


# ============================================================================
# The config the outer tier renders, and the alert path
# ============================================================================

class WatchedHome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1)
    probe: bool = True


class WatchConfig(BaseModel):
    """Rendered from the declarations found on a host, never kept by hand.

    ``alert_command`` receives each pass's lines on stdin and holds its own credential,
    one no agent environment carries (MIS-0002-R75). Which command, and whether its
    destination is independent of every agent, is the operator's review of the
    deployment's path.
    """

    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    homes: List[WatchedHome]
    alert_command: List[str] = Field(min_length=1)
    state_dir: str = Field(min_length=1)


def render_config(candidate_homes: Sequence[Path], alert_command: Sequence[str], state_dir: Path,
                  unprobed: Sequence[Path] = ()) -> WatchConfig:
    """A watch over every candidate home that has a declaration: a declared daemon is
    watched by construction, an undeclared home is not expected to run one."""
    unprobed_set = {str(Path(p)) for p in unprobed}
    homes = [WatchedHome(path=str(Path(h)), probe=str(Path(h)) not in unprobed_set)
             for h in candidate_homes if interface.declaration_path(Path(h)).is_file()]
    return WatchConfig(homes=homes, alert_command=list(alert_command), state_dir=str(state_dir))


def unwatched(config: WatchConfig, candidate_homes: Sequence[Path]) -> List[str]:
    """Homes with a declaration that the config does not watch (MIS-0002-R74)."""
    watched = {h.path for h in config.homes}
    return [str(Path(h)) for h in candidate_homes
            if interface.declaration_path(Path(h)).is_file() and str(Path(h)) not in watched]


def render_systemd(config_path: Path, every_s: int = 120,
                   python: str = sys.executable) -> Dict[str, str]:
    """The Linux user units: a oneshot service and the timer that runs it. The watch is
    its own process on its own timer, so no daemon it watches can take it down."""
    service = (
        "[Unit]\n"
        "Description=MacEff outside watch over the primal daemons (MIS-0002-R74)\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={python} -m macf.pd.watch --config {config_path}\n"
        # An unhealthy or unreachable verdict is the watch working, not failing.
        "SuccessExitStatus=1 2\n"
    )
    timer = (
        "[Unit]\n"
        "Description=Run the MacEff outside watch\n\n"
        "[Timer]\n"
        f"OnBootSec={every_s}\n"
        f"OnUnitActiveSec={every_s}\n"
        "AccuracySec=10\n\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )
    return {f"{interface.PD_IDENTIFIER}_watch.service": service,
            f"{interface.PD_IDENTIFIER}_watch.timer": timer}


def send(alert_command: Sequence[str], text: str, durable_log: Path,
         open_after: Optional[Dict[str, dict]] = None) -> bool:
    """Push the lines through the alert command, and record them whatever happens.

    Each record carries whether it was delivered and, when it was, the stretches open
    after it (``open_after``): ``open_stretches`` reads them back from the newest
    delivered record, so a failed push changes nothing and its lines go out again on the
    next pass. A notifier that cannot notify must not also fall silent
    (``service_supervision`` section 4.4): a failed push is still written here and to
    stderr. The command's own output is never echoed, since a transport error can carry
    its URL.
    """
    durable_log.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(list(alert_command), input=text, text=True,
                                capture_output=True, timeout=SEND_TIMEOUT_S)
        delivered = result.returncode == 0
        outcome = "delivered" if delivered else f"alert command exited {result.returncode}"
    except (OSError, subprocess.TimeoutExpired) as e:
        delivered = False
        outcome = f"alert command failed: {type(e).__name__}"
    record = {"ts": time.time(), "delivered": delivered, "outcome": outcome, "text": text}
    if open_after is not None:
        record["open_after"] = open_after
    with durable_log.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    if not delivered:
        print(f"MacEff outside watch: {outcome}; the alert is in {durable_log}:\n{text}", file=sys.stderr)
    return delivered


def open_stretches(durable_log: Path) -> Dict[str, dict]:
    """The stretches a person has been told are open: ``open_after`` of the newest record
    that was delivered and carries it. Records that failed, or that carry no stretch state
    (the watch's own fault alert), are passed over."""
    try:
        for line in iter_lines_reverse(durable_log):
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("delivered") and "open_after" in record:
                return dict(record["open_after"])
    except FileNotFoundError:
        pass
    return {}


def run_pass(config: WatchConfig, now: Optional[float] = None,
             base: Optional[Path] = None, probe: Probe = verify_incarnation) -> int:
    """One pass: check every home, and send what changed since the last delivered alert."""
    now = time.time() if now is None else now
    durable_log = Path(config.state_dir) / "alerts.jsonl"
    findings: List[Finding] = []
    for home in config.homes:
        findings += check_home(Path(home.path), now, base, probe if home.probe else None)
    lines, after = transitions(findings, open_stretches(durable_log), now)
    if lines:
        send(config.alert_command, "MacEff outside watch\n" + "\n".join(lines) + "\n",
             durable_log, open_after=after)
    return exit_code(findings)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m macf.pd.watch",
                                     description="One pass of the outside watch over the primal daemons.")
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        config = WatchConfig.model_validate_json(args.config.read_text())
    except (OSError, ValidationError, ValueError) as e:
        print(f"MacEff outside watch: CHECK-FAILED, the config {args.config} cannot be used: "
              f"{type(e).__name__}", file=sys.stderr)
        return EXIT_CHECK_FAILED
    try:
        return run_pass(config)
    except Exception as e:  # noqa: BLE001 -- the watch breaking is itself an alert, never silence
        send(config.alert_command,
             f"MacEff outside watch\nALERT: the watch itself: CHECK-FAILED, {type(e).__name__}: {e}\n",
             Path(config.state_dir) / "alerts.jsonl")
        return EXIT_CHECK_FAILED


if __name__ == "__main__":
    sys.exit(main())
