"""
Paths utilities.
"""

import os
import re
import stat
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional


def detect_cc_binary() -> str:
    """Detect the Claude Code binary path.

    Resolution order:
    1. MACF_CC_BINARY env var (explicit override, e.g., from launcher alias)
    2. shutil.which('claude') resolved through symlinks
    3. Falls back to "(not found)"

    Returns human-readable string showing resolved path and source.
    """
    import shutil

    # Priority 1: Explicit env var (set by launcher alias)
    env_binary = os.environ.get('MACF_CC_BINARY')
    if env_binary:
        return env_binary

    # Priority 2: Find on PATH and resolve symlinks
    try:
        cc_path = shutil.which('claude')
        if cc_path:
            resolved = str(Path(cc_path).resolve())
            if resolved != cc_path:
                return f"{resolved} (via {cc_path})"
            return resolved
    except (OSError, ValueError) as e:
        print(f"Warning: CC binary detection failed: {e}", file=sys.stderr)

    return "(not found on PATH)"


def encode_cc_project_path(path: str) -> str:
    """Encode a filesystem path the way Claude Code does for project directories.

    CC stores project data at ~/.claude/projects/{encoded_path}/ where
    all non-alphanumeric characters are replaced with hyphens.

    Example: /Users/foo/My Project → -Users-foo-My-Project
    """
    return re.sub(r'[^a-zA-Z0-9]', '-', path)


def cc_project_dir(project_root: Path) -> Path:
    """The one Claude Code transcript directory of the project at ``project_root``.

    A match on the project's name instead would also take every project whose
    path contains it: for an agent home, each repository under it.
    """
    return Path.home() / ".claude" / "projects" / encode_cc_project_path(str(project_root))


# The parent of the per-user fallback below. A module constant so that a test
# can point it at a temporary directory instead of the real /tmp.
_TMP_ROOT = "/tmp"


def user_runtime_dir() -> Path:
    """This user's private directory for MacEff's own small runtime files.

    ``$XDG_RUNTIME_DIR`` when it is set, which is per-user by construction.
    Otherwise ``/tmp/macf-<uid>``, created 0700 on first use.

    Two other fallbacks look reasonable and are wrong:

    - A bare ``/tmp`` is shared by every account. The first uid to write a file
      there owns it, and the next agent on the same host or container can
      neither replace it nor tell it from its own. The supervisor met this
      first and keeps its registry under ``/tmp/macf-<uid>`` for that reason.
    - ``/run/user/<uid>`` exists only where a login manager created it. It does
      not exist on macOS, nor in a container started without one, so a write
      there fails.

    The fallback must be this user's private directory, because the files kept
    here include an agent's own masking declaration:

    - One this user owns that others can only read is tightened to 0700 and
      used. That is the shape real hosts already have: the supervisor creates
      this directory as the parent of its registry, and ``mkdir(parents=True)``
      gives parents the umask default (0755), whatever mode the leaf asks for
      (#494).
    - One that others can write is refused, since files may have been planted
      in it; tightening it now would not remove them.
    - One another account owns, or anything that is not a real directory (a
      symlink planted in the shared ``/tmp``), is refused. ``lstat`` is used so
      a symlink is never followed into a directory this user would then chmod.

    Raises:
        PermissionError: the fallback exists and is not this user's directory,
            or others can write it.
    """
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg)
    path = Path(_TMP_ROOT) / f"macf-{os.getuid()}"
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    st = os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o022:
        raise PermissionError(
            f"{path} is not this user's private directory (owner uid {st.st_uid}, "
            f"mode {st.st_mode & 0o777:o}); refusing to keep runtime files there")
    if st.st_mode & 0o077:
        os.chmod(path, 0o700)
    return path


@lru_cache(maxsize=1)
def get_macf_package_path() -> Optional[Path]:
    """Get the path to the installed macf package directory.

    Walks upward from this file looking for .macf_root_marker file.
    This explicit marker avoids false positives from generic files.

    Works for both:
    - Regular pip install (site-packages/macf/)
    - Editable install (src/macf/)

    Returns:
        Path to macf package root, or None if marker not found
    """
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".macf_root_marker").exists():
            return current
        current = current.parent
    return None


