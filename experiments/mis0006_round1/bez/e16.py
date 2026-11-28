"""E16, text the operator never said: the fixed flag and trim over dictated utterances transcribed before the Mac
transcriber change (2026-11-23 17:30 local), prevalence by day, the typed-prompt false-positive check, the post-change
check, and the blind-reading and miss-rate samples (written to a private folder, never posted).
usage: e16.py DRIVES_JSON PRIVATE_OUT_DIR"""
import sys, json, re, zlib, random, collections, unicodedata, datetime
from zoneinfo import ZoneInfo

SEED, B = 20261123, 10000
SENT_END = re.compile(r"[.!?](?=\s|$)")
CHANGE = datetime.datetime(2026, 11, 23, 17, 30, tzinfo=ZoneInfo("America/New_York")).timestamp()
CHANGE = datetime.datetime(2026, 11, 23, 17, 30, tzinfo=ZoneInfo("America/New_York")).timestamp()
def ratio(s):
    b = s.encode("utf8")
    return len(b) / len(zlib.compress(b)) if b else 0.0


def non_latin_alpha(ch):
    return ch.isalpha() and "LATIN" not in unicodedata.name(ch, "")


def repeat_run(text):
    """Start offset of the first run where a 1-3 token sequence repeats 6+ times in a row, else None."""
    toks = [(m.start(), m.group().lower().strip(".,!?;:")) for m in re.finditer(r"\S+", text)]
    w = [t for _, t in toks]
    for n in (1, 2, 3):
        for i in range(len(w) - n * 6 + 1):
            unit = w[i:i + n]; k = 1
            while w[i + k * n:i + (k + 1) * n] == unit: k += 1
            if k >= 6: return toks[i][0]
    return None


def nonlatin_run(text):
    """Start of the first run holding 10+ non-Latin letters, spaces and punctuation allowed inside it."""
    start, count = None, 0
    for i, ch in enumerate(text):
        if non_latin_alpha(ch):
            if start is None: start = i
            count += 1
            if count >= 10: return start
        elif ch.isalpha():                      # a Latin letter ends the run
            start, count = None, 0
    return None


def last_sentence_start(text):
    ends = [m.end() for m in SENT_END.finditer(text.rstrip())]
    ends = [e for e in ends if e < len(text.rstrip())]
    return ends[-1] if ends else 0


def flag_and_trim(text):
    """(flags, cut_from or None, cut chars). Repeat and non-Latin runs cut back to the end of the sentence before
    the run (the whole utterance when no sentence precedes it); compression alone cuts the last sentence only if
    that sentence alone compresses above 2.4."""
    flags = []
    r1, r3 = repeat_run(text), nonlatin_run(text)
    if r1 is not None: flags.append("repeat")
    if ratio(text) > 2.4: flags.append("compress")
    if r3 is not None: flags.append("nonlatin")
    starts = [s for s in (r1, r3) if s is not None]
    if starts:
        s = min(starts)
        ends = [m.end() for m in SENT_END.finditer(text[:s])]
        cut = ends[-1] if ends else 0
        return flags, cut, len(text) - cut
    if flags == ["compress"]:
        ls = last_sentence_start(text)
        if ratio(text[ls:]) > 2.4: return flags, ls, len(text) - ls
        return flags, None, 0
    return flags, None, 0


def boot(rows, num, den):
    by = collections.defaultdict(lambda: [0, 0])
    for r in rows: by[r["day"]][0] += num(r); by[r["day"]][1] += den(r)
    days = list(by.values()); rnd = random.Random(SEED)
    est = sum(a for a, _ in days) / sum(b for _, b in days)
    bs = sorted((lambda s: sum(a for a, _ in s) / max(1, sum(b for _, b in s)))([rnd.choice(days) for _ in days]) for _ in range(B))
    return est, bs[int(0.025 * B)], bs[int(0.975 * B) - 1], len(days)



