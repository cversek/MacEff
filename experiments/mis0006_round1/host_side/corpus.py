# Candidate corpus shared by E13 (and E12/E8 consult typing): knowledge-web artifacts, memory files, policies.
import os, re, glob, math, collections

HOME = os.path.expanduser("~")
AGENT = os.path.expanduser(os.environ.get("KIT_AGENT_HOME", "~"))
MEMORY = os.path.expanduser(os.environ.get("KIT_MEMORY", "~/.claude/memory"))
POLICIES = os.path.expanduser(os.environ.get("KIT_POLICIES", "~/MacEff/framework/policies"))
STRIP = re.compile(r"^##+\s*(Cross-References|Wiki-Links|Related|See also)\b.*?(?=^##\s|\Z)", re.S | re.M | re.I)
STAMP = re.compile(r"(\d{4}-\d{2}-\d{2})[_ ]?(\d{6})?")
TOKEN = re.compile(r"[a-z0-9]+")

def item_of(path):
    if "/agent/" in path:
        return "ca:" + path.split("/agent/", 1)[1]
    if "/memory/" in path:
        return "memory:" + os.path.basename(path)
    if "/framework/policies/" in path:
        return "policy:" + os.path.basename(path)[:-3]
    return None

def norm_item(it):
    if it.startswith("policy:") and it.endswith(".md"):
        return it[:-3]
    if it.startswith("idea:"):
        return "idea:%d" % int(it[5:]) if it[5:].isdigit() else it
    return it

def created(path):
    m = STAMP.search(os.path.basename(path)) or STAMP.search(path)
    if not m:
        return None
    import time
    s = m.group(1) + (" " + m.group(2) if m.group(2) else " 000000")
    try:
        return time.mktime(time.strptime(s, "%Y-%m-%d %H%M%S"))
    except ValueError:
        return None

def load():
    paths = [p for p in glob.glob(AGENT + "/agent/private/**/*.md", recursive=True) + glob.glob(AGENT + "/agent/public/**/*.md", recursive=True)
             if "/mis0006_r1/" not in p]
    paths += glob.glob(MEMORY + "/*.md")
    paths += glob.glob(POLICIES + "/**/*.md", recursive=True)
    docs = {}
    for p in paths:
        it = item_of(p)
        if not it:
            continue
        try:
            txt = open(p, errors="ignore").read()
        except OSError:
            continue
        txt = STRIP.sub("", txt)
        toks = TOKEN.findall((os.path.basename(p) + " " + txt).lower())
        title = next((l.lstrip("# ").strip() for l in txt.splitlines() if l.startswith("# ")), os.path.basename(p))
        docs[it] = {"path": p, "toks": toks, "tf": collections.Counter(toks), "len": len(toks),
                    "created": created(p), "mtime": os.path.getmtime(p), "title": title}
    import json as _json
    for p in glob.glob(AGENT + "/agent/public/ideas/*.json"):
        try:
            j = _json.load(open(p))
        except (OSError, ValueError):
            continue
        it = "idea:%d" % int(j.get("id"))
        txt = " ".join(str(j.get(k, "")) for k in ("title", "slug", "description", "summary", "body", "notes"))
        toks = TOKEN.findall(txt.lower())
        docs[it] = {"path": p, "toks": toks, "tf": collections.Counter(toks), "len": len(toks),
                    "created": created(p), "mtime": os.path.getmtime(p), "title": str(j.get("title", ""))}
    df = collections.Counter()
    for d in docs.values():
        df.update(set(d["toks"]))
    n = len(docs)
    idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
    avg = sum(d["len"] for d in docs.values()) / max(n, 1)
    return docs, idf, avg

def bm25(q_toks, docs, idf, avg, eligible, k1=1.2, b=0.75):
    sc = {}
    for it in eligible:
        d = docs[it]
        s = 0.0
        for w in q_toks:
            f = d["tf"].get(w, 0)
            if f:
                s += idf.get(w, 0) * f * (k1 + 1) / (f + k1 * (1 - b + b * d["len"] / avg))
        if s > 0:
            sc[it] = s
    return [it for it, _ in sorted(sc.items(), key=lambda x: -x[1])]

def grep5(q_toks, docs, idf, eligible):
    terms = sorted(set(q_toks), key=lambda w: (-idf.get(w, 0), q_toks.index(w)))[:5]
    sc = {}
    for it in eligible:
        k = sum(1 for w in terms if w in docs[it]["tf"])
        if k:
            sc[it] = (k, docs[it]["created"] or 0)
    return [it for it, _ in sorted(sc.items(), key=lambda x: (-x[1][0], -x[1][1]))]