@lru_cache(maxsize=1)
def find_maceff_root() -> Path:
    """Find MacEff installation root.

    Priority:
    1. MACEFF_ROOT_DIR env var (explicit configuration)
    2. Git root with framework/ subdirectory (development checkout)
    3. Discovery via framework/ marker from __file__
    4. Current working directory as fallback

    This is where MacEff repo is checked out (host) or installed (container).
    The framework/ subdirectory contains policies and templates.

    Result is cached - warnings only appear once per process.
    """
    fallback_reasons = []

    # 1. Check MACEFF_ROOT_DIR (preferred for container environments)
    maceff_root = os.environ.get("MACEFF_ROOT_DIR")
    if maceff_root:
        root_path = Path(maceff_root)
        if root_path.exists() and root_path.is_dir():
            # Verify by checking for framework/ subdirectory
            if (root_path / "framework").exists():
                return root_path
            fallback_reasons.append(f"MACEFF_ROOT_DIR={maceff_root} missing framework/")
        else:
            fallback_reasons.append(f"MACEFF_ROOT_DIR={maceff_root} does not exist")

    # 2. Try git repository root with framework/ marker
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=1,
            cwd=Path.cwd(),
        )
        if result.returncode == 0:
            git_root = Path(result.stdout.strip())
            if (git_root / "framework").exists():
                return git_root
            fallback_reasons.append(f"git root {git_root} missing framework/")
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        fallback_reasons.append("git not available or not in repo")

    # 3. Discovery by walking up from __file__ looking for framework/
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / "framework").exists():
            return current
        current = current.parent
    fallback_reasons.append("no framework/ found walking up from __file__")

    # 4. Fallback with warning
    print(
        f"⚠️ MACF: MacEff root not found, using cwd fallback: {Path.cwd()}\n"
        f"   Reasons: {'; '.join(fallback_reasons)}\n"
        f"   Fix: Set MACEFF_ROOT_DIR to MacEff installation location",
        file=sys.stderr,
    )
    return Path.cwd()


# Variables that change where git looks for a repository. With any of them set,
# ask git rather than reproduce its discovery.
_GIT_LOCATION_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR",
                     "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM")


def git_location_redirected() -> bool:
    """True when the environment changes where git finds a repository."""
    return any(os.environ.get(v) for v in _GIT_LOCATION_ENV)


def find_git_worktree(start: Path) -> Optional[Path]:
    """The top of the working tree holding ``start``, found the way git finds it.

    The first directory at or above ``start`` with a ``.git`` entry (a
    directory, or the file a linked worktree or submodule has), not crossing
    onto another filesystem, which git by default does not either. None when
    there is none. A few stat calls where ``git rev-parse --show-toplevel`` is a
    process; callers check ``git_location_redirected()`` first and ask git when
    it is true. An OSError from the walk propagates: the caller asks git.
    """
    here = start.resolve()
    device = here.stat().st_dev
    for directory in (here, *here.parents):
        if directory.stat().st_dev != device:
            return None
        if (directory / ".git").exists():
            return directory
    return None


def _git_toplevel_from_git(cwd: Path) -> Optional[Path]:
    try:
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                                capture_output=True, text=True, timeout=1, cwd=cwd)
    except (subprocess.SubprocessError, OSError) as e:
        print(f"⚠️ MACF: git could not run to find the repository above {cwd}: {e}", file=sys.stderr)
        return None
    return Path(result.stdout.strip()) if result.returncode == 0 else None


def git_toplevel(cwd: Path) -> Optional[Path]:
    """The working tree top above ``cwd``: from the filesystem, or from git when the
    environment redirects git or the filesystem cannot be searched."""
    if not git_location_redirected():
        try:
            return find_git_worktree(cwd)
        except OSError as e:
            print(f"⚠️ MACF: could not search above {cwd} for a repository ({e}); asking git",
                  file=sys.stderr)
    return _git_toplevel_from_git(cwd)


@lru_cache(maxsize=1)
def find_project_root() -> Path:
    """Find user's project/workspace root.

    Priority:
    1. CLAUDE_PROJECT_DIR env var (set by Claude Code)
    2. Git root with .claude/ or CLAUDE.md marker
    3. Current working directory

    This is where `claude` was launched - the user's workspace.
    Contains project-specific CLAUDE.md and .claude/ configuration.

    Result is cached - warnings only appear once per process.
    """
    # 1. Check CLAUDE_PROJECT_DIR (set by Claude Code)
    claude_project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if claude_project_dir:
        project_path = Path(claude_project_dir)
        if project_path.exists() and project_path.is_dir():
            return project_path

    # 2. Git repository root with Claude markers. Outside Claude Code (a
    # terminal, a tool's shell) this runs for every command, so it is found
    # from the filesystem unless the environment redirects git.
    cwd = Path.cwd()
    git_root = git_toplevel(cwd)
    if git_root is not None and ((git_root / ".claude").exists() or (git_root / "CLAUDE.md").exists()):
        return git_root

    # 3. Fallback to current working directory
    return cwd


