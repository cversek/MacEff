"""
Policy manifest merge/filter/format.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from .paths import find_project_root

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

def load_merged_manifest(agent_root: Optional[Path] = None) -> Dict[str, Any]:
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
        agent_root: Optional project root path (auto-detect if None via find_project_root())

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
        if agent_root is None:
            agent_root = find_project_root()
        else:
            agent_root = Path(agent_root)

        # Strategy 1: Check if we're in MacEff repo itself
        if (agent_root / 'framework' / 'policies' / 'manifest.json').exists():
            base_path = agent_root / 'framework' / 'policies' / 'manifest.json'
        # Strategy 2: Check for MacEff as submodule
        elif (agent_root / 'MacEff' / 'framework' / 'policies' / 'manifest.json').exists():
            base_path = agent_root / 'MacEff' / 'framework' / 'policies' / 'manifest.json'
        # Strategy 3: Check environment variable
        elif 'MACEFF_FRAMEWORK_PATH' in os.environ:
            base_path = Path(os.environ['MACEFF_FRAMEWORK_PATH']) / 'policies' / 'manifest.json'
        # Strategy 4: Check known sibling locations in gitwork/
        else:
            # Try to find MacEff as sibling repo
            gitwork_base = agent_root.parent.parent if 'gitwork' in str(agent_root) else None
            if gitwork_base:
                # Try cversek/MacEff (framework development location)
                candidate = gitwork_base / 'cversek' / 'MacEff' / 'framework' / 'policies' / 'manifest.json'
                if candidate.exists():
                    base_path = candidate
                else:
                    # Fallback: assume submodule (will fail with warning below)
                    base_path = agent_root / 'MacEff' / 'framework' / 'policies' / 'manifest.json'
            else:
                base_path = agent_root / 'MacEff' / 'framework' / 'policies' / 'manifest.json'

    # Load framework base (always required)
    manifest = {}
    try:
        with open(base_path) as f:
            manifest = json.load(f)
    except Exception as e:
        # Log warning but don't crash - return empty dict
        print(f"WARNING: Failed to load base manifest from {base_path}: {e}", file=sys.stderr)
        return {}

    # Discover project overlay path (cwd first, then agent_root)
    project_manifest_path = Path.cwd() / '.maceff' / 'policies' / 'manifest.json'

    if not project_manifest_path.exists() and agent_root:
        project_manifest_path = agent_root / '.maceff' / 'policies' / 'manifest.json'

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
        # Load merged+filtered manifest
        manifest = load_merged_manifest()
        if not manifest:
            return "📋 POLICY MANIFEST AWARENESS\n\nManifest not found - policy awareness unavailable"

        filtered_manifest = filter_active_policies(manifest)

        # Extract configuration
        version = filtered_manifest.get('version', 'unknown')
        active_layers = filtered_manifest.get('active_layers', [])
        active_languages = filtered_manifest.get('active_languages', [])
        active_ca_types = filtered_manifest.get('active_consciousness', [])

        # Build output sections with directive tone
        lines = [
            "📋 POLICY MANIFEST AWARENESS",
            "",
            f"Version: {version}",
            f"Active Layers: {', '.join(active_layers) if active_layers else 'none'}",
            f"Active Languages: {', '.join(active_languages) if active_languages else 'none'}",
            ""
        ]

        # Consciousness patterns summary
        consciousness_patterns = filtered_manifest.get('consciousness_patterns', {})
        pattern_count = len(consciousness_patterns.get('triggers', []))
        lines.append(f"Consciousness Patterns Active: {pattern_count}")

        # Active CA types with emoji mapping
        if active_ca_types:
            lines.append("Active CA Types:")
            # Emoji mapping from DELEG_PLAN
            ca_emoji_map = {
                'observations': '🔬',
                'experiments': '🧪',
                'reports': '📊',
                'reflections': '💭',
                'checkpoints': '🔖',
                'roadmaps': '🗺️',
                'learnings': '❤️'
            }
            for ca_type in active_ca_types:
                emoji = ca_emoji_map.get(ca_type, '📝')
                lines.append(f"  {emoji}  {ca_type}")
        else:
            lines.append("Active CA Types: none")

        lines.append("")

        # CRITICAL: Policies persist, memory doesn't
        lines.append("⚠️ CRITICAL: Policies persist across compaction. Your memory doesn't.")
        lines.append("These are PROJECT PRIORITIES configured by the user, not suggestions.")
        lines.append("")

        # BEFORE ANY WORK directive
        mandatory_policies = filtered_manifest.get('mandatory_policies', {}).get('policies', [])
        if mandatory_policies:
            lines.append("🔴 BEFORE ANY WORK: Check mandatory policies")
            lines.append("")
            for policy in mandatory_policies[:4]:  # Show top 4 for token efficiency
                name = policy.get('name', 'unknown')
                short_name = policy.get('short_name', '')
                desc = policy.get('description', '')
                lines.append(f"  {short_name}: {desc}")
                lines.append(f"      → macf_tools policy search {name.split('_')[0]}")
            lines.append("")

        # Pattern-to-action mapping (directive, not catalog)
        consciousness_patterns = filtered_manifest.get('consciousness_patterns', {})
        triggers = consciousness_patterns.get('triggers', [])
        if triggers:
            lines.append("🔴 WHEN YOU FEEL THESE PATTERNS → ACT IMMEDIATELY:")
            lines.append("")
            for trigger in triggers[:6]:  # Show top 6 for token efficiency
                consciousness = trigger.get('consciousness', '')
                likely_policies = trigger.get('likely_policies', [])
                search_terms = trigger.get('search_terms', [])

                lines.append(f'"{consciousness}"')
                if likely_policies:
                    policy_name = likely_policies[0]  # First policy is most relevant
                    lines.append(f"   → macf_tools policy search {policy_name.split('/')[-1].replace('_', ' ')}")
                elif search_terms:
                    lines.append(f"   → macf_tools policy search {search_terms[0]}")
                lines.append("")

        # Project enforcement section (if configured)
        if active_layers or active_languages:
            lines.append("🔴 PROJECT ENFORCEMENT:")
            if active_layers:
                layers_str = ', '.join(active_layers)
                lines.append(f"   Development layers MANDATORY: {layers_str}")
            if active_languages:
                langs_str = ', '.join(active_languages)
                lines.append(f"   Language standards MANDATORY: {langs_str}")
            lines.append("")

        # CLI commands for discovery
        lines.append("CLI Commands for Discovery:")
        lines.append("- macf_tools policy manifest --format=summary")
        lines.append("- macf_tools policy search <keyword>")
        lines.append("- macf_tools policy ca-types")
        lines.append("- macf_tools policy list --layer=mandatory")

        return "\n".join(lines)

    except Exception:
        # Graceful fallback
        return "📋 POLICY MANIFEST AWARENESS\n\nError loading manifest - policy awareness unavailable"
