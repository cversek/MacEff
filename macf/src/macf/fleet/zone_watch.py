"""The zone watch, as a unit of a fleet daemon (PROTOTYPE, mission B phase B1).

The shared mail zone is a fleet resource, so the watch runs under the fleet's own daemon, on the
fleet's account, and alerts a person through the outside watch's alert path: a command that holds
its own credential, never an agent's channel (MIS-0002-R75). No agent is in the path.

Each pass reads the zone's email routing log (Cloudflare's ``emailRoutingAdaptive`` dataset) over a
trailing window, because entries appear minutes after the send. It records each attempt once as a
``zone_contact`` event in the fleet's own log, and alerts on a sender never seen before or on a
burst. A second check compares the edge's routing rules with the addresses the systems declare.

WHAT IS REMEMBERED, AND WHERE. Nothing but the fleet's event log: the attempts already recorded and
every sender ever seen are read back from its ``zone_contact`` events, and the last edge findings
from its last ``zone_edge_check``. There is no state file that could disagree with the log.

FIRST START. A log with no ``zone_contact`` yet is read back over the dataset's retention, one day
at a time; those attempts are recorded, and one summary alert replaces a first-contact alert each.

Every deployment fact comes from the configuration file the unit's command names: the zone's id
and domain, the token file, the addressing files, the routes expected outside them, and the alert
command. The zone never appears in this repository. Token parts of zone addresses are masked in
everything written, and the token is read from its file per request and never printed.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

QUERY = (
    "query($z:String!,$s:Time!,$e:Time!){viewer{zones(filter:{zoneTag:$z})"
    "{emailRoutingAdaptive(limit:1000,filter:{datetime_geq:$s,datetime_leq:$e},"
    "orderBy:[datetime_ASC]){datetime action status from to messageId spf dkim dmarc "
    "ruleMatched errorDetail isSpam spamScore}}}}"
)
#: name_shortid_<token>@zone: keep the name and short id, mask the token.
TOKEN_ADDR = re.compile(r"^([a-z0-9]+_[0-9a-f]{6}_)([0-9a-f]{12,})(@.*)$", re.I)
STAMP = "%Y-%m-%dT%H:%M:%SZ"


@dataclass
class Config:
    zone_id: str
    zone_domain: str
    token_file: str
    alert_command: List[str]
    addressing_files: List[str] = field(default_factory=list)
    expected_routes: List[str] = field(default_factory=list)
    interval_s: int = 300
    window_min: int = 60
    burst_per_hour: int = 10
    seen_keep_h: int = 48
    readback_days: int = 31

    @classmethod
    def load(cls, path: Path) -> "Config":
        return cls(**json.loads(Path(path).read_text()))


def mask(addr: str) -> str:
    m = TOKEN_ADDR.match(addr or "")
    return f"{m.group(1)}{m.group(2)[:4]}…{m.group(3)}" if m else (addr or "")


def bare_sender(from_field: str) -> str:
    m = re.search(r"<([^>]+)>", from_field or "")
    return (m.group(1) if m else (from_field or "")).strip().lower()


def attempt_key(row: dict) -> str:
    """One attempt's identity across passes, with the address masked like everything written."""
    return f"{row['datetime']}|{row.get('messageId') or ''}|{mask(row.get('to') or '')}"


# --- what the log remembers ----------------------------------------------------------------------


@dataclass
class Memory:
    seen: Dict[str, str]          # attempt key -> when, within seen_keep_h
    senders: Set[str]             # every sender ever recorded
    edge: Optional[List[str]]     # the last edge findings recorded
    empty: bool                   # no zone_contact recorded yet: the first start


def remember(events: Sequence[dict], now: datetime, keep_h: int) -> Memory:
    """What the fleet's log says the watch has already done."""
    cutoff = (now - timedelta(hours=keep_h)).strftime(STAMP)
    seen, senders, edge, contacts = {}, set(), None, 0
    for e in events:
        data = e.get("data") or {}
        if e.get("event") == "zone_contact":
            contacts += 1
            if data.get("sender"):
                senders.add(data["sender"])
            if data.get("key") and str(data.get("at", "")) >= cutoff:
                seen[data["key"]] = data["at"]
        elif e.get("event") == "zone_edge_check" and isinstance(data.get("findings"), list):
            edge = data["findings"]
    return Memory(seen=seen, senders=senders, edge=edge, empty=contacts == 0)


# --- Cloudflare -------------------------------------------------------------------------------------


