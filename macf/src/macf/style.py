"""MacEff style rules that ruff structurally cannot express.

WHY THIS EXISTS RATHER THAN A RUFF CONFIG. Ruff has no plugin API, so several
principles the coding standards DOCUMENT have no rule available. The tempting
move is to reach for the nearest built-in and call the principle covered --
which is exactly what PLC0415 would have been for the import rule: the documented
hazard is an import inside an EXCEPT handler (27 instances here), while that rule
flags every non-top-level import (684), and the standards explicitly PERMIT a
justified deferred import. The rule the linter offers is not the rule the policy
states, and adopting it would have manufactured ~657 false positives against our
own standard.

WHAT THIS DOES NOT AND CANNOT COVER. Only the SYNTACTIC principles are here. The
semantic ones -- that a component is pointed at the wrong subject, that a stale
record misleads worse than a missing one, that a control has no invocation path
-- are not decidable from an AST at all. They stay at the tier where a human must
recall them, and should be labelled as such wherever they are written down rather
than being quietly implied to be covered.

MESSAGES SAY WHAT TO DO INSTEAD. A finding that only names the offence leaves the
reader to guess at the remedy, and the guess is where the next defect comes from.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

#: Consecutive `.parent` hops tolerated. One is accessing a sibling directory and
#: is explicitly allowed by the standards; two or more hardcodes a directory
#: depth, which is what breaks silently when a file moves.
PARENT_CHAIN_LIMIT = 1

_NOQA_RE = re.compile(r"#\s*noqa\b(?::\s*(?P<codes>[A-Za-z0-9,\s]+))?")


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One rule violation, addressed by name rather than by tuple position.

    kw_only for the same reason the amail parse result is: enforcing names on
    access while allowing positional construction leaves the hole open at the one
    place a mistake can be introduced.
    """

    code: str
    line: int
    col: int
    message: str
    path: Optional[Path] = None

    def render(self) -> str:
        where = f"{self.path}:{self.line}:{self.col}" if self.path else f"{self.line}:{self.col}"
        return f"{where}: {self.code} {self.message}"


