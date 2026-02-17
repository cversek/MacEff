"""
Task creation module with MTMD generation and smart defaults.

Provides functions to create MISSION, EXPERIMENT, DETOUR, PHASE, and BUG tasks
with automatic metadata population and skeleton CA file generation.
"""

import json
import os
import re
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Generator

from .models import MacfTaskMetaData
from .reader import TaskReader
from ..utils.paths import find_agent_home


def validate_plan_ca_ref(plan_ca_ref: Optional[str]) -> None:
    """Reject CC native plan paths that are not MacEff-compliant CAs.

    CC plan files (~/.claude/plans/*.md) are ephemeral and lack MacEff metadata
    (breadcrumbs, timestamps, CA type headers). Tasks referencing them create
    broken forensic trails after compaction.

    Raises:
        ValueError: If plan_ca_ref matches CC native plan path pattern
    """
    if plan_ca_ref is None:
        return

    # Expand ~ and resolve to catch both literal and expanded forms
    expanded = str(Path(plan_ca_ref).expanduser())
    home = str(Path.home())
    cc_plans_dir = os.path.join(home, '.claude', 'plans')

    if expanded.startswith(cc_plans_dir) or '/.claude/plans/' in plan_ca_ref:
        raise ValueError(
            "CC native plans (~/.claude/plans/) are not MacEff-compliant CAs.\n"
            "Transfer plan content to a compliant CA under ~/agent/public/roadmaps/.\n\n"
            "For guidance: macf_tools policy navigate roadmaps_drafting"
        )


