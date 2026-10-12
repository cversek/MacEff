"""
Policy manifest merge/filter/format.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from .paths import find_maceff_root

#: Extra policy roots, os.pathsep-separated, each ``path`` or ``name=path`` (#592). A package
#: that ships policy in MacEff's format is read where it lives, never copied into the
#: framework's tree (policy_awareness: where policies come from).
POLICY_ROOTS_ENV = "MACEFF_POLICY_ROOTS"

#: The framework root's name, for a qualified ``framework:<policy>``. No extra root may take it.
FRAMEWORK_ROOT_NAME = "framework"


@dataclass(frozen=True)
class PolicyRoot:
    name: str
    path: Path
    framework: bool = False


class PolicyAmbiguous(LookupError):
    """An unqualified policy name found in more than one extra root."""


_reported: set = set()


def _report_once(message: str) -> None:
    """A skipped root or a shadowed name is said once per process, not on every lookup."""
    if message not in _reported:
        _reported.add(message)
        print(f"⚠️ MACF: {message}", file=sys.stderr)


def extra_policy_roots(environ=None) -> List[PolicyRoot]:
    """The roots ``MACEFF_POLICY_ROOTS`` names, in order. An entry is ``path`` (named by its
    directory) or ``name=path``. A missing or unreadable root, a bad name and a repeated name
    are each reported once and left out, never skipped silently."""
    environ = os.environ if environ is None else environ
    roots: List[PolicyRoot] = []
    for entry in (e.strip() for e in environ.get(POLICY_ROOTS_ENV, "").split(os.pathsep)):
        if not entry:
            continue
        name, sep, raw = entry.partition("=")
        if not sep:
            name, raw = Path(entry).name, entry
        path = Path(raw).expanduser()
        if not name or any(c in name for c in "/:") or name == FRAMEWORK_ROOT_NAME:
            _report_once(f"policy root {entry!r} skipped: a root's name may not be empty, "
                         f"contain '/' or ':', or be {FRAMEWORK_ROOT_NAME!r} ({POLICY_ROOTS_ENV})")
            continue
        if any(r.name == name for r in roots):
            _report_once(f"policy root {entry!r} skipped: the name {name!r} is already taken "
                         f"by an earlier entry; give one a name=path ({POLICY_ROOTS_ENV})")
            continue
        if not path.is_dir():
            _report_once(f"policy root {name!r} skipped: {path} is not a directory ({POLICY_ROOTS_ENV})")
            continue
        if not os.access(path, os.R_OK | os.X_OK):
            _report_once(f"policy root {name!r} skipped: {path} is not readable by this user ({POLICY_ROOTS_ENV})")
            continue
        roots.append(PolicyRoot(name, path))
    return roots


def policy_roots(maceff_root: Optional[Path] = None) -> List[PolicyRoot]:
    """Every root policies are read from: the framework's first, then the extra roots."""
    roots = []
    framework = get_framework_policies_path(maceff_root)
    if framework:
        roots.append(PolicyRoot(FRAMEWORK_ROOT_NAME, framework, framework=True))
    return roots + extra_policy_roots()


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


def _find_in(root: Path, name: str, parents: Optional[List[str]]) -> Optional[Path]:
    for md_file in root.rglob('*.md'):
        if md_file.name == name:
            if parents:
                path_parts = md_file.relative_to(root).parts[:-1]
                if all(p in path_parts for p in parents):
                    return md_file
            else:
                return md_file
    return None


@dataclass(frozen=True, kw_only=True)
class _Qualified:
    root: Optional[str]
    name: str
    parents: Optional[List[str]]


def _split_root(policy_name: str, parents: Optional[List[str]]) -> _Qualified:
    """``<root>:<name>`` names a root. The prefix may sit on the name, or on the first parent
    when a caller has already split ``<root>:<dir>/<name>`` on '/'."""
    if parents and ":" in parents[0]:
        root_name, first = parents[0].split(":", 1)
        rest = ([first] if first else []) + list(parents[1:])
        return _Qualified(root=root_name, name=policy_name, parents=rest or None)
    if ":" in policy_name:
        root_name, policy_name = policy_name.split(":", 1)
        return _Qualified(root=root_name, name=policy_name, parents=parents)
    return _Qualified(root=None, name=policy_name, parents=parents)


