"""
MACF Utilities - Modular package structure.
"""

from .paths import (
    find_project_root,
    get_session_dir,
    get_hooks_dir,
    get_dev_scripts_dir,
    get_logs_dir,
    get_session_transcript_path,
)
from .session import (
    get_current_session_id,
    get_last_user_prompt_uuid,
    detect_session_migration,
)
from .json_io import (
    write_json_safely,
    read_json,
    get_agent_state_path,
)
from .artifacts import (
    get_latest_consciousness_artifacts,
    ConsciousnessArtifacts,
)
from .cycles import (
    detect_auto_mode,
)
from .drives import (
    start_dev_drv,
    complete_dev_drv,
    get_dev_drv_stats,
    start_deleg_drv,
    complete_deleg_drv,
    get_deleg_drv_stats,
    record_delegation_start,
    record_delegation_complete,
    get_delegations_this_drive,
    clear_delegations_this_drive,
)
from .temporal import (
    get_formatted_timestamp,
    get_temporal_context,
    format_duration,
    calculate_session_duration,
    format_temporal_awareness_section,
    get_minimal_timestamp,
    format_minimal_temporal_message,
)
from .environment import (
    detect_execution_environment,
    get_rich_environment_string,
)
from .breadcrumbs import (
    format_breadcrumb,
    parse_breadcrumb,
    extract_current_git_hash,
    get_breadcrumb,
)
from .tokens import (
    get_token_info,
    format_token_context_minimal,
    format_token_context_full,
    get_boundary_guidance,
    get_usable_context,
    CC2_TOTAL_CONTEXT,
)
from .claude_settings import (
    get_autocompact_setting,
)
from .manifest import (
    _deep_merge,
    load_merged_manifest,
    filter_active_policies,
    format_manifest_awareness,
    get_framework_policies_path,
    find_policy_file,
    list_policy_files,
)
from .formatting import (
    format_macf_footer,
    get_claude_code_version,
)

from .temporal import DATEUTIL_AVAILABLE

__all__ = [
    "CC2_TOTAL_CONTEXT",
    "ConsciousnessArtifacts",
    "DATEUTIL_AVAILABLE",
    "_deep_merge",
    "calculate_session_duration",
    "clear_delegations_this_drive",
    "complete_deleg_drv",
    "complete_dev_drv",
    "detect_auto_mode",
    "detect_execution_environment",
    "detect_session_migration",
    "extract_current_git_hash",
    "filter_active_policies",
    "find_policy_file",
    "find_project_root",
    "format_breadcrumb",
    "format_duration",
    "format_macf_footer",
    "get_claude_code_version",
    "format_manifest_awareness",
    "format_minimal_temporal_message",
    "get_framework_policies_path",
    "format_temporal_awareness_section",
    "format_token_context_full",
    "format_token_context_minimal",
    "get_agent_state_path",
    "get_autocompact_setting",
    "get_boundary_guidance",
    "get_breadcrumb",
    "get_current_session_id",
    "get_deleg_drv_stats",
    "get_delegations_this_drive",
    "get_dev_drv_stats",
    "get_dev_scripts_dir",
    "get_formatted_timestamp",
    "get_hooks_dir",
    "get_last_user_prompt_uuid",
    "get_latest_consciousness_artifacts",
    "get_logs_dir",
    "get_minimal_timestamp",
    "get_rich_environment_string",
    "get_session_dir",
    "get_session_transcript_path",
    "get_temporal_context",
    "get_token_info",
    "get_usable_context",
    "list_policy_files",
    "load_merged_manifest",
    "parse_breadcrumb",
    "read_json_safely",
    "record_delegation_complete",
    "record_delegation_start",
    "start_deleg_drv",
    "start_dev_drv",
    "write_json_safely",
]