"""#1170: policy search says which mode actually ran.

The hybrid call fell back to vector search on every query and nothing said so, while the
recommender labelled each result "hybrid". These tests use a stand-in table, so no model or index
is loaded; they pin the reporting, not the ranking, which MIS-0006's landing decides.
"""
import pytest

from macf.hybrid_search import policy_search
from macf.hybrid_search.policy_search import PolicySearch


class _Model:
    def encode(self, text):
        return [0.0, 1.0]


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, n):
        return self

    def to_list(self):
        return list(self.rows)


class _Index:
    def __init__(self, name, index_type):
        self.name, self.index_type = name, index_type


class _Table:
    """A documents table whose hybrid search either works or raises, as told."""

    def __init__(self, hybrid_error=None, indices=()):
        self.hybrid_error = hybrid_error
        self.indices = list(indices)
        self.created = []
        self.row = {"policy_name": "git_discipline", "_distance": 0.25, "content": "x" * 10,
                    "section_count": 1}

    def search(self, embedding, query_type=None):
        if query_type == "hybrid" and self.hybrid_error:
            raise self.hybrid_error
        return _Query([self.row])

    def list_indices(self):
        return self.indices

    def create_fts_index(self, column, replace=False):
        self.created.append(column)


def _searcher(table):
    ps = PolicySearch.__new__(PolicySearch)
    ps._model, ps._documents_table, ps._questions_table, ps._db = _Model(), table, None, None
    return ps


@pytest.fixture(autouse=True)
def _fresh_warning(monkeypatch):
    monkeypatch.setattr(policy_search, "_FALLBACK_WARNED", False)


def test_a_fallback_is_reported_as_a_fallback_and_warned_once(capsys):
    ps = _searcher(_Table(hybrid_error=ValueError("Text query must be a string or FullTextQuery")))
    first = ps.hybrid_search("how do I merge", limit=1)
    second = ps.hybrid_search("how do I merge", limit=1)
    assert first["search_type"] == "semantic" and second["search_type"] == "semantic"
    assert "Text query must be a string" in first["fallback_reason"]
    err = capsys.readouterr().err
    assert err.count("hybrid is unavailable, so results are semantic only") == 1, "warned once, not per query"


def test_a_hybrid_search_that_runs_says_hybrid_with_no_reason(capsys):
    r = _searcher(_Table()).hybrid_search("how do I merge", limit=1)
    assert r["search_type"] == "hybrid" and r["fallback_reason"] == ""
    assert capsys.readouterr().err == ""


def test_the_recommender_labels_results_with_the_mode_that_ran(monkeypatch):
    from macf.utils import recommend
    ps = _searcher(_Table(hybrid_error=RuntimeError("no INVERTED index")))
    monkeypatch.setattr(ps, "search_questions", lambda q, limit=10: [])
    monkeypatch.setattr(recommend, "get_searcher", lambda: ps)
    [rec] = recommend.search_policies("how do I merge a pull request", limit=1)
    assert list(rec.retriever_contributions) == ["semantic"]
    assert rec.retriever_contributions["semantic"].retriever == "semantic"


def test_checking_for_the_full_text_index_writes_nothing():
    absent = _Table()
    assert _searcher(absent).check_fts_support()["fts_available"] is False
    present = _Table(indices=[_Index("content_idx", "FTS")])
    assert _searcher(present).check_fts_support() == {"fts_available": True,
                                                      "message": "full-text index present: content_idx"}
    assert absent.created == [] and present.created == [], "a check never creates an index"
    assert _searcher(absent).ensure_fts_index()["fts_available"] is True and absent.created == ["content"]


def test_an_unreadable_index_list_is_reported_as_unavailable():
    """A list that can't be read is no evidence of an index, so the check says unavailable and why."""
    class _Broken(_Table):
        def list_indices(self):
            raise OSError("table directory unreadable")
    r = _searcher(_Broken()).check_fts_support()
    assert r["fts_available"] is False and "can't be read" in r["message"]
