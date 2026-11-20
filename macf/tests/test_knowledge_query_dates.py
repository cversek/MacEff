"""knowledge query shows each result's date, filters with --since, and orders newest first with --recent (#1040)."""
import io
import json
from argparse import Namespace
from contextlib import redirect_stdout
from functools import partial

import pytest

from macf import knowledge_web
from macf.cli import cmd_knowledge_query
from macf.knowledge_web import node_date, query_knowledge_web

MEMBERS = {
    "learnings:2026-11-20_131800_a": ["topic"],       # dated by its name
    "checkpoints:2026-11-18_b": ["topic"],
    "roadmaps:2026-10-01_plan/roadmap.md": ["topic"],   # dated by its folder's name
    "learnings:no_date_here": ["topic"],
    "learnings:2025-01-05_old": ["topic", "extra"],
}


def _web():
    wiki = {}
    for node, concepts in MEMBERS.items():
        for c in concepts:
            wiki.setdefault(c, set()).add(node)
    edges = {a: set(m) - {a} for m in wiki.values() for a in m}
    ca = {n: {"type": n.split(":")[0], "title": n, "node_class": "conceptual_authority"} for n in MEMBERS}
    return {"ideas": {}, "ca_nodes": ca, "edges": edges, "wiki_index": wiki, "stats": {}}


def _run(monkeypatch, **flags):
    kg = _web()
    monkeypatch.setattr(knowledge_web, "query_knowledge_web", partial(query_knowledge_web, kg=kg))
    args = Namespace(**{"term": ["topic"], "like": None, "any_term": False, "min_idf": 0.0, "node_class": None,
                        "json_output": True, "since": None, "recent": False, **flags})
    out = io.StringIO()
    with redirect_stdout(out):
        rc = cmd_knowledge_query(args)
    return rc, out.getvalue()


def test_a_date_comes_from_the_name_or_the_folder_and_an_undated_node_says_none():
    assert node_date("learnings:2026-11-20_131800_a") == "2026-11-20"
    assert node_date("roadmaps:2026-10-01_plan/roadmap.md") == "2026-10-01"
    assert node_date("learnings:no_date_here") is None
    assert node_date(7, {"created": "2026-11-01T10:00:00"}) == "2026-11-01"


def test_every_result_carries_its_date(monkeypatch):
    rc, out = _run(monkeypatch)
    dates = {n["id"]: n["date"] for n in json.loads(out)["nodes"]}
    assert rc == 0 and dates["checkpoints:2026-11-18_b"] == "2026-11-18" and dates["learnings:no_date_here"] is None


def test_since_keeps_the_newer_and_counts_the_undated_it_left_out(monkeypatch):
    rc, out = _run(monkeypatch, since="2026-11-01")
    r = json.loads(out)
    assert {n["id"] for n in r["nodes"]} == {"learnings:2026-11-20_131800_a", "checkpoints:2026-11-18_b"}
    assert r["since"] == "2026-11-01" and r["undated_left_out"] == 1


def test_recent_orders_newest_first_and_puts_the_undated_last(monkeypatch):
    rc, out = _run(monkeypatch, recent=True)
    order = [n["date"] for n in json.loads(out)["nodes"]]
    assert order == ["2026-11-20", "2026-11-18", "2026-10-01", "2025-01-05", None]


def test_a_bad_since_is_refused(monkeypatch, capsys):
    rc, _ = _run(monkeypatch, since="last tuesday")
    assert rc == 2
