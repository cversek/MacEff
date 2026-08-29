"""Provision git hooks composably: a dispatcher that adopts rather than clobbers.

Git gives a repository exactly one file per hook. Every installer that wants a
say therefore has to refuse or overwrite, and the framework now wants two things
in ``pre-commit`` — the OPSEC scan and the style gate. Whichever installs second
loses, and is silent about it afterwards.

This installs a **dispatcher** that runs a directory, and it reads from two:

``$REPO/.githooks/<hook>.d/``
    Versioned. Travels to every clone. Only for hooklets that embed nothing
    private and nothing machine-specific.

``$GIT_COMMON/hooks.local.d/<hook>.d/``
    Per-clone, never committed. For hooklets carrying a private path — the OPSEC
    gate hardcodes the location of a private pattern file — and for whatever hook
    the developer already had, which is **adopted** here rather than destroyed.

The split is not tidiness. A single shared directory would publish a local's
private material to everyone who clones, which is a worse failure than the
collision it was meant to solve.

The canonical dispatcher is the one in MacEff's own tree, and installing copies
it. Keeping a second copy in a templates directory would let the two drift, and
a drifted hook is the kind that is believed while being wrong.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Hooks this installer knows how to dispatch. Extending it means adding a
#: ``<hook>`` dispatcher alongside the existing one; the dispatcher itself is
#: hook-agnostic and derives its directory from its own basename.
DISPATCHED_HOOKS = ("pre-commit",)

#: Where an adopted or private hooklet lives, relative to the git common dir.
LOCAL_HOOKLET_DIR = "hooks.local.d"

#: The name an adopted pre-existing hook is given. The ``00`` prefix puts it
#: first: whatever the developer had was running before the framework arrived,
#: and it keeps that position.
ADOPTED_NAME = "00-local-preexisting"


def _canonical_hooks_dir(source_root: Optional[Path] = None) -> Path:
    """The ``.githooks`` directory this installer copies from.

    Derived from THIS module's location, not from the agent home. ``find_maceff_root``
    answers a different question — where the running agent lives — and from a
    consciousness home it returns that home, which has no dispatcher in it. The
    package's own path is the only thing guaranteed to sit inside the tree the
    dispatcher ships in.
    """
    if source_root is not None:
        candidate = Path(source_root) / ".githooks"
        if not candidate.is_dir():
            raise ValueError(f"no .githooks directory at {candidate}")
        return candidate

    # .../<root>/macf/src/macf/githooks.py -> <root>
    candidate = Path(__file__).resolve().parents[3] / ".githooks"
    if candidate.is_dir():
        return candidate

    raise ValueError(
        "cannot locate the canonical .githooks directory. This installer copies "
        "from the MacEff source tree; an installed-but-not-checked-out package "
        "does not carry one. Pass source_root explicitly."
    )


def _resolve_git_common_dir(repo: Path) -> Path:
    """The git dir shared by every worktree of this repository.

    A worktree has its own git dir but shares the common one. Installing into
    the per-worktree dir would mean a hooklet installed in one worktree is
    invisible from the others, which is exactly the sort of per-clone surprise
    this module exists to remove.
    """
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--git-common-dir"],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise ValueError(f"not a git repository: {repo}")
    common = Path(out.stdout.strip())
    if not common.is_absolute():
        common = (repo / common).resolve()
    return common


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _is_our_dispatcher(path: Path) -> bool:
    try:
        return "MacEff git hook dispatcher" in path.read_text(errors="replace")
    except (OSError, IOError):
        return False


def install_dispatcher(
    repo: Path,
    source_root: Optional[Path] = None,
    adopt: bool = True,
) -> Dict[str, Any]:
    """Install the dispatcher into ``repo`` and adopt any pre-existing hook.

    Returns **what changed**, not whether the call was made. A report that says
    "done" for a run that replaced a security control tells the operator the one
    thing they needed to check has happened.

    Re-running produces a byte-identical tree: the actions list comes back empty
    on the second run, which is the observable difference between idempotent and
    merely harmless.
    """
    repo = Path(repo).resolve()
    git_common = _resolve_git_common_dir(repo)

    source_dir = _canonical_hooks_dir(source_root)

    actions: List[str] = []
    adopted: List[str] = []

    target_dir = repo / ".githooks"
    for hook in DISPATCHED_HOOKS:
        src = source_dir / hook
        if not src.is_file():
            raise ValueError(f"canonical dispatcher missing: {src}")

        # 1. ADOPT BEFORE INSTALLING. core.hooksPath replaces .git/hooks
        #    wholesale, so a pre-existing hook stops running the moment the
        #    config line lands. Adopting afterwards would leave a window in
        #    which the developer's own gate is silently off, and adopting never
        #    would destroy it.
        existing = git_common / "hooks" / hook
        if adopt and existing.is_file() and not _is_our_dispatcher(existing):
            local_d = git_common / LOCAL_HOOKLET_DIR / f"{hook}.d"
            local_d.mkdir(parents=True, exist_ok=True)
            destination = local_d / ADOPTED_NAME
            if not destination.exists():
                shutil.move(str(existing), str(destination))
                _make_executable(destination)
                adopted.append(f"{hook} -> {LOCAL_HOOKLET_DIR}/{hook}.d/{ADOPTED_NAME}")
                actions.append(f"adopted the existing {hook} as {ADOPTED_NAME}")

        # 2. The dispatcher and its versioned hooklets, copied only when the
        #    content actually differs so a re-run is a genuine no-op.
        target_dir.mkdir(parents=True, exist_ok=True)
        dst = target_dir / hook
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            dst.write_bytes(src.read_bytes())
            actions.append(f"installed the {hook} dispatcher")
        _make_executable(dst)

        # Only the dispatcher is copied. VERSIONED HOOKLETS TRAVEL BY BEING IN
        # THE REPOSITORY -- that is what versioning them means, and copying them
        # into other repos would be actively wrong: MacEff's own 20-style calls
        # tools/lint_staged.sh, which does not exist anywhere else, so every
        # commit in an unrelated repo would be blocked by a gate that repo never
        # asked for. Caught by a test that installed the OPSEC gate into a
        # scratch repo and could no longer commit in it.
        dst_d = target_dir / f"{hook}.d"
        dst_d.mkdir(parents=True, exist_ok=True)
        for existing_hooklet in sorted(dst_d.iterdir()):
            if existing_hooklet.is_file():
                _make_executable(existing_hooklet)

    # 3. Point git at the versioned directory. This is what makes the claim
    #    "enforced for this checkout" true; .git/hooks is per-clone, so no
    #    statement of the form "enforced repo-wide by .git/hooks/..." could ever
    #    have been true, including the one the ratchet's config used to make.
    current = subprocess.run(
        ["git", "-C", str(repo), "config", "--get", "core.hooksPath"],
        capture_output=True, text=True,
    ).stdout.strip()
    if current != ".githooks":
        subprocess.run(
            ["git", "-C", str(repo), "config", "core.hooksPath", ".githooks"],
            check=True, capture_output=True, text=True,
        )
        actions.append("set core.hooksPath to .githooks")

    return {
        "repo": str(repo),
        "git_common_dir": str(git_common),
        "versioned_dir": str(target_dir),
        "local_dir": str(git_common / LOCAL_HOOKLET_DIR),
        "actions": actions,
        "adopted": adopted,
        "already_current": not actions,
    }


def list_hooklets(repo: Path, hook: str = "pre-commit") -> List[Dict[str, Any]]:
    """Every hooklet that would run, in the order the dispatcher would run it.

    Ordering is by basename ACROSS both directories, which is why this cannot be
    answered by listing either one.
    """
    repo = Path(repo).resolve()
    git_common = _resolve_git_common_dir(repo)
    found: Dict[str, Dict[str, Any]] = {}

    for source, directory in (
        ("local", git_common / LOCAL_HOOKLET_DIR / f"{hook}.d"),
        ("versioned", repo / ".githooks" / f"{hook}.d"),
    ):
        if not directory.is_dir():
            continue
        for path in directory.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            found[path.name] = {
                "name": path.name,
                "path": str(path),
                "source": source,
                # Reported rather than filtered: a present-but-not-executable
                # hooklet is the case where skipping quietly would report
                # success for a gate that never ran.
                "executable": os.access(path, os.X_OK),
            }

    return [found[name] for name in sorted(found)]
