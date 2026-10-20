"""Step 0: one time-ordered event stream from the three scopes of history the operator named.

Sources, each event tagged with its scope:
  conv   the session transcript: prompts, the agent's messages, its tool calls (with any
         knowledge consult they make), and compaction boundaries, which set the in-context boundary
  task   the task tree: creations and every update note, from each task's metadata history
  duty   roles' duties: every update, from the duty files

A prompt is taken from the record that DELIVERED it into context, once, at delivery time (found
14:42 Oct 17, after the queue was first mistaken for the deliveries):
  - a new turn is a user record; Telegram, scheduled and peer turns are isMeta user records
  - a prompt delivered mid-turn is a queued_command attachment, stamped with its enqueue time;
    the queue's matching remove operation is when it entered context
  - enqueue records mark entry to the queue, not delivery, and are not prompts
Each prompt is classified by origin before anything else (a quick test found machines posing as the
operator), from the record's own origin, turnOrigin and scheduledTaskId where it carries them, and
from its text for machines that type into the pane as if human: operator, telegram, cron,
mail_clock, wake, recovery, notification, peer (a subagent's hand-back), or slash (a skill
invocation, kept as its own stratum; local UI commands never reach the model and are dropped).

KG artifacts are not events here; they are retrieval candidates, built in step0b with their
creation times.

Usage: python3 semantic_events.py   (writes data/events.jsonl and data/events_manifest.json)
"""
import bisect
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from kit_config import DATA, END, HOME, REPO, TRANSCRIPTS, machine_patterns

sys.path.insert(0, str(REPO / "macf/src"))
KINDS =('"type":"user"', '"type":"assistant"', '"type":"queue-operation"', '"type":"attachment"')
SKIP = re.compile(r"^\s*(<local-command|Caveat:|\[Request interrupted|<bash-(?:input|stdout|stderr)>)")
SLASH = re.compile(r"<command-name>/?([^<]*)</command-name>")
SLASH_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
LOCAL = {"compact", "autocompact", "model", "mcp", "usage", "login", "logout", "permissions", "config", "exit",
         "effort", "context", "rename", "cost", "status", "help", "resume", "doctor", "hooks", "agents", "memory",
         "ide", "export", "rewind", "plugin", "fast", "statusline", "vim", "output-style", "add-dir",
         "release-notes", "upgrade", "telegram:access", "telegram:configure"}
ORIGINS = [("compaction", re.compile(r"^\s*This session is being continued from a previous conversation")),
           ("notification", re.compile(r"^\s*(<task-notification|\[SYSTEM NOTIFICATION|<system-reminder)")),
           ("peer", re.compile(r"^\s*(Another Claude session sent a message|<agent-message)")),
           ("cron", re.compile(r"<<autonomous-loop")),
           *machine_patterns(),      # the deployment's own: check-ins and the like typed into the pane
           ("mail_clock", re.compile(r"^\s*MAIL CLOCK:")),
           ("wake", re.compile(r"^\s*\[maceff:wake\]")),
           ("recovery", re.compile(r"^\s*(?:/?🤖\s*)?(?:do your recovery|AUTO_MODE RESUME|Session resumed by the harness"
                                   r"|\S*\s*MACF \| The compaction you queued)", re.I))]
BREADCRUMB = re.compile(r"Breadcrumb: (s_[0-9a-f]{8}/c_(\d+)/p_[0-9a-f]{8}/t_(\d{10}))")
CA_PATH = re.compile(r"agent/(?:private|public)/(learnings|reflections|checkpoints|observations|experiments|reports|roadmaps)/[^\s\"']+")
CONSULT_CMD = re.compile(r"macf_tools (knowledge query|idea get|idea search|transcripts search|dev_drv|task get|learnings)\b[^\"\n]{0,120}")
BREADCRUMB_T = re.compile(r"\bt_(\d{9,11})\b")


