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


class EventLog:
    """An in-memory event log: the seal and held runs go through it as they would the agent's."""

    def __init__(self):
        self.rows = []

    def append(self, event, data):
        self.rows.append({"event": event, "data": data, "timestamp": 1792000000.0 + len(self.rows)})

    def read(self):
        return iter(list(self.rows))

    def kw(self):
        return {"append": self.append, "events": self.read}


@pytest.fixture
def log():
    return EventLog()


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


def test_concept_ranking_beats_the_floor_and_today_is_scored_from_the_snapshot(corpus, log):
    out = ke.evaluate(corpus, ["random", "today", "idf"], sources=["xref"], **log.kw(), boot=50)
    r = out["results"]["xref"]
    assert r["idf"]["MRR"]["mean"] > r["random"]["MRR"]["mean"]
    assert r["today"]["returned_share"]["mean"] > 0


def test_every_held_run_is_an_event_and_the_count_is_a_fold_over_the_log(corpus, log):
    """The seed is sealed by its first run, dev or held; each held run is an event; the count a
    report prints is read back from the log, so another seed's runs don't count."""
    first = ke.evaluate(corpus, ["idf"], sources=["xref"], **log.kw(), boot=10)
    assert first["chart"]["seal"]["held_runs_before"] == 0          # sealed by the dev run
    sealed = [r for r in log.rows if r["event"] == ke.EVENT_SEALED]
    held_ids = ke.split(ke.xref_labels(corpus)[0], ke.DEFAULT_SEED)[1]
    assert len(sealed) == 1 and sealed[0]["data"]["held_ids_sha256"]["xref"] == ke.ids_digest(held_ids)
    one = ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", **log.kw(), boot=10)
    ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", seed="other", **log.kw(), boot=10)
    two = ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", **log.kw(), boot=10)
    assert one["chart"]["seal"]["this_held_run"] == 1
    assert two["chart"]["seal"]["held_runs_before"] == 1 and two["chart"]["seal"]["this_held_run"] == 2
    runs = [r["data"] for r in log.rows if r["event"] == ke.EVENT_HELD_RUN]
    assert [r["seed"] for r in runs] == [ke.DEFAULT_SEED, "other", ke.DEFAULT_SEED]
    assert runs[0]["snapshot"] == corpus.digest and runs[0]["rankers"] == ["idf"]
    assert sum(1 for r in log.rows if r["event"] == ke.EVENT_SEALED) == 2     # one per seed


def test_a_ranker_that_reads_the_cross_references_is_refused_by_name(corpus, log):
    """The planted leak: a text ranker whose input includes the section that names the answer."""
    def reads_all(q, c):
        return c.nodes[q]["text"]

    def rank(q, c):
        seen = ke._norm(reads_all(q, c))
        return sorted((x for x in c.web if x != q), key=lambda x: not any(n in seen for n in ke._names(c.nodes[x])))

    leaky = ke.Ranker("leaky", rank, "reads the whole body", reads=reads_all)
    with pytest.raises(ke.EvalRefused, match=r"ranker 'leaky' reads text that names its target"):
        ke.evaluate(corpus, ["leaky"], sources=["xref"], **log.kw(),
                    extra_rankers={"leaky": leaky}, boot=10)


def test_the_same_ranker_is_scored_once_its_input_no_longer_names_the_answer(corpus, log):
    """The opposite control: strip the section, and the audit goes quiet."""
    def reads_clean(q, c):
        return re.sub(r"## Cross-References.*", "", c.nodes[q]["text"], flags=re.S)

    clean = ke.Ranker("clean", lambda q, c: ke._idf(q, c), "reads the body without its references", reads=reads_clean)
    out = ke.evaluate(corpus, ["clean"], sources=["xref"], **log.kw(),
                      extra_rankers={"clean": clean}, boot=10)
    assert out["results"]["xref"]["clean"]["MRR"]["mean"] > 0


def test_two_runs_on_one_snapshot_give_identical_results(corpus, log):
    a = ke.evaluate(corpus, ["random", "today", "idf"], **log.kw(), compare=("today", "idf"), boot=100)
    b = ke.evaluate(ke.Corpus(_snapshot(), "f" * 64), ["random", "today", "idf"], **log.kw(),
                    compare=("today", "idf"), boot=100)
    assert json.dumps(a["results"], sort_keys=True) == json.dumps(b["results"], sort_keys=True)
    assert a["comparison"] == b["comparison"]


