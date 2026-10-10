"""Every skill, command and policy a framework file names exists.

Skills dispatch other skills by name, and policies tell the agent which command
to run or which policy to read next. When a target is renamed or retired, the
instruction still reads as an instruction: the agent follows it and finds
nothing, and nothing failed on the way. These tests resolve every such name
against the framework tree.
"""

import argparse
import re
from collections import Counter
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
    """Files in maceff_tools/, console scripts the package installs, and plugins the
    repository ships: each is a name a framework file may tell an agent to use."""
    root = FRAMEWORK.parent
    names = {p.name for p in (root / "maceff_tools").iterdir() if p.is_file()}
    names |= _console_scripts(root / "macf" / "pyproject.toml")
    plugins = root / "plugins"
    if plugins.is_dir():
        names |= {p.name for p in plugins.iterdir() if (p / ".claude-plugin" / "plugin.json").is_file()}
    return names


def _console_scripts(pyproject):
    """Names under [project.scripts]. Parsed by line, not with tomllib, because CI
    still runs Python 3.10, which has no tomllib."""
    names, inside = set(), False
    for line in pyproject.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            inside = stripped == "[project.scripts]"
            continue
        if inside and "=" in stripped and not stripped.startswith("#"):
            names.add(stripped.split("=", 1)[0].strip())
    return names


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



# ---- macf_tools commands, resolved against the CLI's own parser ----------------------------

# `macf_tools policy read x`, `macf_tools task create bug`: the words after macf_tools.
MACF_COMMAND = re.compile(r"macf_tools((?:[ \t]+[a-z][a-z0-9_-]*)+)")

# Commands framework text names on purpose although they do not exist, and how many times.
# A count, not a name, so a stale command beside a deliberate one still fails.
DELIBERATE = {
    # Examples of bad command names, in the CLI naming guidance.
    ("policies/base/development/cli_development.md", "get-current-session-information"): 1,
    ("policies/base/development/cli_development.md", "hooks do-install"): 1,
    ("policies/base/development/cli_development.md", "bc"): 1,
    # Sketches of commands not built yet, each labelled as future where it appears.
    ("policies/base/consciousness/scholarship.md", "memory"): 6,
    ("policies/base/consciousness/structure_governance.md", "ca"): 2,
    ("policies/base/development/release_workflow.md", "tasks"): 1,
    ("templates/SUBAGENT_DEF_TEMPLATE.md", "subagent"): 1,
}


def _cli():
    from macf.cli import _build_parser
    return _build_parser()


def _subcommands(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices
    return None


def _code(text):
    """Fenced blocks and inline code: where text gives a command. In prose, "macf_tools"
    is often followed by an English word ("the macf_tools commands")."""
    fenced = re.findall(r"```.*?```", text, re.S)
    inline = re.findall(r"`[^`\n]+`", re.sub(r"```.*?```", "", text, flags=re.S))
    return "\n".join(fenced + inline)


def _unknown_commands(text, cli):
    """Each `macf_tools <words>` in text's code whose words leave the CLI's subcommands, as
    the words up to and including the first unknown one."""
    unknown = []
    for m in MACF_COMMAND.finditer(_code(text)):
        parser, walked = cli, []
        for word in m.group(1).split():
            subs = _subcommands(parser)
            if subs is None:
                break  # the rest are arguments
            walked.append(word)
            if word not in subs:
                unknown.append(" ".join(walked))
                break
            parser = subs[word]
    return unknown


def test_an_unknown_command_is_reported_and_known_ones_are_not():
    text = (
        "Run `macf_tools agent skills`, then `macf_tools policy read scholarship`.\n"
        "```bash\nmacf_tools task create bug --plan x title\nmacf_tools idea capture x\n```\n"
        "The macf_tools commands, in prose, are not read as commands.\n"
    )
    assert sorted(_unknown_commands(text, _cli())) == ["agent skills", "idea capture"]


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.relative_to(FRAMEWORK)))
def test_every_macf_tools_command_a_framework_file_gives_exists(path):
    rel = str(path.relative_to(FRAMEWORK))
    found = Counter(_unknown_commands(path.read_text(errors="replace"), _cli()))
    expected = Counter({cmd: n for (f, cmd), n in DELIBERATE.items() if f == rel})
    assert found == expected, (
        f"{rel}: macf_tools commands that do not exist {dict(found)}; "
        f"deliberate ones listed for this file {dict(expected)}")


def test_every_deliberate_example_is_still_there():
    """An entry whose text has gone must leave the list, or it would excuse a stale one later."""
    for f in {f for f, _ in DELIBERATE}:
        assert (FRAMEWORK / f).is_file(), f

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
