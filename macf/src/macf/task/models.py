"""
Task models with MacfTaskMetaData (MTMD) parsing.

MTMD is embedded in task descriptions within <macf_task_metadata> tags.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
import re
import yaml


@dataclass
class MacfTaskUpdate:
    """
    Record of a significant task update.

    Captures both the breadcrumb (when) and description (what) of each update.
    Extensible for future fields like agent, timestamp, etc.
    """
    breadcrumb: str
    description: str = ""

    # Future extensibility
    agent: Optional[str] = None  # Who made the update (PA, SA:DevOpsEng, etc.)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MacfTaskUpdate":
        """Create from dict (YAML parsing)."""
        if isinstance(data, str):
            # Legacy format: just a breadcrumb string
            return cls(breadcrumb=data)
        return cls(
            breadcrumb=data.get("breadcrumb", ""),
            description=data.get("description", ""),
            agent=data.get("agent"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for YAML."""
        result = {"breadcrumb": self.breadcrumb}
        if self.description:
            result["description"] = self.description
        if self.agent:
            result["agent"] = self.agent
        return result


@dataclass
class MacfTaskMetaData:
    """
    MacEff Task Metadata (MTMD) schema v1.0.

    Embedded in task descriptions within <macf_task_metadata version="1.0"> tags.
    Provides hierarchy, version tracking, and lifecycle breadcrumbs.
    """
    # Schema version
    version: str = "1.0"

    # Required for ALL tasks
    creation_breadcrumb: Optional[str] = None
    created_cycle: Optional[int] = None
    created_by: Optional[str] = None  # PA | SA:{agent_type}

    # Task type - AUTHORITATIVE source (takes precedence over subject line emoji parsing)
    # Valid values: MISSION, EXPERIMENT, DETOUR, DELEG_PLAN, SUBPLAN, ARCHIVE, AD_HOC, BUG
    # See task_management.md §2.1 for definitions
    task_type: Optional[str] = None

    # Required for MISSION/DETOUR/EXPERIMENT/DELEG_PLAN/SUBPLAN
    plan_ca_ref: Optional[str] = None

    # Optional - set on conversion from experiment
    experiment_ca_ref: Optional[str] = None

    # Optional - hierarchy
    parent_id: Optional[int] = None

    # Optional - version association
    repo: Optional[str] = None
    target_version: Optional[str] = None
    release_branch: Optional[str] = None

    # Lifecycle breadcrumbs
    completion_breadcrumb: Optional[str] = None
    completion_report: Optional[str] = None  # Brief report on completion (difficulties, future work)
    unblock_breadcrumb: Optional[str] = None
    updates: List[MacfTaskUpdate] = field(default_factory=list)  # Ordered list of updates

    # Optional - archive state
    archived: bool = False
    archived_at: Optional[str] = None

    # Optional - custom fields
    custom: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, description: str) -> Optional["MacfTaskMetaData"]:
        """
        Parse MacfTaskMetaData from task description.

        Extracts content between <macf_task_metadata> tags and parses as YAML.
        Returns None if no MTMD block found.
        """
        # Match <macf_task_metadata version="1.0">...</macf_task_metadata>
        pattern = r'<macf_task_metadata[^>]*>(.*?)</macf_task_metadata>'
        match = re.search(pattern, description, re.DOTALL)

        if not match:
            return None

        yaml_content = match.group(1).strip()

        try:
            data = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError:
            return None

        # Extract version from tag if present
        version_match = re.search(r'version=["\']([^"\']+)["\']', match.group(0))
        version = version_match.group(1) if version_match else "1.0"

        # Parse updates list
        updates = []
        if "updates" in data and isinstance(data["updates"], list):
            # New format: updates: [{breadcrumb: "...", description: "..."}, ...]
            updates = [MacfTaskUpdate.from_dict(u) for u in data["updates"]]
        else:
            # Legacy format: update1_breadcrumb, update2_breadcrumb, etc.
            legacy_updates = {}
            for key, value in data.items():
                match_update = re.match(r'update(\d+)_breadcrumb', key)
                if match_update and value:
                    legacy_updates[int(match_update.group(1))] = value
            # Convert to ordered list
            for idx in sorted(legacy_updates.keys()):
                updates.append(MacfTaskUpdate(breadcrumb=legacy_updates[idx]))

        return cls(
            version=version,
            creation_breadcrumb=data.get("creation_breadcrumb"),
            created_cycle=data.get("created_cycle"),
            created_by=data.get("created_by"),
            task_type=data.get("task_type"),
            plan_ca_ref=data.get("plan_ca_ref"),
            experiment_ca_ref=data.get("experiment_ca_ref"),
            parent_id=data.get("parent_id"),
            repo=data.get("repo"),
            target_version=data.get("target_version"),
            release_branch=data.get("release_branch"),
            completion_breadcrumb=data.get("completion_breadcrumb"),
            completion_report=data.get("completion_report"),
            unblock_breadcrumb=data.get("unblock_breadcrumb"),
            updates=updates,
            archived=data.get("archived", False),
            archived_at=data.get("archived_at"),
            custom=data.get("custom", {}),
        )

    def with_updated_field(self, field: str, value: Any, breadcrumb: str, description: str = "") -> "MacfTaskMetaData":
        """
        Return new MTMD with field updated and update record added.

        Args:
            field: Field name to update
            value: New value for field
            breadcrumb: Current breadcrumb for tracking
            description: Description of the update

        Returns:
            New MacfTaskMetaData instance with updated field and update record
        """
        import copy
        # Create a copy of current state
        new_mtmd = copy.deepcopy(self)

        # Update the field
        if hasattr(new_mtmd, field):
            setattr(new_mtmd, field, value)

        # Add update record
        update_desc = description or f"Set {field} = {value}"
        new_mtmd.updates.append(MacfTaskUpdate(
            breadcrumb=breadcrumb,
            description=update_desc,
            agent="PA"
        ))

        return new_mtmd

    def with_custom_field(self, key: str, value: Any, breadcrumb: str) -> "MacfTaskMetaData":
        """
        Return new MTMD with custom field added and update record.

        Args:
            key: Custom field key
            value: Custom field value
            breadcrumb: Current breadcrumb for tracking

        Returns:
            New MacfTaskMetaData instance with custom field added
        """
        import copy
        new_mtmd = copy.deepcopy(self)

        # Add to custom dict
        new_mtmd.custom[key] = value

        # Add update record
        new_mtmd.updates.append(MacfTaskUpdate(
            breadcrumb=breadcrumb,
            description=f"Added custom.{key} = {value}",
            agent="PA"
        ))

        return new_mtmd

    def to_yaml(self) -> str:
        """Serialize to YAML for embedding in description."""
        data = {}

        # Only include non-None/non-default values
        if self.creation_breadcrumb:
            data["creation_breadcrumb"] = self.creation_breadcrumb
        if self.created_cycle is not None:
            data["created_cycle"] = self.created_cycle
        if self.created_by:
            data["created_by"] = self.created_by
        if self.task_type:
            data["task_type"] = self.task_type
        if self.plan_ca_ref:
            data["plan_ca_ref"] = self.plan_ca_ref
        if self.experiment_ca_ref:
            data["experiment_ca_ref"] = self.experiment_ca_ref
        if self.parent_id is not None:
            data["parent_id"] = self.parent_id
        if self.repo:
            data["repo"] = self.repo
        if self.target_version:
            data["target_version"] = self.target_version
        if self.release_branch:
            data["release_branch"] = self.release_branch
        if self.completion_breadcrumb:
            data["completion_breadcrumb"] = self.completion_breadcrumb
        if self.unblock_breadcrumb:
            data["unblock_breadcrumb"] = self.unblock_breadcrumb
        if self.updates:
            data["updates"] = [u.to_dict() for u in self.updates]
        if self.archived:
            data["archived"] = self.archived
        if self.archived_at:
            data["archived_at"] = self.archived_at
        if self.custom:
            data["custom"] = self.custom

        return yaml.dump(data, default_flow_style=False, sort_keys=False)


