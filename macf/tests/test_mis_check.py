"""`macf_tools mis check`: the decidable requirements of the mis policy (MIS-0001).

The repository's own MIS files and glossary must pass. Then, for each decidable
check, one defect is planted in a copy of the real MIS-0001, and the check must
name that requirement. Fixtures are the real files, not text composed to suit
the checker.
"""
import re
from pathlib import Path

import pytest

from macf import mis

REPO = Path(__file__).resolve().parents[2]
MIS_DIR = REPO / "framework" / "mis"
GLOSSARY = REPO / "framework" / "glossary.md"
MIS1 = MIS_DIR / "MIS-0001-maceff-improvement-specifications.md"


def test_repo_mis_files_pass():
    """MIS-0000 R01: every MIS file in the repository, and the glossary, pass."""
    findings = mis.check([MIS_DIR], GLOSSARY)
    assert findings == [], "\n".join(str(f) for f in findings)
    assert len(mis.mis_files([MIS_DIR])) >= 2


def _mis_tree(d, skip=()):
    """Copy the repository's MIS files into d.

    MIS-0001 cites other MIS, and a check resolves each citation against the MIS beside the
    file, so a copy of MIS-0001 alone would report its own citations as citations of MIS that
    do not exist.
    """
    for f in MIS_DIR.glob("MIS-*.md"):
        if f not in skip:
            (d / f.name).write_bytes(f.read_bytes())


@pytest.fixture
def plant(tmp_path):
    """Copy MIS-0001, the MIS beside it and the glossary into a temporary framework tree, apply one edit, and check."""
    def run(edit=None, name=MIS1.name, glossary_edit=None, extra=None):
        d = tmp_path / "framework" / "mis"
        d.mkdir(parents=True, exist_ok=True)
        _mis_tree(d, skip={MIS1})
        text = MIS1.read_text(encoding="utf-8")
        if edit:
            text = edit(text)
        (d / name).write_text(text, encoding="utf-8")
        g = tmp_path / "framework" / "glossary.md"
        gtext = GLOSSARY.read_text(encoding="utf-8")
        g.write_text(glossary_edit(gtext) if glossary_edit else gtext, encoding="utf-8")
        if extra:
            extra(d)
        return {f.rule for f in mis.check([d], g)}
    return run


def sub(old, new):
    def edit(text):
        assert old in text, old
        return text.replace(old, new, 1)
    return edit


def field(name, value):
    """Set a header field, whatever MIS-0001 currently holds there (its Status moves as it is decided)."""
    def edit(text):
        pattern = rf"^\*\*{name}\*\*: .*$"
        assert re.search(pattern, text, flags=re.M), name
        return re.sub(pattern, lambda _: f"**{name}**: {value}", text, count=1, flags=re.M)
    return edit


def test_the_unedited_copy_passes(plant):
    assert plant() == set()


def test_r03_file_name(plant):
    assert "R03" in plant(name="MIS-1-bad.md")


def test_r03_number_matches_name(plant):
    assert "R03" in plant(sub("**Number**: 0001", "**Number**: 0002"))


def test_r04_two_files_one_number(plant):
    def twin(d):
        (d / "MIS-0001-another.md").write_text((d / MIS1.name).read_text(encoding="utf-8"), encoding="utf-8")
    assert "R04" in plant(extra=twin)


def test_r06_header_field_missing(plant):
    assert "R06" in plant(sub("**Supersedes**: none\n", ""))


def test_r07_section_missing(plant):
    assert "R07" in plant(sub("## 8 Prior Art", "## 8 Earlier Work"))


def test_r08_type(plant):
    assert "R08" in plant(sub("**Type**: Process", "**Type**: Feature"))


def test_r09_status(plant):
    assert "R09" in plant(field("Status", "Approved"))


def test_r10_requirement_form(plant):
    assert "R10" in plant(sub("- **R02** [MAY · judgment: the author]", "- **R02** [MAY] (judgment)"))


def test_r11_duplicate_id(plant):
    assert "R11" in plant(sub("- **R02** [MAY", "- **R01** [MAY"))


def test_r12_two_keywords(plant):
    assert "R12" in plant(sub("An author MAY write an MIS for any other change.",
                              "An author MAY write an MIS, and SHOULD for any other change."))


def test_r12_keyword_does_not_match_tag(plant):
    assert "R12" in plant(sub("An author MAY write an MIS for any other change.",
                              "An author MUST write an MIS for any other change."))


