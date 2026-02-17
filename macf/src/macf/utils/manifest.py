"""
Policy manifest merge/filter/format.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from .paths import find_maceff_root


def get_framework_policies_path(maceff_root: Optional[Path] = None) -> Optional[Path]:
    """
    Get the framework policies root path for container or host.

    Resolution Strategy:
        Container (/.dockerenv exists): /opt/maceff/framework/policies
        Host:
            1. Check if we're in MacEff repo itself: {maceff_root}/framework/policies
            2. Check for MacEff as submodule: {maceff_root}/MacEff/framework/policies
            3. Check MACEFF_FRAMEWORK_PATH env var: ${MACEFF_FRAMEWORK_PATH}/policies
            4. Check sibling directories (walk up from maceff root)

    Args:
        maceff_root: Optional MacEff installation root (auto-detected if None)

    Returns:
        Path to framework/policies directory (root, includes base/, tech/, lang/, recovery/)
    """
    # Container path
    if Path('/.dockerenv').exists():
        policies_root = Path('/opt/maceff/framework/policies')
        return policies_root if policies_root.exists() else None

    # Host path resolution
    if maceff_root is None:
        maceff_root = find_maceff_root()

    if maceff_root is None:
        return None

    maceff_root = Path(maceff_root)

    # Strategy 1: Check if we're in MacEff repo itself
    candidate = maceff_root / 'framework' / 'policies'
    if candidate.exists():
        return candidate

    # Strategy 2: Check for MacEff as submodule
    candidate = maceff_root / 'MacEff' / 'framework' / 'policies'
    if candidate.exists():
        return candidate

    # Strategy 3: Check environment variable
    if 'MACEFF_FRAMEWORK_PATH' in os.environ:
        candidate = Path(os.environ['MACEFF_FRAMEWORK_PATH']) / 'policies'
        if candidate.exists():
            return candidate

    # Strategy 4: Check sibling MacEff repos (walk up directory tree)
    for parent in [maceff_root.parent, maceff_root.parent.parent]:
        if parent.exists():
            for candidate in parent.glob("*/MacEff/framework/policies"):
                if candidate.exists():
                    return candidate

    return None


def find_policy_file(
    policy_name: str,
    parents: Optional[List[str]] = None,
    maceff_root: Optional[Path] = None
) -> Optional[Path]:
    """
    Find policy file by name, walking the framework policies tree.

    Args:
        policy_name: Policy filename (with or without .md extension)
                    e.g., 'todo_hygiene', 'todo_hygiene.md'
        parents: Optional list of parent directory names to match
                e.g., ['development'] to find development/todo_hygiene.md
        maceff_root: Optional MacEff installation root (auto-detected if None)

    Returns:
        Path to policy file, or None if not found

    Examples:
        find_policy_file('todo_hygiene')
            → .../framework/policies/base/development/todo_hygiene.md

        find_policy_file('todo_hygiene', parents=['development'])
            → .../framework/policies/base/development/todo_hygiene.md

        find_policy_file('checkpoints', parents=['consciousness'])
            → .../framework/policies/base/consciousness/checkpoints.md
    """
    base_path = get_framework_policies_path(maceff_root)
    if not base_path:
        return None

    # Normalize: ensure .md extension
    name = policy_name if policy_name.endswith('.md') else f"{policy_name}.md"

    # Walk the tree looking for matching files
    for md_file in base_path.rglob('*.md'):
        if md_file.name == name:
            # If parents specified, check path contains them
            if parents:
                rel_path = md_file.relative_to(base_path)
                path_parts = rel_path.parts[:-1]  # Exclude filename
                # Check all parent requirements are in path
                if all(p in path_parts for p in parents):
                    return md_file
            else:
                return md_file

    return None


def list_policy_files(
    tier: Optional[str] = None,
    category: Optional[str] = None,
    maceff_root: Optional[Path] = None,
    include_tier: bool = False
) -> List[Dict[str, Any]]:
    """
    List all policy files with optional filtering.

    Args:
        tier: Filter by tier (CORE, optional) - reads from file metadata
        category: Filter by subdirectory (development, consciousness, meta)
        maceff_root: Optional MacEff installation root (auto-detected if None)
        include_tier: If True, read tier info for all policies (for display)

    Returns:
        List of dicts with keys: name, path, relative_path, category, tier
    """
    base_path = get_framework_policies_path(maceff_root)
    if not base_path:
        return []

    policies = []
    for md_file in base_path.rglob('*.md'):
        rel_path = md_file.relative_to(base_path)
        path_parts = rel_path.parts

        # Determine category from path (full parent path for nested dirs)
        file_category = str(rel_path.parent) if len(path_parts) > 1 else 'root'

        # Apply category filter (prefix match for nested categories)
        if category and not file_category.startswith(category):
            continue

        # Read tier from file if filtering by tier OR include_tier requested
        file_tier = None
        if tier or include_tier:
            try:
                content = md_file.read_text()
                # Look for **Tier**: CORE or similar in first 500 chars
                for line in content[:500].split('\n'):
                    if 'Tier' in line and ':' in line:
                        file_tier = line.split(':')[1].strip().upper()
                        break
            except Exception as e:
                print(f"⚠️ MACF: Policy tier parse failed ({md_file.name}): {e}", file=sys.stderr)

            # Only filter if tier argument was provided
            if tier and file_tier != tier.upper():
                continue

        policies.append({
            'name': md_file.stem,
            'path': str(md_file),
            'relative_path': str(rel_path),
            'category': file_category,
            'tier': file_tier
        })

    return sorted(policies, key=lambda p: p['relative_path'])


def _deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """
    Recursively merge overlay dict into base dict.

    Merge strategy:
    - Lists: Append overlay items to base (combine both)
    - Scalars: Overlay overrides base (project wins)
    - Nested dicts: Recurse to merge deeply

    Args:
        base: Base dictionary (framework defaults)
        overlay: Overlay dictionary (project customizations)

    Returns:
        Merged dictionary with overlay taking precedence
    """
    result = base.copy()

    for key, overlay_val in overlay.items():
        if key in result:
            base_val = result[key]

            # Lists: Append (combine both)
            if isinstance(base_val, list) and isinstance(overlay_val, list):
                result[key] = base_val + overlay_val

            # Nested dicts: Recurse
            elif isinstance(base_val, dict) and isinstance(overlay_val, dict):
                result[key] = _deep_merge(base_val, overlay_val)

            # Scalars: Override
            else:
                result[key] = overlay_val
        else:
            # New key from overlay
            result[key] = overlay_val

    return result

def load_merged_manifest(maceff_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Load and merge manifest.json from framework base + project overlay.

    2-Layer Architecture:
    1. Framework base: MacEff/framework/policies/manifest.json (always present)
    2. Project overlay: {cwd}/.maceff/policies/manifest.json (optional)

    Personal layer deferred - stub with comment showing future 3rd layer.

    Merge Strategy:
    - Lists: Append project items to base (e.g., custom_policies)
    - Scalars: Project overrides base (e.g., active_layers)
    - Deep merge: Recursively merge nested dicts

    Args:
        maceff_root: Optional MacEff installation root (auto-detect if None via find_maceff_root())

    Returns:
        Merged manifest dict (base + project overlay)
        Falls back to base-only if project manifest missing/malformed

    Example:
        manifest = load_merged_manifest()
        active_cas = manifest.get('active_consciousness', [])
    """
    # Detect framework base path (container vs host)
    if Path('/.dockerenv').exists():
        # Container path
        base_path = Path('/opt/maceff/framework/policies/manifest.json')
    else:
        # Host path - try multiple strategies
        if maceff_root is None:
            maceff_root = find_maceff_root()
        else:
            maceff_root = Path(maceff_root)

        # Strategy 1: Check if we're in MacEff repo itself
        if (maceff_root / 'framework' / 'policies' / 'manifest.json').exists():
            base_path = maceff_root / 'framework' / 'policies' / 'manifest.json'
        # Strategy 2: Check for MacEff as submodule
        elif (maceff_root / 'MacEff' / 'framework' / 'policies' / 'manifest.json').exists():
            base_path = maceff_root / 'MacEff' / 'framework' / 'policies' / 'manifest.json'
        # Strategy 3: Check environment variable
        elif 'MACEFF_FRAMEWORK_PATH' in os.environ:
            base_path = Path(os.environ['MACEFF_FRAMEWORK_PATH']) / 'policies' / 'manifest.json'
        # Strategy 4: Check sibling MacEff repos (walk up directory tree)
        else:
            found = False
            for parent in [maceff_root.parent, maceff_root.parent.parent]:
                if parent.exists():
                    for candidate in parent.glob("*/MacEff/framework/policies/manifest.json"):
                        if candidate.exists():
                            base_path = candidate
                            found = True
                            break
                if found:
                    break
            if not found:
                # Fallback: assume submodule (will fail with warning below)
                base_path = maceff_root / 'MacEff' / 'framework' / 'policies' / 'manifest.json'

    # Load framework base (always required)
    manifest = {}
    try:
        with open(base_path) as f:
            manifest = json.load(f)
    except Exception as e:
        # Log warning but don't crash - return empty dict
        print(f"WARNING: Failed to load base manifest from {base_path}: {e}", file=sys.stderr)
        return {}

    # Discover project overlay path (cwd first, then maceff_root)
    project_manifest_path = Path.cwd() / '.maceff' / 'policies' / 'manifest.json'

    if not project_manifest_path.exists() and maceff_root:
        project_manifest_path = maceff_root / '.maceff' / 'policies' / 'manifest.json'

    # Load and merge project overlay (optional)
    if project_manifest_path.exists():
        try:
            with open(project_manifest_path) as f:
                project_overlay = json.load(f)

            # Deep merge overlay into base
            manifest = _deep_merge(manifest, project_overlay)
        except Exception as e:
            # Log warning but continue with base-only
            print(
                f"WARNING: Failed to load project manifest from {project_manifest_path}, using base only: {e}",
                file=sys.stderr
            )

    # TODO: Personal layer deferred until Framework+Project validated
    # Future: Load ~/.maceff/policies/manifest.json as 3rd layer
    # Merge order: Framework → Project → Personal (highest precedence)

    return manifest

