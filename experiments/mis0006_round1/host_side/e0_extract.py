# E0: one row per tool call from this seat's transcripts. Writes calls_<session>.jsonl per transcript, and a progress line per file.
import json, re, sys, os, glob, time

OUT = os.path.expanduser(os.environ.get("KIT_DATA", "~/mis0006_r1_data"))
os.makedirs(OUT, exist_ok=True)
CONSULT = [
    (re.compile(r"agent/private/(learnings|reflections|checkpoints|observations|experiments|roadmaps|ideas)/[^\s'\"|;]+"), "ca"),
    (re.compile(r"agent/public/[a-z_]+/[^\s'\"|;]+"), "ca"),
    (re.compile(r"\.claude/projects/[^/]+/memory/[^\s'\"|;]+\.md"), "memory"),
    (re.compile(r"framework/policies/[^\s'\"|;]+\.md"), "policy"),
]
POLICY_READ = re.compile(r"macf_tools\s+policy\s+(?:read|navigate)\s+([A-Za-z0-9_:\-]+)")
IDEA_GET = re.compile(r"macf_tools\s+idea\s+get\s+#?(\d+)")
KQ = re.compile(r"macf_tools\s+knowledge\s+query\s+(.*)")
SEND = re.compile(r"amail\s+send|gmail\s+draft|outlook\s+draft")

def items_in(text):
    out = set()
    for rx, kind in CONSULT:
        for m in rx.finditer(text):
            p = m.group(0).rstrip(").,:")
            out.add(kind + ":" + p.split("agent/")[-1] if kind == "ca" else kind + ":" + os.path.basename(p))
    for m in POLICY_READ.finditer(text):
        out.add("policy:" + m.group(1).split(":")[-1])
    for m in IDEA_GET.finditer(text):
        out.add("idea:" + m.group(1))
    return sorted(out)

def run(path):
    sid = os.path.basename(path)[:8]
    dest = os.path.join(OUT, "calls_%s.jsonl" % sid)
    if os.path.exists(dest + ".done"):
        return
    pending = {}
    rows = []
    seq = 0
    with open(path) as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            t = d.get("type")
            ts = d.get("timestamp")
            side = bool(d.get("isSidechain"))
            if t == "system" and d.get("subtype") == "compact_boundary":
                rows.append({"kind": "compact", "ts": ts, "seq": seq})
                continue
            msg = d.get("message") or {}
            content = msg.get("content")
            if t == "user":
                if isinstance(content, str):
                    rows.append({"kind": "prompt", "ts": ts, "seq": seq, "side": side, "chars": len(content)})
                elif isinstance(content, list):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            r = pending.pop(b.get("tool_use_id"), None)
                            if r is not None:
                                c = b.get("content")
                                txt = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                                if r.get("kq") is not None:
                                    r["kq_hits"] = items_in(txt)[:50]
                                    r["kq_text"] = txt[:8000]
                                if r.get("tool") in ("Read",) or r.get("reads"):
                                    pass
                        elif isinstance(b, dict) and b.get("type") == "text":
                            rows.append({"kind": "prompt", "ts": ts, "seq": seq, "side": side, "chars": len(b.get("text", ""))})
            elif t == "assistant" and isinstance(content, list):
                for b in content:
                    if not (isinstance(b, dict) and b.get("type") == "tool_use"):
                        continue
                    seq += 1
                    name = b.get("name")
                    inp = b.get("input") or {}
                    r = {"kind": "call", "ts": ts, "seq": seq, "side": side, "tool": name}
                    text = ""
                    if name == "Bash":
                        text = str(inp.get("command", ""))
                        r["cmd"] = text[:400]
                        r["commit"] = bool(re.search(r"\bgit\b[^\n|;&]*\bcommit\b", text)) and "--dry-run" not in text
                        r["pr_open"] = bool(re.search(r"\bpr\s+create\b", text))
                        r["pytest"] = "pytest" in text
                        r["send"] = bool(SEND.search(text))
                        m = KQ.search(text)
                        if m:
                            r["kq"] = m.group(1)[:200]
                    elif name in ("Read", "Edit", "Write", "NotebookEdit"):
                        text = str(inp.get("file_path", ""))
                        r["path"] = text[:300]
                    elif name == "SendMessage":
                        r["send"] = True
                    elif name == "Skill":
                        r["skill"] = str(inp.get("skill", ""))
                    if name in ("Read",) or name == "Bash":
                        r["reads"] = items_in(text)
                    if name in ("Write", "Edit"):
                        r["writes"] = items_in(text)
                    rows.append(r)
                    pending[b.get("id")] = r
    with open(dest, "w") as out:
        for r in rows:
            out.write(json.dumps(r) + "\n")
    open(dest + ".done", "w").close()

if __name__ == "__main__":
    files = sys.argv[1:] or sorted(glob.glob(os.path.join(os.path.expanduser(os.environ["KIT_TRANSCRIPTS"]), "*.jsonl")), key=os.path.getsize)
    for f in files:
        t0 = time.time()
        run(f)
        with open(os.path.join(OUT, "progress.log"), "a") as p:
            p.write("%s %s %.1fs\n" % (time.strftime("%H:%M:%S"), os.path.basename(f), time.time() - t0))