def test_r13_lowercase_keyword(plant):
    assert "R13" in plant(sub("An author MAY write an MIS for any other change.",
                              "An author MAY write an MIS, which must be short, for any other change."))


def test_r14_too_long(plant):
    long = "An author MAY write an MIS for any other change " + "and then " * 12 + "rest."
    assert "R14" in plant(sub("An author MAY write an MIS for any other change.", long))


def test_r17_requirement_without_rationale(plant):
    def drop(text):
        head, sep, rest = text.partition("## 7 Rationale and Rejected Alternatives")
        body, sep2, tail = rest.partition("## 8 Prior Art")
        return head + sep + re.sub(r"\bR02\b", "R0X", body) + sep2 + tail
    assert "R17" in plant(drop)


def test_r18_requirement_without_conformance(plant):
    assert "R18" in plant(sub("| R02 | judgment | the author | standing |\n", ""))


def test_r19_too_few_links(plant):
    assert "R19" in plant(sub("[[methodology]] [[policy_as_api]] [[collaboration]]", "[[methodology]]"))


def test_r20_glossary_duplicate(plant):
    dup = "- **operator**: someone else entirely.\n"
    assert "R20" in plant(glossary_edit=lambda g: g + dup)


def test_r21_accepted_term_missing_from_glossary(plant):
    edit = lambda t: field("Status", "Accepted")(
        field("Resolution", "accepted")(
            sub("## 5 Terms\n", "## 5 Terms\n\n- **unlisted word**: a term no glossary defines.\n")(t)))
    assert "R21" in plant(edit)


def test_r21_draft_may_carry_new_terms(plant):
    edit = lambda t: field("Status", "Draft")(
        sub("## 5 Terms\n", "## 5 Terms\n\n- **unlisted word**: a term no glossary defines.\n")(t))
    assert "R21" not in plant(edit)


def test_r23_secretary_after_draft(plant):
    assert "R23" in plant(sub("**Secretary**: the Secretary of deliberation #493", "**Secretary**: none"))


def test_r27_decided_without_resolution(plant):
    assert "R27" in plant(lambda t: field("Status", "Accepted")(field("Resolution", "none")(t)))


def test_r31_final_without_lands_in(plant):
    assert "R31" in plant(lambda t: field("Status", "Final")(field("Lands-in", "none")(t)))


def test_findings_name_their_rule_and_line(plant, tmp_path):
    plant(sub("**Type**: Process", "**Type**: Feature"))
    f = next(x for x in mis.check([tmp_path / "framework" / "mis"]) if x.rule == "R08")
    assert f.line == 4 and "Feature" in str(f) and str(f).startswith(str(tmp_path))


def test_r38_requirement_without_slug(plant):
    assert "R38" in plant(sub("for any other change. (author_MAY_write_MIS_for_any_change)",
                              "for any other change."))


def test_r38_slug_with_forbidden_characters(plant):
    assert "R38" in plant(sub("(author_MAY_write_MIS_for_any_change)",
                              "(author MAY write MIS)"))
    assert "R38" in plant(sub("(author_MAY_write_MIS_for_any_change)",
                              "(author_MAY_écrire)"))


def test_r39_duplicate_slug(plant):
    assert "R39" in plant(sub("(author_MAY_write_MIS_for_any_change)", "(PR_MUST_cite_accepted_MIS)"))


def test_findings_name_their_slugs(plant, tmp_path):
    """MIS-0001 R43: a finding names its own rule's slug, and the requirement's slug it concerns."""
    long = "An author MAY write an MIS for any other change " + "and then " * 12 + "rest."
    plant(sub("An author MAY write an MIS for any other change.", long))
    f = next(x for x in mis.check([tmp_path / "framework" / "mis"]) if x.rule == "R14")
    text = str(f)
    assert "MIS-0001-R14 (req_MUST_have_30_words_max)" in text
    assert "R02 (author_MAY_write_MIS_for_any_change)" in text


def test_rule_slugs_match_mis_0001():
    """The checker's slug table is the one written in MIS-0001, so the two cannot drift apart."""
    written = dict(re.findall(r"^- \*\*(R\d+)\*\* \[.*\((\S+)\)$", MIS1.read_text(encoding="utf-8"), flags=re.M))
    for rule, slug in mis.RULE_SLUGS.items():
        assert written.get(rule) == slug, (rule, slug, written.get(rule))


