"""Controls for the MacEff style rules ruff cannot express.

Every rule gets BOTH POLARITIES. A suite that only plants violations passes
against a checker that flags everything, and one that only checks clean input
passes against a checker that flags nothing -- and a checker that flags nothing
is the dead control this whole ruleset exists to prevent.

The clean controls are not decoration. Each one is a shape that LOOKS like the
violation and is explicitly permitted by the standards, so it pins the boundary
rather than the centre.
"""
import textwrap

import pytest

from macf.style import (PARENT_CHAIN_LIMIT, Finding, Report, check_paths,
                        check_source)


def codes(src: str) -> list:
    return [f.code for f in check_source(textwrap.dedent(src))]


class TestImportInsideExceptHandler:
    """MACEFF001 -- base/coding_standards §6, recorded there as FP#28."""

    def test_import_inside_an_except_handler_is_flagged(self):
        assert "MACEFF001" in codes("""
            def f():
                try:
                    g()
                except OSError as e:
                    import sys
                    print(e, file=sys.stderr)
        """)

    def test_a_deferred_import_OUTSIDE_a_handler_is_permitted(self):
        """THE BOUNDARY, and the reason PLC0415 was rejected. The standards
        explicitly allow a justified deferred import -- paths.py needs one
        because session.py imports from it and a module-level import would be
        circular. A rule that flagged this would fire ~657 times here against
        our own policy."""
        assert "MACEFF001" not in codes("""
            def f():
                from .session import get_current_session_id
                return get_current_session_id()
        """)

    def test_module_level_import_is_permitted(self):
        assert "MACEFF001" not in codes("""
            import sys

            def f():
                try:
                    g()
                except OSError as e:
                    print(e, file=sys.stderr)
        """)


class TestParentChainNavigation:
    """MACEFF002 -- §5, whose recorded consequence is 9 tests silently skipping."""

    def test_two_hops_are_flagged(self):
        assert "MACEFF002" in codes("root = Path(__file__).parent.parent\n")

    def test_three_hops_are_flagged_once_not_three_times(self):
        """Counting SITES, not nodes. Attribute chains nest, so a naive walk
        reports the same expression once per hop and overstates a burn-down."""
        assert codes("root = Path(__file__).parent.parent.parent\n").count("MACEFF002") == 1

    def test_a_single_parent_is_permitted(self):
        """§5 allows accessing a sibling directory; it forbids counting levels."""
        assert "MACEFF002" not in codes("sibling = Path(__file__).parent / 'config'\n")
        assert PARENT_CHAIN_LIMIT == 1


class TestSilentReturn:
    """MACEFF003 -- §3 silent swallowing, in its return-shaped form."""

    def test_handler_returning_bare_none_is_flagged(self):
        assert "MACEFF003" in codes("""
            def f():
                try:
                    return g()
                except OSError:
                    return None
        """)

    def test_handler_returning_implicit_none_is_flagged(self):
        assert "MACEFF003" in codes("""
            def f():
                try:
                    return g()
                except OSError:
                    return
        """)

    def test_a_handler_that_warns_then_returns_is_permitted(self):
        """The documented pattern is warn-then-fall-back. What the rule forbids
        is the SILENCE, not the fallback -- so a handler that says something
        must pass, or the rule would push people to delete the warning."""
        assert "MACEFF003" not in codes("""
            def f():
                try:
                    return g()
                except OSError as e:
                    print(f"warn: {e}", file=sys.stderr)
                    return None
        """)

    def test_a_handler_that_reraises_is_permitted(self):
        assert "MACEFF003" not in codes("""
            def f():
                try:
                    return g()
                except OSError:
                    raise
        """)


class TestPositionalMultiValueReturn:
    """MACEFF004 -- the operator's principle, from ~2 decades of Python."""

    def test_three_positional_values_are_flagged(self):
        assert "MACEFF004" in codes("def f():\n    return a, b, c\n")

    def test_two_values_are_permitted(self):
        """A pair is the idiomatic (value, error) / (key, value) shape and
        reordering it is visible at the call site. The hazard scales with
        width, so the rule starts where the hazard does."""
        assert "MACEFF004" not in codes("def f():\n    return a, b\n")

    def test_a_single_value_is_permitted(self):
        assert "MACEFF004" not in codes("def f():\n    return a\n")


