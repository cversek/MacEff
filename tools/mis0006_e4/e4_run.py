"""E4 step 3: run H4a to H4d on one split and print figures only (no question or episode text).

usage: e4_run.py EPISODES QUESTIONS CACHE_DIR WINNER SPLIT
  WINNER  the E1 winner with its frozen parameter, cc:ALPHA or rrf:K
  SPLIT   dev or held

Indexes:
  op      one unit per episode: the operator's turn, pasted blocks left out (H4a, H4b, H4c)
  both    one unit per episode: operator and agent words (H4a's beside-figure, H4d's episode arm)
  turns   one unit per turn, operator or agent, each returning its episode (H4d's turn arm)

Time-aware ordering (H4b), as fixed before data: a question is time-directed if it contains
now, current, currently, latest, or before / as of followed by a date. A "now" question reorders
the plain ranking's top 10 newest first and leaves the rest; a "before" question drops every
episode dated on or after the date. Anything else is the plain ranking unchanged.

Abstention (H4c): the score is the raw MiniLM cosine of the winner's top episode. The threshold
is the 10th percentile of that score over the dev Q-decision questions (so 10% of them would
abstain falsely); a negative is abstained on when its score falls below it.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from e4_lib import (Index, grep_rank, mean_interval, paired_interval, rank, recall_all_at,  # noqa: E402
                    sign_test)

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
BEFORE = re.compile(rf"\b(?:before|as of)\s+((?:{MONTHS})\s+\d{{1,2}},\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}})", re.I)
NOW = re.compile(r"\b(now|current|currently|latest)\b", re.I)


def _date(s):
    for fmt in ("%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.replace("  ", " "), fmt).strftime("%Y-%m-%d")
        except ValueError:  # noqa: S112 - the next format is tried; none matching returns None (no date)
            continue
    return None


def time_aware(q, ranked, day):
    m = BEFORE.search(q)
    if m and _date(m.group(1)):
        cut = _date(m.group(1))
        return [e for e in ranked if day[e] < cut]
    if NOW.search(q):
        top = sorted(ranked[:10], key=lambda e: day[e], reverse=True)
        return top + ranked[10:]
    return ranked


def main(ep_path, q_path, cache, winner, split):
    t0 = time.time()
    eps = json.load(open(ep_path))
    qs = [q for q in json.load(open(q_path)) if q["held"] == (split == "held")]
    ts = [datetime.fromisoformat(e["ts"].replace("Z", "+00:00")).timestamp() if e["ts"] else 0 for e in eps]
    day = [datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d") for t in ts]
    n = len(eps)
    op = Index("op", [e["operator_unpasted"] for e in eps], list(range(n)), cache)
    both = Index("both", [e["operator"] + "\n\n" + e["agent"] for e in eps], list(range(n)), cache)
    units, owners = [], []
    for i, e in enumerate(eps):
        for t in [e["operator"]] + list(e.get("agent_turns") or []):
            if t.strip():
                units.append(t)
                owners.append(i)
    turns = Index("turns", units, owners, cache)
    out = {"split": split, "winner": winner, "episodes": n, "turn_units": len(units), "questions": {}}
    dec = [q for q in qs if q["kind"] == "decision"]
    for k in ("decision", "current_now", "current_before", "none_invocab", "none_oov"):
        out["questions"][k] = sum(1 for q in qs if q["kind"] == k)

    # H4a: operator index; winner against the better of grep and bm25.
    r = {"grep": [], "bm25": [], "win": []}
    rb = {"grep": [], "bm25": [], "win": []}
    for q in dec:
        rel = set(q["relevant"])
        r["grep"].append(recall_all_at(grep_rank(op, q["q"], ts)[0], rel))
        r["bm25"].append(recall_all_at(rank(op, q["q"], "bm25")[0], rel))
        r["win"].append(recall_all_at(rank(op, q["q"], winner)[0], rel))
        rb["grep"].append(recall_all_at(grep_rank(both, q["q"], ts)[0], rel))
        rb["bm25"].append(recall_all_at(rank(both, q["q"], "bm25")[0], rel))
        rb["win"].append(recall_all_at(rank(both, q["q"], winner)[0], rel))
    m = {k: sum(v) / len(v) if v else None for k, v in r.items()}
    better = "grep" if (m["grep"] or 0) >= (m["bm25"] or 0) else "bm25"
    iv = paired_interval(r[better], r["win"])
    verdict = ("validated" if iv["ci95"][0] is not None and iv["ci95"][0] > 0.05 else
               "contradicted" if iv["ci95"][1] is not None and iv["ci95"][1] < 0 else "not reached")
    out["H4a"] = {"index": "operator turns", "recall_all@10": {k: mean_interval(v) for k, v in r.items()},
                  "better_baseline": better, "winner_minus_better": iv, "verdict": verdict,
                  "beside_both_speakers": {k: mean_interval(v) for k, v in rb.items()}}

    # H4d: turn-keyed against episode-keyed, both speakers, the winner.
    ep_keyed, turn_keyed = rb["win"], []
    for q in dec:
        turn_keyed.append(recall_all_at(rank(turns, q["q"], winner)[0], set(q["relevant"])))
    iv = paired_interval(ep_keyed, turn_keyed)
    out["H4d"] = {"episode_keyed": mean_interval(ep_keyed), "turn_keyed": mean_interval(turn_keyed),
                  "turn_minus_episode": iv,
                  "verdict": ("validated" if iv["ci95"][0] is not None and iv["ci95"][0] > 0 else
                              "contradicted" if iv["ci95"][1] is not None and iv["ci95"][1] < 0 else "not reached")}

    # H4b: top-1 on Q-current, time-aware against plain; and its price on Q-decision.
    wins = losses = ties = 0
    top1 = {"plain": [], "time": []}
    for q in qs:
        if not q["kind"].startswith("current"):
            continue
        plain = rank(op, q["q"], winner)[0]
        ta = time_aware(q["q"], plain, day)
        a, b = int(bool(plain) and plain[0] == q["right"]), int(bool(ta) and ta[0] == q["right"])
        top1["plain"].append(a)
        top1["time"].append(b)
        wins, losses, ties = wins + (b > a), losses + (b < a), ties + (b == a)
    price_plain, price_time = r["win"], []
    for q in dec:
        plain = rank(op, q["q"], winner)[0]
        price_time.append(recall_all_at(time_aware(q["q"], plain, day), set(q["relevant"])))
    piv = paired_interval(price_plain, price_time)
    base = sum(price_plain) / len(price_plain) if price_plain else 0.0
    p = sign_test(wins, losses)
    first = p < 0.05
    second = piv["ci95"][0] is not None and piv["ci95"][0] > -0.10 * base
    out["H4b"] = {"pairs_questions": len(top1["plain"]), "top1_plain": sum(top1["plain"]), "top1_time": sum(top1["time"]),
                  "wins": wins, "losses": losses, "ties": ties, "sign_test_p": round(p, 4),
                  "decision_price": {"plain": round(base, 4), "time_minus_plain": piv,
                                     "limit": round(-0.10 * base, 4)},
                  "verdict": "validated" if first and second else
                             ("contradicted" if losses > wins else "not reached")}

    # H4c: abstention threshold from dev positives; abstain share on in-vocabulary negatives.
    out["H4c_scores"] = {"decision": [round(rank(op, q["q"], winner)[1]["top_cos"], 4) for q in dec],
                         "none_invocab": [round(rank(op, q["q"], winner)[1]["top_cos"], 4)
                                          for q in qs if q["kind"] == "none_invocab"],
                         "none_oov": [round(rank(op, q["q"], winner)[1]["top_cos"], 4)
                                      for q in qs if q["kind"] == "none_oov"],
                         "grep_oov_returns": [len(grep_rank(op, q["q"], ts)[0]) for q in qs if q["kind"] == "none_oov"]}
    out["seconds"] = round(time.time() - t0, 1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main(*sys.argv[1:6])