def test_metrics_rank_a_relevant_item_by_its_position():
    rel = {"b"}
    assert ke.mrr(["a", "b", "c"], rel) == 0.5 and ke.mrr(["b", "a"], rel) == 1.0 and ke.mrr(["a"], rel) == 0.0
    assert ke.ndcg_at(["b"], rel) == 1.0 and 0 < ke.ndcg_at(["a", "b"], rel) < 1.0
    assert ke.recall_at(["a", "b"], {"b", "z"}) == 0.5


def test_a_snapshot_saves_owner_only_and_reloads_to_the_same_digest(tmp_path):
    """Created 0600 whatever the umask, and an existing readable file is narrowed before it is
    written, so the private text is never readable by others."""
    import os
    p = tmp_path / "snap.json"
    old = os.umask(0o000)
    try:
        digest = ke.save_snapshot(_snapshot(), p)
    finally:
        os.umask(old)
    assert p.stat().st_mode & 0o777 == 0o600
    assert ke.load_snapshot(p)[1] == digest
    p.chmod(0o644)
    ke.save_snapshot(_snapshot(), p)
    assert p.stat().st_mode & 0o777 == 0o600


def test_a_target_with_no_name_to_search_for_is_unauditable_not_clean(corpus):
    """Pairs whose target can't be searched for are counted apart and left out of the share, so
    they can't pull a leaking ranker under the limit."""
    labels = ke.xref_labels(corpus)[0]                        # labels first: they resolve by file name
    for nid, n in corpus.nodes.items():
        if n["type"] == "learnings" and int(nid.split("_")[1]) % 2:
            n["path"], n["title"] = "/x/a.md", "short"
    reader = ke.Ranker("reader", ke._idf, "reads the whole body", reads=lambda q, c: c.nodes[q]["text"])
    audit = ke.leak_audit(reader, sorted(labels), labels, corpus)
    assert audit.unauditable == N // 2 and audit.audited == N // 2
    assert audit.share == len(audit.leaks) / audit.audited


def test_the_command_scores_a_pinned_snapshot_and_refuses_an_unknown_ranker(tmp_path, capsys, monkeypatch):
    from macf.cli import cmd_knowledge_eval
    p = tmp_path / "snap.json"
    ke.save_snapshot(_snapshot(), p)
    log = EventLog()
    monkeypatch.setattr(ke, "_default_append", log.append)
    monkeypatch.setattr(ke, "_default_events", log.read)
    base = {"snapshot": str(p), "save_snapshot": None, "exclude": None, "rankers": ["idf"], "labels": ["xref"],
            "split": "dev", "split_seed": "t", "compare": None, "json_output": True}
    assert cmd_knowledge_eval(Namespace(**base)) == 0
    assert json.loads(capsys.readouterr().out)["results"]["xref"]["idf"]["MRR"]["mean"] > 0
    assert cmd_knowledge_eval(Namespace(**{**base, "rankers": ["nope"]})) == 2
    assert "unknown ranker 'nope'" in capsys.readouterr().out


def test_held_runs_go_through_the_real_event_log_and_a_failed_append_refuses(corpus, isolated_events_log, monkeypatch):
    """No stand-in log: the seal and two held runs are appended to the agent's event log (isolated
    here), the count is read back from it, and a run whose event can't be appended is refused
    rather than scored uncounted (the head maintainer's surviving plant on #750)."""
    from macf import agent_events_log
    ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", boot=10)
    second = ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", boot=10)
    assert second["chart"]["seal"]["held_runs_before"] == 1 and second["chart"]["seal"]["this_held_run"] == 2
    written = [json.loads(line)["event"] for line in isolated_events_log.read_text().splitlines()]
    assert written.count(ke.EVENT_SEALED) == 1 and written.count(ke.EVENT_HELD_RUN) == 2
    monkeypatch.setattr(agent_events_log, "append_event", lambda *a, **k: False)
    with pytest.raises(ke.EvalRefused, match="could not record knowledge_eval_held_run"):
        ke.evaluate(corpus, ["idf"], sources=["xref"], which="held", boot=10)
