#!/usr/bin/env python3
"""Run the MacEff style rules and hold the line with a RATCHET.

WHY A RATCHET RATHER THAN A ZERO-COUNT GATE. The ruff gate blocks only rules
already at zero, which makes them pure ratchets -- they can fire on nothing but a
new introduction. The rules here have real backlogs (111 findings at the time of
writing), so that trick is unavailable: blocking outright would wall off the
codebase, and blocking on nothing would make the checker advice.

So the committed baseline records the count PER RULE, and a commit is refused
when any count goes UP. The debt is visible, cannot grow, and shrinks whenever
someone touches a site -- which is the same direction of travel the ruff gate
has, reached by a different mechanism because the starting condition differs.

WHAT THIS RATCHET DOES NOT CATCH, stated so nobody assumes otherwise: counts are
repo-wide, so removing one violation and adding another elsewhere nets to zero
and passes. That is a real hole. It is accepted because the alternative --
attributing findings to changed lines -- is substantially more machinery for a
gate whose job is to stop the debt GROWING, and a swap does not grow it.

Usage:
    tools/style_check.py              # check against the baseline
    tools/style_check.py --report     # print every finding, exit 0
    tools/style_check.py --baseline   # rewrite the baseline (only ever tighten)
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "tools" / "style_baseline.json"
TARGETS = ["macf/src", "macf/tests", "docker"]


def _load_checker():
    """Import the checker, preferring the repo copy over an installed one.

    A gate must check THIS tree, not whatever version happens to be installed --
    the two can disagree, and the disagreement would be silent.
    """
    sys.path.insert(0, str(REPO / "macf" / "src"))
    from macf.style import check_paths  # noqa: PLC0415 - path set above
    return check_paths


def main() -> int:
    check_paths = _load_checker()
    report = check_paths([REPO / t for t in TARGETS])

    if report.unreadable:
        # REFUSE rather than continue: a file that could not be read is not a
        # file that is clean, and a count taken over a partial tree is a number
        # that means nothing.
        print("style: refusing to compare -- some files could not be read:")
        for u in report.unreadable:
            print(f"  {u}")
        return 2

    counts = report.counts_by_code()

    if "--report" in sys.argv:
        for f in sorted(report.findings, key=lambda x: (str(x.path), x.line)):
            print(f.render())
        print(f"\n{len(report.findings)} finding(s) across {report.files_checked} files")
        return 0

    if "--baseline" in sys.argv:
        BASELINE.write_text(json.dumps(counts, indent=2, sort_keys=True) + "\n")
        print(f"style: baseline written -- {sum(counts.values())} finding(s)")
        return 0

    if not BASELINE.exists():
        print(f"style: no baseline at {BASELINE}; run tools/style_check.py --baseline")
        return 1

    base = json.loads(BASELINE.read_text())
    regressions, improvements = [], []
    for code in sorted(set(base) | set(counts)):
        was, now = base.get(code, 0), counts.get(code, 0)
        if now > was:
            regressions.append((code, was, now))
        elif now < was:
            improvements.append((code, was, now))

    for code, was, now in improvements:
        print(f"style: {code} {was} -> {now}  (improved)")
    if improvements and not regressions:
        print("style: baseline can be tightened -- tools/style_check.py --baseline")

    if regressions:
        print("\nstyle: commit BLOCKED -- these counts went UP:")
        for code, was, now in regressions:
            print(f"  {code}  {was} -> {now}")
        print("\nThe backlog may shrink and must not grow. See the finding with:")
        print("  tools/style_check.py --report | grep <CODE>")
        print("If the new site is genuinely justified, suppress it AT THE SITE")
        print("with '# noqa: <CODE> - <reason>' so the exception is auditable.")
        return 1

    print(f"style: {sum(counts.values())} known finding(s), none new")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