def test_r45_open_question_without_id(plant):
    assert "R45" in plant(sub("- **Q01** Should", "- Should"))


def test_r45_open_question_without_slug(plant):
    assert "R45" in plant(sub(" (lint_policies_too)", ""))


def test_r45_position_without_slug(plant):
    assert "R45" in plant(sub(" (operator_proposed_80pct_STE)", ""))


def test_r39_slug_shared_by_a_question_and_a_requirement(plant):
    assert "R39" in plant(sub("(lint_policies_too)", "(PR_MUST_cite_accepted_MIS)"))


def test_r20_malformed_glossary_line_is_reported(plant):
    """A second definition with a space before the colon must not slip past the duplicate check."""
    assert "R20" in plant(glossary_edit=lambda g: g.replace("## Retired", "- **accepted** : another meaning.\n\n## Retired"))


def _with_policy(text):
    def extra(d):
        pol = d.parent / "policies" / "base" / "meta"
        pol.mkdir(parents=True, exist_ok=True)
        (pol / "example.md").write_text(text, encoding="utf-8")
    return extra


def _cite(rid, slug, num="0001", between=" "):
    """A citation built when the test runs. The check reads this file too, and the citations
    these tests need are wrong on purpose, so the file's own text must not cite them."""
    return f"MIS-{num}-{rid}{between}({slug})"


def test_r49_citation_with_a_stale_slug(plant):
    assert "R49" in plant(extra=_with_policy(f"A rule ({_cite('R14', 'req_MUST_be_short')}).\n"))


def test_r49_citation_of_a_missing_requirement(plant):
    assert "R49" in plant(extra=_with_policy(f"A rule ({_cite('R99', 'no_such_req')}).\n"))


def test_r49_a_correct_citation_passes(plant):
    assert "R49" not in plant(extra=_with_policy("A rule [MIS-0001-R14 (req_MUST_have_30_words_max)].\n"))


def _beside_mis1(tmp_path, name, text, policy=None):
    """The repository's MIS files with one file written among them, the glossary, and optionally a policy."""
    d = _framework(tmp_path)
    (d / name).write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
    if policy:
        _with_policy(policy)(d)
    return d, GLOSSARY


TEMPLATE = (MIS_DIR / "MIS-0000-template.md").read_text(encoding="utf-8")


def test_r49_one_file_checked_alone_has_its_citations_of_other_mis_resolved(tmp_path):
    # The template tells an author to check their own file. That run defined only the file's
    # own requirements, so a citation of another MIS was never resolved.
    d, g = _beside_mis1(tmp_path, "MIS-0000-template.md",
                        TEMPLATE + f"\nSee {_cite('R14', 'req_MUST_be_short')}.\n")
    messages = [f.message for f in mis.check([d / "MIS-0000-template.md"], g) if f.rule == "R49"]
    # Resolved, not merely unknown: the finding names the slug MIS-0001 gives R14.
    assert messages == [f"cites {_cite('R14', 'req_MUST_be_short')}; MIS-0001 names it (req_MUST_have_30_words_max)"]


def test_r49_a_citation_of_an_mis_that_does_not_exist(plant):
    assert "R49" in plant(extra=_with_policy(f"A rule ({_cite('R01', 'no_such_mis', num='0099')}).\n"))


def test_one_file_checked_alone_reports_nothing_about_the_others(tmp_path):
    # A stale citation of MIS-0001 in a policy is MIS-0001's business: a check of the template
    # alone does not report it, and a check of the directory does.
    d, g = _beside_mis1(tmp_path, "MIS-0000-template.md", TEMPLATE,
                        policy=f"A rule ({_cite('R14', 'req_MUST_be_short')}).\n")
    assert "R49" not in {f.rule for f in mis.check([d / "MIS-0000-template.md"], g)}
    assert "R49" in {f.rule for f in mis.check([d], g)}


def test_r49_a_citation_that_wraps_is_still_found(plant):
    # Wrapped prose and docstrings break a citation between its ID and its slug. Read one
    # line at a time, the citation was never seen.
    wrapped = _cite("R14", "req_MUST_be_short", between="\n    ")
    assert "R49" in plant(extra=_with_policy(f"A rule ({wrapped}).\n"))


