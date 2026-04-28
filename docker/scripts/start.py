#!/usr/bin/env python3
"""
MacEff container startup script - Python implementation.

Parses agents.yaml and projects.yaml using Pydantic models,
validates configurations, and sets up named agent environments.

Design principles:
- Fail fast with actionable error messages
- Use Pydantic for validation (don't reimplement)
- Idempotent operations (safe to run multiple times)
"""

import sys
import os
import json
import hashlib
import shlex
import shutil
import subprocess
import pwd
import grp
import secrets
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import yaml
from pydantic import ValidationError

# Add macf package to path for model imports
sys.path.insert(0, '/opt/macf_tools/src')

from macf.models.agent_spec import AgentsConfig, AgentSpec, SubagentSpec, ClaudeCodeConfig, ConsciousnessArtifactsConfig
from macf.models.project_spec import ProjectsConfig, ProjectSpec


# Configuration paths
AGENTS_CONFIG = Path('/etc/maceff/agents.yaml')
PROJECTS_CONFIG = Path('/etc/maceff/projects.yaml')
FRAMEWORK_ROOT = Path('/opt/maceff/framework')
SHARED_WORKSPACE = Path('/shared_workspace')

# install_macf_tools() — explicit deps installed alongside the editable macf package.
# Lifted from inline strings into a module-level constant so it participates in the
# fingerprint that gates re-installation (see _compute_install_fingerprint).
INSTALL_EXTRA_DEPS = ["lancedb", "sentence-transformers"]


def log(msg: str) -> None:
    """Log message with timestamp."""
    timestamp = datetime.now().strftime('%H:%M:%S')
    print(f"[start.py {timestamp}] {msg}", file=sys.stderr, flush=True)


def run_command(cmd: List[str], check: bool = True, capture: bool = False) -> Optional[str]:
    """Execute shell command with error handling."""
    try:
        if capture:
            result = subprocess.run(cmd, check=check, capture_output=True, text=True)
            return result.stdout.strip()
        else:
            subprocess.run(cmd, check=check)
            return None
    except subprocess.CalledProcessError as e:
        log(f"Command failed: {' '.join(cmd)} (exit {e.returncode})")
        if check:
            raise
        return None


def user_exists(username: str) -> bool:
    """Check if Linux user exists."""
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def group_exists(groupname: str) -> bool:
    """Check if Linux group exists."""
    try:
        grp.getgrnam(groupname)
        return True
    except KeyError:
        return False


def ensure_group(groupname: str) -> None:
    """Create group if it doesn't exist."""
    if not group_exists(groupname):
        run_command(['groupadd', groupname])
        log(f"Group created: {groupname}")


def provision_agent_identity(username: str, home_dir: str, display_name: Optional[str], agent_key: str) -> str:
    """
    Create persistent identity file and set GECOS field.

    Args:
        username: Linux username (e.g., 'pa_manny')
        home_dir: Agent's home directory path
        display_name: Human-readable name from agents.yaml (e.g., 'Manny MacEff')
        agent_key: Agent dictionary key (e.g., 'manny') for fallback

    Returns:
        str: The 6-character agent UUID (existing or newly generated)
    """
    identity_file = Path(home_dir) / '.maceff_primary_agent.id'

    # Check if identity file already exists (preserve continuity)
    if identity_file.exists():
        try:
            agent_uuid = identity_file.read_text().strip()
            log(f"Identity preserved: {username} -> {agent_uuid}")
        except Exception as e:
            log(f"WARNING: Could not read existing identity file for {username}: {e}")
            agent_uuid = secrets.token_hex(3)
            log(f"Generated new identity: {username} -> {agent_uuid}")
    else:
        # Generate new 6-character lowercase hex UUID
        agent_uuid = secrets.token_hex(3)

        try:
            # Write identity file with root ownership and immutable permissions
            identity_file.write_text(agent_uuid)
            identity_file.chmod(0o444)
            run_command(['chown', 'root:root', str(identity_file)])
            log(f"Identity created: {username} -> {agent_uuid}")
        except Exception as e:
            log(f"WARNING: Could not create identity file for {username}: {e}")

    # Set GECOS field (Full Name) for user
    try:
        # Use display_name if provided, otherwise derive from agent_key
        gecos_name = display_name if display_name else agent_key.title()
        run_command(['chfn', '-f', gecos_name, username], check=False)
        log(f"GECOS field set: {username} -> {gecos_name}")
    except Exception as e:
        log(f"WARNING: Could not set GECOS field for {username}: {e}")

    return agent_uuid


def create_pa_user(agent_name: str, agent_spec: AgentSpec, defaults_dict: Optional[Dict] = None) -> None:
    """Create Primary Agent Linux user."""
    username = agent_spec.username

    if not user_exists(username):
        run_command(['useradd', '-m', '-s', '/bin/bash', username])
        run_command(['usermod', '-aG', 'agents_all', username])
        log(f"PA user created: {username}")

    # Ensure home directory exists with correct permissions
    # 710 + group=agents_all: owner full access, other PAs can traverse (for agent/public/ access)
    home_dir = Path(f'/home/{username}')
    home_dir.mkdir(mode=0o710, exist_ok=True)
    run_command(['chown', f'{username}:agents_all', str(home_dir)])
    run_command(['chmod', '710', str(home_dir)])

    # Provision persistent agent identity (UUID + GECOS field)
    display_name = getattr(agent_spec, 'display_name', None)
    agent_uuid = provision_agent_identity(username, str(home_dir), display_name, agent_name)

    # Install SSH key if present
    install_ssh_key(username)

    # Create bash_init.sh (MUST come before configure_bashrc)
    # This is the single source of truth for PA environment setup
    channels = None
    if agent_spec.claude_config and agent_spec.claude_config.channels:
        channels = agent_spec.claude_config.channels
    create_bash_init(username, agent_name, channels=channels)

    # Configure .bashrc to source bash_init.sh
    configure_bashrc(username)

    # Configure Claude Code settings (merge defaults + agent-specific)
    configure_claude_settings(username, agent_name, agent_spec, defaults_dict)


def install_ssh_key(username: str) -> None:
    """Install SSH key for user if available."""
    if not user_exists(username):
        return

    ssh_dir = Path(f'/home/{username}/.ssh')
    key_file = Path(f'/keys/{username}.pub')

    if key_file.exists():
        ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        run_command(['chown', f'{username}:{username}', str(ssh_dir)])

        authorized_keys = ssh_dir / 'authorized_keys'
        run_command(['cp', str(key_file), str(authorized_keys)])
        run_command(['chown', f'{username}:{username}', str(authorized_keys)])
        run_command(['chmod', '600', str(authorized_keys)])
        log(f"SSH key installed: {username}")


