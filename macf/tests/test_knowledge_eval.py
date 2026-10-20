"""knowledge eval: labels from the agent's own artifacts, a sealed held split, a leak audit.

Every test builds a small synthetic snapshot, so none reads the agent's real corpus.
"""

import json
import re
from argparse import Namespace

import pytest

from macf import knowledge_eval as ke

N = 40


def _learning(i):
    return f"2026-01-{1 + i % 28:02d}_{i:06d}_topic_{i:02d}_learning.md"


def _snapshot(cross_refs=True):
    """N learnings in four topics. Each cross-references the next learning in its topic, and
    shares its topic's concept with it, so a concept ranker can find it and random can't."""
    nodes = {}
    for i in range(N):
        topic = i % 4
        target = (i + 4) % N
        body = f"# Topic {topic} note {i}\n\nSomething learned.\n"
        if cross_refs:
            body += f"\n## Cross-References\n\n- `{_learning(target)}`\n"
        nodes[f"learnings:{_learning(i)[:-3]}"] = {
            "type": "learnings", "class": "conceptual_authority", "title": f"Topic {topic} note {i}",
            "path": f"/home/a/agent/private/learnings/{_learning(i)}",
            "concepts": [f"topic_{topic}", "shared"], "text": body, "in_web": True, "linked": True}
    nodes["reflections:2026-02-01_JOTEWR_x"] = {
        "type": "reflections", "class": "temporal_record", "title": "a reflection",
        "path": "/home/a/agent/private/reflections/2026-02-01_JOTEWR_x.md", "concepts": ["shared"],
        "text": '[LEARNING 2026-01-02 "topic 01"]', "in_web": True, "linked": True}
    index = "## Cluster A\n" + "\n".join(f"- {_learning(i)}" for i in range(0, N, 4))
    return {"taken_at": "2026-02-02T00:00:00+0000", "nodes": nodes, "learnings_index": index}


@pytest.fixture
def corpus():
    snap = _snapshot()
    return ke.Corpus(snap, "f" * 64)


def test_labels_come_from_cross_references_citations_and_index_clusters(corpus):
    xref, _ = ke.xref_labels(corpus)
    assert len(xref) == N
    assert xref[f"learnings:{_learning(0)[:-3]}"] == {f"learnings:{_learning(4)[:-3]}"}
    cites, unresolved = ke.citation_labels(corpus)
    assert cites == {"reflections:2026-02-01_JOTEWR_x": {f"learnings:{_learning(1)[:-3]}"}} and unresolved == 0
    same, _ = ke.same_subject_labels(corpus, corpus.snap["learnings_index"])
    assert len(same) == N // 4 and all(len(v) == N // 4 - 1 for v in same.values())


def test_the_split_is_stable_and_a_query_keeps_its_side_as_the_corpus_grows():
    ids = [f"q{i}" for i in range(500)]
    dev, held = ke.split(ids, "s")
    assert 0.15 < len(held) / 500 < 0.25
    dev2, held2 = ke.split(ids + [f"new{i}" for i in range(100)], "s")
    assert set(held) <= set(held2) and set(dev) <= set(dev2)


def test_concept_ranking_beats_the_floor_and_today_is_scored_from_the_snapshot(corpus, tmp_path):
    out = ke.evaluate(corpus, ["random", "today", "idf"], sources=["xref"], seal_path=tmp_path / "seal.json", boot=50)
    r = out["results"]["xref"]
    assert r["idf"]["MRR"]["mean"] > r["random"]["MRR"]["mean"]
    assert r["today"]["returned_share"]["mean"] > 0


def test_every_held_run_is_recorded_and_counted_on_the_next(corpus, tmp_path):
    seal = tmp_path / "seal.json"
    first = ke.evaluate(corpus, ["idf"], sources=["xref"], seal_path=seal, boot=10)
    assert first["chart"]["seal"]["held_runs_before"] == 0          # sealed by the dev run
    sealed = json.loads(seal.read_text())[ke.DEFAULT_SEED]
    held_ids = ke.split(ke.xref_labels(corpus)[0], ke.DEFAULT_SEED)[1]
    assert sealed["held_ids_sha256"]["xref"] == ke.ids_digest(held_ids)
    one = ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", seal_path=seal, boot=10)
    two = ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", seal_path=seal, boot=10)
    assert one["chart"]["seal"]["this_held_run"] == 1
    assert two["chart"]["seal"]["held_runs_before"] == 1 and two["chart"]["seal"]["this_held_run"] == 2
    assert len(json.loads(seal.read_text())[ke.DEFAULT_SEED]["held_runs"]) == 2


