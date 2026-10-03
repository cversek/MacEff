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


@pytest.fixture
def plant(tmp_path):
    """Copy MIS-0001 and the glossary into a temporary framework tree, apply one edit, and check."""
    def run(edit=None, name=MIS1.name, glossary_edit=None, extra=None):
        d = tmp_path / "framework" / "mis"
        d.mkdir(parents=True, exist_ok=True)
        text = MIS1.read_text()
        if edit:
            text = edit(text)
        (d / name).write_text(text)
        g = tmp_path / "framework" / "glossary.md"
        gtext = GLOSSARY.read_text()
        g.write_text(glossary_edit(gtext) if glossary_edit else gtext)
        if extra:
            extra(d)
        return {f.rule for f in mis.check([d], g)}
    return run


def sub(old, new):
    def edit(text):
        assert old in text, old
        return text.replace(old, new, 1)
    return edit


def test_the_unedited_copy_passes(plant):
    assert plant() == set()


def test_r03_file_name(plant):
    assert "R03" in plant(name="MIS-1-bad.md")


def test_r03_number_matches_name(plant):
    assert "R03" in plant(sub("**Number**: 0001", "**Number**: 0002"))


def test_r04_two_files_one_number(plant):
    def twin(d):
        (d / "MIS-0001-another.md").write_text((d / MIS1.name).read_text())
    assert "R04" in plant(extra=twin)


def test_r06_header_field_missing(plant):
    assert "R06" in plant(sub("**Supersedes**: none\n", ""))


def test_r07_section_missing(plant):
    assert "R07" in plant(sub("## 8 Prior Art", "## 8 Earlier Work"))


def test_r08_type(plant):
    assert "R08" in plant(sub("**Type**: Process", "**Type**: Feature"))


def test_r09_status(plant):
    assert "R09" in plant(sub("**Status**: Accepted", "**Status**: Approved"))


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
    assert "R18" in plant(sub("| R02 | judgment | the author | n/a |\n", ""))


def test_r19_too_few_links(plant):
    assert "R19" in plant(sub("[[methodology]] [[policy_as_api]] [[collaboration]]", "[[methodology]]"))


def test_r20_glossary_duplicate(plant):
    dup = "- **operator**: someone else entirely.\n"
    assert "R20" in plant(glossary_edit=lambda g: g + dup)


def test_r21_accepted_term_missing_from_glossary(plant):
    assert "R21" in plant(sub("## 5 Terms\n", "## 5 Terms\n\n- **unlisted word**: a term no glossary defines.\n"))


def test_r21_draft_may_carry_new_terms(plant):
    edit = lambda t: sub("**Status**: Accepted", "**Status**: Draft")(
        sub("## 5 Terms\n", "## 5 Terms\n\n- **unlisted word**: a term no glossary defines.\n")(t))
    assert "R21" not in plant(edit)


def test_r23_secretary_after_draft(plant):
    assert "R23" in plant(sub("**Secretary**: the Secretary of deliberation #493", "**Secretary**: none"))


def test_r27_decided_without_resolution(plant):
    def edit(text):
        return re.sub(r"^\*\*Resolution\*\*: .*$", "**Resolution**: none", text, count=1, flags=re.M)
    assert "R27" in plant(edit)


def test_r31_final_without_lands_in(plant):
    def edit(text):
        text = text.replace("**Status**: Accepted", "**Status**: Final", 1)
        return re.sub(r"^\*\*Lands-in\*\*: .*$", "**Lands-in**: none", text, count=1, flags=re.M)
    assert "R31" in plant(edit)


def test_findings_name_their_rule_and_line(plant, tmp_path):
    plant(sub("**Type**: Process", "**Type**: Feature"))
    f = next(x for x in mis.check([tmp_path / "framework" / "mis"]) if x.rule == "R08")
    assert f.line == 4 and "Feature" in str(f) and str(f).startswith(str(tmp_path))