def create_bash_init(username: str, agent_name: str, channels: list = None) -> None:
    """Create ~/.bash_init.sh for shell initialization (interactive + non-interactive).

    This file is the single source of truth for PA-specific environment setup.
    It is sourced by:
    - Interactive shells: via ~/.bashrc
    - Non-interactive shells: via BASH_ENV environment variable

    Contains PA-specific variables only. Container-wide vars (MACEFF_ROOT_DIR,
    MACEFF_TZ) are in /etc/environment.

    Environment-specific setup (conda, venv, etc.) is handled by deployment-provided
    scripts in /opt/maceff/framework/env.d/*.sh, which are sourced in alphanumeric order.

    Args:
        username: Linux username (e.g., 'pa_manny')
        agent_name: Agent identity name (e.g., 'manny')
        channels: Optional list of channel plugin strings for --channels flag
    """
    home_dir = Path(f'/home/{username}')
    bash_init = home_dir / '.bash_init.sh'

    # Build channels env var block if configured
    channels_block = ''
    if channels:
        channels_str = ' '.join(channels)
        channels_block = f'''
# CC Channels configuration (from agents.yaml claude_config.channels)
export MACEFF_CHANNELS="{channels_str}"
'''

    bash_init_content = f'''#!/bin/bash
# MacEff: Shell initialization for both interactive and non-interactive shells
# Created by start.py - DO NOT EDIT MANUALLY
# Sourced by: ~/.bashrc (interactive) and BASH_ENV (non-interactive)

# Self-referential BASH_ENV for nested shells
export BASH_ENV="$HOME/.bash_init.sh"

# PA-specific environment (container-wide vars in /etc/environment)
export MACEFF_AGENT_HOME_DIR="$HOME"
export MACEFF_AGENT_NAME="{agent_name}"
{channels_block}
# Source deployment-provided environment scripts (alphanumeric order)
# Scripts: 00-core, 10-lang-managers, 20-path, 50-custom, 90-final
if [ -d /opt/maceff/framework/env.d ]; then
    for script in /opt/maceff/framework/env.d/*.sh; do
        [ -r "$script" ] && . "$script"
    done
fi
'''

    bash_init.write_text(bash_init_content)
    bash_init.chmod(0o755)  # Executable
    run_command(['chown', f'{username}:{username}', str(bash_init)])
    log(f"Created bash_init.sh: {username}")


def configure_bashrc(username: str) -> None:
    """Configure .bashrc for MacEff initialization.

    CRITICAL: Sources ~/.bash_init.sh BEFORE the interactive guard so that
    non-interactive shells (Claude Code's bash -c) get proper initialization.

    Also adds active_project cd for interactive sessions.
    """
    home_dir = Path(f'/home/{username}')
    bashrc = home_dir / '.bashrc'

    # Block that MUST come BEFORE the interactive guard
    # This ensures non-interactive shells get initialized
    prepend_block = '''# MacEff: Source BEFORE interactive guard (for bash -c commands)
if [ -f ~/.bash_init.sh ]; then
    . ~/.bash_init.sh
fi

'''

    # Block that comes AFTER the interactive guard (for interactive features)
    append_block = '''
# MacEff: cd to active project on interactive login
if [[ $- == *i* ]] && [[ -L ~/active_project ]] && [[ -d ~/active_project ]]; then
    cd ~/active_project
    cd "$(pwd -P)"  # Resolve symlink so prompt shows real path
fi
'''

    # Check if already configured
    if bashrc.exists():
        existing_content = bashrc.read_text()
        if 'MacEff: Source BEFORE interactive guard' in existing_content:
            return  # Already configured

        # PREPEND our init block at the very beginning
        new_content = prepend_block + existing_content
        # Append the interactive features if not already there
        if 'MacEff: cd to active project' not in existing_content:
            new_content += append_block
        bashrc.write_text(new_content)
    else:
        # No bashrc exists, create with both blocks
        bashrc.write_text(prepend_block + append_block)

    run_command(['chown', f'{username}:{username}', str(bashrc)])
    log(f"Bashrc configured for active_project: {username}")


