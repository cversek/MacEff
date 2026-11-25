"""E4 step 1: cut the seat's own transcripts into episodes, owner-only.

An episode starts at an operator turn and runs to the next one. It holds the operator's words
and the agent's own words (text blocks only; no tool calls, tool output, thinking, hook
context or the client's bookkeeping). Lines are deduplicated by uuid, since a resumed session
copies its history into the new file.

usage: e4_episodes.py PROJECT_DIR OUT.json
"""

import json
import os
import re
import sys
from pathlib import Path

SKIP_PREFIX = ("<local-command", "<task-notification", "<observed_from", "[Request interrupted",
               "<channel source=\"plugin:maceff-channel", "Caveat:", "This session is being continued")
_TAGS = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
_PASTE = re.compile(r"<pasted_content\b[^>]*>.*?</pasted_content>", re.S)
_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.S)
_NAME = re.compile(r"<command-name>(.*?)</command-name>", re.S)
_CHANNEL = re.compile(r"<channel source=\"plugin:telegram[^>]*>(.*?)</channel>", re.S)


def operator_text(d):
    """(full text, text without pasted blocks) of an operator turn, or None if the line is not one."""
    if d.get("type") != "user" or d.get("isMeta") or d.get("isCompactSummary") or d.get("isSidechain"):
        return None
    ct = (d.get("message") or {}).get("content")
    if isinstance(ct, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in ct):
            return None
        ct = "\n".join(b.get("text", "") for b in ct if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(ct, str):
        return None
    t = _TAGS.sub("", ct).strip()
    if not t or t.startswith(SKIP_PREFIX):
        return None
    if t.startswith("<command-"):
        args = " ".join(a.strip() for a in _ARGS.findall(t))
        name = " ".join(n.strip() for n in _NAME.findall(t))
        t = f"{name} {args}".strip()
        if not args:
            return None          # a bare slash command carries no words of the operator's
    m = _CHANNEL.search(t)
    if m:
        t = m.group(1).strip()
    return t, _PASTE.sub(" ", t).strip()


def agent_text(d):
    if d.get("type") != "assistant" or d.get("isSidechain"):
        return None
    ct = (d.get("message") or {}).get("content")
    if not isinstance(ct, list):
        return None
    t = "\n".join(b.get("text", "") for b in ct if isinstance(b, dict) and b.get("type") == "text").strip()
    return t or None


def main(project_dir, out):
    seen, episodes, bad = set(), [], 0
    files = sorted(Path(project_dir).glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    for f in files:
        cur = None
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
                if not u or u in seen:
                    continue
                seen.add(u)
                op = operator_text(d)
                if op is not None:
                    cur = {"id": f"{d.get('sessionId', f.stem)[:8]}:{u[:8]}", "session": d.get("sessionId"),
                           "ts": d.get("timestamp"), "operator": op[0], "operator_unpasted": op[1], "agent": []}
                    episodes.append(cur)
                    continue
                a = agent_text(d)
                if a and cur is not None:
                    cur["agent"].append(a)
    for e in episodes:
        e["agent_turns"] = e["agent"]
        e["agent"] = "\n\n".join(e["agent"])
    episodes.sort(key=lambda e: e["ts"] or "")
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(episodes, fh)
    n_op = sum(len(e["operator"]) for e in episodes)
    n_ag = sum(len(e["agent"]) for e in episodes)
    print(f"files {len(files)}, episodes {len(episodes)}, operator chars {n_op}, agent chars {n_ag}, "
          f"first {episodes[0]['ts'] if episodes else None}, last {episodes[-1]['ts'] if episodes else None}, "
          f"unreadable lines {bad}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
