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

    # Filter discovery_index by active_consciousness
    active_ca_types = manifest.get('active_consciousness', [])
    if active_ca_types and 'discovery_index' in manifest:
        discovery_index = manifest['discovery_index']
        filtered_discovery = {}

        # Check each discovery key against active CA types
        for key, value in discovery_index.items():
            # Match if key relates to any active CA type (bidirectional substring match)
            # Handles singular/plural variations: "reflection" ↔ "reflections"
            if any(ca_type in key.lower() or key.lower() in ca_type for ca_type in active_ca_types):
                filtered_discovery[key] = value

        if filtered_discovery:
            filtered['discovery_index'] = filtered_discovery

    # Always include custom_policies if present
    if 'custom_policies' in manifest:
        filtered['custom_policies'] = manifest['custom_policies']

    return filtered

def format_manifest_awareness() -> str:
    """
    Format dynamic manifest awareness for SessionStart hook injection.

    Used on: compaction recovery + brand new session
    Skipped on: session resume

    Returns:
        Plain text awareness message (<500 tokens, for <system-reminder> tags)
    """
    # CA emoji mapping (from Phase 3 CLI)
    CA_EMOJIS = {
        'observations': '🔬',
        'experiments': '🧪',
        'reports': '📊',
        'reflections': '💭',
        'checkpoints': '🔖',
        'roadmaps': '🗺️',
        'emotions': '❤️'
    }

    # CA descriptions for display
    CA_DESCRIPTIONS = {
        'observations': 'Technical discoveries and insights',
        'experiments': 'Controlled testing and validation',
        'reports': 'Project completion summaries',
        'reflections': 'Philosophical growth synthesis',
        'checkpoints': 'Strategic state preservation',
        'roadmaps': 'Multi-phase planning documents',
        'emotions': 'Emotional expression and processing'
    }

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

        # Build output sections
        lines = ["📋 POLICY MANIFEST AWARENESS", ""]

        # Configuration section
        lines.append(f"Version: {version}")
        lines.append(f"Active Layers: {', '.join(active_layers) if active_layers else 'none'}")
        lines.append(f"Active Languages: {', '.join(active_languages) if active_languages else 'none'}")
        lines.append("")

        # Consciousness patterns section
        consciousness_patterns = filtered_manifest.get('consciousness_patterns', {})
        triggers = consciousness_patterns.get('triggers', [])
        if triggers:
            lines.append("Consciousness Patterns Active:")
            for trigger in triggers:
                pattern = trigger.get('pattern', 'unknown')
                consciousness = trigger.get('consciousness', '')
                lines.append(f"- {pattern}: {consciousness}")
            lines.append("")

        # Active CA types section
        discovery_index = filtered_manifest.get('discovery_index', {})
        if discovery_index:
            lines.append("Active CA Types:")
            # Sort by key for consistent display
            for ca_key in sorted(discovery_index.keys()):
                # Extract CA type from key (e.g., "observations_dir" -> "observations")
                ca_type = None
                for known_type in CA_EMOJIS.keys():
                    if known_type in ca_key.lower():
                        ca_type = known_type
                        break

                if ca_type:
                    emoji = CA_EMOJIS.get(ca_type, '📄')
                    desc = CA_DESCRIPTIONS.get(ca_type, 'Consciousness artifact')
                    # CRITICAL: Two spaces after emoji to prevent overlap
                    lines.append(f"{emoji}  {ca_type} - {desc}")
            lines.append("")

        # CLI commands section
        lines.append("CLI Commands for Discovery:")
        lines.append("- macf_tools policy manifest --format=summary")
        lines.append("- macf_tools policy search <keyword>")
        lines.append("- macf_tools policy ca-types")
        lines.append("- macf_tools policy list --layer=mandatory")

        return "\n".join(lines)

    except Exception:
        # Graceful fallback
        return "📋 POLICY MANIFEST AWARENESS\n\nError loading manifest - policy awareness unavailable"
