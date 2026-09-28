"""Calling-card sign-off and default-branch pushes, checked where an agent acts.

`public_voice` §2.1 puts the agent's calling card on the last line of a pull
request body and, since 2026-09-28, of a commit message. A rule an agent must
remember is the weakest form it can take: an agent working for a person who
has just told it what to do will drop it without noticing. These checks make
the rule checkable at the three places the artifact leaves the agent's hands:

- a commit message  -> the ``commit-msg`` hooklet (``githooks check-card``);
- a pull request body or comment -> the PreToolUse hook on ``gh pr ...``;
- a push to the default branch -> the ``pre-push`` hooklet (``githooks check-push``).

EVERY CHECK APPLIES ONLY INSIDE AN AGENT SESSION, and only where the agent's
own config opts in. An operator and an agent can share one account, so the
login cannot tell them apart; Claude Code sets ``CLAUDECODE=1`` in the shells it
runs, and a person's own terminal does not. Outside a session every check
passes, so these hooks never obstruct a human.

Config (``{agent_home}/.maceff/config.json``):

- ``opsec.public_attribution: true`` -- the card is required (commits, PR bodies,
  PR comments). Off by default, as for every other use of the card.
- ``git.forbid_default_branch_push: true`` -- the agent may not push to a
  remote's default branch; its work reaches it through a pull request.
"""

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional

POLICY = "public_voice"


def in_agent_session() -> bool:
    """True inside a Claude Code session: the shells it runs carry CLAUDECODE=1."""
    return os.environ.get("CLAUDECODE") == "1"


def _agent_config() -> dict:
    """The agent's .maceff/config.json, or {} when there is none."""
    from .utils.paths import find_agent_home
    try:
        config_file = find_agent_home() / ".maceff" / "config.json"
        if config_file.exists():
            return json.loads(config_file.read_text()) or {}
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: agent config unreadable, attribution checks off: {e}", file=sys.stderr)
    return {}


def attribution_required(config: Optional[dict] = None) -> bool:
    cfg = _agent_config() if config is None else config
    return bool((cfg.get("opsec") or {}).get("public_attribution", False))


def default_branch_push_forbidden(config: Optional[dict] = None) -> bool:
    cfg = _agent_config() if config is None else config
    return bool((cfg.get("git") or {}).get("forbid_default_branch_push", False))


def card_line_pattern(card: str) -> "re.Pattern[str]":
    """The card as a line: ``[Card: scope#id breadcrumb]``, bare or in italics.

    Anchored to the agent's OWN card: a line carrying another agent's card, or a
    card-shaped placeholder, is not a sign-off by this agent.
    """
    return re.compile(
        r"^\*?\[" + re.escape(card) + r": [A-Za-z_]+#[0-9A-Za-z]+ [^\]\n]*\]\*?\s*$"
    )


def last_line(text: str, strip_git_comments: bool = False) -> str:
    lines = text.splitlines()
    if strip_git_comments:
        lines = [ln for ln in lines if not ln.startswith("#")]
    while lines and not lines[-1].strip():
        lines.pop()
    return lines[-1] if lines else ""


def _card() -> Optional[str]:
    from .utils.identity import get_agent_identity
    card = get_agent_identity()
    return None if not card or card.endswith("@unknown") else card


def missing_card(text: str, what: str, strip_git_comments: bool = False) -> Optional[str]:
    """Why ``text`` fails the sign-off rule, or None when it passes."""
    card = _card()
    if card is None:
        return (f"{what} needs this agent's calling card as its last line, but the agent ID "
                f"could not be resolved. Check `macf_tools env`; see {POLICY} §2.1.")
    if card_line_pattern(card).match(last_line(text, strip_git_comments)):
        return None
    return (f"{what} must end with this agent's calling card as its LAST line:\n"
            f"  [{card}: task#N <breadcrumb>]   (italicised *[...]* in a PR body)\n"
            f"`macf_tools breadcrumb` gives the breadcrumb. Policy: {POLICY} §2.1.")


# ---------------------------------------------------------------- commit-msg