def fetch(cfg: Config, start: datetime, end: datetime) -> list:
    body = json.dumps({"query": QUERY, "variables": {
        "z": cfg.zone_id, "s": start.strftime(STAMP), "e": end.strftime(STAMP)}}).encode()
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/graphql", data=body, method="POST",
        headers={"Authorization": "Bearer " + Path(cfg.token_file).read_text().strip(),
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    if d.get("errors"):
        raise RuntimeError("graphql: " + "; ".join(e.get("message", "?") for e in d["errors"]))
    return d["data"]["viewer"]["zones"][0]["emailRoutingAdaptive"]


def cf_get(cfg: Config, path: str) -> dict:
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/zones/{cfg.zone_id}/{path}",
        headers={"Authorization": "Bearer " + Path(cfg.token_file).read_text().strip()})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    if not d.get("success"):
        raise RuntimeError(f"{path}: " + "; ".join(e.get("message", "?") for e in d.get("errors", [])))
    return d


# --- alerts, through the outside watch's path ----------------------------------------------------


def alert(cfg: Config, text: str) -> bool:
    """Push *text* through the alert command, which reads it on stdin and holds its own
    credential (MIS-0002-R75); False when it failed, so the caller records it as unsent."""
    try:
        r = subprocess.run(list(cfg.alert_command), input=text, text=True, capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"zone_watch: alert not sent: {e}", file=sys.stderr)
        return False
    if r.returncode != 0:
        print(f"zone_watch: alert not sent ({r.returncode}): {r.stderr.strip()[:300]}", file=sys.stderr)
    return r.returncode == 0


# --- the contact pass --------------------------------------------------------------------------------


def contact_record(row: dict) -> dict:
    return {"at": row["datetime"], "key": attempt_key(row), "sender": bare_sender(row.get("from")),
            "to": mask(row.get("to")), "action": row.get("action"), "status": row.get("status"),
            "real_address": row.get("action") == "worker", "spf": row.get("spf"),
            "dkim": row.get("dkim"), "dmarc": row.get("dmarc"), "spam": row.get("isSpam"),
            "error": row.get("errorDetail") or ""}


def contact_pass(cfg: Config, now: datetime, *, events: Sequence[dict],
                 fetch_rows: Callable[[datetime, datetime], list],
                 record: Callable[[str, dict], None], push: Callable[[str], bool]) -> dict:
    """One pass: record each new attempt once, and alert on new senders or a burst. On the first
    start the dataset's retention is read back, and one summary alert stands for it."""
    mem = remember(events, now, cfg.seen_keep_h)
    if mem.empty:
        windows = [(now - timedelta(days=d + 1), now - timedelta(days=d)) for d in range(cfg.readback_days)][::-1]
    else:
        windows = [(now - timedelta(minutes=cfg.window_min), now)]
    rows = [r for start, end in windows for r in fetch_rows(start, end)]
    new, firsts = [], []
    for row in rows:
        rec = contact_record(row)
        if rec["key"] in mem.seen:
            continue
        mem.seen[rec["key"]] = rec["at"]
        new.append(rec)
        if rec["sender"] not in mem.senders:
            mem.senders.add(rec["sender"])
            firsts.append(rec)
    for rec in new:
        record("zone_contact", rec)
    hour_ago = (now - timedelta(hours=1)).strftime(STAMP)
    last_hour = sum(1 for at in mem.seen.values() if at >= hour_ago)
    burst = last_hour > cfg.burst_per_hour
    if mem.empty:
        if new:
            sent = push(f"Zone watch started under the fleet daemon. Read back {cfg.readback_days} days: "
                        f"{len(new)} attempts from {len(firsts)} senders, now recorded.\n")
            record("zone_contact_alert", {"readback": True, "attempts": len(new), "senders": len(firsts),
                                          "sent": sent})
    elif firsts or burst:
        lines = [f"- {r['at']} {r['sender']} to {r['to']}, "
                 f"{'a real agent address' if r['real_address'] else 'an unknown address (dropped)'}, "
                 f"dmarc={r['dmarc']} spam={r['spam']}" for r in firsts]
        text = "Outside contact on the agent mail zone.\n\n"
        if lines:
            text += "First contact from:\n" + "\n".join(lines) + "\n\n"
        if burst:
            text += f"Burst: {last_hour} attempts in the last hour (threshold {cfg.burst_per_hour}).\n"
        sent = push(text)
        record("zone_contact_alert", {"new_senders": len(lines), "last_hour": last_hour, "burst": burst,
                                      "sent": sent})
    return {"rows": len(rows), "new": len(new), "new_senders": len(firsts), "last_hour": last_hour,
            "readback": mem.empty}


# --- the edge check ---------------------------------------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class Declared:
    live: Dict[str, str]      # address -> which agent in which system declares it
    revoked: Set[str]
    twice: Set[str]           # declared by two systems: the edge can route it to one only