class TestThrowawayUnpacking:
    """MACEFF005 -- `_, _, x = f()` identifies what it keeps by POSITION."""

    def test_throwaway_unpack_of_a_call_is_flagged(self):
        assert "MACEFF005" in codes("_, _, push = book.load_full()\n")

    def test_named_attribute_access_is_permitted(self):
        assert "MACEFF005" not in codes("push = book.load_full().push\n")

    def test_a_narrow_pair_unpack_is_permitted(self):
        assert "MACEFF005" not in codes("_, value = pair()\n")


class TestEventScanRowLimit:
    """A row limit on an event scan buys nothing and costs the honest negative.

    These scans exit on their first match, so the bound is free when the event
    exists and only takes effect when it does not — returning a miss the caller
    reads as a fact about state. Measured consequence: USER_IDLE cleared while
    the operator was away, because 200 of the agent's own events buried their
    last input and `None` was read as "present".
    """

    def test_flags_a_hardcoded_row_limit(self):
        assert "MACEFF006" in codes("for e in read_events(limit=50, reverse=True):\n    pass\n")

    def test_unbounded_is_the_house_style(self):
        assert "MACEFF006" not in codes("for e in read_events(limit=None, reverse=True):\n    pass\n")

    def test_a_caller_supplied_limit_is_explicit_and_allowed(self):
        """`limit=limit` puts the choice at the call site, which is the point."""
        assert "MACEFF006" not in codes("def f(limit):\n    return read_events(limit=limit)\n")

    def test_other_calls_with_a_limit_are_not_our_business(self):
        """Over-matching would flag every paginated API in the tree."""
        assert "MACEFF006" not in codes("rows = fetch_page(limit=50)\n")


class TestSuppressionIsHonoured:
    """A justified exception must be expressible, or the rule gets disabled."""

    def test_a_matching_noqa_suppresses(self):
        assert "MACEFF004" not in codes(
            "def f():\n    return a, b, c  # noqa: MACEFF004 - wire format\n")

    def test_a_noqa_for_a_DIFFERENT_code_does_not_suppress(self):
        """Otherwise one suppression silently covers every rule on that line,
        which is how a targeted exception becomes a blanket one."""
        assert "MACEFF004" in codes(
            "def f():\n    return a, b, c  # noqa: MACEFF001 - unrelated\n")


class TestReportSeparatesUnreadableFromClean:
    def test_a_file_that_does_not_parse_is_not_reported_as_clean(self, tmp_path):
        """"Violates no rule" and "could not be read" demand different
        responses, and collapsing them lets a broken module report green."""
        from macf.style import check_paths
        bad = tmp_path / "broken.py"
        bad.write_text("def f(:\n")
        report = check_paths([bad])
        assert report.findings == []
        assert report.files_checked == 0
        assert len(report.unreadable) == 1
        assert "does not parse" in report.unreadable[0]

    def test_counts_by_code_aggregates(self, tmp_path):
        from macf.style import check_paths
        p = tmp_path / "m.py"
        p.write_text("def f():\n    return a, b, c\n\n\ndef g():\n    return d, e, h\n")
        report = check_paths([p])
        assert report.counts_by_code() == {"MACEFF004": 2}
        assert report.files_checked == 1


class TestFindingIsNamedNotPositional:
    def test_finding_cannot_be_built_positionally(self):
        """The checker enforcing MACEFF004 must not itself be constructible by
        position -- dogfooding, and the same kw_only argument."""
        with pytest.raises(TypeError):
            Finding("MACEFF004", 1, 1, "msg")

    def test_report_cannot_be_built_positionally(self):
        with pytest.raises(TypeError):
            Report([], 0, [])