def find_policy_file(
    policy_name: str,
    parents: Optional[List[str]] = None,
    maceff_root: Optional[Path] = None
) -> Optional[Path]:
    """
    Find policy file by name, across the framework root and any extra roots (#592).

    Args:
        policy_name: Policy filename (with or without .md extension), optionally qualified
                    by its root: 'task_management', 'framework:task_management',
                    'agentcad:agentcad-usage'
        parents: Optional list of parent directory names to match
                e.g., ['development'] to find development/task_management.md
        maceff_root: Optional MacEff installation root (auto-detected if None)

    Returns:
        Path to policy file, or None if not found

    Raises:
        PolicyAmbiguous: an unqualified name is in no framework policy but in more than one
            extra root. The framework's own policies always resolve: a name the framework
            has is the framework's, and a copy in an extra root is reported, not used, so a
            package can never make a core policy unreadable.

    Examples:
        find_policy_file('task_management')
            → .../framework/policies/base/development/task_management.md

        find_policy_file('task_management', parents=['development'])
            → .../framework/policies/base/development/task_management.md

        find_policy_file('checkpoints', parents=['consciousness'])
            → .../framework/policies/base/consciousness/checkpoints.md
    """
    q = _split_root(policy_name, parents)
    root_name, policy_name, parents = q.root, q.name, q.parents
    name = policy_name if policy_name.endswith('.md') else f"{policy_name}.md"
    roots = policy_roots(maceff_root)

    if root_name is not None:
        for root in roots:
            if root.name == root_name:
                return _find_in(root.path, name, parents)
        return None

    framework_hit = None
    extra_hits = []
    for root in roots:
        hit = _find_in(root.path, name, parents)
        if hit is None:
            continue
        if root.framework:
            framework_hit = hit
        else:
            extra_hits.append((root, hit))
    if framework_hit is not None:
        if extra_hits:
            _report_once(f"policy {name} is also in root(s) {', '.join(r.name for r, _ in extra_hits)}; "
                         f"the framework's is used. Read the other as <root>:{policy_name}")
        return framework_hit
    if len(extra_hits) > 1:
        raise PolicyAmbiguous(
            f"policy {policy_name!r} is in more than one root: "
            + ", ".join(f"{r.name} ({p})" for r, p in extra_hits)
            + f". Name one: " + " or ".join(f"{r.name}:{policy_name}" for r, _ in extra_hits))
    return extra_hits[0][1] if extra_hits else None


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
        List of dicts with keys: name, path, relative_path, category, tier, root. A policy
        from an extra root (#592) has its root's name as the head of its category and its
        relative path, so a listing names where each policy came from.
    """
    policies = []
    for root in policy_roots(maceff_root):
        policies.extend(_list_root(root, tier, category, include_tier))
    return sorted(policies, key=lambda p: (p['root'] != FRAMEWORK_ROOT_NAME, p['relative_path']))


def _list_root(root: PolicyRoot, tier: Optional[str], category: Optional[str],
               include_tier: bool) -> List[Dict[str, Any]]:
    base_path = root.path
    policies = []
    for md_file in base_path.rglob('*.md'):
        rel_path = md_file.relative_to(base_path)
        path_parts = rel_path.parts

        # Determine category from path (full parent path for nested dirs)
        file_category = str(rel_path.parent) if len(path_parts) > 1 else 'root'
        if not root.framework:
            file_category = root.name if len(path_parts) == 1 else f"{root.name}/{rel_path.parent}"

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
            'relative_path': str(rel_path) if root.framework else f"{root.name}:{rel_path}",
            'category': file_category,
            'tier': file_tier,
            'root': root.name,
        })

    return policies


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

    except Exception as e:
        print(f"⚠️ MACF: manifest generation failed: {e}", file=sys.stderr)
        # Graceful fallback - still point to discovery
        return "📋 POLICY DISCOVERY\n\nRun `macf_tools policy list` to discover policies"
