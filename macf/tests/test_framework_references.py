"""Every skill, command and policy a framework file names exists.

Skills dispatch other skills by name, and policies tell the agent which command
to run or which policy to read next. When a target is renamed or retired, the
instruction still reads as an instruction: the agent follows it and finds
nothing, and nothing failed on the way. These tests resolve every such name
against the framework tree.
"""

import re
from pathlib import Path

import pytest

FRAMEWORK = Path(__file__).resolve().parents[2] / "framework"

# /maceff:ccp, /maceff:learnings:curate, /maceff-ideas-curate. The lookbehind
# keeps paths like framework/commands/maceff/... and URLs out.
SLASH_NAME = re.compile(r"(?<![\w/.])/(maceff[:\-][A-Za-z0-9_:\-]*[A-Za-z0-9_])")
SKILL_CALL = re.compile(r"""Skill\(\s*skill:\s*["']([^"']+)["']""")
# `maceff-delegation` in prose names a skill, or a tool such as `maceff-init`.
TICKED_NAME = re.compile(r"`(maceff-[a-z][a-z0-9-]*[a-z0-9])`")
POLICY_CMD = re.compile(r"macf_tools policy (?:navigate|read|inject) ([a-z_]+)")


def _skills():
    return {p.parent.name for p in (FRAMEWORK / "skills").glob("*/SKILL.md")}


def _commands():
    root = FRAMEWORK / "commands"
    return {
        ":".join(p.relative_to(root).with_suffix("").parts)
        for p in root.rglob("*.md")
        if p.name != "CLAUDE.md"
    }


def _tools():
    return {p.name for p in (FRAMEWORK.parent / "maceff_tools").iterdir() if p.is_file()}


def _policies():
    return {p.stem for p in (FRAMEWORK / "policies").rglob("*.md") if p.name != "README.md"}


def _dangling(text, skills, commands, policies, tools):
    """Names in text that resolve to no skill, command, tool or policy."""
    invocable = skills | commands
    missing = [n for n in SLASH_NAME.findall(text) if n not in invocable]
    missing += [n for n in SKILL_CALL.findall(text) if n not in invocable]
    missing += [n for n in TICKED_NAME.findall(text) if n not in skills | tools]
    missing += [n for n in POLICY_CMD.findall(text) if n not in policies]
    return missing


def _sources():
    return sorted(FRAMEWORK.rglob("*.md"))


def test_the_framework_trees_are_found():
    # A moved directory must fail here, not pass every check below vacuously.
    assert len(_skills()) >= 10
    assert len(_commands()) >= 5
    assert len(_policies()) >= 10
    assert "maceff-init" in _tools()


def test_a_name_that_does_not_exist_is_reported_and_one_that_does_is_not():
    text = (
        "Run /maceff:no-such-command, then Skill(skill: \"maceff-no-such-skill\").\n"
        "The `maceff-no-such-helper` skill, and macf_tools policy read no_such_policy.\n"
        "Then /maceff:ccp, `maceff-delegation`, `maceff-init` and\n"
        "macf_tools policy navigate scholarship. See framework/commands/maceff/ccp.md.\n"
    )
    assert _dangling(text, _skills(), _commands(), _policies(), _tools()) == [
        "maceff:no-such-command",
        "maceff-no-such-skill",
        "maceff-no-such-helper",
        "no_such_policy",
    ]


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.relative_to(FRAMEWORK)))
def test_every_name_a_framework_file_uses_exists(path):
    text = path.read_text(errors="replace")
    missing = _dangling(text, _skills(), _commands(), _policies(), _tools())
    assert not missing, f"{path.relative_to(FRAMEWORK)} names what does not exist: {missing}"


def test_the_wind_down_dispatcher_can_find_its_protocol():
    """The dispatcher reads its order from the wind-down protocol, found by
    navigation question. If the section or its navigation entry goes, the
    skill has nothing to read and still looks complete."""
    policy = (FRAMEWORK / "policies/base/operations/autonomous_operation.md").read_text()
    nav, body = policy.split("=== CEP_NAV_BOUNDARY ===", 1)
    assert re.search(r"^\*\*[\d.]+ Wind-Down Protocol\*\*", nav, re.M)

    section = re.search(r"^### [\d.]+ Wind-Down Protocol\n(.*?)(?=^##)", body, re.M | re.S)
    assert section, "no Wind-Down Protocol section below the navigation boundary"
    # The order is the operator's specification. Changing it is a decision,
    # so it should have to be made here as well as in the policy.
    steps = re.findall(r"^\| \d+ \| `/([^`]+)` \|", section.group(1), re.M)
    assert steps == [
        "maceff:learnings:curate",
        "maceff-ideas-curate",
        "maceff-knowledge-web-curate",
        "maceff:ccp",
        "maceff:jotewr",
    ]
    invocable = _skills() | _commands()
    assert [s for s in steps if s not in invocable] == []

    skill = (FRAMEWORK / "skills/maceff-full-wind-down/SKILL.md").read_text()
    assert "macf_tools policy navigate autonomous_operation" in skill
