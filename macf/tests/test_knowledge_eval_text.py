"""knowledge eval's text rankers: what is indexed, BM25 and dense over it, and the two fusions.

The dense tests use a small deterministic embedder in place of MiniLM, so none loads a model.
"""

import math
import re
from collections import Counter

import pytest

from macf import knowledge_eval as ke
from macf import knowledge_eval_text as kt

N = 24
TOPICS = ("granite quarry", "violin bow", "comet orbit", "sourdough starter")


def _learning(i):
    return f"2026-01-{1 + i % 28:02d}_{i:06d}_note_{i:02d}_learning.md"


def _snapshot():
    """N learnings in four topics; each cross-references the next one in its topic."""
    nodes = {}
    for i in range(N):
        t = i % 4
        target = (i + 4) % N
        body = (f"# Note {i}\n\nA finding about the {TOPICS[t]}, recorded on day {i}.\n"
                f"\n## Cross-References\n\n- `{_learning(target)}`\n\n## Wiki-Links\n\n[[topic_{t}]]\n")
        nodes[f"learnings:{_learning(i)[:-3]}"] = {
            "type": "learnings", "class": "conceptual_authority", "title": f"Note {i} on the {TOPICS[t]}",
            "path": f"/home/a/agent/private/learnings/{_learning(i)}",
            "concepts": [f"topic_{t}"], "text": body, "in_web": True, "linked": True}
    return {"taken_at": "2026-02-02T00:00:00+0000", "nodes": nodes, "learnings_index": None}


def _bag_embedder(texts):
    """Unit vectors of hashed word counts: texts sharing words are near, so dense can be tested."""
    import numpy as np
    out = np.zeros((len(texts), 64), dtype="float32")
    for r, t in enumerate(texts):
        for w, n in Counter(kt.words(t)).items():
            out[r, sum(map(ord, w)) % 64] += n
        norm = math.sqrt(float((out[r] ** 2).sum())) or 1.0
        out[r] /= norm
    return out


@pytest.fixture
def corpus():
    c = ke.Corpus(_snapshot(), "e" * 64)
    c.embedder = _bag_embedder
    return c


class _Log:
    def __init__(self):
        self.rows = []

    def kw(self):
        return {"append": lambda e, d: self.rows.append({"event": e, "data": d, "timestamp": 1.0}),
                "events": lambda: iter(list(self.rows))}


def test_indexed_text_drops_the_label_bearing_parts_and_states_the_concepts_once():
    node = _snapshot()["nodes"][f"learnings:{_learning(0)[:-3]}"]
    extra = f'See [LEARNING 2026-01-05 "Note 4 on the granite quarry"] and {_learning(8)} for more.\n'
    node = dict(node, text=node["text"].replace("\n## Cross-References", extra + "\n## Cross-References"))
    assert _learning(8) in node["text"].split("## Cross-References")[0]
    for context in kt.CONTEXTS:
        text = kt.indexed_text(node, context)
        assert "Cross-References" not in text and "Wiki-Links" not in text
        assert "_learning" not in text and "[LEARNING" not in text
        assert len(re.findall(r"\btopic 0\b", text)) == 1
        assert "granite quarry, recorded on day 0" in text
    header = kt.indexed_text(node, "header")
    assert header.startswith("learning 2026-01-01 Note 0 on the granite quarry. Concepts: topic 0.")
    assert kt.indexed_text(node, "plain").endswith("topic 0")


def test_the_text_rankers_pass_the_leak_audit_their_raw_text_would_fail(corpus, monkeypatch):
    out = ke.evaluate(corpus, ["bm25", "dense", "hybrid-cc:0.5", "hybrid-rrf:60"], sources=("xref",),
                      boot=50, **_Log().kw())
    assert set(out["chart"]["leak_share"]) == {"bm25", "dense", "hybrid-cc:0.5", "hybrid-rrf:60"}
    assert all(v["xref"] == 0.0 for v in out["chart"]["leak_share"].values())
    # The same ranker reading the raw text, Cross-References and all, is refused.
    raw = kt.text_ranker("bm25")
    raw.reads = lambda q, c: c.nodes[q]["text"]
    with pytest.raises(ke.EvalRefused, match="names its target"):
        ke.evaluate(corpus, ["bm25raw"], sources=("xref",), extra_rankers={"bm25raw": raw}, **_Log().kw())


def test_bm25_and_dense_rank_the_same_topic_first(corpus):
    q = f"learnings:{_learning(0)[:-3]}"
    same = {f"learnings:{_learning(i)[:-3]}" for i in range(4, N, 4)}
    for name in ("bm25", "dense"):
        top = kt.text_ranker(name).rank(q, corpus)[:len(same)]
        assert set(top) == same, name
        assert q not in kt.text_ranker(name).rank(q, corpus)


def test_convex_combination_weights_dense_by_alpha_and_scores_a_missing_list_as_zero():
    bm25 = [("a", 10.0), ("b", 5.0), ("c", 0.0)]
    dense = [("c", 0.9), ("b", 0.5), ("d", 0.1)]
    # Each list's minimum normalizes to 0, the score an artifact missing from that list gets.
    assert kt.fuse_cc(bm25, dense, 0.0)[:2] == ["a", "b"] and set(kt.fuse_cc(bm25, dense, 0.0)[2:]) == {"c", "d"}
    assert kt.fuse_cc(bm25, dense, 1.0)[:2] == ["c", "b"] and set(kt.fuse_cc(bm25, dense, 1.0)[2:]) == {"a", "d"}
    # At 0.5: a = 0.5, b = 0.25 + 0.25, c = 0.5, d = 0; a tie between a and b and c broken stably.
    assert kt.fuse_cc(bm25, dense, 0.5)[-1] == "d"


def test_reciprocal_rank_fusion_sums_one_over_k_plus_rank():
    bm25 = [("a", 3.0), ("b", 2.0)]
    dense = [("b", 0.9), ("c", 0.8)]
    # b: 1/(k+2) + 1/(k+1), then a: 1/(k+1), then c: 1/(k+2), for any k > 0.
    for k in (1, 60):
        assert kt.fuse_rrf(bm25, dense, k) == ["b", "a", "c"]


def test_parameters_are_read_from_the_name_and_bad_ones_refused():
    assert kt.text_ranker("hybrid-cc:0.3").help.endswith("0.3 on dense")
    assert "k = 30" in kt.text_ranker("hybrid-rrf:30").help
    assert kt.text_ranker("hybrid-cc").help.endswith("0.5 on dense")
    assert kt.text_ranker("nonsense") is None
    for bad in ("hybrid-cc:1.5", "hybrid-rrf:0", "hybrid-cc:x"):
        with pytest.raises(ke.EvalRefused):
            kt.text_ranker(bad)
    with pytest.raises(ke.EvalRefused, match="unknown ranker"):
        ke.evaluate(ke.Corpus(_snapshot(), "e" * 64), ["bm26"], sources=("xref",), **_Log().kw())
