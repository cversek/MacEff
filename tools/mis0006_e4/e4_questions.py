"""E4 step 2: build the questions, mechanically, and write them owner-only. Prints counts only.

Q-decision: one per (memory file, quote of four words or more) whose words appear verbatim in an
operator turn. Question = the file's description line; relevant = every episode whose operator
turn contains the quote.

Q-current: supersession pairs. A memory file recording a replaced rule names it with one of
SUPERSESSION_WORDS, and quotes the operator at least twice; a pair is the earliest and the latest
of its matched quotes, when their episodes fall on different days. Two questions per pair:
"now" (the newer episode is right) and "before <date of the newer>" (the older is right).

Q-none, in vocabulary: per Q-decision question, a term that occurs in 2 to 20 episodes and never
in that question's relevant episodes, picked by a stable hash; the question is the description
followed by the term. Out of vocabulary: a pull request number and a coined word found nowhere.

usage: e4_questions.py EPISODES MEMORY_DIR OUT
"""

import glob
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from e4_lib import norm_quote, stable_split  # noqa: E402
from macf.knowledge_eval_text import words  # noqa: E402

QUOTE = re.compile(r'[“"]([^"“”\n]{12,400})[”"]')
SUPERSESSION_WORDS = re.compile(r"\b(replac\w*|supersed\w*|no longer|instead of|was changed|changed to|"
                                r"raised|lowered|reversed|overrid\w*|now (?:is|the))\b", re.I)


def h(s):
    return hashlib.sha256(s.encode()).hexdigest()


def main(ep_path, mem_dir, out):
    eps = json.load(open(ep_path))
    ops = [norm_quote(e["operator"]) for e in eps]
    day = [e["ts"][:10] for e in eps]
    qdec, dropped, files_used = [], 0, 0
    pairs = []
    for f in sorted(glob.glob(os.path.join(mem_dir, "*.md"))):
        if os.path.basename(f) == "MEMORY.md":
            continue
        text = open(f, errors="replace").read()
        m = re.search(r"^description:\s*(.+)$", text, re.M)
        if not m:
            continue
        desc = m.group(1).strip()
        matched = []
        for q in dict.fromkeys(x for x in QUOTE.findall(text) if len(x.split()) >= 4):
            nq = norm_quote(q)
            rel = [i for i, o in enumerate(ops) if nq in o]
            if not rel:
                dropped += 1
                continue
            qdec.append({"kind": "decision", "q": desc, "relevant": rel, "file": os.path.basename(f),
                         "quote_sha": h(nq)[:12]})
            matched.append((min(rel), max(rel), rel))
        if matched:
            files_used += 1
        if len(matched) >= 2 and SUPERSESSION_WORDS.search(text):
            older = min(matched, key=lambda m: m[0])
            newer = max(matched, key=lambda m: m[0])
            if day[older[0]] < day[newer[0]]:
                pairs.append((desc, older[0], newer[0]))
    qcur = []
    for desc, o, n in pairs:
        d = datetime.strptime(day[n], "%Y-%m-%d").strftime("%B %-d, %Y")
        qcur.append({"kind": "current_now", "q": f"What is the current rule now: {desc}", "right": n, "wrong": o})
        qcur.append({"kind": "current_before", "q": f"What was the rule before {d}: {desc}", "right": o, "wrong": n,
                     "before": day[n]})
    # in-vocabulary negatives
    df = defaultdict(set)
    for i, e in enumerate(eps):
        for w in set(words(e["operator"])):
            df[w].add(i)
    mid = sorted(w for w, s in df.items() if 2 <= len(s) <= 20 and len(w) >= 5 and not w.isdigit())
    qneg = []
    for q in qdec:
        rel = set(q["relevant"])
        cands = [w for w in mid if not (df[w] & rel)]
        if not cands:
            continue
        w = min(cands, key=lambda w: h(f"neg:{q['quote_sha']}:{w}"))
        qneg.append({"kind": "none_invocab", "q": f"{q['q']} {w}", "term_df": len(df[w])})
    alltext = set(df)
    qoov = []
    for i in range(20):
        n = 90000 + int(h(f"oov:{i}")[:6], 16) % 9999
        coined = "zq" + h(f"coin:{i}")[:6]
        if coined in alltext:
            continue
        qoov.append({"kind": "none_oov", "q": f"What did we decide about pull request #{n} and the {coined} rule?"})
    allq = qdec + qcur + qneg + qoov
    for q in allq:
        q["held"] = stable_split(q["q"])
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(allq, fh)
    by = defaultdict(lambda: [0, 0])
    for q in allq:
        by[q["kind"]][int(q["held"])] += 1
    print(f"memory files with a matched quote: {files_used}; quotes dropped for not matching verbatim: {dropped}")
    print(f"supersession pairs: {len(pairs)}")
    for k, (dv, hd) in sorted(by.items()):
        print(f"  {k}: {dv} dev, {hd} held")


if __name__ == "__main__":
    main(*sys.argv[1:4])
