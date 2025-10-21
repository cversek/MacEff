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
import subprocess
import pwd
import grp
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

import yaml
from pydantic import ValidationError

# Add macf package to path for model imports
sys.path.insert(0, '/opt/macf_tools/src')

from macf.models.agent_spec import AgentsConfig, AgentSpec, SubagentSpec
from macf.models.project_spec import ProjectsConfig, ProjectSpec


# Configuration paths
AGENTS_CONFIG = Path('/etc/maceff/agents.yaml')
PROJECTS_CONFIG = Path('/etc/maceff/projects.yaml')
FRAMEWORK_ROOT = Path('/opt/maceff/framework')
SHARED_WORKSPACE = Path('/shared_workspace')


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
        log(f"Command failed: {' '.join(cmd)}")
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


def create_pa_user(agent_spec: AgentSpec) -> None:
    """Create Primary Agent Linux user."""
    username = agent_spec.username

    if not user_exists(username):
        run_command(['useradd', '-m', '-s', '/bin/bash', username])
        run_command(['usermod', '-aG', 'agents_all', username])
        log(f"PA user created: {username}")

    # Ensure home directory exists with correct permissions
    home_dir = Path(f'/home/{username}')
    home_dir.mkdir(mode=0o755, exist_ok=True)
    run_command(['chown', f'{username}:{username}', str(home_dir)])

    # Install SSH key if present
    install_ssh_key(username)

    # Configure Claude Code to maintain working directory
    configure_claude_settings(username)


def install_ssh_key(username: str) -> None:
    """Install SSH key for user if available."""
    if not user_exists(username):
        return

    ssh_dir = Path(f'/home/{username}/.ssh')
    key_file = Path(f'/keys/{username}.pub')

    if key_file.exists():
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        run_command(['chown', f'{username}:{username}', str(ssh_dir)])

        authorized_keys = ssh_dir / 'authorized_keys'
        run_command(['cp', str(key_file), str(authorized_keys)])
        run_command(['chown', f'{username}:{username}', str(authorized_keys)])
        run_command(['chmod', '600', str(authorized_keys)])
        log(f"SSH key installed: {username}")


def configure_claude_settings(username: str) -> None:
    """Configure Claude Code settings for agent."""
    claude_dir = Path(f'/home/{username}/.claude')
    claude_dir.mkdir(mode=0o755, exist_ok=True)

    settings_file = claude_dir / 'settings.json'
    settings = {
        'env': {
            'CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR': '1'
        }
    }

    settings_file.write_text(json.dumps(settings, indent=2))
    run_command(['chown', '-R', f'{username}:{username}', str(claude_dir)])


def create_agent_tree(username: str, agent_spec: AgentSpec, defaults_config: Optional[Dict]) -> None:
    """Create agent directory structure with consciousness artifacts."""
    home = Path(f'/home/{username}')
    agent = home / 'agent'

    # Create root agent directory (read-only parent)
    agent.mkdir(mode=0o555, exist_ok=True)
    run_command(['chown', 'root:root', str(agent)])

    # Create private and public directories
    private = agent / 'private'
    public = agent / 'public'

    private.mkdir(mode=0o750, exist_ok=True)
    public.mkdir(mode=0o755, exist_ok=True)

    run_command(['chown', f'{username}:{username}', str(private)])
    run_command(['chown', f'{username}:{username}', str(public)])

    # Create consciousness artifact directories
    ca_config = agent_spec.consciousness_artifacts
    if ca_config is None and defaults_config:
        ca_config = defaults_config.get('consciousness_artifacts')

    if ca_config:
        # Private artifacts
        if ca_config.private:
            for artifact_type in ca_config.private:
                artifact_dir = private / artifact_type
                artifact_dir.mkdir(mode=0o750, exist_ok=True)
                run_command(['chown', f'{username}:{username}', str(artifact_dir)])

        # Public artifacts
        if ca_config.public:
            for artifact_type in ca_config.public:
                artifact_dir = public / artifact_type
                artifact_dir.mkdir(mode=0o755, exist_ok=True)
                run_command(['chown', f'{username}:{username}', str(artifact_dir)])

    # Create subagents directory (read-only parent)
    subagents = agent / 'subagents'
    subagents.mkdir(mode=0o555, exist_ok=True)
    run_command(['chown', 'root:root', str(subagents)])


