# tools/src/maceff/cli.py
import argparse, json, os, sys, glob, platform, socket
from pathlib import Path
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

try:
    from importlib.metadata import version
    _ver = version("macf")
except Exception:
    _ver = "0.0.0"

from .config import ConsciousnessConfig
from .hooks.compaction import detect_compaction, inject_recovery
from .agent_events_log import append_event
from .event_queries import get_cycle_number_from_events
from .utils import (
    get_current_session_id,
    get_dev_scripts_dir,
    get_formatted_timestamp,
    get_token_info,
    extract_current_git_hash,
    get_claude_code_version,
    get_temporal_context,
    detect_auto_mode,
    find_agent_home,
    get_env_var_report,
    get_agent_identity
)

# -------- helpers --------
def _pick_tz():
    """Prefer MACEFF_TZ, then TZ, else system local; fall back to UTC."""
    for key in ("MACEFF_TZ", "TZ"):
        name = os.getenv(key)
        if name and ZoneInfo is not None:
            try:
                return ZoneInfo(name)
            except Exception:
                pass
    try:
        return datetime.now().astimezone().tzinfo or timezone.utc
    except Exception:
        return timezone.utc

def _now_iso(tz=None):
    tz = tz or _pick_tz()
    return datetime.now(tz).replace(microsecond=0).isoformat()

def _format_time_ago(file_path: Path) -> str:
    """Format time ago string for a file."""
    try:
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=_pick_tz())
        now = datetime.now(_pick_tz())
        delta = now - mtime
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        return f"{hours}h {minutes}m ago"
    except Exception:
        return "unknown"

# -------- commands --------
def cmd_env(args: argparse.Namespace) -> int:
    """Print comprehensive environment summary."""
    temporal = get_temporal_context()
    session_id = get_current_session_id()

    # Get agent home path
    try:
        agent_home = find_agent_home()
    except Exception:
        agent_home = None

    # Count installed hooks (in .claude/hooks/)
    hooks_dir = agent_home / ".claude" / "hooks" if agent_home else None
    hooks_count = len(list(hooks_dir.glob("*.py"))) if hooks_dir and hooks_dir.exists() else 0

    # Get auto mode status
    auto_enabled, _, _ = detect_auto_mode(session_id)

    # Resolve paths safely
    def resolve_path(p):
        try:
            return str(p.resolve()) if p and p.exists() else str(p) if p else "(not set)"
        except Exception:
            return str(p) if p else "(not set)"

    # Get agent identity
    agent_identity = get_agent_identity()

    # Gather all data
    data = {
        "identity": {
            "agent_id": agent_identity
        },
        "versions": {
            "macf": _ver,
            "claude_code": get_claude_code_version() or "(unavailable)",
            "python_path": sys.executable,
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        },
        "time": {
            "local": temporal.get("timestamp_formatted", _now_iso()),
            "utc": datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S"),
            "timezone": temporal.get("timezone", "UTC")
        },
        "paths": {
            "agent_home": resolve_path(agent_home),
            "event_log": resolve_path(agent_home / ".maceff" / "agent_events_log.jsonl") if agent_home else "(not set)",
            "hooks_dir": resolve_path(hooks_dir),
            "checkpoints_dir": resolve_path(agent_home / "agent" / "private" / "checkpoints") if agent_home else "(not set)",
            "settings_local": resolve_path(agent_home / ".claude" / "settings.local.json") if agent_home else "(not set)"
        },
        "session": {
            "session_id": session_id or "(unknown)",
            "cycle": get_cycle_number_from_events(),
            "git_hash": extract_current_git_hash() or "(unknown)"
        },
        "system": {
            "platform": platform.system().lower(),
            "os_version": f"{platform.system()} {platform.release()}",
            "cwd": str(Path.cwd().resolve()),
            "hostname": socket.gethostname()
        },
        "environment": get_env_var_report(),
        "config": {
            "hooks_installed": hooks_count,
            "auto_mode": auto_enabled
        }
    }

    # Output format
    if getattr(args, 'json', False):
        # Convert tuple to dict for JSON serialization
        key_vars, extra_vars = data['environment']
        data['environment'] = {"key": key_vars, "extra": extra_vars}
        print(json.dumps(data, indent=2))
    else:
        # Pretty-print format
        line = "━" * 80
        print(line)

        print("Agent ID")
        print(f"  {data['identity']['agent_id']}")
        print()

        print("Versions")
        print(f"  MACF:         {data['versions']['macf']}")
        print(f"  Claude Code:  {data['versions']['claude_code']}")
        print(f"  Python:       {data['versions']['python_path']} ({data['versions']['python_version']})")
        print()

        print("Time")
        print(f"  Local:        {data['time']['local']}")
        print(f"  UTC:          {data['time']['utc']}")
        print(f"  Timezone:     {data['time']['timezone']}")
        print()

        print("Paths")
        print(f"  Agent Home:   {data['paths']['agent_home']}")
        print(f"  Event Log:    {data['paths']['event_log']}")
        print(f"  Hooks Dir:    {data['paths']['hooks_dir']}")
        print(f"  Checkpoints:  {data['paths']['checkpoints_dir']}")
        print(f"  Settings:     {data['paths']['settings_local']}")
        print()

        print("Session")
        print(f"  Session ID:   {data['session']['session_id']}")
        print(f"  Cycle:        {data['session']['cycle']}")
        print(f"  Git Hash:     {data['session']['git_hash']}")
        print()

        print("System")
        print(f"  Platform:     {data['system']['platform']}")
        print(f"  OS:           {data['system']['os_version']}")
        print(f"  CWD:          {data['system']['cwd']}")
        print(f"  Hostname:     {data['system']['hostname']}")
        print()

        print("Environment")
        key_vars, extra_vars = data['environment']
        for k, v in key_vars.items():
            print(f"  {k}: {v}")
        if extra_vars:
            print("  ---")
            for k, v in extra_vars.items():
                print(f"  {k}: {v}")
        print()

        print("Config")
        print(f"  Hooks Installed: {data['config']['hooks_installed']}")
        print(f"  Auto Mode:       {data['config']['auto_mode']}")

        print(line)

    return 0

def cmd_time(_: argparse.Namespace) -> int:
    current_time = _now_iso()
    print(current_time)

    # Show gap since most recent CCP
    try:
        config = ConsciousnessConfig()
        checkpoints_path = config.get_checkpoints_path()
        if checkpoints_path.exists():
            # Find CCP files (multiple patterns for consciousness checkpoints)
            ccp_patterns = ["*_ccp.md", "*_CCP.md", "*_checkpoint.md"]
            ccp_files = []
            for pattern in ccp_patterns:
                ccp_files.extend(checkpoints_path.glob(pattern))
            ccp_files = sorted(ccp_files, key=lambda p: p.stat().st_mtime, reverse=True)
            if ccp_files:
                latest_ccp = ccp_files[0]
                ccp_mtime = datetime.fromtimestamp(latest_ccp.stat().st_mtime, tz=_pick_tz())
                now = datetime.now(_pick_tz())
                delta = now - ccp_mtime
                hours = int(delta.total_seconds() // 3600)
                minutes = int((delta.total_seconds() % 3600) // 60)
                print(f"Last CCP: {latest_ccp.name} ({hours}h {minutes}m ago)")
    except Exception:
        # Graceful fallback if CCP lookup fails
        pass

    return 0

def cmd_budget(_: argparse.Namespace) -> int:
    warn = float(os.getenv("MACEFF_TOKEN_WARN", "0.85"))
    hard = float(os.getenv("MACEFF_TOKEN_HARD", "0.95"))
    mode = os.getenv("MACEFF_BUDGET_MODE", "concise/default")
    payload = {"mode": mode, "thresholds": {"warn": warn, "hard": hard}}
    used = os.getenv("MACEFF_TOKEN_USED")
    if used is not None:
        try:
            payload["used"] = float(used)
        except ValueError:
            pass
    print(json.dumps(payload, indent=2))
    return 0

def cmd_list_ccps(args: argparse.Namespace) -> int:
    """List consciousness checkpoints with timestamps."""
    try:
        config = ConsciousnessConfig()
        checkpoints_path = config.get_checkpoints_path()

        if not checkpoints_path.exists():
            print("No checkpoints directory found")
            return 0

        # Find CCP files (multiple patterns for consciousness checkpoints)
        ccp_patterns = ["*_ccp.md", "*_CCP.md", "*_checkpoint.md"]
        ccp_files = []
        for pattern in ccp_patterns:
            ccp_files.extend(checkpoints_path.glob(pattern))
        ccp_files = sorted(ccp_files, key=lambda p: p.stat().st_mtime, reverse=True)

        if not ccp_files:
            print("No consciousness checkpoints found")
            return 0

        # Apply --recent limit if specified
        recent = getattr(args, 'recent', None)
        if recent is not None:
            ccp_files = ccp_files[:recent]

        for ccp_file in ccp_files:
            time_ago = _format_time_ago(ccp_file)
            print(f"{ccp_file.name} ({time_ago})")

    except Exception as e:
        print(f"Error listing CCPs: {e}")
        return 1

    return 0

def cmd_session_info(args: argparse.Namespace) -> int:
    """Show session information as JSON."""
    try:
        config = ConsciousnessConfig()
        session_id = get_current_session_id()

        # Get temp directory path using unified utils
        temp_dir = get_dev_scripts_dir(session_id)

        data = {
            "session_id": session_id,
            "agent_name": config.agent_name,
            "agent_id": config.agent_id,
            "agent_root": str(config.agent_root),
            "cwd": str(Path.cwd()),
            "temp_directory": str(temp_dir) if temp_dir else "unavailable",
            "checkpoints_path": str(config.get_checkpoints_path()),
            "reflections_path": str(config.get_reflections_path())
        }

        print(json.dumps(data, indent=2))

    except Exception as e:
        print(f"Error getting session info: {e}")
        return 1

    return 0


def _update_settings_file(settings_path: Path, hooks_prefix: str) -> bool:
    """Update settings.json with hooks configuration, merging existing settings."""
    try:
        # Load existing settings or create new
        if settings_path.exists():
            with open(settings_path) as f:
                settings = json.load(f)
        else:
            settings = {}

        # Ensure hooks section exists
        if "hooks" not in settings:
            settings["hooks"] = {}

        # All 10 hooks with their script names
        hook_configs = [
            ("SessionStart", "session_start.py"),
            ("UserPromptSubmit", "user_prompt_submit.py"),
            ("Stop", "stop.py"),
            ("SubagentStop", "subagent_stop.py"),
            ("PreToolUse", "pre_tool_use.py"),
            ("PostToolUse", "post_tool_use.py"),
            ("SessionEnd", "session_end.py"),
            ("PreCompact", "pre_compact.py"),
            ("PermissionRequest", "permission_request.py"),
            ("Notification", "notification.py"),
        ]

        # Register all hooks
        for hook_name, script_name in hook_configs:
            settings["hooks"][hook_name] = [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"{hooks_prefix}/{script_name}"
                        }
                    ]
                }
            ]

        # Backup existing file
        if settings_path.exists():
            backup_path = settings_path.with_suffix('.json.backup')
            settings_path.rename(backup_path)
            print(f"   Backed up existing settings to: {backup_path}")

        # Write updated settings
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)

        return True

    except Exception as e:
        print(f"Error updating settings: {e}")
        return False


def cmd_hook_install(args: argparse.Namespace) -> int:
    """Install all 10 consciousness hooks with local/global mode selection."""
    try:
        # Container detection (FP#27 fix - check /.dockerenv directly)
        in_container = Path("/.dockerenv").exists()

        # Determine installation mode
        if in_container:
            # Container: force global mode, no interactive prompt (FP#27)
            mode = 'global'
        elif hasattr(args, 'global_install') and args.global_install:
            mode = 'global'
        elif hasattr(args, 'local_install') and args.local_install:
            mode = 'local'
        else:
            # Interactive mode (host only)
            print("\nWhere do you want to install hooks?")
            print("[1] Local project (.claude/hooks/) [DEFAULT]")
            print("[2] Global user directory (~/.claude/hooks/)")
            choice = input("\nPress Enter for [1], or enter choice: ").strip() or "1"
            mode = 'global' if choice == '2' else 'local'

        # Set paths based on mode and environment
        if mode == 'global':
            hooks_dir = Path.home() / ".claude" / "hooks"
            settings_file = Path.home() / ".claude" / "settings.json"
            if in_container:
                # Container: absolute venv Python + absolute hook paths (FP#27)
                hooks_prefix = f"/opt/maceff-venv/bin/python {Path.home()}/.claude/hooks"
            else:
                hooks_prefix = "python ~/.claude/hooks"
        else:
            # Local mode (host only - container always uses global)
            hooks_dir = Path.cwd() / ".claude" / "hooks"
            settings_file = Path.cwd() / ".claude" / "settings.local.json"
            hooks_prefix = "python .claude/hooks"

        # Create hooks directory
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # All 10 hooks with their handler module names
        hooks_to_install = [
            ("session_start.py", "handle_session_start"),
            ("user_prompt_submit.py", "handle_user_prompt_submit"),
            ("stop.py", "handle_stop"),
            ("subagent_stop.py", "handle_subagent_stop"),
            ("pre_tool_use.py", "handle_pre_tool_use"),
            ("post_tool_use.py", "handle_post_tool_use"),
            ("session_end.py", "handle_session_end"),
            ("pre_compact.py", "handle_pre_compact"),
            ("permission_request.py", "handle_permission_request"),
            ("notification.py", "handle_notification"),
        ]

        # Find installed package location for handler modules
        import macf.hooks as hooks_package
        package_hooks_dir = Path(hooks_package.__file__).parent

        # Create symlinks to handler modules
        for script_name, handler_module in hooks_to_install:
            hook_script = hooks_dir / script_name
            handler_path = package_hooks_dir / f"{handler_module}.py"

            # Remove existing file/symlink if present
            if hook_script.exists() or hook_script.is_symlink():
                hook_script.unlink()

            # Create symlink to handler module
            hook_script.symlink_to(handler_path)

        # Update settings file
        if _update_settings_file(settings_file, hooks_prefix):
            print(f"\n✅ All 10 hooks installed successfully!")
            print(f"   Mode: {mode}")
            print(f"   Directory: {hooks_dir}")
            print(f"   Settings: {settings_file}")
            print(f"\n   Hooks installed:")
            for script_name, _ in hooks_to_install:
                print(f"   - {script_name}")
            print(f"\nConsciousness infrastructure will activate on next session.")
            return 0
        else:
            print(f"\n❌ Hook scripts created but settings update failed")
            print(f"   Manually add to {settings_file}")
            return 1

    except Exception as e:
        print(f"Error installing hooks: {e}")
        return 1


