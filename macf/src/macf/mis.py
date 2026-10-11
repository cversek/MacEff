"""`macf_tools mis check`: the decidable requirements of the MIS policy.

The policy is `framework/policies/base/meta/mis.md`; its requirements and their
reasons are in MIS-0001. Each check below names the requirement it decides
(R03, R04, ...), and every finding carries that ID with its semantic slug, so a
refusal names its rule in words as well as by number, as MIS-0001-R43 (tool_MUST_report_slug) asks.

Only decidable requirements are checked here. The judgment requirements (who
may accept an MIS, whether a synthesis quotes every position) are reviewed by
people and agents, and this tool does not pretend to decide them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

HEADER_FIELDS = ["Number", "Type", "Status", "Authors", "Secretary", "Deliberation",
                 "Created", "Updates", "Supersedes", "Lands-in", "Resolution"]
SECTIONS = ["Summary", "Motivation", "Goals and Non-Goals", "Guide-Level Explanation", "Terms",
            "Specification", "Rationale and Rejected Alternatives", "Prior Art",
            "Compatibility and Deployment", "Security and Safety", "Conformance", "Landing Plan",
            "Open Questions", "Deliberation Record", "Revision History"]
TYPES = ("Standards", "Process", "Informational")
STATUSES = ("Draft", "Deliberation", "Final-Comment", "Accepted", "Rejected", "Withdrawn",
            "Deferred", "Final", "Superseded")
DECIDED = ("Accepted", "Rejected", "Deferred", "Final", "Superseded")
MAX_WORDS = 30

NAME_RE = re.compile(r"^MIS-(\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
FIELD_RE = re.compile(r"^\*\*([A-Za-z-]+)\*\*: ?(.*)$")
SECTION_RE = re.compile(r"^## (\d+) (.+?)\s*$")
LOOKS_LIKE_REQ = re.compile(r"^- \*\*R\d")
REQ_RE = re.compile(r"^- \*\*R(\d{2,})\*\* \[(MUST NOT|SHOULD NOT|MUST|SHOULD|MAY) · "
                    r"(decidable|judgment): [^\]]+\] (\S.*)$")
UPPER_KEYWORD_RE = re.compile(r"\b(MUST NOT|SHOULD NOT|MUST|SHOULD|MAY|SHALL|REQUIRED|RECOMMENDED|OPTIONAL)\b")
LOWER_KEYWORD_RE = re.compile(r"\b(must|should|shall|may|required)\b")
TERM_RE = re.compile(r"^- \*\*(.+?)\*\*:")
WIKI_RE = re.compile(r"\[\[[^\]]+\]\]")
SLUG_TAIL_RE = re.compile(r"^(.*\S)\s+\(([^()\s]+)\)$")
SLUG_RE = re.compile(r"^[-_A-Za-z0-9]+$")

# The semantic slug of each MIS-0001 requirement this tool decides, so that every finding names
# its rule in words, as MIS-0001-R43 (tool_MUST_report_slug) asks. A test keeps this table equal to the
# slugs written in MIS-0001 itself.
RULE_SLUGS = {
    "R03": "MIS_MUST_be_named_by_number",
    "R04": "MIS_numbers_MUST-NOT_repeat",
    "R06": "MIS_MUST_carry_header_fields",
    "R07": "MIS_MUST_contain_sections",
    "R08": "type_MUST_be_listed",
    "R09": "status_MUST_be_listed",
    "R10": "req_MUST_use_line_form",
    "R11": "req_IDs_MUST-NOT_repeat",
    "R12": "req_MUST_hold_one_keyword",
    "R13": "req_MUST-NOT_use_lowercase_keyword",
    "R14": "req_MUST_have_30_words_max",
    "R17": "rationale_MUST_name_every_req",
    "R18": "conformance_MUST_list_every_req",
    "R19": "MIS_MUST_end_with_wiki-links",
    "R20": "glossary_MUST-NOT_repeat_terms",
    "R21": "terms_MUST_reach_glossary",
    "R23": "secretary_MUST_be_named",
    "R27": "resolution_MUST-NOT_be_empty",
    "R31": "final_lands-in_MUST-NOT_be_empty",
    "R38": "req_MUST_end_with_slug",
    "R39": "item_slugs_MUST-NOT_repeat",
    "R45": "item_MUST_carry_ID_and_slug",
    "R49": "citation_MUST_match_slug",
}
# A citation of a requirement: MIS-0001-R14 (req_MUST_have_30_words_max). Between the ID and
# the slug it may wrap, as docstrings and comments do: a line break, the next line's
# indentation, and a comment marker or quote that carries the text on.
CITATION_RE = re.compile(
    r"\bMIS-(\d{4})-(R\d{2,})(?:[ \t]+|[ \t]*\n[ \t]*(?:(?:#+|//|\*|>)[ \t]*)?)\(([-_A-Za-z0-9]+)\)")
# A requirement line's ID and trailing slug, for resolving citations.
REQ_SLUG_RE = re.compile(r"^- \*\*(R\d{2,})\*\* \[.*\(([-_A-Za-z0-9]+)\)\s*$", re.M)
# Open questions (Qnn), positions (Pnn) and objections (Onn): numbered items with slugs (R45).
ITEM_RE = re.compile(r"^- \*\*([QPO])(\d{2,})\*\* (\S.*)$")


@dataclass(frozen=True, kw_only=True)
class Finding:
    """One failed check: where, which MIS-0001 requirement, and what is wrong."""
    path: str
    line: int
    rule: str
    message: str

    @property
    def slug(self) -> str:
        """The semantic slug of the MIS-0001 requirement this finding enforces."""
        return RULE_SLUGS.get(self.rule, "")

    def __str__(self) -> str:
        if self.rule == UNREADABLE:  # about the file, not a requirement
            return f"{self.path}:{self.line}: {self.message}"
        label = f"{self.rule} ({self.slug})" if self.slug else self.rule
        return f"{self.path}:{self.line}: MIS-0001-{label}: {self.message}"


UNREADABLE = "UTF-8"


def read_utf8(path: Path) -> tuple[Optional[str], Optional[Finding]]:
    """A file's text, or the finding that says it cannot be read as UTF-8.

    Every read names UTF-8, so the checker reads alike in every locale. A file in another
    encoding is reported, not raised: one Latin-1 byte in a copy of the template used to stop
    the whole run with a traceback, so no file after it was checked either.
    """
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8"), None
    except UnicodeDecodeError as e:
        line = raw.count(b"\n", 0, e.start) + 1
        return None, Finding(path=str(path), line=line, rule=UNREADABLE,
                             message=f"not UTF-8 (byte 0x{raw[e.start]:02x}); no check could read this file")


def _absent(value: Optional[str]) -> bool:
    """A header value that says nothing: empty, or 'none' with or without a note."""
    return value is None or not value.strip() or value.strip().lower().startswith("none")


def read_header(lines: list[str]) -> dict:
    """The header fields above the first rule or section, in order: {name: (value, line)}."""
    fields: dict = {}
    for n, line in enumerate(lines, start=1):
        if line.strip() == "---" or line.startswith("## "):
            break
        m = FIELD_RE.match(line)
        if m:
            fields[m.group(1)] = (m.group(2), n)
    return fields


def read_sections(lines: list[str]) -> dict:
    """Numbered sections and Wiki-Links: {"numbered": [{number, title, start, end}], "wiki": (start, end) or None}."""
    marks = []
    for n, line in enumerate(lines, start=1):
        m = SECTION_RE.match(line)
        if m:
            marks.append({"number": int(m.group(1)), "title": m.group(2), "start": n})
        elif line.rstrip() == "## Wiki-Links":
            marks.append({"number": None, "title": "Wiki-Links", "start": n})
    for i, mark in enumerate(marks):
        mark["end"] = marks[i + 1]["start"] - 1 if i + 1 < len(marks) else len(lines)
    wiki = next(((m["start"], m["end"]) for m in marks if m["title"] == "Wiki-Links"), None)
    return {"numbered": [m for m in marks if m["number"] is not None], "wiki": wiki}


def _body(lines: list[str], sections: list[dict], title: str) -> dict:
    """A section's heading line and the lines under it: {"start": n, "lines": [...]}; start 0 if absent."""
    sec = next((s for s in sections if s["title"] == title), None)
    if sec is None:
        return {"start": 0, "lines": []}
    return {"start": sec["start"], "lines": lines[sec["start"]:sec["end"]]}


