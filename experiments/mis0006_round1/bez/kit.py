"""MIS-0006 round 1, E15-E17 kit: read this seat's transcript into drives (what opened each turn) and the tool calls
that followed, with the source read the way MIS-0002-R121 asks (origin record first, else the opening tag) through
macf.utils.input_origin. Writes a private table (text stays on this host) for the three experiment scripts.
usage: kit.py TRANSCRIPT.jsonl OUT_DIR"""
import sys, json, re, os, datetime, collections
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.expanduser("~/gitwork/cversek/MacEff-bez/macf/src"))
from macf.utils import input_origin as io

TZ = ZoneInfo("America/New_York")
VOICE = "plugin:maceff-voice-input-channel:maceff"
TELEGRAM = "plugin:telegram:telegram"
DICTATION_BY_SOCKET = "[Operator dictation, transcribed;"
# notices the framework types into the box itself; keys_sent records exist only from 2026-11-24 23:36
# client commands that run locally and start no turn of the agent
CLIENT_LOCAL_COMMANDS = {"login", "logout", "status", "remote-control", "mcp", "model", "clear", "config", "cost", "usage", "help", "exit", "resume", "permissions", "context", "plugin", "plugins", "hooks", "agents", "memory", "fast", "effort", "statusline", "theme", "rewind"}
FRAMEWORK_OPENINGS = ("AUTO_MODE RESUME:", "🏗️ MACF |", "[maceff:wake]")


def keys_sent():
    from macf.agent_events_log import read_events
    out = []
    for e in read_events(limit=None, scope="all", only=["keys_sent"]):
        t = (e.get("data") or {}).get("text")
        if t and isinstance(e.get("timestamp"), (int, float)):
            out.append((e["timestamp"], " ".join(str(t).split())))
    return out


def channel_body(text):
    """The words inside the channel tag that opens the text."""
    m = re.match(r"\s*<channel [^>]*>(.*?)(</channel>|$)", text, re.S)
    body = m.group(1).strip() if m else text
    # the channel writes a one-line header, "[Voice input · trigger · spoken ... ]", before the words
    return re.sub(r"^\[Voice input[^\]]*\]\s*", "", body)


def classify(d, text, sent):
    """(class, operator?) for one user entry that is not a tool result; class None = not a drive."""
    o = d.get("origin") or {}
    kind = o.get("kind")
    if d.get("isCompactSummary") or io.opens_with_local_command_output(text) or text.startswith("<local-command-caveat>"):
        return None, False
    if text.startswith("[Request interrupted by user"):
        return None, False                      # an interruption, not a prompt; counted apart
    if kind == "channel" or io.opening_channel_source(text) is not None:
        src = o.get("server") if kind == "channel" else io.opening_channel_source(text)
        if src == VOICE: return "dictated", True
        if src == TELEGRAM: return "telegram", True
        return "daemon_notice", False
    if kind == "peer" or text.startswith("Another Claude session sent a message:"):
        body = text.split("\n", 1)[1] if "\n" in text else ""
        if body.startswith(DICTATION_BY_SOCKET): return "dictated_socket", True
        return "peer_agent", False
    if kind == "task-notification" or io.opens_with_harness_notice(text):
        return "background", False
    if d.get("isMeta"):
        if text.startswith("Stop hook feedback"): return "hook", False
        return None, False                      # skill bodies and reminders the client adds to a turn
    if text.startswith(FRAMEWORK_OPENINGS): return "framework_keys", False
    if io.opens_with_command_row(text):
        name = (re.search(r"<command-name>/?([^<\s]+)", text) or [None, ""])[1]
        if name in CLIENT_LOCAL_COMMANDS: return None, False   # runs in the client, opens no turn
    if kind in (None, "human"):
        ts = stamp(d)
        flat = " ".join(io.typed_text(d["message"]["content"]).split())
        if any(0 <= ts - t <= io.KEYS_SENT_WINDOW_SECONDS and flat and (flat == s or s.startswith(flat)) for t, s in sent):
            return "framework_keys", False
        return "typed", True
    return "other", False


def stamp(d):
    return datetime.datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).timestamp()


PATH_RE = re.compile(r"(?:~|/Users/cversek)/[\w.@%+/~-]+")


def opened_items(block):
    """What a tool call opened: Read paths, paths named in Bash, task ids read, artifact reads."""
    name, inp = block.get("name"), block.get("input") or {}
    items = set()
    if name in ("Read", "NotebookEdit") and inp.get("file_path"): items.add(os.path.expanduser(inp["file_path"]))
    if name == "Bash":
        cmd = inp.get("command", "")
        for p in PATH_RE.findall(cmd): items.add(os.path.expanduser(p.rstrip(".,;:)'\"")))
        for t in re.findall(r"task (?:get|start|note|complete)\s+#?(\d+)", cmd): items.add(f"task#{t}")
        for t in re.findall(r"issue view (\d+)", cmd): items.add(f"issue#{t}")
    if name in ("Grep", "Glob") and inp.get("path"): items.add(os.path.expanduser(inp["path"]))
    return sorted(items)


def main(path, out):
    os.makedirs(out, exist_ok=True)
    sent = keys_sent()
    drives, calls, dropped = [], [], collections.Counter()
    call_i = 0
    for line in open(path):
        try: d = json.loads(line)
        except ValueError: continue
        if d.get("type") == "assistant":
            for b in (d.get("message", {}).get("content") or []):
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    calls.append({"i": call_i, "ts": stamp(d), "name": b.get("name"), "items": opened_items(b)}); call_i += 1
            continue
        if d.get("type") == "system" and d.get("subtype") == "compact_boundary":
            calls.append({"i": call_i, "ts": stamp(d), "name": "_compaction", "items": []}); call_i += 1
            continue
        if d.get("type") != "user": continue
        c = d.get("message", {}).get("content")
        if isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in c): continue
        text = io.entry_text(c)
        cls, op = classify(d, text, sent)
        if cls is None:
            dropped["interruption" if text.startswith("[Request interrupted") else "not_a_drive"] += 1
            continue
        ts = stamp(d)
        words = text
        if cls == "dictated": words = channel_body(text)
        elif cls == "dictated_socket": words = re.sub(r"^\[Operator dictation[^\]]*\]\s*", "", text.split("\n", 1)[1]) if "\n" in text else ""
        elif cls == "typed": words = io.typed_text(c)
        drives.append({"ts": ts, "day": datetime.datetime.fromtimestamp(ts, TZ).date().isoformat(), "cls": cls, "operator": op,
                       "text": words, "raw_head": text[:300], "call_index": call_i,
                       "trigger": (re.search(r'trigger="([^"]+)"', text) or [None, None])[1]})
    json.dump({"drives": drives, "calls": calls, "dropped": dropped, "keys_sent_records": len(sent),
               "transcript": os.path.basename(path)}, open(f"{out}/drives.json", "w"))
    by = collections.Counter(x["cls"] for x in drives)
    print(json.dumps({"drives": len(drives), "by_class": by, "tool_calls": len([c for c in calls if c["name"] != "_compaction"]),
                      "compactions": len([c for c in calls if c["name"] == "_compaction"]), "dropped": dropped, "keys_sent_records": len(sent),
                      "first": drives[0]["day"], "last": drives[-1]["day"]}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