def cmd_framework_install(args: argparse.Namespace) -> int:
    """Install framework artifacts (hooks, commands, skills) to .claude directory."""
    try:
        import subprocess

        # Determine what to install
        hooks_only = getattr(args, 'hooks_only', False)
        skip_hooks = getattr(args, 'skip_hooks', False)

        # Find framework root (git repo root + /framework)
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=Path.cwd()
        )
        if result.returncode != 0:
            print("Error: Not in a git repository")
            return 1

        framework_root = Path(result.stdout.strip()) / "framework"
        if not framework_root.exists():
            print(f"Error: Framework directory not found at {framework_root}")
            return 1

        claude_dir = Path.cwd() / ".claude"
        commands_dir = claude_dir / "commands"
        skills_dir = claude_dir / "skills"

        installed_count = {"hooks": 0, "commands": 0, "skills": 0}

        # Install hooks (unless skip_hooks or already done via hooks_only)
        if not skip_hooks:
            print("\n📦 Installing hooks...")
            # Reuse existing hook install logic
            hooks_args = argparse.Namespace(local_install=True, global_install=False)
            hook_result = cmd_hook_install(hooks_args)
            if hook_result == 0:
                installed_count["hooks"] = 10
            else:
                print("   Warning: Hook installation had issues")

        if hooks_only:
            print(f"\n✅ Hooks-only installation complete")
            return 0

        # Install commands (symlink maceff_*.md files)
        print("\n📦 Installing commands...")
        commands_src = framework_root / "commands"
        if commands_src.exists():
            commands_dir.mkdir(parents=True, exist_ok=True)
            for cmd_file in commands_src.glob("maceff_*.md"):
                target = commands_dir / cmd_file.name
                if target.exists() or target.is_symlink():
                    target.unlink()
                target.symlink_to(cmd_file)
                installed_count["commands"] += 1
                print(f"   ✓ {cmd_file.name}")
        else:
            print(f"   No commands directory at {commands_src}")

        # Install skills (symlink maceff-*/ directories)
        print("\n📦 Installing skills...")
        skills_src = framework_root / "skills"
        if skills_src.exists():
            skills_dir.mkdir(parents=True, exist_ok=True)
            for skill_dir in skills_src.glob("maceff-*/"):
                if skill_dir.is_dir():
                    target = skills_dir / skill_dir.name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        else:
                            import shutil
                            shutil.rmtree(target)
                    target.symlink_to(skill_dir)
                    installed_count["skills"] += 1
                    print(f"   ✓ {skill_dir.name}/")
        else:
            print(f"   No skills directory at {skills_src}")

        # Summary
        print(f"\n✅ Framework installation complete!")
        print(f"   Hooks: {installed_count['hooks']}")
        print(f"   Commands: {installed_count['commands']}")
        print(f"   Skills: {installed_count['skills']}")

        return 0

    except Exception as e:
        print(f"Error installing framework: {e}")
        return 1


def cmd_hook_test(args: argparse.Namespace) -> int:
    """Test compaction detection on current session."""
    try:
        # Find current session JSONL file
        claude_dir = Path.home() / ".claude" / "projects"
        if not claude_dir.exists():
            print("No .claude/projects directory found")
            return 1

        all_jsonl_files = []
        for project_dir in claude_dir.iterdir():
            if project_dir.is_dir():
                jsonl_files = list(project_dir.glob("*.jsonl"))
                all_jsonl_files.extend(jsonl_files)

        if not all_jsonl_files:
            print("No JSONL transcript files found")
            return 1

        # Get most recently modified JSONL file
        latest_file = max(all_jsonl_files, key=lambda p: p.stat().st_mtime)

        print(f"Testing transcript: {latest_file.name}")

        # Check for compaction
        if detect_compaction(latest_file):
            print("✅ COMPACTION DETECTED")
            print(inject_recovery())
        else:
            print("❌ No compaction detected - session appears normal")

    except Exception as e:
        print(f"Error testing hook: {e}")
        return 1

    return 0


def cmd_hook_logs(args: argparse.Namespace) -> int:
    """Display hook event logs."""
    # Get session_id
    session_id = args.session if hasattr(args, 'session') and args.session else get_current_session_id()

    # Get agent_id
    config = ConsciousnessConfig()
    agent_id = config.agent_id

    # Get log path using unified utils
    log_dir = get_hooks_dir(session_id, create=False)
    if not log_dir:
        print(f"No logs found for session: {session_id}")
        return 1

    log_file = log_dir / "hook_events.log"
    if not log_file.exists():
        print(f"No hook events logged yet for session: {session_id}")
        return 0

    # Display logs
    print(f"Hook events for session {session_id} (agent: {agent_id}):\n")

    with open(log_file, 'r') as f:
        for line in f:
            try:
                event = json.loads(line)
                timestamp = event.get('timestamp', 'unknown')
                hook_name = event.get('hook_name', 'unknown')
                event_type = event.get('event_type', 'unknown')

                # Format based on event type
                if event_type == "HOOK_START":
                    print(f"[{timestamp}] {hook_name}: START")
                elif event_type == "HOOK_COMPLETE":
                    duration = event.get('duration_ms', '?')
                    print(f"[{timestamp}] {hook_name}: COMPLETE ({duration}ms)")
                elif event_type == "HOOK_ERROR":
                    error = event.get('error', 'unknown error')
                    print(f"[{timestamp}] {hook_name}: ERROR - {error}")
                elif event_type == "COMPACTION_CHECK":
                    detected = event.get('compaction_detected', False)
                    duration = event.get('duration_ms', '?')
                    print(f"[{timestamp}] {hook_name}: Compaction={'DETECTED' if detected else 'not detected'} ({duration}ms)")
                elif event_type == "TRANSCRIPT_FOUND":
                    transcript_name = event.get('transcript_name', 'unknown')
                    print(f"[{timestamp}] {hook_name}: Found transcript {transcript_name}")
                else:
                    print(f"[{timestamp}] {hook_name}: {event_type}")

            except json.JSONDecodeError:
                print(f"Invalid log entry: {line.strip()}")

    return 0


def cmd_hook_status(args: argparse.Namespace) -> int:
    """Display current hook sidecar states."""
    from .hooks.sidecar import read_sidecar

    # Get session_id
    session_id = get_current_session_id()

    # Get agent_id
    config = ConsciousnessConfig()
    agent_id = config.agent_id

    # Get hooks directory using unified utils
    hooks_dir = get_hooks_dir(session_id, create=False)
    if not hooks_dir:
        print(f"No session directory found for: {session_id}")
        return 1

    print(f"Hook states for session {session_id} (agent: {agent_id}):\n")

    # Find all sidecar files
    sidecar_files = list(hooks_dir.glob("sidecar_*.json"))

    if not sidecar_files:
        print("No hook states recorded yet")
        return 0

    for sidecar_file in sidecar_files:
        hook_name = sidecar_file.stem.replace("sidecar_", "")
        state = read_sidecar(hook_name, session_id)

        print(f"Hook: {hook_name}")
        print(json.dumps(state, indent=2))
        print()

    return 0


def cmd_config_init(args: argparse.Namespace) -> int:
    """Initialize .macf/config.json with interactive prompts."""
    config_dir = Path.cwd() / '.macf'
    config_file = config_dir / 'config.json'

    if config_file.exists() and not args.force:
        print(f"Config file already exists: {config_file}")
        print("Use --force to overwrite")
        return 1

    # Interactive prompts
    print("Initialize MacEff agent configuration\n")
    moniker = input("Agent moniker (e.g., MyAgent): ").strip()
    if not moniker:
        print("Error: Moniker required")
        return 1

    agent_type = input("Agent type [primary_agent]: ").strip() or "primary_agent"
    description = input("Description: ").strip() or f"{moniker} agent"

    # Create config structure
    config = {
        "agent_identity": {
            "moniker": moniker,
            "type": agent_type,
            "description": description
        },
        "logging": {
            "enabled": True,
            "level": "INFO",
            "console_output": False
        },
        "hooks": {
            "capture_output": True,
            "sidecar_enabled": True
        }
    }

    # Write config file
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ Configuration created: {config_file}")
    print(f"   Agent moniker: {moniker}")
    print(f"   Logging paths: /tmp/macf_hooks/{moniker}/{{session_id}}/")

    return 0


def cmd_config_show(args: argparse.Namespace) -> int:
    """Display current configuration."""
    config = ConsciousnessConfig()

    print(f"Agent ID: {config.agent_id}")
    print(f"Agent Name: {config.agent_name}")
    print(f"Agent Root: {config.agent_root}")

    # Determine context
    if config._is_container():
        context = "container"
    elif config._is_host():
        context = "host"
    else:
        context = "fallback"
    print(f"Detection Context: {context}")

    # Load and display full config if available
    config_data = config.load_config()
    if config_data:
        print("\nFull configuration:")
        print(json.dumps(config_data, indent=2))
    else:
        print("\nNo .macf/config.json found (using defaults)")

    # Show computed paths
    print(f"\nComputed paths:")
    print(f"  Checkpoints: {config.get_checkpoints_path()}")
    print(f"  Reflections: {config.get_reflections_path()}")
    print(f"  Logs: /tmp/macf_hooks/{config.agent_id}/{{session_id}}/")

    return 0


def cmd_claude_config_init(args: argparse.Namespace) -> int:
    """Initialize .claude.json with recommended defaults."""
    try:
        settings_path = Path.home() / ".claude.json"

        # Read existing settings or create new
        if settings_path.exists():
            with open(settings_path, 'r') as f:
                settings = json.load(f)
            print(f"Updating existing .claude.json at {settings_path}")
        else:
            settings = {}
            print(f"Creating new .claude.json at {settings_path}")

        # Set recommended defaults
        settings['verbose'] = True
        settings['autoCompactEnabled'] = False

        # Write atomically via temp file
        temp_path = settings_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(settings, f, indent=2)
        temp_path.replace(settings_path)

        print("\n✅ Claude Code configuration updated:")
        print("   verbose: true")
        print("   autoCompactEnabled: false")
        print("\nChanges will take effect on next Claude Code session.")

        return 0

    except (OSError, json.JSONDecodeError, TypeError) as e:
        print(f"❌ Error updating .claude.json: {e}")
        return 1


def cmd_claude_config_show(args: argparse.Namespace) -> int:
    """Show current .claude.json configuration."""
    try:
        settings_path = Path.home() / ".claude.json"

        if not settings_path.exists():
            print(f"No .claude.json found at {settings_path}")
            print("\nRun 'macf_tools claude-config init' to create with defaults.")
            return 0

        with open(settings_path, 'r') as f:
            settings = json.load(f)

        print(f"Claude Code Configuration ({settings_path}):\n")
        print(json.dumps(settings, indent=2))

        return 0

    except (OSError, json.JSONDecodeError) as e:
        print(f"❌ Error reading .claude.json: {e}")
        return 1


def cmd_context(args: argparse.Namespace) -> int:
    """Show current token usage and CLUAC level."""
    try:
        # Get session_id from args or use current
        session_id = getattr(args, 'session', None)

        # Get token info
        token_info = get_token_info(session_id=session_id)

        # JSON output mode
        if getattr(args, 'json_output', False):
            print(json.dumps(token_info, indent=2))
            return 0

        # Human-readable format
        tokens_used = token_info['tokens_used']
        tokens_remaining = token_info['tokens_remaining']
        percentage_used = token_info['percentage_used']
        cluac_level = token_info['cluac_level']
        source = token_info['source']

        print(f"Token Usage: {tokens_used:,} / 200,000 ({percentage_used:.1f}%)")
        print(f"Remaining: {tokens_remaining:,} tokens")
        print(f"CLUAC Level: {cluac_level} (Context Left Until Auto-Compaction)")
        print(f"Source: {source}")

        return 0

    except Exception as e:
        print(f"Error getting token info: {e}")
        return 1


def cmd_statusline(args: argparse.Namespace) -> int:
    """Generate formatted statusline for Claude Code display."""
    from .utils.statusline import get_statusline_data, format_statusline

    try:
        # Check for CC JSON on stdin (non-blocking)
        cc_json = None
        if not sys.stdin.isatty():
            try:
                stdin_data = sys.stdin.read().strip()
                if stdin_data:
                    cc_json = json.loads(stdin_data)
            except (json.JSONDecodeError, Exception):
                # Ignore stdin parsing failures - use MACF data only
                pass

        # Gather statusline data
        data = get_statusline_data(cc_json=cc_json)

        # Format and output
        statusline = format_statusline(
            agent_name=data["agent_name"],
            project=data["project"],
            environment=data["environment"],
            tokens_used=data["tokens_used"],
            tokens_total=data["tokens_total"],
            cluac=data["cluac"]
        )

        print(statusline)
        return 0

    except Exception as e:
        print(f"Error generating statusline: {e}", file=sys.stderr)
        return 1