def read_glossary(path: Path) -> dict:
    """Glossary terms, lowercased, with their line numbers, and any duplicates: {"terms": {...}, "findings": [...]}."""
    terms: dict = {}
    findings = []
    text, unreadable = read_utf8(path)
    if unreadable:  # terms None: the R21 check is skipped, not failed for every term
        return {"terms": None, "findings": [unreadable]}
    for n, line in enumerate(text.splitlines(), start=1):
        m = TERM_RE.match(line)
        if not m:
            if line.startswith("- **"):
                findings.append(Finding(path=str(path), line=n, rule="R20",
                                        message="a bold line that is not a term line '- **term**: definition'; "
                                                "a malformed line escapes the duplicate check"))
            continue
        key = m.group(1).strip().lower()
        if key in terms:
            findings.append(Finding(path=str(path), line=n, rule="R20",
                                    message=f"term '{m.group(1)}' is already defined on line {terms[key]}"))
        else:
            terms[key] = n
    return {"terms": terms, "findings": findings}


def check_file(path: Path, glossary_terms: Optional[dict] = None) -> list[Finding]:
    """Every decidable check that concerns one MIS file."""
    text, unreadable = read_utf8(path)
    if unreadable:
        return [unreadable]
    lines = text.splitlines()
    p = str(path)
    out: list[Finding] = []

    def add(line: int, rule: str, message: str) -> None:
        out.append(Finding(path=p, line=line, rule=rule, message=message))

    header = read_header(lines)
    m = NAME_RE.match(path.name)
    if not m:
        add(1, "R03", "the file name is not MIS-NNNN-slug.md (four digits, lowercase slug)")
    number = header.get("Number", ("", 1))
    if m and number[0].strip() != m.group(1):
        add(number[1], "R03", f"Number '{number[0].strip()}' does not match the file name's {m.group(1)}")

    if list(header) != HEADER_FIELDS:
        missing = [f for f in HEADER_FIELDS if f not in header]
        extra = [f for f in header if f not in HEADER_FIELDS]
        detail = (f"missing {missing}" if missing else "") + (f" unknown {extra}" if extra else "")
        add(1, "R06", f"header fields must be {HEADER_FIELDS} in that order; {detail.strip() or 'order differs'}")

    mtype, mstatus = header.get("Type", ("", 1)), header.get("Status", ("", 1))
    if mtype[0].strip() not in TYPES:
        add(mtype[1], "R08", f"Type '{mtype[0].strip()}' is not one of {list(TYPES)}")
    status = mstatus[0].strip()
    if status not in STATUSES:
        add(mstatus[1], "R09", f"Status '{status}' is not one of {list(STATUSES)}")

    secs = read_sections(lines)
    numbered = secs["numbered"]
    got = [(s["number"], s["title"]) for s in numbered]
    want = list(enumerate(SECTIONS, start=1))
    if got != want:
        missing = [t for _, t in want if t not in [g for _, g in got]]
        add(numbered[0]["start"] if numbered else 1, "R07",
            "sections must be numbered 1 to 15 as in MIS-0000"
            + (f"; missing {missing}" if missing else "; order or numbering differs"))

    spec_part = _body(lines, numbered, "Specification")
    spec_start, spec = spec_part["start"], spec_part["lines"]
    ids: dict = {}
    slugs: dict = {}
    labels: dict = {}
    for offset, line in enumerate(spec, start=1):
        n = spec_start + offset
        if not LOOKS_LIKE_REQ.match(line):
            continue
        rm = REQ_RE.match(line)
        if not rm:
            add(n, "R10", "requirement line is not '- **Rnn** [KEYWORD · decidable|judgment: <check>] <sentence>'")
            continue
        rid, keyword, text = f"R{rm.group(1)}", rm.group(2), rm.group(4)
        sm = SLUG_TAIL_RE.match(text)
        slug = ""
        if sm and SLUG_RE.match(sm.group(2)):
            text, slug = sm.group(1), sm.group(2)
        else:
            add(n, "R38", f"{rid} has no semantic slug at the end of its line: write '(subject_KEYWORD_action)',"
                " with ASCII letters, digits, hyphens and underscores only")
        label = f"{rid} ({slug})" if slug else rid
        if rid in ids:
            add(n, "R11", f"{label}: {rid} is already used on line {ids[rid]}")
            continue
        ids[rid] = n
        labels[rid] = label
        if slug:
            if slug in slugs:
                add(n, "R39", f"{label}: the slug is already used on line {slugs[slug]}")
            else:
                slugs[slug] = n
        found = UPPER_KEYWORD_RE.findall(text)
        if found != [keyword]:
            add(n, "R12", f"{label}: the sentence must contain '{keyword}' once and no other capitalized keyword; found {found}")
        low = LOWER_KEYWORD_RE.findall(text)
        if low:
            add(n, "R13", f"{label}: keyword in lowercase: {sorted(set(low))}")
        words = len(text.split())
        if words > MAX_WORDS:
            add(n, "R14", f"{label}: {words} words; the limit is {MAX_WORDS}")

    # R45: every open question is a Qnn item; positions and objections that are numbered
    # (Pnn, Onn) carry a slug. Their slugs share one namespace with the requirements' (R39).
    items: dict = {}
    for title, kinds, every_bullet in (("Open Questions", "Q", True), ("Deliberation Record", "PO", False)):
        part = _body(lines, numbered, title)
        for offset, line in enumerate(part["lines"], start=1):
            n = part["start"] + offset
            im = ITEM_RE.match(line)
            if not im or im.group(1) not in kinds:
                if every_bullet and line.startswith("- "):
                    add(n, "R45", f"an open question must be '- **Qnn** <question> (semantic_slug)': {line[:60]}")
                elif re.match(r"^- \*\*[PO]\d", line) and not every_bullet:
                    add(n, "R45", f"a numbered position or objection must be '- **Pnn**/**Onn** <text> (semantic_slug)': {line[:60]}")
                continue
            iid = f"{im.group(1)}{im.group(2)}"
            sm = SLUG_TAIL_RE.match(im.group(3))
            if not (sm and SLUG_RE.match(sm.group(2))):
                add(n, "R45", f"{iid} has no semantic slug at the end of its line")
                continue
            slug = sm.group(2)
            if iid in items:
                add(n, "R45", f"{iid} ({slug}): {iid} is already used on line {items[iid]}")
                continue
            items[iid] = n
            if slug in slugs:
                add(n, "R39", f"{iid} ({slug}): the slug is already used on line {slugs[slug]}")
            else:
                slugs[slug] = n

    for title, rule in (("Rationale and Rejected Alternatives", "R17"), ("Conformance", "R18")):
        part = _body(lines, numbered, title)
        start, text = part["start"], "\n".join(part["lines"])
        for rid, n in ids.items():
            if not re.search(rf"\b{rid}\b", text):
                add(start or n, rule, f"{labels.get(rid, rid)} is not named in section '{title}'")

    if secs["wiki"] is None:
        add(len(lines), "R19", "no Wiki-Links section")
    else:
        ws, we = secs["wiki"]
        if len(WIKI_RE.findall("\n".join(lines[ws:we]))) < 2:
            add(ws, "R19", "Wiki-Links must name at least two concepts")

    if status in ("Accepted", "Final") and glossary_terms is not None:
        part = _body(lines, numbered, "Terms")
        start = part["start"]
        for offset, line in enumerate(part["lines"], start=1):
            tm = TERM_RE.match(line)
            if tm and tm.group(1).strip().lower() not in glossary_terms:
                add(start + offset, "R21", f"term '{tm.group(1)}' is not in the glossary, and this MIS is {status}")

    sec_field = header.get("Secretary", ("", 1))
    if status != "Draft" and _absent(sec_field[0]):
        add(sec_field[1], "R23", f"Status is {status}, so the Secretary must be named")
    res = header.get("Resolution", ("", 1))
    if status in DECIDED and _absent(res[0]):
        add(res[1], "R27", f"Status is {status}, so the Resolution must record the decision")
    lands = header.get("Lands-in", ("", 1))
    if status == "Final" and _absent(lands[0]):
        add(lands[1], "R31", "Status is Final, so Lands-in must say where the MIS landed")
    return out