def create_subagent_workspace(username: str, sa_name: str, sa_spec: SubagentSpec) -> None:
    """Create Subagent workspace within PA agent tree."""
    home = Path(f'/home/{username}')
    sa_root = home / 'agent' / 'subagents' / sa_name

    # Create subagent root (read-only parent)
    sa_root.mkdir(mode=0o555, exist_ok=True)
    run_command(['chown', 'root:root', str(sa_root)])

    # Create SUBAGENT_DEF.md placeholder
    sa_def = sa_root / 'SUBAGENT_DEF.md'
    if not sa_def.exists():
        sa_def.touch(mode=0o644)
        run_command(['chown', 'root:root', str(sa_def)])

    # Create private and public directories
    private = sa_root / 'private'
    public = sa_root / 'public'
    assigned = sa_root / 'assigned'

    private.mkdir(mode=0o750, exist_ok=True)
    public.mkdir(mode=0o750, exist_ok=True)
    assigned.mkdir(mode=0o755, exist_ok=True)

    run_command(['chown', f'{username}:{username}', str(private)])
    run_command(['chown', f'{username}:{username}', str(public)])
    run_command(['chown', f'{username}:{username}', str(assigned)])

    # Create consciousness artifact directories for SA
    ca_config = sa_spec.consciousness_artifacts

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


def install_three_layer_context(username: str, agent_spec: AgentSpec) -> None:
    """Install three-layer CLAUDE.md context (System/Identity/Project)."""
    home = Path(f'/home/{username}')
    claude_dir = home / '.claude'
    claude_dir.mkdir(mode=0o755, exist_ok=True)

    # Layer 1 (System): Symlink to framework SYSTEM_PREAMBLE.md
    system_layer = claude_dir / 'CLAUDE.md'
    system_source = FRAMEWORK_ROOT / 'templates' / 'SYSTEM_PREAMBLE.md'

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
    project_dir.mkdir(mode=0o775, exist_ok=True)

    # Install project CLAUDE.md (Layer 3 context)
    project_context = project_dir / 'CLAUDE.md'
    context_source = FRAMEWORK_ROOT / project_spec.context

    if context_source.exists() and not project_context.exists():
        run_command(['cp', str(context_source), str(project_context)])

    # Create repos directory
    if project_spec.repos:
        repos_dir = project_dir / 'repos'
        repos_dir.mkdir(mode=0o775, exist_ok=True)

        # Clone repositories
        for repo_mount in project_spec.repos:
            repo_path = project_dir / repo_mount.path
            if not repo_path.exists():
                log(f"Cloning {repo_mount.url} to {repo_path}")
                repo_path.parent.mkdir(parents=True, exist_ok=True)
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


def create_workspace_symlinks(username: str, assigned_projects: List[str]) -> None:
    """Create workspace symlinks to shared projects."""
    home = Path(f'/home/{username}')
    workspace = home / 'workspace'
    workspace.mkdir(mode=0o755, exist_ok=True)

    for project_name in assigned_projects:
        project_link = workspace / project_name
        project_target = SHARED_WORKSPACE / project_name

        if project_target.exists() and not project_link.exists():
            project_link.symlink_to(project_target)
            log(f"Workspace symlink created: {username} -> {project_name}")


def initialize_agents(agents_config: AgentsConfig) -> None:
    """Initialize Primary Agent with macf_tools."""
    for agent_name, agent_spec in agents_config.agents.items():
        username = agent_spec.username

        # Run macf_tools agent init
        cmd = f'su - {username} -c "macf_tools agent init"'
        result = subprocess.run(cmd, shell=True, capture_output=True)

        if result.returncode == 0:
            log(f"PA initialized: {username}")
        else:
            log(f"PA init skipped for {username} (may already exist)")


