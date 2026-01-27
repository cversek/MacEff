"""
Task creation module with MTMD generation and smart defaults.

Provides functions to create MISSION, EXPERIMENT, DETOUR, PHASE, and BUG tasks
with automatic metadata population and skeleton CA file generation.
"""

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import MacfTaskMetaData
from .reader import TaskReader


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


def _get_agent_root() -> Path:
    """Get agent root directory from MACF_AGENT_ROOT or detect from cwd."""
    env_root = os.environ.get("MACF_AGENT_ROOT")
    if env_root:
        return Path(env_root)

    # Detect from cwd - look for agent/ directory
    cwd = Path.cwd()
    if (cwd / "agent").exists():
        return cwd

    # Check parent directories
    for parent in cwd.parents:
        if (parent / "agent").exists():
            return parent

    # Default to cwd
    return cwd


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
    session_uuid: Optional[str] = None
) -> Path:
    """Create task JSON file directly."""
    reader = TaskReader(session_uuid)

    if not reader.session_path:
        raise RuntimeError("Could not determine session path")

    # Ensure session directory exists
    reader.session_path.mkdir(parents=True, exist_ok=True)

    task_file = reader.session_path / f"{task_id}.json"

    # Build task JSON structure
    # Generate activeForm from subject (present continuous form)
    # Strip emoji prefix and convert to gerund-style
    active_form = subject
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
        "blockedBy": []
    }

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
        repo: Optional repository name (e.g., "MacEff")
        version: Optional target version (e.g., "0.4.0")
        agent_root: Optional agent root path (auto-detect if None)

    Returns:
        CreateResult with task_id, folder_path, ca_path, and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get agent root
    if agent_root is None:
        agent_root = _get_agent_root()

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

    # Create MTMD
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        plan_ca_ref=ca_path_relative,
        repo=repo,
        target_version=version
    )

    # Build description with MTMD
    description = f"→ {ca_path_relative}\n\n{_generate_mtmd_block(mtmd)}"

    # Create subject with emoji
    subject = f"🗺️ MISSION: {title}"

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
        agent_root: Optional agent root path (auto-detect if None)

    Returns:
        CreateResult with task_id, folder_path, ca_path, and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get agent root
    if agent_root is None:
        agent_root = _get_agent_root()

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

    # Create MTMD
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        plan_ca_ref=ca_path_relative
    )

    # Build description with MTMD
    description = f"→ {ca_path_relative}\n\n{_generate_mtmd_block(mtmd)}"

    # Create subject with emoji
    subject = f"🧪 EXPERIMENT: {title}"

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
        repo: Optional repository name
        version: Optional target version
        agent_root: Optional agent root path (auto-detect if None)

    Returns:
        CreateResult with task_id, folder_path, ca_path, and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get agent root
    if agent_root is None:
        agent_root = _get_agent_root()

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

    # Create MTMD
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        plan_ca_ref=ca_path_relative,
        repo=repo,
        target_version=version
    )

    # Build description with MTMD
    description = f"→ {ca_path_relative}\n\n{_generate_mtmd_block(mtmd)}"

    # Create subject with emoji
    subject = f"↩️ DETOUR: {title}"

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
    title: str
) -> CreateResult:
    """
    Create phase task under parent.

    Creates:
    - Task JSON file with MTMD (includes parent_id)
    - Subject prefixed with [^#N] parent reference

    Args:
        parent_id: Parent task ID
        title: Phase title (e.g., "Phase 1: Setup")

    Returns:
        CreateResult with task_id and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Create MTMD with parent_id
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        parent_id=parent_id
    )

    # Build description with MTMD
    description = _generate_mtmd_block(mtmd)

    # Create subject with parent reference and emoji
    subject = f"[^#{parent_id}] 📋 {title}"

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        mtmd=mtmd
    )


def create_bug(
    parent_id: int,
    title: str
) -> CreateResult:
    """
    Create bug task under parent.

    Creates:
    - Task JSON file with MTMD (includes parent_id)
    - Subject prefixed with [^#N] parent reference and 🐛 emoji

    Args:
        parent_id: Parent task ID
        title: Bug title (e.g., "Fix validation error")

    Returns:
        CreateResult with task_id and mtmd
    """
    from ..utils.breadcrumbs import get_breadcrumb, parse_breadcrumb

    # Get breadcrumb and parse cycle
    breadcrumb = get_breadcrumb()
    parsed = parse_breadcrumb(breadcrumb)
    cycle = parsed['cycle'] if parsed else 1

    # Get next task ID
    task_id = _get_next_task_id()

    # Create MTMD with parent_id
    mtmd = MacfTaskMetaData(
        version="1.0",
        creation_breadcrumb=breadcrumb,
        created_cycle=cycle,
        created_by="PA",
        parent_id=parent_id
    )

    # Build description with MTMD
    description = _generate_mtmd_block(mtmd)

    # Create subject with parent reference and bug emoji
    subject = f"[^#{parent_id}] 🐛 BUG: {title}"

    # Create task file
    _create_task_file(task_id, subject, description)

    return CreateResult(
        task_id=task_id,
        subject=subject,
        mtmd=mtmd
    )