def mis_files(paths: Iterable[Path]) -> list[Path]:
    """The MIS files named directly, or found as MIS-*.md in the directories named."""
    found = []
    for p in paths:
        found.extend(sorted(p.glob("MIS-*.md")) if p.is_dir() else [p])
    return found


def check(paths: Iterable[Path], glossary: Optional[Path] = None) -> list[Finding]:
    """Check MIS files and the glossary: per-file checks, unique numbers (R04), glossary duplicates (R20)."""
    files = mis_files(paths)
    out: list[Finding] = []
    terms = None
    if glossary is not None:
        g = read_glossary(glossary)
        out.extend(g["findings"])
        terms = g["terms"]
    seen: dict = {}
    for f in files:
        out.extend(check_file(f, terms))
        text, unreadable = read_utf8(f)
        if unreadable:  # check_file reported it
            continue
        num = read_header(text.splitlines()).get("Number", ("", 1))[0].strip()
        if num and num in seen:
            out.append(Finding(path=str(f), line=1, rule="R04", message=f"number {num} is also used by {seen[num]}"))
        elif num:
            seen[num] = f.name
    out.extend(check_citations(files, glossary))
    return out


def check_citations(files: list, glossary: Optional[Path] = None) -> list:
    """R49: each `MIS-NNNN-Rnn (slug)` in framework text names a requirement and slug that exist.

    Every MIS beside the files checked defines what can be cited, so a check of one file also
    resolves its citations of other MIS, and a citation of an MIS that does not exist is a
    finding. The texts searched are the files checked, the glossary, every policy under
    framework/policies beside the MIS directory, and, in a checkout of this repository, the
    package's code, tests and developer documents, whose docstrings and comments cite
    requirements too. Outside the files checked, a run that names only some MIS checks only
    citations of those, so a check of one file reports nothing about the others. A citation
    is found when it wraps between its ID and its slug.
    """
    tree = sorted({s for f in files for s in f.parent.glob("MIS-*.md")} | set(files))
    defined: dict = {}  # number -> {requirement ID: slug}, or None when the file is unreadable
    named: set = set()
    for f in tree:
        text, unreadable = read_utf8(f)
        if unreadable:  # reported by check_file when named; its citations cannot be resolved
            m = re.match(r"MIS-(\d+)-", f.name)
            num, reqs = (m.group(1) if m else ""), None
        else:
            num = read_header(text.splitlines()).get("Number", ("", 1))[0].strip()
            reqs = dict(REQ_SLUG_RE.findall(text))
        if num:
            defined[num] = reqs
            if f in files:
                named.add(num)
    whole_tree = set(files) >= set(tree)
    reported = set(files) | ({glossary} if glossary else set())
    texts = list(files) + ([glossary] if glossary else [])
    for f in files[:1]:
        framework = f.parent.parent  # noqa: MACEFF002 - MIS-0001-R03 fixes framework/mis beside framework/policies
        pol = framework / "policies"
        if pol.is_dir():
            texts.extend(sorted(pol.rglob("*.md")))
        texts.extend(package_texts(framework.parent))
    out = []
    for path in texts:
        text, unreadable = read_utf8(path)
        if unreadable:
            if path not in reported:  # a policy or the package's text: only this check reads it
                out.append(unreadable)
            continue
        own = path in files
        for m in CITATION_RE.finditer(text):
            num, rid, slug = m.groups()
            n = text.count("\n", 0, m.start()) + 1
            if not (own or whole_tree or num in named):
                continue
            if num not in defined:
                out.append(Finding(path=str(path), line=n, rule="R49",
                                   message=f"cites MIS-{num}-{rid} ({slug}), but there is no MIS-{num}"))
                continue
            if defined[num] is None:
                continue
            want = defined[num].get(rid)
            if want is None:
                out.append(Finding(path=str(path), line=n, rule="R49",
                                   message=f"cites MIS-{num}-{rid} ({slug}), but MIS-{num} has no {rid}"))
            elif want != slug:
                out.append(Finding(path=str(path), line=n, rule="R49",
                                   message=f"cites MIS-{num}-{rid} ({slug}); MIS-{num} names it ({want})"))
    return out


# In a checkout of this repository, the package's own texts that cite requirements: code and
# tests in their docstrings and comments, and the developer documents.
PACKAGE_TEXTS = (("macf/src", "*.py"), ("macf/tests", "*.py"), ("macf/docs", "*.md"))


def package_texts(root: Path) -> list:
    """The package's code, tests and developer documents under ``root``, when it is a checkout.

    A deployment's framework tree has no package beside it, so nothing is added there."""
    return [p for sub, pattern in PACKAGE_TEXTS if (root / sub).is_dir()
            for p in sorted((root / sub).rglob(pattern))]


def default_glossary(paths: list[Path]) -> Optional[Path]:
    """framework/glossary.md beside the first framework/mis directory named, if it exists."""
    for p in paths:
        d = p if p.is_dir() else p.parent
        candidate = d.parent / "glossary.md"
        if candidate.is_file():
            return candidate
    return None