def install_macf_tools() -> None:
    """Install MACF tools in shared venv."""
    macf_tools_src = Path('/opt/macf_tools')

    if not macf_tools_src.exists():
        log("MACF tools source not found, skipping installation")
        return

    log("Installing MACF into /opt/maceff-venv...")
    venv_path = Path('/opt/maceff-venv')

    # Create venv if needed
    if not (venv_path / 'bin' / 'python').exists():
        run_command(['python3', '-m', 'venv', str(venv_path)])
        run_command([str(venv_path / 'bin' / 'python'), '-m', 'pip', '-q', 'install', '--upgrade', 'pip'])

    # Install with uv
    run_command(['uv', 'pip', 'install', '--python', str(venv_path / 'bin' / 'python'), '-e', str(macf_tools_src)], check=False)

    # Create global CLI symlink
    macf_cli = Path('/usr/local/bin/macf_tools')
    if not macf_cli.exists():
        macf_cli.symlink_to(venv_path / 'bin' / 'macf_tools')


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


def propagate_container_env() -> None:
    """Propagate container environment to SSH sessions."""
    maceff_tz = os.getenv('MACEFF_TZ')

    if maceff_tz:
        # Write to /etc/environment for PAM
        env_file = Path('/etc/environment')
        lines = env_file.read_text().splitlines() if env_file.exists() else []
        lines = [line for line in lines if not line.startswith('MACEFF_TZ=')]
        lines.append(f'MACEFF_TZ={maceff_tz}')
        env_file.write_text('\n'.join(lines) + '\n')

        # Write to /etc/profile.d for interactive shells
        profile_script = Path('/etc/profile.d/99-maceff-env.sh')
        profile_script.write_text(f'export MACEFF_TZ={maceff_tz!r}\n')
        profile_script.chmod(0o644)

        # Shell TZ bridge
        tz_bridge = Path('/etc/profile.d/maceff_tz.sh')
        tz_bridge.write_text('# Set TZ for interactive shells based on project MACEFF_TZ\n[ -n "$MACEFF_TZ" ] && export TZ="$MACEFF_TZ"\n')
        tz_bridge.chmod(0o644)


def main() -> int:
    """Main startup orchestration."""
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
            create_pa_user(agent_spec)

            # Create agent tree
            create_agent_tree(agent_spec.username, agent_spec, defaults_dict)

            # Install three-layer context
            install_three_layer_context(agent_spec.username, agent_spec)

            # Create Subagent workspaces
            if agent_spec.subagents:
                for sa_name in agent_spec.subagents:
                    if sa_name not in agents_config.subagents:
                        log(f"WARNING: Subagent '{sa_name}' not defined in subagents section")
                        continue

                    sa_spec = agents_config.subagents[sa_name]
                    log(f"Creating workspace: {agent_spec.username}/{sa_name}")
                    create_subagent_workspace(agent_spec.username, sa_name, sa_spec)

                # Create symlinks to SUBAGENT_DEF.md
                create_subagent_definition_symlinks(agent_spec.username, agent_spec.subagents)

        # Create project workspaces
        if projects_config:
            for project_name, project_spec in projects_config.projects.items():
                log(f"Setting up project: {project_name}")
                create_project_workspace(project_name, project_spec)

        # Create workspace symlinks for assigned projects
        for agent_name, agent_spec in agents_config.agents.items():
            if agent_spec.assigned_projects:
                create_workspace_symlinks(agent_spec.username, agent_spec.assigned_projects)

        # Install MACF tools
        install_macf_tools()

        # Initialize agents with macf_tools
        initialize_agents(agents_config)

        # Install SSH key for admin
        install_ssh_key('admin')

        # Setup policies
        setup_policies()
        setup_policy_editors()

        # Propagate environment
        propagate_container_env()

        log("Startup complete, starting sshd...")
        os.execv('/usr/sbin/sshd', ['/usr/sbin/sshd', '-D'])

    except Exception as e:
        log(f"FATAL ERROR during startup: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
