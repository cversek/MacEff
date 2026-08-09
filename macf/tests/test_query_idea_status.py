"""Idea status is a queryable node property so retrieval can tell a proposal
from a finding (#121). This locks the property (satisfied via #216's extraction)
so it cannot silently regress."""
from macf.knowledge_web import query_knowledge_web


def test_query_result_carries_idea_status():
    kg = {
        "ideas": {
            1: {"title": "A proposal", "status": "captured", "category": "tooling"},
            2: {"title": "A finding", "status": "promoted", "category": "tooling"},
        },
        "ca_nodes": {},
        "wiki_index": {"topic": {1, 2}},
        "edges": {1: {2}, 2: {1}},
        "stats": {},
    }
    result = query_knowledge_web("topic", kg)
    nodes = list(result.get("nodes", [])) + list(result.get("neighbors", []))
    by_id = {n["id"]: n for n in nodes}
    # The proposal-vs-finding weighting must be present per idea node.
    assert by_id["1"]["status"] == "captured"
    assert by_id["2"]["status"] == "promoted"