def get_policies_for_task_type(task_type: str, manifest: Optional[Dict[str, Any]] = None) -> list:
    """
    Look up policies to auto-inject for a given task type.

    Reads task_type_policies.mappings from manifest.json.

    Args:
        task_type: Task type string (e.g., "MISSION", "EXPERIMENT", "BUG")
        manifest: Pre-loaded manifest dict, or None to load fresh

    Returns:
        List of policy name strings to inject, or empty list if no mapping
    """
    if manifest is None:
        manifest = load_merged_manifest()

    task_type_policies = manifest.get("task_type_policies")
    if task_type_policies is None:
        print("[manifest] ⚠️ Missing 'task_type_policies' section", file=sys.stderr)
        return []

    mappings = task_type_policies.get("mappings")
    if mappings is None:
        print("[manifest] ⚠️ 'task_type_policies' missing 'mappings' key", file=sys.stderr)
        return []

    policies = mappings.get(task_type)
    if policies is None:
        print(f"[manifest] ⚠️ No mapping for task type '{task_type}'", file=sys.stderr)
        return []

    return policies


def filter_active_policies(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """
    Filter merged manifest to active policies only (token efficiency).

    Configuration Schema (project manifest .maceff/policies/manifest.json):
    ```json
    {
      "version": "1.0.0",
      "extends": "/opt/maceff/framework/policies/manifest.json",
      "active_layers": ["development"],
      "active_languages": ["python"],
      "active_consciousness": ["observations", "experiments", "reports"],
      "custom_policies": []
    }
    ```

    Filter Rules:
    1. Mandatory policies: Always included
    2. Development policies: Filtered by active_layers
    3. Language policies: Filtered by active_languages
    4. CA types in discovery_index: Filtered by active_consciousness
    5. Consciousness patterns: Always included
    6. Custom policies: Always included

    Args:
        manifest: Merged manifest from load_merged_manifest()

    Returns:
        Filtered manifest with only active policies
    """
    # If no filtering configured, return full manifest
    has_filters = (
        'active_layers' in manifest or
        'active_languages' in manifest or
        'active_consciousness' in manifest
    )

    if not has_filters:
        return manifest

    # Start filtered dict with always-included sections
    filtered = {
        'version': manifest.get('version'),
        'description': manifest.get('description'),
        'last_updated': manifest.get('last_updated'),
        'base_path': manifest.get('base_path'),
        'mandatory_policies': manifest.get('mandatory_policies', {}),
        'consciousness_patterns': manifest.get('consciousness_patterns', {}),
        'active_layers': manifest.get('active_layers', []),
        'active_languages': manifest.get('active_languages', []),
        'active_consciousness': manifest.get('active_consciousness', [])
    }

    # Filter by active_layers (development, production, etc.)
    active_layers = manifest.get('active_layers', [])
    if active_layers:
        # Check for development policies
        if 'development' in active_layers and 'development_policies' in manifest:
            filtered['development_policies'] = manifest['development_policies']

        # Future: production policies, staging policies, etc.
        if 'production' in active_layers and 'production_policies' in manifest:
            filtered['production_policies'] = manifest['production_policies']

    # Filter by active_languages (python, go, etc.)
    active_languages = manifest.get('active_languages', [])
    if active_languages and 'language_policies' in manifest:
        language_policies = {}
        lang_section = manifest['language_policies'].get('languages', {})

        for lang in active_languages:
            if lang in lang_section:
                language_policies[lang] = lang_section[lang]

        if language_policies:
            # Preserve structure with languages key
            filtered['language_policies'] = {
                'description': manifest['language_policies'].get('description'),
                'location': manifest['language_policies'].get('location'),
                'languages': language_policies
            }

    # Filter discovery_index by active_consciousness using explicit CA mapping
    active_ca_types = manifest.get('active_consciousness', [])
    if active_ca_types and 'discovery_index' in manifest and 'consciousness_artifacts' in manifest:
        discovery_index = manifest['discovery_index']
        ca_types = manifest['consciousness_artifacts'].get('types', {})

        # Collect all discovery_keys for active CA types
        active_discovery_keys = set()
        for ca_type in active_ca_types:
            if ca_type in ca_types:
                active_discovery_keys.update(ca_types[ca_type].get('discovery_keys', []))

        # Filter discovery_index to only active keys
        filtered_discovery = {k: v for k, v in discovery_index.items() if k in active_discovery_keys}

        if filtered_discovery:
            filtered['discovery_index'] = filtered_discovery

    # Always include custom_policies if present
    if 'custom_policies' in manifest:
        filtered['custom_policies'] = manifest['custom_policies']

    return filtered

def format_manifest_awareness() -> str:
    """
    Format directive manifest awareness for SessionStart hook injection.

    Transforms passive catalog into active enforcement protocol:
    - Emphasizes policies as project priorities (not suggestions)
    - "Policies persist, memory doesn't" reminder
    - Pattern-to-action mapping with immediate CLI commands
    - BEFORE ANY WORK directive for mandatory policies

    Used on: compaction recovery + brand new session
    Skipped on: session resume

    Returns:
        Plain text awareness message (<500 tokens, for <system-reminder> tags)
    """
    try:
        # Verify manifest exists (validates policy infrastructure)
        manifest = load_merged_manifest()
        if not manifest:
            return "📋 POLICY DISCOVERY\n\nManifest not found - run `macf_tools policy list` to check"

        # Policy Discovery Obsession: Minimal bootstrap, trust discovery infrastructure
        lines = [
            "📋 POLICY DISCOVERY",
            "",
            "⚠️ Policies persist across compaction. Your memory doesn't.",
            "",
            "🎯 FIRST COMMAND: `macf_tools policy list`",
            "",
            "Discovery flow: list → navigate → read",
            "",
            "Task System auto-surfaces CEP Nav Guides when you start work — scan questions, read sections you need",
        ]

        return "\n".join(lines)

    except Exception:
        # Graceful fallback - still point to discovery
        return "📋 POLICY DISCOVERY\n\nRun `macf_tools policy list` to discover policies"
