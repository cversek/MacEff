"""OPSEC pre-commit gate — keep private agent/dev context out of public repos.

Installs a git pre-commit hook that scans STAGED ADDED LINES against a
pattern profile and rejects the commit on any hit. The profile lives OUTSIDE
the target repo (default: {agent_home}/.maceff/opsec_profiles/) because the
pattern list is itself the private vocabulary — committing it would leak the
very things it guards. The installed hook is a thin shim that reads the
profile path baked in at install time.

Born from a working single-repo implementation (2026-07-22) that caught two
real leaks on its first day — an internal idea-number in a code comment and a
non-ASCII em-dash — both of which had slipped past manual grep sweeps.
Deliberate disclosures bypass with a reviewed `git commit --no-verify`.
"""
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


### Default profile: agent-infrastructure vocabulary + private dev markers.
### Each entry is [regex, human label]. "hard" always rejects; "soft" rejects
### with a wording that says why it is a style smell rather than a leak.
DEFAULT_PROFILE: Dict[str, Any] = {
    "hard": [
        [r"\bc[0-9]{1,2}\b(?![0-9a-fA-F])", "cycle code (c15/c22/c25...)"],
        [r"[Cc]ycle[-_ ][0-9]+", "cycle-N reference"],
        [r"\bEXPERIMENT\s*#?[0-9]", "experiment number"],
        [r"\bMISSION\b|\bDETOUR\b", "internal task-type label"],
        [r"\btask\s*#[0-9]+|\bidea\s*#[0-9]+", "task/idea number"],
        [r"[Mm]ac[Ee]ff|\bMACF\b|\bmacf_tools\b", "framework name"],
        [r"\bbreadcrumb\b|\bJOTEWR\b|\bCCP\b", "framework artifact term"],
        [r"calling.card|ULTRATHINK|\bsubagent\b|\bconsciousness\b", "agent infrastructure term"],
        [r"\bClaude\b|\bAnthropic\b|\bChatGPT\b|\bLLM\b", "AI tool reference"],
        [r"[^\x00-\x7f]", "non-ASCII character"],
    ],
    "soft": [
        [r"\barm [A-HJ-Z]\b", "measurement-arm label from private notes"],
    ],
}

### The hook body written into <repo>/.git/hooks/. Reads the profile at run
### time so pattern edits do not require reinstallation. Kept dependency-free
### (stdlib only) because it runs in whatever python3 the committer has.
HOOK_TEMPLATE = '''#!/usr/bin/env python3
"""Pre-commit gate: reject staged lines that leak private context.

Installed by an external tool; the pattern profile lives outside this repo
on purpose. Bypass after human review with: git commit --no-verify
"""
import json
import re
import subprocess
import sys

PROFILE_PATH = {profile_path!r}


def staged_added_lines():
    out = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color"],
        capture_output=True, text=True,
    ).stdout
    fname = None
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            fname = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            yield fname, line[1:]


def main():
    try:
        with open(PROFILE_PATH) as f:
            profile = json.load(f)
    except (OSError, ValueError) as e:
        print("pre-commit gate: cannot read profile %s (%s); failing closed" % (PROFILE_PATH, e))
        return 1
    checks = [(re.compile(p), label, "hard") for p, label in profile.get("hard", [])]
    checks += [(re.compile(p), label, "soft") for p, label in profile.get("soft", [])]
    hits = []
    for fname, text in staged_added_lines():
        for rx, label, kind in checks:
            m = rx.search(text)
            if m:
                hits.append((fname, label, m.group(0), text.strip()[:100]))
    if hits:
        print("COMMIT REJECTED: private-context leakage in staged changes")
        print("-" * 60)
        for fname, label, tok, ctx in hits:
            print("%s: [%s] %r" % (fname, label, tok))
            print("    %s" % ctx)
        print("-" * 60)
        print("%d hit(s). Fix, or bypass after review: git commit --no-verify" % len(hits))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

SHIM_TEMPLATE = '''#!/bin/sh
exec python3 "$(git rev-parse --git-common-dir)/hooks/check_context_leakage.py"
'''


def default_profiles_dir() -> Path:
    """Profile home, outside any target repo."""
    from .utils.paths import find_agent_home
    home = find_agent_home() or Path.home()
    d = home / ".maceff" / "opsec_profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_default_profile() -> Path:
    """Write the default profile if absent; never overwrite user edits."""
    path = default_profiles_dir() / "default.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_PROFILE, indent=2))
    return path


def install_hook(repo: Path, profile: Optional[Path] = None) -> Dict[str, Any]:
    """Install the leakage gate into repo's git hooks. Returns install facts."""
    repo = Path(repo).resolve()
    git_dir = repo / ".git"
    if not git_dir.exists():
        raise ValueError(f"not a git repository (no .git): {repo}")
    # Worktree checkouts have a .git FILE pointing at the real git dir; hooks
    # live in the common dir so one install covers all worktrees.
    if git_dir.is_file():
        gitdir_line = git_dir.read_text().strip()
        actual = Path(gitdir_line.split("gitdir:", 1)[1].strip())
        common = actual / "commondir"
        if common.exists():
            actual = (actual / common.read_text().strip()).resolve()
        git_dir = actual
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    profile_path = Path(profile).resolve() if profile else ensure_default_profile()
    if not profile_path.exists():
        raise ValueError(f"profile not found: {profile_path}")
    # Refuse a profile inside the repo tree: it would get committed.
    inside = True
    try:
        profile_path.relative_to(repo)
    except ValueError:
        inside = False
    if inside:
        raise ValueError(
            f"profile {profile_path} is inside the target repo -- the pattern "
            "list is private vocabulary and must live outside the tree"
        )

    checker = hooks_dir / "check_context_leakage.py"
    checker.write_text(HOOK_TEMPLATE.format(profile_path=str(profile_path)))
    shim = hooks_dir / "pre-commit"
    if shim.exists() and "check_context_leakage" not in shim.read_text():
        raise ValueError(
            f"a different pre-commit hook already exists at {shim}; "
            "chain it manually rather than overwriting"
        )
    shim.write_text(SHIM_TEMPLATE)
    for p in (checker, shim):
        os.chmod(p, p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return {
        "repo": str(repo),
        "hooks_dir": str(hooks_dir),
        "profile": str(profile_path),
    }
