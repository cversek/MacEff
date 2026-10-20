"""knowledge query ranks: summed IDF, an expansion threshold, several terms, --like.

Each test builds a small web by hand, so every score can be worked out on paper.
"""

import json
from argparse import Namespace

import pytest

from macf.knowledge_web import concept_idf, query_knowledge_web


def _web(membership):
    """A web from {node: [concepts]}; edges join nodes that share a concept, as the builder's do."""
    wiki, edges = {}, {}
    for node, concepts in membership.items():
        for c in concepts:
            wiki.setdefault(c, set()).add(node)
    for members in wiki.values():
        for a in members:
            edges.setdefault(a, set()).update(members - {a})
    ca = {n: {"type": "learnings", "title": n, "path": f"/x/{n}.md", "node_class": "conceptual_authority"}
          for n in membership}
    return {"ideas": {}, "ca_nodes": ca, "edges": edges, "wiki_index": wiki, "stats": {}}


# Twelve nodes. "common" is on ten of them; "rare" on two; "mid" on four.
WEB = _web({
    "learnings:a": ["rare", "common", "mid"], "learnings:b": ["rare", "common"],
    "learnings:c": ["mid", "common"], "learnings:d": ["mid", "common"], "learnings:e": ["mid"],
    **{f"learnings:f{i}": ["common"] for i in range(6)}, "learnings:g": ["other"],
})


def ids(nodes):
    return [n["id"] for n in nodes]


def test_a_node_sharing_rarer_concepts_ranks_higher():
    """--like a: b shares rare and common, c shares mid and common, and rare is rarer than mid."""
    idf = concept_idf(WEB)
    r = query_knowledge_web(like="learnings:a", kg=WEB, min_idf=0.0)
    assert ids(r["nodes"])[0] == "learnings:b"
    by = {n["id"]: n["score"] for n in r["nodes"]}
    assert by["learnings:b"] == pytest.approx(idf["rare"] + idf["common"], abs=1e-3)
    assert by["learnings:b"] > by["learnings:c"] > by["learnings:f0"]
    assert "learnings:a" not in by                          # the query node is never its own answer


def test_the_threshold_admits_only_specific_concepts():
    """At min_idf above common's IDF, nodes reached only through common drop out."""
    idf = concept_idf(WEB)
    loose = query_knowledge_web(like="learnings:a", kg=WEB, min_idf=0.0)
    tight = query_knowledge_web(like="learnings:a", kg=WEB, min_idf=idf["common"] + 0.01)
    assert "learnings:f0" in ids(loose["nodes"]) and "learnings:f0" not in ids(tight["nodes"])
    assert set(ids(tight["nodes"])) == {"learnings:b", "learnings:c", "learnings:d", "learnings:e"}


def test_equal_scores_go_to_the_more_specific_node_first():
    """c and e both share mid with a query on mid; e has fewer concepts, so it comes first."""
    r = query_knowledge_web("mid", kg=WEB, min_idf=99)
    order = ids(r["nodes"])
    assert order.index("learnings:e") < order.index("learnings:c")
    assert order.index("learnings:e") < order.index("learnings:d")


def test_several_terms_match_all_by_default_and_any_on_request():
    both = query_knowledge_web(["rare", "mid"], kg=WEB)
    either = query_knowledge_web(["rare", "mid"], kg=WEB, any_term=True)
    assert ids(both["nodes"]) == ["learnings:a"]
    assert set(ids(either["nodes"])) == {"learnings:a", "learnings:b", "learnings:c", "learnings:d", "learnings:e"}
    assert query_knowledge_web(["rare", "nothing-matches-this"], kg=WEB)["match_type"] == "none"


def test_neighbours_come_only_through_specific_concepts_and_say_through_what():
    """A query on rare matches a and b. Their other concepts are mid and common; at a threshold
    between the two, neighbours come through mid only, and each names it."""
    idf = concept_idf(WEB)
    r = query_knowledge_web("rare", kg=WEB, min_idf=(idf["mid"] + idf["common"]) / 2)
    assert set(ids(r["neighbors"])) == {"learnings:c", "learnings:d", "learnings:e"}
    assert all(n["via"] == ["mid"] for n in r["neighbors"])


def test_two_runs_give_the_same_order():
    a = query_knowledge_web(like="learnings:a", kg=WEB, min_idf=0.0)
    b = query_knowledge_web(like="learnings:a", kg=WEB, min_idf=0.0)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_like_refuses_a_node_it_cannot_name():
    with pytest.raises(ValueError, match="names no node"):
        query_knowledge_web(like="learnings:nope", kg=WEB)
    with pytest.raises(ValueError, match="names 6 nodes"):
        query_knowledge_web(like="learnings:f", kg=WEB)


def test_the_command_ranks_and_refuses_terms_with_like(monkeypatch, capsys):
    from macf import knowledge_web
    from macf.cli import cmd_knowledge_query
    monkeypatch.setattr(knowledge_web, "build_knowledge_web", lambda *a, **k: WEB)
    base = {"term": [], "like": "learnings:a", "any_term": False, "min_idf": 0.0, "node_class": None, "json_output": True}
    assert cmd_knowledge_query(Namespace(**base)) == 0
    nodes = json.loads(capsys.readouterr().out)["nodes"]
    assert nodes[0]["id"] == "learnings:b" and nodes == sorted(nodes, key=lambda n: -n["score"])
    assert cmd_knowledge_query(Namespace(**{**base, "term": ["rare"]})) == 2
    assert "not both" in capsys.readouterr().out