def test_a_ranker_that_reads_the_cross_references_is_refused_by_name(corpus, tmp_path):
    """The planted leak: a text ranker whose input includes the section that names the answer."""
    def reads_all(q, c):
        return c.nodes[q]["text"]

    def rank(q, c):
        seen = ke._norm(reads_all(q, c))
        return sorted((x for x in c.web if x != q), key=lambda x: not any(n in seen for n in ke._names(c.nodes[x])))

    leaky = ke.Ranker("leaky", rank, "reads the whole body", reads=reads_all)
    with pytest.raises(ke.EvalRefused, match=r"ranker 'leaky' reads text that names its target"):
        ke.evaluate(corpus, ["leaky"], sources=["xref"], seal_path=tmp_path / "s.json",
                    extra_rankers={"leaky": leaky}, boot=10)


def test_the_same_ranker_is_scored_once_its_input_no_longer_names_the_answer(corpus, tmp_path):
    """The opposite control: strip the section, and the audit goes quiet."""
    def reads_clean(q, c):
        return re.sub(r"## Cross-References.*", "", c.nodes[q]["text"], flags=re.S)

    clean = ke.Ranker("clean", lambda q, c: ke._idf(q, c), "reads the body without its references", reads=reads_clean)
    out = ke.evaluate(corpus, ["clean"], sources=["xref"], seal_path=tmp_path / "s.json",
                      extra_rankers={"clean": clean}, boot=10)
    assert out["results"]["xref"]["clean"]["MRR"]["mean"] > 0


def test_two_runs_on_one_snapshot_give_identical_results(corpus, tmp_path):
    seal = tmp_path / "s.json"
    a = ke.evaluate(corpus, ["random", "today", "idf"], seal_path=seal, compare=("today", "idf"), boot=100)
    b = ke.evaluate(ke.Corpus(_snapshot(), "f" * 64), ["random", "today", "idf"], seal_path=seal,
                    compare=("today", "idf"), boot=100)
    assert json.dumps(a["results"], sort_keys=True) == json.dumps(b["results"], sort_keys=True)
    assert a["comparison"] == b["comparison"]


def test_metrics_rank_a_relevant_item_by_its_position():
    rel = {"b"}
    assert ke.mrr(["a", "b", "c"], rel) == 0.5 and ke.mrr(["b", "a"], rel) == 1.0 and ke.mrr(["a"], rel) == 0.0
    assert ke.ndcg_at(["b"], rel) == 1.0 and 0 < ke.ndcg_at(["a", "b"], rel) < 1.0
    assert ke.recall_at(["a", "b"], {"b", "z"}) == 0.5


def test_a_snapshot_saves_owner_only_and_reloads_to_the_same_digest(tmp_path):
    p = tmp_path / "snap.json"
    digest = ke.save_snapshot(_snapshot(), p)
    assert p.stat().st_mode & 0o777 == 0o600
    assert ke.load_snapshot(p)[1] == digest


def test_the_command_scores_a_pinned_snapshot_and_refuses_an_unknown_ranker(tmp_path, capsys):
    from macf.cli import cmd_knowledge_eval
    p = tmp_path / "snap.json"
    ke.save_snapshot(_snapshot(), p)
    base = dict(snapshot=str(p), save_snapshot=None, exclude=None, rankers=["idf"], labels=["xref"],
                split="dev", split_seed="t", seal=str(tmp_path / "seal.json"), compare=None, json_output=True)
    assert cmd_knowledge_eval(Namespace(**base)) == 0
    assert json.loads(capsys.readouterr().out)["results"]["xref"]["idf"]["MRR"]["mean"] > 0
    assert cmd_knowledge_eval(Namespace(**{**base, "rankers": ["nope"]})) == 2
    assert "unknown ranker 'nope'" in capsys.readouterr().out