@contextmanager
def _unprotect_for_creation(dir_path: Path) -> Generator[None, None, None]:
    """Context manager to temporarily unprotect task directory for file creation.

    CC purges all task files when all tasks become completed. Protection (chmod 555)
    prevents this, but blocks file creation. This context manager:
    1. Checks if directory is protected (no write permission)
    2. Temporarily enables write (chmod 755)
    3. Yields for file creation
    4. Re-protects directory (chmod 555)

    If directory wasn't protected, does nothing special.
    """
    if not dir_path.exists():
        # Directory doesn't exist yet, no protection to manage
        yield
        # After creation, protect the new directory
        if dir_path.exists():
            os.chmod(dir_path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 555
        return

    # Check current permissions
    current_mode = dir_path.stat().st_mode
    is_protected = not (current_mode & stat.S_IWUSR)  # No user write = protected

    if is_protected:
        # Temporarily enable write
        os.chmod(dir_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 755

    try:
        yield
    finally:
        # Always protect after creation (even if it wasn't protected before)
        # This makes protection the default state
        os.chmod(dir_path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 555

# ANSI escape codes for dim text (CC UI renders these!)
ANSI_DIM = "\033[2m"
ANSI_RESET = "\033[0m"
ANSI_BOLD = "\033[1m"
ANSI_ORANGE = "\033[38;5;208m"
ANSI_STRIKE = "\033[9m"
# Selective reset codes (don't break nesting)
ANSI_DIM_OFF = "\033[22m"
ANSI_STRIKE_OFF = "\033[29m"

# Sentinel task ID (reserved system ID)
SENTINEL_TASK_ID = "000"


def compose_subject(task_id: str, task_type: str, title: str,
                    parent_id: Optional[str] = None, status: str = "pending",
                    plan_ca_ref: Optional[str] = None,
                    custom: Optional[dict] = None) -> str:
    """Compose subject from components with proper ANSI formatting.

    Args:
        task_id: Task ID (string)
        task_type: One of MISSION, EXPERIMENT, DETOUR, BUG, AD_HOC, TASK, PHASE, SENTINEL
        title: Plain semantic title
        parent_id: Optional parent task ID for hierarchy
        status: Task status (pending, in_progress, completed)
        plan_ca_ref: Optional CA reference (affects PHASE display: 📋 if set, - if not)
    """
    # Sentinel is special
    if task_type == "SENTINEL":
        return f"{ANSI_BOLD}{ANSI_ORANGE}🛡️ MACF TASK LIST{ANSI_RESET}"

    # ID prefix (dim, right-aligned to width 4 with space padding)
    # E.g., "  #5", " #11", "#238", "#999"
    id_str = f"#{task_id}"
    padded_id = id_str.rjust(4)  # Right-align to width 4
    id_part = f"{ANSI_DIM}{padded_id}{ANSI_DIM_OFF}"

    # Parent reference if exists and not sentinel
    if parent_id and parent_id != SENTINEL_TASK_ID:
        parent_part = f" {ANSI_DIM}[^#{parent_id}]{ANSI_DIM_OFF}"
    else:
        parent_part = ""

    # Type emoji/marker
    # PHASE type: 📋 if has subplan (plan_ca_ref), - if not
    if task_type == "PHASE":
        type_part = "📋" if plan_ca_ref else "-"
    else:
        type_map = {
            "MISSION": "🗺️ MISSION:",
            "EXPERIMENT": "🧪 EXPERIMENT:",
            "DETOUR": "↩️ DETOUR:",
            "DELEG_PLAN": "📜 DELEG:",
            "BUG": "🐛 BUG:",
            "TASK": "🔧",  # Generic task with wrench emoji
        }
        # GH_ISSUE has special format: 🐙 GH/owner/repo#N [label]: title
        if task_type == "GH_ISSUE" and custom:
            owner = custom.get("gh_owner", "?")
            repo = custom.get("gh_repo", "?")
            issue_num = custom.get("gh_issue_number", "?")
            labels = custom.get("gh_labels", [])
            label_str = f" [{labels[0]}]" if labels else ""
            type_part = f"🐙 GH/{owner}/{repo}#{issue_num}{label_str}:"
        else:
            type_part = type_map.get(task_type, "")

    return f"{id_part}{parent_part} {type_part} {title}"


def _ensure_sentinel_task(session_path: Path) -> None:
    """Create sentinel task #000 if it doesn't exist.

    The sentinel task prevents CC from purging all tasks when they're completed.
    CC only purges when ALL tasks are completed - having one permanent in_progress
    task prevents this.

    Belt-and-suspenders protection alongside chmod 555 directory protection.
    """
    sentinel_file = session_path / f"{SENTINEL_TASK_ID}.json"

    if sentinel_file.exists():
        return  # Sentinel already exists

    sentinel_data = {
        "id": SENTINEL_TASK_ID,
        "subject": f"{ANSI_BOLD}{ANSI_ORANGE}🛡️ MACF TASK LIST{ANSI_RESET}",
        "description": """<macf_task_metadata version="1.0">
task_type: SENTINEL
created_by: MACF
parent_id: null
</macf_task_metadata>

# MACF Task List Sentinel

**Purpose**: This is a permanent system task that protects the task list from CC purge.

## Why This Exists

Claude Code purges ALL task files when all tasks become 'completed'. This sentinel task remains forever 'in_progress' to prevent that purge.

## Rules

1. **NEVER complete this task** - doing so may trigger task purge
2. **NEVER delete this task** - it protects all other tasks
3. This task is managed by MACF infrastructure, not agents

## Technical Details

- ID: 000 (reserved system ID)
- Status: permanently in_progress
- File permissions: read-only (444)

*Belt-and-suspenders protection alongside chmod 555 directory protection.*""",
        "activeForm": "Protecting task list",
        "status": "in_progress",
        "blocks": [],
        "blockedBy": []
    }

    # Write sentinel file
    with open(sentinel_file, "w") as f:
        json.dump(sentinel_data, f, indent=2)

    # Make sentinel read-only (444) - can't be accidentally modified
    os.chmod(sentinel_file, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    # Emit task_started event so sentinel appears in get_active_tasks_from_events()
    # This enables core policy injection via manifest task_type_policies SENTINEL mapping
    try:
        from ..agent_events_log import append_event
        from .events import TASK_STARTED
        append_event(TASK_STARTED, {
            "task_id": SENTINEL_TASK_ID,
            "task_type": "SENTINEL",
            "breadcrumb": "",
            "plan_ca_ref": "",
            "source": "sentinel_creation",
        })
    except Exception as e:
        print(f"⚠️ MACF: Sentinel event emission failed: {e}", file=sys.stderr)


@dataclass
class CreateResult:
    """Result of task creation operation."""
    task_id: int
    subject: str
    folder_path: Optional[str] = None  # For mission/experiment/detour
    ca_path: Optional[str] = None      # roadmap.md or protocol.md path
    mtmd: Optional[MacfTaskMetaData] = None


def _sanitize_title(title: str) -> str:
    """Sanitize title for use in folder/file names."""
    # Replace non-alphanumeric (except dash/underscore) with underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', title)
    # Collapse multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    return sanitized.strip('_')



def _get_next_task_id(session_uuid: Optional[str] = None) -> int:
    """Get next available task ID by scanning existing task files."""
    reader = TaskReader(session_uuid)
    task_files = reader.list_task_files()

    if not task_files:
        return 1

    # Extract IDs and find max
    ids = []
    for tf in task_files:
        if tf.stem.isdigit():
            ids.append(int(tf.stem))

    return max(ids) + 1 if ids else 1


def _get_next_experiment_number(agent_root: Path) -> int:
    """Scan experiments folder to find next NNN number."""
    experiments_dir = agent_root / "agent" / "public" / "experiments"

    if not experiments_dir.exists():
        return 1

    # Find folders matching YYYY-MM-DD_HHMMSS_NNN_* pattern
    max_num = 0
    for folder in experiments_dir.iterdir():
        if folder.is_dir():
            # Match pattern: YYYY-MM-DD_HHMMSS_NNN_*
            match = re.match(r'\d{4}-\d{2}-\d{2}_\d{6}_(\d{3})_', folder.name)
            if match:
                num = int(match.group(1))
                max_num = max(max_num, num)

    return max_num + 1


def _create_task_file(
    task_id: int,
    subject: str,
    description: str,
    status: str = "pending",
    session_uuid: Optional[str] = None,
    blocked_by: Optional[List[str]] = None
) -> Path:
    """Create task JSON file directly.

    Automatically handles CC purge protection:
    - Temporarily unprotects directory if protected
    - Creates the task file
    - Re-protects directory (protection becomes default state)
    """
    reader = TaskReader(session_uuid)

    if not reader.session_path:
        raise RuntimeError("Could not determine session path")

    # Build task JSON structure before entering protection context
    # Generate activeForm from subject (present continuous form)
    # Strip ID prefix, emoji prefix and convert to gerund-style
    active_form = subject
    # First strip #N prefix if present
    if active_form.startswith("#"):
        active_form = re.sub(r'^#\d+\s*', '', active_form)
    for prefix in ["🗺️ MISSION:", "🧪 EXPERIMENT:", "↩️ DETOUR:", "📋", "🐛 BUG:", "[^#"]:
        if prefix in active_form:
            active_form = active_form.split(prefix)[-1].strip()
            if active_form.startswith("]"):
                active_form = active_form.split("]", 1)[-1].strip()
            break
    # Make it gerund-style if it's a noun phrase
    if not active_form.endswith("ing"):
        active_form = f"Working on {active_form}"

    task_data = {
        "id": str(task_id),  # CC expects string, not int
        "subject": subject,
        "description": description,
        "activeForm": active_form,  # Required for CC UI visibility
        "status": status,
        "blocks": [],
        "blockedBy": blocked_by or []
    }

    # Use protection context manager for directory operations
    # This temporarily unprotects if needed, then re-protects after
    with _unprotect_for_creation(reader.session_path):
        # Ensure session directory exists
        reader.session_path.mkdir(parents=True, exist_ok=True)

        # Ensure sentinel task exists (belt-and-suspenders CC purge protection)
        _ensure_sentinel_task(reader.session_path)

        task_file = reader.session_path / f"{task_id}.json"

        # Write task file
        with open(task_file, "w") as f:
            json.dump(task_data, f, indent=2)

    return task_file


def _generate_mtmd_block(mtmd: MacfTaskMetaData) -> str:
    """Generate MTMD XML block for embedding in description."""
    yaml_content = mtmd.to_yaml()
    return f'<macf_task_metadata version="{mtmd.version}">\n{yaml_content}</macf_task_metadata>'


def create_mission(
    title: str,
    parent_id: Optional[str] = None,
    repo: Optional[str] = None,
    version: Optional[str] = None,
    agent_root: Optional[Path] = None
) -> CreateResult:
    """
    Create MISSION task with roadmap folder atomically.

    Creates:
    - Task JSON file with MTMD
    - Roadmap folder: agent/public/roadmaps/YYYY-MM-DD_Title/
    - Skeleton roadmap.md file

    Args:
        title: Mission title (e.g., "MACF Task CLI")
        parent_id: Optional parent task ID (defaults to "000" sentinel)
        repo: Optional repository name (e.g., "MacEff")
        version: Optional target version (e.g., "0.4.0")
        agent_root: Optional agent root path (auto-detect if None)

    Returns:
        CreateResult with task_id, folder_path, ca_path, and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get agent root
    if agent_root is None:
        agent_root = find_agent_home()

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Create folder name: YYYY-MM-DD_Title
    date_str = datetime.now().strftime("%Y-%m-%d")
    sanitized_title = _sanitize_title(title)
    folder_name = f"{date_str}_{sanitized_title}"

    # Create roadmap folder
    roadmaps_dir = agent_root / "agent" / "public" / "roadmaps"
    roadmaps_dir.mkdir(parents=True, exist_ok=True)

    folder_path = roadmaps_dir / folder_name
    folder_path.mkdir(exist_ok=True)

    # Create roadmap.md skeleton
    roadmap_file = folder_path / "roadmap.md"
    ca_path_relative = str(roadmap_file.relative_to(agent_root))

    roadmap_content = f"""# ROADMAP: {title}

**Date**: {datetime.now().strftime("%Y-%m-%d")}
**Breadcrumb**: {breadcrumb}
**Status**: DRAFT

---

## Purpose

{{Describe mission objectives here}}

---

## Phase Breakdown

### Phase 1: {{First Phase}}

**Completion Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2

---

## Success Criteria

1. {{Overall criterion 1}}
2. {{Overall criterion 2}}
"""

    roadmap_file.write_text(roadmap_content)

    # Default parent_id to sentinel if not specified
    effective_parent_id = parent_id if parent_id else SENTINEL_TASK_ID

    # Create MTMD with title for recomposition
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="MISSION",
        title=title,
        parent_id=effective_parent_id,
        plan_ca_ref=ca_path_relative,
        repo=repo,
        target_version=version
    )

    # Build description with MTMD
    description = f"→ {ca_path_relative}\n\n{_generate_mtmd_block(mtmd)}"

    # Compose subject with proper ANSI nesting
    subject = compose_subject(str(task_id), "MISSION", title)

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        folder_path=str(folder_path.relative_to(agent_root)),
        ca_path=ca_path_relative,
        mtmd=mtmd
    )


def create_experiment(
    title: str,
    parent_id: Optional[str] = None,
    agent_root: Optional[Path] = None
) -> CreateResult:
    """
    Create EXPERIMENT task with protocol folder atomically.

    Creates:
    - Task JSON file with MTMD
    - Experiment folder: agent/public/experiments/YYYY-MM-DD_HHMMSS_NNN_Title/
    - Skeleton protocol.md file

    Args:
        title: Experiment title
        parent_id: Optional parent task ID (defaults to "000" sentinel)
        agent_root: Optional agent root path (auto-detect if None)

    Returns:
        CreateResult with task_id, folder_path, ca_path, and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get agent root
    if agent_root is None:
        agent_root = find_agent_home()

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID and experiment number
    task_id = _get_next_task_id()
    exp_num = _get_next_experiment_number(agent_root)

    # Create folder name: YYYY-MM-DD_HHMMSS_NNN_Title
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    sanitized_title = _sanitize_title(title)
    folder_name = f"{timestamp}_{exp_num:03d}_{sanitized_title}"

    # Create experiment folder
    experiments_dir = agent_root / "agent" / "public" / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)

    folder_path = experiments_dir / folder_name
    folder_path.mkdir(exist_ok=True)

    # Create protocol.md skeleton
    protocol_file = folder_path / "protocol.md"
    ca_path_relative = str(protocol_file.relative_to(agent_root))

    protocol_content = f"""# EXPERIMENT: {title}

**Date**: {datetime.now().strftime("%Y-%m-%d")}
**Breadcrumb**: {breadcrumb}
**Status**: DRAFT

---

## Hypothesis

{{State hypothesis here}}

---

## Method

{{Describe approach}}

---

## Success Criteria

{{Define what validates/invalidates hypothesis}}
"""

    protocol_file.write_text(protocol_content)

    # Default parent_id to sentinel if not specified
    effective_parent_id = parent_id if parent_id else SENTINEL_TASK_ID

    # Create MTMD with title for recomposition
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="EXPERIMENT",
        title=title,
        parent_id=effective_parent_id,
        plan_ca_ref=ca_path_relative
    )

    # Build description with MTMD
    description = f"→ {ca_path_relative}\n\n{_generate_mtmd_block(mtmd)}"

    # Compose subject with proper ANSI nesting
    subject = compose_subject(str(task_id), "EXPERIMENT", title)

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        folder_path=str(folder_path.relative_to(agent_root)),
        ca_path=ca_path_relative,
        mtmd=mtmd
    )


def create_detour(
    title: str,
    parent_id: Optional[str] = None,
    repo: Optional[str] = None,
    version: Optional[str] = None,
    agent_root: Optional[Path] = None
) -> CreateResult:
    """
    Create DETOUR task with roadmap folder atomically.

    Creates:
    - Task JSON file with MTMD
    - Roadmap folder: agent/public/roadmaps/YYYY-MM-DD_Title/
    - Skeleton roadmap.md file

    Args:
        title: Detour title
        parent_id: Optional parent task ID (defaults to "000" sentinel)
        repo: Optional repository name
        version: Optional target version
        agent_root: Optional agent root path (auto-detect if None)

    Returns:
        CreateResult with task_id, folder_path, ca_path, and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get agent root
    if agent_root is None:
        agent_root = find_agent_home()

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Create folder name: YYYY-MM-DD_Title
    date_str = datetime.now().strftime("%Y-%m-%d")
    sanitized_title = _sanitize_title(title)
    folder_name = f"{date_str}_{sanitized_title}"

    # Create roadmap folder
    roadmaps_dir = agent_root / "agent" / "public" / "roadmaps"
    roadmaps_dir.mkdir(parents=True, exist_ok=True)

    folder_path = roadmaps_dir / folder_name
    folder_path.mkdir(exist_ok=True)

    # Create roadmap.md skeleton
    roadmap_file = folder_path / "roadmap.md"
    ca_path_relative = str(roadmap_file.relative_to(agent_root))

    roadmap_content = f"""# DETOUR: {title}

**Date**: {datetime.now().strftime("%Y-%m-%d")}
**Breadcrumb**: {breadcrumb}
**Status**: DRAFT

---

## Purpose

{{Describe detour objectives here}}

---

## Completion Criteria

- [ ] Criterion 1
- [ ] Criterion 2

---

## Return Conditions

{{Define when to return to main mission}}
"""

    roadmap_file.write_text(roadmap_content)

    # Default parent_id to sentinel if not specified
    effective_parent_id = parent_id if parent_id else SENTINEL_TASK_ID

    # Create MTMD with title for recomposition
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="DETOUR",
        title=title,
        parent_id=effective_parent_id,
        plan_ca_ref=ca_path_relative,
        repo=repo,
        target_version=version
    )

    # Build description with MTMD
    description = f"→ {ca_path_relative}\n\n{_generate_mtmd_block(mtmd)}"

    # Compose subject with proper ANSI nesting
    subject = compose_subject(str(task_id), "DETOUR", title)

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        folder_path=str(folder_path.relative_to(agent_root)),
        ca_path=ca_path_relative,
        mtmd=mtmd
    )


def create_phase(
    parent_id: int,
    title: str,
    plan: Optional[str] = None,
    plan_ca_ref: Optional[str] = None,
    blocked_by: Optional[List[str]] = None
) -> CreateResult:
    """
    Create phase task under parent.

    Creates:
    - Task JSON file with MTMD (includes parent_id)
    - Subject with 📋 if has subplan, - if not

    Args:
        parent_id: Parent task ID
        title: Phase title (e.g., "Phase 1: Setup")
        plan: Inline plan description (XOR with plan_ca_ref)
        plan_ca_ref: Path to subplan CA (XOR with plan, affects marker: 📋 vs -)

    Returns:
        CreateResult with task_id and mtmd
    """
    validate_plan_ca_ref(plan_ca_ref)
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Create MTMD with parent_id, title, and plan (XOR)
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="PHASE",
        title=title,
        parent_id=parent_id,
        plan=plan,
        plan_ca_ref=plan_ca_ref
    )

    # Build description with MTMD only (plan_ca_ref is in MTMD, not displayed separately)
    description = _generate_mtmd_block(mtmd)

    # Compose subject with proper ANSI nesting
    # PHASE uses 📋 if has subplan, - if not
    subject = compose_subject(str(task_id), "PHASE", title,
                              parent_id=str(parent_id), plan_ca_ref=plan_ca_ref)

    # Create task file
    _create_task_file(task_id, subject, description, blocked_by=blocked_by)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        ca_path=plan_ca_ref,
        mtmd=mtmd
    )


def create_bug(
    title: str,
    parent_id: Optional[str] = None,
    plan: Optional[str] = None,
    plan_ca_ref: Optional[str] = None
) -> CreateResult:
    """
    Create bug task (standalone or under parent).

    Creates:
    - Task JSON file with MTMD (includes parent_id if provided)
    - Subject with 🐛 BUG: prefix

    Args:
        title: Bug title (e.g., "Fix validation error")
        parent_id: Optional parent task ID (string to support "000" etc.)
        plan: Inline fix description for simple bugs (XOR with plan_ca_ref)
        plan_ca_ref: Path to BUG_FIX roadmap CA for complex bugs (XOR with plan)

    Returns:
        CreateResult with task_id and mtmd

    Raises:
        ValueError: If neither or both of plan and plan_ca_ref are provided
    """
    validate_plan_ca_ref(plan_ca_ref)
    # Enforce XOR: exactly one of plan or plan_ca_ref required
    if bool(plan) == bool(plan_ca_ref):
        raise ValueError("BUG task requires exactly one of plan or plan_ca_ref (XOR)")

    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Default parent_id to sentinel if not specified
    effective_parent_id = parent_id if parent_id else SENTINEL_TASK_ID

    # Create MTMD with title and fix tracking
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="BUG",
        title=title,
        parent_id=effective_parent_id,
        plan=plan,
        plan_ca_ref=plan_ca_ref
    )

    # Build description with MTMD
    description = _generate_mtmd_block(mtmd)

    # Compose subject with proper ANSI nesting
    subject = compose_subject(str(task_id), "BUG", title, parent_id=effective_parent_id)

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        mtmd=mtmd
    )


def create_gh_issue(
    issue_url: str,
    parent_id: Optional[str] = None,
) -> CreateResult:
    """
    Create GH_ISSUE task by auto-fetching metadata from GitHub.

    Parses issue URL, calls `gh issue view --json` to fetch title, labels, state,
    and creates a task with rich GitHub metadata in custom fields.

    Args:
        issue_url: GitHub issue URL (https://github.com/owner/repo/issues/N)
        parent_id: Optional parent task ID

    Returns:
        CreateResult with task_id and mtmd

    Raises:
        ValueError: If URL can't be parsed or gh CLI fails
    """
    import subprocess as _subprocess

    # Parse URL: https://github.com/owner/repo/issues/N
    url_match = re.match(r'https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)', issue_url)
    if not url_match:
        raise ValueError(f"Cannot parse GitHub issue URL: {issue_url}\n"
                         f"Expected: https://github.com/owner/repo/issues/N")
    owner, repo, issue_number = url_match.group(1), url_match.group(2), int(url_match.group(3))

    # Fetch issue metadata via gh CLI
    gh_result = _subprocess.run(
        ["gh", "issue", "view", str(issue_number),
         "--repo", f"{owner}/{repo}",
         "--json", "title,labels,state,url"],
        capture_output=True, text=True, timeout=15
    )
    if gh_result.returncode != 0:
        raise ValueError(f"gh issue view failed: {gh_result.stderr.strip()}")

    import json as _json
    gh_data = _json.loads(gh_result.stdout)
    title = gh_data["title"]
    labels = [label["name"] for label in gh_data.get("labels", [])]
    state = gh_data.get("state", "OPEN")
    url = gh_data.get("url", issue_url)

    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    task_id = _get_next_task_id()
    effective_parent_id = parent_id if parent_id else SENTINEL_TASK_ID

    # GitHub metadata stored in custom fields
    custom = {
        "gh_owner": owner,
        "gh_repo": repo,
        "gh_issue_number": issue_number,
        "gh_labels": labels,
        "gh_state": state,
        "gh_url": url,
    }

    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="GH_ISSUE",
        title=title,
        parent_id=effective_parent_id,
        plan_ca_ref=issue_url,
        custom=custom,
    )

    description = _generate_mtmd_block(mtmd)

    subject = compose_subject(
        str(task_id), "GH_ISSUE", title,
        parent_id=effective_parent_id, custom=custom
    )

    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        mtmd=mtmd
    )


def create_deleg(
    title: str,
    parent_id: Optional[str] = None,
    plan: Optional[str] = None,
    plan_ca_ref: Optional[str] = None
) -> CreateResult:
    """
    Create DELEG_PLAN task for delegation work.

    Args:
        title: Delegation title
        parent_id: Optional parent task ID (usually a MISSION or DETOUR)
        plan: Inline delegation plan (simple delegations) - XOR with plan_ca_ref
        plan_ca_ref: Path to deleg_plan.md CA (complex delegations) - XOR with plan

    Returns:
        CreateResult with task_id and mtmd

    Raises:
        ValueError: If neither or both of plan and plan_ca_ref are provided
    """
    validate_plan_ca_ref(plan_ca_ref)
    # Enforce XOR: exactly one of plan or plan_ca_ref required
    if bool(plan) == bool(plan_ca_ref):
        raise ValueError("DELEG_PLAN task requires exactly one of plan or plan_ca_ref (XOR)")

    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Default parent_id to sentinel if not specified
    effective_parent_id = parent_id if parent_id else SENTINEL_TASK_ID

    # Create MTMD
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="DELEG_PLAN",
        title=title,
        parent_id=effective_parent_id,
        plan=plan,
        plan_ca_ref=plan_ca_ref
    )

    # Build description with MTMD
    description = _generate_mtmd_block(mtmd)

    # Compose subject with proper ANSI nesting
    subject = compose_subject(str(task_id), "DELEG_PLAN", title, parent_id=effective_parent_id)

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        mtmd=mtmd
    )


def create_task(
    title: str,
    parent_id: Optional[str] = None,
    plan: Optional[str] = None,
    plan_ca_ref: Optional[str] = None
) -> CreateResult:
    """
    Create standalone TASK for general work.

    Creates:
    - Task JSON file with MTMD (parent_id defaults to sentinel)
    - Subject with 🔧 marker

    Args:
        title: Task title (e.g., "Fix urgent CEP alignment issue")
        parent_id: Optional parent task ID (string to support "000" etc.)
        plan: Inline plan description (XOR with plan_ca_ref)
        plan_ca_ref: Path to plan CA (XOR with plan)

    Returns:
        CreateResult with task_id and mtmd
    """
    validate_plan_ca_ref(plan_ca_ref)
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Default parent_id to sentinel if not specified
    effective_parent_id = parent_id if parent_id else SENTINEL_TASK_ID

    # Create MTMD with title and task_type
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        task_type="TASK",
        title=title,
        parent_id=effective_parent_id,
        plan=plan,
        plan_ca_ref=plan_ca_ref
    )

    # Build description with MTMD
    description = _generate_mtmd_block(mtmd)

    # Compose subject using proper ANSI nesting
    subject = compose_subject(str(task_id), "TASK", title)

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        mtmd=mtmd
    )


# Backwards compatibility alias (deprecated)
create_adhoc = create_task