def test_r49_citations_in_the_packages_code_are_checked(tmp_path):
    """In a checkout, code cites requirements in docstrings and comments, and a stale slug
    there is found as it is in a policy, here wrapped across a comment's two lines."""
    d = _framework(tmp_path)
    src = tmp_path / "macf" / "src" / "macf"
    src.mkdir(parents=True)
    wrapped = _cite("R14", "req_MUST_be_short", between="\n# ")
    (src / "example.py").write_text(f"x = 1\n# A rule, cited as {wrapped}.\n", encoding="utf-8")
    found = [f for f in mis.check([d], GLOSSARY) if f.rule == "R49"]
    assert [(Path(f.path).name, f.line) for f in found] == [("example.py", 2)]


def test_a_citation_of_an_unreadable_mis_is_not_called_missing(tmp_path):
    # The unreadable file is reported when it is checked; a citation of it cannot be resolved,
    # and must not be reported as a citation of an MIS that does not exist.
    d, g = _beside_mis1(tmp_path, "MIS-0000-template.md", "café\n".encode("latin-1"))
    cited = d / "MIS-0002-cites.md"
    cited.write_text(MIS1.read_text(encoding="utf-8")
                     + "\nSee MIS-0000-R01 (MIS_MUST_pass_check).\n", encoding="utf-8")
    messages = [f.message for f in mis.check_citations([cited], g)]
    assert not any("there is no MIS-0000" in m for m in messages), messages


def test_reads_are_utf8_whatever_the_locale():
    """The tag's middle dot decodes wrongly under a Latin-1 locale unless every read is UTF-8.

    Every read goes through read_utf8, which decodes the bytes as UTF-8 itself, so no read can
    fall back to the locale's encoding."""
    src = Path(mis.__file__).read_text(encoding="utf-8")
    assert "read_text(" not in src
    assert 'raw.decode("utf-8")' in src


def test_mis_files_are_a_knowledge_web_root(tmp_path, monkeypatch):
    from macf import knowledge_web
    from macf.utils import manifest
    pol = tmp_path / "framework" / "policies"
    (tmp_path / "framework" / "mis").mkdir(parents=True)
    pol.mkdir(parents=True)
    monkeypatch.setattr(manifest, "get_framework_policies_path", lambda: pol)
    roots = knowledge_web._type_roots(tmp_path / "home")
    assert ("mis", tmp_path / "framework" / "mis") in roots


# ---- files that are not UTF-8 ---------------------------------------------------------------


def _with_latin1_line(src: Path, dst: Path) -> int:
    """Copy src to dst with one Latin-1 line appended; return the line holding the bad byte."""
    raw = src.read_bytes()
    dst.write_bytes(raw + "a café line\n".encode("latin-1"))
    return raw.count(b"\n") + 1


def _framework(tmp_path):
    d = tmp_path / "framework" / "mis"
    d.mkdir(parents=True)
    _mis_tree(d)
    return d


def test_a_file_that_is_not_utf8_is_a_finding_not_a_traceback(tmp_path):
    # One Latin-1 byte in a copy of the template used to stop the run with a traceback,
    # so no other file was checked. Now it is one finding, and the other file is still checked.
    d = _framework(tmp_path)
    template = MIS_DIR / "MIS-0000-template.md"
    line = _with_latin1_line(template, d / template.name)
    findings = mis.check([d], GLOSSARY)
    assert [(f.rule, Path(f.path).name, f.line) for f in findings] == [
        (mis.UNREADABLE, template.name, line)]
    assert str(findings[0]).endswith("not UTF-8 (byte 0xe9); no check could read this file")


def test_a_glossary_that_is_not_utf8_is_one_finding_and_skips_the_term_check(tmp_path):
    # MIS-0001 is Accepted, so R21 checks its Terms against the glossary. An unreadable glossary
    # must not turn into one R21 finding per term.
    d = _framework(tmp_path)
    g = tmp_path / "framework" / "glossary.md"
    line = _with_latin1_line(GLOSSARY, g)
    findings = mis.check([d], g)
    assert [(f.rule, Path(f.path).name, f.line) for f in findings] == [
        (mis.UNREADABLE, "glossary.md", line)]


def test_a_policy_that_is_not_utf8_is_reported_by_the_citation_check(tmp_path):
    # Only the citation check reads policies, so it reports an unreadable one, once.
    d = _framework(tmp_path)
    pol = tmp_path / "framework" / "policies"
    pol.mkdir()
    (pol / "bad.md").write_bytes("café\n".encode("latin-1"))
    findings = mis.check([d], GLOSSARY)
    assert [(f.rule, Path(f.path).name) for f in findings] == [(mis.UNREADABLE, "bad.md")]