@dataclass
class MacfTask:
    """
    Representation of a Claude Code native task with MTMD support.

    Combines CC native fields with parsed MacfTaskMetaData.
    """
    # CC Native fields
    id: Union[int, str]  # String IDs like "000" for system tasks
    subject: str
    description: str
    status: str  # pending, in_progress, completed

    # CC Native dependency tracking
    blocks: List[int] = field(default_factory=list)
    blocked_by: List[int] = field(default_factory=list)

    # Parsed MTMD (None if no MTMD block in description)
    mtmd: Optional[MacfTaskMetaData] = None

    # Computed hierarchy fields (from subject line parsing)
    parent_ref: Optional[int] = None  # Extracted from [^#N] prefix
    task_type: Optional[str] = None   # MISSION, EXPERIMENT, DETOUR, PHASE, or None

    # Source tracking
    session_uuid: Optional[str] = None
    file_path: Optional[str] = None

    @classmethod
    def from_json(cls, data: Dict[str, Any], session_uuid: str = None, file_path: str = None) -> "MacfTask":
        """
        Create MacfTask from CC native JSON structure.

        Parses MTMD from description and extracts hierarchy from subject.
        """
        # Parse task_id - preserve string IDs with leading zeros (like "000")
        raw_id = str(data.get("id", "0"))
        if raw_id.startswith('0') and len(raw_id) > 1:
            task_id = raw_id  # Preserve as string (e.g., "000")
        else:
            task_id = int(raw_id)  # Convert to int for normal IDs
        subject = data.get("subject", "")
        description = data.get("description", "")
        status = data.get("status", "pending")

        # Parse blocks/blockedBy
        blocks = data.get("blocks", [])
        blocked_by = data.get("blockedBy", [])

        # Parse MTMD from description
        mtmd = MacfTaskMetaData.parse(description)

        # Extract parent reference from subject [^#N]
        parent_ref = None
        parent_match = re.search(r'\[\^#(\d+)\]', subject)
        if parent_match:
            parent_ref = int(parent_match.group(1))

        # Detect task type from emoji prefix
        task_type = None
        if "🗺️" in subject:
            task_type = "MISSION"
        elif "🧪" in subject:
            task_type = "EXPERIMENT"
        elif "↩️" in subject:
            task_type = "DETOUR"
        elif "📋" in subject:
            task_type = "PHASE"

        return cls(
            id=task_id,
            subject=subject,
            description=description,
            status=status,
            blocks=blocks,
            blocked_by=blocked_by,
            mtmd=mtmd,
            parent_ref=parent_ref,
            task_type=task_type,
            session_uuid=session_uuid,
            file_path=file_path,
        )

    @property
    def parent_id(self) -> Optional[int]:
        """
        Get parent ID from either MTMD or subject prefix.

        MTMD parent_id takes precedence if present.
        """
        if self.mtmd and self.mtmd.parent_id is not None:
            return self.mtmd.parent_id
        return self.parent_ref

    @property
    def status_emoji(self) -> str:
        """Status indicator emoji."""
        if self.status == "completed":
            return "✅"
        elif self.status == "in_progress":
            return "🔄"
        else:
            return "⏳"

    @property
    def type_emoji(self) -> str:
        """Type indicator emoji (or empty if regular task)."""
        emoji_map = {
            "MISSION": "🗺️",
            "EXPERIMENT": "🧪",
            "DETOUR": "↩️",
            "PHASE": "📋",
        }
        return emoji_map.get(self.task_type, "")

    def description_without_mtmd(self) -> str:
        """Return description with MTMD block removed."""
        pattern = r'<macf_task_metadata[^>]*>.*?</macf_task_metadata>'
        return re.sub(pattern, '', self.description, flags=re.DOTALL).strip()

    def description_with_updated_mtmd(self, new_mtmd: "MacfTaskMetaData") -> str:
        """
        Return description with MTMD block replaced/added.

        Args:
            new_mtmd: New MacfTaskMetaData to embed

        Returns:
            Description with updated MTMD block
        """
        # Get description without existing MTMD
        base_desc = self.description_without_mtmd()

        # Build new MTMD block
        mtmd_block = f'<macf_task_metadata version="{new_mtmd.version}">\n{new_mtmd.to_yaml()}</macf_task_metadata>'

        # Append MTMD to description
        if base_desc:
            return f"{base_desc}\n\n{mtmd_block}"
        else:
            return mtmd_block