def check_commit_message(path: Path) -> Optional[str]:
    if not (in_agent_session() and attribution_required()):
        return None
    try:
        text = Path(path).read_text()
    except OSError as e:
        return f"The commit message could not be read to check its calling card: {e}"
    return missing_card(text, "A commit message", strip_git_comments=True)


# ---------------------------------------------------------------- pre-push

def _default_branches(remote: str, repo: Optional[Path]) -> set:
    names = {"main", "master"}
    cmd = ["git", "symbolic-ref", "--short", f"refs/remotes/{remote}/HEAD"]
    if repo is not None:
        cmd[1:1] = ["-C", str(repo)]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode == 0 and "/" in out.stdout:
        names.add(out.stdout.strip().split("/", 1)[1])
    return names


def check_push(remote: str, ref_lines: Iterable[str], repo: Optional[Path] = None) -> Optional[str]:
    """Refuse an update of the remote's default branch. ``ref_lines`` is git's
    pre-push stdin: ``<local ref> <local sha> <remote ref> <remote sha>``."""
    if not (in_agent_session() and default_branch_push_forbidden()):
        return None
    protected = _default_branches(remote, repo)
    hits: List[str] = []
    for line in ref_lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        remote_ref = parts[2]
        if remote_ref.startswith("refs/heads/") and remote_ref[len("refs/heads/"):] in protected:
            hits.append(remote_ref[len("refs/heads/"):])
    if not hits:
        return None
    return (f"This agent may not push to the default branch ({', '.join(sorted(set(hits)))}) "
            f"of '{remote}'. Push a feature branch and open a pull request; the operator "
            f"merges. Policy: {POLICY} §2.3.")


# ---------------------------------------------------------------- gh pr

_BODY_FLAGS = {"--body", "-b"}
_BODY_FILE_FLAGS = {"--body-file", "-F"}
_CHECKED = {"create", "edit", "comment"}


def _segments(command: str) -> List[List[str]]:
    """Split a shell command into simple commands at ; && || | (quote-aware)."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return []
    segs: List[List[str]] = [[]]
    for tok in tokens:
        if tok and set(tok) <= set(";&|"):
            segs.append([])
        else:
            segs[-1].append(tok)
    return [s for s in segs if s]


def check_gh_command(command: str, cwd: Optional[str] = None) -> Optional[str]:
    """Why a ``gh pr create|edit|comment`` in ``command`` fails the sign-off rule.

    The body must be readable to be checked: ``--body``/``-b`` or
    ``--body-file``/``-F <path>``. A body the hook cannot see (``--fill``, an
    editor, ``-F -``) is refused with the way to make it checkable, because a
    check that passes what it cannot read is a check that is never run.
    """
    if not (in_agent_session() and attribution_required()):
        return None
    for seg in _segments(command):
        if len(seg) < 3 or os.path.basename(seg[0]) != "gh" or seg[1] != "pr" or seg[2] not in _CHECKED:
            continue
        sub = seg[2]
        body: Optional[str] = None
        unreadable = False
        args = seg[3:]
        for i, tok in enumerate(args):
            flag, sep, inline = tok.partition("=")
            value = inline if sep else (args[i + 1] if i + 1 < len(args) else None)
            if flag in _BODY_FLAGS and value is not None:
                body = value
            elif flag in _BODY_FILE_FLAGS and value is not None:
                if value == "-":
                    unreadable = True
                    continue
                p = Path(value)
                if not p.is_absolute() and cwd:
                    p = Path(cwd) / p
                try:
                    body = p.read_text()
                except OSError:
                    return (f"`gh pr {sub}`: the body file {p} cannot be read. This check runs "
                            f"BEFORE the command, so a file the same command creates does not "
                            f"exist yet: write the body file in an earlier step, then run "
                            f"`gh pr {sub}`. Policy: {POLICY} §2.1.")
        if body is None:
            if sub == "edit" and not unreadable:
                continue  # a title/label/reviewer edit does not touch the body
            return (f"`gh pr {sub}` must carry a body this check can read, ending with the "
                    f"calling card: use --body-file <file>. Policy: {POLICY} §2.1.")
        reason = missing_card(body, f"A pull request {'comment' if sub == 'comment' else 'body'}")
        if reason:
            return reason
    return None