def declared_addresses(cfg: Config, documents: Sequence[Tuple[str, dict]]) -> Declared:
    """The addresses the systems declare under this zone, the revoked ones, and any declared by
    two systems, from each system's addressing document (``(name, document)``)."""
    from macf.amail.zone import local_part_from_card
    live, revoked, twice = {}, set(), set()
    for where, doc in documents:
        if doc.get("zone") != cfg.zone_domain:
            continue
        bad = {str(t).lower() for t in doc.get("revoked_zone_tokens") or []}
        for name, a in (doc.get("agents") or {}).items():
            card, tok = (a or {}).get("card"), (a or {}).get("zone_token")
            if card and tok:
                addr = f"{local_part_from_card(card, tok)}@{cfg.zone_domain}"
                if addr in live:
                    twice.add(addr)
                live[addr] = f"{name} in {where}"
            if card:
                for t in bad:
                    revoked.add(f"{local_part_from_card(card, t)}@{cfg.zone_domain}")
    return Declared(live=live, revoked=revoked, twice=twice)


def edge_findings(cfg: Config, documents, rules: Sequence[dict], catch_all: dict) -> List[str]:
    """What the edge routes that the declarations don't say, and the reverse. Masked."""
    declared = declared_addresses(cfg, documents)
    live, revoked, twice = declared.live, declared.revoked, declared.twice
    routed = {}
    for r in rules:
        if not r.get("enabled"):
            continue
        for m in r.get("matchers") or []:
            if m.get("type") == "literal" and m.get("field") == "to":
                routed[str(m.get("value", "")).lower()] = r
    findings = [f"declared by two systems: {mask(a)}" for a in sorted(twice)]
    for addr, agent in live.items():
        if addr not in routed:
            findings.append(f"declared, not routed at the edge: {mask(addr)} ({agent})")
    expected = {e.lower() for e in cfg.expected_routes}
    for addr in routed:
        if not addr.endswith("@" + cfg.zone_domain) or addr in expected:
            continue
        if addr in revoked:
            findings.append(f"REVOKED token still routed: {mask(addr)}")
        elif addr not in live:
            findings.append(f"routed at the edge, declared by no system: {mask(addr)}")
    if not catch_all.get("enabled") or [a.get("type") for a in catch_all.get("actions") or []] != ["drop"]:
        findings.append("catch-all is not an enabled drop: probes to unknown addresses are not logged")
    return sorted(findings)


def edge_pass(cfg: Config, findings: List[str], *, events: Sequence[dict],
              record: Callable[[str, dict], None], push: Callable[[str], bool]) -> List[str]:
    """Record and alert only when the findings change from the last ones the log holds."""
    before = remember(events, datetime.now(timezone.utc), cfg.seen_keep_h).edge
    if findings == before:
        return findings
    record("zone_edge_check", {"findings": findings})
    if findings or before:
        push("The edge's routing rules and the declared zone addresses "
             + ("differ:\n" + "\n".join(f"- {f}" for f in findings) if findings else "agree again.") + "\n")
    return findings


# --- the unit ---------------------------------------------------------------------------------------------


def live_edge(cfg: Config) -> List[str]:
    import yaml
    docs = []
    for f in cfg.addressing_files:
        doc = yaml.safe_load(Path(f).read_text()) or {}
        docs.append((str(doc.get("domain") or Path(f).name), doc))   # a system goes by its own domain
    rules, page = [], 1
    while True:
        d = cf_get(cfg, f"email/routing/rules?per_page=50&page={page}")
        rules += d["result"]
        if page >= (d.get("result_info") or {}).get("total_pages", 1):
            break
        page += 1
    return edge_findings(cfg, docs, rules, cf_get(cfg, "email/routing/rules/catch_all")["result"])


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="the zone watch, a fleet daemon's unit")
    ap.add_argument("config", type=Path, help="the deployment's zone watch configuration (JSON)")
    ap.add_argument("--once", action="store_true", help="one pass of each check, then exit")
    args = ap.parse_args(argv)
    cfg = Config.load(args.config)
    from macf.agent_events_log import append_event, read_events
    from macf.pd.liveness import heartbeat_from_env

    def events():
        return list(read_events(reverse=False, scope="all", only=("zone_contact", "zone_edge_check")))

    def push(text: str) -> bool:
        return alert(cfg, text)
    heartbeat = None if args.once else heartbeat_from_env()
    next_run = 0.0
    while True:
        if heartbeat:
            heartbeat.tick()
        if time.time() >= next_run:
            next_run = time.time() + cfg.interval_s
            for name, step in (
                    ("contacts", lambda: contact_pass(cfg, datetime.now(timezone.utc), events=events(),
                                                      fetch_rows=lambda s, e: fetch(cfg, s, e),
                                                      record=append_event, push=push)),
                    ("edge", lambda: edge_pass(cfg, live_edge(cfg), events=events(), record=append_event,
                                               push=push))):
                try:
                    print(json.dumps(step()), flush=True)
                except Exception as exc:  # noqa: BLE001 - one bad pass is logged; the next one tries again
                    print(f"zone_watch: {name} pass failed: {type(exc).__name__}: {str(exc)[:300]}",
                          file=sys.stderr, flush=True)
        if args.once:
            return 0
        time.sleep(15)


if __name__ == "__main__":
    sys.exit(main())