def cmd_statusline_install(args: argparse.Namespace) -> int:
    """Install statusline script and configure Claude Code settings."""
    from pathlib import Path
    import stat

    try:
        # Find .claude directory (project or global)
        cwd = Path.cwd()
        claude_dir = cwd / ".claude"

        if not claude_dir.exists():
            # Try global directory
            claude_dir = Path.home() / ".claude"
            if not claude_dir.exists():
                print("Error: No .claude directory found (checked project and ~/.claude)", file=sys.stderr)
                return 1

        # Create statusline.sh wrapper script
        script_path = claude_dir / "statusline.sh"
        script_content = """#!/bin/bash
# MacEff Statusline for Claude Code
exec macf_tools statusline
"""

        script_path.write_text(script_content)

        # Make executable
        script_path.chmod(script_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        # Update settings.local.json
        settings_path = claude_dir / "settings.local.json"

        # Read existing settings or create empty dict
        if settings_path.exists():
            settings = json.loads(settings_path.read_text())
        else:
            settings = {}

        # Add statusLine configuration
        settings["statusLine"] = {
            "type": "command",
            "command": ".claude/statusline.sh",
            "padding": 0
        }

        # Write back
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")

        print(f"✅ Statusline installed successfully:")
        print(f"   Script: {script_path}")
        print(f"   Settings: {settings_path}")
        print(f"\nRestart Claude Code to see the statusline.")

        return 0

    except Exception as e:
        print(f"Error installing statusline: {e}", file=sys.stderr)
        return 1


def cmd_breadcrumb(args: argparse.Namespace) -> int:
    """Generate fresh breadcrumb for current DEV_DRV."""
    from .utils import get_breadcrumb, parse_breadcrumb

    try:
        # Use the canonical get_breadcrumb() utility (DRY - single source of truth)
        breadcrumb = get_breadcrumb()

        # Output format based on flags
        if getattr(args, 'json_output', False):
            # Parse breadcrumb to extract components
            components = parse_breadcrumb(breadcrumb) or {}
            output = {
                "breadcrumb": breadcrumb,
                "components": components
            }
            print(json.dumps(output, indent=2))
        else:
            # Simple string output (default)
            print(breadcrumb)

        return 0

    except Exception as e:
        print(f"🏗️ MACF | ❌ Breadcrumb error: {e}", file=sys.stderr)
        return 1


def cmd_dev_drv(args: argparse.Namespace) -> int:
    """Extract and display DEV_DRV from JSONL using breadcrumb."""
    from .forensics.dev_drive import extract_dev_drive, render_markdown_summary, render_raw_jsonl
    from .utils import parse_breadcrumb

    try:
        # Parse breadcrumb
        breadcrumb_data = parse_breadcrumb(args.breadcrumb)
        if not breadcrumb_data:
            print(f"Error: Invalid breadcrumb format: {args.breadcrumb}")
            print("Expected format: s_abc12345/c_42/g_abc1234/p_def5678/t_1234567890")
            return 1

        # Extract DEV_DRV from JSONL
        drive = extract_dev_drive(
            session_id=breadcrumb_data['session_id'],
            prompt_uuid=breadcrumb_data['prompt_uuid'],
            breadcrumb_data=breadcrumb_data
        )

        if not drive:
            print(f"Error: Could not extract DEV_DRV for breadcrumb: {args.breadcrumb}")
            print(f"Session: {breadcrumb_data['session_id']}")
            print(f"Prompt: {breadcrumb_data['prompt_uuid']}")
            return 1

        # Render output based on format flag
        if args.raw:
            output = render_raw_jsonl(drive)
        else:
            # Default: markdown
            output = render_markdown_summary(drive)

        # Write to file or stdout
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(output)
            print(f"DEV_DRV written to: {output_path}")
        else:
            print(output)

        return 0

    except Exception as e:
        print(f"Error extracting DEV_DRV: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_backup_create(args: argparse.Namespace) -> int:
    """Create consciousness backup archive."""
    from .backup import get_backup_paths, collect_backup_sources, create_archive
    paths = get_backup_paths(output_dir=args.output)
    sources = collect_backup_sources(
        paths,
        include_transcripts=not args.no_transcripts,
        quick_mode=args.quick
    )
    archive_path = create_archive(sources, paths)
    print(f"Created: {archive_path}")
    return 0


def cmd_backup_list(args: argparse.Namespace) -> int:
    """List backup archives in directory."""
    from pathlib import Path
    import json
    scan_dir = args.dir or Path.cwd()
    archives = list(scan_dir.glob("*_consciousness.tar.xz"))
    if args.json_output:
        print(json.dumps([str(a) for a in archives], indent=2))
    else:
        for a in sorted(archives):
            print(a.name)
    return 0


def cmd_backup_info(args: argparse.Namespace) -> int:
    """Show backup archive info."""
    from .backup.archive import get_archive_manifest
    import json
    manifest = get_archive_manifest(args.archive)
    if manifest:
        if args.json_output:
            print(json.dumps(manifest, indent=2))
        else:
            print(f"Project: {manifest.get('project_name')}")
            print(f"Created: {manifest.get('created_at')}")
            print(f"Files: {manifest['totals']['file_count']}")
            print(f"Size: {manifest['totals']['total_bytes']} bytes")
    return 0


def cmd_restore_verify(args: argparse.Namespace) -> int:
    """Verify archive integrity."""
    from .backup.archive import get_archive_manifest, extract_archive
    from .backup.manifest import verify_manifest
    import tempfile
    manifest = get_archive_manifest(args.archive)
    if not manifest:
        print("No manifest found in archive")
        return 1
    with tempfile.TemporaryDirectory() as tmpdir:
        extract_archive(args.archive, Path(tmpdir))
        result = verify_manifest(manifest, Path(tmpdir))

    broken_symlinks = result.get("broken_symlinks", [])
    has_errors = not result["valid"]
    has_symlink_warnings = len(broken_symlinks) > 0

    if not has_errors and not has_symlink_warnings:
        print(f"Archive valid: {result['checked']} files verified")
        return 0

    if has_errors:
        print(f"Archive INVALID: {len(result['corrupted'])} corrupted, {len(result['missing'])} missing")
    else:
        print(f"Archive valid: {result['checked']} files verified")

    # Report broken symlinks (warning, not error)
    if has_symlink_warnings:
        print(f"\n⚠️  {len(broken_symlinks)} broken symlinks (targets don't exist on this system)")
        print("   These are hooks/commands pointing to source system paths.")
        print("   Use --transplant with 'restore install' to rewrite paths for this system:")
        print("   macf_tools agent restore install <archive> --target <dir> --transplant")
        if hasattr(args, 'verbose') and args.verbose:
            print("\n   Broken symlinks:")
            for s in broken_symlinks:
                print(f"     {s['path']} -> {s['target']}")

    if hasattr(args, 'verbose') and args.verbose:
        if result['missing']:
            print("\nMissing files:")
            for f in result['missing']:
                print(f"  - {f}")
        if result['corrupted']:
            print("\nCorrupted files:")
            for f in result['corrupted']:
                print(f"  - {f['path']}: expected {f['expected'][:8]}... got {f['actual'][:8]}...")

    return 1 if has_errors else 0


def cmd_restore_install(args: argparse.Namespace) -> int:
    """Install backup to target directory with optional transplant."""
    from .backup.archive import extract_archive, get_archive_manifest, list_archive
    from .backup.integrity import (
        has_existing_consciousness,
        detect_existing_consciousness,
        create_recovery_checkpoint,
        format_safety_warning,
    )

    target = args.target or Path.cwd()

    # Safety check: detect existing consciousness
    if has_existing_consciousness(target) and not args.force:
        checks = detect_existing_consciousness(target)
        print(format_safety_warning(checks))
        return 1

    if args.dry_run:
        contents = list_archive(args.archive)
        print(f"Would extract {len(contents)} items to {target}")

        if has_existing_consciousness(target):
            print("\nWould create recovery checkpoint before overwriting")

        if args.transplant:
            manifest = get_archive_manifest(args.archive)
            if manifest:
                from .backup.transplant import create_transplant_mapping
                maceff_root = args.maceff_root or (target.parent / "MacEff")
                mapping = create_transplant_mapping(manifest, target, maceff_root)
                print(f"\nTransplant would rewrite paths:")
                print(f"  Project: {mapping.source_project_root} -> {mapping.target_project_root}")
                print(f"  MacEff:  {mapping.source_maceff_root} -> {mapping.target_maceff_root}")
                print(f"  Home:    {mapping.source_home} -> {mapping.target_home}")
        return 0

    # Create recovery checkpoint if overwriting existing consciousness
    if has_existing_consciousness(target):
        checkpoint = create_recovery_checkpoint(target)
        if checkpoint:
            print(f"Recovery checkpoint created: {checkpoint}")

    # Extract archive
    manifest = extract_archive(args.archive, target)
    print(f"Extracted to: {target}")

    # Run transplant if requested
    if args.transplant:
        from .backup.transplant import create_transplant_mapping, run_transplant, transplant_summary
        maceff_root = args.maceff_root or (target.parent / "MacEff")
        mapping = create_transplant_mapping(manifest, target, maceff_root)
        changes = run_transplant(target, mapping, dry_run=False)
        print(f"\n{transplant_summary(changes)}")

        # Suggest running hooks install
        print("\nNext step: Run 'macf_tools hooks install' to complete setup")

    return 0


def cmd_agent_init(args: argparse.Namespace) -> int:
    """Initialize agent with preamble injection (idempotent)."""
    try:
        # Detect PA home directory
        config = ConsciousnessConfig()
        if config._is_container():
            # In container: use detected home
            pa_home = Path.home()
        else:
            # On host: use agent home
            try:
                from .utils import find_agent_home
                agent_home = find_agent_home()
                if agent_home:
                    pa_home = agent_home
                else:
                    pa_home = Path.cwd()
            except Exception:
                pa_home = Path.cwd()

        claude_md_path = pa_home / "CLAUDE.md"

        # Determine preamble template path (portable)
        template_locations = []

        # 1. Environment variable (deployment-configurable)
        env_templates = os.getenv("MACEFF_TEMPLATES_DIR")
        if env_templates:
            template_locations.append(Path(env_templates) / "PA_PREAMBLE.md")

        # 2. MacEff standard location (with MACEFF_ROOT support)
        maceff_root = os.getenv("MACEFF_ROOT", "/opt/maceff")
        template_locations.append(Path(maceff_root) / "framework" / "templates" / "PA_PREAMBLE.md")

        # 3. Development mode (relative to current directory)
        template_locations.append(Path.cwd() / "templates" / "PA_PREAMBLE.md")

        preamble_template_path = None
        for loc in template_locations:
            if loc.exists():
                preamble_template_path = loc
                break

        if not preamble_template_path:
            print("Error: PA_PREAMBLE.md template not found")
            print("Expected locations:")
            for loc in template_locations:
                print(f"  - {loc}")
            return 1

        # Read preamble template
        preamble_content = preamble_template_path.read_text()

        # Upgrade boundary marker
        UPGRADE_BOUNDARY = """---

<!-- ⚠️ DO NOT WRITE BELOW THIS LINE ⚠️ -->
<!-- Framework preamble managed by macf_tools - edits below will be lost on upgrade -->
<!-- Add custom policies and agent-specific content ABOVE this boundary -->
"""

        # Check if CLAUDE.md exists and process accordingly
        if claude_md_path.exists():
            existing_content = claude_md_path.read_text()

            # If boundary exists, extract user content above it
            if "<!-- ⚠️ DO NOT WRITE BELOW THIS LINE" in existing_content:
                user_content = existing_content.split("<!-- ⚠️ DO NOT WRITE BELOW THIS LINE")[0].rstrip()
                print(f"Updating PA Preamble in existing CLAUDE.md at {claude_md_path}")
            else:
                # No boundary = first time, preserve all existing content
                user_content = existing_content.rstrip()
                print(f"Adding PA Preamble to existing CLAUDE.md at {claude_md_path}")

            # Append: user + boundary + preamble
            new_content = user_content + "\n\n" + UPGRADE_BOUNDARY + "\n\n" + preamble_content
            claude_md_path.write_text(new_content)
            print(f"✅ PA Preamble appended successfully")
        else:
            # Create new CLAUDE.md with just the preamble (no boundary needed)
            print(f"Creating new CLAUDE.md with PA Preamble at {claude_md_path}")
            claude_md_path.write_text(preamble_content)
            print(f"✅ CLAUDE.md created successfully")

        # Create personal policy directory structure (PA only)
        personal_policies_dir = pa_home / "agent" / "policies" / "personal"
        personal_policies_dir.mkdir(parents=True, exist_ok=True)

        # Create personal manifest if it doesn't exist
        personal_manifest = personal_policies_dir / "manifest.json"
        if not personal_manifest.exists():
            manifest_data = {
                "version": "1.0.0",
                "description": f"{config.agent_name} Personal Policies",
                "extends": "/opt/maceff/policies/manifest.json",
                "personal_policies": []
            }
            with open(personal_manifest, 'w') as f:
                json.dump(manifest_data, f, indent=2)
            print(f"✅ Created personal policy manifest at {personal_manifest}")

        print(f"\n📍 PA Home: {pa_home}")
        print(f"📍 Personal Policies: {personal_policies_dir}")
        print(f"\nAgent initialization complete!")

        return 0

    except Exception as e:
        print(f"Error during agent initialization: {e}")
        return 1


# TODO: Migrate policy read caching to event-first architecture
# Legacy _get_policy_read_cache and _update_policy_read_cache deleted (used session_state.json)
# Implementation needed:
#   1. _get_policy_read_from_events(policy_name) - scan events backwards until session_started/compaction_detected
#      - Look for 'policy_read' events with matching policy_name
#      - Return breadcrumb if found, None otherwise
#   2. _record_policy_read_event(policy_name, breadcrumb) - append 'policy_read' event
# Call sites at lines ~1240 and ~1255 reference deleted functions - currently broken


def cmd_policy_navigate(args: argparse.Namespace) -> int:
    """Navigate policy by showing CEP guide only (up to CEP_NAV_BOUNDARY)."""
    from .utils import find_policy_file

    try:
        policy_name = args.policy_name
        # Parse optional parent from path-like input (e.g., "development/todo_hygiene")
        parents = None
        if '/' in policy_name:
            parts = policy_name.split('/')
            policy_name = parts[-1]
            parents = parts[:-1]

        policy_path = find_policy_file(policy_name, parents=parents)

        if not policy_path:
            print(f"Policy not found: {args.policy_name}")
            print("\nUse 'macf_tools policy list' to see available policies")
            return 1

        # Read file and extract content up to CEP_NAV_BOUNDARY
        content = policy_path.read_text()

        boundary_marker = "=== CEP_NAV_BOUNDARY ==="
        if boundary_marker in content:
            nav_content = content.split(boundary_marker)[0]
        else:
            # No boundary - show first 100 lines as navigation
            lines = content.split('\n')[:100]
            nav_content = '\n'.join(lines)
            nav_content += f"\n\n[No CEP_NAV_BOUNDARY found - showing first 100 lines]"

        # Output with line numbers
        print(f"=== CEP Navigation Guide: {policy_path.name} ===\n")
        nav_lines = nav_content.split('\n')
        for i, line in enumerate(nav_lines, 1):
            print(f"{i:4d}│ {line}")

        print(f"\n=== End Navigation Guide ===")

        # Discovery flow footer with guidance
        print(f"\nTo read full policy: macf_tools policy read {args.policy_name}")
        print(f"To read specific section: macf_tools policy read {args.policy_name} --section N (e.g., --section 5 or --section 5.1)")

        # Estimate tokens: ~4 tokens/line average for markdown, display in k
        full_lines = len(content.split('\n'))
        est_tokens_k = (full_lines * 4) / 1000
        print(f"\n📊 Full policy: ~{full_lines} lines (~{est_tokens_k:.1f}k tokens)")

        return 0

    except Exception as e:
        print(f"Error navigating policy: {e}")
        return 1


def cmd_policy_read(args: argparse.Namespace) -> int:
    """Read policy file with line numbers and optional caching."""
    from .utils import find_policy_file, get_breadcrumb

    try:
        policy_name = args.policy_name
        # Parse optional parent from path-like input
        parents = None
        if '/' in policy_name:
            parts = policy_name.split('/')
            policy_name = parts[-1]
            parents = parts[:-1]

        policy_path = find_policy_file(policy_name, parents=parents)

        if not policy_path:
            print(f"Policy not found: {args.policy_name}")
            print("\nUse 'macf_tools policy list' to see available policies")
            return 1

        # Read full content
        content = policy_path.read_text()
        lines = content.split('\n')

        # Get session for caching
        session_id = get_current_session_id()
        cache_key = policy_path.stem  # Use stem for cache key

        # Check if this is a partial read (--lines or --section or --from-nav-boundary)
        from_nav = hasattr(args, 'from_nav_boundary') and args.from_nav_boundary
        is_partial = (hasattr(args, 'lines') and args.lines) or (hasattr(args, 'section') and args.section) or from_nav
        force_read = hasattr(args, 'force') and args.force
        line_offset = 1

        # Handle --from-nav-boundary option (skip CEP navigation guide)
        if from_nav:
            boundary_marker = "=== CEP_NAV_BOUNDARY ==="
            boundary_idx = None
            for i, line in enumerate(lines):
                if boundary_marker in line:
                    boundary_idx = i
                    break
            if boundary_idx is not None:
                lines = lines[boundary_idx + 1:]  # Start after boundary
                line_offset = boundary_idx + 2  # +2 for 1-indexed and skip boundary line
            # If no boundary found, read full file (no-op)

        # Handle --lines option (e.g., "50:100")
        elif hasattr(args, 'lines') and args.lines:
            try:
                parts = args.lines.split(':')
                start = int(parts[0]) - 1  # Convert to 0-indexed
                end = int(parts[1]) if len(parts) > 1 else len(lines)
                lines = lines[start:end]
                line_offset = start + 1
            except (ValueError, IndexError):
                print(f"Invalid --lines format: {args.lines}")
                print("Expected format: START:END (e.g., 50:100)")
                return 1
        # Handle --section option
        elif hasattr(args, 'section') and args.section:
            section_num = str(args.section)

            def matches_section_prefix(heading_num: str, target: str) -> bool:
                """Check if heading_num matches target section (hierarchical).

                Examples:
                    matches_section_prefix("10", "10") → True (exact)
                    matches_section_prefix("10.1", "10") → True (subsection)
                    matches_section_prefix("10", "10.1") → False (parent doesn't match child request)
                    matches_section_prefix("100", "10") → False (not a subsection!)
                """
                if heading_num == target:
                    return True
                # Check if heading is a subsection: must start with "target."
                return heading_num.startswith(target + ".")

            # Find section by heading number, include subsections
            # Stop only at same-or-higher level heading (not subsections)
            in_section = False
            section_lines = []
            section_start = 0
            section_level = 0  # Track heading level (## = 2, ### = 3, etc.)
            in_code_block = False  # Track if we're inside a fenced code block

            for i, line in enumerate(lines):
                # Track code block boundaries (``` or ~~~)
                if line.startswith('```') or line.startswith('~~~'):
                    in_code_block = not in_code_block

                # Only process headings outside code blocks
                if line.startswith('#') and not in_code_block:
                    # Count heading level
                    level = len(line) - len(line.lstrip('#'))
                    heading_text = line.lstrip('#').strip()

                    if heading_text:
                        heading_num = heading_text.split()[0].rstrip('.')

                        if matches_section_prefix(heading_num, section_num):
                            # Found target section or subsection
                            if not in_section:
                                # First match - record the section level
                                in_section = True
                                section_start = i + 1
                                section_level = level
                            # Subsequent matches (subsections) don't reset level
                        elif in_section and level <= section_level:
                            # Same or higher level heading = new section, stop
                            break
                        # else: subsection (deeper level), keep capturing

                if in_section:
                    section_lines.append(line)

            if not section_lines:
                print(f"Section {section_num} not found in {policy_name}")
                return 1

            lines = section_lines
            line_offset = section_start
        else:
            # TODO: Re-enable event-first cache check when implemented
            # Full read - cache check disabled pending event-first migration
            pass

        # Output with line numbers
        print(f"=== {policy_path.name} ===\n")
        for i, line in enumerate(lines, line_offset):
            print(f"{i:4d}│ {line}")

        # TODO: Re-enable event-first cache recording when implemented
        # Cache recording disabled pending event-first migration
        if not is_partial:
            breadcrumb = get_breadcrumb()
            print(f"\n=== Read at {breadcrumb} (caching disabled) ===")
        else:
            print(f"\n=== Partial read (not cached) ===")

        # Show policy metadata footer
        import os
        from datetime import datetime
        mtime = os.path.getmtime(policy_path)
        last_modified = datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        print(f"\n📅 Last updated: {last_modified}")
        if is_partial:
            print(f"💡 Run `macf_tools policy navigate {args.policy_name}` to see all sections")

        return 0

    except Exception as e:
        print(f"Error reading policy: {e}")
        import traceback
        traceback.print_exc()
        return 1


def cmd_policy_manifest(args: argparse.Namespace) -> int:
    """Display merged and filtered policy manifest."""
    from .utils import load_merged_manifest, filter_active_policies

    try:
        # Load and filter manifest
        manifest = load_merged_manifest()
        filtered = filter_active_policies(manifest)

        # Choose format
        format_type = getattr(args, 'format', 'summary')

        if format_type == 'json':
            # Pretty-print full filtered manifest
            print(json.dumps(filtered, indent=2))
        else:
            # Summary format
            print("Policy Manifest Summary")
            print("=" * 50)
            print(f"Version: {filtered.get('version', 'unknown')}")
            print(f"Description: {filtered.get('description', 'N/A')}")

            # Active layers
            active_layers = manifest.get('active_layers', [])
            if active_layers:
                print(f"Active Layers: {', '.join(active_layers)}")
            else:
                print("Active Layers: none configured")

            # Active languages
            active_languages = manifest.get('active_languages', [])
            if active_languages:
                print(f"Active Languages: {', '.join(active_languages)}")
            else:
                print("Active Languages: none configured")

            # CA type count
            discovery_index = filtered.get('discovery_index', {})
            ca_types = set()
            for key in discovery_index.keys():
                # Extract CA types from discovery index keys
                if any(ca in key for ca in ['observation', 'experiment', 'report', 'reflection', 'checkpoint', 'roadmap', 'emotion']):
                    if 'observation' in key:
                        ca_types.add('observations')
                    if 'experiment' in key:
                        ca_types.add('experiments')
                    if 'report' in key:
                        ca_types.add('reports')
                    if 'reflection' in key:
                        ca_types.add('reflections')
                    if 'checkpoint' in key or 'ccp' in key:
                        ca_types.add('checkpoints')
                    if 'roadmap' in key:
                        ca_types.add('roadmaps')
                    if 'emotion' in key:
                        ca_types.add('emotions')

            print(f"CA Types Configured: {len(ca_types)}")
            if ca_types:
                print(f"  Types: {', '.join(sorted(ca_types))}")

        return 0

    except Exception as e:
        print(f"Error displaying manifest: {e}")
        return 1


def cmd_policy_search(args: argparse.Namespace) -> int:
    """Search for keyword in policy manifest with section-level results."""
    from .utils import load_merged_manifest, filter_active_policies

    try:
        keyword = args.keyword.lower()

        # Load and filter manifest
        manifest = load_merged_manifest()
        filtered = filter_active_policies(manifest)

        policy_matches = []  # (category, name, description)
        section_matches = []  # (index_key, policy_ref)

        def search_policy_dict(policy: dict, category: str) -> bool:
            """Check if a policy dict matches the keyword. Returns True if matched."""
            name = policy.get('name', '')
            desc = policy.get('description', '')
            keywords_list = policy.get('keywords', [])

            if (keyword in name.lower() or
                keyword in desc.lower() or
                any(keyword in kw.lower() for kw in keywords_list)):
                policy_matches.append((category, name, desc or name))
                return True
            return False

        def search_policies_recursive(data: any, category: str) -> None:
            """Recursively search for policies in any manifest structure."""
            if isinstance(data, dict):
                # Check if this dict has 'policies' key (standard policy list)
                if 'policies' in data and isinstance(data['policies'], list):
                    for policy in data['policies']:
                        if isinstance(policy, dict):
                            search_policy_dict(policy, category)
                # Check if this dict has 'triggers' key (consciousness_patterns)
                elif 'triggers' in data and isinstance(data['triggers'], list):
                    for trigger in data['triggers']:
                        if isinstance(trigger, dict):
                            pattern_name = trigger.get('pattern', '')
                            consciousness = trigger.get('consciousness', '')
                            search_terms = trigger.get('search_terms', [])
                            if (keyword in pattern_name.lower() or
                                keyword in consciousness.lower() or
                                any(keyword in term.lower() for term in search_terms)):
                                policy_matches.append(('pattern', pattern_name, consciousness))
                # Check if this dict looks like a policy itself (has 'name' and 'keywords')
                elif 'name' in data and 'keywords' in data:
                    search_policy_dict(data, category)
                # Otherwise recurse into nested structures
                else:
                    for key, value in data.items():
                        if key not in ('description', 'location', 'opt_in', 'version',
                                       'last_updated', 'base_path', 'discovery_index',
                                       'consciousness_artifacts'):
                            sub_category = f"{category}/{key}" if category else key
                            search_policies_recursive(value, sub_category)
            elif isinstance(data, list):
                for item in data:
                    search_policies_recursive(item, category)

        # Search all policy categories dynamically
        for key, value in filtered.items():
            if key.endswith('_policies') or key == 'consciousness_patterns':
                category = key.replace('_policies', '').replace('_', ' ')
                search_policies_recursive(value, category)

        # Search discovery_index for section-level matches
        discovery_index = filtered.get('discovery_index', {})
        for index_key, policy_refs in discovery_index.items():
            if keyword in index_key.lower():
                for ref in policy_refs:
                    section_matches.append((index_key, ref))

        # Display results
        total = len(policy_matches) + len(section_matches)
        print(f"Search results for '{keyword}': {total} matches")
        print("=" * 50)

        if policy_matches:
            print("\n📋 Policy Matches:")
            for category, name, desc in policy_matches:
                print(f"  [{category}] {name}: {desc}")

        if section_matches:
            print("\n📍 Section Matches (from discovery index):")
            for index_key, ref in section_matches:
                print(f"  [{index_key}] → {ref}")

        if not policy_matches and not section_matches:
            print("No matches found")
            print("\n💡 Try:")
            print("  macf_tools policy list              # Browse all policies")
            print("  macf_tools policy search <keyword>  # Try different keyword")
        else:
            # Guide toward discovery flow: search → navigate → read
            print("\n💡 Next steps:")
            print("  macf_tools policy navigate <name>          # See CEP navigation guide")
            print("  macf_tools policy read <name> --section N  # Read specific section")

        return 0

    except Exception as e:
        print(f"Error searching manifest: {e}")
        return 1


def cmd_policy_list(args: argparse.Namespace) -> int:
    """List policy files from framework with optional filtering."""
    from .utils import list_policy_files

    try:
        tier = getattr(args, 'tier', None)
        category = getattr(args, 'category', None)

        # Always extract tier info for all policies
        policies = list_policy_files(tier=tier, category=category, include_tier=True)

        if tier or category:
            filter_desc = []
            if tier:
                filter_desc.append(f"tier={tier}")
            if category:
                filter_desc.append(f"category={category}")
            print(f"Policies ({', '.join(filter_desc)})")
        else:
            print("All Policies")
        print("=" * 50)

        if not policies:
            print("No policies found")
            return 0

        # Group by category for display
        by_category = {}
        core_count = 0
        for p in policies:
            cat = p['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(p)
            tier_val = p.get('tier') or ''
            if tier_val.upper() == 'CORE':
                core_count += 1

        for cat in sorted(by_category.keys()):
            print(f"\n{cat}/")
            for p in by_category[cat]:
                policy_tier = (p.get('tier') or '').upper()
                if policy_tier == 'CORE':
                    tier_str = " [CORE]"
                elif policy_tier:
                    tier_str = f" [{policy_tier}]"
                else:
                    tier_str = ""
                print(f"  {p['name']}.md{tier_str}")

        # Summary with CORE highlight
        print(f"\nTotal: {len(policies)} policies ({core_count} CORE)")

        # Discovery footer - guide agents to next step
        print("\n" + "-" * 50)
        print("💡 Run `macf_tools policy navigate <name>` to explore any policy")
        return 0

    except Exception as e:
        print(f"Error listing policies: {e}")
        return 1


def cmd_policy_ca_types(args: argparse.Namespace) -> int:
    """Show CA types with emojis."""
    from .utils import load_merged_manifest, filter_active_policies

    try:
        # CA emoji mapping
        CA_EMOJIS = {
            'observations': '🔬',
            'experiments': '🧪',
            'reports': '📊',
            'reflections': '💭',
            'checkpoints': '🔖',
            'roadmaps': '🗺️',
            'emotions': '❤️'
        }

        # Load and filter manifest
        manifest = load_merged_manifest()
        filtered = filter_active_policies(manifest)

        # Detect active CA types from discovery_index
        discovery_index = filtered.get('discovery_index', {})
        active_types = set()

        for key in discovery_index.keys():
            # Map discovery keys to CA types
            if 'observation' in key:
                active_types.add('observations')
            if 'experiment' in key:
                active_types.add('experiments')
            if 'report' in key:
                active_types.add('reports')
            if 'reflection' in key or 'jotewr' in key or 'wisdom' in key:
                active_types.add('reflections')
            if 'checkpoint' in key or 'ccp' in key:
                active_types.add('checkpoints')
            if 'roadmap' in key:
                active_types.add('roadmaps')
            if 'emotion' in key:
                active_types.add('emotions')

        print("Consciousness Artifact (CA) Types")
        print("=" * 50)

        if active_types:
            for ca_type in sorted(active_types):
                emoji = CA_EMOJIS.get(ca_type, '📄')
                print(f"{emoji} {ca_type}")
        else:
            print("No CA types configured")

        return 0

    except Exception as e:
        print(f"Error showing CA types: {e}")
        return 1


def cmd_policy_recommend(args: argparse.Namespace) -> int:
    """Get hybrid search policy recommendations using RRF scoring.

    First tries the warm search service (fast, ~20ms), falls back to
    direct search (slow, ~8s) if service unavailable.
    """
    import sys
    from .search_service.client import query_search_service

    query = args.query
    json_output = getattr(args, 'json_output', False)
    explain = getattr(args, 'explain', False)
    limit = getattr(args, 'limit', 5)

    if len(query) < 10:
        print("⚠️ Query too short (minimum 10 characters)")
        return 1

    # Try warm service first (fast path)
    result = query_search_service("policy", query, limit=limit, timeout_s=1.0)

    if result.get("formatted") and not result.get("error"):
        # Service responded - use fast path
        formatted = result["formatted"]
        explanations = result.get("explanations", [])
    else:
        # Service unavailable - fall back to direct search (slow)
        print("⚠️ Search service unavailable, using direct search (~8s)...",
              file=sys.stderr)
        print("   Start service: macf_tools search-service start", file=sys.stderr)
        try:
            from .utils.recommend import get_recommendations
            formatted, explanations = get_recommendations(query)
        except ImportError as e:
            print("⚠️ Policy recommend requires optional dependencies:")
            print("   pip install lancedb sentence-transformers")
            print(f"\nImport error: {e}")
            return 1

    try:

        if not formatted and not explanations:
            if json_output:
                import json
                print(json.dumps({"results": [], "query": query}))
            else:
                print("No recommendations found for query.")
                print("\n💡 Tips:")
                print("  - Try more specific keywords")
                print("  - Use policy-related terms (TODO, backup, checkpoint, etc.)")
            return 0

        # Limit results
        explanations = explanations[:limit]

        if json_output:
            import json
            output = {
                "results": explanations,
                "query": query,
                "engine": "rrf_hybrid",
            }
            print(json.dumps(output, indent=2))
        elif explain:
            # Use library function for verbose output
            print(format_verbose_output(explanations, query))
        else:
            # Default: rich human output from library
            print(formatted)

        return 0

    except Exception as e:
        if json_output:
            import json
            print(json.dumps({"error": str(e), "query": query}))
        else:
            print(f"❌ Error getting recommendations: {e}")
        return 1


def cmd_policy_build_index(args: argparse.Namespace) -> int:
    """Build hybrid FTS5 + semantic index from policy files."""
    try:
        from .hybrid_search import PolicyIndexer
    except ImportError as e:
        print("⚠️ Policy build_index requires optional dependencies:")
        print("   pip install sqlite-vec sentence-transformers")
        print(f"\nImport error: {e}")
        return 1

    from pathlib import Path
    from .utils.recommend import get_policy_db_path
    from .utils.manifest import get_framework_policies_path

    # Get paths with defaults
    policies_dir = Path(args.policies_dir) if args.policies_dir else get_framework_policies_path()
    if policies_dir is None:
        print("❌ Could not locate framework policies directory")
        print("   Use --policies-dir to specify manually")
        return 1

    db_path = Path(args.db_path) if args.db_path else get_policy_db_path()
    json_output = getattr(args, 'json_output', False)

    try:
        # Build index
        manifest_path = policies_dir / "manifest.json"
        indexer = PolicyIndexer(manifest_path=manifest_path if manifest_path.exists() else None)
        stats = indexer.build_index(
            policies_dir=policies_dir,
            db_path=db_path,
        )

        # Output
        if json_output:
            import json
            print(json.dumps(stats, indent=2))
        else:
            print("✅ Policy index built:")
            print(f"   Documents: {stats.get('documents_indexed', 0)}")
            print(f"   Questions: {stats.get('questions_indexed', 0)}")
            print(f"   Total time: {stats.get('total_time', 0):.2f}s")
            print(f"   Database: {db_path}")

        return 0

    except Exception as e:
        if json_output:
            import json
            print(json.dumps({"error": str(e)}))
        else:
            print(f"❌ Error building index: {e}")
        return 1


# -------- Mode Commands --------

def cmd_mode_get(args: argparse.Namespace) -> int:
    """Get current operating mode."""
    from .utils.cycles import detect_auto_mode

    try:
        session_id = get_current_session_id()
        enabled, source, confidence = detect_auto_mode(session_id)

        mode = "AUTO_MODE" if enabled else "MANUAL_MODE"

        if getattr(args, 'json_output', False):
            data = {
                "mode": mode,
                "enabled": enabled,
                "source": source,
                "confidence": confidence,
                "session_id": session_id
            }
            print(json.dumps(data, indent=2))
        else:
            print(f"Mode: {mode}")
            print(f"Source: {source} (confidence: {confidence})")

        return 0

    except Exception as e:
        print(f"Error getting mode: {e}")
        return 1


def cmd_mode_set(args: argparse.Namespace) -> int:
    """Set operating mode (requires auth token for AUTO_MODE)."""
    from .utils.cycles import set_auto_mode

    try:
        mode = args.mode.upper()
        auth_token = getattr(args, 'auth_token', None)

        # Validate mode argument
        if mode not in ('AUTO_MODE', 'MANUAL_MODE'):
            print(f"Invalid mode: {mode}")
            print("Valid modes: AUTO_MODE, MANUAL_MODE")
            return 1

        enabled = (mode == 'AUTO_MODE')
        session_id = get_current_session_id()

        # AUTO_MODE requires auth token
        if enabled and not auth_token:
            print("Error: AUTO_MODE requires --auth-token")
            print("\nTo activate AUTO_MODE:")
            print("  macf_tools mode set AUTO_MODE --auth-token \"$(python3 -c \"import json; print(json.load(open('.maceff/settings.json'))['auto_mode_auth_token'])\")\"\n")
            return 1

        # Set mode
        success, message = set_auto_mode(
            enabled=enabled,
            session_id=session_id,
            auth_token=auth_token,
        )

        if success:
            print(f"✅ {message}")

            # If enabling AUTO_MODE, also enable autocompact and bypass permissions
            if enabled:
                from .utils.claude_settings import set_autocompact_enabled, set_permission_mode
                if set_autocompact_enabled(True):
                    print("✅ autoCompactEnabled set to true in ~/.claude.json")
                else:
                    print("⚠️  Could not update autoCompactEnabled setting")
                if set_permission_mode("bypassPermissions"):
                    print("✅ permissions.defaultMode set to bypassPermissions")
                else:
                    print("⚠️  Could not update permissions.defaultMode setting")
            else:
                # Returning to MANUAL_MODE - restore default permissions
                from .utils.claude_settings import set_autocompact_enabled, set_permission_mode
                set_autocompact_enabled(False)
                set_permission_mode("default")
                print("✅ Restored default settings (autocompact disabled, default permissions)")
        else:
            print(f"❌ {message}")
            return 1

        return 0

    except Exception as e:
        print(f"Error setting mode: {e}")
        return 1


# -------- Agent Events Log Commands --------

def cmd_events_show(args: argparse.Namespace) -> int:
    """Display current agent state from events log."""
    from .agent_events_log import get_current_state

    try:
        state = get_current_state()

        if getattr(args, 'json_output', False):
            # JSON output
            print(json.dumps(state, indent=2))
        else:
            # Human-readable output
            print("Current Agent State")
            print("=" * 50)
            print(f"Session ID: {state.get('session_id', 'N/A')}")
            print(f"Cycle: {state.get('cycle', 'N/A')}")

        return 0

    except Exception as e:
        print(f"Error reading current state: {e}")
        return 1


def cmd_events_history(args: argparse.Namespace) -> int:
    """Display recent events from log."""
    from .agent_events_log import read_events

    try:
        limit = getattr(args, 'limit', 10)

        print(f"Recent Events (last {limit})")
        print("=" * 50)

        events = list(read_events(limit=limit, reverse=True))

        if not events:
            print("No events found")
            return 0

        for event in events:
            timestamp = event.get('timestamp', 0)
            event_type = event.get('event', 'unknown')
            breadcrumb = event.get('breadcrumb', 'N/A')

            # Format timestamp
            dt = datetime.fromtimestamp(timestamp, tz=_pick_tz())
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

            print(f"[{time_str}] {event_type}")
            print(f"  Breadcrumb: {breadcrumb}")

            # Show key data fields
            data = event.get('data', {})
            if data:
                for key, value in data.items():
                    print(f"  {key}: {value}")
            print()

        return 0

    except Exception as e:
        print(f"Error reading event history: {e}")
        return 1


def cmd_events_query(args: argparse.Namespace) -> int:
    """Query events with filters."""
    from .agent_events_log import query_events

    try:
        # Build filter dict from args
        filters = {}

        # Event type filter
        if hasattr(args, 'event') and args.event:
            filters['event_type'] = args.event

        # Breadcrumb filters
        breadcrumb_filters = {}

        if hasattr(args, 'cycle') and args.cycle:
            breadcrumb_filters['c'] = int(args.cycle)

        if hasattr(args, 'git_hash') and args.git_hash:
            breadcrumb_filters['g'] = args.git_hash

        if hasattr(args, 'session') and args.session:
            breadcrumb_filters['s'] = args.session

        if hasattr(args, 'prompt') and args.prompt:
            breadcrumb_filters['p'] = args.prompt

        if breadcrumb_filters:
            filters['breadcrumb'] = breadcrumb_filters

        # Timestamp filters
        if hasattr(args, 'after') and args.after:
            filters['since'] = float(args.after)

        if hasattr(args, 'before') and args.before:
            filters['until'] = float(args.before)

        # Execute query
        results = query_events(filters)

        # Post-filter by command if specified (for cli_command_invoked events)
        command_filter = getattr(args, 'command', None)
        if command_filter:
            filtered = []
            for event in results:
                if event.get('event') == 'cli_command_invoked':
                    argv = event.get('data', {}).get('argv', [])
                    cmd_str = ' '.join(argv)
                    if command_filter in cmd_str:
                        filtered.append(event)
            results = filtered

        print(f"Query Results: {len(results)} events")
        print("=" * 50)

        if not results:
            print("No matching events found")
            return 0

        verbose = getattr(args, 'verbose', False)

        for event in results:
            timestamp = event.get('timestamp', 0)
            event_type = event.get('event', 'unknown')
            breadcrumb = event.get('breadcrumb', 'N/A')
            data = event.get('data', {})

            # Format timestamp
            dt = datetime.fromtimestamp(timestamp, tz=_pick_tz())
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

            print(f"[{time_str}] {event_type}")
            print(f"  Breadcrumb: {breadcrumb}")

            # Show command details for cli_command_invoked
            if event_type == 'cli_command_invoked' and 'argv' in data:
                argv = data.get('argv', [])
                print(f"  Command: {' '.join(argv)}")

            # Verbose mode: show all data
            if verbose and data:
                import json
                print(f"  Data: {json.dumps(data, indent=4)}")

            print()

        return 0

    except Exception as e:
        print(f"Error querying events: {e}")
        return 1


def cmd_events_query_set(args: argparse.Namespace) -> int:
    """Perform set operations on queries."""
    from .agent_events_log import query_events

    try:
        # Parse query and subtract arguments
        query_filters = {}
        subtract_filters = {}

        # Parse --query argument
        if hasattr(args, 'query') and args.query:
            # Format: "event_type=migration_detected" or "cycle=171"
            query_str = args.query
            if '=' in query_str:
                key, value = query_str.split('=', 1)
                if key == 'event_type':
                    query_filters['event_type'] = value
                elif key == 'cycle':
                    query_filters['breadcrumb'] = {'c': int(value)}

        # Parse --subtract argument
        if hasattr(args, 'subtract') and args.subtract:
            subtract_str = args.subtract
            if '=' in subtract_str:
                key, value = subtract_str.split('=', 1)
                if key == 'cycle':
                    subtract_filters['breadcrumb'] = {'c': int(value)}

        # Execute queries
        from .agent_events_log import query_set_operations

        queries = [query_filters, subtract_filters]
        results = query_set_operations(queries, 'subtraction')

        print(f"Set Operation Results: {len(results)} events")
        print("=" * 50)

        if not results:
            print("No events after set operation")
            return 0

        for event in results:
            timestamp = event.get('timestamp', 0)
            event_type = event.get('event', 'unknown')
            breadcrumb = event.get('breadcrumb', 'N/A')

            # Format timestamp
            dt = datetime.fromtimestamp(timestamp, tz=_pick_tz())
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")

            print(f"[{time_str}] {event_type}")
            print(f"  Breadcrumb: {breadcrumb}")
            print()

        return 0

    except Exception as e:
        print(f"Error performing set operation: {e}")
        return 1


def cmd_events_sessions_list(args: argparse.Namespace) -> int:
    """List all sessions from events log."""
    from .agent_events_log import read_events

    try:
        # Collect unique sessions
        sessions = {}

        for event in read_events(limit=None, reverse=False):
            data = event.get('data', {})
            session_id = data.get('session_id')

            if session_id:
                # Track session info
                if session_id not in sessions:
                    sessions[session_id] = {
                        'first_seen': event.get('timestamp', 0),
                        'last_seen': event.get('timestamp', 0),
                        'events': 1
                    }
                else:
                    sessions[session_id]['last_seen'] = event.get('timestamp', 0)
                    sessions[session_id]['events'] += 1

        print(f"Sessions: {len(sessions)} total")
        print("=" * 50)

        for session_id, info in sessions.items():
            # Show first 8 chars of session ID
            short_id = session_id[:8] if len(session_id) > 8 else session_id
            event_count = info['events']
            print(f"{short_id}... ({event_count} events)")

        return 0

    except Exception as e:
        print(f"Error listing sessions: {e}")
        return 1


def cmd_events_stats(args: argparse.Namespace) -> int:
    """Display event statistics."""
    from .agent_events_log import read_events

    try:
        # Count events by type
        event_counts = {}

        for event in read_events(limit=None, reverse=False):
            event_type = event.get('event', 'unknown')
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

        print("Event Statistics")
        print("=" * 50)

        if not event_counts:
            print("No events found")
            return 0

        for event_type, count in sorted(event_counts.items()):
            print(f"{event_type}: {count}")

        return 0

    except Exception as e:
        print(f"Error calculating statistics: {e}")
        return 1


def cmd_events_gaps(args: argparse.Namespace) -> int:
    """Detect time gaps between events (potential crashes)."""
    from .agent_events_log import read_events

    try:
        threshold = getattr(args, 'threshold', 3600)  # Default 1 hour
        threshold = float(threshold)

        print(f"Time Gap Analysis (threshold: {threshold}s)")
        print("=" * 50)

        events = list(read_events(limit=None, reverse=False))

        if len(events) < 2:
            print("Not enough events for gap analysis")
            return 0

        gaps_found = 0

        for i in range(1, len(events)):
            prev_event = events[i - 1]
            curr_event = events[i]

            prev_time = prev_event.get('timestamp', 0)
            curr_time = curr_event.get('timestamp', 0)

            gap = curr_time - prev_time

            if gap > threshold:
                gaps_found += 1

                # Format timestamps
                prev_dt = datetime.fromtimestamp(prev_time, tz=_pick_tz())
                curr_dt = datetime.fromtimestamp(curr_time, tz=_pick_tz())

                print(f"Gap #{gaps_found}: {gap:.0f}s")
                print(f"  From: {prev_dt.strftime('%Y-%m-%d %H:%M:%S')} ({prev_event.get('event')})")
                print(f"  To:   {curr_dt.strftime('%Y-%m-%d %H:%M:%S')} ({curr_event.get('event')})")
                print()

        if gaps_found == 0:
            print("No significant gaps detected")

        return 0

    except Exception as e:
        print(f"Error analyzing gaps: {e}")
        return 1


# -------- todos commands --------

def cmd_todos_list(args: argparse.Namespace) -> int:
    """Show active TODO list from events."""
    from macf.event_queries import get_nth_event
    from datetime import datetime

    # ANSI escape codes
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"

    # Status markers (lightweight)
    STATUS_MARKERS = {
        "completed": "✔",
        "in_progress": "◼",
        "pending": "◻",
    }

    # Status styling (completed=dim, active=bold)
    STATUS_STYLES = {
        "completed": DIM,
        "in_progress": BOLD,
        "pending": BOLD,
    }

    try:
        n = getattr(args, 'previous', 0)
        event = get_nth_event("todos_updated", n=n)
        if not event:
            if n > 0:
                print(f"No todos_updated event found at position {n}")
            else:
                print("No todos_updated events found")
            return 0

        data = event.get("data", {})
        items = data.get("items", [])
        timestamp = event.get("timestamp", 0)

        # Apply filter if specified
        filter_mode = getattr(args, 'filter', 'all')
        if filter_mode == 'active':
            items = [i for i in items if i.get('status') in ('pending', 'in_progress')]
        elif filter_mode == 'completed':
            items = [i for i in items if i.get('status') == 'completed']

        if getattr(args, 'json_output', False):
            print(json.dumps(items, indent=2))
            return 0

        # Calculate status counts for header
        by_status = {"completed": 0, "in_progress": 0, "pending": 0}
        for item in items:
            status = item.get("status", "pending")
            by_status[status] = by_status.get(status, 0) + 1

        # Pretty print with timestamp context and status summary
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "unknown"
        status_summary = ", ".join(f"{v} {k}" for k, v in by_status.items() if v > 0)
        filter_note = f" [{filter_mode}]" if filter_mode != 'all' else ""
        if n > 0:
            print(f"TODO List (previous #{n}, {len(items)} items: {status_summary}, from {time_str}){filter_note}")
        else:
            print(f"Active TODO List ({len(items)} items: {status_summary}){filter_note}")
        print("=" * 60)

        # Enhanced item display with markers BEFORE number + styling
        for i, item in enumerate(items, 1):
            content = item.get("content", "")
            status = item.get("status", "pending")
            marker = STATUS_MARKERS.get(status, "◻")
            style = STATUS_STYLES.get(status, "")
            print(f"{style}{marker} {i:3}. {content}{RESET}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_todos_status(args: argparse.Namespace) -> int:
    """Show current TODO state summary from events."""
    from macf.event_queries import get_latest_event

    try:
        event = get_latest_event("todos_updated")
        if not event:
            print("No todos_updated events found")
            return 0

        data = event.get("data", {})
        count = data.get("count", 0)
        by_status = data.get("by_status", {})

        print(f"TODO Status (from events)")
        print("=" * 40)
        print(f"Total items: {count}")
        print(f"  Completed:   {by_status.get('completed', 0)}")
        print(f"  In Progress: {by_status.get('in_progress', 0)}")
        print(f"  Pending:     {by_status.get('pending', 0)}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_todos_auth_collapse(args: argparse.Namespace) -> int:
    """Authorize a TODO collapse operation."""
    from macf.agent_events_log import append_event

    from_count = args.from_count
    to_count = args.to_count
    reason = getattr(args, 'reason', None) or "No reason provided"

    if to_count >= from_count:
        print(f"Error: to_count ({to_count}) must be less than from_count ({from_count})")
        print("This command is for authorizing collapses (reductions), not expansions.")
        return 1

    try:
        append_event(
            event="todos_auth_collapse",
            data={
                "from_count": from_count,
                "to_count": to_count,
                "reason": reason
            }
        )

        reduction = from_count - to_count
        print(f"✅ Collapse authorized: {from_count} → {to_count} items (removing {reduction})")
        print(f"   Reason: {reason}")
        print(f"\nYou may now execute TodoWrite. Authorization is single-use.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_todos_auth_restore(args: argparse.Namespace) -> int:
    """Authorize a TODO restore from previous state."""
    from macf.agent_events_log import append_event
    from macf.event_queries import get_nth_event

    n = args.previous
    reason = getattr(args, 'reason', None) or f"Restore from previous #{n}"

    try:
        event = get_nth_event("todos_updated", n=n)
        if not event:
            print(f"Error: No todos_updated event found at position {n}")
            return 1

        data = event.get("data", {})
        items = data.get("items", [])

        if not items:
            print(f"Error: Previous state #{n} has no items")
            return 1

        append_event(
            event="todos_auth_restore",
            data={
                "previous_n": n,
                "expected_items": items,
                "expected_count": len(items),
                "reason": reason
            }
        )

        print(f"✅ Restore authorized: from previous #{n} ({len(items)} items)")
        print(f"   Reason: {reason}")
        print(f"\nYou may now execute TodoWrite. Authorization is single-use.")
        print(f"⚠️  TodoWrite MUST exactly match the stored JSON to proceed.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_todos_auth_status(args: argparse.Namespace) -> int:
    """Show pending authorization status."""
    from macf.event_queries import get_latest_event

    try:
        # Get latest auth and latest cleared
        auth_event = get_latest_event("todos_auth_collapse")
        cleared_event = get_latest_event("todos_auth_cleared")

        if not auth_event:
            print("No pending collapse authorization")
            return 0

        auth_ts = auth_event.get("timestamp", 0)
        cleared_ts = cleared_event.get("timestamp", 0) if cleared_event else 0

        if cleared_ts > auth_ts:
            print("No pending collapse authorization (last auth was cleared)")
            return 0

        data = auth_event.get("data", {})
        print(f"⚠️  Pending collapse authorization:")
        print(f"   From: {data.get('from_count')} items")
        print(f"   To:   {data.get('to_count')} items")
        print(f"   Reason: {data.get('reason', 'N/A')}")

        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


def parse_index_spec(spec: str) -> list[int]:
    """Parse index specification: single (13), range (13-17), or comma-separated (13,14,15).

    Supports mixed formats like '13-15,18,20-22'.
    Returns sorted unique indices.
    """
    indices = []
    for part in spec.split(','):
        part = part.strip()
        if '-' in part:
            try:
                start, end = part.split('-', 1)
                start_int, end_int = int(start.strip()), int(end.strip())
                if start_int > end_int:
                    raise ValueError(f"Invalid range: {start_int}-{end_int} (start > end)")
                indices.extend(range(start_int, end_int + 1))
            except ValueError as e:
                raise ValueError(f"Invalid range format '{part}': {e}")
        else:
            try:
                indices.append(int(part))
            except ValueError:
                raise ValueError(f"Invalid index: '{part}'")
    return sorted(set(indices))


def cmd_todos_auth_item_edit(args: argparse.Namespace) -> int:
    """Authorize editing content of TODO items by index.

    Supports single index (13), range (13-17), or comma-separated (13,14,15).
    """
    from macf.agent_events_log import append_event

    reason = getattr(args, 'reason', None) or "No reason provided"

    try:
        indices = parse_index_spec(args.index)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Validate all indices first
    for index in indices:
        if index < 1:
            print(f"Error: index {index} must be >= 1 (1-based indexing)")
            return 1

    try:
        # Authorize each index
        for index in indices:
            append_event(
                event="todos_auth_item_edit",
                data={
                    "index": index,
                    "reason": reason
                }
            )

        if len(indices) == 1:
            print(f"✅ Item edit authorized: index {indices[0]}")
        else:
            print(f"✅ Item edits authorized: indices {', '.join(map(str, indices))}")
        print(f"   Reason: {reason}")
        print(f"\nYou may now execute TodoWrite. Authorization is single-use.")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


# -------- search-service commands --------

# -------- task commands --------
# ANSI escape codes for styling
ANSI_DIM = "\033[2m"
ANSI_STRIKE = "\033[9m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_RESET = "\033[0m"


def cmd_task_list(args: argparse.Namespace) -> int:
    """List tasks from current session with hierarchy and metadata."""
    from .task import TaskReader, MacfTask

    reader = TaskReader()
    tasks = reader.read_all_tasks()

    if not tasks:
        print("No tasks found in current session.")
        return 0

    # Sort tasks numerically by ID first
    tasks = sorted(tasks, key=lambda t: t.id)

    # Apply filters
    if args.type_filter:
        type_upper = args.type_filter.upper()
        tasks = [t for t in tasks if t.task_type == type_upper]

    if args.status_filter:
        tasks = [t for t in tasks if t.status == args.status_filter]

    if args.parent_filter is not None:
        tasks = [t for t in tasks if t.parent_id == args.parent_filter]

    if not tasks:
        print("No tasks match filters.")
        return 0

    # JSON output
    if args.json_output:
        import json
        output = []
        for t in sorted(tasks, key=lambda t: t.id):
            item = {
                "id": t.id,
                "subject": t.subject,
                "status": t.status,
                "type": t.task_type,
                "parent_id": t.parent_id,
                "blocked_by": t.blocked_by,
            }
            if t.mtmd:
                item["mtmd"] = {
                    "plan_ca_ref": t.mtmd.plan_ca_ref,
                    "creation_breadcrumb": t.mtmd.creation_breadcrumb,
                    "created_cycle": t.mtmd.created_cycle,
                    "repo": t.mtmd.repo,
                    "target_version": t.mtmd.target_version,
                }
            output.append(item)
        print(json.dumps(output, indent=2))
        return 0

    # Build hierarchy for tree display
    task_map = {t.id: t for t in tasks}
    root_tasks = [t for t in tasks if t.parent_id is None or t.parent_id not in task_map]

    def get_children(parent_id):
        return sorted([t for t in tasks if t.parent_id == parent_id], key=lambda t: t.id)

    def format_task(t: MacfTask, indent: int = 0) -> str:
        prefix = "  " * indent
        # CC-style markers with colors: red ◼ in_progress, ◻ pending, green ✔ completed
        if t.status == "completed":
            status_icon = f"{ANSI_GREEN}✔{ANSI_RESET}"
            # Dim+strikethrough for completed task text
            line = f"{prefix}{status_icon} {ANSI_DIM}{ANSI_STRIKE}#{t.id} {t.subject}{ANSI_RESET}"
        elif t.status == "in_progress":
            status_icon = f"{ANSI_RED}◼{ANSI_RESET}"
            line = f"{prefix}{status_icon} #{t.id} {t.subject}"
        else:  # pending
            status_icon = "◻"
            line = f"{prefix}{status_icon} #{t.id} {t.subject}"

        # Add plan_ca_ref if present (key feature of enhanced display)
        if t.mtmd and t.mtmd.plan_ca_ref:
            if t.status == "completed":
                line += f"\n{prefix}   {ANSI_DIM}{ANSI_STRIKE}→ {t.mtmd.plan_ca_ref}{ANSI_RESET}"
            else:
                line += f"\n{prefix}   → {t.mtmd.plan_ca_ref}"

        return line

    def print_tree(task: MacfTask, indent: int = 0):
        print(format_task(task, indent))
        for child in get_children(task.id):
            print_tree(child, indent + 1)

    # Print header
    print(f"📋 Tasks ({len(tasks)} total) - Session: {reader.session_uuid[:8]}...")
    print("-" * 60)

    # Print tree from roots (sorted by ID)
    for root in sorted(root_tasks, key=lambda t: t.id):
        print_tree(root)

    return 0


def cmd_task_get(args: argparse.Namespace) -> int:
    """Get detailed information about a specific task."""
    from .task import TaskReader

    # Parse task ID (handle #N or N format)
    task_id_str = args.task_id.lstrip('#')
    try:
        task_id = int(task_id_str)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    reader = TaskReader()
    task = reader.read_task(task_id)

    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    # JSON output
    if args.json_output:
        import json
        output = {
            "id": task.id,
            "subject": task.subject,
            "description": task.description,
            "status": task.status,
            "type": task.task_type,
            "parent_id": task.parent_id,
            "blocks": task.blocks,
            "blocked_by": task.blocked_by,
            "session_uuid": task.session_uuid,
            "file_path": task.file_path,
        }
        if task.mtmd:
            output["mtmd"] = {
                "version": task.mtmd.version,
                "creation_breadcrumb": task.mtmd.creation_breadcrumb,
                "created_cycle": task.mtmd.created_cycle,
                "created_by": task.mtmd.created_by,
                "plan_ca_ref": task.mtmd.plan_ca_ref,
                "experiment_ca_ref": task.mtmd.experiment_ca_ref,
                "parent_id": task.mtmd.parent_id,
                "repo": task.mtmd.repo,
                "target_version": task.mtmd.target_version,
                "release_branch": task.mtmd.release_branch,
                "completion_breadcrumb": task.mtmd.completion_breadcrumb,
                "unblock_breadcrumb": task.mtmd.unblock_breadcrumb,
                "updates": [{"breadcrumb": u.breadcrumb, "description": u.description, "agent": u.agent} for u in task.mtmd.updates],
                "archived": task.mtmd.archived,
            }
        print(json.dumps(output, indent=2))
        return 0

    # Human-readable output
    status_icon = {"completed": "✅", "in_progress": "🔄", "pending": "⏳"}.get(task.status, "❓")

    print(f"{'='*60}")
    print(f"Task #{task.id} {status_icon}")
    print(f"{'='*60}")
    print(f"Subject: {task.subject}")
    print(f"Status: {task.status}")
    if task.task_type:
        print(f"Type: {task.task_type}")
    if task.parent_id:
        print(f"Parent: #{task.parent_id}")
    if task.blocked_by:
        print(f"Blocked by: {', '.join(f'#{b}' for b in task.blocked_by)}")
    if task.blocks:
        print(f"Blocks: {', '.join(f'#{b}' for b in task.blocks)}")

    # MTMD section
    if task.mtmd:
        print(f"\n📦 MacfTaskMetaData (v{task.mtmd.version})")
        print("-" * 40)
        if task.mtmd.plan_ca_ref:
            print(f"  plan_ca_ref: {task.mtmd.plan_ca_ref}")
        if task.mtmd.experiment_ca_ref:
            print(f"  experiment_ca_ref: {task.mtmd.experiment_ca_ref}")
        if task.mtmd.creation_breadcrumb:
            print(f"  created: {task.mtmd.creation_breadcrumb}")
        if task.mtmd.created_cycle:
            print(f"  cycle: {task.mtmd.created_cycle}")
        if task.mtmd.created_by:
            print(f"  by: {task.mtmd.created_by}")
        if task.mtmd.repo:
            print(f"  repo: {task.mtmd.repo}")
        if task.mtmd.target_version:
            print(f"  target: {task.mtmd.target_version}")
        if task.mtmd.completion_breadcrumb:
            print(f"  completed: {task.mtmd.completion_breadcrumb}")
        if task.mtmd.unblock_breadcrumb:
            print(f"  unblocked: {task.mtmd.unblock_breadcrumb}")
        if task.mtmd.updates:
            print(f"  updates: ({len(task.mtmd.updates)})")
            for u in task.mtmd.updates:
                desc = f" - {u.description}" if u.description else ""
                print(f"    • {u.breadcrumb}{desc}")

    # Description (without MTMD)
    desc_clean = task.description_without_mtmd()
    if desc_clean:
        print(f"\n📝 Description")
        print("-" * 40)
        print(desc_clean)

    print(f"\n📁 File: {task.file_path}")

    return 0


def cmd_task_tree(args: argparse.Namespace) -> int:
    """Display task hierarchy tree from a root task."""
    from .task import TaskReader

    # Parse task ID
    task_id_str = args.task_id.lstrip('#')
    try:
        root_id = int(task_id_str)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    reader = TaskReader()
    all_tasks = reader.read_all_tasks()
    task_map = {t.id: t for t in all_tasks}

    if root_id not in task_map:
        print(f"❌ Task #{root_id} not found")
        print(f"   Session: {reader.session_uuid}")
        print(f"   Tasks loaded: {len(all_tasks)}")
        if all_tasks:
            ids = sorted(t.id for t in all_tasks)
            print(f"   Available IDs: {ids[:10]}{'...' if len(ids) > 10 else ''}")
        return 1

    root = task_map[root_id]

    def get_children(parent_id):
        return sorted([t for t in all_tasks if t.parent_id == parent_id], key=lambda t: t.id)

    def count_descendants(task_id):
        children = get_children(task_id)
        return len(children) + sum(count_descendants(c.id) for c in children)

    def print_tree(task, prefix="", is_last=True):
        connector = "└── " if is_last else "├── "

        # CC-style markers with colors
        if task.status == "completed":
            status_icon = f"{ANSI_GREEN}✔{ANSI_RESET}"
            text = f"{ANSI_DIM}{ANSI_STRIKE}#{task.id} {task.subject[:47]}{'...' if len(task.subject) > 50 else ''}{ANSI_RESET}"
        elif task.status == "in_progress":
            status_icon = f"{ANSI_RED}◼{ANSI_RESET}"
            text = f"#{task.id} {task.subject[:47]}{'...' if len(task.subject) > 50 else ''}"
        else:
            status_icon = "◻"
            text = f"#{task.id} {task.subject[:47]}{'...' if len(task.subject) > 50 else ''}"

        print(f"{prefix}{connector}{status_icon} {text}")

        children = get_children(task.id)
        for i, child in enumerate(children):
            extension = "    " if is_last else "│   "
            print_tree(child, prefix + extension, i == len(children) - 1)

    # Print header
    total = 1 + count_descendants(root_id)
    print(f"🌳 Task Tree from #{root_id} ({total} tasks)")
    print("=" * 60)

    # Print root specially with CC-style markers
    if root.status == "completed":
        status_icon = f"{ANSI_GREEN}✔{ANSI_RESET}"
        root_text = f"{ANSI_DIM}{ANSI_STRIKE}#{root.id} {root.subject}{ANSI_RESET}"
    elif root.status == "in_progress":
        status_icon = f"{ANSI_RED}◼{ANSI_RESET}"
        root_text = f"#{root.id} {root.subject}"
    else:
        status_icon = "◻"
        root_text = f"#{root.id} {root.subject}"
    print(f"{status_icon} {root_text}")
    if root.mtmd and root.mtmd.plan_ca_ref:
        print(f"   → {root.mtmd.plan_ca_ref}")

    # Print children
    children = get_children(root_id)
    for i, child in enumerate(children):
        print_tree(child, "", i == len(children) - 1)

    return 0


def cmd_task_edit(args: argparse.Namespace) -> int:
    """Edit a top-level JSON field in a task file."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    # Parse task ID
    task_id_str = args.task_id.lstrip('#')
    try:
        task_id = int(task_id_str)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    field = args.field
    value = args.value

    # Validate field is editable
    editable_fields = ["subject", "status", "description"]
    if field not in editable_fields:
        print(f"❌ Field '{field}' is not editable")
        print(f"   Editable fields: {', '.join(editable_fields)}")
        return 1

    # Validate status values
    if field == "status" and value not in ["pending", "in_progress", "completed"]:
        print(f"❌ Invalid status value: {value}")
        print("   Valid values: pending, in_progress, completed")
        return 1

    # Read task to verify it exists and get current state
    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    # For MTMD-aware tasks, add update record when editing description
    if field == "description" and task.mtmd:
        breadcrumb = get_breadcrumb()
        new_mtmd = task.mtmd.with_updated_field("description", "(edited)", breadcrumb, f"Description replaced via CLI")
        value = task.description_with_updated_mtmd(new_mtmd)

    # Apply update
    if update_task_file(task_id, {field: value}):
        print(f"✅ Updated task #{task_id}")
        print(f"   {field} = {value[:50]}{'...' if len(str(value)) > 50 else ''}")
        return 0
    else:
        print(f"❌ Failed to update task #{task_id}")
        return 1


def cmd_task_edit_mtmd(args: argparse.Namespace) -> int:
    """Edit an MTMD field within a task's description."""
    from .task import TaskReader, update_task_file, MacfTaskMetaData
    from .utils.breadcrumbs import get_breadcrumb

    # Parse task ID
    task_id_str = args.task_id.lstrip('#')
    try:
        task_id = int(task_id_str)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    field = args.field
    value = args.value

    # Read task
    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    # Validate MTMD field exists
    mtmd_fields = [
        "plan_ca_ref", "parent_id", "repo", "target_version", "release_branch",
        "completion_breadcrumb", "unblock_breadcrumb", "archived", "archived_at",
        "creation_breadcrumb", "created_cycle", "created_by", "experiment_ca_ref"
    ]
    if field not in mtmd_fields:
        print(f"❌ Unknown MTMD field: {field}")
        print(f"   Valid fields: {', '.join(mtmd_fields)}")
        return 1

    # Parse value types for specific fields
    if field == "parent_id" and value != "null":
        try:
            value = int(value)
        except ValueError:
            print(f"❌ parent_id must be an integer")
            return 1
    elif field == "created_cycle" and value != "null":
        try:
            value = int(value)
        except ValueError:
            print(f"❌ created_cycle must be an integer")
            return 1
    elif field == "archived":
        value = value.lower() in ("true", "1", "yes")
    elif value == "null":
        value = None

    # Get or create MTMD
    breadcrumb = get_breadcrumb()
    if task.mtmd:
        new_mtmd = task.mtmd.with_updated_field(field, value, breadcrumb, f"Set {field} via CLI")
    else:
        # Create new MTMD with just this field
        new_mtmd = MacfTaskMetaData()
        setattr(new_mtmd, field, value)
        from .task.models import MacfTaskUpdate
        new_mtmd.updates.append(MacfTaskUpdate(
            breadcrumb=breadcrumb,
            description=f"Created MTMD with {field} via CLI",
            agent="PA"
        ))

    # Embed updated MTMD in description
    new_description = task.description_with_updated_mtmd(new_mtmd)

    # Apply update
    if update_task_file(task_id, {"description": new_description}):
        print(f"✅ Updated MTMD for task #{task_id}")
        print(f"   {field} = {value}")
        return 0
    else:
        print(f"❌ Failed to update task #{task_id}")
        return 1


def cmd_task_add_mtmd(args: argparse.Namespace) -> int:
    """Add a custom field to MTMD's custom_data section."""
    from .task import TaskReader, update_task_file, MacfTaskMetaData
    from .utils.breadcrumbs import get_breadcrumb

    # Parse task ID
    task_id_str = args.task_id.lstrip('#')
    try:
        task_id = int(task_id_str)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    key = args.key
    value = args.value

    # Read task
    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    # Get or create MTMD
    breadcrumb = get_breadcrumb()
    if task.mtmd:
        new_mtmd = task.mtmd.with_custom_field(key, value, breadcrumb)
    else:
        # Create new MTMD with custom field
        new_mtmd = MacfTaskMetaData()
        new_mtmd.custom[key] = value
        from .task.models import MacfTaskUpdate
        new_mtmd.updates.append(MacfTaskUpdate(
            breadcrumb=breadcrumb,
            description=f"Created MTMD with custom.{key} via CLI",
            agent="PA"
        ))

    # Embed updated MTMD in description
    new_description = task.description_with_updated_mtmd(new_mtmd)

    # Apply update
    if update_task_file(task_id, {"description": new_description}):
        print(f"✅ Added custom field to task #{task_id}")
        print(f"   custom.{key} = {value}")
        return 0
    else:
        print(f"❌ Failed to update task #{task_id}")
        return 1


def cmd_search_service_start(args: argparse.Namespace) -> int:
    """Start the search service daemon."""
    try:
        from macf.search_service import SearchService, is_service_running
        from macf.search_service.retrievers.policy_retriever import PolicyRetriever
    except ImportError as e:
        print("⚠️ Search service requires optional dependencies:")
        print("   pip install sqlite-vec sentence-transformers")
        print(f"\nImport error: {e}")
        return 1

    # Check if already running
    if is_service_running():
        print("⚠️  Search service is already running")
        print("   Use 'macf_tools search-service stop' to stop it first")
        return 1

    # Get configuration
    port = getattr(args, 'port', 9001)
    daemonize = getattr(args, 'daemon', False)

    try:
        # Create service and register policy retriever
        service = SearchService(port=port)
        service.register(PolicyRetriever())

        # Start service (blocking unless daemonized)
        print(f"Starting search service on port {port}...", file=sys.stderr)
        if daemonize:
            print("Running in background (daemon mode)", file=sys.stderr)

        service.start(daemonize=daemonize)
        return 0

    except Exception as e:
        print(f"❌ Error starting search service: {e}", file=sys.stderr)
        return 1


def cmd_search_service_stop(args: argparse.Namespace) -> int:
    """Stop the running search service."""
    try:
        from macf.search_service import stop_service, is_service_running
    except ImportError as e:
        print(f"Import error: {e}")
        return 1

    if not is_service_running():
        print("Search service is not running")
        return 0

    try:
        if stop_service():
            print("✅ Search service stopped")
            return 0
        else:
            print("⚠️  Service was not running")
            return 0
    except Exception as e:
        print(f"❌ Error stopping service: {e}")
        return 1


def cmd_search_service_status(args: argparse.Namespace) -> int:
    """Show search service status."""
    try:
        from macf.search_service import get_service_status
    except ImportError as e:
        print(f"Import error: {e}")
        return 1

    try:
        status = get_service_status()
        json_output = getattr(args, 'json_output', False)

        if json_output:
            print(json.dumps(status, indent=2))
        else:
            running = status.get('running', False)
            pid = status.get('pid')
            port = status.get('port', 9001)

            if running:
                print(f"✅ Search service is running")
                print(f"   PID: {pid}")
                print(f"   Port: {port}")
            else:
                print("⚠️  Search service is not running")
                print(f"   Start with: macf_tools search-service start")

        return 0

    except Exception as e:
        print(f"❌ Error getting status: {e}")
        return 1


# -------- parser --------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="macf_tools", description="macf demo CLI (no external deps)"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_ver}")
    sub = p.add_subparsers(dest="cmd")  # keep non-required for compatibility
    env_parser = sub.add_parser("env", help="print environment summary")
    env_parser.add_argument("--json", action="store_true", help="output as JSON")
    env_parser.set_defaults(func=cmd_env)
    sub.add_parser("time", help="print current local time with CCP gap").set_defaults(func=cmd_time)
    sub.add_parser("budget", help="print budget thresholds (JSON)").set_defaults(func=cmd_budget)

    # New consciousness commands
    list_parser = sub.add_parser("list", help="list consciousness artifacts")
    list_sub = list_parser.add_subparsers(dest="list_cmd")
    ccps_parser = list_sub.add_parser("ccps", help="list consciousness checkpoints")
    ccps_parser.add_argument("--recent", type=int, help="limit to N most recent CCPs")
    ccps_parser.set_defaults(func=cmd_list_ccps)

    session_parser = sub.add_parser("session", help="session management")
    session_sub = session_parser.add_subparsers(dest="session_cmd")
    session_sub.add_parser("info", help="show session information").set_defaults(func=cmd_session_info)

    # Hook commands
    hook_parser = sub.add_parser("hooks", help="hook management")
    hook_sub = hook_parser.add_subparsers(dest="hook_cmd")

    install_parser = hook_sub.add_parser("install", help="install compaction detection hook")
    install_parser.add_argument("--local", dest="local_install", action="store_true",
                               help="install to local project (default)")
    install_parser.add_argument("--global", dest="global_install", action="store_true",
                               help="install to global ~/.claude directory")
    install_parser.set_defaults(func=cmd_hook_install)

    hook_sub.add_parser("test", help="test compaction detection on current session").set_defaults(func=cmd_hook_test)

    logs_parser = hook_sub.add_parser("logs", help="display hook event logs")
    logs_parser.add_argument("--session", help="specific session ID (default: current)")
    logs_parser.set_defaults(func=cmd_hook_logs)

    hook_sub.add_parser("status", help="display current hook states").set_defaults(func=cmd_hook_status)

    # Framework commands (unified installation of hooks, commands, skills)
    framework_parser = sub.add_parser("framework", help="framework artifact management")
    framework_sub = framework_parser.add_subparsers(dest="framework_cmd")

    fw_install = framework_sub.add_parser("install", help="install framework artifacts (hooks, commands, skills)")
    fw_install.add_argument("--hooks-only", dest="hooks_only", action="store_true",
                           help="install only hooks (backward compatibility)")
    fw_install.add_argument("--skip-hooks", dest="skip_hooks", action="store_true",
                           help="skip hook installation (commands and skills only)")
    fw_install.set_defaults(func=cmd_framework_install)

    # Config commands
    config_parser = sub.add_parser("config", help="agent configuration management")
    config_sub = config_parser.add_subparsers(dest="config_cmd")

    init_parser = config_sub.add_parser("init", help="initialize agent configuration")
    init_parser.add_argument("--force", action="store_true", help="overwrite existing config")
    init_parser.set_defaults(func=cmd_config_init)

    config_sub.add_parser("show", help="show current configuration").set_defaults(func=cmd_config_show)

    # Claude Code configuration commands
    claude_config_parser = sub.add_parser("claude-config", help="Claude Code settings management")
    claude_config_sub = claude_config_parser.add_subparsers(dest="claude_config_cmd")

    claude_config_sub.add_parser("init", help="set recommended defaults (verbose=true, autoCompact=false)").set_defaults(func=cmd_claude_config_init)
    claude_config_sub.add_parser("show", help="show current .claude.json configuration").set_defaults(func=cmd_claude_config_show)

    # Agent commands
    agent_parser = sub.add_parser("agent", help="agent initialization and management")
    agent_sub = agent_parser.add_subparsers(dest="agent_cmd")

    agent_sub.add_parser("init", help="initialize agent with PA preamble").set_defaults(func=cmd_agent_init)

    # Agent backup subcommands
    backup_parser = agent_sub.add_parser("backup", help="consciousness backup operations")
    backup_sub = backup_parser.add_subparsers(dest="backup_cmd")

    backup_create = backup_sub.add_parser("create", help="create consciousness backup archive")
    backup_create.add_argument("--output", "-o", type=Path, help="output directory (default: CWD)")
    backup_create.add_argument("--no-transcripts", action="store_true", help="exclude transcripts")
    backup_create.add_argument("--quick", action="store_true", help="only recent transcripts (7 days)")
    backup_create.set_defaults(func=cmd_backup_create)

    backup_list = backup_sub.add_parser("list", help="list backup archives")
    backup_list.add_argument("--dir", type=Path, help="directory to scan (default: CWD)")
    backup_list.add_argument("--json", dest="json_output", action="store_true", help="output as JSON")
    backup_list.set_defaults(func=cmd_backup_list)

    backup_info = backup_sub.add_parser("info", help="show backup archive info")
    backup_info.add_argument("archive", type=Path, help="path to archive")
    backup_info.add_argument("--json", dest="json_output", action="store_true", help="output as JSON")
    backup_info.set_defaults(func=cmd_backup_info)

    # Agent restore subcommands
    restore_parser = agent_sub.add_parser("restore", help="consciousness restore operations")
    restore_sub = restore_parser.add_subparsers(dest="restore_cmd")

    restore_verify = restore_sub.add_parser("verify", help="verify archive integrity")
    restore_verify.add_argument("archive", type=Path, help="path to archive")
    restore_verify.add_argument("-v", "--verbose", action="store_true", help="show missing/corrupted file details")
    restore_verify.set_defaults(func=cmd_restore_verify)

    restore_install = restore_sub.add_parser("install", help="install backup to target")
    restore_install.add_argument("archive", type=Path, help="path to archive")
    restore_install.add_argument("--target", type=Path, help="target directory (default: CWD)")
    restore_install.add_argument("--transplant", action="store_true", help="rewrite paths for new system")
    restore_install.add_argument("--maceff-root", type=Path, help="MacEff location (default: sibling of target)")
    restore_install.add_argument("--force", action="store_true", help="overwrite existing consciousness (creates checkpoint)")
    restore_install.add_argument("--dry-run", action="store_true", help="show what would be done")
    restore_install.set_defaults(func=cmd_restore_install)

    # Context command
    context_parser = sub.add_parser("context", help="show token usage and CLUAC level")
    context_parser.add_argument("--json", dest="json_output", action="store_true",
                               help="output as JSON")
    context_parser.add_argument("--session", help="specific session ID (default: current)")
    context_parser.set_defaults(func=cmd_context)

    # Statusline command with subcommands
    statusline_parser = sub.add_parser("statusline", help="statusline operations for Claude Code")
    statusline_sub = statusline_parser.add_subparsers(dest="statusline_cmd")

    # statusline (default - generate output)
    statusline_generate = statusline_sub.add_parser("generate", help="generate formatted statusline output")
    statusline_generate.set_defaults(func=cmd_statusline)

    # statusline install
    statusline_install = statusline_sub.add_parser("install", help="install statusline script and configure Claude Code")
    statusline_install.set_defaults(func=cmd_statusline_install)

    # Default to generate if no subcommand
    statusline_parser.set_defaults(func=cmd_statusline)

    # Breadcrumb command
    breadcrumb_parser = sub.add_parser("breadcrumb", help="generate fresh breadcrumb for TODO completion")
    breadcrumb_parser.add_argument("--json", dest="json_output", action="store_true",
                                  help="output as JSON with components")
    breadcrumb_parser.set_defaults(func=cmd_breadcrumb)

    # DEV_DRV forensic command
    dev_drv_parser = sub.add_parser("dev_drv", help="extract and display DEV_DRV from JSONL")
    dev_drv_parser.add_argument("--breadcrumb", required=True,
                               help="breadcrumb string like s_abc12345/c_42/g_abc1234/p_def5678/t_1234567890")
    dev_drv_parser.add_argument("--raw", action="store_true",
                               help="output raw JSONL (default: markdown summary)")
    dev_drv_parser.add_argument("--md", action="store_true",
                               help="output markdown summary (default)")
    dev_drv_parser.add_argument("--output", help="output file path (default: stdout)")
    dev_drv_parser.set_defaults(func=cmd_dev_drv)

    # Policy commands
    policy_parser = sub.add_parser("policy", help="policy manifest management")
    policy_sub = policy_parser.add_subparsers(dest="policy_cmd")

    # policy manifest
    manifest_parser = policy_sub.add_parser("manifest", help="display merged and filtered policy manifest")
    manifest_parser.add_argument("--format", choices=["json", "summary"], default="summary",
                                help="output format (default: summary)")
    manifest_parser.set_defaults(func=cmd_policy_manifest)

    # policy search
    search_parser = policy_sub.add_parser("search", help="search for keyword in policy manifest")
    search_parser.add_argument("keyword", help="keyword to search for")
    search_parser.set_defaults(func=cmd_policy_search)

    # policy navigate
    navigate_parser = policy_sub.add_parser("navigate", help="show CEP navigation guide (up to boundary)")
    navigate_parser.add_argument("policy_name", help="policy name (e.g., todo_hygiene, development/todo_hygiene)")
    navigate_parser.set_defaults(func=cmd_policy_navigate)

    # policy read
    read_parser = policy_sub.add_parser("read", help="read policy with line numbers and caching")
    read_parser.add_argument("policy_name", help="policy name (e.g., todo_hygiene, development/todo_hygiene)")
    read_parser.add_argument("--lines", help="line range START:END (e.g., 50:100)")
    read_parser.add_argument("--section", help="section number to read (e.g., 5, 5.1) - includes subsections")
    read_parser.add_argument("--force", action="store_true", help="bypass cache for full read")
    read_parser.add_argument("--from-nav-boundary", action="store_true", help="start after CEP_NAV_BOUNDARY (use after navigate)")
    read_parser.set_defaults(func=cmd_policy_read)

    # policy list
    list_parser = policy_sub.add_parser("list", help="list policy files from framework")
    list_parser.add_argument("--tier", choices=["CORE", "optional"], help="filter by tier")
    list_parser.add_argument("--category", help="filter by category (development, consciousness, meta)")
    list_parser.set_defaults(func=cmd_policy_list)

    # policy ca-types
    ca_types_parser = policy_sub.add_parser("ca-types", help="show CA types with emojis")
    ca_types_parser.set_defaults(func=cmd_policy_ca_types)

    # policy recommend
    recommend_parser = policy_sub.add_parser("recommend", help="hybrid search policy recommendations")
    recommend_parser.add_argument("query", help="natural language query (minimum 10 chars)")
    recommend_parser.add_argument("--json", dest="json_output", action="store_true",
                                  help="output as JSON for automation")
    recommend_parser.add_argument("--explain", action="store_true",
                                  help="show detailed retriever breakdown")
    recommend_parser.add_argument("--limit", type=int, default=5,
                                  help="max results to show (default: 5)")
    recommend_parser.set_defaults(func=cmd_policy_recommend)

    # policy build_index
    build_index_parser = policy_sub.add_parser("build_index", help="build hybrid FTS5 + semantic index")
    build_index_parser.add_argument("--policies-dir", help="path to policies directory")
    build_index_parser.add_argument("--db-path", help="output database path")
    build_index_parser.add_argument("--skip-embeddings", action="store_true",
                                    help="skip embedding generation (FTS5 only)")
    build_index_parser.add_argument("--json", dest="json_output", action="store_true",
                                    help="output stats as JSON")
    build_index_parser.set_defaults(func=cmd_policy_build_index)

    # Mode commands
    mode_parser = sub.add_parser("mode", help="operating mode management (MANUAL_MODE/AUTO_MODE)")
    mode_sub = mode_parser.add_subparsers(dest="mode_cmd")

    mode_get = mode_sub.add_parser("get", help="get current operating mode")
    mode_get.add_argument("--json", dest="json_output", action="store_true",
                         help="output as JSON")
    mode_get.set_defaults(func=cmd_mode_get)

    mode_set = mode_sub.add_parser("set", help="set operating mode")
    mode_set.add_argument("mode", help="mode to set (AUTO_MODE or MANUAL_MODE)")
    mode_set.add_argument("--auth-token", dest="auth_token",
                         help="auth token for AUTO_MODE activation")
    mode_set.set_defaults(func=cmd_mode_set)

    # Events commands
    events_parser = sub.add_parser("events", help="agent events log management")
    events_sub = events_parser.add_subparsers(dest="events_cmd")

    # events show
    show_parser = events_sub.add_parser("show", help="display current agent state")
    show_parser.add_argument("--json", dest="json_output", action="store_true",
                            help="output as JSON")
    show_parser.set_defaults(func=cmd_events_show)

    # events history
    history_parser = events_sub.add_parser("history", help="show recent events")
    history_parser.add_argument("--limit", type=int, default=10,
                               help="number of events to show (default: 10)")
    history_parser.set_defaults(func=cmd_events_history)

    # events query
    query_parser = events_sub.add_parser("query", help="query events with filters")
    query_parser.add_argument("--event", help="filter by event type")
    query_parser.add_argument("--cycle", help="filter by cycle number")
    query_parser.add_argument("--git-hash", help="filter by git hash")
    query_parser.add_argument("--session", help="filter by session ID")
    query_parser.add_argument("--prompt", help="filter by prompt UUID")
    query_parser.add_argument("--after", help="events after timestamp")
    query_parser.add_argument("--before", help="events before timestamp")
    query_parser.add_argument("--command", help="filter cli_command_invoked by command (e.g., 'policy read')")
    query_parser.add_argument("--verbose", "-v", action="store_true", help="show full event data")
    query_parser.set_defaults(func=cmd_events_query)

    # events query-set
    query_set_parser = events_sub.add_parser("query-set", help="perform set operations on queries")
    query_set_parser.add_argument("--query", help="base query (format: key=value)")
    query_set_parser.add_argument("--subtract", help="subtract query (format: key=value)")
    query_set_parser.set_defaults(func=cmd_events_query_set)

    # events sessions
    sessions_parser = events_sub.add_parser("sessions", help="session analysis")
    sessions_sub = sessions_parser.add_subparsers(dest="sessions_cmd")
    sessions_sub.add_parser("list", help="list all sessions").set_defaults(func=cmd_events_sessions_list)

    # events stats
    events_sub.add_parser("stats", help="display event statistics").set_defaults(func=cmd_events_stats)

    # events gaps
    gaps_parser = events_sub.add_parser("gaps", help="detect time gaps (crashes)")
    gaps_parser.add_argument("--threshold", type=float, default=3600,
                            help="gap threshold in seconds (default: 3600)")
    gaps_parser.set_defaults(func=cmd_events_gaps)

    # Todos commands (TODO collapse authorization)
    todos_parser = sub.add_parser("todos", help="TODO list management and collapse authorization")
    todos_sub = todos_parser.add_subparsers(dest="todos_cmd")

    # todos list
    todos_list_parser = todos_sub.add_parser("list", help="show active TODO list")
    todos_list_parser.add_argument("--json", dest="json_output", action="store_true",
                                   help="output as JSON")
    todos_list_parser.add_argument("--previous", "-p", type=int, default=0, metavar="N",
                                   help="show Nth previous TODO list (0=current, 1=previous, etc.)")
    todos_list_parser.add_argument("--filter", "-f", choices=["all", "active", "completed"],
                                   default="all",
                                   help="filter by status (active=pending+in_progress)")
    todos_list_parser.set_defaults(func=cmd_todos_list)

    # todos status
    todos_sub.add_parser("status", help="show TODO status summary").set_defaults(func=cmd_todos_status)

    # todos auth-collapse
    auth_collapse_parser = todos_sub.add_parser("auth-collapse", help="authorize a TODO collapse")
    auth_collapse_parser.add_argument("--from", dest="from_count", type=int, required=True,
                                      help="current item count")
    auth_collapse_parser.add_argument("--to", dest="to_count", type=int, required=True,
                                      help="target item count after collapse")
    auth_collapse_parser.add_argument("--reason", help="reason for collapse")
    auth_collapse_parser.set_defaults(func=cmd_todos_auth_collapse)

    # todos auth-item-edit
    auth_item_edit_parser = todos_sub.add_parser("auth-item-edit", help="authorize editing TODO item(s) content")
    auth_item_edit_parser.add_argument("--index", type=str, required=True,
                                       help="indices to edit: single (13), range (13-17), or list (13,14,15)")
    auth_item_edit_parser.add_argument("--reason", help="reason for edit")
    auth_item_edit_parser.set_defaults(func=cmd_todos_auth_item_edit)

    # todos auth-restore
    auth_restore_parser = todos_sub.add_parser("auth-restore", help="authorize restoring TODO list from previous state")
    auth_restore_parser.add_argument("--previous", "-p", type=int, required=True, metavar="N",
                                     help="restore from Nth previous state (1=last, 2=before that)")
    auth_restore_parser.add_argument("--reason", help="reason for restore")
    auth_restore_parser.set_defaults(func=cmd_todos_auth_restore)

    # todos auth-status
    todos_sub.add_parser("auth-status", help="show pending authorization").set_defaults(func=cmd_todos_auth_status)

    # Task commands (MACF Task CLI)
    task_parser = sub.add_parser("task", help="task management with MTMD support")
    task_sub = task_parser.add_subparsers(dest="task_cmd")

    # task list
    task_list_parser = task_sub.add_parser("list", help="list tasks with hierarchy")
    task_list_parser.add_argument("--json", dest="json_output", action="store_true",
                                  help="output as JSON")
    task_list_parser.add_argument("--type", dest="type_filter",
                                  choices=["MISSION", "EXPERIMENT", "DETOUR", "PHASE"],
                                  help="filter by task type")
    task_list_parser.add_argument("--status", dest="status_filter",
                                  choices=["pending", "in_progress", "completed"],
                                  help="filter by status")
    task_list_parser.add_argument("--parent", dest="parent_filter", type=int,
                                  help="filter by parent task ID")
    task_list_parser.set_defaults(func=cmd_task_list)

    # task get
    task_get_parser = task_sub.add_parser("get", help="get task details")
    task_get_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_get_parser.add_argument("--json", dest="json_output", action="store_true",
                                 help="output as JSON")
    task_get_parser.set_defaults(func=cmd_task_get)

    # task tree
    task_tree_parser = task_sub.add_parser("tree", help="show task hierarchy tree")
    task_tree_parser.add_argument("task_id", help="root task ID (e.g., #67 or 67)")
    task_tree_parser.set_defaults(func=cmd_task_tree)

    # task edit
    task_edit_parser = task_sub.add_parser("edit", help="edit task JSON field")
    task_edit_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_edit_parser.add_argument("field", help="field to edit (subject, status, description)")
    task_edit_parser.add_argument("value", help="new value for the field")
    task_edit_parser.set_defaults(func=cmd_task_edit)

    # task edit-mtmd
    task_edit_mtmd_parser = task_sub.add_parser("edit-mtmd", help="edit MTMD field")
    task_edit_mtmd_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_edit_mtmd_parser.add_argument("field", help="MTMD field to edit")
    task_edit_mtmd_parser.add_argument("value", help="new value for the field")
    task_edit_mtmd_parser.set_defaults(func=cmd_task_edit_mtmd)

    # task add-mtmd
    task_add_mtmd_parser = task_sub.add_parser("add-mtmd", help="add custom MTMD field")
    task_add_mtmd_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_add_mtmd_parser.add_argument("key", help="custom field key")
    task_add_mtmd_parser.add_argument("value", help="custom field value")
    task_add_mtmd_parser.set_defaults(func=cmd_task_add_mtmd)

    # Search service commands
    search_service_parser = sub.add_parser("search-service", help="search service daemon management")
    search_service_sub = search_service_parser.add_subparsers(dest="search_service_cmd")

    # search-service start
    start_parser = search_service_sub.add_parser("start", help="start search service daemon")
    start_parser.add_argument("--daemon", "-d", action="store_true",
                             help="run in background (daemonize)")
    start_parser.add_argument("--port", type=int, default=9001,
                             help="port to listen on (default: 9001)")
    start_parser.set_defaults(func=cmd_search_service_start)

    # search-service stop
    search_service_sub.add_parser("stop", help="stop running search service").set_defaults(func=cmd_search_service_stop)

    # search-service status
    status_parser = search_service_sub.add_parser("status", help="show search service status")
    status_parser.add_argument("--json", dest="json_output", action="store_true",
                              help="output as JSON")
    status_parser.set_defaults(func=cmd_search_service_status)

    return p

def main(argv=None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "cmd", None):
        # Capture argv before try block to avoid scope issues in exception handler
        argv_list = argv if argv else sys.argv[1:]
        # Log CLI command invocation for forensic reconstruction
        try:
            session_id = get_current_session_id()
            cmd = getattr(args, "cmd", "unknown")
            subcmd = getattr(args, "subcmd", None)
            command_str = f"{cmd} {subcmd}" if subcmd else cmd
            append_event(
                event="cli_command_invoked",
                data={
                    "session_id": session_id,
                    "command": command_str,
                    "argv": argv_list
                }
            )
        except Exception as e:
            # Log error but don't break CLI functionality (use print, not sys.stderr)
            print(f"🏗️ MACF | ❌ CLI event logging error: {e}")
        exit(args.func(args))
    parser.print_help()

if __name__ == "__main__":
    main()
