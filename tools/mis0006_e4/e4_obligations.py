"""E4, H4e: obligations from checkpoints' recovery sections, and whether each was done within the
hour after the next session start. Builds the starts and their obligations, owner-only; prints
counts only.

A session start is a compaction (the client's summary line) or a restart (the first new operator
turn of a transcript file that does not follow a summary). Its checkpoint is the latest one
written before it. Its obligations are the list items of that checkpoint's sections headed
recover / resume / first / next session / after compaction / startup, that a tool call could show
done: an item naming a command in backticks (its key is the command's first three words) or a
file by name (its key is the file's base name). Done means a tool call's input within 60 minutes
after the start contains the key.

usage: e4_obligations.py PROJECT_DIR CHECKPOINT_DIR OUT
"""

import json
import os
import re
import sys
from bisect import bisect_left, bisect_right
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from e4_episodes import SKIP_PREFIX, operator_text  # noqa: E402

HEAD = re.compile(r"^(#{1,4})\s+(.*)$")
WANT = re.compile(r"recover|resum|\bfirst\b|next session|after compaction|startup", re.I)
ITEM = re.compile(r"^\s*(?:[-*]|\d+[.)])\s+(.*)$")
TICK = re.compile(r"`([^`]{3,200})`")
FILE = re.compile(r"([A-Za-z0-9_.\-]+\.(?:md|json|py|sh))\b")
CMD = re.compile(r"^(macf_tools|git|gh|python3?|cat|ls|pytest|cd|tree|uv|make)\b")
TZ = datetime.now().astimezone().tzinfo   # checkpoint names carry local time
WINDOW = 3600


def ccp_time(name):
    m = re.match(r"(\d{4}-\d{2}-\d{2})_(\d{6})", name)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H%M%S").replace(tzinfo=TZ).timestamp()
    except ValueError as e:
        print(f"warning: {name}: no time in its name ({e}); left out", file=sys.stderr)
        return None


def obligations(text):
    out, on, level = [], False, 0
    for line in text.splitlines():
        h = HEAD.match(line)
        if h:
            if on and len(h.group(1)) <= level:
                on = False
            if WANT.search(h.group(2)):
                on, level = True, len(h.group(1))
            continue
        if not on:
            continue
        m = ITEM.match(line)
        if not m:
            continue
        item = m.group(1).strip()
        key = None
        for t in TICK.findall(item):
            if CMD.match(t.strip()):
                key = " ".join(t.split()[:3])
                break
        if key is None:
            f = FILE.search(item)
            if f and not f.group(1).startswith("."):
                key = f.group(1)
        if key:
            out.append({"item": item, "key": key})
    return out


def iso(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def main(project_dir, ccp_dir, out):
    seen, starts, calls, bad = set(), [], [], 0
    files = sorted(Path(project_dir).glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    for f in files:
        first_new, after_summary = True, False
        with open(f, errors="replace") as fh:
            for line in fh:
                if '"type":"user"' not in line and '"type":"assistant"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:  # noqa: S112 - counted in `bad` and printed at the end
                    bad += 1    # a line cut mid-write
                    continue
                u = d.get("uuid")
                if not u or u in seen or not d.get("timestamp"):
                    continue
                seen.add(u)
                ts = iso(d["timestamp"])
                if d.get("type") == "assistant":
                    for b in (d.get("message") or {}).get("content") or []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            calls.append((ts, json.dumps(b.get("input"), ensure_ascii=False)[:4000]))
                    continue
                if d.get("isCompactSummary"):
                    ct = (d.get("message") or {}).get("content")
                    text = ct if isinstance(ct, str) else " ".join(
                        b.get("text", "") for b in ct or [] if isinstance(b, dict))
                    starts.append({"kind": "compaction", "ts": ts, "prompt": text})
                    first_new, after_summary = False, True
                    continue
                op = operator_text(d)
                if op is not None and first_new:
                    if not after_summary:
                        starts.append({"kind": "restart", "ts": ts, "prompt": op[0]})
                    first_new = False
                elif op is None and isinstance((d.get("message") or {}).get("content"), str) and \
                        d["message"]["content"].startswith(SKIP_PREFIX):
                    pass
    calls.sort()
    call_ts = [c[0] for c in calls]
    ccps = sorted((t, p) for p in Path(ccp_dir).glob("*.md") if "ccp" in p.name.lower()
                  for t in [ccp_time(p.name)] if t)
    ccp_ts = [t for t, _ in ccps]
    rows, no_items = [], 0
    for s in sorted(starts, key=lambda s: s["ts"]):
        i = bisect_left(ccp_ts, s["ts"]) - 1
        if i < 0:
            continue
        obs = obligations(ccps[i][1].read_text(errors="replace"))
        if not obs:
            no_items += 1
            continue
        lo, hi = bisect_left(call_ts, s["ts"]), bisect_right(call_ts, s["ts"] + WINDOW)
        window = "\n".join(c[1] for c in calls[lo:hi]).lower()
        for o in obs:
            o["done"] = o["key"].lower() in window
        rows.append({"kind": s["kind"], "ts": s["ts"], "ccp": ccps[i][1].name, "prompt": s["prompt"][:20000],
                     "obligations": obs, "calls_in_window": hi - lo})
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(rows, fh)
    for kind in ("compaction", "restart"):
        r = [x for x in rows if x["kind"] == kind]
        dropped = [x for x in r if any(not o["done"] for o in x["obligations"])]
        print(f"{kind}: starts {sum(1 for s in starts if s['kind'] == kind)}, with checkable obligations {len(r)}, "
              f"with one dropped {len(dropped)}, obligations {sum(len(x['obligations']) for x in r)}, "
              f"dropped {sum(1 for x in r for o in x['obligations'] if not o['done'])}")
    print(f"starts whose checkpoint names no checkable obligation: {no_items}; tool calls read: {len(calls)}; "
          f"unreadable lines: {bad}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
