"""A shared policy's header carries no agent's breadcrumb.

The policy-writing guidelines give a policy header Type, Scope and Status and
no breadcrumb: every agent reads the policy, and one agent's session
coordinate means nothing to the others while pointing at private context.
A cleanup once removed such lines from every policy, and nothing checked, so
two policies written days later brought them back. This test is the check.
"""

import re
from pathlib import Path

import pytest

POLICIES = Path(__file__).resolve().parents[2] / "framework" / "policies"
BREADCRUMB_LINE = re.compile(r"^\*\*Breadcrumb\*\*", re.IGNORECASE)


def _header(path):
    """The policy's header block: every line before the first rule or section heading."""
    lines = []
    for line in path.read_text().splitlines():
        if line.strip() == "---" or line.startswith("## "):
            break
        lines.append(line)
    return lines


def _policies():
    return sorted(p for p in POLICIES.rglob("*.md") if p.name != "README.md")


def test_the_policies_are_found():
    # A moved directory must fail here, not pass every check below vacuously.
    assert len(_policies()) >= 10


@pytest.mark.parametrize("path", _policies(), ids=lambda p: str(p.relative_to(POLICIES)))
def test_a_policy_header_carries_no_breadcrumb(path):
    hits = [line for line in _header(path) if BREADCRUMB_LINE.match(line.strip())]
    assert not hits, (f"{path.relative_to(POLICIES)}: a policy header carries no breadcrumb "
                      f"(see policy_writing, header format): {hits}")
