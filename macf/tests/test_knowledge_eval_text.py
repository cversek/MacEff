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
    with pytest.raises(ke.EvalRefused, match="--context is one of"):
        kt.indexed_text(node, "footer")


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
    # A list of one scores its member 1, not 0, so the weight decides between two singletons.
    assert kt.fuse_cc([("a", 5.0)], [("b", 0.3)], 0.3) == ["a", "b"]
    assert kt.fuse_cc([("a", 5.0)], [("b", 0.3)], 0.7) == ["b", "a"]


def test_reciprocal_rank_fusion_sums_one_over_k_plus_rank():
    bm25 = [("a", 3.0), ("b", 2.0)]
    dense = [("b", 0.9), ("c", 0.8)]
    # b: 1/(k+2) + 1/(k+1), then a: 1/(k+1), then c: 1/(k+2), for any k > 0.
    for k in (1, 60):
        assert kt.fuse_rrf(bm25, dense, k) == ["b", "a", "c"]
    # Ranks count from 1: x, first in one list, scores 1/(k+1); y, third in both, 2/(k+3). At k = 1.5,
    # y leads; ranks counted from 0 would give x 1/k against y's 2/(k+2) and put x first.
    assert kt.fuse_rrf([("x", 9.0), ("p", 8.0), ("y", 7.0)], [("q", 9.0), ("r", 8.0), ("y", 7.0)], 1.5)[0] == "y"
    for bad in ("hybrid-rrf:nan", "hybrid-rrf:inf", "hybrid-cc:nan"):
        with pytest.raises(ke.EvalRefused):
            kt.text_ranker(bad)


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


def test_a_context_after_an_at_sign_scores_both_arms_in_one_run(corpus):
    q = f"learnings:{_learning(0)[:-3]}"
    plain, header = kt.text_ranker("bm25"), kt.text_ranker("bm25@header")
    assert plain.reads(q, corpus).endswith("topic 0")
    assert header.reads(q, corpus).startswith("learning 2026-01-01 Note 0")
    out = ke.evaluate(corpus, ["hybrid-cc:0.5", "hybrid-cc:0.5@header"], sources=("xref",), boot=50,
                      compare=("hybrid-cc:0.5", "hybrid-cc:0.5@header"), **_Log().kw())
    assert set(out["chart"]["leak_share"]) == {"hybrid-cc:0.5", "hybrid-cc:0.5@header"}
    assert "xref" in out["comparison"]
    with pytest.raises(ke.EvalRefused, match="context after"):
        kt.text_ranker("bm25@footer")


def test_the_model_context_puts_the_written_text_first_and_needs_a_file(corpus):
    q = f"learnings:{_learning(0)[:-3]}"
    with pytest.raises(ke.EvalRefused, match="context-file"):
        kt.text_ranker("bm25@model").reads(q, corpus)
    corpus.model_contexts = {n: f"A learning, {n[-12:]}." for n in corpus.web}
    corpus.model_contexts[q] = "A learning about quarrying granite."
    text = kt.text_ranker("bm25@model").reads(q, corpus)
    assert text.startswith("A learning about quarrying granite.")
    assert text.endswith(kt.text_ranker("bm25").reads(q, corpus))


def test_a_long_artifact_is_embedded_in_windows_and_averaged(corpus):
    seen = []

    def recording(texts):
        seen.extend(texts)
        return _bag_embedder(texts)
    q = f"learnings:{_learning(0)[:-3]}"
    body = corpus.nodes[q]["text"].replace("\n## Cross-References", " filler" * (2 * kt.CHUNK_WORDS) + "\n## Cross-References")
    corpus.nodes[q] = dict(corpus.nodes[q], text=body)   # in the body: text after Wiki-Links is not indexed
    corpus.embedder = recording
    v = kt.text_index(corpus).vectors()
    words_q = len(kt.text_index(corpus).text[q].split())
    assert sum(1 for t in seen if "filler" in t) == -(-words_q // kt.CHUNK_WORDS) >= 3
    import numpy as np
    windows = [kt.text_index(corpus).text[q].split()[i:i + kt.CHUNK_WORDS] for i in range(0, words_q, kt.CHUNK_WORDS)]
    mean = _bag_embedder([" ".join(w) for w in windows]).sum(axis=0)
    assert np.allclose(v[kt.text_index(corpus).ids.index(q)], mean / np.linalg.norm(mean), atol=1e-6)


def test_the_command_takes_context_boot_and_refuses_a_mis_keyed_context_file(tmp_path, capsys, monkeypatch):
    import json
    from argparse import Namespace
    from macf.cli import cmd_knowledge_eval
    snap = _snapshot()
    p = tmp_path / "snap.json"
    ke.save_snapshot(snap, p)
    log = _Log()
    monkeypatch.setattr(ke, "_default_append", log.kw()["append"])
    monkeypatch.setattr(ke, "_default_events", log.kw()["events"])
    base = {"snapshot": str(p), "save_snapshot": None, "exclude": None, "rankers": ["bm25@header"], "labels": ["xref"],
            "split": "dev", "split_seed": "t", "compare": None, "json_output": True,
            "context": "header", "boot": 37, "context_file": None}
    assert cmd_knowledge_eval(Namespace(**base)) == 0
    chart = json.loads(capsys.readouterr().out)["chart"]
    assert chart["context"] == "header" and chart["bootstrap"] == 37
    by_path = tmp_path / "by_path.json"
    by_path.write_text(json.dumps({"contexts": {v["path"]: "context" for v in snap["nodes"].values()}}))
    assert cmd_knowledge_eval(Namespace(**{**base, "rankers": ["bm25@model"], "context_file": str(by_path)})) == 2
    assert "covers 0 of the 24" in capsys.readouterr().out
    by_id = tmp_path / "by_id.json"
    by_id.write_text(json.dumps({"contexts": {k: "a note" for k in snap["nodes"]}}))
    assert cmd_knowledge_eval(Namespace(**{**base, "rankers": ["bm25@model"], "context_file": str(by_id),
                                           "json_output": False})) == 0
    assert "model-written contexts for 24 of the 24 artifacts" in capsys.readouterr().out