@dataclass(frozen=True, kw_only=True)
class Report:
    """The result of checking a set of files.

    `unreadable` is carried SEPARATELY from `findings` rather than folded in as a
    finding, because "this file violates a rule" and "this file could not be read"
    demand different responses from the caller -- and a checker that reports a
    parse failure as a clean result is the silent-failure shape this whole
    ruleset exists to prevent.
    """

    findings: List[Finding]
    files_checked: int
    unreadable: List[str]

    def counts_by_code(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for f in self.findings:
            out[f.code] = out.get(f.code, 0) + 1
        return out


def _suppressed(code: str, line: int, source_lines: Sequence[str]) -> bool:
    """True when the reported line carries a `# noqa` covering this code.

    A BARE `# noqa` counts, matching the surrounding convention -- but the
    codebase style is `# noqa: CODE - reason`, and a suppression without a stated
    reason is a decision nobody can audit later.
    """
    if not (1 <= line <= len(source_lines)):
        return False
    m = _NOQA_RE.search(source_lines[line - 1])
    if not m:
        return False
    codes = m.group("codes")
    if not codes:
        return True
    return code in {c.strip() for c in codes.split(",") if c.strip()}


def _parent_chain_length(node: ast.AST) -> int:
    n = 0
    while isinstance(node, ast.Attribute) and node.attr == "parent":
        n += 1
        node = node.value
    return n


def check_source(source: str, *, path: Optional[Path] = None) -> List[Finding]:
    """Every MacEff style finding in one module's source.

    Raises SyntaxError to the caller rather than swallowing it: a file that does
    not parse is not a file that is clean, and collapsing the two would let a
    broken module report green.
    """
    tree = ast.parse(source, filename=str(path) if path else "<source>")
    lines = source.splitlines()
    found: List[Finding] = []

    def add(code: str, node: ast.AST, message: str) -> None:
        line = getattr(node, "lineno", 0)
        if _suppressed(code, line, lines):
            return
        found.append(Finding(code=code, line=line,
                             col=getattr(node, "col_offset", 0) + 1,
                             message=message, path=path))

    # Attribute chains are visited nested, so record only the OUTERMOST hop of a
    # chain -- otherwise `a.parent.parent.parent` reports three times and the
    # count overstates the number of SITES, which is what a burn-down tracks.
    chain_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "parent":
            inner = node.value
            if isinstance(inner, ast.Attribute) and inner.attr == "parent":
                chain_roots.add(id(inner))

    for node in ast.walk(tree):
        # ---- MACEFF001: an import inside an except handler --------------------
        if isinstance(node, ast.ExceptHandler):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    add("MACEFF001", sub,
                        "import inside an `except` handler. Python binds scope at "
                        "compile time, so any earlier reference to this name in the "
                        "same scope makes it an UnboundLocalError -- and only when "
                        "the handler runs, which is the path least often exercised. "
                        "Move the import to module level.")

        # ---- MACEFF002: parent-chain navigation -------------------------------
        if isinstance(node, ast.Attribute) and node.attr == "parent" and id(node) not in chain_roots:
            hops = _parent_chain_length(node)
            if hops > PARENT_CHAIN_LIMIT:
                add("MACEFF002", node,
                    f"{hops} chained `.parent` hops hardcode a directory depth and "
                    f"break silently when a file moves. Use dynamic discovery "
                    f"(find_project_root and friends) instead of counting levels.")

        # ---- MACEFF003: a handler whose entire body is `return None` ----------
        if isinstance(node, ast.ExceptHandler) and len(node.body) == 1:
            stmt = node.body[0]
            is_bare_return = isinstance(stmt, ast.Return) and (
                stmt.value is None
                or (isinstance(stmt.value, ast.Constant) and stmt.value.value is None))
            if is_bare_return:
                add("MACEFF003", stmt,
                    "silent return: the handler swallows the error and returns None, "
                    "so the caller cannot distinguish failure from a legitimate "
                    "None. Warn to stderr and re-raise, or return a value that "
                    "states the failure.")

        # ---- MACEFF004: a bare positional multi-value return ------------------
        if isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple):
            width = len(node.value.elts)
            if width >= 3:
                add("MACEFF004", node,
                    f"returns {width} values positionally, coupling every caller to "
                    f"this function's arity AND order. Adding a field breaks each "
                    f"unpacking site loudly; REORDERING two same-typed fields breaks "
                    f"nothing visibly and silently swaps their meaning. Return a "
                    f"dataclass (frozen, kw_only) or a dict.")

        # ---- MACEFF005: throwaway `_` unpacking of a call ---------------------
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, (ast.Tuple, ast.List)) and isinstance(node.value, ast.Call):
                names = [e.id for e in target.elts if isinstance(e, ast.Name)]
                if "_" in names and len(target.elts) >= 3:
                    add("MACEFF005", node,
                        "discards fields by position with `_`. The discarded slots "
                        "are identified only by where they sit, so a change to the "
                        "callee's order silently rebinds the ones you kept. Have the "
                        "callee return a named record and read the fields you want.")

    return found


def check_paths(paths: Iterable[Path]) -> Report:
    """Check .py files, following directories.

    Unreadable files are REPORTED, never skipped -- see Report.unreadable.
    """
    findings: List[Finding] = []
    unreadable: List[str] = []
    checked = 0
    for p in paths:
        candidates = sorted(p.rglob("*.py")) if p.is_dir() else [p]
        for f in candidates:
            if "__pycache__" in f.parts:
                continue
            try:
                source = f.read_text(encoding="utf-8")
            except OSError as e:
                unreadable.append(f"{f}: unreadable ({e})")
                continue
            try:
                findings.extend(check_source(source, path=f))
            except SyntaxError as e:
                unreadable.append(f"{f}: does not parse ({e})")
                continue
            checked += 1
    return Report(findings=findings, files_checked=checked, unreadable=unreadable)