def main():
    global d, out, dr, dict_all, pre, post
    d = json.load(open(sys.argv[1])); out = sys.argv[2]
    dr = [x for x in d["drives"] if x["day"] >= "2026-11-18"]
    dict_all = [x for x in dr if x["cls"] in ("dictated", "dictated_socket") and x["text"].strip()]
    pre = [x for x in dict_all if x["ts"] < CHANGE]
    post = [x for x in dict_all if x["ts"] >= CHANGE]
    SENT_END = re.compile(r"[.!?](?=\s|$)")
    rows = []
    for x in pre:
        f, cut, n = flag_and_trim(x["text"])
        rows.append({**x, "flags": f, "cut": cut, "cut_chars": n, "chars": len(x["text"])})
    flagged = [r for r in rows if r["flags"]]
    e1 = boot(rows, lambda r: 1 if r["flags"] else 0, lambda r: 1)
    e2 = boot(rows, lambda r: r["cut_chars"], lambda r: r["chars"])
    print(f"Pre-change dictated utterances: {len(rows)} on {e1[3]} days ({', '.join(sorted({r['day'] for r in rows}))}); {sum(r['chars'] for r in rows)} characters")
    print(f"H16.1 utterances flagged: {len(flagged)} = {e1[0]:.3f}, 95% interval by day [{e1[1]:.3f}, {e1[2]:.3f}] (bar 0.10)")
    print(f"H16.1 characters cut: {sum(r['cut_chars'] for r in rows)} = {e2[0]:.3f}, 95% interval by day [{e2[1]:.3f}, {e2[2]:.3f}] (bar 0.25)")
    v = "NOT REACHED (fewer than ten days)" if e1[3] < 10 else ("VALIDATED" if e1[1] > 0.10 and e2[1] > 0.25 else "CONTRADICTED" if e1[2] < 0.10 and e2[2] < 0.25 else "SUPPORTED, NOT SHOWN" if e1[0] > 0.10 and e2[0] > 0.25 and e1[1] > 0.05 and e2[1] > 0.125 else "NOT REACHED")
    print(f"H16.1: {v}")
    by_flag = collections.Counter(f for r in flagged for f in r["flags"])
    print(f"  by flag (an utterance can carry several): {dict(by_flag)}; flagged with nothing cut: {sum(1 for r in flagged if r['cut_chars'] == 0)}")
    trig = collections.defaultdict(lambda: [0, 0])
    for r in rows: trig[r["trigger"] or "socket route"][0] += bool(r["flags"]); trig[r["trigger"] or "socket route"][1] += 1
    print("  by trigger: " + "; ".join(f"{k} {a} of {b}" for k, (a, b) in trig.items()))

    typed = [x for x in dr if x["cls"] == "typed" and x["day"] in {r["day"] for r in rows} and x["text"].strip() and not x["text"].lstrip().startswith(("<command", "<bash", "/"))]
    tf = [x for x in typed if flag_and_trim(x["text"])[0]]
    print(f"Typed operator prompts on the same days: {len(tf)} of {len(typed)} flagged = {len(tf)/max(1,len(typed)):.3f} (bar 0.01): {'PASS' if len(tf)/max(1,len(typed)) <= 0.01 else 'FAIL'}; flags: {dict(collections.Counter(f for x in tf for f in flag_and_trim(x['text'])[0]))}")

    pf = [x for x in post if flag_and_trim(x["text"])[0]]
    print(f"After the change (check on the new filter, no rule): {len(pf)} of {len(post)} flagged")

    # samples for the readings, private
    rnd = random.Random(SEED)
    cuts = [r for r in rows if r["cut_chars"] > 0]
    cut_s = rnd.sample(cuts, min(30, len(cuts)))
    uncut_pool = [r for r in rows if r["cut_chars"] == 0]
    uncut_s = rnd.sample(uncut_pool, min(30, len(uncut_pool)))
    spans = [{"key": "cut", "span": r["text"][r["cut"]:]} for r in cut_s] + \
            [{"key": "uncut", "span": r["text"][last_sentence_start(r["text"]):]} for r in uncut_s]
    rnd.shuffle(spans)
    json.dump([{"n": i + 1, "span": s["span"][:1500]} for i, s in enumerate(spans)], open(f"{out}/e16_blind_spans.json", "w"), ensure_ascii=False, indent=1)
    json.dump([{"n": i + 1, "key": s["key"]} for i, s in enumerate(spans)], open(f"{out}/e16_blind_key.json", "w"))
    miss = rnd.sample([r for r in rows if not r["flags"]], min(30, len([r for r in rows if not r["flags"]])))
    json.dump([{"n": i + 1, "text": r["text"][-600:]} for i, r in enumerate(miss)], open(f"{out}/e16_miss_sample.json", "w"), ensure_ascii=False, indent=1)
    print(f"Samples written privately: {len(cut_s)} cuts + {len(uncut_s)} uncut final spans, shuffled; {len(miss)} unflagged utterances for the miss reading")


if __name__ == "__main__":
    main()