def epoch(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def origin_of(text):
    for name, pat in ORIGINS:
        if pat.search(text[:400]):
            return name
    return "operator"


def origin_from(rec_origin, turn_origin, scheduled, text):
    """The record's own word on who sent it, where it carries one; the text otherwise, which also
    catches the machines that type into the pane and so arrive marked human."""
    kind = (rec_origin or {}).get("kind")
    if kind == "channel":
        return "telegram"
    if kind == "peer" or turn_origin == "peer":
        return "peer"
    if kind == "task-notification" or turn_origin == "task_notification":
        return "notification"
    if scheduled or turn_origin == "scheduled":
        return "cron"
    return origin_of(text)


def norm(s):
    return " ".join(str(s).split())[:300]


def prompt_event(t, text, origin, seen_tg):
    """One delivered prompt as an event, or None for what never reached the model as a prompt."""
    if SKIP.match(text):
        return None
    s = text.lstrip()
    m = SLASH.search(s[:300]) if s.startswith(("<command-name>", "<command-message>")) else None
    if m or (s.startswith("/") and origin == "operator"):
        name = (m.group(1) if m else s[1:].split(maxsplit=1)[0] if s[1:].strip() else "").strip().lstrip("/")
        if name == "clear":
            return {"t": t, "scope": "conv", "kind": "boundary", "origin": "clear", "text": ""}
        if name in LOCAL or not name:
            return None
        args = (SLASH_ARGS.search(s).group(1).strip() if SLASH_ARGS.search(s) else "") if m else s[1 + len(name):].strip()
        text, origin = f"/{name} {args}".strip(), "slash"
    if origin == "telegram":
        mid = re.search(r'message_id="(\d+)"', text)
        if mid and mid.group(1) in seen_tg:
            return None
        if mid:
            seen_tg.add(mid.group(1))
        text = re.sub(r"<channel[^>]*>|</channel>", "", text)
    return {"t": t, "scope": "conv", "kind": "prompt", "origin": origin, "text": text.strip()[:2000]}


def tool_summary(name, inp):
    if name == "Bash":
        return f"Bash: {str(inp.get('command', ''))[:240]}"
    if name in ("Read", "Write", "Edit"):
        return f"{name}: {inp.get('file_path', '')}"
    first = next(iter(inp.items()), ("", ""))
    return f"{name}: {first[0]}={str(first[1])[:160]}"


def consults(inp_text):
    """What a tool call consults from the record: CA paths read, and consult commands run."""
    out = sorted(set(m.group(0).rstrip(".,;)") for m in CA_PATH.finditer(inp_text)))
    out += [m.group(0)[:160] for m in CONSULT_CMD.finditer(inp_text)]
    return out


def transcript_events():
    events, seen_tg, removes, attached, crumbs = [], set(), defaultdict(list), [], {}
    for n, transcript in enumerate(TRANSCRIPTS):
        events.extend(_one_transcript(transcript, n, seen_tg, removes, attached, crumbs))
    return _deliver_queued(events, seen_tg, removes, attached, crumbs)


def _one_transcript(transcript, n, seen_tg, removes, attached, crumbs):
    """One session's records. A session after the first opens with an empty context, so it
    starts with a boundary (none before the first, which is the stream's start)."""
    events, opened = [], n == 0
    with open(transcript, errors="replace") as f:
        for line in f:
            # the record's "type" key comes after several others, so search the whole line
            if not any(k in line for k in KINDS):
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            ts = d.get("timestamp")
            if not ts:
                continue
            t, kind = epoch(ts), d.get("type")
            if not opened:
                events.append({"t": t - 0.001, "scope": "conv", "kind": "boundary", "origin": "session", "text": ""})
                opened = True
            if kind == "queue-operation":
                if d.get("operation") == "remove" and d.get("content"):
                    removes[norm(d["content"])].append(t)
                continue
            if kind == "attachment":
                a = d.get("attachment") or {}
                if a.get("type") == "queued_command" and isinstance(a.get("prompt"), str) and a["prompt"].strip():
                    attached.append((t, a))
                elif a.get("hookEvent") == "UserPromptSubmit" or a.get("hookName") == "UserPromptSubmit":
                    for m in BREADCRUMB.finditer(json.dumps(a.get("content") or a.get("stdout") or "")):
                        crumbs[int(m.group(3))] = m.group(1)
                continue
            content = (d.get("message") or {}).get("content")
            if kind == "user":
                if isinstance(content, list):
                    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                        continue
                    content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                if not isinstance(content, str) or not content.strip():
                    continue
                if d.get("isCompactSummary") or origin_of(content) == "compaction":
                    # the boundary, then the summary the new context opens with: it is in context
                    # from here on, so a trace over the in-context turns computes over it too
                    events.append({"t": t, "scope": "conv", "kind": "boundary", "origin": "compaction", "text": ""})
                    body = content.split("Summary:", 1)[-1] if "Summary:" in content[:600] else content
                    events.append({"t": t + 0.001, "scope": "conv", "kind": "summary", "origin": "compaction",
                                   "text": body.strip()[:2000]})
                    continue
                rec, turn, sched = d.get("origin"), d.get("turnOrigin"), d.get("scheduledTaskId")
                if d.get("isMeta") and (rec or {}).get("kind") not in ("channel", "peer", "task-notification") \
                        and not sched and turn != "scheduled":
                    continue      # skill bodies and local-command caveats: injected, never sent
                ev = prompt_event(t, content, origin_from(rec, turn, sched, content), seen_tg)
                if ev:
                    events.append(ev)
            elif kind == "assistant" and isinstance(content, list):
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    if b.get("type") == "text" and b.get("text", "").strip():
                        events.append({"t": t, "scope": "conv", "kind": "agent", "origin": "agent", "text": b["text"].strip()[:1200]})
                    elif b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        ev = {"t": t, "scope": "conv", "kind": "tool", "origin": "agent", "text": tool_summary(b.get("name", ""), inp)}
                        c = consults(json.dumps(inp))
                        if c:
                            ev["consults"] = c
                        if b.get("name") == "Write" and CA_PATH.search(str(inp.get("file_path", ""))):
                            ev["writes_ca"] = True
                        events.append(ev)
    return events


def _deliver_queued(events, seen_tg, removes, attached, crumbs):
    # a mid-turn delivery entered context at its queue remove, the first unused one at or after
    # its enqueue time (the attachment carries the enqueue time, to the millisecond)
    for v in removes.values():
        v.sort()
    used = defaultdict(set)
    for t, a in sorted(attached, key=lambda x: x[0]):
        key, at = norm(a["prompt"]), t
        times = removes.get(key, [])
        j = bisect.bisect_left(times, t - 1.0)
        while j < len(times) and j in used[key]:
            j += 1
        if j < len(times):
            used[key].add(j)
            at = times[j]
        ev = prompt_event(at, a["prompt"], origin_from(a.get("origin"), None, None, a["prompt"]), seen_tg)
        if ev:
            ev["mid_turn"] = True
            events.append(ev)
    # each prompt carries the breadcrumb the UserPromptSubmit hook printed for it (its t_ is the
    # submission second), so a hit can be checked against the session, cycle and prompt it came from
    stamps = sorted(crumbs)
    for e in events:
        if e["kind"] == "prompt" and stamps:
            j = bisect.bisect_left(stamps, e["t"])
            near = min(stamps[max(0, j - 1): j + 1], key=lambda s: abs(s - e["t"]))
            if abs(near - e["t"]) <= 10:
                e["bc"] = crumbs[near]
    return events


def task_events():
    from macf.task.models import MacfTaskMetaData
    out = []
    for p in sorted((HOME / "agent/public/tasks").glob("*.json")):
        try:
            rec = json.loads(p.read_text())
        except ValueError:
            continue
        desc = rec.get("description") or ""
        subject = re.sub(r"\x1b\[[0-9;]*m", "", rec.get("subject", ""))
        try:
            mtmd = MacfTaskMetaData.parse(desc) if "macf_task_metadata" in desc else None
        except Exception:
            mtmd = None
        if mtmd is None:
            continue
        m = BREADCRUMB_T.search(str(getattr(mtmd, "creation_breadcrumb", "") or ""))
        if m:
            out.append({"t": float(m.group(1)), "scope": "task", "kind": "task_create", "origin": "agent",
                        "text": f"task #{rec.get('id')} created: {subject}"[:1200], "task": str(rec.get("id"))})
        for u in getattr(mtmd, "updates", None) or []:
            bc = u.get("breadcrumb", "") if isinstance(u, dict) else getattr(u, "breadcrumb", "")
            txt = u.get("description", "") if isinstance(u, dict) else getattr(u, "description", "")
            m = BREADCRUMB_T.search(str(bc))
            if not m:
                continue
            k = "task_start" if "started" in txt.lower()[:40] else "task_complete" if "completed" in txt.lower()[:40] else "task_note"
            out.append({"t": float(m.group(1)), "scope": "task", "kind": k, "origin": "agent",
                        "text": f"task #{rec.get('id')} {subject[:80]}: {txt}"[:1200], "task": str(rec.get("id"))})
    return out


def duty_events():
    out = []
    for p in sorted((HOME / "agent/public/roles").glob("*/DUTY_*.json")):
        d = json.loads(p.read_text())
        for u in d.get("updates") or []:
            m = BREADCRUMB_T.search(u.get("breadcrumb", ""))
            if m:
                out.append({"t": float(m.group(1)), "scope": "duty", "kind": f"duty_{u.get('kind', 'note')}", "origin": "agent",
                            "text": f"duty {d.get('title', '')[:100]}: {u.get('description', '')}"[:1200], "duty": d.get("id")})
    return out


def main():
    # the record as it stood when the experiment was registered: later records hold the experiment's
    # own work (its reads of learnings among them), and a rebuild must give the same snapshot
    events = [e for e in transcript_events() + task_events() + duty_events() if e["t"] < END]
    events.sort(key=lambda e: (e["t"], e["scope"], e["kind"], e["text"]))
    for i, e in enumerate(events):
        e["id"] = i
    blob = "\n".join(json.dumps(e, sort_keys=True, ensure_ascii=False) for e in events) + "\n"
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "events.jsonl").write_text(blob)
    prompts = [e for e in events if e["kind"] == "prompt"]
    manifest = {"sha256": hashlib.sha256(blob.encode()).hexdigest(), "events": len(events),
                "by_scope_kind": dict(Counter(f"{e['scope']}:{e['kind']}" for e in events).most_common()),
                "prompts_by_origin": dict(Counter(e["origin"] for e in prompts).most_common()),
                "mid_turn_by_origin": dict(Counter(e["origin"] for e in prompts if e.get("mid_turn")).most_common()),
                "with_breadcrumb_by_origin": dict(Counter(e["origin"] for e in prompts if e.get("bc")).most_common()),
                "boundaries": dict(Counter(e["origin"] for e in events if e["kind"] == "boundary")),
                "end": datetime.fromtimestamp(END).isoformat() if END != float("inf") else None,
                "tool_calls_consulting": sum(1 for e in events if e.get("consults")),
                "ca_writes": sum(1 for e in events if e.get("writes_ca")),
                "span": [datetime.fromtimestamp(events[0]["t"]).isoformat(), datetime.fromtimestamp(events[-1]["t"]).isoformat()]}
    (DATA / "events_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=1))


if __name__ == "__main__":
    main()