def configure_claude_settings(
    username: str,
    agent_name: str,
    agent_spec: AgentSpec,
    defaults_dict: Optional[Dict] = None
) -> None:
    """Configure Claude Code settings for agent.

    Writes TWO separate files based on settings epistemology:
    - ~/.claude/settings.json: Project/capability settings (hooks, env, outputStyle)
    - ~/.claude.json: Person/UI preferences (verbose, autoCompactEnabled)

    Merges deployment-level defaults with per-agent overrides.
    Priority: agent_spec.claude_config > defaults.claude_config > hardcoded defaults
    """
    from macf.models.agent_spec import (
        ClaudeCodeConfig, ClaudeCodeSettingsConfig, ClaudeCodePreferencesConfig
    )

    home_dir = Path(f'/home/{username}')
    claude_dir = home_dir / '.claude'
    claude_dir.mkdir(mode=0o755, exist_ok=True)

    # Start with defaults from Pydantic models
    merged_settings = ClaudeCodeSettingsConfig()
    merged_prefs = ClaudeCodePreferencesConfig()

    def merge_layer(source: Optional[Dict]) -> None:
        """Merge a config layer into merged settings/prefs."""
        nonlocal merged_settings, merged_prefs
        if not source:
            return
        if source.get('settings'):
            # Deep merge: update only non-None values
            layer = ClaudeCodeSettingsConfig(**source['settings'])
            for field in layer.model_fields:
                val = getattr(layer, field)
                if val is not None:
                    setattr(merged_settings, field, val)
        if source.get('preferences'):
            layer = ClaudeCodePreferencesConfig(**source['preferences'])
            for field in layer.model_fields:
                setattr(merged_prefs, field, getattr(layer, field))

    # Apply layers: defaults < agent overrides
    if defaults_dict and defaults_dict.get('claude_config'):
        merge_layer(defaults_dict['claude_config'])
    if agent_spec.claude_config:
        merge_layer(agent_spec.claude_config.model_dump())

    # Inject PA-specific environment variables (belt-and-suspenders with BASH_ENV)
    # These are available to Claude Code directly without shell sourcing
    pa_env_vars = {
        'MACEFF_AGENT_HOME_DIR': str(home_dir),
        'MACEFF_AGENT_NAME': agent_name,
    }
    # Merge PA vars into env (don't overwrite explicit config)
    for key, value in pa_env_vars.items():
        if key not in merged_settings.env:
            merged_settings.env[key] = value

    # Write ~/.claude/settings.json (preserve user keys like 'theme')
    settings_file = claude_dir / 'settings.json'
    existing_settings = {}
    if settings_file.exists():
        try:
            existing_settings = json.loads(settings_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # Start fresh if file is corrupted
    # Merge: existing user keys + managed keys (managed keys win on conflict)
    final_settings = {**existing_settings, **merged_settings.model_dump(exclude_none=True)}
    settings_file.write_text(json.dumps(final_settings, indent=2))

    # Write ~/.claude.json (preserve user keys like 'hasCompletedOnboarding')
    prefs_file = home_dir / '.claude.json'
    existing_prefs = {}
    if prefs_file.exists():
        try:
            existing_prefs = json.loads(prefs_file.read_text())
        except (json.JSONDecodeError, OSError):
            pass  # Start fresh if file is corrupted
    # Merge: existing user keys + managed keys (managed keys win on conflict)
    final_prefs = {**existing_prefs, **merged_prefs.model_dump()}
    prefs_file.write_text(json.dumps(final_prefs, indent=2))

    # Set ownership
    run_command(['chown', '-R', f'{username}:{username}', str(claude_dir)])
    run_command(['chown', f'{username}:{username}', str(prefs_file)])

    log(f"  Claude settings: {merged_settings.model_dump(exclude_none=True)}")
    log(f"  Claude prefs: {merged_prefs.model_dump()}")


def create_agent_tree(username: str, agent_spec: AgentSpec, defaults_config: Optional[Dict]) -> None:
    """Create agent directory structure with consciousness artifacts."""
    home = Path(f'/home/{username}')
    agent = home / 'agent'

    # Create root agent directory (group=agents_all for cross-PA traversal)
    agent.mkdir(mode=0o550, exist_ok=True)
    run_command(['chown', f'root:agents_all', str(agent)])
    run_command(['chmod', '550', str(agent)])

    # Create private and public directories
    private = agent / 'private'
    public = agent / 'public'

    # Determine parent directory permissions based on immutable_structure flag
    ca_config = agent_spec.consciousness_artifacts
    if ca_config is None and defaults_config:
        ca_config = defaults_config.get('consciousness_artifacts')

    # Check immutable_structure flag (defaults to True for governance)
    immutable = getattr(ca_config, 'immutable_structure', True) if ca_config else True

    # Private: owner-only (other PAs cannot read)
    # Public: group-readable via agents_all (other PAs can read)
    if immutable:
        parent_mode_private = 0o500  # r-x------ (owner-only, no mkdir)
        parent_mode_public = 0o550   # r-xr-x--- (group=agents_all readable, no mkdir)
    else:
        parent_mode_private = 0o700  # rwx------ (owner-only, writable)
        parent_mode_public = 0o750   # rwxr-x--- (group=agents_all readable, writable)

    private.mkdir(mode=parent_mode_private, exist_ok=True)
    public.mkdir(mode=parent_mode_public, exist_ok=True)

    # Private: owner's group only; Public: agents_all for cross-PA access
    run_command(['chown', f'{username}:{username}', str(private)])
    run_command(['chown', f'{username}:agents_all', str(public)])

    # Explicitly enforce permissions (mkdir mode= is unreliable due to umask)
    if immutable:
        run_command(['chmod', '500', str(private)])
        run_command(['chmod', '550', str(public)])
    else:
        run_command(['chmod', '700', str(private)])
        run_command(['chmod', '750', str(public)])

    if ca_config:
        # Private artifacts (owner-only: other PAs cannot access)
        if ca_config.private:
            for artifact_type in ca_config.private:
                artifact_dir = private / artifact_type
                artifact_dir.mkdir(mode=0o700, exist_ok=True)
                run_command(['chown', f'{username}:{username}', str(artifact_dir)])
                run_command(['chmod', '700', str(artifact_dir)])

        # Public artifacts (group=agents_all: other PAs can read)
        if ca_config.public:
            for artifact_type in ca_config.public:
                artifact_dir = public / artifact_type
                artifact_dir.mkdir(mode=0o750, exist_ok=True)
                run_command(['chown', f'{username}:agents_all', str(artifact_dir)])
                run_command(['chmod', '750', str(artifact_dir)])

    # Create task_archives directory (MACF infrastructure, always needed)
    # This is NOT a consciousness artifact type — it's where task archive JSON goes.
    # Must be created at init time because agent/public/ is immutable (550).
    task_archives = public / 'task_archives'
    task_archives.mkdir(mode=0o750, exist_ok=True)
    run_command(['chown', f'{username}:agents_all', str(task_archives)])
    run_command(['chmod', '750', str(task_archives)])

    # Create subagents directory (owner-only, like private)
    subagents = agent / 'subagents'
    subagents.mkdir(mode=0o500, exist_ok=True)
    run_command(['chown', f'{username}:{username}', str(subagents)])
    run_command(['chmod', '500', str(subagents)])

    # Initialize ~/.maceff/ with per-PA settings (AUTO_MODE auth + initial state).
    #
    # macf_tools mode set AUTO_MODE requires --auth-token, validated against the
    # `auto_mode_auth_token` value in <agent_home>/.maceff/settings.json. Without
    # this file, the activation flow can't complete (the CLI gates --auth-token
    # presence regardless of whether token validation itself would skip).
    #
    # Token is generated PER-CONTAINER at first boot, never baked into the image
    # (would defeat the auth purpose). Subsequent restarts preserve the existing
    # token because the home volume persists and the if-not-exists guard skips
    # regeneration.
    maceff_dir = home / '.maceff'
    maceff_dir.mkdir(mode=0o700, exist_ok=True)
    run_command(['chown', f'{username}:{username}', str(maceff_dir)])
    run_command(['chmod', '700', str(maceff_dir)])

    settings_file = maceff_dir / 'settings.json'
    if not settings_file.exists():
        token = secrets.token_urlsafe(32)
        settings_file.write_text(json.dumps({
            "auto_mode_auth_token": token,
        }, indent=2) + '\n')
        log(f"Generated auto_mode_auth_token for {username}")
    run_command(['chown', f'{username}:{username}', str(settings_file)])
    run_command(['chmod', '600', str(settings_file)])

    state_file = maceff_dir / 'agent_state.json'
    if not state_file.exists():
        state_file.write_text(json.dumps({
            "auto_mode": False,
            "auto_mode_authorized_at": None,
        }, indent=2) + '\n')
        log(f"Initialized agent_state.json for {username}")
    run_command(['chown', f'{username}:{username}', str(state_file)])
    run_command(['chmod', '600', str(state_file)])


def create_personal_policies(username: str) -> None:
    """Create personal policies directory with templates (highest precedence layer)."""
    home = Path(f'/home/{username}')
    policies_dir = home / 'agent' / 'policies' / 'personal'

    # Create directory structure
    policies_dir.mkdir(parents=True, mode=0o755, exist_ok=True)
    run_command(['chown', f'{username}:{username}', str(policies_dir)])
    run_command(['chown', f'{username}:{username}', str(policies_dir.parent)])

    # Install manifest.json template
    manifest_template = FRAMEWORK_ROOT / 'templates' / 'personal_policies_manifest.json'
    manifest_target = policies_dir / 'manifest.json'

    if manifest_template.exists() and not manifest_target.exists():
        run_command(['cp', str(manifest_template), str(manifest_target)])
        run_command(['chown', f'{username}:{username}', str(manifest_target)])
        log(f"Personal policies manifest created: {username}")

    # Install README.md template
    readme_template = FRAMEWORK_ROOT / 'templates' / 'personal_policies_README.md'
    readme_target = policies_dir / 'README.md'

    if readme_template.exists() and not readme_target.exists():
        run_command(['cp', str(readme_template), str(readme_target)])
        run_command(['chown', f'{username}:{username}', str(readme_target)])
        log(f"Personal policies README created: {username}")


def create_subagent_workspace(username: str, sa_name: str, sa_spec: SubagentSpec) -> None:
    """Create Subagent workspace within PA agent tree."""
    home = Path(f'/home/{username}')
    sa_root = home / 'agent' / 'subagents' / sa_name

    # Create subagent root (read-only parent: r-xr-xr-x root:root)
    # Mode is 555 so PA (and SA dispatched under PA's UID) can traverse
    # via "other" permission bits, but no one can mkdir new top-level
    # CA types — only root can write at the structure level.
    sa_root.mkdir(mode=0o555, exist_ok=True)
    run_command(['chown', 'root:root', str(sa_root)])
    # Idempotent enforcement: mkdir(mode=) is ignored when exist_ok=True
    # matches a pre-existing dir, and persistent volumes carry forward
    # whatever mode the original create used. Always chmod to authoritative mode.
    run_command(['chmod', '555', str(sa_root)])

    # Always overwrite SUBAGENT_DEF.md from framework/deployment definition
    sa_def = sa_root / 'SUBAGENT_DEF.md'
    framework_def = FRAMEWORK_ROOT / 'subagents' / f'{sa_name}.md'
    if framework_def.exists():
        shutil.copy2(str(framework_def), str(sa_def))
        log(f"Populated SUBAGENT_DEF.md from framework: {framework_def.name}")
    elif not sa_def.exists():
        sa_def.touch(mode=0o644)
        log(f"WARNING: No framework definition found for '{sa_name}', created empty SUBAGENT_DEF.md")
    run_command(['chown', 'root:root', str(sa_def)])
    run_command(['chmod', '644', str(sa_def)])  # Idempotent: enforce world-readable

    # Create private and public directories
    private = sa_root / 'private'
    public = sa_root / 'public'
    assigned = sa_root / 'assigned'

    # Determine parent directory permissions based on immutable_structure flag
    ca_config = sa_spec.consciousness_artifacts
    immutable = getattr(ca_config, 'immutable_structure', True) if ca_config else True

    if immutable:
        # Read-only parent dirs prevent subagents from creating new CA types
        parent_mode_private = 0o555  # r-xr-xr-x (read-only, no mkdir)
        parent_mode_public = 0o555   # r-xr-xr-x (read-only, no mkdir)
    else:
        # Standard permissions allow subagents to create new directories
        parent_mode_private = 0o750  # rwxr-x--- (writable)
        parent_mode_public = 0o750   # rwxr-x--- (writable)

    private.mkdir(mode=parent_mode_private, exist_ok=True)
    public.mkdir(mode=parent_mode_public, exist_ok=True)
    assigned.mkdir(mode=0o755, exist_ok=True)

    run_command(['chown', f'{username}:{username}', str(private)])
    run_command(['chown', f'{username}:{username}', str(public)])
    run_command(['chown', f'{username}:{username}', str(assigned)])

    # Explicitly enforce permissions (mkdir mode= is unreliable due to umask)
    if immutable:
        run_command(['chmod', '555', str(private)])
        run_command(['chmod', '555', str(public)])
    else:
        run_command(['chmod', '750', str(private)])
        run_command(['chmod', '750', str(public)])
    run_command(['chmod', '755', str(assigned)])

    if ca_config:
        # Private artifacts
        if ca_config.private:
            for artifact_type in ca_config.private:
                artifact_dir = private / artifact_type
                artifact_dir.mkdir(mode=0o750, exist_ok=True)
                run_command(['chown', f'{username}:{username}', str(artifact_dir)])

        # Public artifacts (typically delegation_trails, reports, observations)
        if ca_config.public:
            for artifact_type in ca_config.public:
                artifact_dir = public / artifact_type
                artifact_dir.mkdir(mode=0o750, exist_ok=True)
                run_command(['chown', f'{username}:{username}', str(artifact_dir)])

    # Always create dev_scripts for ad hoc development scripts (all PAs)
    dev_scripts_dir = public / 'dev_scripts'
    dev_scripts_dir.mkdir(mode=0o750, exist_ok=True)
    run_command(['chown', f'{username}:{username}', str(dev_scripts_dir)])


def install_framework_commands(home_dir: Path) -> None:
    """Install framework commands as symlinks to ~/.claude/commands/.

    Supports nested directory structure for hierarchical namespaces.
    E.g., commands/maceff/todos/start.md → /maceff:todos:start
    """
    commands_dir = home_dir / '.claude' / 'commands'
    commands_dir.mkdir(parents=True, exist_ok=True)

    framework_commands = FRAMEWORK_ROOT / 'commands'
    if framework_commands.exists():
        # Walk nested structure recursively
        for cmd_file in framework_commands.rglob('*.md'):
            # Get relative path from commands/ root
            rel_path = cmd_file.relative_to(framework_commands)
            # Create target path preserving directory structure
            link = commands_dir / rel_path
            link.parent.mkdir(parents=True, exist_ok=True)
            if not link.exists() and not link.is_symlink():
                link.symlink_to(cmd_file)
                log(f"Created command symlink: {rel_path}")


def install_framework_skills(home_dir: Path) -> None:
    """Install framework skills as symlinks to ~/.claude/skills/."""
    skills_dir = home_dir / '.claude' / 'skills'
    skills_dir.mkdir(parents=True, exist_ok=True)

    framework_skills = FRAMEWORK_ROOT / 'skills'
    if framework_skills.exists():
        for skill_dir in framework_skills.iterdir():
            if skill_dir.is_dir() and skill_dir.name.startswith('maceff-'):
                link = skills_dir / skill_dir.name
                if not link.exists() and not link.is_symlink():
                    link.symlink_to(skill_dir)
                    log(f"Created skill symlink: {link.name}")


def install_framework_output_styles(home_dir: Path) -> None:
    """Install framework output styles as symlinks to ~/.claude/output-styles/."""
    styles_dir = home_dir / '.claude' / 'output-styles'
    styles_dir.mkdir(parents=True, exist_ok=True)

    framework_styles = FRAMEWORK_ROOT / 'output-styles'
    if framework_styles.exists():
        for style_file in framework_styles.glob('*.md'):
            link = styles_dir / style_file.name
            if not link.exists() and not link.is_symlink():
                link.symlink_to(style_file)
                log(f"Created output-style symlink: {link.name}")


def install_three_layer_context(username: str, agent_spec: AgentSpec) -> None:
    """Install three-layer CLAUDE.md context (System/Identity/Project)."""
    home = Path(f'/home/{username}')
    claude_dir = home / '.claude'
    claude_dir.mkdir(mode=0o755, exist_ok=True)

    # Layer 1 (System): Symlink to framework PA_PREAMBLE.md
    system_layer = claude_dir / 'CLAUDE.md'
    system_source = FRAMEWORK_ROOT / 'templates' / 'PA_PREAMBLE.md'

    if system_source.exists() and not system_layer.exists():
        system_layer.symlink_to(system_source)

    # Layer 2 (Identity): Copy personality file to ~/CLAUDE.md
    identity_layer = home / 'CLAUDE.md'
    personality_source = FRAMEWORK_ROOT / agent_spec.personality

    if personality_source.exists() and not identity_layer.exists():
        run_command(['cp', str(personality_source), str(identity_layer)])
        run_command(['chown', f'{username}:{username}', str(identity_layer)])

    # Layer 3 (Project): Handled by create_project_workspace()

    # Create agents/ directory for subagent definition symlinks
    agents_dir = claude_dir / 'agents'
    agents_dir.mkdir(mode=0o755, exist_ok=True)

    # Install hooks directory structure
    hooks_dir = claude_dir / 'hooks'
    hooks_dir.mkdir(mode=0o755, exist_ok=True)

    # Install framework commands, skills, and output styles
    install_framework_commands(home)
    install_framework_skills(home)
    install_framework_output_styles(home)

    # Ensure ownership
    run_command(['chown', '-R', f'{username}:{username}', str(claude_dir)])


def create_subagent_definition_symlinks(username: str, subagent_names: List[str]) -> None:
    """Create symlinks from .claude/agents/ to SUBAGENT_DEF.md files."""
    home = Path(f'/home/{username}')
    agents_dir = home / '.claude' / 'agents'

    for sa_name in subagent_names:
        sa_def_target = home / 'agent' / 'subagents' / sa_name / 'SUBAGENT_DEF.md'
        sa_link = agents_dir / f'{sa_name}.md'

        if sa_def_target.exists() and not sa_link.exists():
            sa_link.symlink_to(f'../../agent/subagents/{sa_name}/SUBAGENT_DEF.md')


def create_project_workspace(project_name: str, project_spec: ProjectSpec) -> None:
    """Create shared project workspace with repos and context."""
    project_dir = SHARED_WORKSPACE / project_name
    project_dir.mkdir(mode=0o2775, exist_ok=True)
    os.chmod(project_dir, 0o2775)  # Override umask to ensure group write

    # Install project CLAUDE.md (Layer 3 context)
    project_context = project_dir / 'CLAUDE.md'
    context_source = FRAMEWORK_ROOT / project_spec.context

    if context_source.exists() and not project_context.exists():
        run_command(['cp', str(context_source), str(project_context)])

    # Create repos directory
    if project_spec.repos:
        repos_dir = project_dir / 'repos'
        repos_dir.mkdir(mode=0o2775, exist_ok=True)
        os.chmod(repos_dir, 0o2775)  # Override umask to ensure group write

        # Clone repositories
        for repo_mount in project_spec.repos:
            repo_path = repos_dir / repo_mount.name
            if not repo_path.exists():
                log(f"Cloning {repo_mount.url} to {repo_path}")
                run_command(['git', 'clone', repo_mount.url, str(repo_path)], check=False)

    # Create .claude/commands directory for project-specific commands
    if project_spec.commands:
        commands_dir = project_dir / '.claude' / 'commands'
        commands_dir.mkdir(parents=True, mode=0o755, exist_ok=True)

        for cmd_name, cmd_source_path in project_spec.commands.items():
            cmd_source = FRAMEWORK_ROOT / cmd_source_path
            cmd_target = commands_dir / f'{cmd_name}.md'

            if cmd_source.exists() and not cmd_target.exists():
                run_command(['cp', str(cmd_source), str(cmd_target)])


def create_workspace_structure(username: str, assigned_projects: List[str],
                               projects_config: Optional[ProjectsConfig]) -> None:
    """
    Create workspace directory structure for agent projects.

    Creates workspace directories and symlinks. Git worktree creation is
    deferred to deploy.py WorktreeSetup for single-command deployment.

    This preserves 3-layer CLAUDE.md discovery by avoiding symlinks that
    break upward path traversal.

    Args:
        username: Agent username
        assigned_projects: List of project names assigned to this agent
        projects_config: Validated ProjectsConfig (needed for repo details)
    """
    home = Path(f'/home/{username}')
    workspace = home / 'workspace'
    workspace.mkdir(mode=0o755, exist_ok=True)

    for project_name in assigned_projects:
        project_workspace = workspace / project_name
        shared_project = SHARED_WORKSPACE / project_name

        if not shared_project.exists():
            log(f"Shared project missing: {project_name}")
            continue

        # Create real workspace directory (not symlink)
        project_workspace.mkdir(mode=0o755, exist_ok=True)
        run_command(['chown', f'{username}:{username}', str(project_workspace)])

        # Copy project CLAUDE.md (Layer 3 context)
        shared_context = shared_project / 'CLAUDE.md'
        agent_context = project_workspace / 'CLAUDE.md'
        if shared_context.exists() and not agent_context.exists():
            run_command(['cp', str(shared_context), str(agent_context)])
            run_command(['chown', f'{username}:{username}', str(agent_context)])

        # Get project spec for repo details
        if not projects_config or project_name not in projects_config.projects:
            log(f"Project spec not found: {project_name}")
            continue

        project_spec = projects_config.projects[project_name]

        # Setup repos (worktrees or symlinks)
        if project_spec.repos:
            for repo_mount in project_spec.repos:
                # Shared repo always in /shared_workspace/{project}/repos/{name}
                shared_repo = shared_project / 'repos' / repo_mount.name

                if not shared_repo.exists():
                    log(f"Shared repo missing: {shared_repo}")
                    continue

                # Compute agent path based on worktree flag
                if repo_mount.worktree:
                    # Worktree repos: Create directory structure only
                    # Actual worktree creation handled by deploy.py WorktreeSetup
                    worktree_base = project_workspace / 'git-worktrees'
                    worktree_base.mkdir(mode=0o755, exist_ok=True)
                    run_command(['chown', f'{username}:{username}', str(worktree_base)])
                    log(f"Worktree directory prepared: {worktree_base} (use deploy.py to create worktrees)")
                else:
                    # Symlink: ~/workspace/{project}/repos/{name} -> shared
                    agent_repo = project_workspace / 'repos' / repo_mount.name
                    agent_repo.parent.mkdir(parents=True, exist_ok=True)
                    if not agent_repo.exists():
                        agent_repo.symlink_to(shared_repo)
                        log(f"Repo symlink: {agent_repo} -> {shared_repo}")

        # Create data and outputs symlinks (if shared directories exist)
        shared_data = shared_project / 'data'
        agent_data = project_workspace / 'data'
        if shared_data.exists() and not agent_data.exists():
            agent_data.symlink_to(shared_data)
            log(f"Data symlink: {username}/{project_name}/data → {shared_data}")

        shared_outputs = shared_project / 'outputs'
        agent_outputs = project_workspace / 'outputs'
        if shared_outputs.exists() and not agent_outputs.exists():
            agent_outputs.symlink_to(shared_outputs)
            log(f"Outputs symlink: {username}/{project_name}/outputs → {shared_outputs}")

        log(f"Workspace structure created: {username} -> {project_name}")

    # Create active_project symlink pointing to first assigned project
    # This enables .bashrc to cd to the active project on login
    if assigned_projects:
        first_project = assigned_projects[0]
        active_project_link = home / 'active_project'
        target_project = workspace / first_project
        if target_project.exists() and not active_project_link.exists():
            active_project_link.symlink_to(target_project)
            run_command(['chown', '-h', f'{username}:{username}', str(active_project_link)])
            log(f"Active project symlink: ~/active_project -> {first_project}")


def initialize_agents(agents_config: AgentsConfig) -> None:
    """
    Main orchestrator for agent initialization.

    For each primary agent: creates user, builds directory tree,
    installs SSH keys, configures Claude settings, sets up subagent
    workspaces, and creates project symlinks.

    Args:
        agents_config: Validated AgentsConfig from agents.yaml
    """
    for agent_name, agent_spec in agents_config.agents.items():
        username = agent_spec.username

        # Run macf_tools agent init
        cmd = f'su - {username} -c "macf_tools agent init"'
        result = subprocess.run(cmd, shell=True, capture_output=True)

        if result.returncode == 0:
            log(f"PA initialized: {username}")
        else:
            log(f"PA init skipped for {username} (may already exist)")

        # Install hooks (agent init doesn't do this)
        log(f"Installing hooks for {username}...")
        cmd = f'su - {username} -c "macf_tools hooks install --local"'
        result = subprocess.run(cmd, shell=True, capture_output=True)

        if result.returncode == 0:
            log(f"Hooks installed: {username}")
        else:
            log(f"Hook installation failed for {username}: {result.stderr.decode()}")


def _compute_install_fingerprint(macf_tools_src: Path) -> str:
    """Compute a stable fingerprint for the macf install state.

    Hashes Python interpreter version + macf pyproject.toml + the
    INSTALL_EXTRA_DEPS constant. Drift in any of these invalidates the
    sentinel and triggers a reinstall on next container start.

    Returns:
        Hex sha256 digest.
    """
    h = hashlib.sha256()
    try:
        h.update(subprocess.check_output(['python3', '--version']))
    except Exception as e:
        log(f"Warning: python3 --version probe failed during fingerprint: {e}")
        h.update(b'unknown-python')
    pyproject = macf_tools_src / 'pyproject.toml'
    if pyproject.exists():
        h.update(pyproject.read_bytes())
    h.update(','.join(INSTALL_EXTRA_DEPS).encode())
    return h.hexdigest()


def install_macf_tools() -> None:
    """Install MACF tools in shared venv (idempotent via fingerprint sentinel).

    On first run, or when the fingerprint changes (Python upgrade, pyproject
    edit, INSTALL_EXTRA_DEPS edit), runs the full uv-pip-install sequence —
    typically 2-3 minutes due to torch + nvidia-cuda + transformers wheels.

    On subsequent runs with matching fingerprint, returns in milliseconds.

    The sentinel file is written into /opt/maceff-venv after a successful
    install. Deployments are encouraged (but not required) to mount that
    path as a persistent named volume so the install survives container
    destroy/recreate cycles.

    Override: set MACF_FORCE_REINSTALL=1 to bypass the sentinel and force
    a fresh install regardless of fingerprint state.
    """
    macf_tools_src = Path('/opt/macf_tools')

    if not macf_tools_src.exists():
        log("MACF tools source not found, skipping installation")
        return

    venv_path = Path('/opt/maceff-venv')

    # Create venv if needed (preserves existing guard)
    if not (venv_path / 'bin' / 'python').exists():
        run_command(['python3', '-m', 'venv', str(venv_path)])
        run_command([str(venv_path / 'bin' / 'python'), '-m', 'pip', '-q', 'install', '--upgrade', 'pip'])

    # Sentinel-based skip: if fingerprint matches the last successful install,
    # the venv is already current and we can return without reinstalling the
    # ~1GB+ of torch/nvidia/transformers wheels. The MACF_FORCE_REINSTALL=1
    # env override bypasses this skip for emergency invalidation.
    sentinel = venv_path / '.macf_install_fingerprint'
    fp = _compute_install_fingerprint(macf_tools_src)
    force_reinstall = os.getenv('MACF_FORCE_REINSTALL') == '1'
    if (not force_reinstall
            and sentinel.exists()
            and f'fingerprint={fp}' in sentinel.read_text()):
        log("MACF venv up-to-date (fingerprint match), skipping install")
        # Still ensure the global CLI symlink exists (cheap; idempotent)
        macf_cli = Path('/usr/local/bin/macf_tools')
        if not macf_cli.exists():
            macf_cli.symlink_to(venv_path / 'bin' / 'macf_tools')
        return

    if force_reinstall:
        log("MACF_FORCE_REINSTALL=1 — bypassing sentinel, full reinstall")
    log("Installing MACF into /opt/maceff-venv (fingerprint changed or first run; expect 2-3 min)...")

    # Install with uv (editable — links against the bind-mounted /opt/macf_tools)
    run_command(['uv', 'pip', 'install', '--python', str(venv_path / 'bin' / 'python'), '-e', str(macf_tools_src)], check=False)

    # Install search service dependencies (INSTALL_EXTRA_DEPS).
    # These enable the warm-cache search service for 89x faster policy recommendations.
    log("Installing search service dependencies...")
    run_command(['uv', 'pip', 'install', '--python', str(venv_path / 'bin' / 'python'),
                 *INSTALL_EXTRA_DEPS], check=False)

    # Create global CLI symlink
    macf_cli = Path('/usr/local/bin/macf_tools')
    if not macf_cli.exists():
        macf_cli.symlink_to(venv_path / 'bin' / 'macf_tools')

    # Write sentinel — multi-line for human debuggability. If a future install
    # is interrupted before reaching this point, the missing/incomplete sentinel
    # naturally triggers a fresh reinstall on the next container start.
    sentinel_content = (
        f"fingerprint={fp}\n"
        f"python={sys.version.split()[0]}\n"
        f"installed_at={datetime.utcnow().isoformat()}Z\n"
        f"extra_deps={','.join(INSTALL_EXTRA_DEPS)}\n"
    )
    sentinel.write_text(sentinel_content)
    log(f"MACF install complete; sentinel written to {sentinel}")


def setup_shared_workspace_permissions() -> None:
    """Configure collaborative permissions on shared workspace."""
    ensure_group('agents_all')

    SHARED_WORKSPACE.mkdir(mode=0o1777, exist_ok=True)

    run_command(['chgrp', '-R', 'agents_all', str(SHARED_WORKSPACE)], check=False)
    run_command(['chmod', '-R', 'g+ws', str(SHARED_WORKSPACE)], check=False)
    run_command(['chmod', 'g+s', str(SHARED_WORKSPACE)], check=False)
    run_command(['chmod', '+t', str(SHARED_WORKSPACE)], check=False)

    # Log final permissions
    result = run_command(['stat', '-c', '%A %U %G %n', str(SHARED_WORKSPACE)], capture=True)
    log(f"shared_workspace perms: {result}")


def setup_policy_editors() -> None:
    """Setup policy editors group and permissions."""
    ensure_group('policyeditors')

    policies_dir = FRAMEWORK_ROOT / 'policies'

    run_command(['chgrp', '-R', 'policyeditors', str(policies_dir)], check=False)
    run_command(['find', str(policies_dir), '-type', 'd', '-exec', 'chmod', '2770', '{}', '+'], check=False)
    run_command(['find', str(policies_dir), '-type', 'f', '-exec', 'chmod', '0660', '{}', '+'], check=False)

    # Add configured policy editors
    policy_editors = os.getenv('POLICY_EDITORS', '').split()
    for editor_user in policy_editors:
        if user_exists(editor_user):
            run_command(['usermod', '-a', '-G', 'policyeditors', editor_user])


def setup_policies() -> None:
    """Auto-deploy base policies if current symlink not present."""
    policies_dir = FRAMEWORK_ROOT / 'policies'
    current_link = policies_dir / 'current'

    if not current_link.exists():
        log("Creating policies/current symlink to base set...")
        base_policies = policies_dir / 'sets' / 'base'
        if base_policies.exists():
            current_link.symlink_to(base_policies)
            log("Policies deployed (symlink created)")
    else:
        log("Policies already deployed (current symlink exists)")


def build_policy_index(agents_config: AgentsConfig) -> None:
    """Build policy index for first PA user.

    Creates ~/.maceff/policy_index.db with FTS5 and embedding tables
    for hybrid search. Required for search service to provide recommendations.
    """
    if not agents_config.agents:
        log("No agents configured, skipping policy index build")
        return

    # Get first PA username
    first_agent_name = list(agents_config.agents.keys())[0]
    first_agent = agents_config.agents[first_agent_name]
    pa_username = first_agent.username or f"pa_{first_agent_name}"

    log(f"Building policy index as {pa_username}...")
    try:
        result = subprocess.run(
            ['su', '-', pa_username, '-c',
             '/opt/maceff-venv/bin/macf_tools policy build_index'],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            log("Policy index built successfully")
        else:
            log(f"Policy index build warning: {result.stderr or result.stdout or 'unknown'}")
    except subprocess.TimeoutExpired:
        log("Policy index build timed out (non-fatal) - will retry on first search")
    except Exception as e:
        log(f"Policy index build failed (non-fatal): {e}")


def start_search_service_daemon(agents_config: AgentsConfig) -> None:
    """Start search service daemon as first PA user (background process).

    The search service provides 89x faster policy recommendations by keeping
    the sentence-transformers model warm in memory.
    """
    if not agents_config.agents:
        log("No agents configured, skipping search service")
        return

    # Get first PA username
    first_agent_name = list(agents_config.agents.keys())[0]
    first_agent = agents_config.agents[first_agent_name]
    pa_username = first_agent.username or f"pa_{first_agent_name}"

    log(f"Starting search service daemon as {pa_username}...")
    try:
        # Start as background daemon using su
        result = subprocess.run(
            ['su', '-', pa_username, '-c',
             '/opt/maceff-venv/bin/python -m macf.search_service.daemon --daemon'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            log("Search service daemon started successfully")
        else:
            log(f"Search service start warning: {result.stderr or 'unknown'}")
    except Exception as e:
        log(f"Search service start failed (non-fatal): {e}")


def propagate_container_env(agents_config: Optional[AgentsConfig] = None) -> None:
    """Propagate container environment to all session types.

    Writes to /etc/environment (PAM reads this for SSH sessions):
    - MACEFF_TZ: Timezone from docker-compose.yml (if set)
    - MACEFF_ROOT_DIR: Framework root (constant /opt/maceff)
    - BASH_ENV: Points to /etc/profile.d/maceff-bash-env.sh
    - Plus all keys declared in agents_config.defaults.container_env
      (deployment-wide env, formerly required Dockerfile ENV + triple-write)

    Also writes:
    - /etc/profile.d/maceff-deployment-env.sh (login-shell exports)
    - /etc/profile.d/maceff-bash-env.sh (BASH_ENV target — sources both
      ~/.bash_init.sh AND the deployment-env file so non-login bash
      `bash -c "..."` invocations also see the deployment env)

    Per-agent overrides intentionally not supported: container env is
    process-wide; per-user env belongs in ~/.bash_init.sh.

    Args:
        agents_config: AgentsConfig with optional defaults.container_env.
            When None or defaults absent, behaves identically to the
            pre-v0.5.x version — only the framework's own static keys
            (MACEFF_TZ / MACEFF_ROOT_DIR / BASH_ENV) get written.
    """
    # Pull deployment env from agents.yaml defaults block
    deployment_env: Dict[str, str] = {}
    if agents_config is not None and agents_config.defaults is not None:
        deployment_env = dict(agents_config.defaults.container_env or {})

    env_file = Path('/etc/environment')
    lines = env_file.read_text().splitlines() if env_file.exists() else []

    # Filter out entries we'll rewrite — both the framework's static keys
    # and any deployment-declared keys (so agents.yaml edits propagate
    # correctly across container restarts).
    filter_prefixes = (
        'MACEFF_TZ=', 'MACEFF_ROOT_DIR=', 'BASH_ENV=',
        *(f'{k}=' for k in deployment_env),
    )
    lines = [line for line in lines if not any(line.startswith(p) for p in filter_prefixes)]

    # Add container-wide environment variables
    maceff_tz = os.getenv('MACEFF_TZ')
    if maceff_tz:
        lines.append(f'MACEFF_TZ={maceff_tz}')

    # Framework root - constant for all PAs
    lines.append('MACEFF_ROOT_DIR=/opt/maceff')

    # Deployment-declared env vars from agents.yaml.defaults.container_env
    for key in sorted(deployment_env):
        # Quote values containing spaces/special chars; bare otherwise (PAM-safe)
        value = deployment_env[key]
        lines.append(f'{key}={value}' if all(c.isalnum() or c in '_-/.:' for c in value)
                     else f'{key}="{value}"')

    # Write the per-shell deployment-env script (login bash via /etc/profile.d/*)
    deployment_env_script = Path('/etc/profile.d/maceff-deployment-env.sh')
    if deployment_env:
        script_lines = [
            '#!/bin/bash',
            '# MacEff deployment env (declared in agents.yaml.defaults.container_env)',
            '# Sourced by login bash from /etc/profile.d/* and by non-login bash via',
            '# the BASH_ENV → /etc/profile.d/maceff-bash-env.sh chain.',
        ]
        for key in sorted(deployment_env):
            value = deployment_env[key]
            # Use shell-safe quoting for export
            script_lines.append(f'export {key}={shlex.quote(value)}')
        deployment_env_script.write_text('\n'.join(script_lines) + '\n')
        deployment_env_script.chmod(0o755)
    elif deployment_env_script.exists():
        # No deployment env declared — clean up stale script from a prior run
        deployment_env_script.unlink()

    # BASH_ENV wrapper — sources both per-user .bash_init.sh AND the
    # deployment-env script so `bash -c "..."` (non-login, non-interactive)
    # invocations see deployment env. Without sourcing deployment-env here,
    # CC's Bash tool subprocesses would only see vars in container Config.Env
    # (which agents.yaml-driven vars aren't in by design).
    bash_env_wrapper = Path('/etc/profile.d/maceff-bash-env.sh')
    bash_env_wrapper.write_text('''#!/bin/bash
# MacEff BASH_ENV wrapper - sources deployment env + per-user bash_init.sh
# This script is pointed to by BASH_ENV in /etc/environment
if [ -f "/etc/profile.d/maceff-deployment-env.sh" ]; then
    . "/etc/profile.d/maceff-deployment-env.sh"
fi
if [ -f "$HOME/.bash_init.sh" ]; then
    . "$HOME/.bash_init.sh"
fi
''')
    bash_env_wrapper.chmod(0o644)
    lines.append('BASH_ENV=/etc/profile.d/maceff-bash-env.sh')

    env_file.write_text('\n'.join(lines) + '\n')
    extra_keys = ", ".join(sorted(deployment_env)) if deployment_env else "none"
    log(f"Container env propagated: MACEFF_TZ, MACEFF_ROOT_DIR, BASH_ENV; deployment env: {extra_keys}")

    # Write to /etc/profile.d for interactive shells (timezone only)
    if maceff_tz:
        profile_script = Path('/etc/profile.d/99-maceff-env.sh')
        profile_script.write_text(f'export MACEFF_TZ={maceff_tz!r}\n')
        profile_script.chmod(0o644)

        # Shell TZ bridge
        tz_bridge = Path('/etc/profile.d/maceff_tz.sh')
        tz_bridge.write_text('# Set TZ for interactive shells based on project MACEFF_TZ\n[ -n "$MACEFF_TZ" ] && export TZ="$MACEFF_TZ"\n')
        tz_bridge.chmod(0o644)


def main() -> int:
    """
    Container startup entry point.

    Loads agents.yaml and projects.yaml, validates with Pydantic models,
    creates users and directory structures, installs contexts and policies,
    sets up shared workspace, and starts sshd.

    Returns:
        0 on success, 1 on error
    """
    try:
        # Generate SSH host keys
        run_command(['ssh-keygen', '-A'], check=False)

        # Create base groups
        ensure_group('agents_all')
        ensure_group('sa_all')

        # Clean admin home if requested
        if os.getenv('CLEAN_ADMIN_HOME') == '1':
            run_command(['rm', '-rf', '/home/admin'], check=False)

        # Setup shared workspace
        setup_shared_workspace_permissions()

        # Load and validate agents configuration
        log("Loading agents.yaml...")
        if not AGENTS_CONFIG.exists():
            log(f"ERROR: {AGENTS_CONFIG} not found")
            return 1

        with open(AGENTS_CONFIG) as f:
            agents_yaml = yaml.safe_load(f)

        try:
            agents_config = AgentsConfig(**agents_yaml)
        except ValidationError as e:
            log(f"ERROR: Invalid agents.yaml configuration:")
            log(str(e))
            return 1

        log(f"Validated {len(agents_config.agents)} agents, {len(agents_config.subagents)} subagent types")

        # Load and validate projects configuration
        log("Loading projects.yaml...")
        if not PROJECTS_CONFIG.exists():
            log(f"WARNING: {PROJECTS_CONFIG} not found, skipping project setup")
            projects_config = None
        else:
            with open(PROJECTS_CONFIG) as f:
                projects_yaml = yaml.safe_load(f)

            try:
                projects_config = ProjectsConfig(**projects_yaml)
            except ValidationError as e:
                log(f"ERROR: Invalid projects.yaml configuration:")
                log(str(e))
                return 1

            log(f"Validated {len(projects_config.projects)} projects")

        # Extract defaults
        defaults_dict = None
        if agents_config.defaults:
            defaults_dict = agents_config.defaults.model_dump()

        # Create Primary Agents
        for agent_name, agent_spec in agents_config.agents.items():
            log(f"Setting up PA: {agent_spec.username}")

            # Create user
            create_pa_user(agent_name, agent_spec, defaults_dict)

            # Create agent tree
            create_agent_tree(agent_spec.username, agent_spec, defaults_dict)

            # Create personal policies directory (highest precedence layer)
            create_personal_policies(agent_spec.username)

            # Install three-layer context
            install_three_layer_context(agent_spec.username, agent_spec)

            # Create Subagent workspaces
            if agent_spec.subagents:
                for sa_name in agent_spec.subagents:
                    if sa_name in agents_config.subagents:
                        sa_spec = agents_config.subagents[sa_name]
                    else:
                        # Framework-provided subagent: create workspace using defaults
                        log(f"Subagent '{sa_name}' not in subagents section, using defaults")
                        default_ca = defaults_dict.get('consciousness_artifacts') if defaults_dict else None
                        ca_config = ConsciousnessArtifactsConfig(**default_ca) if default_ca else None
                        sa_spec = SubagentSpec(
                            role="Framework-provided specialist",
                            tool_access="Read, Write, Edit, Bash, Glob, Grep",
                            consciousness_artifacts=ca_config
                        )
                    log(f"Creating workspace: {agent_spec.username}/{sa_name}")
                    create_subagent_workspace(agent_spec.username, sa_name, sa_spec)

                # Create symlinks to SUBAGENT_DEF.md
                create_subagent_definition_symlinks(agent_spec.username, agent_spec.subagents)

                # Validate SUBAGENT_DEF.md files are non-empty (catches misconfigured names)
                home = Path(f'/home/{agent_spec.username}')
                for sa_name in agent_spec.subagents:
                    sa_def = home / 'agent' / 'subagents' / sa_name / 'SUBAGENT_DEF.md'
                    if sa_def.exists() and sa_def.stat().st_size == 0:
                        log(f"WARNING: {sa_def} is empty - delegation to '{sa_name}' will fail. "
                            f"Check that framework/subagents/{sa_name}.md exists.")

        # Create project workspaces
        if projects_config:
            for project_name, project_spec in projects_config.projects.items():
                log(f"Setting up project: {project_name}")
                create_project_workspace(project_name, project_spec)

        # Create workspace structure with worktrees for assigned projects
        for agent_name, agent_spec in agents_config.agents.items():
            if agent_spec.assigned_projects:
                create_workspace_structure(agent_spec.username, agent_spec.assigned_projects, projects_config)

        # Install MACF tools
        install_macf_tools()

        # Initialize agents with macf_tools
        initialize_agents(agents_config)

        # Install SSH key for admin
        install_ssh_key('admin')

        # Setup policies
        setup_policies()
        setup_policy_editors()

        # Propagate environment (passes agents_config so deployment env from
        # agents.yaml.defaults.container_env is fanned out to /etc/environment +
        # /etc/profile.d/maceff-deployment-env.sh + sourced by BASH_ENV wrapper)
        propagate_container_env(agents_config)

        # Start sshd EARLY so SSH access is available during slow init steps
        log("Starting sshd (background)...")
        import subprocess as _sp
        sshd_proc = _sp.Popen(['/usr/sbin/sshd', '-D'])
        log(f"sshd started (pid {sshd_proc.pid})")

        # Build policy index for first PA (required for search service)
        build_policy_index(agents_config)

        # Start search service daemon for first PA (background process)
        start_search_service_daemon(agents_config)

        log("Startup complete")
        log("Run 'python scripts/deploy.py install' to deploy repos and worktrees")

        # Wait on sshd (keeps container alive)
        sshd_proc.wait()

    except Exception as e:
        log(f"FATAL ERROR during startup: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
