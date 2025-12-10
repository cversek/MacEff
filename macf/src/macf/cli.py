# tools/src/maceff/cli.py
import argparse, json, os, sys, glob
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
from .utils import (
    get_current_session_id,
    get_dev_scripts_dir,
    get_hooks_dir,
    get_formatted_timestamp,
    get_token_info
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
def cmd_env(_: argparse.Namespace) -> int:
    warn = float(os.getenv("MACEFF_TOKEN_WARN", "0.85"))
    hard = float(os.getenv("MACEFF_TOKEN_HARD", "0.95"))
    mode = os.getenv("MACEFF_BUDGET_MODE", "concise/default")
    vcs = "git" if (Path.cwd() / ".git").exists() else "none"
    tz = _pick_tz()
    tz_label = getattr(tz, "key", None) or str(tz)

    data = {
        "time_local": _now_iso(tz),
        "time_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "tz": tz_label,
        "time_source": "env",  # future: "gateway"
        "budget": {
            "adapter": "absent",
            "mode": mode,
            "thresholds": {"warn": warn, "hard": hard},
        },
        "persistence": {"adapter": "absent", "plan": "emit checkpoints inline"},
        "cwd": str(Path.cwd()),
        "vcs": vcs,
    }
    print(json.dumps(data, indent=2))
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
    """Install all 6 consciousness hooks with local/global mode selection."""
    try:
        # Determine installation mode
        if hasattr(args, 'global_install') and args.global_install:
            mode = 'global'
        elif hasattr(args, 'local_install') and args.local_install:
            mode = 'local'
        else:
            # Interactive mode
            print("\nWhere do you want to install hooks?")
            print("[1] Local project (.claude/hooks/) [DEFAULT]")
            print("[2] Global user directory (~/.claude/hooks/)")
            choice = input("\nPress Enter for [1], or enter choice: ").strip() or "1"
            mode = 'global' if choice == '2' else 'local'

        # Set paths based on mode
        if mode == 'global':
            hooks_dir = Path.home() / ".claude" / "hooks"
            settings_file = Path.home() / ".claude" / "settings.json"
            hooks_prefix = "python ~/.claude/hooks"
        else:
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
            # On host: try to find project root with .claude/
            try:
                from .utils import find_project_root
                project_root = find_project_root()
                if project_root:
                    pa_home = project_root
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


def _get_policy_read_cache(session_id: str) -> dict:
    """Get policy reads cache from session state."""
    from .utils.state import get_session_state_path, read_json_safely
    state_path = get_session_state_path(session_id)
    state = read_json_safely(state_path)
    return state.get('policy_reads', {})


def _update_policy_read_cache(session_id: str, policy_name: str, breadcrumb: str) -> bool:
    """Update policy reads cache in session state."""
    from .utils.state import get_session_state_path, read_json_safely, write_json_safely
    state_path = get_session_state_path(session_id)
    state = read_json_safely(state_path)

    # Initialize policy_reads if needed
    if 'policy_reads' not in state:
        state['policy_reads'] = {}

    state['policy_reads'][policy_name] = breadcrumb

    # Ensure directory exists
    state_path.parent.mkdir(parents=True, exist_ok=True)
    return write_json_safely(state_path, state)


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
        for i, line in enumerate(nav_content.split('\n'), 1):
            print(f"{i:4d}│ {line}")

        print(f"\n=== End Navigation Guide ===")
        print(f"\nTo read full policy: macf_tools policy read {args.policy_name}")
        print(f"To read specific section: macf_tools policy read {args.policy_name} --section N")

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
            # Find section by heading number, include subsections
            # Stop only at same-or-higher level heading (not subsections)
            in_section = False
            section_lines = []
            section_start = 0
            section_level = 0  # Track heading level (## = 2, ### = 3, etc.)

            for i, line in enumerate(lines):
                if line.startswith('#'):
                    # Count heading level
                    level = len(line) - len(line.lstrip('#'))
                    heading_text = line.lstrip('#').strip()

                    if heading_text:
                        heading_num = heading_text.split()[0].rstrip('.')

                        if heading_num == section_num:
                            # Found target section
                            in_section = True
                            section_start = i + 1
                            section_level = level
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
            # Full read - check cache (unless --force)
            if not force_read:
                cache = _get_policy_read_cache(session_id)
                if cache_key in cache:
                    cached_breadcrumb = cache[cache_key]
                    print(f"Already read at {cached_breadcrumb}")
                    print(f"\nUse --force to re-read, or --section N for specific section")
                    return 0

        # Output with line numbers
        print(f"=== {policy_path.name} ===\n")
        for i, line in enumerate(lines, line_offset):
            print(f"{i:4d}│ {line}")

        # Cache full reads only (not partial)
        if not is_partial:
            breadcrumb = get_breadcrumb()
            _update_policy_read_cache(session_id, cache_key, breadcrumb)
            print(f"\n=== Read logged at {breadcrumb} ===")
        else:
            print(f"\n=== Partial read (not cached) ===")

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
    """Search for keyword in policy manifest."""
    from .utils import load_merged_manifest, filter_active_policies

    try:
        keyword = args.keyword.lower()

        # Load and filter manifest
        manifest = load_merged_manifest()
        filtered = filter_active_policies(manifest)

        matches = []

        # Search mandatory policies
        mandatory = filtered.get('mandatory_policies', {}).get('policies', [])
        for policy in mandatory:
            name = policy.get('name', '')
            desc = policy.get('description', '')
            keywords_list = policy.get('keywords', [])

            if (keyword in name.lower() or
                keyword in desc.lower() or
                any(keyword in kw.lower() for kw in keywords_list)):
                matches.append(('mandatory', name, desc))

        # Search development policies
        dev = filtered.get('development_policies', {}).get('policies', [])
        for policy in dev:
            name = policy.get('name', '')
            desc = policy.get('description', '')
            keywords_list = policy.get('keywords', [])

            if (keyword in name.lower() or
                keyword in desc.lower() or
                any(keyword in kw.lower() for kw in keywords_list)):
                matches.append(('development', name, desc))

        # Search consciousness patterns
        patterns = filtered.get('consciousness_patterns', {}).get('triggers', [])
        for pattern in patterns:
            pattern_name = pattern.get('pattern', '')
            consciousness = pattern.get('consciousness', '')
            search_terms = pattern.get('search_terms', [])

            if (keyword in pattern_name.lower() or
                keyword in consciousness.lower() or
                any(keyword in term.lower() for term in search_terms)):
                matches.append(('consciousness_pattern', pattern_name, consciousness))

        # Display results
        print(f"Search results for '{keyword}': {len(matches)} matches")
        print("=" * 50)

        if matches:
            for section, name, desc in matches:
                print(f"[{section}] {name}: {desc}")
        else:
            print("No matches found")

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

        policies = list_policy_files(tier=tier, category=category)

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
        for p in policies:
            cat = p['category']
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(p)

        for cat in sorted(by_category.keys()):
            print(f"\n{cat}/")
            for p in by_category[cat]:
                tier_str = f" [{p['tier']}]" if p.get('tier') else ""
                print(f"  {p['name']}.md{tier_str}")

        print(f"\nTotal: {len(policies)} policies")
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


# -------- parser --------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="macf_tools", description="macf demo CLI (no external deps)"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_ver}")
    sub = p.add_subparsers(dest="cmd")  # keep non-required for compatibility
    sub.add_parser("env", help="print env summary (JSON)").set_defaults(func=cmd_env)
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
    read_parser.add_argument("--section", help="section number to read (e.g., 5)")
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

    return p

def main(argv=None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "cmd", None):
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
                    "argv": argv if argv else sys.argv[1:]
                }
            )
        except Exception as e:
            # Log error but don't break CLI functionality
            import traceback
            print(f"🏗️ MACF | ❌ CLI event logging error: {e}", file=sys.stderr)
        exit(args.func(args))
    parser.print_help()

if __name__ == "__main__":
    main()