@lru_cache(maxsize=1)
def find_agent_home() -> Path:
    """Find agent's persistent home directory root.

    Priority:
    1. MACEFF_AGENT_HOME_DIR env var (explicit configuration)
    2. Project root detection via .maceff/agent_events_log.jsonl marker
    3. ~ (user home directory, default)

    Directory structure under agent_home:
    - {agent_home}/.maceff/config.json - agent configuration
    - {agent_home}/.maceff/agent_events_log.jsonl - event log
    - {agent_home}/agent/ - consciousness artifacts (CAs)

    This is SACRED - agent continuity persists across project reassignments.

    Result is cached.
    """
    # 1. Check MACEFF_AGENT_HOME_DIR (explicit configuration takes precedence)
    agent_home = os.environ.get("MACEFF_AGENT_HOME_DIR")
    if agent_home:
        home_path = Path(agent_home)
        if home_path.exists() and home_path.is_dir():
            return home_path
        # Create if doesn't exist but env var is set
        try:
            home_path.mkdir(parents=True, exist_ok=True, mode=0o755)
            return home_path
        except OSError:
            pass  # Fall through to detection

    # 2. Project root detection: walk up from cwd looking for .maceff/agent_events_log.jsonl
    # This enables running macf_tools from within a project without setting env vars
    current = Path.cwd().resolve()
    while current != current.parent:
        marker = current / ".maceff" / "agent_events_log.jsonl"
        if marker.exists():
            return current
        current = current.parent

    # 3. Default to user home directory
    return Path.home()

def session_root() -> Path:
    """Where per-session directories live: ``/tmp/macf`` unless ``MACF_SESSION_ROOT``
    names another.

    Each agent and session gets a directory under it for the hook log, scratch
    scripts and caches. The test suite points it at a temporary directory, so a
    run inside a live session cannot write into that session's hook log.
    """
    return Path(os.environ.get("MACF_SESSION_ROOT") or "/tmp/macf")


def get_session_dir(
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    subdir: Optional[str] = None,
    create: bool = True
) -> Optional[Path]:
    """
    Get agent-scoped session directory with optional subdirectory.

    Path structure: {session_root}/{agent_id}/{session_id}/{subdir}/, where the
    root is /tmp/macf by default (see ``session_root``).

    Args:
        session_id: Session ID (auto-detected if None)
        agent_id: Agent ID (auto-detected using ConsciousnessConfig if None)
        subdir: Optional subdirectory ("hooks", "dev_scripts", "logs")
        create: Create directory if doesn't exist

    Returns:
        Path or None if creation fails and create=False
    """
    # Auto-detect session_id
    if not session_id:
        # DEFERRED DELIBERATELY: session.py imports find_project_root from
        # this module, so a module-level import here is circular. This is the
        # justified-deferred-import case the coding standards name, and it is
        # scoped to the one function that uses it -- the hazard the policy
        # forbids is a function-level import whose name is then used in
        # ANOTHER scope, which is how it becomes a NameError nobody sees
        # until that branch runs.
        from .session import get_current_session_id
        session_id = get_current_session_id()

    if session_id == "unknown":
        return None

    # Auto-detect agent_id using ConsciousnessConfig
    if not agent_id:
        try:
            from ..config import ConsciousnessConfig
            config = ConsciousnessConfig()
            agent_id = config.agent_id
        except (ImportError, OSError, KeyError) as e:
            # Fallback if config unavailable
            print(f"⚠️ MACF: Config load failed (using env fallback): {e}", file=sys.stderr)
            agent_id = os.environ.get('MACEFF_USER') or os.environ.get('USER') or 'unknown_agent'

    # Build unified path: {session_root}/{agent_id}/{session_id}/{subdir}/
    base_path = session_root() / agent_id / session_id

    if subdir:
        base_path = base_path / subdir

    if create:
        try:
            base_path.mkdir(parents=True, exist_ok=True, mode=0o755)
            return base_path
        except OSError as e:
            print(f"⚠️ MACF: Session dir creation failed: {e}", file=sys.stderr)
            return None
    else:
        return base_path if base_path.exists() else None

def get_hooks_dir(session_id: Optional[str] = None, create: bool = True) -> Optional[Path]:
    """Get hooks subdirectory: /tmp/macf/{agent_id}/{session_id}/hooks/"""
    return get_session_dir(session_id=session_id, subdir="hooks", create=create)

def get_dev_scripts_dir(session_id: Optional[str] = None, create: bool = True) -> Optional[Path]:
    """Get dev_scripts subdirectory: /tmp/macf/{agent_id}/{session_id}/dev_scripts/"""
    return get_session_dir(session_id=session_id, subdir="dev_scripts", create=create)

def get_logs_dir(session_id: Optional[str] = None, create: bool = True) -> Optional[Path]:
    """Get logs subdirectory: /tmp/macf/{agent_id}/{session_id}/logs/"""
    return get_session_dir(session_id=session_id, subdir="logs", create=create)

def get_session_transcript_path(session_id: str) -> Optional[str]:
    """Get path to session JSONL file given session ID.

    Args:
        session_id: Session identifier

    Returns:
        Path string to JSONL file or None if not found
    """
    if session_id == "unknown":
        return None

    projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.exists():
        return None

    # Find project directory using current working directory name
    project_name = find_project_root().name

    # Try exact match first
    for project_dir in projects_dir.glob(f"*{project_name}*"):
        potential_file = project_dir / f"{session_id}.jsonl"
        if potential_file.exists():
            return str(potential_file)

    # Fallback: search all project directories
    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            potential_file = project_dir / f"{session_id}.jsonl"
            if potential_file.exists():
                return str(potential_file)

    return None
