# PYTHON_ARGCOMPLETE_OK
# tools/src/maceff/cli.py
import argparse, json, os, re, subprocess, sys, glob, platform, socket, time, unicodedata
from pathlib import Path
from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

try:
    from importlib.metadata import version
    _ver = version("macf")
except (ImportError, Exception):
    _ver = "0.0.0"

from .config import ConsciousnessConfig
from .hooks.compaction import detect_compaction, inject_recovery
from .agent_events_log import append_event
from .event_queries import get_cycle_number_from_events
from .task.reader import TaskReader
from .task.create import subject_with_live_parent
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
    get_agent_identity,
    find_project_root,
    find_maceff_root,
    get_macf_package_path,
    get_hooks_dir,
    get_total_context,
)
from .utils.environment import detect_model

# -------- ANSI escape codes --------
ANSI_RESET = "\033[0m"
ANSI_RED = "\033[31m"
ANSI_GREEN = "\033[32m"
ANSI_YELLOW = "\033[33m"
ANSI_DIM = "\033[2m"
ANSI_STRIKE = "\033[9m"
ANSI_STRIKE_OFF = "\033[29m"


def _dim_task_ids(text: str) -> str:
    """Wrap task ID patterns (#N and [^#N]) in dim ANSI codes."""
    import re
    # Pattern matches: #123 at start, or [^#123] anywhere
    # Replace #N at start with dim version
    text = re.sub(r'^(#\d+)', f'{ANSI_DIM}\\1{ANSI_RESET}', text)
    # Replace [^#N] with dim version
    text = re.sub(r'(\[\^#\d+\])', f'{ANSI_DIM}\\1{ANSI_RESET}', text)
    return text


def _strip_ansi(text: str) -> str:
    """Strip all ANSI escape codes from text."""
    import re
    return re.sub(r'\x1b\[[0-9;]*m', '', text)


def _truncate_subject_title(subject: str, width: int) -> str:
    """Trim the semantic title of a composed subject to `width` visible chars.

    Only the free-text title is shortened. The structural prefix — id, `[^#N]`
    parent marker, and type marker (`🗺️ MISSION:`, `🐙 GH/owner/repo#3 [bug]:`,
    `🔧`, …) — is preserved in full, as are anything appended downstream
    (timestamps, scope/recency markers), which are added after this runs.

    Width is measured on visible characters, so ANSI styling never eats budget.
    """
    if not width or width <= 0:
        return subject

    import re
    # The title starts after the structural prefix. Type markers end in ':' for
    # the labelled types; the bare-emoji types (🔧, 📋, -) have no colon, so fall
    # back to the id/parent prefix and treat the remainder as the title.
    visible = _strip_ansi(subject)
    m = re.match(r'^(\s*#\d+\s*)?(\[\^#\d+\]\s*)?(\S+[^:]*:\s*)?', visible)
    prefix_len = m.end() if m else 0
    title = visible[prefix_len:]
    if len(title) <= width:
        return subject

    trimmed = title[:max(1, width - 3)].rstrip() + '...'
    # Rebuild against the original so ANSI in the prefix survives; the title
    # region of a composed subject carries no styling of its own.
    idx = subject.find(title[:20]) if len(title) >= 20 else subject.find(title)
    if idx == -1:
        return subject
    return subject[:idx] + trimmed


# -------- helpers --------
def _pick_tz():
    """Prefer MACEFF_TZ, then TZ, else system local; fall back to UTC."""
    for key in ("MACEFF_TZ", "TZ"):
        name = os.getenv(key)
        if name and ZoneInfo is not None:
            try:
                return ZoneInfo(name)
            except (ValueError, KeyError) as e:
                print(f"⚠️ MACF: invalid timezone '{name}' in {key}: {e}", file=sys.stderr)
    try:
        return datetime.now().astimezone().tzinfo or timezone.utc
    except OSError as e:
        print(f"⚠️ MACF: could not detect system timezone: {e}", file=sys.stderr)
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
    except (OSError, IOError, OverflowError, ValueError) as e:
        print(f"⚠️ MACF: file age calculation failed: {e}", file=sys.stderr)
        return "unknown"

def _parse_task_id_arg(arg: str):
    """Parse a task ID CLI argument into the form TaskReader.read_task expects.

    Accepts: ``N``, ``#N``, ``000``, ``#000``, ``00X`` and other leading-zero
    forms (used by the sentinel ``000`` and reserved hierarchy slots like
    ``00X``). Returns ``int`` for plain digit IDs, ``str`` for leading-zero
    IDs and non-numeric forms.

    Raises ``ValueError`` for empty input after stripping the optional ``#``
    prefix; callers should catch and emit their own user-facing error.

    This unifies the parsing rule across all ``cmd_task_*`` handlers. Prior
    to this helper, ``cmd_task_get`` had a leading-zero special branch while
    most other handlers did a bare ``int()`` conversion that silently turned
    ``000`` into ``0`` and then failed lookup against the string-keyed
    sentinel — see GH issue #68.
    """
    cleaned = arg.lstrip('#')
    if not cleaned:
        raise ValueError("empty task ID")
    # Preserve string identity for leading-zero forms (the "000" sentinel,
    # reserved hierarchy slots like "00X", etc.)
    if cleaned.startswith('0') and len(cleaned) > 1:
        return cleaned
    try:
        return int(cleaned)
    except ValueError:
        # Non-numeric IDs (legacy) — pass through as-is.
        return cleaned


# -------- commands --------
def cmd_tree(args: argparse.Namespace, root_parser: argparse.ArgumentParser = None) -> int:
    """Print command tree by introspecting argparse parser structure.

    Modeled after unix 'tree' command - minimal token output showing
    subcommand structure with usage strings at leaves.

    Uses argparse internal attributes:
    - parser._actions to find all actions
    - isinstance(action, argparse._SubParsersAction) to identify subparsers
    - action.choices to get {name: parser} mapping
    """
    if root_parser is None:
        # Parser will be injected by main() after construction
        print("Error: Parser not available", file=sys.stderr)
        return 1

    def get_args_string(parser: argparse.ArgumentParser) -> str:
        """Build args string from parser actions (cleaner than parsing usage).

        Distinguishes required from optional args and renders mutually
        exclusive required groups with (--a A | --b B) notation.
        """
        parts = []

        # Collect actions that belong to required mutually exclusive groups
        mutex_actions = set()
        mutex_groups = []
        for group in parser._mutually_exclusive_groups:
            if group.required:
                group_parts = []
                for action in group._group_actions:
                    mutex_actions.add(id(action))
                    opts = action.option_strings[0] if action.option_strings else action.dest
                    meta = action.metavar or action.dest.upper()
                    if action.nargs == 0:
                        group_parts.append(opts)
                    else:
                        group_parts.append(f"{opts} {meta}")
                mutex_groups.append(f"({' | '.join(group_parts)})")

        for action in parser._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            if isinstance(action, argparse._SubParsersAction):
                continue
            if id(action) in mutex_actions:
                continue  # Rendered as group below
            if action.option_strings:
                opts = action.option_strings[0]
                if action.nargs == 0:
                    parts.append(f"[{opts}]")
                elif action.required:
                    parts.append(f"{opts} {action.metavar or action.dest.upper()}")
                else:
                    parts.append(f"[{opts} {action.metavar or action.dest.upper()}]")
            else:
                name = action.metavar or action.dest
                if action.nargs in ('?', '*'):
                    parts.append(f"[{name}]")
                elif action.nargs == '+':
                    parts.append(f"{name} [{name} ...]")
                else:
                    parts.append(name)

        # Insert mutex groups after required positional/named args, before optional flags
        return ' '.join(mutex_groups + parts)

    def get_subparsers(parser: argparse.ArgumentParser) -> dict:
        """Get {name: parser} dict of subcommands from parser."""
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                return dict(action.choices)
        return {}

    def print_tree(parser: argparse.ArgumentParser, prefix: str = "", name: str = "macf_tools", is_last: bool = True):
        """Recursively print parser tree in unix tree format."""
        # Connector characters
        connector = "└── " if is_last else "├── "
        extension = "    " if is_last else "│   "

        # Get subparsers for this parser
        subparsers = get_subparsers(parser)

        if subparsers:
            # Has subcommands - print name only
            print(f"{prefix}{connector}{name}")
            # Recurse into subcommands
            items = sorted(subparsers.items())
            for i, (subcmd_name, subcmd_parser) in enumerate(items):
                is_last_child = (i == len(items) - 1)
                print_tree(subcmd_parser, prefix + extension, subcmd_name, is_last_child)
        else:
            # Leaf node - print name with args
            args_str = get_args_string(parser)
            if args_str:
                print(f"{prefix}{connector}{name} {args_str}")
            else:
                print(f"{prefix}{connector}{name}")

    print("macf_tools")
    subparsers = get_subparsers(root_parser)
    items = sorted(subparsers.items())
    for i, (name, parser) in enumerate(items):
        is_last = (i == len(items) - 1)
        print_tree(parser, "", name, is_last)

    return 0


def cmd_env(args: argparse.Namespace) -> int:
    """Print comprehensive environment summary."""
    temporal = get_temporal_context()
    session_id = get_current_session_id()

    # Get agent home path
    try:
        agent_home = find_agent_home()
    except (OSError, IOError) as e:
        print(f"⚠️ MACF: agent home detection failed: {e}", file=sys.stderr)
        agent_home = None

    # Count installed hooks (in .claude/hooks/)
    hooks_dir = agent_home / ".claude" / "hooks" if agent_home else None
    hooks_count = len(list(hooks_dir.glob("*.py"))) if hooks_dir and hooks_dir.exists() else 0

    # Get auto mode status
    auto_enabled, _ = detect_auto_mode(session_id)

    # Resolve paths safely
    def resolve_path(p):
        try:
            return str(p.resolve()) if p and p.exists() else str(p) if p else "(not set)"
        except (OSError, IOError) as e:
            print(f"⚠️ MACF: path resolution failed: {e}", file=sys.stderr)
            return str(p) if p else "(not set)"

    from macf.utils.paths import detect_cc_binary
    _detect_cc_binary = detect_cc_binary

    # Get agent identity
    agent_identity = get_agent_identity()

    # Compute CC internal paths
    try:
        project_root = find_project_root()
        from macf.utils.paths import encode_cc_project_path
        encoded_path = encode_cc_project_path(str(project_root))
        cc_project_dir = Path.home() / ".claude" / "projects" / encoded_path
    except (OSError, IOError, ValueError) as e:
        print(f"⚠️ MACF: CC project dir detection failed: {e}", file=sys.stderr)
        cc_project_dir = None

    # CC Tasks path (use TaskReader for session detection)
    try:
        reader = TaskReader()
        cc_tasks_dir = reader.session_path if reader.session_path else None
    except (OSError, IOError, ValueError) as e:
        print(f"⚠️ MACF: CC tasks dir detection failed: {e}", file=sys.stderr)
        cc_tasks_dir = None

    # Get framework paths
    try:
        macf_package = get_macf_package_path()
    except (OSError, IOError) as e:
        print(f"⚠️ MACF: macf package path detection failed: {e}", file=sys.stderr)
        macf_package = None

    try:
        maceff_root = find_maceff_root()
        framework_dir = maceff_root / "framework" if maceff_root else None
    except (OSError, IOError) as e:
        print(f"⚠️ MACF: maceff root detection failed: {e}", file=sys.stderr)
        framework_dir = None

    # Gather all data
    data = {
        "identity": {
            "agent_id": agent_identity
        },
        "versions": {
            "macf": _ver,
            "claude_code": get_claude_code_version() or "(unavailable)",
            "model": detect_model(),
            "context_window": f"{get_total_context():,}",
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
        "cc_internal": {
            "cc_binary": _detect_cc_binary(),
            "cc_project_dir": resolve_path(cc_project_dir),
            "cc_tasks_dir": resolve_path(cc_tasks_dir)
        },
        "framework": {
            "macf_package": resolve_path(macf_package),
            "framework_dir": resolve_path(framework_dir)
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

    # Supervision diagnostics. Every fact below was derivable before this
    # existed, and every one of them was derived by hand -- repeatedly, in one
    # evening, by the person who had just written the harness -- from $TMUX, ps
    # ancestry walks and greps of the supervisor registry. Two came out wrong.
    try:
        from macf.utils.supervision import diagnose
        data["supervision"] = diagnose()
    except Exception as e:
        # Never let a diagnostic break the command it is reporting on.
        data["supervision"] = {"error": f"{type(e).__name__}: {e}"}

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

        print("Supervision")
        sup = data.get("supervision") or {}
        if "error" in sup:
            print(f"  (unavailable: {sup['error']})")
        else:
            from macf.utils.supervision import format_diagnosis
            print(format_diagnosis(sup))
        print()

        print("Versions")
        print(f"  MACF:         {data['versions']['macf']}")
        print(f"  Claude Code:  {data['versions']['claude_code']}")
        print(f"  Model:        {data['versions']['model']}")
        print(f"  Context:      {data['versions']['context_window']} tokens")
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

        print("Claude Code Internal")
        print(f"  CC Binary:      {data['cc_internal']['cc_binary']}")
        print(f"  CC Project Dir: {data['cc_internal']['cc_project_dir']}")
        print(f"  CC Tasks Dir:   {data['cc_internal']['cc_tasks_dir']}")
        print()

        print("Framework")
        print(f"  MACF Package:   {data['framework']['macf_package']}")
        print(f"  Framework Dir:  {data['framework']['framework_dir']}")
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


def cmd_env_set_term_title(args: argparse.Namespace) -> int:
    """Set the terminal window title (default: agent calling card).

    Writes an OSC 2 escape to stderr. No-op (with informational stderr
    note) when stdout is not a TTY or $TERM is unset/dumb.
    """
    from .utils.identity import get_agent_identity
    from .utils.terminal import set_terminal_title

    title = args.title if args.title else get_agent_identity()
    ok = set_terminal_title(title)
    if not ok:
        print(
            "ℹ️ MACF: terminal title not set (stdout is not a TTY, or $TERM unsupported)",
            file=sys.stderr,
        )
    return 0


def cmd_time(_: argparse.Namespace) -> int:
    current_time = _now_iso()
    print(current_time)

    # Show gap since most recent CCP.
    #
    # This goes to stderr, not stdout. `time` is documented as emitting a single
    # ISO-8601 timestamp, which makes it the kind of command other code parses;
    # a second line on stdout breaks every such consumer, and breaks them
    # quietly, because the first line still parses for anything reading only one.
    # Human-facing annotation belongs on stderr whenever stdout has a machine
    # consumer, and an interactive caller still sees both streams.
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
                print(f"Last CCP: {latest_ccp.name} ({hours}h {minutes}m ago)",
                      file=sys.stderr)
    except OSError as e:
        print(f"⚠️ MACF: CCP lookup failed: {e}", file=sys.stderr)

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

        # 11 lifecycle hooks with their script names. SubagentStart joins
        # SubagentStop as the boot-boundary marker, used by MACF to bridge
        # the parent's tool_use_id to the subagent's agent_id (CC doesn't
        # supply a direct join key between the two surfaces).
        hook_configs = [
            ("SessionStart", "session_start.py"),
            ("UserPromptSubmit", "user_prompt_submit.py"),
            ("Stop", "stop.py"),
            ("SubagentStart", "subagent_start.py"),
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

        # Merge permissions from template (allow/ask/deny lists are additively merged,
        # deduplicated per-bucket — user's existing entries are preserved)
        try:
            maceff_root = find_maceff_root()
            template_path = maceff_root / "framework" / "templates" / "settings.permissions.json"
            if template_path.exists():
                with open(template_path) as f:
                    perm_template = json.load(f)
                if "permissions" in perm_template:
                    if "permissions" not in settings:
                        settings["permissions"] = {}
                    for bucket in ("allow", "ask", "deny"):
                        if bucket in perm_template["permissions"]:
                            if bucket not in settings["permissions"]:
                                settings["permissions"][bucket] = []
                            for perm in perm_template["permissions"][bucket]:
                                if perm not in settings["permissions"][bucket]:
                                    settings["permissions"][bucket].append(perm)
        except Exception as e:
            print(f"   Warning: Could not merge permissions template: {e}", file=sys.stderr)

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


def _check_hooks_in_settings(settings_path: Path) -> bool:
    """Check if hooks section exists in a settings file."""
    try:
        if not settings_path.exists():
            return False
        with open(settings_path) as f:
            settings = json.load(f)
        return bool(settings.get("hooks"))
    except (OSError, IOError, json.JSONDecodeError) as e:
        print(f"⚠️ MACF: hooks settings check failed: {e}", file=sys.stderr)
        return False


def _count_hook_events_in_settings(settings_path: Path) -> int:
    """Count distinct hook events bound in a settings file. Returns 0 on any failure."""
    try:
        if not settings_path.exists():
            return 0
        with open(settings_path) as f:
            settings = json.load(f)
        hooks = settings.get("hooks") or {}
        return len(hooks) if isinstance(hooks, dict) else 0
    except (OSError, IOError, json.JSONDecodeError) as e:
        print(f"⚠️ MACF: hooks count check failed: {e}", file=sys.stderr)
        return 0


def _clear_hooks_from_settings(settings_path: Path) -> bool:
    """Remove hooks section from a settings file to prevent duplicate execution."""
    try:
        if not settings_path.exists():
            return True

        with open(settings_path) as f:
            settings = json.load(f)

        if "hooks" not in settings:
            return True

        del settings["hooks"]

        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)

        return True
    except Exception as e:
        print(f"Warning: Could not clear hooks from {settings_path}: {e}")
        return False


def _hooks_to_install_list():
    """Canonical (script_name, handler_module) pairs for MacEff hooks.

    Single source of truth for `cmd_hook_install` (which writes the
    symlinks + settings entries) and `cmd_framework_install` (which
    verifies the post-install bound count). Adding a hook here is the
    only edit needed for both install + self-validation to scale.
    """
    return [
        ("session_start.py", "handle_session_start"),
        ("user_prompt_submit.py", "handle_user_prompt_submit"),
        ("stop.py", "handle_stop"),
        ("subagent_start.py", "handle_subagent_start"),
        ("subagent_stop.py", "handle_subagent_stop"),
        ("pre_tool_use.py", "handle_pre_tool_use"),
        ("post_tool_use.py", "handle_post_tool_use"),
        ("session_end.py", "handle_session_end"),
        ("pre_compact.py", "handle_pre_compact"),
        ("permission_request.py", "handle_permission_request"),
        ("notification.py", "handle_notification"),
    ]


def cmd_hook_install(args: argparse.Namespace) -> int:
    """Install consciousness hooks with local/global mode selection.

    IDEMPOTENT: Always clears hooks from the OTHER location to prevent duplicate execution.
    If switching modes, prompts for confirmation.
    """
    try:
        # Container detection (FP#27 fix - check /.dockerenv directly)
        in_container = Path("/.dockerenv").exists()

        # Define both settings paths
        global_settings = Path.home() / ".claude" / "settings.json"
        local_settings = Path.cwd() / ".claude" / "settings.local.json"

        # Check current state
        has_global_hooks = _check_hooks_in_settings(global_settings)
        has_local_hooks = _check_hooks_in_settings(local_settings)

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

        # Check if switching modes (hooks exist in opposite location)
        switching_to_global = (mode == 'global' and has_local_hooks)
        switching_to_local = (mode == 'local' and has_global_hooks)

        if switching_to_global or switching_to_local:
            other_loc = "local (.claude/settings.local.json)" if switching_to_global else "global (~/.claude/settings.json)"
            print(f"\n⚠️  Hooks currently exist in {other_loc}")
            print(f"   Installing to {'global' if mode == 'global' else 'local'} will REMOVE hooks from {other_loc}")
            confirm = input("   Continue? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("❌ Cancelled")
                return 1

        # Clear hooks from the OTHER location (always, to ensure no duplicates)
        if mode == 'local':
            if has_global_hooks:
                print(f"   Clearing hooks from global settings...")
                _clear_hooks_from_settings(global_settings)
        else:  # global
            if has_local_hooks:
                print(f"   Clearing hooks from local settings...")
                _clear_hooks_from_settings(local_settings)

        # Set paths based on mode and environment.
        #
        # Hook commands MUST resolve to absolute paths in settings (cversek/MacEff#89).
        # A bare `cd` in the agent's persistent Bash shell shifts CWD; if the
        # hook command is relative (e.g. "python .claude/hooks/X.py"), every
        # subsequent PreToolUse lookup resolves against the shifted CWD,
        # fails with ENOENT, and blocks ALL tool calls including the
        # de-escalation paths needed to recover. Only an external session
        # restart unblocks the agent. Absolute paths sidestep this entirely.
        if mode == 'global':
            hooks_dir = Path.home() / ".claude" / "hooks"
            settings_file = Path.home() / ".claude" / "settings.json"
            if in_container:
                # Container: absolute venv Python + absolute hook paths (FP#27)
                hooks_prefix = f"/opt/maceff-venv/bin/python {Path.home()}/.claude/hooks"
            else:
                # Host global: write the absolute home path. ~ expansion is
                # shell-dependent and CC's hook exec model isn't documented to
                # guarantee it; absolute removes the assumption.
                hooks_prefix = f"python {Path.home()}/.claude/hooks"
        else:
            # Local mode (host only - container always uses global).
            # Resolve to canonical absolute path so symlinked project trees,
            # relative invocations, and CWD-shifts all hit the same hooks dir.
            hooks_dir = Path.cwd() / ".claude" / "hooks"
            settings_file = Path.cwd() / ".claude" / "settings.local.json"
            hooks_prefix = f"python {hooks_dir.resolve()}"

        # Create hooks directory
        hooks_dir.mkdir(parents=True, exist_ok=True)

        # 11 lifecycle hooks with their handler module names.
        # subagent_start.py was added alongside subagent_stop.py to act
        # as the parent→child join-key bridge for delegation events
        # (CC's SubagentStop hook input carries agent_id but not the
        # parent's tool_use_id; SubagentStart sees agent_id at boot
        # time and emits the bridging deleg_drv_subagent_booted event).
        hooks_to_install = _hooks_to_install_list()

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
            print(f"\n✅ All {len(hooks_to_install)} hooks installed successfully!")
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
        # Determine what to install
        hooks_only = getattr(args, 'hooks_only', False)
        skip_hooks = getattr(args, 'skip_hooks', False)

        # Find framework root using standard path resolution
        maceff_root = find_maceff_root()
        framework_root = maceff_root / "framework"
        if not framework_root.exists():
            print(f"Error: Framework directory not found at {framework_root}")
            print(f"   MacEff root resolved to: {maceff_root}")
            print(f"   Fix: Set MACEFF_ROOT_DIR to your MacEff installation")
            return 1

        claude_dir = Path.cwd() / ".claude"
        commands_dir = claude_dir / "commands"
        skills_dir = claude_dir / "skills"

        installed_count = {"hooks": 0, "commands": 0, "skills": 0}

        # Install hooks (unless skip_hooks or already done via hooks_only)
        # The framework install hands cmd_hook_install a local mode choice, which
        # writes the settings file at <CWD>/.claude/settings.local.json. We verify
        # the post-install state below rather than trusting the return code alone
        # — the migration path clears global hooks BEFORE writing local, so a
        # silent write failure would leave the agent with no hooks anywhere.
        in_container = Path("/.dockerenv").exists()
        if in_container:
            expected_settings = Path.home() / ".claude" / "settings.json"
        else:
            expected_settings = Path.cwd() / ".claude" / "settings.local.json"

        if not skip_hooks:
            print("\n📦 Installing hooks...")
            hooks_args = argparse.Namespace(local_install=True, global_install=False)
            hook_result = cmd_hook_install(hooks_args)
            if hook_result != 0:
                print(f"\n❌ Hook installation failed (exit {hook_result}). Aborting framework install.")
                print(f"   Expected settings file: {expected_settings}")
                return 1
            actual_hook_count = _count_hook_events_in_settings(expected_settings)
            expected_hook_count = len(_hooks_to_install_list())
            if actual_hook_count != expected_hook_count:
                print(f"\n❌ Hook installation reported success but settings file has {actual_hook_count}/{expected_hook_count} hook events bound.")
                print(f"   Expected settings file: {expected_settings}")
                print(f"   This can happen after a global→local migration if the local write silently dropped the hooks block.")
                print(f"   Recovery: re-run with `macf_tools framework install --hooks-only` from the same directory.")
                return 1
            installed_count["hooks"] = actual_hook_count

        if hooks_only:
            print(f"\n✅ Hooks-only installation complete")
            print(f"ℹ️  Commands and skills NOT installed; rerun without `--hooks-only` (or use `--skip-hooks` if hooks are already in place) to install those.")
            return 0

        # An install that reports success while linking nothing is
        # indistinguishable from one that worked, and the agent only finds out
        # much later when a command it was told it had turns out to be missing.
        # Both an absent source tree and a present-but-empty one are recorded
        # here and made fatal at the summary.
        problems: list[str] = []

        def prune_orphaned_links(target_dir, owned_prefixes):
            """Remove framework-owned symlinks whose target no longer exists.

            Installing relinks what the source tree still has; nothing removed
            links to what it no longer has. So every framework rename or
            retirement left an orphan behind permanently, and Claude Code drops
            broken symlinks from autocomplete silently — the only symptom is a
            command quietly missing, with nothing pointing at the install as
            the cause.

            Deliberately narrow, because agents keep their own commands and
            skills in these same directories and a prune that ate one would be
            strictly worse than the orphan it fixes. Two guards do that work:
            the entry must fail to resolve (which already excludes every real
            file and every link that still points somewhere), and its name must
            be one the framework owns. The is_symlink() check is intent rather
            than protection — it is redundant with the resolve check, and
            removing it does not change behaviour.
            """
            removed = []
            if not target_dir.is_dir():
                return removed
            for entry in sorted(target_dir.iterdir()):
                if not entry.is_symlink():
                    continue
                # exists() follows the link, so this is False exactly when the
                # target is gone.
                if entry.exists():
                    continue
                if not any(entry.name.startswith(p) for p in owned_prefixes):
                    continue
                entry.unlink()
                removed.append(entry.name)
            return removed

        # Install commands (symlink maceff*/ namespace directories)
        print("\n📦 Installing commands...")
        commands_src = framework_root / "commands"
        linked_commands = 0
        if commands_src.exists():
            commands_dir.mkdir(parents=True, exist_ok=True)
            for cmd_ns in commands_src.glob("maceff*/"):
                if cmd_ns.is_dir():
                    target = commands_dir / cmd_ns.name
                    if target.exists() or target.is_symlink():
                        if target.is_symlink():
                            target.unlink()
                        else:
                            import shutil
                            shutil.rmtree(target)
                    target.symlink_to(cmd_ns)
                    linked_commands += 1
                    # Count .md files in namespace for reporting
                    md_count = sum(1 for _ in cmd_ns.rglob("*.md"))
                    installed_count["commands"] += md_count
                    print(f"   ✓ {cmd_ns.name}/ ({md_count} commands)")
            for orphan in prune_orphaned_links(commands_dir, ("maceff",)):
                print(f"   🧹 removed orphaned link {orphan} (target no longer in framework)")
            if linked_commands == 0:
                problems.append(
                    f"commands: {commands_src} exists but contains no maceff*/ namespace directories"
                )
                print(f"   ❌ no maceff*/ namespaces found in {commands_src}", file=sys.stderr)
        else:
            problems.append(f"commands: source tree missing at {commands_src}")
            print(f"   ❌ no commands directory at {commands_src}", file=sys.stderr)

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
            for orphan in prune_orphaned_links(skills_dir, ("maceff-",)):
                print(f"   🧹 removed orphaned link {orphan} (target no longer in framework)")
            if installed_count["skills"] == 0:
                problems.append(
                    f"skills: {skills_src} exists but contains no maceff-*/ directories"
                )
                print(f"   ❌ no maceff-*/ skills found in {skills_src}", file=sys.stderr)
        else:
            problems.append(f"skills: source tree missing at {skills_src}")
            print(f"   ❌ no skills directory at {skills_src}", file=sys.stderr)

        # Summary
        if problems:
            print(f"\n❌ Framework installation INCOMPLETE — nothing was installed for:", file=sys.stderr)
            for problem in problems:
                print(f"   • {problem}", file=sys.stderr)
            print(f"   Framework root resolved to: {framework_root}", file=sys.stderr)
            print(f"   Hooks: {installed_count['hooks']}   Commands: {installed_count['commands']}   Skills: {installed_count['skills']}", file=sys.stderr)
            print(f"   This usually means the framework tree was never deployed to this", file=sys.stderr)
            print(f"   root — on a container, check that framework/ is mounted and that", file=sys.stderr)
            print(f"   the sync step ran ('make framework-upgrade' on the host).", file=sys.stderr)
            print(f"   Use --hooks-only if installing hooks alone is what you intended.", file=sys.stderr)
            return 1

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


def cmd_config_show(args: argparse.Namespace) -> int:
    """Show the resolved value + source for every unified-config setting.

    Iterates ``macf.config.RESOLVED_SETTINGS`` and prints each setting's
    name, current resolved value, and source label (``env`` / ``config`` /
    ``default``). Output is column-aligned for fast scanning; ``--json``
    emits the same data as a JSON array for programmatic consumers.

    Closes the visible portion of cversek/MacEff#96 Phases 2-4.
    """
    from macf.config import resolve_setting, RESOLVED_SETTINGS
    rows = []
    for spec in RESOLVED_SETTINGS:
        value, source = resolve_setting(
            spec["env_var"],
            spec["config_path"],
            spec["default"],
            coerce=spec.get("coerce"),
        )
        rows.append({
            "name": spec["name"],
            "env_var": spec["env_var"],
            "value": value,
            "source": source,
            "description": spec.get("description", ""),
        })
    if getattr(args, "json_output", False):
        print(json.dumps(rows, indent=2, default=str))
        return 0
    name_w = max(len(r["name"]) for r in rows)
    val_w = max(len(str(r["value"])) for r in rows)
    src_w = max(len(r["source"]) for r in rows)
    header = f"  {'SETTING':<{name_w}}  {'VALUE':<{val_w}}  {'SOURCE':<{src_w}}  ENV_VAR"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in rows:
        print(
            f"  {r['name']:<{name_w}}  {str(r['value']):<{val_w}}  "
            f"{r['source']:<{src_w}}  {r['env_var']}"
        )
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    """Show current token usage and CL (Context Left) level."""
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
        cl_level = token_info['cl_level']
        source = token_info['source']
        total = get_total_context()

        print(f"Token Usage: {tokens_used:,} / {total:,} ({percentage_used:.1f}%)")
        print(f"Remaining: {tokens_remaining:,} tokens")
        print(f"CL Level: {cl_level} (Context Left)")
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
            cl=data["cl"]
        )

        print(statusline)
        return 0

    except Exception as e:
        print(f"Error generating statusline: {e}", file=sys.stderr)
        return 1


def _harness_params(args: argparse.Namespace):
    from dataclasses import replace
    from .utils.harness import default_params
    p = default_params(agent=getattr(args, "agent", None), home=getattr(args, "home", None))
    # Channels are declared, never inferred. They are the agent's inbound link
    # when nobody is attached, and a default would be a guess about reachability.
    channels = tuple(getattr(args, "channel", None) or ())
    prefix = getattr(args, "shell_prefix", None)
    if channels or prefix:
        p = replace(p, channels=channels, shell_prefix=prefix)
    # Fill anything not given from what the last install recorded. Without this
    # a flagless `install --check` renders different artifacts and reports drift
    # that is not there — and acting on that report with --force would strip the
    # channel silently.
    from .utils.harness import load_settings
    return load_settings(p)


def cmd_harness_generate(args: argparse.Namespace) -> int:
    """Render harness artifacts to stdout without touching anything.

    Rendering and installing are separate verbs so the output can be reviewed,
    diffed against a live unit, or scanned for identifiers before it lands
    anywhere — the hand-edited predecessor drifted precisely because there was
    nothing to diff against.
    """
    from .utils.harness import (
        render_child,
        render_launch_functions,
        render_start,
        render_tmux_conf,
        render_unit,
        render_watchdog,
    )

    try:
        p = _harness_params(args)
        attach = not getattr(args, "no_proxy", False)
        what = getattr(args, "what", "unit")
        if what == "watchdog":
            svc, tmr = render_watchdog(p)
            print(f"# ===== cc-harness-{p.agent}-watch.service =====")
            print(svc, end="")
            print(f"\n# ===== cc-harness-{p.agent}-watch.timer =====")
            print(tmr, end="")
            return 0
        if what in ("unit", "all"):
            print(render_unit(p, attach_proxy=attach), end="")
        if what in ("start", "all"):
            if what == "all":
                print(f"\n# ===== {p.start} =====")
            print(render_start(p, attach_proxy=attach), end="")
        if what in ("child", "all"):
            if what == "all":
                print(f"\n# ===== {p.child_path} =====")
            print(render_child(p), end="")
        if what in ("functions", "all"):
            if what == "all":
                print(f"\n# ===== {p.functions} =====")
            print(render_launch_functions(p), end="")
        if what in ("tmux", "all"):
            if what == "all":
                print(f"\n# ===== {p.home}/.tmux-{p.agent}.conf =====")
            print(render_tmux_conf(p), end="")
        return 0
    except Exception as e:
        print(f"Error rendering harness: {e}", file=sys.stderr)
        return 1


def cmd_harness_install(args: argparse.Namespace) -> int:
    """Write the rendered artifacts into place.

    Refuses to clobber a unit that differs unless --force, and --check reports
    drift without writing. A live unit that has diverged from what the generator
    produces is the failure this command exists to make visible rather than
    silently overwrite.
    """
    from pathlib import Path
    import stat as _stat
    from .utils.harness import (
        render_child,
        render_launch_functions,
        render_start,
        render_tmux_conf,
        render_unit,
        save_settings,
    )

    try:
        p = _harness_params(args)
        attach = not getattr(args, "no_proxy", False)
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        targets = [
            (unit_dir / p.unit_name, render_unit(p, attach_proxy=attach), False),
            (Path(p.start), render_start(p, attach_proxy=attach), True),
            (Path(p.child_path), render_child(p), True),
            (Path(p.functions), render_launch_functions(p), False),
            (p.home / f".tmux-{p.agent}.conf", render_tmux_conf(p), False),
        ]
        if getattr(args, "watchdog", False):
            svc, tmr = render_watchdog(p)
            targets += [
                (unit_dir / f"cc-harness-{p.agent}-watch.service", svc, False),
                (unit_dir / f"cc-harness-{p.agent}-watch.timer", tmr, False),
            ]

        if getattr(args, "check", False):
            drift = 0
            for path, content, _ in targets:
                if not path.exists():
                    print(f"   ABSENT   {path}")
                    drift += 1
                elif path.read_text() != content:
                    print(f"   DRIFTED  {path}")
                    drift += 1
                else:
                    print(f"   ok       {path}")
            if drift:
                print(f"\n{drift} artifact(s) differ from what would be rendered.", file=sys.stderr)
                return 1
            print("\nAll harness artifacts match the generator output.")
            return 0

        for path, content, executable in targets:
            if path.exists() and path.read_text() != content and not getattr(args, "force", False):
                print(f"Error: {path} exists and differs from the rendered output.", file=sys.stderr)
                print("       Review with `macf_tools harness install --check`, then re-run with --force.", file=sys.stderr)
                return 1

        for path, content, executable in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            if executable:
                path.chmod(path.stat().st_mode | _stat.S_IXUSR)
            print(f"   ✓ {path}")

        save_settings(p)
        print(f"   ✓ {p.settings_path}")
        print(f"\n✅ Harness installed for agent '{p.agent}'")
        print(f"   systemctl --user daemon-reload && systemctl --user enable --now {p.unit_name}")
        # "=" is not decoration: tmux matches targets by PREFIX, so advice
        # without it teaches the loose form that caused GH #209.
        print(f"   attach:  tmux attach -t ={p.agent}   (or: maceff_{p.prefix}_harness_launch)")
        print(f"   status:  macf_tools harness status --agent {p.agent}")
        print(f"   stop:    systemctl --user stop {p.unit_name}   (stops the supervisor, not the child)")
        return 0
    except Exception as e:
        print(f"Error installing harness: {e}", file=sys.stderr)
        return 1


def cmd_harness_attach(args: argparse.Namespace) -> int:
    """Attach this terminal to the agent's supervised session.

    Exists so that no remote shell has to hardcode a session name. A helper on
    another machine held the OLD name after the session was renamed, and broke
    with "no sessions" -- a fourth hand-maintained copy of harness knowledge, on
    a host the generator cannot reach. `ssh host -t macf_tools harness attach`
    resolves the name where the name is defined, so a rename cannot strand it.
    """
    from .utils.harness import resolve_agent
    from .utils.identity import calling_card_from_identifier

    try:
        agent, source = resolve_agent(getattr(args, "agent", None))
        if source == "ambiguous":
            print("Several harnesses are installed here; name one with --agent:",
                  file=sys.stderr)
            for a in agent:
                print(f"   {a}  ({calling_card_from_identifier(a)})", file=sys.stderr)
            return 1

        # "=" forces an exact match; tmux resolves targets by prefix, so a bare
        # name would happily attach to "<agent>-stale-ssh".
        target = f"={agent}"
        if subprocess.run(["tmux", "has-session", "-t", target],
                          capture_output=True).returncode != 0:
            print(f"No tmux session '{agent}' on this host.", file=sys.stderr)
            print(f"   start it:  {'maceff_' + agent.rpartition('_')[0].lower() + '_harness_launch'}",
                  file=sys.stderr)
            print(f"   or:        systemctl --user start cc-harness-{agent}.service",
                  file=sys.stderr)
            return 1

        # -CC hands the session to iTerm2 as native windows. It matters more
        # than it looks: the client owns the alternate screen, so under a plain
        # attach there is no tmux-level scrollback at all -- control mode is
        # what restores native scrollback, selection and find on macOS.
        cmd = ["tmux"]
        if getattr(args, "control", False):
            cmd.append("-CC")
        cmd += ["attach", "-t", target]
        # -d evicts other clients: two clients of different geometries is the
        # cause of the fragmented redraws. Read-only observers skip it.
        cmd.append("-r" if getattr(args, "read_only", False) else "-d")
        os.execvp("tmux", cmd)
    except Exception as e:
        print(f"Error attaching to harness: {e}", file=sys.stderr)
        return 1


def cmd_harness_status(args: argparse.Namespace) -> int:
    """Report unit state, session presence and proxy attachment.

    Every negative line names the agent it checked, and a defaulted name says
    so. This command once printed a confident ABSENT for a harness that was
    running under a different name, and came within one step of telling the
    operator his harness did not exist — an instrument answering about
    something it never looked at.
    """
    from pathlib import Path
    from .utils.harness import resolve_agent
    from .utils.identity import calling_card_from_identifier

    try:
        agent, source = resolve_agent(getattr(args, "agent", None))
        if source == "ambiguous":
            print("agent:   AMBIGUOUS — several harnesses are installed here:")
            for a in agent:
                print(f"           {a}  ({calling_card_from_identifier(a)})")
            print("\nPick one with --agent; this command will not choose for you.",
                  file=sys.stderr)
            return 1

        p = _harness_params(args)
        unit_path = Path.home() / ".config" / "systemd" / "user" / p.unit_name
        card = calling_card_from_identifier(p.agent)
        if source == "default":
            # The line that was missing. A default reported as a resolution is
            # how "no harness for the name I guessed" reads as "no harness".
            print(f"agent:   {p.agent}  (DEFAULT — not resolved from the "
                  f"environment, config or any installed unit)")
        else:
            print(f"agent:   {p.agent}  ({card}, via {source})")
        print(f"unit:    {unit_path} "
              f"{'(present)' if unit_path.exists() else f'(ABSENT for agent {p.agent})'}")

        active = subprocess.run(["systemctl", "--user", "is-active", p.unit_name],
                                capture_output=True, text=True).stdout.strip()
        print(f"active:  {active or 'unknown'}")

        # "=" forces an EXACT session match. Without it tmux resolves a target
        # by prefix, so `-t thm` happily matches a session called
        # "thm-stale-ssh" -- which is precisely the name someone gives the
        # imposter while moving it out of the way, so the workaround for the
        # name collision silently did not resolve the collision.
        has_session = subprocess.run(["tmux", "has-session", "-t", f"={p.agent}"],
                                     capture_output=True).returncode == 0
        print(f"session: {'up' if has_session else f'absent for {p.agent}'} "
              f"(tmux -t ={p.agent})")

        # Presence is not ownership. A session under this name may be anyone's
        # — that is how the harness stayed down for days while every surface
        # said "session: up".
        if has_session:
            sup = subprocess.run(
                ["bash", "-c",
                 f'for f in {p.registry}/*.json; do [ -e "$f" ] || continue; '
                 f'grep -q \'"name": "{p.agent}"\' "$f" || continue; '
                 f'grep -q \'"status": "running"\' "$f" || continue; '
                 f'pid=${{f##*/}}; pid=${{pid%.json}}; kill -0 "$pid" 2>/dev/null || continue; '
                 f'ps -o args= -p "$pid" | grep -q "macf\\.supervisor" || continue; '
                 f'echo "$pid"; break; done'],
                capture_output=True, text=True).stdout.strip()
            print(f"owner:   {'macf supervisor pid ' + sup if sup else 'NOT this harness — the name is held by something else'}")

        probe = subprocess.run(
            ["curl", "-s", "--max-time", "2", "-o", "/dev/null",
             f"http://127.0.0.1:{p.proxy_port}/"], capture_output=True).returncode == 0
        # Reported the same way the unit decides it, so this cannot claim an
        # attachment the unit would not actually make.
        print(f"proxy:   {'answering on ' + str(p.proxy_port) + ' — harness would attach' if probe else 'not answering — harness would run direct'}")
        return 0
    except Exception as e:
        print(f"Error reading harness status: {e}", file=sys.stderr)
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


def cmd_agent_sleep(args: argparse.Namespace) -> int:
    """Emergency sleep with fibonacci backoff and channel notification."""
    import time
    from .agent_events_log import append_event
    from .utils.cycles import set_auto_mode, get_current_session_id

    session_id = get_current_session_id()
    interval = args.start
    prev_interval = args.start
    attempt = 0

    print(f"🛑 MACF Emergency Sleep")
    print(f"   Interval: {args.interval} (start: {args.start}s)")
    print(f"   Max attempts: {args.max_attempts}")
    print(f"   Notify: {args.notify}")

    while attempt < args.max_attempts:
        attempt += 1
        elapsed = sum(range(attempt)) * args.start if args.interval == "fixed" else 0  # approximate

        # Try MANUAL_MODE switch
        print(f"\n⏰ Wakeup #{attempt} — attempting MANUAL_MODE switch...")
        try:
            success, msg = set_auto_mode(enabled=False, session_id=session_id)
            if success:
                print(f"✅ MANUAL_MODE restored! Sleep ended after {attempt} attempts.")
                append_event("agent_sleep_recovery", {
                    "attempt": attempt, "session_id": session_id, "result": "recovered"
                })
                return 0
        except Exception as e:
            print(f"   ❌ MANUAL_MODE switch failed: {e}")

        # Log sleep cycle event
        append_event("agent_sleep_cycle", {
            "attempt": attempt, "interval": args.interval,
            "sleep_seconds": interval, "session_id": session_id,
            "manual_mode_result": "failed", "notification_sent": args.notify,
        })

        # Notify via channels
        if args.notify:
            try:
                from macf.channels.telegram import send_telegram_notification
                send_telegram_notification(
                    f"Attempt #{attempt}, sleeping {interval}s. Awaiting operator.",
                    prefix="🛑 MACF Emergency Sleep"
                )
                print(f"   📨 Notification sent")
            except Exception as e:
                print(f"   ⚠️  Notification failed: {e}")

        # Sleep
        print(f"   💤 Sleeping {interval}s...")
        time.sleep(interval)

        # Fibonacci backoff
        if args.interval == "fibonacci":
            new_interval = interval + prev_interval
            prev_interval = interval
            interval = new_interval

    print(f"\n❌ Max attempts ({args.max_attempts}) reached. Giving up.")
    append_event("agent_sleep_exhausted", {
        "attempts": args.max_attempts, "session_id": session_id,
    })
    return 1


def _editable_source_suffix() -> str:
    """Describe the live source checkout when running from an editable install.

    A bare dev version string says nothing about *which* checkout is running.
    Dogfooding a feature branch or a worktree, `macf_tools --version` reported
    the same `0.5.1.dev0` whether the code under it was main, a branch, or a
    dirty tree — so "is my fix actually loaded?" could not be answered from the
    tool itself.

    Returns:
        `` (empty) for a normal wheel install, or e.g.
        `` (main @ 9dbeab3, dirty)`` when the package resolves to a git
        checkout.
    """
    import subprocess as _subprocess
    try:
        pkg_root = Path(__file__).resolve().parent
        r = _subprocess.run(
            ["git", "-C", str(pkg_root), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return ""  # installed from a wheel, not a checkout
        repo = r.stdout.strip()

        def _git(*a):
            out = _subprocess.run(["git", "-C", repo, *a],
                                  capture_output=True, text=True, timeout=5)
            return out.stdout.strip() if out.returncode == 0 else ""

        branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "?"
        commit = _git("rev-parse", "--short", "HEAD") or "?"
        dirty = ", dirty" if _git("status", "--porcelain") else ""
        return f" ({branch} @ {commit}{dirty})"
    except (FileNotFoundError, _subprocess.TimeoutExpired, OSError):
        # No git, or it hung: the version string is still useful without this.
        return ""


def _ensure_agent_uuid(
    pa_home: Path,
    *,
    assume_yes: bool = False,
    mint_fresh: bool = False,
) -> None:
    """Establish the agent's identity file at ``pa_home`` without ever
    silently changing who the agent is.

    Without an id file the resolver returns ``unknown``, so a freshly
    provisioned host displays ``Name@unknown`` and breadcrumbs lose their UUID
    half (#131). The naive fix — mint whenever *this* file is missing — checks
    the wrong thing: the resolver prefers the per-project file over the
    host-global one, so minting into an agent home while a global identity is
    already resolving changes the effective identity while overwriting nothing
    (#180). Nothing on disk is damaged and the calling card changes anyway.

    The per-project file is the canonical mechanism: one ``~`` cannot serve N
    agents on a shared host or container, while a per-agent-home file can. So
    the response to "resolves globally, project file absent" is to *carry the
    existing value across*, not to skip the write and not to mint a stranger:

        already in this file      → report, leave untouched
        resolves from elsewhere   → warn, offer to transfer that exact value
        nothing resolves anywhere → offer a fresh value, previewed, re-rollable

    The first six characters become the agent's public calling card, so a
    minted value is shown before it is accepted and can be re-rolled.

    Non-interactive (``-y``, used by container start.py and the test suite)
    takes the safe branch at every fork: transfer when an identity resolves,
    mint only on genuine absence. ``mint_fresh`` is the explicit opt-in for the
    rare deliberate case of a *new* identity in a home that would otherwise
    inherit one.
    """
    import uuid as _uuid
    from .utils.identity import _resolve_uuid_source

    uuid_file = pa_home / '.maceff_primary_agent.id'
    target_scope = 'project' if pa_home != Path.home() else 'global'

    def _write(value: str, verb: str) -> None:
        try:
            uuid_file.write_text(value + "\n")
            uuid_file.chmod(0o600)
            print(f"\n🆔 {verb} agent UUID ({target_scope}): {value[:6]} → {uuid_file}")
        except OSError as e:
            print(f"⚠️  Could not write agent UUID at {uuid_file}: {e}", file=sys.stderr)

    # Already established here — the only fully silent branch.
    try:
        if uuid_file.exists() and uuid_file.read_text().strip():
            print(f"\n🆔 Agent UUID present ({target_scope}): {uuid_file}")
            return
    except OSError as e:
        print(f"⚠️  Could not read agent UUID at {uuid_file}: {e}", file=sys.stderr)
        return

    resolved, resolved_scope, resolved_source = _resolve_uuid_source()
    inherited = bool(resolved) and resolved_source != uuid_file

    if inherited and not mint_fresh:
        print(f"\n⚠️  This agent already has an identity that resolves from another scope:")
        print(f"      {resolved[:6]}  ({resolved_scope}) ← {resolved_source}")
        print(f"    Writing a different value to {uuid_file} would take precedence")
        print(f"    over it and change the agent's calling card.")
        if assume_yes:
            print("    Non-interactive: transferring the existing identity (use "
                  "--mint-fresh-id to mint a new one instead).")
            _write(resolved, "Transferred")
            return
        answer = input(f"\n  Transfer {resolved[:6]} into {uuid_file.name}? [Y/n]: ").strip().lower()
        if answer in ('', 'y', 'yes'):
            _write(resolved, "Transferred")
            return
        print("    Keeping the resolved identity; not writing a project file.")
        return

    # Genuine absence (or an explicit --mint-fresh-id): offer a value.
    while True:
        candidate = str(_uuid.uuid4())
        if assume_yes:
            _write(candidate, "Minted")
            return
        print(f"\n🆔 Proposed agent UUID: {candidate}")
        print(f"    Calling card would be: @{candidate[:6]}")
        answer = input("  [A]ccept / [r]egenerate / [s]kip: ").strip().lower()
        if answer in ('', 'a', 'accept', 'y', 'yes'):
            _write(candidate, "Minted")
            return
        if answer in ('s', 'skip', 'n', 'no'):
            print("    Skipped — the agent will resolve to @unknown until an id exists.")
            return
        # anything else re-rolls


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
            except (OSError, IOError) as e:
                print(f"⚠️ MACF: agent home detection failed: {e}", file=sys.stderr)
                pa_home = Path.cwd()

        claude_md_path = pa_home / "CLAUDE.md"

        # Determine preamble template path (portable)
        template_locations = []

        # 1. Environment variable (deployment-configurable)
        env_templates = os.getenv("MACEFF_TEMPLATES_DIR")
        if env_templates:
            template_locations.append(Path(env_templates) / "PA_PREAMBLE.md")

        # 2. MacEff installation root (via find_maceff_root - works in container and host)
        try:
            maceff_root = find_maceff_root()
            if maceff_root:
                template_locations.append(maceff_root / "framework" / "templates" / "PA_PREAMBLE.md")
        except (OSError, ImportError) as e:
            print(f"⚠️ MACF: could not locate maceff root for PA_PREAMBLE template: {e}", file=sys.stderr)

        # 3. Development mode (relative to current directory - fallback with warning)
        cwd_fallback = Path.cwd() / "templates" / "PA_PREAMBLE.md"
        template_locations.append(cwd_fallback)

        preamble_template_path = None
        for loc in template_locations:
            if loc.exists():
                preamble_template_path = loc
                break

        # Warn if using CWD fallback (likely unintended)
        if preamble_template_path == cwd_fallback:
            print(f"⚠️  Warning: Using CWD fallback for template: {cwd_fallback}", file=sys.stderr)
            print("   Consider setting MACEFF_TEMPLATES_DIR or MACEFF_ROOT_DIR", file=sys.stderr)

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
                action_desc = "Update PA Preamble in existing"
            else:
                # No boundary = first time, preserve all existing content
                user_content = existing_content.rstrip()
                action_desc = "⚠️  Add PA Preamble to existing"

            # Strip stale managed preamble blocks stranded in the user region.
            # A preamble installed before the boundary convention (or moved above
            # it) sits in what is otherwise treated as user content, so upgrades
            # left the old copy in place and appended the new one — injecting the
            # preamble twice, with the stale copy's superseded guidance still in
            # play (issue #153). The MACEFF_PA_PREAMBLE_vX.Y_START/_END sentinels
            # exist precisely to make managed blocks identifiable wherever they
            # sit; honor them, and leave genuine user content untouched.
            import re
            stale_versions = re.findall(
                r'<!--\s*MACEFF_PA_PREAMBLE_v([\d.]+)_START\s*-->', user_content)
            if stale_versions:
                user_content = re.sub(
                    r'<!--\s*MACEFF_PA_PREAMBLE_v[\d.]+_START\s*-->.*?'
                    r'<!--\s*MACEFF_PA_PREAMBLE_v[\d.]+_END\s*-->\s*',
                    '', user_content, flags=re.DOTALL).rstrip()
                print(f"🧹 Removing {len(stale_versions)} stale preamble block(s): "
                      f"{', '.join('v' + v for v in stale_versions)}")

            # Confirmation prompt for modifying existing file
            print(f"\n{action_desc} CLAUDE.md:")
            print(f"  📄 {claude_md_path}")
            if not getattr(args, 'yes', False):
                response = input("\nProceed? [y/N]: ").strip().lower()
                if response != 'y':
                    print("Aborted.")
                    return 0

            # Append: user + boundary + preamble
            new_content = user_content + "\n\n" + UPGRADE_BOUNDARY + "\n\n" + preamble_content
            claude_md_path.write_text(new_content)
            print(f"✅ PA Preamble appended successfully")
        else:
            # Create new CLAUDE.md with just the preamble (no boundary needed)
            print(f"\nCreate new CLAUDE.md with PA Preamble:")
            print(f"  📄 {claude_md_path}")
            if not getattr(args, 'yes', False):
                response = input("\nProceed? [y/N]: ").strip().lower()
                if response != 'y':
                    print("Aborted.")
                    return 0
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

        _ensure_agent_uuid(
            pa_home,
            assume_yes=getattr(args, 'yes', False),
            mint_fresh=getattr(args, 'mint_fresh_id', False),
        )

        print(f"\n📍 PA Home: {pa_home}")
        print(f"📍 Personal Policies: {personal_policies_dir}")
        print(f"\nAgent initialization complete!")

        return 0

    except Exception as e:
        print(f"Error during agent initialization: {e}")
        return 1


def cmd_agent_init_auth_token(args: argparse.Namespace) -> int:
    """Generate and install the AUTO_MODE auth token on a host.

    Writes a random ``auto_mode_auth_token`` into
    ``<agent_home>/.maceff/settings.json`` (preserving existing keys). This is
    the sanctioned bootstrap for bare-metal / migrated installs where
    ``docker/scripts/start.py`` never ran (cversek/MacEff#115). Refuses to
    overwrite an existing token unless ``--force``.
    """
    import secrets

    agent_home = find_agent_home()
    maceff_dir = agent_home / ".maceff"
    maceff_dir.mkdir(parents=True, exist_ok=True)
    settings_path = maceff_dir / "settings.json"

    settings = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"❌ Could not read existing {settings_path}: {e}")
            return 1

    if settings.get("auto_mode_auth_token") and not getattr(args, "force", False):
        print(f"⚠️ An auth token is already configured in {settings_path}.")
        print("   Re-run with --force to regenerate (invalidates the old one).")
        return 1

    token = secrets.token_hex(16)
    settings["auto_mode_auth_token"] = token
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    print(f"✅ AUTO_MODE auth token written to {settings_path}")
    print("   Activate with:")
    print(f"     macf_tools mode set AUTO_MODE --auth-token '{token}'")
    print(
        "\n   Security note: on a single-user host this token is a coordination /\n"
        "   accidental-self-auth gate, not a hard boundary — a same-user agent can\n"
        "   read or rewrite this file. True enforcement requires the external harness\n"
        "   classifier or a multi-user / file-permission setup."
    )
    return 0


def cmd_agent_set_github(args: argparse.Namespace) -> int:
    """Set per-project GitHub identity via GH_TOKEN in settings.local.json."""
    username = args.username

    # Extract token from gh auth keyring
    try:
        result = subprocess.run(
            ["gh", "auth", "token", "--user", username],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print(f"Error: could not get token for '{username}'")
            print(f"  gh auth token --user {username}")
            print(f"  stderr: {result.stderr.strip()}")
            print(f"\nMake sure '{username}' is logged in: gh auth login --with-token")
            return 1
        token = result.stdout.strip()
    except FileNotFoundError:
        print("Error: 'gh' CLI not found. Install GitHub CLI first.")
        return 1
    except subprocess.TimeoutExpired:
        print("Error: gh auth token timed out")
        return 1

    if not token:
        print(f"Error: empty token returned for '{username}'")
        return 1

    # Write to settings.local.json
    from .utils.claude_settings import _read_settings, _write_settings
    try:
        settings, settings_path = _read_settings()
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: could not read settings: {e}", file=sys.stderr)
        settings = {}
        from .utils.paths import find_project_root
        settings_path = find_project_root() / ".claude" / "settings.local.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)

    env = settings.setdefault("env", {})
    env["GH_TOKEN"] = token
    _write_settings(settings, settings_path)

    # Verify
    masked = token[:4] + "..." + token[-4:] if len(token) > 8 else "****"
    print(f"✅ GH_TOKEN set for '{username}' in {settings_path}")
    print(f"   Token: {masked}")
    print(f"\n   All CC tool processes (gh, git push) will use this identity.")
    print(f"   To change: macf_tools agent set-github <other-username>")
    print(f"   To remove: edit {settings_path} and delete env.GH_TOKEN")
    return 0


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
        # Parse optional parent from path-like input (e.g., "development/task_management")
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
    from .event_queries import get_active_policy_injections_from_events

    try:
        tier = getattr(args, 'tier', None)
        category = getattr(args, 'category', None)

        # Get active injections for 💉 marker
        active_injections = {inj["policy_name"] for inj in get_active_policy_injections_from_events()}

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
                inject_marker = "💉 " if p['name'] in active_injections else "  "
                print(f"{inject_marker}{p['name']}.md{tier_str}")

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


# -------- Policy Injection Commands --------

def cmd_policy_inject(args: argparse.Namespace) -> int:
    """Activate policy injection into PreToolUse hooks."""
    from .utils import find_policy_file
    from .agent_events_log import append_event
    from .event_queries import get_active_policy_injections_from_events

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
            print(f"❌ Policy not found: {args.policy_name}")
            print("\nUse 'macf_tools policy list' to see available policies")
            return 1

        # Emit activation event
        append_event("policy_injection_activated", {
            "policy_name": policy_name,
            "policy_path": str(policy_path)
        })

        # Show confirmation with active list
        active = get_active_policy_injections_from_events()
        active_names = [inj["policy_name"] for inj in active]

        print(f"✅ Injecting: {policy_name}.md")
        print(f"   Active injections: {active_names}")
        print("   Content will appear in PreToolUse hooks")
        return 0

    except Exception as e:
        print(f"❌ Error injecting policy: {e}")
        return 1


def cmd_policy_clear_injection(args: argparse.Namespace) -> int:
    """Clear a specific policy injection."""
    from .agent_events_log import append_event
    from .event_queries import get_active_policy_injections_from_events

    try:
        policy_name = args.policy_name
        # Strip path prefix if provided
        if '/' in policy_name:
            policy_name = policy_name.split('/')[-1]

        # Check if currently active
        active = get_active_policy_injections_from_events()
        active_names = [inj["policy_name"] for inj in active]

        if policy_name not in active_names:
            print(f"⚠️ Policy '{policy_name}' is not currently injected")
            if active_names:
                print(f"   Active injections: {active_names}")
            else:
                print("   No active injections")
            return 0

        # Emit clear event
        append_event("policy_injection_cleared", {
            "policy_name": policy_name
        })

        # Show remaining
        remaining = get_active_policy_injections_from_events()
        remaining_names = [inj["policy_name"] for inj in remaining]

        print(f"✅ Cleared injection: {policy_name}.md")
        if remaining_names:
            print(f"   Remaining: {remaining_names}")
        else:
            print("   No remaining injections")
        return 0

    except Exception as e:
        print(f"❌ Error clearing injection: {e}")
        return 1


def cmd_policy_clear_injections(args: argparse.Namespace) -> int:
    """Clear all policy injections."""
    from .agent_events_log import append_event
    from .event_queries import get_active_policy_injections_from_events

    try:
        # Get current count
        active = get_active_policy_injections_from_events()
        count = len(active)

        if count == 0:
            print("✅ No active injections to clear")
            return 0

        # Emit clear-all event
        append_event("policy_injections_cleared_all", {})

        print(f"✅ Cleared all policy injections (was {count} active)")
        return 0

    except Exception as e:
        print(f"❌ Error clearing injections: {e}")
        return 1


def cmd_policy_injections(args: argparse.Namespace) -> int:
    """List active policy injections."""
    from .event_queries import get_active_policy_injections_from_events

    try:
        active = get_active_policy_injections_from_events()

        if not active:
            print("No active policy injections")
            print("\nUse 'macf_tools policy inject <name>' to activate")
            return 0

        print("Active policy injections:")
        for inj in active:
            print(f"  💉 {inj['policy_name']} ({inj['policy_path']})")

        print(f"\nTotal: {len(active)} active")
        return 0

    except Exception as e:
        print(f"❌ Error listing injections: {e}")
        return 1


# -------- Mode Commands --------

def cmd_mode_set_work(args: argparse.Namespace) -> int:
    """Set the active work mode.

    SPRINT/PLAY_TIME aware:
    - If a SPRINT task is in scope, applies the SPRINT mode lock (warn-and-noop
      when transitioning to a different mode).
    - If a PLAY_TIME task is in scope, records the transition in its MTMD
      ``custom.mode_transitions`` log and updates ``current_work_mode`` /
      ``chain_position`` / ``chain_exhausted`` as appropriate.
    """
    from .modes import WORK_MODES
    from .modes.detection import apply_sprint_mode_lock, get_current_work_mode, detect_active_modes

    mode = args.work_mode.upper()
    if mode not in WORK_MODES:
        valid = ", ".join(sorted(WORK_MODES.keys()))
        print(f"❌ Unknown work mode: {mode}. Valid modes: {valid}")
        return 1

    # Detect previous mode for transition logging
    session_id = get_current_session_id()
    token_info = get_token_info(session_id)
    try:
        active_modes = detect_active_modes(session_id, token_info)
        prev_mode = get_current_work_mode(active_modes)
    except (OSError, ValueError):
        prev_mode = None

    # SPRINT mode lock: warn-and-noop if currently in SPRINT and trying to switch
    try:
        effective = apply_sprint_mode_lock(requested_mode=mode, current_work_mode=prev_mode)
    except (ImportError, AttributeError) as e:
        print(f"⚠️ MACF: SPRINT mode-lock check failed: {e}", file=sys.stderr)
        effective = mode
    if effective != mode:
        # Lock fired — helper already printed the warning. Stay in current mode.
        return 0

    info = WORK_MODES[mode]
    append_event("work_mode_change", {"mode": mode})
    print(f"✅ Work mode set: {info['emoji']} {mode}")
    from .modes.transition_messages import transition_reinforcement
    _reinforce = transition_reinforcement(mode)
    if _reinforce:
        print(f"   {_reinforce}")

    # PLAY_TIME transition recording
    try:
        from .task.sprint_gate import get_sprint_play_time_in_scope, advance_play_time_chain
        from .task.custom_models import PlayTimeCustom
        from .task.reader import TaskReader, update_task_file
        import time, copy

        autowork = get_sprint_play_time_in_scope()
        pt_task = autowork.get("play_time_task")
        if pt_task and pt_task.mtmd and pt_task.mtmd.custom:
            trigger = getattr(args, "trigger", None) or "manual"
            try:
                breadcrumb = _generate_breadcrumb()
            except (OSError, RuntimeError) as e:
                print(f"⚠️ MACF: breadcrumb generation failed: {e}", file=sys.stderr)
                breadcrumb = None

            try:
                pt = PlayTimeCustom.from_dict(pt_task.mtmd.custom)
                chain = pt.predetermined_chain
                # Did the new mode match the next step in the chain?
                next_idx = pt.chain_position + 1
                if not pt.chain_exhausted and next_idx < len(chain) and chain[next_idx] == mode:
                    if trigger == "manual":
                        trigger = "chain_advance"
                    advance_play_time_chain(pt_task)

                # Now re-read and append transition entry
                reader = TaskReader()
                stored = reader.read_task(pt_task.id)
                if stored and stored.mtmd:
                    new_custom = dict(stored.mtmd.custom or {})
                    transitions = list(new_custom.get("mode_transitions", []))
                    transitions.append({
                        "at": int(time.time()),
                        "breadcrumb": breadcrumb,
                        "from": prev_mode,
                        "to": mode,
                        "trigger": trigger,
                    })
                    new_custom["mode_transitions"] = transitions
                    new_custom["current_work_mode"] = mode
                    new_mtmd = copy.deepcopy(stored.mtmd)
                    new_mtmd.custom = new_custom
                    update_task_file(str(pt_task.id), {
                        "description": stored.description_with_updated_mtmd(new_mtmd),
                    })
            except Exception as e:
                print(f"⚠️ MACF: PLAY_TIME mode_transitions update failed: {e}", file=sys.stderr)
    except (ImportError, OSError, ValueError):
        pass

    return 0


def _generate_breadcrumb() -> str:
    """Best-effort breadcrumb for transition logging.

    Uses the in-process breadcrumb helper instead of shelling out via
    subprocess — the previous subprocess approach hit a 2s timeout because
    the spawned process pays the full Python interpreter + module-import
    cost. In-process is essentially free.
    """
    try:
        from .utils.breadcrumbs import get_breadcrumb
        return get_breadcrumb() or ""
    except (ImportError, OSError, RuntimeError) as e:
        print(f"⚠️ MACF: in-process breadcrumb failed: {e}", file=sys.stderr)
        return ""


def cmd_mode_unset_work(args: argparse.Namespace) -> int:
    """Clear the active work mode."""
    append_event("work_mode_change", {"mode": None})
    print("✅ Work mode cleared")
    return 0


def cmd_mode_show(args: argparse.Namespace) -> int:
    """Show active mode set with emojis and trigger sources."""
    from .modes import detect_active_modes, format_mode_indicators, OPERATIONAL_MODES, WORK_MODES
    from .modes import should_self_manage_closeout, should_closeout_now, is_quiet

    session_id = get_current_session_id()
    token_info = get_token_info(session_id)
    modes = detect_active_modes(session_id, token_info)

    indicators = format_mode_indicators(modes)
    print(f"🏗️ MACF{indicators}")
    print()

    print("Operational Modes:")
    for name, info in sorted(OPERATIONAL_MODES.items(), key=lambda x: x[1]["order"]):
        active = "✅" if name in modes else "—"
        print(f"  {active} {info['emoji']} {name}")

    print()
    print("Work Modes:")
    for name, info in sorted(WORK_MODES.items(), key=lambda x: x[1]["order"]):
        active = "✅" if name in modes else "—"
        print(f"  {active} {info['emoji']} {name}")

    print()
    print("Behavioral Triggers:")
    print(f"  Closeout responsibility: {'AGENT' if should_self_manage_closeout(modes) else 'USER'}")
    print(f"  Closeout urgency:        {'NOW' if should_closeout_now(modes) else 'normal'}")
    print(f"  Notification suppression: {'YES' if is_quiet(modes) else 'no'}")

    # Idle detection status
    print()
    print("Idle Detection:")
    try:
        from .transcript_monitor.daemon import is_running as tm_is_running
        tm_running = tm_is_running()
        print(f"  Transcript Monitor: {'✅ running' if tm_running else '⏹️  stopped'}")
        if tm_running:
            print("  USER_IDLE detection: ✅ active (transcript monitor + prompt hook)")
        else:
            print("  USER_IDLE detection: ⚠️  partial (prompt hook only — no mid-turn "
                  "or channel activity while TM is stopped)")
    except (ImportError, OSError) as e:
        print(f"  Transcript Monitor: ❌ unavailable ({e})")
        print("  USER_IDLE detection: ⚠️  partial (prompt hook only)")

    return 0


def cmd_recommender_show(args: argparse.Namespace) -> int:
    """Show current Markov distribution for active mode-set."""
    from .modes import detect_active_modes, get_current_work_mode, get_transition_distribution, WORK_MODES

    session_id = get_current_session_id()
    token_info = get_token_info(session_id)
    modes = detect_active_modes(session_id, token_info)
    current_wm = get_current_work_mode(modes)
    op_modes = {m for m in modes if m in ("AUTO_MODE", "USER_IDLE", "QUIET_MODE", "LOW_CONTEXT")}

    dist = get_transition_distribution(current_wm, op_modes)
    sorted_dist = sorted(dist.items(), key=lambda x: -x[1])

    print(f"Current work mode: {current_wm or '(none)'}")
    print(f"Active operational: {', '.join(sorted(op_modes)) or '(none)'}")
    print()
    print("Transition distribution:")
    for mode, prob in sorted_dist:
        emoji = WORK_MODES.get(mode, {}).get("emoji", "?")
        bar = "█" * int(prob * 40)
        print(f"  {emoji} {mode:<14} {prob:5.1%} {bar}")
    return 0


def cmd_recommender_sample(args: argparse.Namespace) -> int:
    """Trigger a Monte Carlo sample and display recommendation."""
    from .modes import (
        detect_active_modes, get_current_work_mode,
        sample_next_work_mode, format_recommendation,
    )

    session_id = get_current_session_id()
    token_info = get_token_info(session_id)
    modes = detect_active_modes(session_id, token_info)
    current_wm = get_current_work_mode(modes)
    op_modes = {m for m in modes if m in ("AUTO_MODE", "USER_IDLE", "QUIET_MODE", "LOW_CONTEXT")}

    prefix = getattr(args, "prefix", "maceff")
    selected, dist = sample_next_work_mode(current_wm, op_modes)
    print(format_recommendation(current_wm, selected, dist, prefix))
    return 0


def cmd_mode_get(args: argparse.Namespace) -> int:
    """Get current operating mode."""
    from .utils.cycles import detect_auto_mode

    try:
        session_id = get_current_session_id()
        enabled, source = detect_auto_mode(session_id)

        mode = "AUTO_MODE" if enabled else "MANUAL_MODE"

        if getattr(args, 'json_output', False):
            data = {
                "mode": mode,
                "enabled": enabled,
                "source": source,
                "session_id": session_id
            }
            print(json.dumps(data, indent=2))
        else:
            print(f"Mode: {mode}")
            print(f"Source: {source}")

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

        # USER_REMOTE / USER_PRESENT: an orthogonal presence mode, not part of the
        # AUTO/MANUAL operational toggle. Handle up front and return. It emits the
        # mode_change event detection reads; the mode auto-clears when the operator's
        # next CLI message lands (see modes.detection._detect_user_remote). v1 is
        # advisory — this switch message plus mode_system.md are the binding
        # guidance; the Ask->Deny permission enforcement is a follow-up.
        if mode in ("USER_REMOTE", "USER_PRESENT"):
            from .agent_events_log import append_event
            if mode == "USER_PRESENT":
                append_event("mode_change", {"mode": "USER_REMOTE", "enabled": False})
                from .utils.claude_settings import toggle_user_remote_deny_permissions
                restored = toggle_user_remote_deny_permissions(False)
                print("✅ USER_REMOTE cleared — operator present at the CLI.")
                if restored and restored.get("restored"):
                    print(f"   Restored {len(restored['restored'])} CLI-blocking permission(s) (restart to load).")
                return 0
            append_event("mode_change", {"mode": "USER_REMOTE", "enabled": True})
            print("📡 USER_REMOTE active. The operator is reachable ONLY via a remote")
            print("   channel (Telegram); the CLI is unattended. Do NOT use tools that")
            print("   block on CLI input — they hang the session until someone returns:")
            print("   • AskUserQuestion — does not reach Telegram. Ask via the Telegram")
            print("     reply tool, or your turn-final message (the Stop hook forwards it).")
            print("   • Ask-list commands (git push, gh pr create/merge, gh issue")
            print("     create/close, git reset --hard, rm -r, docker teardown) — each")
            print("     prompts at the empty CLI. Commit locally; HOLD pushes/PRs.")
            print("   Communicate via the Telegram reply tool. The dashboard indicator")
            print("   clears when you return to the CLI; run `mode set USER_PRESENT`")
            print("   (or restart) to restore the denied permissions.")
            from .utils.claude_settings import toggle_user_remote_deny_permissions
            denied = toggle_user_remote_deny_permissions(True)
            if denied and denied.get("denied"):
                print(f"   🚫 Denied {len(denied['denied'])} CLI-blocking tools (AskUserQuestion + "
                      "Ask-list) — takes effect on next restart.")
            return 0

        # Validate mode argument
        if mode not in ('AUTO_MODE', 'MANUAL_MODE'):
            print(f"Invalid mode: {mode}")
            print("Valid modes: AUTO_MODE, MANUAL_MODE, USER_REMOTE, USER_PRESENT")
            return 1

        enabled = (mode == 'AUTO_MODE')
        session_id = get_current_session_id()

        # MANUAL_MODE with active scope: two-step emergency friction
        # Step 1: ALWAYS warn and reject on first attempt
        # Step 2: Requires valid --justification (+ --explain for "other")
        _VALID_JUSTIFICATIONS = ["security", "opsec", "blocked", "user_directive", "other"]
        if not enabled:
            try:
                from .task.scope import get_scope_check
                from .agent_events_log import append_event, query_events
                scope = get_scope_check()
                if scope["active_count"] > 0:
                    justification = getattr(args, 'justification', None)
                    explain = getattr(args, 'explain', None)

                    # Always show warning
                    print(f"🚨 SCOPE GATE: {scope['active_count']} active scoped task(s) remain!")
                    print(f"   De-escalation to MANUAL_MODE is for EMERGENCIES ONLY.")
                    print(f"   Scoped tasks:")
                    for t in scope["active"]:
                        print(f"     👀 #{t['id']}: {t['subject']}")

                    # Check for prior warning event (step 1 must have fired)
                    recent = list(query_events({"event_type": "deescalation_warning"}))
                    has_prior_warning = len(recent) > 0

                    if not has_prior_warning:
                        # Step 1: First attempt — warn and log, always reject
                        append_event("deescalation_warning", {
                            "active_scope_count": scope["active_count"],
                            "session_id": session_id,
                        })
                        print(f"\n   ⛔ First attempt REJECTED. You must run this command again with justification.")
                        print(f"\n   Valid justifications: {', '.join(_VALID_JUSTIFICATIONS)}")
                        print(f"   macf_tools mode set MANUAL_MODE --justification <reason>")
                        print(f"   (use --justification other --explain \"detailed reason\" for unlisted reasons)")
                        return 1

                    # Step 2: Second+ attempt — validate justification
                    if not justification:
                        print(f"\n   ⛔ Missing --justification. Valid options: {', '.join(_VALID_JUSTIFICATIONS)}")
                        print(f"   macf_tools mode set MANUAL_MODE --justification <reason>")
                        return 1

                    if justification not in _VALID_JUSTIFICATIONS:
                        print(f"\n   ⛔ Invalid justification '{justification}'.")
                        print(f"   Valid options: {', '.join(_VALID_JUSTIFICATIONS)}")
                        return 1

                    if justification == "other" and not explain:
                        print(f"\n   ⛔ --justification other requires --explain \"detailed reason\"")
                        return 1

                    # Justification accepted — log event with full details
                    reason = explain if justification == "other" else justification
                    append_event("deescalation_executed", {
                        "justification": justification,
                        "explain": explain or "",
                        "active_scope_count": scope["active_count"],
                        "scoped_tasks": [t["id"] for t in scope["active"]],
                        "session_id": session_id,
                    })
                    print(f"\n   ⚠️  Emergency de-escalation ACCEPTED: {justification}" +
                          (f" — {explain}" if explain else ""))
                    print(f"   Logged to events. Will be forwarded to channels on next Stop hook.")
            except (OSError, KeyError, AttributeError) as e:
                print(f"⚠️ MACF: scope check failed during mode switch (non-blocking): {e}", file=sys.stderr)

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
            from .modes.transition_messages import transition_reinforcement
            _reinforce = transition_reinforcement(mode)
            if _reinforce:
                print(f"   {_reinforce}")

            from .utils.claude_settings import (
                set_autocompact_enabled, set_permission_mode,
                toggle_write_ask_for_auto_mode, ensure_mode_safety_permissions,
                toggle_auto_mode_ask_permissions,
            )

            # Always ensure infrastructure permissions exist (idempotent)
            safety = ensure_mode_safety_permissions()
            if safety is not None:
                if safety['deny_added']:
                    print("✅ Deny list installed:")
                    for entry in safety['deny_added']:
                        print(f"   🚫 {entry}")
                if safety['ask_added']:
                    print("✅ Permanent ask entries installed:")
                    for entry in safety['ask_added']:
                        print(f"   ❓ {entry}")
                if safety['allow_added']:
                    print("✅ Permanent allow entries installed:")
                    for entry in safety['allow_added']:
                        print(f"   ✅ {entry}")
                if not any(safety.values()):
                    print("✅ Safety permissions already present")
            else:
                print("⚠️  Could not ensure mode safety permissions")

            if enabled:
                # AUTO_MODE
                if set_autocompact_enabled(True):
                    print("✅ autoCompactEnabled set to true")
                else:
                    print("⚠️  Could not update autoCompactEnabled")
                if set_permission_mode("bypassPermissions"):
                    print("✅ permissions.defaultMode set to bypassPermissions")
                else:
                    print("⚠️  Could not update permissions.defaultMode")
                if toggle_write_ask_for_auto_mode(True):
                    print("✅ Write removed from 'ask' list")
                else:
                    print("⚠️  Could not toggle Write permission")
                auto_ask = toggle_auto_mode_ask_permissions(True)
                if auto_ask is not None:
                    changed = auto_ask.get('changed', [])
                    shadows_relocated = auto_ask.get('shadows_relocated', [])
                    if changed:
                        print("✅ AUTO_MODE ask permissions installed:")
                        for entry in changed:
                            print(f"   ❓ {entry}")
                    else:
                        print("✅ AUTO_MODE ask permissions already present")
                    if shadows_relocated:
                        print("⚠️  Shadowing allow entries relocated for safekeeping (will be restored on MANUAL_MODE return):")
                        for ask_entry, shadows in shadows_relocated:
                            print(f"   {ask_entry}")
                            for shadow in shadows:
                                print(f"     ↦ relocated: {shadow}")
                else:
                    print("⚠️  Could not install AUTO_MODE ask permissions")
                # Auto-start Transcript Monitor for idle detection
                try:
                    from .transcript_monitor.daemon import is_running as tm_is_running, start_daemon as tm_start
                    if tm_is_running():
                        print("✅ Transcript Monitor already running")
                    else:
                        tm_start()
                        print("✅ Transcript Monitor started for idle detection")
                except (ImportError, OSError) as e:
                    print(f"⚠️  Transcript Monitor auto-start failed (non-blocking): {e}", file=sys.stderr)

                print("⚠️  Restart session for permissions to take effect")
            else:
                # MANUAL_MODE
                set_autocompact_enabled(False)
                set_permission_mode("default")
                toggle_write_ask_for_auto_mode(False)
                removed = toggle_auto_mode_ask_permissions(False)
                print("✅ Restored MANUAL_MODE defaults:")
                print("   autocompact disabled")
                print("   permissions.defaultMode = default")
                print("   Write restored to ask list")
                if removed:
                    changed = removed.get('changed', [])
                    shadows_restored = removed.get('shadows_restored', [])
                    if changed:
                        print(f"   AUTO_MODE ask entries removed:")
                        for entry in changed:
                            print(f"   ↩️  {entry}")
                    if shadows_restored:
                        print(f"   Allow entries restored from safekeeping:")
                        for entry in shadows_restored:
                            print(f"   ↪️  {entry}")
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


def cmd_events_analyze(args: argparse.Namespace) -> int:
    """Analyze a structured-event JSONL log (BUG #1069 generalization).

    Wraps :class:`macf.eventlog.EventLogAnalyzer` so any JSONL log following
    the {ts, request_id, phase, ...} shape is analyzable from the CLI without
    a per-domain script. Domain customization (started phase, success field,
    elapsed field) flows through `--started-phase` / `--success-field` /
    `--elapsed-field` flags.
    """
    from .eventlog import EventLogAnalyzer, parse_since
    import json as _json

    if not args.path.exists():
        print(f"❌ Log file not found: {args.path}")
        return 1

    analyzer = EventLogAnalyzer(
        args.path,
        started_phase=args.started_phase,
        success_field=args.success_field,
        elapsed_field=args.elapsed_field,
        correlation_field=args.correlation_field,
    )

    if args.tail and args.tail > 0:
        rows = analyzer.tail(args.tail)
        if args.json_output:
            print(_json.dumps(rows, indent=2))
        else:
            print(f"Last {len(rows)} requests from {args.path}:")
            for r in rows:
                ok_emoji = "✅" if r.get("success") is True else (
                    "⏳" if r.get("success") is None else "❌"
                )
                ms = r.get("elapsed_ms")
                ms_str = f"{ms}ms" if ms is not None else "?ms"
                rid = r.get(args.correlation_field, "?")
                err = r.get("error", "") or ""
                print(
                    f"  {ok_emoji} {str(rid):<14} {r.get('terminal_phase', 'unknown'):<20} "
                    f"{ms_str:<8} {err}"
                )
        return 0

    since = parse_since(args.since) if args.since else None
    summary = analyzer.summarize(since=since, group_by=args.by)

    if args.json_output:
        print(_json.dumps(summary, indent=2))
        return 0

    print(f"Event log analysis: {args.path}")
    if since:
        print(f"Window: since {args.since}")
    print(f"  Total started:     {summary['total_started']}")
    print(f"  Completed:         {summary['completed_count']}")
    print(f"  Success count:     {summary['success_count']}")
    sr = summary["success_rate"]
    print(f"  Success rate:      {(f'{sr*100:.1f}%') if sr is not None else 'n/a'}")
    print(f"  Phase counts:      {summary['phase_counts']}")
    if summary["elapsed_ms_p50"] is not None:
        print(
            f"  Elapsed (ms):      "
            f"min={summary['elapsed_ms_min']} "
            f"p50={summary['elapsed_ms_p50']} "
            f"p90={summary['elapsed_ms_p90']} "
            f"p99={summary['elapsed_ms_p99']} "
            f"max={summary['elapsed_ms_max']}"
        )
    if "groups" in summary:
        print(f"  Groups (--by {summary['group_by_field']}): {summary['groups']}")
    return 0


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


def cmd_task_list(args: argparse.Namespace) -> int:
    """List tasks from current session with hierarchy and metadata."""
    from .task import TaskReader, MacfTask

    reader = TaskReader()
    tasks = reader.read_all_tasks()

    if not tasks:
        print("No tasks found in current session.")
        return 0

    # Sort tasks by ID (string-safe with zero-padding)
    tasks = sorted(tasks, key=lambda t: str(t.id).zfill(10))

    # Apply archive visibility filters (before other filters)
    # By default, hide archived tasks unless --all or --archived is specified
    if args.show_archived_only:
        tasks = [t for t in tasks if t.status == "archived"]
    elif not args.show_all:
        tasks = [t for t in tasks if t.status != "archived"]

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
        for t in sorted(tasks, key=lambda t: str(t.id).zfill(10)):
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
    # Sort root tasks numerically (zero-pad string IDs for proper ordering)
    root_tasks = sorted(root_tasks, key=lambda t: str(t.id).zfill(10))

    def get_children(parent_id):
        # Normalize both sides to str() so a task whose parent_id was stored as
        # int (e.g. mutated by a prior int-coercing `metadata set` — see GH #112
        # Bug 1) still matches the framework's string sentinel "000" and any
        # string parent IDs going forward.
        target = str(parent_id) if parent_id is not None else None
        return sorted(
            [t for t in tasks if (str(t.parent_id) if t.parent_id is not None else None) == target],
            key=lambda t: str(t.id).zfill(10),
        )

    # Scope markers are sourced from the EVENT LOG — the single source of truth the
    # gate uses — not the per-task MTMD scope_status field. That field is a
    # denormalized cache duplicated across task stores and drifts both ways: markers
    # vanish where it is unwritten (the event log has the task), and zombie orphans
    # persist where it is stale (the event log dropped it). get_scope_state() replays
    # scope events and is store-independent, so the tree always agrees with
    # `scope check` / `scope show`.
    from .task.scope import get_scope_state
    scope_state = get_scope_state()

    def format_task(t: MacfTask, indent: int = 0) -> str:
        prefix = "  " * indent
        # CC-style markers with colors:
        # ◼ red = in_progress, ◻ = pending, ✔ green = completed, ▫ = archived
        # Formatting: completed = strikethrough, archived = dim+strikethrough
        if t.status == "archived":
            # Cardboard brown filled box for archived (▪ with tan/brown color)
            ANSI_BROWN = "\033[38;5;137m"  # Tan/cardboard brown
            status_icon = f"{ANSI_BROWN}▪{ANSI_RESET}"
            # Dim + strikethrough for archived (strip embedded ANSI first)
            clean_subject = _strip_ansi(subject_with_live_parent(t))
            line = f"{prefix}{status_icon} {ANSI_DIM}{ANSI_STRIKE}{clean_subject}{ANSI_RESET}"
        elif t.status == "completed":
            status_icon = f"{ANSI_GREEN}✔{ANSI_RESET}"
            # Strikethrough only for completed (strip embedded ANSI first)
            clean_subject = _strip_ansi(subject_with_live_parent(t))
            line = f"{prefix}{status_icon} {ANSI_STRIKE}{clean_subject}{ANSI_RESET}"
        elif t.status == "in_progress":
            status_icon = f"{ANSI_RED}◼{ANSI_RESET}"
            line = f"{prefix}{status_icon} {_dim_task_ids(subject_with_live_parent(t))}"
        else:  # pending
            status_icon = "◻"
            line = f"{prefix}{status_icon} {_dim_task_ids(subject_with_live_parent(t))}"

        # Scope indicator (👀 active, ⏸️ paused, ✅ inactive/completed)
        if scope_state and t.id in scope_state:
            if scope_state[t.id] == "active":
                line += " 👀"
            elif scope_state[t.id] == "paused":
                line += " ⏸️"
            elif scope_state[t.id] == "inactive":
                line += " ✅"

        # Add plan_ca_ref if present (key feature of enhanced display)
        if t.mtmd and t.mtmd.plan_ca_ref:
            if t.status == "archived":
                line += f"\n{prefix}   {ANSI_DIM}{ANSI_STRIKE}→ {t.mtmd.plan_ca_ref}{ANSI_RESET}"
            elif t.status == "completed":
                line += f"\n{prefix}   {ANSI_STRIKE}→ {t.mtmd.plan_ca_ref}{ANSI_RESET}"
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

    # Print tree from roots (sorted by ID with zero-padding for numeric order)
    for root in sorted(root_tasks, key=lambda t: str(t.id).zfill(10)):
        print_tree(root)

    return 0


def cmd_task_get(args: argparse.Namespace) -> int:
    """Get detailed information about a specific task."""
    from .task import TaskReader

    # Parse task ID (handle #N or N format, support string IDs like "000")
    try:
        task_id = _parse_task_id_arg(args.task_id)
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
                "completion_report": task.mtmd.completion_report,
                "unblock_breadcrumb": task.mtmd.unblock_breadcrumb,
                "updates": [u.to_dict() for u in task.mtmd.updates],
                "archived": task.mtmd.archived,
            }
        print(json.dumps(output, indent=2))
        return 0

    # Human-readable output
    status_icon = {"completed": "✅", "in_progress": "🔄", "pending": "⏳"}.get(task.status, "❓")

    print(f"{'='*60}")
    print(f"Task #{task.id} {status_icon}")
    print(f"{'='*60}")
    print(f"Subject: {subject_with_live_parent(task)}")
    print(f"Status: {task.status}")
    if task.task_type:
        print(f"Type: {task.task_type}")
    if task.parent_id:
        print(f"Parent: #{task.parent_id}")
    if task.blocked_by:
        print(f"Blocked by: {', '.join(f'#{b}' for b in task.blocked_by)}")
    if task.blocks:
        print(f"Blocks: {', '.join(f'#{b}' for b in task.blocks)}")

    # MTMD section - iterate dataclass fields in definition order
    if task.mtmd:
        from dataclasses import fields
        print(f"\nℹ️ MacfTaskMetaData (v{task.mtmd.version})")
        print("-" * 40)
        for f in fields(task.mtmd):
            if f.name == "version":
                continue  # Already shown in header
            value = getattr(task.mtmd, f.name)
            # Skip None/empty/False values
            if value is None or value == [] or value is False or value == {}:
                continue
            # Special handling for updates list
            if f.name == "updates" and value:
                print(f"  {f.name}: ({len(value)})")
                for u in value:
                    desc = f" - {u.description}" if u.description else ""
                    marker = "📝" if getattr(u, 'type', None) == "note" else "•"
                    print(f"    {marker} {u.breadcrumb}{desc}")
            else:
                print(f"  {f.name}: {value}")

    # Description (without MTMD)
    desc_clean = task.description_without_mtmd()
    if desc_clean:
        print(f"\n📝 Description")
        print("-" * 40)
        print(desc_clean)

    print(f"\n📁 File: {task.file_path}")

    return 0


def get_display_mtime(tasks_dir) -> float:
    """Latest change to anything the tree renders — store *and* event log.

    The store alone is not enough. Scope is event-sourced: `scope set` writes to
    the event log and touches no task file, so a detector watching only the store
    cannot see it. The loop then held a stale frame until its timed redraw came
    round, which made scope markers appear up to a minute late while ordinary
    task edits appeared in about a second.

    That asymmetry is worse than uniform slowness. The display *is* updating, so
    nothing suggests any part of it is stale, and the movement is what persuades
    a reader the whole frame is current.
    """
    latest = get_tasks_mtime(tasks_dir)
    try:
        from .agent_events_log import get_log_path
        log_path = get_log_path()
        if log_path and log_path.exists():
            latest = max(latest, log_path.stat().st_mtime)
    except (OSError, ImportError):
        pass  # event log unreadable: fall back to store-only detection
    return latest


def get_tasks_mtime(tasks_dir) -> float:
    """Get latest modification time of any task file in the store directory."""
    try:
        if not tasks_dir or not tasks_dir.exists():
            return 0.0

        # Both backends are flat dirs of {id}.json (+ hidden .{id}.json).
        # Include the directory's own mtime so create/delete/hide renames
        # are detected even though they don't touch file mtimes.
        mtimes = [tasks_dir.stat().st_mtime]
        for task_file in tasks_dir.glob("*.json"):
            mtimes.append(task_file.stat().st_mtime)
        for task_file in tasks_dir.glob(".*.json"):
            mtimes.append(task_file.stat().st_mtime)

        return max(mtimes)
    except (OSError, IOError) as e:
        print(f"⚠️ MACF: task mtime scan failed: {e}", file=sys.stderr)
        return 0.0


def cmd_task_tree(args: argparse.Namespace) -> int:
    """Display task hierarchy tree from a root task."""
    import time
    from pathlib import Path
    from .task import TaskReader

    succinct = getattr(args, 'succinct', False)
    verbose = getattr(args, 'verbose', False)
    # Title width: succinct mode is a scanning view, so it trims harder. An
    # explicit --title-width overrides both defaults; 0 disables truncation.
    title_width = getattr(args, 'title_width', None)
    if title_width is None:
        title_width = 40 if succinct else 80
    show_archived_only = getattr(args, 'archived', False)
    show_all = getattr(args, 'show_all', False)

    def display_tree(root_id: str):
        """Display the task tree for given root_id."""
        reader = TaskReader()
        all_tasks = reader.read_all_tasks()

        # Scope markers sourced from the event log (single source of truth), not the
        # per-task MTMD scope_status field which drifts across stores. See the note
        # at the other render site.
        from .task.scope import get_scope_state
        scope_state = get_scope_state()

        # Archive filtering (default: hide archived)
        def is_archived(task):
            return task.mtmd and getattr(task.mtmd, 'archived', False)

        if show_archived_only:
            all_tasks = [t for t in all_tasks if is_archived(t)]
        elif not show_all:
            all_tasks = [t for t in all_tasks if not is_archived(t)]
        # else show_all: no filtering

        task_map = {t.id: t for t in all_tasks}

        if root_id not in task_map:
            print(f"❌ Task #{root_id} not found")
            print(f"   Session: {reader.session_uuid}")
            print(f"   Tasks loaded: {len(all_tasks)}")
            if all_tasks:
                ids = sorted(t.id for t in all_tasks)
                print(f"   Available IDs: {ids[:10]}{'...' if len(ids) > 10 else ''}")
            return False

        root = task_map[root_id]

        def get_children(parent_id):
            # Zero-pad IDs for proper numeric string sorting.
            # Normalize both sides to str() to handle tasks with int parent_id
            # (see GH #112 Bug 1 — int-coerced legacy entries).
            target = str(parent_id) if parent_id is not None else None
            return sorted(
                [t for t in all_tasks if (str(t.parent_id) if t.parent_id is not None else None) == target],
                key=lambda t: t.id.zfill(10),
            )

        def has_active_sibling(task, siblings):
            """Check if any sibling is active (in_progress or pending)."""
            for s in siblings:
                if s.id != task.id and s.status in ("in_progress", "pending"):
                    return True
            return False

        def is_fully_completed(task, _seen=None):
            """True when this task AND every descendant are completed.

            "Completed" alone is not enough to hide a subtree: a completed
            parent can still own active children, and hiding the parent hides
            them with it — the work disappears from the tree entirely rather
            than merely collapsing.
            """
            if task.status != "completed":
                return False
            # Same cycle guard as count_descendants: a self-parenting task is
            # malformed but reachable, and must not take the render down.
            _seen = set() if _seen is None else _seen
            if task.id in _seen:
                return True
            _seen.add(task.id)
            return all(is_fully_completed(c, _seen) for c in get_children(task.id))

        def should_show_task(task, siblings, depth, parent=None):
            """Determine if task should be shown in succinct mode.

            Succinct is progressive disclosure, not a completed-filter. The
            rule that matters: a parent still open means its finished children
            are the context that makes the remaining work legible. Hiding them
            renders an in-progress parent as a bare line with nothing under it,
            which reads as "nothing was done here" — the opposite of the truth.
            """
            if not succinct:
                return True
            # Always show root sentinel (depth 0)
            if depth == 0:
                return True
            # Always show the recency-marked (last-touched) task so its 👈 marker
            # never vanishes when that task completes — otherwise a completed
            # depth-1 task carrying the marker gets hidden below (issue #150).
            if task.id == latest_id:
                return True
            # Show if active/pending
            if task.status in ("in_progress", "pending"):
                return True
            # Top tier (depth 1): hide only a subtree that is done all the way
            # down. A completed task with active descendants stays, or those
            # descendants would have no path to the surface.
            if depth == 1:
                return not is_fully_completed(task)
            # Deeper tiers: while the parent is still open, show its completed
            # children. Their own finished descendants collapse by the same
            # rule one level further in, so a resolved branch costs one line
            # rather than a subtree.
            if parent is not None and parent.status != "completed":
                return True
            # Under a completed parent, fall back to sibling context.
            if task.status == "completed" and has_active_sibling(task, siblings):
                return True
            return False

        def count_descendants(task_id, _seen=None):
            # A task whose parent_id points at itself (or a cycle of them) is
            # malformed but reachable — a hand-edited file, a bad fixture, an
            # interrupted reparent. Without the guard this recurses until the
            # interpreter dies, taking the whole tree render with it, and the
            # traceback names recursion rather than the malformed task.
            _seen = set() if _seen is None else _seen
            if task_id in _seen:
                print(f"Warning: cycle in task hierarchy at #{task_id} — "
                      f"descendant count truncated", file=sys.stderr)
                return 0
            _seen.add(task_id)
            children = get_children(task_id)
            return len(children) + sum(count_descendants(c.id, _seen) for c in children)

        def get_task_notes(task):
            """Extract notes from task MTMD updates."""
            if not task.mtmd or not task.mtmd.updates:
                return []
            return [u for u in task.mtmd.updates if getattr(u, 'type', None) == 'note']

        def get_task_plan(task):
            """Get plan or plan_ca_ref from task MTMD."""
            if not task.mtmd:
                return None, None
            return task.mtmd.plan, task.mtmd.plan_ca_ref

        def truncate(text, max_len=70):
            """Truncate text to max_len with ellipsis."""
            if not text:
                return ""
            text = text.replace('\n', ' ').strip()
            if len(text) <= max_len:
                return text
            return text[:max_len-3] + "..."

        def get_last_update_breadcrumb(task):
            """Breadcrumb of the task's most recent activity (last update, else creation)."""
            if not task.mtmd or not task.mtmd.updates:
                return task.mtmd.creation_breadcrumb if task.mtmd else None
            return task.mtmd.updates[-1].breadcrumb

        def get_last_update_timestamp(task):
            """Extract Unix timestamp from last update's breadcrumb t_ field."""
            bc = get_last_update_breadcrumb(task)
            if not bc:
                return None
            # Extract t_ timestamp from breadcrumb (format: s_.../c_.../g_.../p_.../t_XXXXXXXX)
            import re
            match = re.search(r't_(\d+)', bc)
            return int(match.group(1)) if match else None

        def get_last_update_cycle(task):
            """Extract the cycle number from the last-activity breadcrumb (c_N)."""
            bc = get_last_update_breadcrumb(task)
            if not bc:
                return None
            import re
            match = re.search(r'/c_(\d+)', bc) or re.search(r'(?:^|/)C(\d+)', bc)
            return int(match.group(1)) if match else None

        def format_task_suffix(task):
            """Format suffix: [repo version] timestamp with status-colored timestamp."""
            from datetime import datetime
            parts = []
            # Repo and version
            if task.mtmd:
                repo = task.mtmd.repo
                version = task.mtmd.target_version
                if repo or version:
                    rv = " ".join(filter(None, [repo, version]))
                    parts.append(f"[{rv}]")
            # Timestamp from last update
            ts = get_last_update_timestamp(task)
            if ts:
                dt = datetime.fromtimestamp(ts)
                time_str = dt.strftime("%m/%d %H:%M")
                # Append the cycle the timestamp belongs to, e.g. "07/17 16:20 C25"
                cyc = get_last_update_cycle(task)
                if cyc is not None:
                    time_str = f"{time_str} C{cyc}"
                # Color based on status
                if task.status == "in_progress":
                    time_str = f"{ANSI_RED}{time_str}{ANSI_RESET}"
                elif task.status == "pending":
                    time_str = f"{ANSI_YELLOW}{time_str}{ANSI_RESET}"
                else:  # completed
                    time_str = f"{ANSI_GREEN}{time_str}{ANSI_RESET}"
                parts.append(time_str)
            return " ".join(parts) if parts else ""

        def print_task_details(task, detail_prefix):
            """Print plan and notes for a task."""
            if succinct:
                return

            # Apply strikethrough + dim to completed task details
            is_completed = task.status == "completed"
            def fmt(text):
                if is_completed:
                    return f"{ANSI_DIM}{ANSI_STRIKE}{text}{ANSI_RESET}"
                return text

            def fmt_green(text):
                return f"{ANSI_GREEN}{text}{ANSI_RESET}"

            plan, plan_ca_ref = get_task_plan(task)

            # Show plan_ca_ref or plan
            if plan_ca_ref:
                if verbose:
                    print(f"{detail_prefix}{fmt('📄 ' + plan_ca_ref)}")
                else:
                    print(f"{detail_prefix}{fmt('→ ' + truncate(plan_ca_ref, 60))}")
            elif plan:
                if verbose:
                    for line in plan.split('\n'):
                        print(f"{detail_prefix}{fmt('📋 ' + line)}")
                else:
                    print(f"{detail_prefix}{fmt('→ ' + truncate(plan, 60))}")

            # Show notes
            notes = get_task_notes(task)
            for note in notes:
                if verbose:
                    print(f"{detail_prefix}{fmt('📝 ' + note.description)}")
                    if note.breadcrumb:
                        print(f"{detail_prefix}{fmt('   🔖 ' + note.breadcrumb)}")
                else:
                    print(f"{detail_prefix}{fmt('📝 ' + truncate(note.description, 60))}")

            # In verbose mode, show all updates (not just notes, excluding completion reports)
            if verbose and task.mtmd and task.mtmd.updates:
                lifecycle_updates = [u for u in task.mtmd.updates
                                   if getattr(u, 'type', None) not in ('note', 'completion')]
                for update in lifecycle_updates:
                    desc = update.description or "(lifecycle update)"
                    print(f"{detail_prefix}{fmt('🔄 ' + desc)}")
                    if update.breadcrumb:
                        print(f"{detail_prefix}{fmt('   🔖 ' + update.breadcrumb)}")

            # Always show completion reports (both modes)
            # Last completion report = green, previous = strikethrough
            completion_reports = []
            if task.mtmd:
                # Get completion reports from updates with type='completion'
                for u in (task.mtmd.updates or []):
                    if getattr(u, 'type', None) == 'completion' and u.description:
                        completion_reports.append((u.description, u.breadcrumb))
                # Always check completion_report field (may be the primary source)
                if task.mtmd.completion_report:
                    bc = getattr(task.mtmd, 'completion_breadcrumb', None)
                    completion_reports.append((task.mtmd.completion_report, bc))

            for i, (report, breadcrumb) in enumerate(completion_reports):
                is_last = (i == len(completion_reports) - 1)
                if is_last:
                    # Last completion report: green
                    if verbose:
                        print(f"{detail_prefix}{fmt_green('✅ ' + report)}")
                        if breadcrumb:
                            print(f"{detail_prefix}{fmt_green('   🔖 ' + breadcrumb)}")
                    else:
                        print(f"{detail_prefix}{fmt_green('✅ ' + truncate(report, 60))}")
                else:
                    # Previous completion reports: strikethrough
                    if verbose:
                        print(f"{detail_prefix}{fmt('✅ ' + report)}")
                        if breadcrumb:
                            print(f"{detail_prefix}{fmt('   🔖 ' + breadcrumb)}")
                    else:
                        print(f"{detail_prefix}{fmt('✅ ' + truncate(report, 60))}")

        _rendered = set()

        def print_tree(task, prefix="", is_last=True, depth=0, siblings=None):
            # A cyclic parent chain — a hand-edited file, a bad fixture, an
            # interrupted reparent — otherwise recurses until the interpreter
            # dies, and the traceback blames recursion rather than naming the
            # malformed task. Render the node once, say so, and stop descending.
            if task.id in _rendered:
                print(f"{prefix}{'└── ' if is_last else '├── '}"
                      f"⚠️  #{task.id} — cycle in task hierarchy, not descended")
                print(f"Warning: cycle in task hierarchy at #{task.id}; "
                      f"check parent_id", file=sys.stderr)
                return
            _rendered.add(task.id)

            connector = "└── " if is_last else "├── "
            extension = "    " if is_last else "│   "

            # CC-style markers with colors - subject now contains #N prefix
            suffix = format_task_suffix(task)
            subject = _truncate_subject_title(subject_with_live_parent(task), title_width)
            if task.status == "completed":
                status_icon = f"{ANSI_GREEN}✔{ANSI_RESET}"
                text = f"{ANSI_DIM}{ANSI_STRIKE}{subject}{ANSI_RESET}"
            elif task.status == "in_progress":
                status_icon = f"{ANSI_RED}◼{ANSI_RESET}"
                text = _dim_task_ids(subject)
            else:
                status_icon = "◻"
                text = _dim_task_ids(subject)

            # Append suffix (repo, version, timestamp) after subject
            if suffix:
                text = f"{text} {suffix}"

            # Scope indicator. Inactive scope gets NO marker: those tasks are
            # completed, and the line already says so three ways (check icon,
            # strikethrough, green timestamp) -- a fourth was pure noise, and
            # the end-of-subject slot is reserved for the recency marker.
            if scope_state and task.id in scope_state:
                if scope_state[task.id] == "active":
                    text += " 👀"
                elif scope_state[task.id] == "paused":
                    text += " ⏸️"

            text += recency_marker(task)

            print(f"{prefix}{connector}{status_icon} {text}")

            # Print task details (plan, notes) with proper indentation
            detail_prefix = prefix + extension + "   "  # Extra indent beyond task header
            print_task_details(task, detail_prefix)

            children = get_children(task.id)
            # Filter children in succinct mode
            visible_children = [c for c in children if should_show_task(c, children, depth + 1, task)]

            for i, child in enumerate(visible_children):
                print_tree(child, prefix + extension, i == len(visible_children) - 1, depth + 1, children)

        # Last-touched marker: the single most recently updated task (notes,
        # lifecycle changes -- anything that stamps an update breadcrumb)
        # carries a trailing left-pointing finger plus a dim relative age, so
        # the reader can see at a glance where work last happened. Kept fresh
        # by loop mode's timed redraw.
        latest_id = None
        latest_ts = 0
        for t in all_tasks:
            _ts = get_last_update_timestamp(t)
            if _ts and _ts > latest_ts:
                latest_ts = _ts
                latest_id = t.id

        def _rel_age(ts):
            secs = max(0, int(time.time() - ts))
            if secs < 3600:
                return f"{secs // 60}m"
            if secs < 86400:
                return f"{secs // 3600}h"
            return f"{secs // 86400}d"

        def recency_marker(task):
            if task.id != latest_id or not latest_ts:
                return ""
            return f" 👈 {ANSI_DIM}{_rel_age(latest_ts)}{ANSI_RESET}"

        # Print header
        total = 1 + count_descendants(root_id)
        print(f"🌳 Task Tree from #{root_id} ({total} tasks)")
        print("=" * 60)

        # Print root specially with CC-style markers - subject now contains #N prefix
        root_suffix = format_task_suffix(root)
        root_subject = _truncate_subject_title(subject_with_live_parent(root), title_width)
        if root.status == "completed":
            status_icon = f"{ANSI_GREEN}✔{ANSI_RESET}"
            root_text = f"{ANSI_DIM}{ANSI_STRIKE}{root_subject}{ANSI_RESET}"
        elif root.status == "in_progress":
            status_icon = f"{ANSI_RED}◼{ANSI_RESET}"
            root_text = _dim_task_ids(root_subject)
        else:
            status_icon = "◻"
            root_text = _dim_task_ids(root_subject)
        if root_suffix:
            root_text = f"{root_text} {root_suffix}"
        if scope_state and root.id in scope_state:
            if scope_state[root.id] == "active":
                root_text += " 👀"
        root_text += recency_marker(root)
        print(f"{status_icon} {root_text}")

        # Print root task details (plan, notes) - extra indent beyond header
        print_task_details(root, "      ")

        # Print children
        children = get_children(root_id)
        visible_children = [c for c in children if should_show_task(c, children, 1)]
        for i, child in enumerate(visible_children):
            print_tree(child, "", i == len(visible_children) - 1, depth=1, siblings=children)

        return True

    # Parse task ID (preserve string IDs like "000")
    # Both branches set root_id to task_id_str — leading-zero forms (like "000")
    # need string identity preserved; ordinary numeric IDs are also kept as strings
    # for consistent comparison downstream. Helper handles this uniformly.
    try:
        root_id = str(_parse_task_id_arg(args.task_id))
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    # Loop mode - monitor for changes
    if args.loop:
        reader = TaskReader()
        # Watch the resolved store (home store or legacy session dir), not the
        # legacy per-session root — the home store lives outside ~/.claude/tasks.
        tasks_dir = reader.session_path
        last_mtime = None  # sentinel: always render the first iteration
        last_draw = 0.0
        REDRAW_SECS = 60.0  # timed redraw keeps relative-age displays current

        # Brand the terminal window with the agent calling card so
        # multi-agent terminal layouts are distinguishable at a glance.
        # Set once (titles persist) and only for loop mode — single-render
        # `task tree` exits too quickly to benefit.
        try:
            from .utils.identity import get_agent_identity
            from .utils.terminal import set_terminal_title
            set_terminal_title(f"{get_agent_identity()} - Task Tree")
        except (OSError, IOError, ImportError) as e:
            print(f"⚠️ MACF: could not set window title (non-blocking): {e}", file=sys.stderr)

        try:
            while True:
                current_mtime = get_display_mtime(tasks_dir)
                now = time.time()

                # Redraw when tasks changed, on first iteration, or on the
                # timed interval so age displays don't go stale.
                if last_mtime is None or current_mtime != last_mtime or (now - last_draw) >= REDRAW_SECS:
                    # Home, clear screen, THEN clear scrollback (E3) — the order
                    # tput/terminfo `clear` uses. 2J scrolls the old frame into
                    # scrollback, so 3J must come after it to wipe that copy.
                    print("\033[H\033[2J\033[3J", end="")

                    if not display_tree(root_id):
                        return 1

                    print()  # Add blank line
                    print(f"{ANSI_DIM}[Monitoring for changes... Press Ctrl+C to exit]{ANSI_RESET}")
                    last_mtime = current_mtime
                    last_draw = now

                time.sleep(1)  # Poll every second

        except KeyboardInterrupt:
            print()  # Clean newline after Ctrl+C
            return 0

    # Normal mode - single display
    return 0 if display_tree(root_id) else 1


def cmd_task_delete(args: argparse.Namespace) -> int:
    """Delete one or more tasks with set-matching grant authorization.

    Requires grant-delete to have been run first with EXACTLY the same task IDs.
    Temporarily unprotects directory for deletion, then re-protects.
    """
    import os
    import stat
    from .task import TaskReader
    from .task.protection import check_grant_in_events, clear_grant
    from .task.create import SENTINEL_TASK_ID

    # Parse all task IDs (handle #N or N format, keep as strings)
    task_ids = []
    for tid_raw in args.task_ids:
        tid_str = str(tid_raw).lstrip('#')
        task_ids.append(tid_str)

    # Block deletion of sentinel task
    filtered_ids = []
    for tid in task_ids:
        if tid == SENTINEL_TASK_ID:
            print(f"⚠️  Skipping sentinel task #{SENTINEL_TASK_ID}")
        else:
            filtered_ids.append(tid)

    if not filtered_ids:
        print("❌ No valid tasks to delete")
        return 1

    # Check for delete grant - sets must match EXACTLY
    has_grant, grant_event = check_grant_in_events("delete", filtered_ids)
    if not has_grant:
        id_list = " ".join(filtered_ids)
        print(f"❌ Delete requires grant authorization")
        print(f"   Run: macf_tools task grant-delete {id_list}")
        print(f"   (Grant must match EXACTLY the tasks to delete)")
        return 1

    # Verify tasks exist
    reader = TaskReader()
    to_delete = []
    for tid in filtered_ids:
        task = reader.read_task(tid)
        if task:
            print(f"🗑️  #{tid}: {task.subject[:60]}")
            to_delete.append(tid)
        else:
            print(f"⚠️  #{tid}: not found, skipping")

    if not to_delete:
        print("❌ No tasks found to delete")
        return 1

    # Confirmation (basic CLI protection)
    if not args.force:
        print()
        confirm = input(f"⚠️  Delete {len(to_delete)} task(s)? [y/N]: ").strip().lower()
        if confirm != 'y':
            print("❌ Cancelled")
            return 1

    # Temporarily unprotect directory for deletion
    session_path = reader.session_path
    if session_path and session_path.exists():
        current_mode = session_path.stat().st_mode
        if not (current_mode & stat.S_IWUSR):
            os.chmod(session_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 755

    try:
        deleted = 0
        for tid in to_delete:
            task_file = reader.session_path / f"{tid}.json"
            if task_file.exists():
                task_file.unlink()
                deleted += 1
                print(f"   ✓ Deleted #{tid}")
    finally:
        # Re-protect directory
        if session_path and session_path.exists():
            os.chmod(session_path, stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)  # 555

    # Clear the grant after use
    clear_grant("delete", filtered_ids, reason="consumed by delete")

    print(f"\n✅ Deleted {deleted} task(s)")
    return 0


def cmd_task_edit(args: argparse.Namespace) -> int:
    """Edit a top-level JSON field in a task file."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    # Parse task ID
    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    field = args.field
    value = args.value

    # Validate field is editable
    # Note: 'subject' is NOT directly editable - it's composed from task_id, parent_id, type, and title
    # To change the title portion, use: macf_tools task metadata set title "New Title"
    if field == "subject":
        print(f"❌ Direct subject editing is not allowed")
        print(f"   Subject is composed from task metadata (id, parent, type, title)")
        print(f"   To change the title: macf_tools task metadata set {task_id} title \"New Title\"")
        return 1

    # Block direct status editing - use lifecycle commands instead
    if field == "status":
        print(f"❌ Direct status editing is not allowed")
        print(f"   Use lifecycle commands instead:")
        print(f"   • macf_tools task start {task_id}    → in_progress")
        print(f"   • macf_tools task pause {task_id}    → pending")
        print(f"   • macf_tools task complete {task_id} → completed")
        print(f"   • macf_tools task archive {task_id}  → archived")
        return 1

    # Block direct description editing - preserves MTMD metadata
    if field == "description":
        print(f"❌ Direct description editing is not allowed")
        print(f"   Description contains MTMD metadata set during creation.")
        print(f"   Use structured commands instead:")
        print(f"   • macf_tools task note {task_id} \"message\"  → append notes")
        print(f"   • macf_tools task edit {task_id} plan \"ref\" → update plan reference")
        return 1

    editable_fields = []
    if field not in editable_fields:
        print(f"❌ Field '{field}' is not editable")
        return 1

    # Validate status values
    # Note: "archived" is not a CC-native status but we allow it - CC UI will hide these tasks
    if field == "status" and value not in ["pending", "in_progress", "completed", "archived"]:
        print(f"❌ Invalid status value: {value}")
        print("   Valid values: pending, in_progress, completed, archived")
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
        # Check if new description already has MTMD (user provided it)
        if "<macf_task_metadata" not in value:
            # Append updated MTMD to NEW description (preserving update history)
            mtmd_block = f'<macf_task_metadata version="{new_mtmd.version}">\n{new_mtmd.to_yaml()}</macf_task_metadata>'
            value = f"{value}\n\n{mtmd_block}"
        # else: user provided MTMD in their description, use as-is

    # Apply update
    if update_task_file(task_id, {field: value}):
        print(f"✅ Updated task #{task_id}")
        print(f"   {field} = {value[:50]}{'...' if len(str(value)) > 50 else ''}")
        return 0
    else:
        print(f"❌ Failed to update task #{task_id}")
        return 1


def cmd_task_metadata_get(args: argparse.Namespace) -> int:
    """Display MTMD for a task (pure metadata output)."""
    from .task import TaskReader

    # Parse task ID
    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    # Read task
    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    if not task.mtmd:
        print(f"⚠️  Task #{task_id} has no MTMD")
        return 0

    # Output MTMD
    mtmd = task.mtmd
    print(f"ℹ️ MacfTaskMetaData (v{mtmd.version}) for #{task_id}")
    print("-" * 40)
    if mtmd.creation_breadcrumb:
        print(f"  creation_breadcrumb: {mtmd.creation_breadcrumb}")
    if mtmd.created_cycle:
        print(f"  created_cycle: {mtmd.created_cycle}")
    if mtmd.created_by:
        print(f"  created_by: {mtmd.created_by}")
    if mtmd.parent_id:
        print(f"  parent_id: {mtmd.parent_id}")
    if mtmd.plan_ca_ref:
        print(f"  plan_ca_ref: {mtmd.plan_ca_ref}")
    if mtmd.experiment_ca_ref:
        print(f"  experiment_ca_ref: {mtmd.experiment_ca_ref}")
    if mtmd.repo:
        print(f"  repo: {mtmd.repo}")
    if mtmd.target_version:
        print(f"  target_version: {mtmd.target_version}")
    if mtmd.release_branch:
        print(f"  release_branch: {mtmd.release_branch}")
    if mtmd.completion_breadcrumb:
        print(f"  completion_breadcrumb: {mtmd.completion_breadcrumb}")
    if mtmd.unblock_breadcrumb:
        print(f"  unblock_breadcrumb: {mtmd.unblock_breadcrumb}")
    if mtmd.archived:
        print(f"  archived: {mtmd.archived}")
    if mtmd.archived_at:
        print(f"  archived_at: {mtmd.archived_at}")
    if mtmd.custom:
        print(f"  custom:")
        for k, v in mtmd.custom.items():
            print(f"    {k}: {v}")
    if mtmd.updates:
        print(f"  updates: ({len(mtmd.updates)})")
        for u in mtmd.updates:
            marker = "📝" if getattr(u, 'type', None) == "note" else "•"
            print(f"    {marker} {u.breadcrumb} - {u.description}")

    return 0


def cmd_task_metadata_set(args: argparse.Namespace) -> int:
    """Set an MTMD field within a task's description."""
    from .task import TaskReader, update_task_file, MacfTaskMetaData
    from .utils.breadcrumbs import get_breadcrumb

    # Parse task ID
    try:
        task_id = _parse_task_id_arg(args.task_id)
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

    # Validate MTMD field exists - use dataclass as single source of truth
    import dataclasses
    mtmd_fields = [f.name for f in dataclasses.fields(MacfTaskMetaData) if f.name not in ("version", "updates")]
    if field not in mtmd_fields:
        print(f"❌ Unknown MTMD field: {field}")
        print(f"   Valid fields: {', '.join(sorted(mtmd_fields))}")
        return 1

    # Parse value types for specific fields.
    # NOTE: `parent_id` is kept as a STRING. The framework's top-level
    # sentinel is the literal string "000" (SENTINEL_TASK_ID), and the
    # tree-rendering get_children() does equality matching. Coercing to
    # int here would store 0 and orphan the task from `task tree`
    # because `0 == "000"` is False. The get_children helpers normalize
    # both sides to str() to also catch tasks that were already mutated
    # by the prior int-coercing version. Closes cversek/MacEff#112 Bug 1.
    if field == "parent_id" and value != "null":
        # Light validation: must be a positive integer literal or the sentinel.
        if not (value.isdigit() or value == "000"):
            print(f"❌ parent_id must be a digit string (e.g. '000', '42') or 'null'")
            return 1
        # Keep as-is (string) — preserves "000" sentinel exactly.
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

    # Protection check: modifying existing value requires grant
    if task.mtmd:
        old_val = getattr(task.mtmd, field, None)
        if old_val is not None and old_val != value:
            # Changing existing value - check for grant with field/value specificity
            from .task.protection import check_grant_in_events, clear_grant
            has_grant, _ = check_grant_in_events("update", task_id, field=field, value=value)
            if not has_grant:
                print(f"❌ Modifying MTMD field '{field}' requires grant (current value: {old_val!r})")
                print(f"   To authorize: macf_tools task grant-update {task_id} --field {field} --value \"{value}\"")
                return 1
            # Clear the grant (single-use)
            clear_grant("update", task_id, "consumed_by_metadata_set")

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

    # Build updates dict
    updates = {"description": new_description}

    # If title or other subject-affecting fields changed, recompose subject.
    # Skip the recompose when MTMD title is None and the changed field isn't
    # the title itself — compose_subject formats `... {title}` directly,
    # which renders as the literal string "None" and blanks the visible
    # title of plugin tasks (whose MTMD.title is intentionally None). The
    # parent_id / task_type change is still reflected in MTMD; only the
    # visible subject is preserved. Closes cversek/MacEff#112 Bug 3.
    if field in ("title", "task_type", "parent_id"):
        title_for_recompose = new_mtmd.title or (value if field == "title" else None)
        if title_for_recompose is None:
            # Conservative: keep the existing subject when we have no title
            # to synthesize one from. The user can re-set title explicitly
            # via `metadata set <id> title "..."` to trigger a fresh recompose.
            pass
        else:
            from .task.create import compose_subject
            new_subject = compose_subject(
                task_id=str(task_id),
                task_type=new_mtmd.task_type,
                title=title_for_recompose,
                parent_id=new_mtmd.parent_id,
            )
            updates["subject"] = new_subject

    # Apply update
    if update_task_file(task_id, updates):
        print(f"✅ Updated MTMD for task #{task_id}")
        print(f"   {field} = {value}")
        if "subject" in updates:
            print(f"   subject recomposed")
        return 0
    else:
        print(f"❌ Failed to update task #{task_id}")
        return 1


def cmd_task_metadata_add(args: argparse.Namespace) -> int:
    """Add a custom field to MTMD's custom section."""
    from .task import TaskReader, update_task_file, MacfTaskMetaData
    from .utils.breadcrumbs import get_breadcrumb

    # Parse task ID
    try:
        task_id = _parse_task_id_arg(args.task_id)
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


def cmd_task_reparent(args: argparse.Namespace) -> int:
    """Atomically change a task's parent_id, gating on grant and rejecting cycles."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    new_parent_raw = args.parent
    # Validate parent argument: must be digit string or the literal "null"
    if new_parent_raw != "null" and not (new_parent_raw.isdigit() or new_parent_raw == "000"):
        print(f"❌ <parent> must be a digit string (e.g. '000', '42') or 'null'")
        return 1

    # Normalise: "null" maps to None inside MTMD but we store "null" as sentinel
    # on the wire so callers see consistent string output.
    new_parent = new_parent_raw  # keep as string throughout

    # Reject self-as-parent
    if new_parent != "null" and str(task_id) == new_parent:
        print(f"❌ Cannot make task its own parent")
        return 1

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    old_parent = task.parent_id or "000"

    # Cycle detection: walk new_parent's parent chain, looking for task_id
    if new_parent not in ("null", "000"):
        visited = set()
        cursor = new_parent
        depth = 0
        while cursor and cursor not in ("null", "000") and depth < 10:
            if str(cursor) == str(task_id):
                print(f"❌ Cycle detected: reparenting #{task_id} under #{new_parent} would create a parent→child loop")
                return 1
            visited.add(cursor)
            ancestor = reader.read_task(cursor)
            if not ancestor:
                break
            next_parent = ancestor.parent_id
            if next_parent is None or next_parent == "000":
                break
            cursor = next_parent
            if cursor in visited:
                break
            depth += 1

    # Grant gate for existing parent_id field
    if task.mtmd and task.mtmd.parent_id is not None:
        from .task.protection import check_grant_in_events, clear_grant
        has_grant, _ = check_grant_in_events("update", task_id, field="parent_id", value=new_parent)
        if not has_grant:
            print(f"❌ Changing parent_id requires grant (current: {old_parent!r})")
            print(f"   To authorize: macf_tools task grant-update {task_id} --field parent_id --value \"{new_parent}\"")
            return 1
        clear_grant("update", task_id, "consumed_by_reparent")

    # Apply update via MTMD plumbing
    breadcrumb = get_breadcrumb()
    if task.mtmd:
        # Store "null" as None in MTMD when caller passes "null"
        mtmd_value = None if new_parent == "null" else new_parent
        new_mtmd = task.mtmd.with_updated_field("parent_id", mtmd_value, breadcrumb, f"Reparent via CLI")
    else:
        from .task import MacfTaskMetaData
        from .task.models import MacfTaskUpdate
        new_mtmd = MacfTaskMetaData()
        new_mtmd.parent_id = None if new_parent == "null" else new_parent
        new_mtmd.updates.append(MacfTaskUpdate(
            breadcrumb=breadcrumb,
            description=f"Created MTMD with parent_id via reparent CLI",
            agent="PA"
        ))

    new_description = task.description_with_updated_mtmd(new_mtmd)
    updates = {"description": new_description}

    # Always recompose the subject so its [^#parent] marker tracks parent_id.
    # When the MTMD title isn't stored, recover it from the current subject —
    # closing the Bug-3 gap where a title-less task kept a stale parent marker.
    from .task.create import compose_subject, title_from_subject
    custom = new_mtmd.custom or None
    title = new_mtmd.title
    if title is None:
        title = title_from_subject(task.subject, new_mtmd.task_type,
                                   new_mtmd.plan_ca_ref, custom)
    new_subject = compose_subject(
        task_id=str(task_id),
        task_type=new_mtmd.task_type,
        title=title,
        parent_id=new_mtmd.parent_id,
        plan_ca_ref=new_mtmd.plan_ca_ref,
        custom=custom,
    )
    updates["subject"] = new_subject

    if update_task_file(task_id, updates):
        print(f"✅ Reparented #{task_id}: {old_parent} → {new_parent}")
        return 0
    else:
        print(f"❌ Failed to reparent task #{task_id}")
        return 1


def cmd_task_trace(args: argparse.Namespace) -> int:
    """Show where attention has been, and what it owes a return to.

    The tree answers "what work exists". This answers "what was I in the middle
    of" — which after an interrupt, a compaction, or a handoff is the question
    that actually needs answering, and the one a tree of six open tasks cannot.
    """
    from .task import TaskReader
    from .task.trace import visitation_trace, open_frames

    tasks = TaskReader().read_all_tasks()
    frames = open_frames(tasks)
    path_n = getattr(args, "path", 0)

    if getattr(args, "json", False):
        print(json.dumps({
            "frames": [vars(f) for f in frames],
            "path": [vars(t) for t in reversed(visitation_trace(tasks)[-path_n:])] if path_n else [],
        }, indent=2))
        return 0

    if path_n:
        # Newest first: the question this answers is a recency question, and the
        # convention every other log-shaped tool sets. The move markers survive
        # the reversal because they were computed chronologically and carried on
        # each touch — reading them off display adjacency would invert them.
        trace = visitation_trace(tasks)[-path_n:]
        full = getattr(args, "full", False)
        print(f"👣 Where attention has been — {len(trace)} most recent, newest first\n")
        for touch in reversed(trace):
            moved = "→" if touch.begins_dwell else " "
            when = _rel_age_short(touch.timestamp)
            note = touch.description if full else _ellipsize(touch.description, 56)
            print(f"  {moved} #{touch.task_id:<6} {when:>8}  {note}")
        print()

    # An enclosing frame owes nothing — the work is running inside it. Counting
    # it as a debt would make the tally grow with every level of decomposition.
    owed = [f for f in frames if f.state not in ("active", "enclosing")]
    print(f"🧵 Open frames: {len(frames)} ({len(owed)} awaiting a return)")
    if not frames:
        print("   ✅ nothing in progress")
        return 0

    icon = {"active": "▶️ ", "enclosing": "📂", "parked": "⏸️ ", "abandoned": "⚠️ "}
    for f in frames:
        when = _rel_age_short(f.last_touch) if f.last_touch else "never"
        print(f"   {icon.get(f.state, '  ')} #{f.task_id:<6} {f.state:<10} last touched {when}")
        print(f"        {_strip_ansi(f.subject)[:96]}")
        if f.blockers_open:
            print(f"        ⏸  waiting on {', '.join('#' + b for b in f.blockers_open)}")
        if f.parent_completed and f.state != "active":
            print(f"        ⚠️  its parent is marked COMPLETE while this is still running")

    # Recommend a frame that was actually dropped. Pointing at a parked frame
    # sends the agent at something legitimately waiting on a blocker, and this
    # line is the one an agent *acts* on — during recovery, when it has least
    # context with which to notice the advice is wrong.
    dropped = [f for f in owed if f.state == "abandoned"]
    if dropped:
        print(f"\n   Resume with:  macf_tools task start {dropped[0].task_id}")
    return 0


def _ellipsize(text: str, width: int) -> str:
    """Trim to `width`, marking the cut so a truncated note cannot read as whole.

    A note silently clipped mid-sentence looks like a note that simply ended
    there, which is the reading most likely to mislead whoever is reconstructing
    what they were doing.
    """
    text = (text or "").strip()
    if len(text) <= width:
        return text
    return text[:width - 1].rstrip() + "…"


def _rel_age_short(ts) -> str:
    """Compact relative age, e.g. '3m', '5h', '12d'."""
    if not ts:
        return "?"
    secs = max(0, int(time.time() - int(ts)))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit}"
    return f"{secs}s"


def _doctor_check_subject_markers(tasks) -> "list[tuple[str, str, str]]":
    """Find tasks whose stored ``[^#N]`` marker disagrees with ``parent_id``.

    Returns:
        list of (task_id, stored_subject, corrected_subject) for divergent tasks.
    """
    findings = []
    for t in tasks:
        corrected = subject_with_live_parent(t)
        if corrected != t.subject:
            findings.append((t.id, t.subject, corrected))
    return findings


def cmd_task_store_init(args: argparse.Namespace) -> int:
    """Provision the home task store for an agent home, idempotently.

    This is the mechanism provisioning calls so the home store is *built*
    rather than opted into. It had been neither: nothing in agent init, config
    init or any downstream provisioning script created the directory or wrote
    the config key, so every agent silently ran on the session-scoped legacy
    store — the one CC deletes from and that a fork duplicates.

    Deliberately does NOT migrate. Provisioning a fresh home and rescuing an
    existing history are different operations with different failure modes, and
    a command that quietly did both would make ``--dry-run`` mean two things.
    Use ``task migrate-store`` for the second.

    Idempotent: safe to run on every provision and every upgrade.
    """
    from .task.reader import TaskReader

    if getattr(args, "home", None):
        agent_home = Path(args.home).expanduser()
        if not agent_home.is_dir():
            print(f"❌ Not a directory: {agent_home}", file=sys.stderr)
            return 1
    else:
        agent_home = find_agent_home()
        if not agent_home:
            print("❌ Could not determine the agent home; pass --home.",
                  file=sys.stderr)
            return 1

    _, rel = TaskReader._load_task_store_config()
    store = agent_home / rel
    config_path = agent_home / ".maceff" / "config.json"

    created = not store.exists()
    try:
        store.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"❌ Could not create {store}: {e}", file=sys.stderr)
        return 1
    print(f"{'✅ Created' if created else '✓ Present'}: {store}")

    # Read-modify-write. A fresh home has no config at all, and an existing one
    # holds identity and hook settings that must survive being pointed at a new
    # store.
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            print(f"❌ Refusing to overwrite unreadable {config_path}: {e}",
                  file=sys.stderr)
            print("   The directory exists; fix the config and re-run.")
            return 1

    was = (config.get("task_store") or {}).get("mode")
    config.setdefault("task_store", {})
    config["task_store"]["mode"] = "home"
    config["task_store"].setdefault("path", rel)
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    except OSError as e:
        print(f"❌ Could not write {config_path}: {e}", file=sys.stderr)
        return 1
    print(f"{'✓ Already' if was == 'home' else '✅ Set'}: "
          f"task_store.mode = home  ({config_path})")

    _ensure_store_gitignored_for_migration(store)
    return 0


def cmd_task_migrate_store(args: argparse.Namespace) -> int:
    """Move the legacy per-session task store into the project-scoped home store.

    The legacy store lives under CC's ``~/.claude/tasks/{session_uuid}/`` and is
    keyed by session: a continue, rewind or fork gets a *copy* that then
    diverges, and CC deletes completed task files once the last open task
    closes. The home store is a single directory under the agent home, so it
    survives all of that.

    Done by hand this is: copy every file including the dot-prefixed completed
    ones, edit the config, then hope. The ordering is what matters — **copy,
    verify, then flip** — because a config flipped before verification points
    the agent at a store that may be incomplete, and the failure looks like
    amnesia rather than like a bad migration.

    The legacy directory is never deleted. Reverting is a one-line config edit
    as long as it is still there.

    **Every** legacy session directory is migrated, not just the current one. An
    agent that has been continued, rewound or forked has several, and migrating
    only the session that happens to be live produces a result shaped exactly
    like a complete one: a success message, a populated store, and a directory
    left behind that nothing will ever mention again.

    Dot-prefixed completed tasks are normalised to plain ``{id}.json`` on the
    way in, because the prefix exists solely to hide files from CC's scanner and
    the home store is never scanned.
    """
    import hashlib
    from .task import TaskReader

    dry_run = getattr(args, "dry_run", False)
    force = getattr(args, "force", False)

    def _digest(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    mode, rel = TaskReader._load_task_store_config()
    if mode == "home" and not force:
        print("✅ Already on the home store — nothing to migrate.")
        print("   Re-run with --force to copy any remaining legacy files in.")
        return 0

    # Every session directory, oldest first, not merely the live one.
    #
    # Resolved through TaskReader rather than from Path.home(): MACF_TASKS_DIR
    # relocates the legacy root for isolation, and reading ~/.claude directly
    # ignores it — which points a sandboxed run at the real store. The mirror of
    # the leak reader.py guards against in the other direction.
    cc_root = TaskReader._get_tasks_dir()
    source_dirs = sorted(
        (d for d in cc_root.glob("*/") if d.is_dir()),
        key=lambda d: d.name,
    ) if cc_root.exists() else []
    if not source_dirs:
        print("❌ No legacy task store found under "
              f"{cc_root} — nothing to migrate.")
        return 1

    agent_home = find_agent_home()
    target = agent_home / rel
    config_path = agent_home / ".maceff" / "config.json"

    # Gather every file from every directory, keyed by the name it will land
    # under. Normalising the dot prefix here is what makes two directories
    # comparable at all: ".7.json" and "7.json" are the same task.
    by_target_name = {}
    total_seen = 0
    print(f"📦 Migrate task store")
    for d in source_dirs:
        files = TaskReader(session_uuid=d.name).list_task_files(include_hidden=True)
        hidden = [f for f in files if f.name.startswith(".")]
        total_seen += len(files)
        print(f"   from: {d}  ({len(files)} files, {len(hidden)} hidden)")
        for f in files:
            by_target_name.setdefault(f.name.lstrip("."), []).append(f)
    print(f"   to:   {target}")
    print(f"   config: {config_path}")
    print(f"   {total_seen} file(s) across {len(source_dirs)} directory(ies) "
          f"-> {len(by_target_name)} task(s)")

    if not by_target_name:
        print("❌ Legacy store is empty — refusing to migrate nothing.")
        return 1

    # Divergence between directories. A fork copies the store and both sides
    # then move on, so the same id can exist twice with different content.
    # Choosing silently would discard whichever copy lost a coin toss.
    conflicts = {}
    chosen = {}
    for name, candidates in sorted(by_target_name.items()):
        digests = {_digest(c) for c in candidates}
        if len(digests) == 1:
            chosen[name] = candidates[0]
        else:
            conflicts[name] = candidates
            chosen[name] = max(candidates, key=lambda p: p.stat().st_mtime)

    if conflicts and not force:
        print(f"\n❌ {len(conflicts)} task(s) differ between legacy directories:")
        for name, cands in list(conflicts.items())[:5]:
            print(f"   {name}")
            for c in sorted(cands, key=lambda p: p.stat().st_mtime, reverse=True):
                stamp = datetime.fromtimestamp(c.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                print(f"      {stamp}  {c.parent.name}/{c.name}")
        if len(conflicts) > 5:
            print(f"   ... and {len(conflicts) - 5} more")
        print("\n   Refusing to choose for you. Re-run with --force to take the "
              "most recently modified copy of each,")
        print("   which is reported per file so the discarded ones are named "
              "rather than silently dropped.")
        return 1
    if conflicts:
        print(f"\n⚠️  {len(conflicts)} divergent task(s); taking most recent:")
        for name, cands in sorted(conflicts.items()):
            keep = chosen[name]
            dropped = [f"{c.parent.name}/{c.name}" for c in cands if c is not keep]
            print(f"   {name}: keeping {keep.parent.name}/{keep.name}, "
                  f"discarding {', '.join(dropped)}")

    collisions = []
    if target.exists():
        for name in chosen:
            if (target / name).exists():
                collisions.append(name)
    if collisions and not force:
        print(f"\n❌ {len(collisions)} file(s) already exist in the target "
              f"(e.g. {collisions[:3]}).")
        print("   Refusing to overwrite. Re-run with --force if that is intended.")
        return 1

    if dry_run:
        print("\n🔍 Dry run — nothing copied, config untouched.")
        return 0

    # 1. COPY
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for name, src in sorted(chosen.items()):
        try:
            (target / name).write_bytes(src.read_bytes())
            copied += 1
        except OSError as e:
            print(f"❌ Copy failed at {name}: {e}", file=sys.stderr)
            print("   Config NOT flipped; the legacy store is untouched.")
            return 1

    # 2. VERIFY before flipping. A config pointed at an unverified store fails
    #    later, elsewhere, and looks like data loss rather than a bad copy.
    mismatched = []
    for name, src in chosen.items():
        dest = target / name
        if not dest.exists() or _digest(dest) != _digest(src):
            mismatched.append(name)
    if mismatched:
        print(f"\n❌ Verification failed for {len(mismatched)} file(s): "
              f"{mismatched[:5]}")
        print("   Config NOT flipped. The legacy store remains authoritative.")
        return 1
    print(f"\n✅ Copied and verified {copied} file(s) (sha256, byte-for-byte)")

    # 3. FLIP
    try:
        config = json.loads(config_path.read_text()) if config_path.exists() else {}
    except (OSError, json.JSONDecodeError) as e:
        print(f"❌ Could not read {config_path}: {e}", file=sys.stderr)
        print("   Files are copied and verified; set task_store.mode=home by hand.")
        return 1

    config.setdefault("task_store", {})
    config["task_store"]["mode"] = "home"
    config["task_store"].setdefault("path", rel)
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(config, indent=2) + "\n")
    except OSError as e:
        print(f"❌ Could not write {config_path}: {e}", file=sys.stderr)
        print("   Files are copied and verified; set task_store.mode=home by hand.")
        return 1

    print(f"✅ Config flipped: task_store.mode = home")

    # Only now does the store read as "home", which is what the gitignore
    # helper gates on — calling it before the flip would silently no-op.
    _ensure_store_gitignored_for_migration(target)

    print("\n📁 The legacy store(s) are retained at:")
    for d in source_dirs:
        print(f"   {d}")
    print("   Nothing was deleted — revert by setting task_store.mode back to "
          "\"legacy\".")
    print("\n▶️  Verify with: macf_tools task tree")
    return 0


def _ensure_store_gitignored_for_migration(target: Path) -> None:
    """Gitignore a store created by migration rather than by first task write."""
    try:
        from .task.create import _ensure_store_gitignored
        _ensure_store_gitignored(target)
    except (ImportError, OSError) as e:
        print(f"Warning: could not gitignore {target}: {e}", file=sys.stderr)


def _gh_live_state(kind: str, repo_slug: str, number: str) -> "Optional[str]":
    """Query GitHub for the current state of an issue or PR.

    Args:
        kind: ``"issue"`` or ``"pr"``.
        repo_slug: ``owner/repo``.
        number: Issue or PR number.

    Returns:
        ``OPEN`` / ``CLOSED`` / ``MERGED``, or None when the query fails —
        an unreachable authority is reported as unknown, never as agreement.
    """
    import subprocess as _subprocess
    try:
        r = _subprocess.run(
            ["gh", kind, "view", str(number), "--repo", repo_slug, "--json", "state"],
            capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return None
        return (json.loads(r.stdout) or {}).get("state")
    except (FileNotFoundError, _subprocess.TimeoutExpired, ValueError, OSError) as e:
        print(f"Warning: could not query {repo_slug} {kind} #{number}: {e}",
              file=sys.stderr)
        return None


def _doctor_check_gh_state(tasks, include_completed: bool = False):
    """Compare open GitHub-backed tasks against live GitHub state.

    Only tasks that are still open are checked by default: a completed task's
    cached state has no operational consequence, while an open task whose
    issue or PR has already been resolved is the drift that matters — it is
    what left a task pending for hours after its PR merged.

    The cached ``gh_state`` is never trusted as the answer; it is one of the
    two values being compared.

    Returns:
        list of dicts with task id, reference, cached state, live state, and
        whether the task itself should be closed out.
    """
    findings = []
    for t in tasks:
        mtmd = getattr(t, "mtmd", None)
        if not mtmd or getattr(mtmd, "task_type", None) not in ("GH_ISSUE", "GH_PR"):
            continue
        if not include_completed and t.status in ("completed", "archived"):
            continue

        custom = getattr(mtmd, "custom", None) or {}
        owner, repo = custom.get("gh_owner"), custom.get("gh_repo")
        is_pr = mtmd.task_type == "GH_PR"
        number = custom.get("gh_pr_number") if is_pr else custom.get("gh_issue_number")
        if not (owner and repo and number):
            continue

        repo_slug = f"{owner}/{repo}"
        live = _gh_live_state("pr" if is_pr else "issue", repo_slug, number)
        if live is None:
            findings.append({
                "id": t.id, "ref": f"{repo_slug}#{number}",
                "cached": custom.get("gh_state"), "live": None,
                "task_status": t.status, "resolved_upstream": False,
                "unreachable": True,
            })
            continue

        cached = custom.get("gh_state")
        # "Resolved upstream" is only a finding when the task has NOT been
        # closed out. A completed task whose PR merged is the correct end
        # state, not drift — its cached field may still be stale, which is
        # reported separately and is harmless once nothing acts on the task.
        open_task = t.status not in ("completed", "archived")
        resolved = open_task and live in ("CLOSED", "MERGED")
        if cached != live or resolved:
            findings.append({
                "id": t.id, "ref": f"{repo_slug}#{number}",
                "cached": cached, "live": live,
                "task_status": t.status, "resolved_upstream": resolved,
                "unreachable": False,
            })
    return findings


def cmd_task_doctor(args: argparse.Namespace) -> int:
    """Reconcile stored task records against the authorities they derive from.

    Read-only by default: it reports divergence and exits non-zero so a caller
    can gate on it. ``--fix`` applies the corrections it is safe to apply
    unattended.

    Two checks, two authorities. The hierarchy marker is compared against
    ``parent_id`` on the same object; a GitHub-backed task is compared against
    live GitHub. Both complement the read-time re-derivation in the renderers:
    displays are truthful without this, but the stored records are what other
    consumers — including automation — actually read.
    """
    from .task import TaskReader, update_task_file

    fix = getattr(args, "fix", False)
    skip_gh = getattr(args, "no_github", False)
    include_completed = getattr(args, "all", False)
    tasks = TaskReader().read_all_tasks()
    print(f"🩺 Task doctor — {len(tasks)} task(s) scanned\n")

    marker_findings = _doctor_check_subject_markers(tasks)
    print(f"Hierarchy markers: {len(marker_findings)} divergent")
    if not marker_findings:
        print("   ✅ every [^#N] marker agrees with its parent_id")
    for task_id, stored, corrected in marker_findings:
        print(f"   #{task_id}")
        print(f"     stored:    {_strip_ansi(stored)}")
        print(f"     corrected: {_strip_ansi(corrected)}")
        if fix:
            if update_task_file(task_id, {"subject": corrected}):
                print("     ✅ healed")
            else:
                print(f"     ❌ could not write #{task_id}")

    gh_findings = []
    print()
    if skip_gh:
        print("GitHub state: skipped (--no-github)")
    else:
        gh_findings = _doctor_check_gh_state(tasks, include_completed=include_completed)
        checked = "all" if include_completed else "open"
        print(f"GitHub state ({checked} tasks): {len(gh_findings)} divergent")
        if not gh_findings:
            print("   ✅ every tracked issue/PR agrees with its task")
        for f in gh_findings:
            if f["unreachable"]:
                print(f"   #{f['id']} {f['ref']} — ⚠️  unreachable, state unknown")
                continue
            print(f"   #{f['id']} {f['ref']}  cached={f['cached']} live={f['live']}")
            if f["resolved_upstream"]:
                print(f"     ⚠️  resolved upstream while the task is still "
                      f"{f['task_status']} — close it out with a report:")
                print(f"        macf_tools task complete {f['id']} --report \"...\"")
            if fix and f["cached"] != f["live"]:
                task = next((t for t in tasks if t.id == f["id"]), None)
                if task is None:
                    continue
                new_mtmd = task.mtmd
                new_mtmd.custom = {**(new_mtmd.custom or {}), "gh_state": f["live"]}
                if update_task_file(
                    f["id"], {"description": task.description_with_updated_mtmd(new_mtmd)}
                ):
                    print(f"     ✅ cached state refreshed to {f['live']}")
                else:
                    print(f"     ❌ could not write #{f['id']}")

    # Completion is a judgement call that owes a report, so --fix refreshes
    # cached metadata but never closes a task on the operator's behalf.
    needs_closeout = [f for f in gh_findings if f.get("resolved_upstream")]
    total = len(marker_findings) + len(gh_findings)
    print()
    if total == 0:
        print("✅ No drift detected.")
        return 0
    if fix and not needs_closeout:
        print(f"🔧 Healed {total} record(s).")
        return 0
    if needs_closeout:
        print(f"⚠️  {len(needs_closeout)} task(s) resolved upstream still need a "
              f"completion report — task doctor will not write one for you.")
    if not fix:
        print(f"⚠️  {total} record(s) diverge from their authority. "
              f"Re-run with --fix to heal what is safe to heal.")
    return 1


def cmd_task_advance(args: argparse.Namespace) -> int:
    """Drive a plugin task's lifecycle state through its declared state machine."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    new_state = args.state
    reason = getattr(args, "reason", None) or ""

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    if not task.mtmd:
        print(f"❌ Task #{task_id} has no MTMD and no lifecycle_state_machine declared in custom")
        return 1

    state_machine = task.mtmd.custom.get("lifecycle_state_machine")
    if state_machine is None:
        print(f"❌ Task #{task_id} has no lifecycle_state_machine declared in custom")
        return 1

    if not isinstance(state_machine, dict):
        print(f"❌ Task #{task_id} lifecycle_state_machine must be a flat dict mapping state → [legal_next_states]")
        return 1

    # Determine current state
    current_state = task.mtmd.custom.get("lifecycle_state")
    if current_state is None:
        # Use declared initial state or first key
        current_state = task.mtmd.custom.get("lifecycle_state_machine_initial") or (
            next(iter(state_machine), None)
        )

    if current_state not in state_machine:
        print(f"❌ Current state {current_state!r} is not a key in lifecycle_state_machine")
        return 1

    legal_next = state_machine[current_state]
    if new_state not in legal_next:
        print(f"❌ Illegal transition: {current_state} → {new_state}. Legal: {set(legal_next)}")
        return 1

    # Update custom.lifecycle_state
    breadcrumb = get_breadcrumb()
    import copy
    new_mtmd = copy.deepcopy(task.mtmd)
    new_mtmd.custom["lifecycle_state"] = new_state
    from .task.models import MacfTaskUpdate
    new_mtmd.updates.append(MacfTaskUpdate(
        breadcrumb=breadcrumb,
        description=f"Lifecycle advanced {current_state} → {new_state} via CLI",
        agent="PA"
    ))

    new_description = task.description_with_updated_mtmd(new_mtmd)

    if update_task_file(task_id, {"description": new_description}):
        # Emit forensic event
        from .agent_events_log import append_event
        append_event("task_lifecycle_advanced", {
            "task_id": str(task_id),
            "from_state": current_state,
            "to_state": new_state,
            "reason": reason,
        })
        print(f"✅ Advanced #{task_id}: {current_state} → {new_state}")
        return 0
    else:
        print(f"❌ Failed to advance lifecycle for task #{task_id}")
        return 1


def _dotted_path_set(container: dict, path_segments: list, value):
    """
    Set a value in a nested dict/list structure using a list of path segments.

    String segments index into dicts (creating intermediate dicts as needed).
    Numeric segments index into lists.
    """
    if not path_segments:
        return
    key = path_segments[0]
    # Numeric segment → list index
    try:
        idx = int(key)
        is_index = True
    except ValueError:
        is_index = False

    if len(path_segments) == 1:
        if is_index:
            container[idx] = value
        else:
            container[key] = value
    else:
        # Descend, creating intermediate dicts as needed
        if is_index:
            next_node = container[idx]
        else:
            if key not in container or not isinstance(container[key], (dict, list)):
                container[key] = {}
            next_node = container[key]
        _dotted_path_set(next_node, path_segments[1:], value)


def _dotted_path_exists(container: dict, path_segments: list) -> bool:
    """Return True if the dotted path already exists in the container."""
    node = container
    for seg in path_segments:
        try:
            idx = int(seg)
            if not isinstance(node, list) or idx >= len(node):
                return False
            node = node[idx]
        except ValueError:
            if not isinstance(node, dict) or seg not in node:
                return False
            node = node[seg]
    return True


def cmd_task_metadata_set_custom(args: argparse.Namespace) -> int:
    """Set or create a key in MTMD.custom using a dotted-path syntax."""
    import re
    import json as _json
    from .task import TaskReader, update_task_file, MacfTaskMetaData
    from .utils.breadcrumbs import get_breadcrumb

    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    dotted_path = args.path
    raw_value = args.value
    use_json = getattr(args, "json", False)

    # Validate dotted path is non-empty
    path_segments = dotted_path.split(".")
    if not all(seg for seg in path_segments):
        print(f"❌ Invalid path: {dotted_path!r} (empty segment)")
        return 1

    # Parse value
    if use_json:
        try:
            value = _json.loads(raw_value)
        except _json.JSONDecodeError as e:
            print(f"❌ Invalid JSON: {e}")
            return 1
    else:
        # Default coercion
        low = raw_value.lower()
        if low == "true":
            value = True
        elif low == "false":
            value = False
        elif low == "null":
            value = None
        elif re.fullmatch(r"-?\d+", raw_value):
            value = int(raw_value)
        elif re.fullmatch(r"-?\d+\.\d+", raw_value):
            value = float(raw_value)
        else:
            value = raw_value

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    import copy
    breadcrumb = get_breadcrumb()
    if task.mtmd:
        new_mtmd = copy.deepcopy(task.mtmd)
    else:
        new_mtmd = MacfTaskMetaData()

    # Grant gate: only when the key already exists in custom
    existing_custom = new_mtmd.custom
    key_exists = _dotted_path_exists(existing_custom, path_segments)
    if key_exists:
        from .task.protection import check_grant_in_events, clear_grant
        grant_field = f"custom.{dotted_path}"
        has_grant, _ = check_grant_in_events("update", task_id, field=grant_field, value=value)
        if not has_grant:
            print(f"❌ Modifying existing custom.{dotted_path} requires grant")
            print(f"   To authorize: macf_tools task grant-update {task_id} --field \"{grant_field}\" --value \"{value}\"")
            return 1
        clear_grant("update", task_id, "consumed_by_set_custom")

    # Apply the dotted-path set
    _dotted_path_set(existing_custom, path_segments, value)

    # Record update
    from .task.models import MacfTaskUpdate
    new_mtmd.updates.append(MacfTaskUpdate(
        breadcrumb=breadcrumb,
        description=f"Set custom.{dotted_path} = {value!r} via CLI",
        agent="PA"
    ))

    new_description = task.description_with_updated_mtmd(new_mtmd)

    if update_task_file(task_id, {"description": new_description}):
        print(f"✅ Set #{task_id} custom.{dotted_path} = {value!r}")
        return 0
    else:
        print(f"❌ Failed to set custom.{dotted_path} on task #{task_id}")
        return 1


def cmd_task_create_mission(args: argparse.Namespace) -> int:
    """Create MISSION task with roadmap folder."""
    from .task.create import create_mission

    # Parse parent ID (normalize)
    parent_id = args.parent.lstrip('#') if args.parent else "000"

    try:
        result = create_mission(
            title=args.title,
            parent_id=parent_id,
            repo=args.repo,
            version=args.version
        )

        if args.json:
            # JSON output for automation
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "folder_path": result.folder_path,
                "ca_path": result.ca_path,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "plan_ca_ref": result.mtmd.plan_ca_ref,
                    "repo": result.mtmd.repo,
                    "target_version": result.mtmd.target_version
                }
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-friendly output
            print(f"✅ Created MISSION task #{result.task_id}")
            print(f"📁 Folder: {result.folder_path}")
            print(f"📄 Roadmap: {result.ca_path}")
            print(f"🏷️  Subject: {result.subject}")
            print()
            print("Next steps:")
            print("1. Edit roadmap.md to fill in phases")
            print(f"2. Run `macf_tools task get #{result.task_id}` to view task details")

        return 0
    except Exception as e:
        print(f"❌ Failed to create MISSION: {e}")
        return 1


def cmd_task_create_experiment(args: argparse.Namespace) -> int:
    """Create EXPERIMENT task with protocol folder."""
    from .task.create import create_experiment

    # Parse parent ID (normalize)
    parent_id = args.parent.lstrip('#') if args.parent else "000"

    try:
        result = create_experiment(title=args.title, parent_id=parent_id)

        if args.json:
            # JSON output for automation
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "folder_path": result.folder_path,
                "ca_path": result.ca_path,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "plan_ca_ref": result.mtmd.plan_ca_ref
                }
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-friendly output
            print(f"✅ Created EXPERIMENT task #{result.task_id}")
            print(f"📁 Folder: {result.folder_path}")
            print(f"📄 Protocol: {result.ca_path}")
            print(f"🏷️  Subject: {result.subject}")
            print()
            print("Next steps:")
            print("1. Edit protocol.md to fill in hypothesis and method")
            print(f"2. Run `macf_tools task get #{result.task_id}` to view task details")

        return 0
    except Exception as e:
        print(f"❌ Failed to create EXPERIMENT: {e}")
        return 1


def cmd_task_create_detour(args: argparse.Namespace) -> int:
    """Create DETOUR task with roadmap folder."""
    from .task.create import create_detour

    # Parse parent ID (normalize)
    parent_id = args.parent.lstrip('#') if args.parent else "000"

    try:
        result = create_detour(
            title=args.title,
            parent_id=parent_id,
            repo=args.repo,
            version=args.version
        )

        if args.json:
            # JSON output for automation
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "folder_path": result.folder_path,
                "ca_path": result.ca_path,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "plan_ca_ref": result.mtmd.plan_ca_ref,
                    "repo": result.mtmd.repo,
                    "target_version": result.mtmd.target_version
                }
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-friendly output
            print(f"✅ Created DETOUR task #{result.task_id}")
            print(f"📁 Folder: {result.folder_path}")
            print(f"📄 Roadmap: {result.ca_path}")
            print(f"🏷️  Subject: {result.subject}")
            print()
            print("Next steps:")
            print("1. Edit roadmap.md to define detour objectives")
            print(f"2. Run `macf_tools task get #{result.task_id}` to view task details")

        return 0
    except Exception as e:
        print(f"❌ Failed to create DETOUR: {e}")
        return 1


def cmd_task_create_phase(args: argparse.Namespace) -> int:
    """Create phase task under parent."""
    from .task.create import create_phase

    # Parse parent ID
    parent_id_str = args.parent.lstrip('#')
    try:
        parent_id = int(parent_id_str)
    except ValueError:
        print(f"❌ Invalid parent ID: {args.parent}")
        return 1

    # Get plan or plan_ca_ref (XOR enforced by argparse)
    plan = getattr(args, 'plan', None)
    plan_ca_ref = getattr(args, 'plan_ca_ref', None)

    # Parse blocked-by IDs (strip # prefix)
    blocked_by = None
    if getattr(args, 'blocked_by', None):
        blocked_by = [bid.lstrip('#') for bid in args.blocked_by]

    try:
        result = create_phase(parent_id=parent_id, title=args.title, plan=plan, plan_ca_ref=plan_ca_ref, blocked_by=blocked_by)

        if args.json:
            # JSON output for automation
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "parent_id": result.mtmd.parent_id
                }
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-friendly output
            print(f"✅ Created phase task #{result.task_id}")
            print(f"🏷️  Subject: {result.subject}")
            print(f"📎 Parent: #{parent_id}")
            if blocked_by:
                print(f"🚧 Blocked by: {', '.join(f'#{b}' for b in blocked_by)}")
            print()
            print("Next steps:")
            print(f"1. Run `macf_tools task tree #{parent_id}` to see hierarchy")

        return 0
    except Exception as e:
        print(f"❌ Failed to create phase: {e}")
        return 1


def cmd_task_create_bug(args: argparse.Namespace) -> int:
    """Create bug task (standalone or under parent)."""
    from .task.create import create_bug

    # Parse optional parent ID
    parent_id = None
    if args.parent:
        parent_id_str = args.parent.lstrip('#')
        # Preserve string IDs (like "000") or convert numeric
        if parent_id_str.lstrip('0') == '' or not parent_id_str.isdigit():
            parent_id = parent_id_str  # Keep as string
        else:
            parent_id = parent_id_str  # Keep as string for consistency

    # Get plan or plan_ca_ref (XOR enforced in create_bug)
    plan = getattr(args, 'plan', None)
    plan_ca_ref = getattr(args, 'plan_ca_ref', None)

    try:
        result = create_bug(
            title=args.title,
            parent_id=parent_id,
            plan=plan,
            plan_ca_ref=plan_ca_ref
        )

        if args.json:
            # JSON output for automation
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "parent_id": result.mtmd.parent_id
                }
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-friendly output
            print(f"✅ Created BUG task #{result.task_id}")
            print(f"🏷️  Subject: {result.subject}")
            if parent_id:
                print(f"📎 Parent: #{parent_id}")
                print()
                print("Next steps:")
                print(f"1. Run `macf_tools task tree #{parent_id}` to see hierarchy")
            else:
                print()
                print("Next steps:")
                print(f"1. Run `macf_tools task get #{result.task_id}` to view details")
                print("2. Mark in_progress when starting work")

        return 0
    except Exception as e:
        print(f"❌ Failed to create bug: {e}")
        return 1


def cmd_task_create_gh_issue(args: argparse.Namespace) -> int:
    """Create GH_ISSUE task by auto-fetching from GitHub."""
    from .task.create import create_gh_issue

    parent_id = None
    if args.parent:
        parent_id = args.parent.lstrip('#')

    try:
        result = create_gh_issue(
            issue_url=args.issue_url,
            parent_id=parent_id,
        )

        if args.json:
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "parent_id": result.mtmd.parent_id,
                    "custom": result.mtmd.custom,
                }
            }
            print(json.dumps(output, indent=2))
        else:
            custom = result.mtmd.custom
            labels = custom.get("gh_labels", [])
            print(f"✅ Created GH_ISSUE task #{result.task_id}")
            print(f"🏷️  Subject: {result.subject}")
            if labels:
                print(f"🏷️  Labels: {', '.join(labels)}")
            print(f"🔗 {custom.get('gh_url', args.issue_url)}")
            if parent_id:
                print(f"📎 Parent: #{parent_id}")

        return 0
    except Exception as e:
        print(f"❌ Failed to create GH_ISSUE: {e}")
        return 1


def cmd_task_create_gh_pr(args: argparse.Namespace) -> int:
    """Create GH_PR task by auto-fetching from a GitHub pull request."""
    from .task.create import create_gh_pr

    parent_id = None
    if args.parent:
        parent_id = args.parent.lstrip('#')

    try:
        result = create_gh_pr(
            pr_url=args.pr_url,
            parent_id=parent_id,
        )

        if args.json:
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "parent_id": result.mtmd.parent_id,
                    "custom": result.mtmd.custom,
                }
            }
            print(json.dumps(output, indent=2))
        else:
            custom = result.mtmd.custom
            labels = custom.get("gh_labels", [])
            linked = custom.get("linked_issues", [])
            print(f"✅ Created GH_PR task #{result.task_id}")
            print(f"🏷️  Subject: {result.subject}")
            if labels:
                print(f"🏷️  Labels: {', '.join(labels)}")
            print(f"🌿 {custom.get('head_branch', '?')} → {custom.get('base_branch', '?')}")
            if linked:
                print(f"🔗 Fixes: {', '.join('#' + str(n) for n in linked)}")
            print(f"🔗 {custom.get('gh_url', args.pr_url)}")
            if parent_id:
                print(f"📎 Parent: #{parent_id}")

        return 0
    except Exception as e:
        print(f"❌ Failed to create GH_PR: {e}")
        return 1


def cmd_task_create_deleg(args: argparse.Namespace) -> int:
    """Create DELEG_PLAN task for delegation work."""
    from .task.create import create_deleg

    # Parse optional parent ID
    parent_id = None
    if args.parent:
        parent_id_str = args.parent.lstrip('#')
        parent_id = parent_id_str

    # Get plan or plan_ca_ref (XOR enforced in create_deleg)
    plan = getattr(args, 'plan', None)
    plan_ca_ref = getattr(args, 'plan_ca_ref', None)

    try:
        result = create_deleg(
            title=args.title,
            parent_id=parent_id,
            plan=plan,
            plan_ca_ref=plan_ca_ref
        )

        if args.json:
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by,
                    "parent_id": result.mtmd.parent_id
                }
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"✅ Created DELEG task #{result.task_id}")
            print(f"🏷️  Subject: {result.subject}")
            if parent_id:
                print(f"📎 Parent: #{parent_id}")
            print()
            print("Next steps:")
            print(f"1. Run `macf_tools task get #{result.task_id}` to view details")
            print("2. Mark in_progress when starting delegation")

        return 0
    except Exception as e:
        print(f"❌ Failed to create deleg: {e}")
        return 1


def cmd_task_create_task(args: argparse.Namespace) -> int:
    """Create standalone TASK for general work."""
    from .task.create import create_task

    # Parse parent ID (normalize)
    parent_id = args.parent.lstrip('#') if args.parent else "000"

    # Get plan or plan_ca_ref (XOR enforced by argparse)
    plan = getattr(args, 'plan', None)
    plan_ca_ref = getattr(args, 'plan_ca_ref', None)

    try:
        result = create_task(title=args.title, parent_id=parent_id, plan=plan, plan_ca_ref=plan_ca_ref)

        if args.json:
            # JSON output for automation
            output = {
                "task_id": result.task_id,
                "subject": result.subject,
                "mtmd": {
                    "version": result.mtmd.version,
                    "creation_breadcrumb": result.mtmd.creation_breadcrumb,
                    "created_cycle": result.mtmd.created_cycle,
                    "created_by": result.mtmd.created_by
                }
            }
            print(json.dumps(output, indent=2))
        else:
            # Human-friendly output
            print(f"✅ Created task #{result.task_id}")
            print(f"🏷️  Subject: {result.subject}")
            print()
            print("Next steps:")
            print(f"1. Run `macf_tools task get #{result.task_id}` to view details")
            print(f"2. Mark in_progress when starting work")

        return 0
    except Exception as e:
        print(f"❌ Failed to create task: {e}")
        return 1


def cmd_task_create_sprint(args: argparse.Namespace) -> int:
    """Create SPRINT task (workload-defined autonomous work, no timer)."""
    from .task.create import create_sprint

    # Hard-fail if --timer was passed (sprint rejects timers)
    if getattr(args, "timer", None) is not None and args.timer > 0:
        print(
            "Error: SPRINT does not accept --timer. "
            "For time-bounded autonomous work, use 'task create play_time'."
        )
        return 1

    parent_id = int(args.parent.lstrip("#")) if args.parent and args.parent.lstrip("#").isdigit() else 0

    scoped = getattr(args, "scoped", None)
    children = getattr(args, "children", None)

    try:
        result = create_sprint(
            title=args.title,
            goal=getattr(args, "goal", None),
            scoped_task_ids=[int(x.lstrip("#")) for x in scoped] if scoped else None,
            children_titles=list(children) if children else None,
            parent_id=parent_id,
            repo=getattr(args, "repo", None),
            no_auto_start=getattr(args, "no_auto_start", False),
        )

        if getattr(args, "json", False):
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Created SPRINT task #{result['task_id']}")
            print(f"📄 Sprint log: {result['ca_path']}")
            print(f"📌 Scope ({len(result['scope'])} tasks): {result['scope']}")
            if result["auto_start_completed"]:
                print(f"🏃 Auto-started in SPRINT mode")
            elif not getattr(args, "no_auto_start", False):
                print(f"⚠️  Auto-start incomplete: {result.get('auto_start_error')}")
            else:
                print("ℹ️  --no-auto-start: task created but not started")
        return 0
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    except Exception as e:
        print(f"❌ Failed to create SPRINT: {e}")
        return 1


def cmd_task_create_play_time(args: argparse.Namespace) -> int:
    """Create PLAY_TIME task (time-bounded autonomous exploration)."""
    from .task.create import create_play_time

    timer = getattr(args, "timer", None)
    if timer is None or timer <= 0:
        print(
            "Error: PLAY_TIME requires --timer with positive minutes. "
            "For workload-defined autonomous work, use 'task create sprint'."
        )
        return 1

    parent_id = int(args.parent.lstrip("#")) if args.parent and args.parent.lstrip("#").isdigit() else 0

    scoped = getattr(args, "scoped", None)
    children = getattr(args, "children", None)
    chain = getattr(args, "chain", None)

    try:
        result = create_play_time(
            title=args.title,
            goal=getattr(args, "goal", None),
            timer_minutes=timer,
            chain=[m.upper() for m in chain] if chain else None,
            children_titles=list(children) if children else None,
            scoped_task_ids=[int(x.lstrip("#")) for x in scoped] if scoped else None,
            parent_id=parent_id,
            repo=getattr(args, "repo", None),
            no_auto_start=getattr(args, "no_auto_start", False),
        )

        if getattr(args, "json", False):
            print(json.dumps(result, indent=2))
        else:
            print(f"✅ Created PLAY_TIME task #{result['task_id']}")
            print(f"📄 Play log: {result['ca_path']}")
            print(f"📌 Scope ({len(result['scope'])} tasks): {result['scope']}")
            if result["auto_start_completed"]:
                print(f"⏲️  Auto-started in {result['initial_mode']} mode (timer: {timer} min)")
            elif not getattr(args, "no_auto_start", False):
                print(f"⚠️  Auto-start incomplete: {result.get('auto_start_error')}")
            else:
                print("ℹ️  --no-auto-start: task created but not started")
        return 0
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    except Exception as e:
        print(f"❌ Failed to create PLAY_TIME: {e}")
        return 1


def cmd_task_archive(args: argparse.Namespace) -> int:
    """DEPRECATED: task archive no longer performs meaningful archiving.

    The operator retired this command (2026-08-06): it printed a ✅ success line
    while writing nothing — a report of a state change that did not happen, the
    exact failure mode to avoid. Rather than repair an unwanted feature it now
    fails closed with a pointer to the supported alternative. Kept as a stub (not
    removed) so the subcommand still resolves and explains itself rather than
    vanishing from under existing muscle memory.
    """
    if getattr(args, "json_output", False):
        import json
        print(json.dumps({
            "success": False,
            "deprecated": True,
            "message": "task archive is deprecated; it performed no archiving. "
                       "Use `task hide-completed` to declutter.",
        }, indent=2))
    else:
        print("⚠️  `task archive` is DEPRECATED and performs no archiving.")
        print("    It used to print a success checkmark while writing nothing — a")
        print("    false report of a state change. To declutter the task tree, use:")
        print("        macf_tools task hide-completed")
    # Fail closed: never exit 0, so nothing can read this as a successful archive.
    return 2


def cmd_task_restore(args: argparse.Namespace) -> int:
    """DEPRECATED: the archive/restore/archived trio is retired.

    `task restore` restored a task from an archive produced by `task archive` —
    which is itself deprecated for reporting success while archiving nothing.
    With no supported way to produce an archive, restore has no real input, so it
    is retired alongside archive rather than left as a path into dead machinery.
    Kept as a self-explaining stub (not removed) so the subcommand still resolves
    and points at the supported alternative instead of vanishing.
    """
    if getattr(args, "json_output", False):
        import json
        print(json.dumps({
            "success": False,
            "deprecated": True,
            "message": "task restore is deprecated; the archive subsystem it "
                       "depended on performed no real archiving. Use "
                       "`task hide-completed` / `task unhide-all` to manage tree clutter.",
        }, indent=2))
    else:
        print("⚠️  `task restore` is DEPRECATED — the archive/restore/archived")
        print("    trio is retired. `task archive` reported success while writing")
        print("    nothing, so there is no supported archive to restore from. To")
        print("    manage task-tree clutter, use:")
        print("        macf_tools task hide-completed")
        print("        macf_tools task unhide-all")
    # Fail closed: never exit 0, so nothing reads this as a successful restore.
    return 2


def cmd_task_archived_list(args: argparse.Namespace) -> int:
    """DEPRECATED: the archive/restore/archived trio is retired.

    `task archived` listed archives produced by `task archive` — which is
    deprecated for reporting success while archiving nothing. With no supported
    way to produce an archive, this list is definitionally empty, so it is retired
    alongside archive rather than left implying a working archive store. Kept as a
    self-explaining stub (not removed) so the subcommand still resolves.
    """
    if getattr(args, "json_output", False):
        import json
        print(json.dumps({
            "success": False,
            "deprecated": True,
            "message": "task archived is deprecated; the archive subsystem "
                       "produced no real archives. Use `task hide-completed` / "
                       "`task unhide-all` to manage tree clutter.",
        }, indent=2))
    else:
        print("⚠️  `task archived` is DEPRECATED — the archive/restore/archived")
        print("    trio is retired. `task archive` produced no real archives, so this")
        print("    list has nothing to show. To manage task-tree clutter, use:")
        print("        macf_tools task hide-completed")
        print("        macf_tools task unhide-all")
    # Fail closed: never exit 0, so nothing reads this as an authoritative listing.
    return 2


def cmd_task_hide_completed(args: argparse.Namespace) -> int:
    """Bulk dot-prefix all completed task files to hide from CC scanner."""
    from .task import TaskReader
    from .task.reader import hide_task_file
    import json

    reader = TaskReader()
    if not reader.session_path or not reader.session_path.exists():
        print("❌ No task session found")
        return 1

    # Snapshot visible task files before iterating (glob is lazy, files rename during loop)
    hidden_count = 0
    skipped_count = 0
    visible_files = list(reader.session_path.glob("*.json"))
    for task_file in visible_files:
        try:
            with open(task_file, "r") as f:
                data = json.load(f)
            if data.get("status") == "completed":
                task_id = task_file.stem
                if hide_task_file(reader.session_path, task_id):
                    hidden_count += 1
                else:
                    skipped_count += 1
        except (json.JSONDecodeError, IOError):
            continue

    # Re-count after all renames complete
    visible_after = len(list(reader.session_path.glob("*.json")))
    hidden_after = len(list(reader.session_path.glob(".*.json")))
    print(f"✅ Hidden {hidden_count} completed task files from CC scanner")
    if skipped_count:
        print(f"   ⚠️  {skipped_count} files failed to hide")
    print(f"   📁 CC-visible: {visible_after} | Hidden: {hidden_after}")
    return 0


def cmd_task_unhide_all(args: argparse.Namespace) -> int:
    """Restore all hidden (dot-prefixed) task files to visible state."""
    from .task import TaskReader
    from .task.reader import unhide_task_file

    reader = TaskReader()
    if not reader.session_path or not reader.session_path.exists():
        print("❌ No task session found")
        return 1

    unhidden_count = 0
    for task_file in reader.session_path.glob(".*.json"):
        task_id = task_file.stem.lstrip('.')
        if unhide_task_file(reader.session_path, task_id):
            unhidden_count += 1

    total = len(list(reader.session_path.glob("*.json")))
    print(f"✅ Restored {unhidden_count} hidden task files")
    print(f"   📁 Total CC-visible files: {total}")
    return 0


def cmd_task_grant_update(args: argparse.Namespace) -> int:
    """Grant permission to update a task's description."""
    from .task.protection import create_grant

    # Parse task ID
    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    # Validate --value requires --field
    field = getattr(args, 'field', None)
    value = getattr(args, 'value', None)
    if value is not None and field is None:
        print("❌ --value requires --field to be specified")
        return 1

    create_grant("update", task_id, args.reason, field=field, value=value)
    print(f"✅ Grant created for updating task #{task_id}")
    if field:
        print(f"   Field: {field}")
    if value:
        print(f"   Expected value: {value}")
    if args.reason:
        print(f"   Reason: {args.reason}")
    print("   Grant is single-use and will be cleared after consumption.")
    return 0


def cmd_task_grant_delete(args: argparse.Namespace) -> int:
    """Grant permission to delete one or more tasks (single grant for the set)."""
    from .task.protection import create_grant

    # Parse all task IDs into a normalized set
    task_ids = []
    for task_id_raw in args.task_ids:
        task_id_str = str(task_id_raw).lstrip('#')
        # Keep as string (per Cycle 382 string ID refactor)
        task_ids.append(task_id_str)

    # Create ONE grant for the entire set
    create_grant("delete", task_ids, args.reason)

    if len(task_ids) == 1:
        print(f"✅ Grant created for deleting task #{task_ids[0]}")
    else:
        id_list = ", ".join(f"#{tid}" for tid in task_ids)
        print(f"✅ Grant created for deleting {len(task_ids)} tasks: {id_list}")
    if args.reason:
        print(f"   Reason: {args.reason}")
    print("   Grant is single-use and will be cleared after consumption.")

    return 0


def _stale_resume_info(task):
    """Detect resuming work that was put down in an earlier cycle.

    Returns (last_cycle, last_ts, current_cycle) if the task's most recent
    activity was in a cycle before the current one and the task isn't complete;
    otherwise None. Must be called BEFORE appending the new start update, so the
    "last activity" reflects the prior work, not this resume.
    """
    from .utils.breadcrumbs import get_breadcrumb, parse_breadcrumb
    if not task.mtmd or task.status == "completed":
        return None
    bc = None
    if task.mtmd.updates:
        bc = task.mtmd.updates[-1].breadcrumb
    bc = bc or getattr(task.mtmd, "started_breadcrumb", None) or task.mtmd.creation_breadcrumb
    prev = parse_breadcrumb(bc or "") or {}
    cur = parse_breadcrumb(get_breadcrumb() or "") or {}
    last_cycle, cur_cycle = prev.get("cycle"), cur.get("cycle")
    if last_cycle is None or cur_cycle is None or last_cycle >= cur_cycle:
        return None
    return (last_cycle, prev.get("timestamp"), cur_cycle)


def _print_stale_resume_banner(task_id, last_cycle, last_ts, cur_cycle):
    """Terminal banner prompting the read-notes-and-narrate resume ritual."""
    from .utils.temporal import format_duration
    import time as _time
    elapsed = f", {format_duration(_time.time() - last_ts)} ago" if last_ts else ""
    print(f"🔁 Resuming #{task_id} — last worked in Cycle {last_cycle}{elapsed} (now Cycle {cur_cycle}).")
    print(f"   Put down across cycles; the live working context was lost to compaction. Before continuing:")
    print(f"   • Read the full history:  macf_tools task get {task_id}")
    print(f"   • Re-read every note in the update stream, plus any plan/CA it references.")
    print(f"   • Narrate your understanding of where things stand and the next step to the user before executing.")


def cmd_task_start(args: argparse.Namespace) -> int:
    """Start work on a task - sets status to in_progress with started_breadcrumb."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb
    import json

    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    reader = TaskReader()

    # Unhide task file if it was completed (dot-prefixed) — must happen before update
    from .task.reader import unhide_task_file
    if reader.session_path:
        unhide_task_file(reader.session_path, str(task_id))

    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    # Detect resuming work put down in an earlier cycle BEFORE mutating the task,
    # so "last activity" reflects the prior work rather than this resume.
    stale = _stale_resume_info(task)

    breadcrumb = get_breadcrumb()

    if task.status == "in_progress":
        # Already active. Both a same-cycle re-start and a stale resume are
        # legitimate RESUMPTIONS and both refresh the recency stamp; they differ
        # only in ceremony. A stale resume (last worked an earlier cycle) also
        # prompts the read-notes-and-narrate ritual, which same-cycle work does
        # not need because the history is still in context.
        #
        # Re-starting used to warn and return without touching anything, which
        # made resumption invisible: an agent returning to a task it had put
        # down could not move the tree's focus marker back to it, so the tree
        # kept asserting that work was happening wherever it LAST happened
        # rather than where it IS happening. Interleaved work made that reliably
        # wrong. Resuming is an event, not a mistake.
        if not stale:
            if task.mtmd:
                from .task.models import MacfTaskUpdate
                import copy
                new_mtmd = copy.deepcopy(task.mtmd)
                new_mtmd.updates.append(MacfTaskUpdate(
                    breadcrumb=breadcrumb,
                    description="Task resumed via CLI (same-cycle)",
                    agent="PA"))
                update_task_file(task_id, {"description": task.description_with_updated_mtmd(new_mtmd)})
            append_event("task_resumed", {
                "task_id": str(task_id), "from_cycle": None, "breadcrumb": breadcrumb})
            print(f"▶️  Task #{task_id} resumed (was already in_progress)")
            print(f"   Breadcrumb: {breadcrumb}")
            return 0
        last_cycle, last_ts, cur_cycle = stale
        if task.mtmd:
            from .task.models import MacfTaskUpdate
            import copy
            new_mtmd = copy.deepcopy(task.mtmd)
            new_mtmd.started_breadcrumb = breadcrumb
            new_mtmd.updates.append(MacfTaskUpdate(
                breadcrumb=breadcrumb,
                description=f"Task resumed via CLI (stale-resume from Cycle {last_cycle})",
                agent="PA"))
            update_task_file(task_id, {"description": task.description_with_updated_mtmd(new_mtmd)})
        append_event("task_resumed", {
            "task_id": str(task_id), "from_cycle": last_cycle, "breadcrumb": breadcrumb})
        _print_stale_resume_banner(task_id, last_cycle, last_ts, cur_cycle)
        return 0

    if task.mtmd:
        from .task.models import MacfTaskUpdate
        import copy
        new_mtmd = copy.deepcopy(task.mtmd)
        new_mtmd.started_breadcrumb = breadcrumb
        desc = (f"Task resumed via CLI (stale-resume from Cycle {stale[0]})"
                if stale else "Task started via CLI")
        new_mtmd.updates.append(MacfTaskUpdate(breadcrumb=breadcrumb, description=desc, agent="PA"))
        new_description = task.description_with_updated_mtmd(new_mtmd)
        update_task_file(task_id, {"status": "in_progress", "description": new_description})
    else:
        update_task_file(task_id, {"status": "in_progress"})

    # Emit task lifecycle event for downstream hooks and proxy integration
    task_type = getattr(task.mtmd, 'task_type', None) if task.mtmd else None
    plan_ca_ref = getattr(task.mtmd, 'plan_ca_ref', None) if task.mtmd else None
    append_event("task_started", {
        "task_id": str(task_id),
        "task_type": task_type,
        "breadcrumb": breadcrumb,
        "plan_ca_ref": plan_ca_ref,
    })

    # Auto-inject policies mapped to this task type via manifest
    injected_policies = []
    if task_type:
        from .utils.manifest import get_policies_for_task_type
        from .utils import find_policy_file
        policies = get_policies_for_task_type(task_type)
        for policy_name in policies:
            policy_path = find_policy_file(policy_name)
            if policy_path:
                append_event("policy_injection_activated", {
                    "policy_name": policy_name,
                    "policy_path": str(policy_path),
                    "source": "task_type_auto",
                    "task_id": str(task_id),
                })
                injected_policies.append(policy_name)

    # Cascade upstream (#115 / GH#212): a phase in_progress under an ancestor
    # still 'pending' makes the tree misreport where work stands — orientation
    # reads the MISSION as "nobody is working this", the wrong direction. Walk the
    # ancestor chain and start any pending ancestor, reporting each so the
    # resumption is visible rather than silent.
    cascaded = []
    if task.mtmd and getattr(task.mtmd, "parent_id", None) and str(task.mtmd.parent_id).lstrip("#") != "000":
        from .task.create import _run_task_start
        try:
            _pid = int(str(task.mtmd.parent_id).lstrip("#"))
        except (ValueError, TypeError):
            _pid = None
        if _pid is not None:
            ancestor = reader.read_task(_pid)
            if ancestor and ancestor.status == "pending":
                # _run_task_start now cascades the full ancestor chain through the
                # shared chokepoint; collect the started ancestors for the report.
                _run_task_start(_pid, _cascaded=cascaded)

    print(f"✅ Task #{task_id} started")
    print(f"   Breadcrumb: {breadcrumb}")
    if cascaded:
        print(f"   ⬆️  Cascade-started {len(cascaded)} pending ancestor(s): "
              + ", ".join(f"#{c}" for c in cascaded))
        print("      (a phase cannot truly be underway while an ancestor reads 'pending')")
    if injected_policies:
        print(f"   Auto-injected policies: {injected_policies}")
    if stale:
        _print_stale_resume_banner(task_id, stale[0], stale[1], stale[2])
    return 0


def cmd_task_pause(args: argparse.Namespace) -> int:
    """Pause work on a task - sets status back to pending."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb
    from .agent_events_log import append_event
    import json

    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    reader = TaskReader()

    # Unhide task file if it was completed (dot-prefixed) — must happen before update
    from .task.reader import unhide_task_file
    if reader.session_path:
        unhide_task_file(reader.session_path, str(task_id))

    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    if task.status == "pending":
        print(f"⚠️  Task #{task_id} is already pending")
        return 0

    breadcrumb = get_breadcrumb()

    if task.mtmd:
        from .task.models import MacfTaskUpdate
        import copy
        new_mtmd = copy.deepcopy(task.mtmd)
        new_mtmd.updates.append(MacfTaskUpdate(breadcrumb=breadcrumb, description="Task paused via CLI", agent="PA"))
        new_description = task.description_with_updated_mtmd(new_mtmd)
        update_task_file(task_id, {"status": "pending", "description": new_description})
    else:
        update_task_file(task_id, {"status": "pending"})

    # Emit task lifecycle event for downstream hooks and proxy integration
    task_type = getattr(task.mtmd, 'task_type', None) if task.mtmd else None
    append_event("task_paused", {
        "task_id": str(task_id),
        "task_type": task_type,
        "breadcrumb": breadcrumb,
    })

    # Clear policy injections that were activated for this task type
    cleared_policies = []
    if task_type:
        from .utils.manifest import get_policies_for_task_type
        policies = get_policies_for_task_type(task_type)
        for policy_name in policies:
            append_event("policy_injection_cleared", {
                "policy_name": policy_name,
                "reason": f"task_paused:{task_id}",
            })
            cleared_policies.append(policy_name)

    print(f"✅ Task #{task_id} paused")
    print(f"   Breadcrumb: {breadcrumb}")
    if cleared_policies:
        print(f"   Cleared policies: {cleared_policies}")
    return 0


def cmd_task_reconcile(args: argparse.Namespace) -> int:
    """Union-merge forked CC per-session task DBs into the home store.

    Dry-run by default; pass --apply to write. Newest-mtime-per-id wins, so no
    task ever worked on is dropped.
    """
    from .task.reconcile import reconcile

    try:
        report = reconcile(apply=args.apply)
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1

    print(f"Sources ({len(report['sources'])} project session dirs):")
    for name in report["sources"]:
        print(f"  {name}")
    print(f"Merged {report['merged_count']} unique task ids -> {report['dest']}")
    if report["missing_status"]:
        print(f"⚠️  {len(report['missing_status'])} task(s) missing a status field: "
              f"{', '.join(report['missing_status'])}")
    if report["applied"]:
        print(f"✅ Wrote {report['merged_count']} task files to the home store.")
    else:
        print("DRY RUN — re-run with --apply to write.")
    return 0


def cmd_task_note(args: argparse.Namespace) -> int:
    """Add a note to a task's updates list (type='note').

    With --idea, formats the note as ``<MODE>: 💡 <text>`` (current work mode
    prefix + lightbulb glyph) and increments ``custom.ideas_captured`` on the
    nearest active scoped SPRINT or PLAY_TIME task.
    """
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb
    from .task.models import MacfTaskUpdate
    import copy

    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    if not task.mtmd:
        print(f"⚠️  Task #{task_id} has no MTMD - cannot add note")
        return 1

    breadcrumb = get_breadcrumb()
    is_idea = bool(getattr(args, "idea", False))

    # Format message: --idea prefixes with current work mode + 💡
    if is_idea:
        try:
            from .modes.detection import get_current_work_mode, detect_active_modes
            session_id = get_current_session_id()
            token_info = get_token_info(session_id)
            current_wm = get_current_work_mode(detect_active_modes(session_id, token_info))
        except (OSError, ValueError, ImportError) as e:
            print(f"⚠️ MACF: work mode detection failed: {e}", file=sys.stderr)
            current_wm = None
        prefix = f"{current_wm}: " if current_wm else ""
        message = f"{prefix}💡 {args.message}"
    else:
        message = args.message

    # DRY refactor (BUG #1067 follow-up): use add_task_note helper instead of
    # inlining the read-modify-write MacfTaskUpdate pattern. Helper handles
    # deepcopy + append + write_task_file. Returns False on any failure.
    from .task.reader import add_task_note
    if not add_task_note(str(task_id), message, agent="PA", note_type="note", breadcrumb=breadcrumb):
        print(f"❌ Failed to add note to task #{task_id}")
        return 1

    print(f"📝 Note added to task #{task_id}")
    print(f"   {message}")
    print(f"   Breadcrumb: {breadcrumb}")

    # --idea: increment ideas_captured on active scoped SPRINT or PLAY_TIME
    if is_idea:
        try:
            from .task.sprint_gate import get_sprint_play_time_in_scope
            autowork = get_sprint_play_time_in_scope()
            target = autowork.get("sprint_task") or autowork.get("play_time_task")
            if target and target.mtmd and target.mtmd.custom is not None:
                target_reader = TaskReader()
                stored = target_reader.read_task(target.id)
                if stored and stored.mtmd:
                    new_custom = dict(stored.mtmd.custom or {})
                    new_custom["ideas_captured"] = int(new_custom.get("ideas_captured", 0)) + 1
                    new_target_mtmd = copy.deepcopy(stored.mtmd)
                    new_target_mtmd.custom = new_custom
                    update_task_file(str(target.id), {
                        "description": stored.description_with_updated_mtmd(new_target_mtmd),
                    })
                    print(f"   💡 ideas_captured++ on #{target.id} (now {new_custom['ideas_captured']})")
        except (ImportError, OSError, ValueError) as e:
            print(f"⚠️  ideas_captured increment failed: {e}", file=sys.stderr)

    return 0


def cmd_task_block(args: argparse.Namespace) -> int:
    """Add blocking relationship: task blocks another task."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    try:
        task_id = _parse_task_id_arg(args.task_id)
        target_id = _parse_task_id_arg(args.target_id)
    except ValueError:
        print(f"❌ Invalid task ID(s): {args.task_id} or {args.target_id}")
        return 1

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    # Verify target exists
    target = reader.read_task(target_id)
    if not target:
        print(f"❌ Target task #{target_id} not found")
        return 1

    # Get current blocks array
    current_blocks = task.blocks or []
    if str(target_id) in current_blocks or target_id in current_blocks:
        print(f"⚠️  Task #{task_id} already blocks #{target_id}")
        return 0

    # Add to blocks
    new_blocks = current_blocks + [str(target_id)]
    update_task_file(task_id, {"blocks": new_blocks})

    print(f"✅ Task #{task_id} now blocks #{target_id}")
    print(f"   Breadcrumb: {get_breadcrumb()}")
    return 0


def cmd_task_unblock(args: argparse.Namespace) -> int:
    """Remove blocking relationship."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    try:
        task_id = _parse_task_id_arg(args.task_id)
        target_id = _parse_task_id_arg(args.target_id)
    except ValueError:
        print(f"❌ Invalid task ID(s): {args.task_id} or {args.target_id}")
        return 1

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    current_blocks = task.blocks or []
    # Check both str and int forms
    if str(target_id) not in current_blocks and target_id not in current_blocks:
        print(f"⚠️  Task #{task_id} does not block #{target_id}")
        return 0

    # Remove from blocks
    new_blocks = [b for b in current_blocks if str(b) != str(target_id)]
    update_task_file(task_id, {"blocks": new_blocks})

    print(f"✅ Task #{task_id} no longer blocks #{target_id}")
    print(f"   Breadcrumb: {get_breadcrumb()}")
    return 0


def cmd_task_blocked_by(args: argparse.Namespace) -> int:
    """Add blocked-by relationship: task is blocked by another task."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    try:
        task_id = _parse_task_id_arg(args.task_id)
        blocker_id = _parse_task_id_arg(args.blocker_id)
    except ValueError:
        print(f"❌ Invalid task ID(s): {args.task_id} or {args.blocker_id}")
        return 1

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    # Verify blocker exists
    blocker = reader.read_task(blocker_id)
    if not blocker:
        print(f"❌ Blocker task #{blocker_id} not found")
        return 1

    # Get current blockedBy array (Python attr is blocked_by, JSON field is blockedBy)
    current_blocked_by = task.blocked_by or []
    if str(blocker_id) in current_blocked_by or blocker_id in current_blocked_by:
        print(f"⚠️  Task #{task_id} is already blocked by #{blocker_id}")
        return 0

    # Add to blockedBy
    new_blocked_by = current_blocked_by + [str(blocker_id)]
    update_task_file(task_id, {"blockedBy": new_blocked_by})

    print(f"✅ Task #{task_id} is now blocked by #{blocker_id}")
    print(f"   Breadcrumb: {get_breadcrumb()}")
    return 0


def cmd_task_unblocked_by(args: argparse.Namespace) -> int:
    """Remove blocked-by relationship."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb

    try:
        task_id = _parse_task_id_arg(args.task_id)
        blocker_id = _parse_task_id_arg(args.blocker_id)
    except ValueError:
        print(f"❌ Invalid task ID(s): {args.task_id} or {args.blocker_id}")
        return 1

    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    current_blocked_by = task.blocked_by or []
    if str(blocker_id) not in current_blocked_by and blocker_id not in current_blocked_by:
        print(f"⚠️  Task #{task_id} is not blocked by #{blocker_id}")
        return 0

    # Remove from blockedBy (JSON field name)
    new_blocked_by = [b for b in current_blocked_by if str(b) != str(blocker_id)]
    update_task_file(task_id, {"blockedBy": new_blocked_by})

    print(f"✅ Task #{task_id} is no longer blocked by #{blocker_id}")
    print(f"   Breadcrumb: {get_breadcrumb()}")
    return 0


# -------- Task Scope Commands --------


def cmd_task_scope_set(args: argparse.Namespace) -> int:
    """Scope tasks for AUTO_MODE boundary enforcement."""
    from .task import TaskReader
    from .task.scope import set_scope
    from .utils.breadcrumbs import get_breadcrumb

    reader = TaskReader()
    raw_ids = [tid.lstrip('#') for tid in args.task_ids]

    # Expand parent tasks to their pending/in_progress children.
    # Dedup at both the outer (raw_ids) and inner (children) levels so callers
    # who pass a parent ID alongside its already-known children don't see
    # duplicate entries or inflated counts in the success output.
    expanded = []
    for tid in raw_ids:
        task = reader.read_task(tid)
        if not task:
            print(f"⚠️  Task #{tid} not found, skipping")
            continue
        if tid not in expanded:
            expanded.append(tid)
        # Check for children
        all_tasks = reader.read_all_tasks()
        children = [t for t in all_tasks if t.mtmd and str(getattr(t.mtmd, "parent_id", "")) == tid]
        if children:
            for child in children:
                if child.status in ("pending", "in_progress"):
                    child_id = child.id
                    if child_id not in expanded:
                        expanded.append(child_id)

    if not expanded:
        print("❌ No valid tasks to scope")
        return 1

    result = set_scope(expanded, parent_expanded=len(expanded) > len(raw_ids),
                       expanded_from=raw_ids[0] if len(raw_ids) == 1 else None)

    if result["success"]:
        print(f"✅ Scoped {len(expanded)} task(s):")
        for tid in result["tasks_scoped"]:
            task = reader.read_task(tid)
            subject = task.subject if task else f"Task #{tid}"
            is_parent = tid in raw_ids
            marker = "📌" if is_parent else "  └─"
            print(f"   {marker} #{tid} {subject}")
        if result["parent_expanded"]:
            print(f"   (parent #{result['expanded_from']} expanded to {len(expanded) - len(raw_ids)} children)")
        print(f"   Breadcrumb: {get_breadcrumb()}")

        # Show full scope state after adding
        from .task.scope import get_active_scope
        all_scoped = get_active_scope()
        if all_scoped:
            active = [t for t in all_scoped if t["status"] == "active"]
            inactive = [t for t in all_scoped if t["status"] == "inactive"]
            if inactive:  # Only show full list if there are prior scoped tasks
                print(f"\n📋 Full Scope ({len(active)} active, {len(inactive)} inactive):")
                for t in active:
                    print(f"   👀 #{t['id']} {t['subject']}")
                for t in inactive:
                    print(f"   ✅ #{t['id']} {t['subject']}")
        # Timer: emit scope_timer event if --timer provided
        timer_minutes = getattr(args, 'timer', 0)
        if timer_minutes > 0:
            # Guard: block setting new timer when one is already active
            from .task.scope import get_active_timer
            existing_timer = get_active_timer()
            if existing_timer.get("active"):
                print(f"⏱️  Timer already active ({existing_timer['remaining_min']} min remaining). "
                      f"Cannot set new timer without user authorization.")
                return 1

            import time
            from .agent_events_log import append_event
            timer_end = time.time() + (timer_minutes * 60)
            append_event("scope_timer_set", {
                "timer_minutes": timer_minutes,
                "timer_end_epoch": timer_end,
                "session_id": get_current_session_id(),
            })
            print(f"   ⏱️  Timer: {timer_minutes} min (until {time.strftime('%H:%M', time.localtime(timer_end))})")
    else:
        print("❌ Failed to activate scope")
        return 1
    return 0


def cmd_task_scope_show(args: argparse.Namespace) -> int:
    """Display current scope with status."""
    from .task.scope import get_active_scope, find_orphaned_scope_tasks

    tasks = get_active_scope()
    orphans = find_orphaned_scope_tasks()
    if not tasks and not orphans:
        print("No active scope.")
        return 0

    active = [t for t in tasks if t["status"] == "active"]
    paused = [t for t in tasks if t["status"] == "paused"]
    inactive = [t for t in tasks if t["status"] == "inactive"]

    if not tasks:
        print(f"No active scope (event state empty).")
        print(f"⚠️  {len(orphans)} task(s) carry stale scope_status with no event history (orphans):")
        for tid in sorted(orphans, key=lambda x: int(x) if x.isdigit() else 0):
            print(f"   🧟 #{tid} (mtmd: {orphans[tid]})")
        print("   Heal with: macf_tools task scope remove <ids>  (drop from scope)")
        print("         or:  macf_tools task scope pause <ids> --justification ...  (adopt as paused)")
        return 0

    summary_parts = [f"{len(active)} active"]
    if paused:
        summary_parts.append(f"{len(paused)} paused")
    summary_parts.append(f"{len(inactive)} inactive")
    print(f"📋 Task Scope ({', '.join(summary_parts)})")
    for t in active:
        print(f"   👀 #{t['id']} {t['subject']}")
    for t in paused:
        print(f"   ⏸️  #{t['id']} {t['subject']}")
    for t in inactive:
        print(f"   ✅ #{t['id']} {t['subject']}")
    if orphans:
        print(f"⚠️  {len(orphans)} task(s) carry stale scope_status with no event history (orphans):")
        for tid in sorted(orphans, key=lambda x: int(x) if x.isdigit() else 0):
            print(f"   🧟 #{tid} (mtmd: {orphans[tid]})")
        print("   Heal with: macf_tools task scope remove <ids>  (drop from scope)")
        print("         or:  macf_tools task scope pause <ids> --justification ...  (adopt as paused)")
    return 0


def cmd_task_scope_pause(args: argparse.Namespace) -> int:
    """Pause one or more active scoped tasks (BUG #1067).

    Paused tasks remain in scope (visible in `scope show` with ⏸️) but are
    EXCLUDED from the Stop gate. Justification is REQUIRED and recorded as
    a task note for human audit.
    """
    from .task.scope import pause_scoped_tasks
    from .utils.breadcrumbs import get_breadcrumb

    if not args.justification or not args.justification.strip():
        print("❌ --justification REASON is REQUIRED to pause scoped tasks.")
        print("   Pause is a structural exit (carry-through with audit trail), not a convenience.")
        print("   Examples of acceptable justifications:")
        print("     'Pinned MISSION — cycle-spanning by design; carry through compaction'")
        print("     'Deferred to user — needs network/disk decision (model pulls)'")
        print("     'Multi-cycle implementation work — design draft delivered, awaits user sign-off'")
        return 1

    # --all: pause every currently-ACTIVE scoped task. This is the non-hanging,
    # reversible, audited full-gate quiet — the USER_REMOTE-safe alternative to the
    # destructive `scope clear` (which is denied while remote). Pause keeps the
    # tasks in scope and reversible via `scope unpause`.
    if getattr(args, "all", False):
        if args.task_ids:
            print("❌ Pass task IDs OR --all, not both.")
            return 1
        from .task.scope import get_active_scope
        raw_ids = [str(t["id"]) for t in get_active_scope() if t.get("status") == "active"]
        if not raw_ids:
            print("✅ No active scoped tasks to pause.")
            return 0
    elif not args.task_ids:
        print("❌ Provide task IDs, or --all to pause every active scoped task.")
        return 1
    else:
        raw_ids = [tid.lstrip('#') for tid in args.task_ids]

    result = pause_scoped_tasks(
        raw_ids,
        justification=args.justification.strip(),
        session_id=get_current_session_id(),
    )

    if result["paused_ids"]:
        print(f"⏸️  Paused {len(result['paused_ids'])} task(s):")
        for tid in result["paused_ids"]:
            print(f"   ⏸️  #{tid}")
        print(f"   Justification: {args.justification.strip()}")
        print(f"   Breadcrumb: {get_breadcrumb()}")
    if result["skipped_ids"]:
        print(f"⚠️  Skipped {len(result['skipped_ids'])} task(s):")
        for entry in result["skipped_ids"]:
            print(f"   - #{entry['id']}: {entry['reason']}")
    if not result["paused_ids"] and not result["skipped_ids"]:
        print("❌ No tasks pausable (none in scope?)")
        return 1
    return 0 if result["success"] else 1


def cmd_task_scope_unpause(args: argparse.Namespace) -> int:
    """Unpause paused scoped tasks (BUG #1067)."""
    from .task.scope import unpause_scoped_tasks
    from .utils.breadcrumbs import get_breadcrumb

    raw_ids = [tid.lstrip('#') for tid in args.task_ids]
    result = unpause_scoped_tasks(raw_ids, session_id=get_current_session_id())

    if result["unpaused_ids"]:
        print(f"▶️  Unpaused {len(result['unpaused_ids'])} task(s):")
        for tid in result["unpaused_ids"]:
            print(f"   👀 #{tid}")
        print(f"   Breadcrumb: {get_breadcrumb()}")
    if result["skipped_ids"]:
        print(f"⚠️  Skipped {len(result['skipped_ids'])} task(s):")
        for entry in result["skipped_ids"]:
            print(f"   - #{entry['id']}: {entry['reason']}")
    if not result["unpaused_ids"] and not result["skipped_ids"]:
        print("❌ No tasks unpausable (none paused in scope?)")
        return 1
    return 0 if result["success"] else 1


def cmd_task_scope_add(args: argparse.Namespace) -> int:
    """Incrementally add tasks to scope as active (BUG #1067).

    Distinct from `scope set` which replaces the entire scope. `scope add`
    appends without affecting existing scoped tasks.
    """
    from .task.scope import add_to_scope
    from .utils.breadcrumbs import get_breadcrumb

    raw_ids = [tid.lstrip('#') for tid in args.task_ids]
    result = add_to_scope(raw_ids, session_id=get_current_session_id())

    if result["added_ids"]:
        print(f"➕ Added {len(result['added_ids'])} task(s) to scope:")
        for tid in result["added_ids"]:
            print(f"   👀 #{tid}")
        print(f"   Breadcrumb: {get_breadcrumb()}")
    if result["skipped_ids"]:
        print(f"⚠️  Skipped {len(result['skipped_ids'])} task(s):")
        for entry in result["skipped_ids"]:
            print(f"   - #{entry['id']}: {entry['reason']}")
    if not result["added_ids"] and not result["skipped_ids"]:
        print("❌ No tasks to add")
        return 1
    return 0 if result["success"] else 1


def cmd_task_scope_remove(args: argparse.Namespace) -> int:
    """Incrementally remove tasks from scope (BUG #1067).

    Distinct from `complete_scoped_task` (marks 'inactive') and
    `pause_scoped_tasks` (marks 'paused' with justification).
    `scope remove` drops tasks entirely without status transition.
    """
    from .task.scope import remove_from_scope
    from .utils.breadcrumbs import get_breadcrumb

    raw_ids = [tid.lstrip('#') for tid in args.task_ids]
    result = remove_from_scope(raw_ids, session_id=get_current_session_id())

    if result["removed_ids"]:
        print(f"➖ Removed {len(result['removed_ids'])} task(s) from scope:")
        for tid in result["removed_ids"]:
            print(f"   ↩️  #{tid}")
        print(f"   Breadcrumb: {get_breadcrumb()}")
    if result["skipped_ids"]:
        print(f"⚠️  Skipped {len(result['skipped_ids'])} task(s):")
        for entry in result["skipped_ids"]:
            print(f"   - #{entry['id']}: {entry['reason']}")
    if not result["removed_ids"] and not result["skipped_ids"]:
        print("❌ No tasks removable")
        return 1
    return 0 if result["success"] else 1


def cmd_task_scope_clear(args: argparse.Namespace) -> int:
    """Remove all tasks from scope."""
    from .task.scope import clear_scope
    from .utils.breadcrumbs import get_breadcrumb

    result = clear_scope()

    if result["success"]:
        print("✅ Scope cleared:")
        for tid in result["active_removed"]:
            print(f"   ↩️  #{tid} (was active)")
        for tid in result["inactive_removed"]:
            print(f"   ↩️  #{tid} (was inactive)")
        if not result["active_removed"] and not result["inactive_removed"]:
            print("   (scope was already empty)")
        print(f"   Breadcrumb: {get_breadcrumb()}")
    else:
        print("❌ Failed to clear scope")
        return 1
    return 0


def cmd_task_scope_check(args: argparse.Namespace) -> int:
    """Check active scope count (JSON output for Stop hook)."""
    import json as json_mod
    from .task.scope import get_scope_check

    result = get_scope_check()
    print(json_mod.dumps(result, indent=2))
    return 0


def _commit_landed_in_merged_pr(repo_slug: str, commits: list) -> bool:
    """Return True if any of `commits` is in a merged PR on the default branch.

    Used by the GH_ISSUE close-out path to decide whether to close the upstream
    issue or just post a status comment (closes GH issue #79). When the fix
    is still on a feature branch awaiting PR review/merge, the upstream issue
    should remain OPEN so the GitHub issue tracker reflects the actual fix-in-flight
    status; only after PR merge does closure become semantically correct.

    Conservative on API failure: returns False so the close path is skipped
    (the issue stays open) — better to under-close than to incorrectly close
    an issue whose fix hasn't landed.
    """
    if not commits:
        return False
    import subprocess as _subprocess
    for sha in commits:
        try:
            result = _subprocess.run(
                ["gh", "pr", "list",
                 "--repo", repo_slug,
                 "--search", sha,
                 "--state", "merged",
                 "--limit", "1",
                 "--json", "number"],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip() not in ("", "[]"):
                return True
        except (FileNotFoundError, _subprocess.TimeoutExpired):
            continue
    return False


def _public_attribution_enabled() -> bool:
    """Read opsec.public_attribution from {agent_home}/.maceff/config.json.

    Gates the calling-card footer on public GitHub close-out comments
    (GH issue #156). Default False: operators running agents in proxy mode
    (public artifacts authored under the operator's identity) must not leak
    agent monikers, id fragments, or breadcrumbs to public surfaces.

    🚨 OPSEC: setting this to true publishes the agent's calling card and
    breadcrumb on public issues. The pair is only traceable by the agent's
    operator (it links public artifacts back to private task/transcript
    context) and is innocuous to third parties, but it still reveals that an
    agent produced the work and gives it a stable public identity. Enable it
    deliberately — e.g. for dogfooding agents contributing to MacEff itself —
    never by default.
    """
    try:
        from .utils.paths import find_agent_home
        config_file = find_agent_home() / ".maceff" / "config.json"
        if config_file.exists():
            data = json.loads(config_file.read_text())
            opsec = data.get("opsec", {}) or {}
            return bool(opsec.get("public_attribution", False))
    except (OSError, ValueError) as e:
        print(f"⚠️ MACF: opsec config read failed: {e}", file=sys.stderr)
    return False


def _gh_issue_closeout(task_id: int, mtmd, args, breadcrumb: str) -> None:
    """Post close-out comment and close GitHub issue.

    The --report is the agent's conscious, professional contribution — passed
    through as the comment body. Automation adds structured metadata (commits,
    verification) and — only when opsec.public_attribution is enabled — a
    calling card footer for agent traceability (GH issue #156).

    Closure semantics (GH issue #79): the upstream issue is closed ONLY if at
    least one of the supplied --commit hashes is verifiably in a merged PR on
    the repo's default branch. Otherwise the comment is posted (so reviewers
    see the close-out report and the linked commits) but the issue stays
    OPEN — closure waits for the PR to merge, where GitHub's natural
    "closes #N" auto-close path takes over.

    Failures are warnings, not errors — the task is already marked complete.
    """
    import subprocess as _subprocess

    custom = mtmd.custom
    gh_owner = custom.get("gh_owner")
    gh_repo = custom.get("gh_repo")
    gh_issue_number = custom.get("gh_issue_number")

    if not (gh_owner and gh_repo and gh_issue_number):
        print("   ⚠️  Missing GitHub metadata — skipping GitHub closeout")
        return

    repo_slug = f"{gh_owner}/{gh_repo}"

    # Compose close-out comment:
    # - Report body (agent's conscious contribution)
    # - Structured commits and verification
    # - Calling card footer (opt-in via opsec.public_attribution — issue #156)
    comment_lines = ["## Close-out Report", ""]
    comment_lines.append(args.report)

    if args.commit:
        comment_lines.append("")
        comment_lines.append("**Commits:**")
        for c in args.commit:
            comment_lines.append(f"- [`{c[:8]}`](https://github.com/{repo_slug}/commit/{c})")

    if args.verified:
        comment_lines.append("")
        comment_lines.append(f"**Verification:** {args.verified}")

    if _public_attribution_enabled():
        # Resolve agent identity for calling card
        try:
            from .utils.identity import get_agent_identity
            agent_name = get_agent_identity()
        except (ImportError, OSError) as e:
            print(f"⚠️ MACF: agent identity resolution failed: {e}", file=sys.stderr)
            agent_name = "unknown"
        comment_lines.append("")
        comment_lines.append("---")
        comment_lines.append(f"*[{agent_name}: task#{task_id} {breadcrumb}]*")

    comment_body = "\n".join(comment_lines)

    # Post comment
    try:
        comment_result = _subprocess.run(
            ["gh", "issue", "comment", str(gh_issue_number),
             "--repo", repo_slug,
             "--body", comment_body],
            capture_output=True, text=True, timeout=15
        )
        if comment_result.returncode == 0:
            print(f"   📝 Close-out comment posted to {repo_slug}#{gh_issue_number}")
        else:
            print(f"   ⚠️  Failed to post comment: {comment_result.stderr.strip()}")
    except FileNotFoundError:
        print("   ⚠️  gh CLI not found — skipping GitHub comment")
    except _subprocess.TimeoutExpired:
        print("   ⚠️  gh CLI timed out — skipping GitHub comment")

    # Status-aware closure (GH issue #79): close the upstream issue only when
    # the fix has actually landed (at least one --commit hash is in a merged
    # PR). Otherwise leave it open and let the natural PR-merge auto-close
    # path take over once the user reviews+merges the PR.
    fix_landed = _commit_landed_in_merged_pr(repo_slug, list(args.commit or []))
    if not fix_landed:
        print(
            f"   ⏳ Issue {repo_slug}#{gh_issue_number} left OPEN — "
            f"no merged PR found for the supplied commit(s). "
            f"GitHub will auto-close on PR merge if the PR body links the issue."
        )
        return

    # Close issue
    try:
        close_result = _subprocess.run(
            ["gh", "issue", "close", str(gh_issue_number),
             "--repo", repo_slug,
             "--reason", "completed"],
            capture_output=True, text=True, timeout=15
        )
        if close_result.returncode == 0:
            print(f"   🔒 Issue {repo_slug}#{gh_issue_number} closed")
        else:
            stderr = close_result.stderr.strip()
            if "already closed" in stderr.lower():
                print(f"   ℹ️  Issue {repo_slug}#{gh_issue_number} already closed")
            else:
                print(f"   ⚠️  Failed to close issue: {stderr}")
    except FileNotFoundError:
        print("   ⚠️  gh CLI not found — skipping issue close")
    except _subprocess.TimeoutExpired:
        print("   ⚠️  gh CLI timed out — skipping issue close")


def _find_sprint_log(plan_ca_ref: str):
    """Return Path to sprint_log.md given plan_ca_ref directory, or None."""
    from pathlib import Path
    p = Path(plan_ca_ref)
    # plan_ca_ref may be a file (roadmap.md) or a directory
    folder = p if p.is_dir() else p.parent
    candidate = folder / "sprint_log.md"
    return candidate if candidate.exists() else None


def _find_play_log(plan_ca_ref: str):
    """Return Path to play_log.md given plan_ca_ref directory, or None."""
    from pathlib import Path
    p = Path(plan_ca_ref)
    folder = p if p.is_dir() else p.parent
    candidate = folder / "play_log.md"
    return candidate if candidate.exists() else None


def _write_final_synthesis(log_path, aggregate: str, open_children) -> None:
    """Append aggregate stats under ## Final Synthesis in log_path.

    Creates the section if absent; never overwrites content above it.
    """
    from pathlib import Path
    text = Path(log_path).read_text(encoding="utf-8")
    section_header = "## Final Synthesis"
    if section_header in text:
        # Insert after the header line, before any existing content in the section
        idx = text.index(section_header) + len(section_header)
        insertion = f"\n\n{aggregate}"
        if open_children:
            child_ids = ", ".join(f"#{c.id}" for c in open_children)
            insertion += f"\n\nNote: completed with open child tasks: {child_ids}"
        new_text = text[:idx] + insertion + text[idx:]
    else:
        new_text = text.rstrip("\n") + f"\n\n{section_header}\n\n{aggregate}\n"
        if open_children:
            child_ids = ", ".join(f"#{c.id}" for c in open_children)
            new_text += f"\nNote: completed with open child tasks: {child_ids}\n"
    Path(log_path).write_text(new_text, encoding="utf-8")


def _gh_pr_find_linked_issue_tasks(linked_issues: list, repo_slug: str) -> list:
    """Find local, still-open GH_ISSUE tasks whose gh_issue_number is in
    `linked_issues` for the same repo. Returns list of (task_id:int, task)."""
    if not linked_issues:
        return []
    from .task import TaskReader
    wanted = {int(n) for n in linked_issues}
    out = []
    for t in TaskReader().read_all_tasks():
        mtmd = getattr(t, "mtmd", None)
        if not mtmd or getattr(mtmd, "task_type", None) != "GH_ISSUE":
            continue
        if getattr(t, "status", None) in ("completed", "archived"):
            continue
        c = getattr(mtmd, "custom", {}) or {}
        if c.get("gh_issue_number") in wanted and f"{c.get('gh_owner')}/{c.get('gh_repo')}" == repo_slug:
            out.append((int(t.id), t))
    return out


def _gh_pr_closeout(task_id: int, mtmd, args, breadcrumb: str) -> str:
    """GH_PR review/merge closeout: ground-truth the terminal outcome, post a
    review close-out comment, and (with --cascade) complete linked GH_ISSUE tasks.

    Returns the outcome string (MERGED / CLOSED_UNMERGED / OPEN / UNKNOWN).
    The PR's live state is queried at completion time — NOT read from the
    cached `gh_state` stored at creation (that field goes stale). Failures are
    warnings, not errors — the task is already marked complete.
    """
    import subprocess as _subprocess
    import json as _json

    custom = mtmd.custom or {}
    gh_owner = custom.get("gh_owner")
    gh_repo = custom.get("gh_repo")
    gh_pr_number = custom.get("gh_pr_number")
    linked_issues = custom.get("linked_issues", []) or []

    if not (gh_owner and gh_repo and gh_pr_number):
        print("   ⚠️  Missing GitHub PR metadata — skipping GH_PR closeout")
        return "UNKNOWN"

    repo_slug = f"{gh_owner}/{gh_repo}"

    # Ground-truth outcome from GitHub (live), plus the merge commit and CI
    # conclusion (statusCheckRollup folded into the same call — no extra request).
    outcome, merge_commit, ci_red = "OPEN", None, False
    try:
        r = _subprocess.run(
            ["gh", "pr", "view", str(gh_pr_number), "--repo", repo_slug,
             "--json", "state,mergeCommit,statusCheckRollup"],
            capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            d = _json.loads(r.stdout)
            state = d.get("state", "OPEN")
            outcome = "MERGED" if state == "MERGED" else ("CLOSED_UNMERGED" if state == "CLOSED" else "OPEN")
            merge_commit = (d.get("mergeCommit") or {}).get("oid")
            _bad = {"FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED", "ERROR", "STARTUP_FAILURE"}
            for chk in (d.get("statusCheckRollup") or []):
                if (chk.get("conclusion") or chk.get("state") or "").upper() in _bad:
                    ci_red = True
                    break
        else:
            outcome = "UNKNOWN"
    except (FileNotFoundError, _subprocess.TimeoutExpired, ValueError) as e:
        print(f"   ⚠️  Could not fetch PR state ({e}) — outcome UNKNOWN")
        outcome = "UNKNOWN"

    print(f"   🔀 PR outcome: {outcome}" + (f" (merge {merge_commit[:8]})" if merge_commit else ""))

    # CI gate awareness: a MERGED PR whose checks are red is a red-CI merge —
    # surface it loudly with the resolution path (task_management.md §2.3.3).
    if ci_red and outcome == "MERGED":
        print("   🚨 CI GATE VIOLATION: this PR merged with FAILING CI checks.")
        print("      Resolution: create a fix task documenting the failure (root cause + test/code fix),")
        print("      resolve it, and re-verify CI green. Never merge red — see task_management.md §2.3.3.")
        print("      Platform backstop: enable branch protection required_status_checks on the target branch.")

    # Post a review close-out comment (agent's report + outcome). The calling
    # card footer is opt-in via opsec.public_attribution (issue #156).
    comment_lines = [
        "## Review Close-out", "", args.report, "",
        f"**Outcome:** {outcome}",
    ]
    if getattr(args, "verified", None):
        comment_lines.append(f"**Verification:** {args.verified}")
    if _public_attribution_enabled():
        try:
            from .utils.identity import get_agent_identity
            agent_name = get_agent_identity()
        except (ImportError, OSError):
            agent_name = "unknown"
        comment_lines += ["", "---", f"*[{agent_name}: task#{task_id} {breadcrumb}]*"]
    comment = "\n".join(comment_lines)
    try:
        cr = _subprocess.run(
            ["gh", "pr", "comment", str(gh_pr_number), "--repo", repo_slug, "--body", comment],
            capture_output=True, text=True, timeout=15)
        if cr.returncode == 0:
            print(f"   📝 Close-out comment posted to {repo_slug}#{gh_pr_number}")
        else:
            print(f"   ⚠️  Failed to post PR comment: {cr.stderr.strip()}")
    except (FileNotFoundError, _subprocess.TimeoutExpired):
        print("   ⚠️  gh CLI unavailable — skipping PR comment")

    # Cascade to linked GH_ISSUE tasks (only when merged).
    linked_tasks = _gh_pr_find_linked_issue_tasks(linked_issues, repo_slug) if outcome == "MERGED" else []
    if linked_tasks:
        ids = ", ".join(f"#{tid}" for tid, _ in linked_tasks)
        if getattr(args, "cascade", False) and merge_commit:
            print(f"   🔗 Cascade: completing linked GH_ISSUE tasks {ids}")
            for tid, _t in linked_tasks:
                cc = _subprocess.run(
                    ["macf_tools", "task", "complete", str(tid),
                     "--report", f"Auto-completed via merged PR #{gh_pr_number} (GH_PR task #{task_id}).",
                     "--commit", merge_commit,
                     "--verified", f"Fixed by merged PR #{gh_pr_number}"],
                    capture_output=True, text=True, timeout=30)
                if cc.returncode == 0:
                    print(f"      ✅ #{tid} completed")
                else:
                    print(f"      ⚠️  #{tid} cascade failed: {(cc.stderr or cc.stdout).strip()[:120]}")
        else:
            hint = "pass --cascade to auto-complete" if merge_commit else "merge commit unavailable; complete manually"
            print(f"   🔗 Linked GH_ISSUE tasks ({hint}): {ids}")

    return outcome


def cmd_task_complete(args: argparse.Namespace) -> int:
    """Mark task complete with mandatory report, breadcrumb, and status change."""
    from .task import TaskReader, update_task_file
    from .utils.breadcrumbs import get_breadcrumb
    import json

    # Parse task ID
    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    # Timer guard: block completion but fire Markov recommender at this gate point
    try:
        from .task.scope import is_task_timer_blocked
        timer_check = is_task_timer_blocked(task_id)
        if timer_check["blocked"]:
            remaining = timer_check["remaining_min"]
            print(f"⏱️  Timer gate: {remaining} min remaining — this is the last scoped task, completion deferred until timer expires.")
            print(f"   Follow the Markov recommender for productive continuation work:\n")
            # Fire the Markov recommender
            try:
                from .modes import (
                    detect_active_modes, get_current_work_mode,
                    sample_next_work_mode, format_recommendation,
                )
                session_id = get_current_session_id()
                token_info = get_token_info(session_id)
                modes = detect_active_modes(session_id, token_info)
                current_wm = get_current_work_mode(modes)
                op_modes = {m for m in modes if m in ("AUTO_MODE", "USER_IDLE", "QUIET_MODE", "LOW_CONTEXT")}
                selected, dist = sample_next_work_mode(current_wm, op_modes)
                print(format_recommendation(current_wm, selected, dist, "maceff"))
            except Exception as e:
                import sys as _sys
                print(f"⚠️ Markov recommender failed: {e}", file=_sys.stderr)
            return 0  # Not an error — gate point, not failure
    except (ImportError, OSError) as e:
        import sys as _sys
        print(f"⚠️ MACF: Timer check failed (non-blocking): {e}", file=_sys.stderr)

    # Check report is provided
    if not args.report:
        print("❌ Completion report is MANDATORY")
        print()
        print("   The --report flag documents work done, difficulties, future work, and git status.")
        print()
        print("   For format guidance:")
        print("   macf_tools policy navigate task_management")
        print("   (See section on Completion Protocol)")
        print()
        print("   Example:")
        print('   macf_tools task complete #67 --report "Implemented X. No difficulties. Committed: abc1234"')
        return 1

    # Read task
    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    if task.status == "completed":
        print(f"⚠️  Task #{task_id} is already completed")
        return 1

    # Guard: completing a parent while its children are still open puts a done
    # parent over unfinished work — an inconsistency the tree reader can't trust.
    # In AUTO_MODE (or with --force) warn and proceed; otherwise refuse and point
    # at the fix. Mirror of cascade-start, which guards the start direction.
    _open_children = [
        (t.id, t.status) for t in reader.read_all_tasks()
        if t.mtmd and str(getattr(t.mtmd, "parent_id", "") or "").lstrip("#") == str(task_id)
        and t.status in ("pending", "in_progress")
    ]
    if _open_children:
        try:
            from .modes import detect_auto_mode
            _auto, _ = detect_auto_mode(get_current_session_id())
        except (ImportError, OSError, ValueError) as e:
            # Not knowing the mode is survivable — the warning below still
            # prints and the operator still decides. Swallowing the reason is
            # not: it would hide a broken mode subsystem behind a completion
            # that merely looks conservative.
            print(f"⚠️ MACF: could not resolve mode for completion gate: {e}",
                  file=sys.stderr)
            _auto = False
        _listing = ", ".join(f"#{cid}({st})" for cid, st in _open_children[:8])
        print(f"⚠️  Task #{task_id} has {len(_open_children)} incomplete child task(s): {_listing}")
        if _auto or getattr(args, "force", False):
            print("   Completing anyway (AUTO_MODE / --force) — those children remain open.")
        else:
            print("   A parent completing over open children misrepresents the tree.")
            print("   Complete, reparent, or pause the children first — or re-run with --force.")
            return 1

    # Type-specific completion gate: GH_ISSUE
    task_type = getattr(task.mtmd, 'task_type', None) if task.mtmd else None
    if task_type == "GH_ISSUE":
        missing = []
        if not args.commit:
            missing.append("--commit HASH")
        if not args.verified:
            missing.append('--verified "description of verification method"')
        if missing:
            print(f"GH_ISSUE #{task_id} requires structured closeout before completion.")
            print()
            print("To understand requirements, read the \"GH_ISSUE Closeout\" section:")
            print("  macf_tools policy navigate task_management")
            print('  → Look for: "How does GH_ISSUE closeout work?"')
            print()
            print(f"Missing: {', '.join(missing)}")
            return 1

    # Type-specific completion logic: SPRINT
    if task_type == "SPRINT":
        # 1. Scope-gate check (parallel to Stop hook scope gate)
        #    Per autonomous_sprint.md §3.3.2: --force with incomplete scope requires --justification
        _justification = getattr(args, 'justification', None)
        try:
            from .task.sprint_gate import get_sprint_play_time_in_scope, emit_scope_nag
            _scope_info = get_sprint_play_time_in_scope()
            _open_scoped = _scope_info.get("open_children", [])

            # Also include direct-child tasks not yet in scope (legacy semantics)
            from .task import TaskReader as _TR
            _all_tasks = _TR().read_all_tasks()
            _open_children = [
                t for t in _all_tasks
                if str(getattr(t, 'parent_id', None)) == str(task_id)
                and getattr(t, 'status', None) not in ("completed", "archived")
            ]
            _open_child_ids_in_scope = {str(c["id"]) for c in _open_scoped}
            _open_children_extra = [
                t for t in _open_children
                if str(t.id) not in _open_child_ids_in_scope
            ]

            _has_incomplete_scope = bool(_open_scoped) or bool(_open_children_extra)

            if _has_incomplete_scope:
                if not getattr(args, 'force', False):
                    # No --force: hard-fail with scope-gate message
                    if _open_scoped:
                        _nag = emit_scope_nag(task, _open_scoped)
                        print(f"❌ SPRINT scope gate:")
                        print(_nag)
                    if _open_children_extra:
                        _ids = ", ".join(f"#{t.id}" for t in _open_children_extra)
                        print(f"❌ SPRINT has {len(_open_children_extra)} open child task(s) not in scope: {_ids}")
                    print("\n   Complete remaining tasks first, OR use --force --justification REASON.")
                    print("   Carry-through-compaction is the proper end-of-cycle exit (see autonomous_sprint.md §3.3.3).")
                    return 1
                elif not _justification:
                    # --force WITHOUT --justification: parallel gate per §3.3.2 — hard-fail
                    print(f"❌ Force-complete bypass requires --justification REASON")
                    if _open_scoped:
                        _nag = emit_scope_nag(task, _open_scoped)
                        print(_nag)
                    if _open_children_extra:
                        _ids = ", ".join(f"#{t.id}" for t in _open_children_extra)
                        print(f"   + {len(_open_children_extra)} open child task(s) not in scope: {_ids}")
                    print("\n   Per autonomous_sprint.md §3.3.2:")
                    print("     macf_tools task complete <id> --force --justification \"<structural reason>\"")
                    print("   Acceptable: pinned MISSIONs intentionally cycle-spanning; carryover from prior sprint.")
                    print("   NOT acceptable: 'cycle is closing' / 'AUTO_MODE so I have authority' / 'main work done'.")
                    print("   Carry-through-compaction is the proper end-of-cycle exit (see §3.3.3).")
                    return 1
                else:
                    # --force WITH --justification: log warning, prepend justification, proceed
                    import sys as _sys
                    _all_open = list(_open_scoped) + [
                        {"id": t.id, "subject": t.subject} for t in _open_children_extra
                    ]
                    _ids = ", ".join(f"#{c['id']}" for c in _all_open)
                    print(f"⚠️  Force-completing SPRINT with {len(_all_open)} open scoped/child task(s): {_ids}",
                          file=_sys.stderr)
                    print(f"⚠️  Justification: {_justification}", file=_sys.stderr)
                    # Prepend justification marker to report (will be visible in completion_report)
                    _just_marker = f"[FORCE-COMPLETE JUSTIFICATION: {_justification}]"
                    if args.report:
                        args.report = f"{_just_marker} | {args.report}"
                    else:
                        args.report = _just_marker
        except (ImportError, OSError) as e:
            import sys as _sys
            print(f"⚠️ MACF: scope-gate check failed (non-blocking): {e}", file=_sys.stderr)

        # 2. Auto-aggregate completion report from custom fields
        _custom = getattr(task.mtmd, 'custom', {}) if task.mtmd else {}
        _goal = _custom.get("goal", "")
        _sp = _custom.get("scoped_progress", {})
        _completed_n = _sp.get("completed", 0) if isinstance(_sp, dict) else 0
        _total_n = _sp.get("total", 0) if isinstance(_sp, dict) else 0
        _ideas = _custom.get("ideas_captured", 0)
        _learnings = _custom.get("learnings_curated", 0)
        _aggregate = (
            f'Goal: "{_goal}". Completed {_completed_n}/{_total_n} children. '
            f'{_ideas} ideas captured. {_learnings} learnings curated.'
        )
        if args.report:
            args.report = args.report + " | " + _aggregate
        else:
            args.report = _aggregate

        # 3. Auto-populate sprint_log.md Final Synthesis section
        _plan_ref = getattr(task.mtmd, 'plan_ca_ref', None) if task.mtmd else None
        if _plan_ref:
            try:
                _log_path = _find_sprint_log(_plan_ref)
                if _log_path:
                    _write_final_synthesis(_log_path, _aggregate, _open_children if '_open_children' in dir() else [])
            except (OSError, ValueError) as e:
                import sys as _sys
                print(f"⚠️ MACF: sprint_log update failed (non-blocking): {e}", file=_sys.stderr)

        # 4. Prompt about ideas in task notes
        _updates = getattr(task.mtmd, 'updates', []) if task.mtmd else []
        _idea_notes = [u for u in _updates if '💡 ' in getattr(u, 'description', '')]
        if _idea_notes:
            print(f"💡 {len(_idea_notes)} ideas in task notes — promote them to formal idea CAs after sprint with macf_tools idea create.")

        # 5. Auto-clear SPRINT work mode if it's currently active
        # The SPRINT mode locks Markov; once the SPRINT task ends we want
        # mode rotation back. Emit a work_mode_change clearing event.
        try:
            from .modes.detection import detect_active_modes, get_current_work_mode
            session_id = get_current_session_id()
            token_info = get_token_info(session_id)
            current_wm = get_current_work_mode(detect_active_modes(session_id, token_info))
            if current_wm == "SPRINT":
                append_event("work_mode_change", {"mode": None})
                print("🧹 SPRINT work mode cleared (Markov re-enabled)")
        except (OSError, ValueError, ImportError) as e:
            import sys as _sys
            print(f"⚠️ MACF: SPRINT mode auto-clear failed (non-blocking): {e}", file=_sys.stderr)

    # Type-specific completion logic: PLAY_TIME
    elif task_type == "PLAY_TIME":
        import time as _time
        _custom = getattr(task.mtmd, 'custom', {}) if task.mtmd else {}

        # 1. Timer expiry check (warn, don't block)
        _expires_at = _custom.get("timer_expires_at")
        if _expires_at is not None and not getattr(args, 'force', False):
            _remaining_sec = int(_expires_at) - int(_time.time())
            if _remaining_sec > 0:
                _remaining_min = round(_remaining_sec / 60, 1)
                print(f"⚠️  PLAY_TIME timer hasn't expired ({_remaining_min} min remaining). Completing anyway. Use --force to suppress this warning.")

        # 2. Auto-aggregate
        _goal = _custom.get("goal", "")
        _timer_min = _custom.get("timer_minutes", 0)
        _mode_trans = _custom.get("mode_transitions", [])
        _markov = _custom.get("markov_gates", [])
        _ideas = _custom.get("ideas_captured", 0)
        _learnings = _custom.get("learnings_curated", 0)
        _modes_used = len(_mode_trans) + 1
        _aggregate = (
            f'Goal: "{_goal}". Timer: {_timer_min}min. '
            f'Modes used: {_modes_used}. Markov gates: {len(_markov)}. '
            f'{_ideas} ideas, {_learnings} learnings.'
        )
        if args.report:
            args.report = args.report + " | " + _aggregate
        else:
            args.report = _aggregate

        # 3. Auto-populate play_log.md Final Synthesis section
        _plan_ref = getattr(task.mtmd, 'plan_ca_ref', None) if task.mtmd else None
        if _plan_ref:
            try:
                _log_path = _find_play_log(_plan_ref)
                if _log_path:
                    _write_final_synthesis(_log_path, _aggregate, [])
            except (OSError, ValueError) as e:
                import sys as _sys
                print(f"⚠️ MACF: play_log update failed (non-blocking): {e}", file=_sys.stderr)

        # 4. Prompt about ideas in task notes
        _updates = getattr(task.mtmd, 'updates', []) if task.mtmd else []
        _idea_notes = [u for u in _updates if '💡 ' in getattr(u, 'description', '')]
        if _idea_notes:
            print(f"💡 {len(_idea_notes)} ideas in task notes — promote them to formal idea CAs after sprint with macf_tools idea create.")

        # 5. Clear the scope timer so subsequent Stop hook fires don't gate
        # on a now-completed PLAY_TIME's expiration window. Targeted event:
        # only timer state is cleared; scope set itself stays intact.
        try:
            append_event("scope_timer_cleared", {"task_id": str(task_id), "reason": "play_time_completed"})
            print("⏹️  PLAY_TIME timer cleared")
        except (OSError, ValueError) as e:
            import sys as _sys
            print(f"⚠️ MACF: scope_timer_cleared event emit failed (non-blocking): {e}", file=_sys.stderr)

    # Generate breadcrumb
    breadcrumb = get_breadcrumb()

    # Update MTMD with completion_breadcrumb and completion_report
    if task.mtmd:
        from .task.models import MacfTaskUpdate
        import copy
        new_mtmd = copy.deepcopy(task.mtmd)
        new_mtmd.completion_breadcrumb = breadcrumb
        new_mtmd.completion_report = args.report
        new_mtmd.updates.append(MacfTaskUpdate(
            breadcrumb=breadcrumb,
            description="Task completed via CLI",
            agent="PA"
        ))
    else:
        from .task.models import MacfTaskMetaData, MacfTaskUpdate
        new_mtmd = MacfTaskMetaData(
            completion_breadcrumb=breadcrumb,
            completion_report=args.report,
            updates=[MacfTaskUpdate(
                breadcrumb=breadcrumb,
                description="Task completed via CLI",
                agent="PA"
            )]
        )

    # Store GH_ISSUE closeout fields in MTMD custom dict
    if task_type == "GH_ISSUE" and (args.commit or args.verified):
        if args.commit:
            new_mtmd.custom["closeout_commits"] = args.commit
        if args.verified:
            new_mtmd.custom["closeout_verified"] = args.verified

    # Embed updated MTMD in description
    new_description = task.description_with_updated_mtmd(new_mtmd)

    # Update task file with status and description
    success = update_task_file(task_id, {
        "status": "completed",
        "description": new_description
    })

    if success:
        # Hide completed task file from CC's native scanner (dot-prefix).
        # hide_task_file guards this itself — it returns early for a non-CC
        # store — so the call is safe everywhere and only the report is gated.
        from .task.reader import hide_task_file, _is_cc_session_dir
        if reader.session_path:
            hide_task_file(reader.session_path, str(task_id))
            if _is_cc_session_dir(reader.session_path):
                print(f"   📁 Hidden from CC scanner (.{task_id}.json)")

        # Emit task lifecycle event for downstream hooks and proxy integration
        plan_ca_ref = getattr(new_mtmd, 'plan_ca_ref', None)
        append_event("task_completed", {
            "task_id": str(task_id),
            "task_type": task_type,
            "breadcrumb": breadcrumb,
            "plan_ca_ref": plan_ca_ref,
            "report": args.report,
        })

        # Auto-complete scoped task if it's in the active scope
        try:
            from .task.scope import complete_scoped_task
            scope_result = complete_scoped_task(str(task_id))
            if scope_result.get("success"):
                remaining = scope_result.get("remaining_active", "?")
                print(f"   👀→✅ Scoped task completed ({remaining} remaining)")
        except (ImportError, OSError, KeyError) as e:
            print(f"⚠️ MACF: scoped task completion check failed for #{task_id} (non-blocking): {e}", file=sys.stderr)

        # Completing a scope OWNER (SPRINT / PLAY_TIME) must release its scoped
        # members from the gate. complete_scoped_task above only marks the
        # owner itself inactive; without this, the owner's pending children stay
        # 'active' forever — `remaining` never reaches 0, the auto-clear never
        # fires, and the Stop-hook scope gate nags long after the sprint is done.
        # This runs in the shared success path, so it covers force-completion too:
        # a force-completed sprint releases its children (they return to the tree
        # at their real status; they are not fake-completed).
        if task_type in ("SPRINT", "PLAY_TIME"):
            try:
                from .task.scope import get_scope_check, clear_scope
                if get_scope_check().get("active_count", 0) > 0:
                    clr = clear_scope()
                    if clr.get("success"):
                        swept = len(set(
                            clr.get("active_removed", [])
                            + clr.get("inactive_removed", [])
                            + clr.get("orphans_swept", [])
                        ))
                        print(f"   🧹 Scope owner completed — released {swept} task(s) from the scope gate")
            except (ImportError, OSError, KeyError) as e:
                print(f"⚠️ MACF: scope release on owner completion failed for #{task_id} (non-blocking): {e}", file=sys.stderr)

        print(f"✅ Task #{task_id} marked complete")
        print(f"   Breadcrumb: {breadcrumb}")
        print(f"   Report: {args.report[:80]}{'...' if len(args.report) > 80 else ''}")
        if task_type == "GH_ISSUE":
            if args.commit:
                print(f"   Commits: {', '.join(args.commit)}")
            if args.verified:
                print(f"   Verified: {args.verified[:80]}{'...' if len(args.verified) > 80 else ''}")

            # GitHub integration: post close-out comment and close issue
            _gh_issue_closeout(task_id, new_mtmd, args, breadcrumb)

        if task_type == "GH_PR":
            # Review/merge closeout: ground-truth outcome + cascade to linked issues
            _gh_pr_closeout(task_id, new_mtmd, args, breadcrumb)

        return 0
    else:
        print(f"❌ Failed to update task #{task_id}")
        return 1


def cmd_task_metadata_validate(args: argparse.Namespace) -> int:
    """Validate task MTMD against schema requirements."""
    from .task import TaskReader

    # Parse task ID
    try:
        task_id = _parse_task_id_arg(args.task_id)
    except ValueError:
        print(f"❌ Invalid task ID: {args.task_id}")
        return 1

    # Read task
    reader = TaskReader()
    task = reader.read_task(task_id)
    if not task:
        print(f"❌ Task #{task_id} not found")
        return 1

    print(f"🔍 Validating task #{task_id}: {task.subject[:50]}...")
    print()

    errors = []
    warnings = []

    # Check MTMD presence
    if not task.mtmd:
        errors.append("No MTMD block found in description")
        print("❌ VALIDATION FAILED")
        print()
        for err in errors:
            print(f"   ❌ {err}")
        return 1

    mtmd = task.mtmd

    # Detect task type from subject
    subject = task.subject
    task_type = "regular"
    if "🗺️" in subject or "MISSION" in subject:
        task_type = "MISSION"
    elif "🧪" in subject or "EXPERIMENT" in subject:
        task_type = "EXPERIMENT"
    elif "↩️" in subject or "DETOUR" in subject:
        task_type = "DETOUR"
    elif "📋" in subject:
        task_type = "PHASE"
    elif "🐛" in subject or "BUG" in subject:
        task_type = "BUG"
    elif "🔧" in subject:
        task_type = "TASK"

    print(f"   Type: {task_type}")
    print()

    # Required for ALL tasks
    if not mtmd.creation_breadcrumb:
        errors.append("Missing required field: creation_breadcrumb")
    if not mtmd.created_cycle:
        warnings.append("Missing recommended field: created_cycle")
    if not mtmd.created_by:
        warnings.append("Missing recommended field: created_by")

    # Required for MISSION/EXPERIMENT/DETOUR
    if task_type in ("MISSION", "EXPERIMENT", "DETOUR"):
        if not mtmd.plan_ca_ref:
            errors.append(f"{task_type} requires plan_ca_ref (roadmap/protocol path)")

    # Required for PHASE tasks (children)
    if task_type == "PHASE":
        if not mtmd.parent_id:
            errors.append("PHASE task requires parent_id")

    # Check parent reference in subject matches MTMD
    if "[^#" in subject:
        import re
        match = re.search(r'\[\^#(\d+)\]', subject)
        if match:
            subject_parent = int(match.group(1))
            if mtmd.parent_id and mtmd.parent_id != subject_parent:
                errors.append(f"Subject parent [^#{subject_parent}] doesn't match MTMD parent_id={mtmd.parent_id}")
            elif not mtmd.parent_id:
                warnings.append(f"Subject has parent [^#{subject_parent}] but MTMD missing parent_id")

    # Report results
    if errors:
        print("❌ VALIDATION FAILED")
        print()
        for err in errors:
            print(f"   ❌ {err}")
        for warn in warnings:
            print(f"   ⚠️  {warn}")
        return 1
    elif warnings:
        print("⚠️  VALIDATION PASSED (with warnings)")
        print()
        for warn in warnings:
            print(f"   ⚠️  {warn}")
        return 0
    else:
        print("✅ VALIDATION PASSED")
        return 0


def _systemd_unit_for_pid(pid: int) -> "str | None":
    """Name of the systemd unit owning `pid`, or None.

    Read from /proc/<pid>/cgroup, where the unit appears verbatim in the path.
    That is a plain file read, unlike parsing `systemctl` output whose format
    varies by version — and it returns None on any non-systemd host (macOS has
    no /proc at all), so callers get a clean "not applicable".

    Matters because the remedy differs entirely: a unit-owned port must be
    handled with `systemctl --user stop`, and killing the PID just feeds a
    Restart=always loop.
    """
    import re
    try:
        with open(f"/proc/{pid}/cgroup") as f:
            content = f.read()
    except (OSError, ValueError):
        return None
    # A cgroup path nests several .service components, e.g.
    #   /user.slice/user-1000.slice/user@1000.service/app.slice/macf-proxy.service
    # The leaf is the unit actually running the process; the `user@NNNN.service`
    # ancestor is the session manager, and naming it would send the operator to
    # `systemctl status user@1000.service` — true, useless, and confusing.
    units = re.findall(r'([A-Za-z0-9_@.\-]+\.service)', content)
    for unit in reversed(units):
        if not re.fullmatch(r'user@\d+\.service', unit):
            return unit
    return units[-1] if units else None


def _check_port_available(port: int, host: str = "127.0.0.1") -> tuple:
    """Check if port is available. Returns (available: bool, owner_pid: int|None)."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind((host, port))
            return True, None
        except OSError:
            pass
    # Port in use — try to find owner via lsof
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            owner_pid = int(result.stdout.strip().split("\n")[0])
            return False, owner_pid
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return False, None


def _amail_config() -> dict:
    """Resolve amail settings: agent address and broker socket.

    Environment wins over the config file so a test or a one-off can retarget
    without editing agent state.
    """
    from macf.utils.paths import find_agent_home
    cfg = {}
    home = find_agent_home()
    if home:
        p = Path(home) / ".maceff" / "amail.json"
        if p.exists():
            try:
                cfg = json.loads(p.read_text())
            except (OSError, ValueError):
                cfg = {}
            # json.loads succeeds on any JSON value, not just an object. A file
            # containing `[]`, `"x"`, `7`, `null` or `true` parses fine and then
            # has no .setdefault, crashing every amail subcommand with an
            # AttributeError traceback. Fail-closed either way — but a clean
            # "not configured" message is diagnosable and a traceback is not.
            if not isinstance(cfg, dict):
                cfg = {}
    cfg.setdefault("domain", os.environ.get("MACF_AMAIL_DOMAIN", ""))
    cfg.setdefault("socket", os.environ.get("MACF_AMAIL_SOCKET", "/run/amail/broker.sock"))
    cfg.setdefault("handoff", os.environ.get("MACF_AMAIL_HANDOFF", "/var/lib/amail/handoff"))
    cfg.setdefault("agent", os.environ.get("MACEFF_AGENT_NAME", ""))
    # The agent's OWN private signing key. It lives in the agent's home, not the
    # broker's: a signing key proves authorship and reaches nothing, so holding
    # one does not give a compromised agent any reach it did not have. Keeping it
    # out of the broker is what lets a signature mean something to a party that
    # does not trust the broker.
    cfg.setdefault("signing_key", os.environ.get(
        "MACF_AMAIL_SIGNING_KEY",
        str(Path(home) / ".maceff" / "amail_signing_key.pem") if home else ""))
    for k in ("domain", "socket", "agent"):
        if os.environ.get(f"MACF_AMAIL_{k.upper()}"):
            cfg[k] = os.environ[f"MACF_AMAIL_{k.upper()}"]
    cfg["home"] = str(home) if home else ""
    return cfg


#: Control characters that must never reach a terminal verbatim.
#:
#: C0 except tab and newline, DEL, and the C1 block: ESC is the one that
#: matters, since it opens the sequences that reposition the cursor, recolour,
#: or clear the screen.
#:
#: Plus the Unicode bidirectional overrides and isolates (U+202A–U+202E,
#: U+2066–U+2069). These drive no cursor and forge no escape sequence, so the
#: first version passed them — but they reorder how text RENDERS, which is the
#: Trojan-source technique, and the whole reason this function exists is that a
#: reader must be able to trust what the screen says. Reordering the display is
#: a quieter way of achieving what cursor control achieves loudly.
#:
#: Written as escapes, not as the characters themselves: a literal bidi override
#: inside this source file would reorder the very line that defines it.
_TERM_UNSAFE = re.compile("[\\x00-\\x08\\x0b-\\x1f\\x7f-\\x9f]")


def _escape_codepoint(ch: str) -> str:
    """\\xNN for a byte-range code point, \\uNNNN above it.

    Formatting U+202E as \\x202e would be ambiguous — it reads as \\x20 followed
    by the literal text '2e'. The escape has to be unambiguous or the rendering
    is itself a small forgery.
    """
    n = ord(ch)
    return f"\\x{n:02x}" if n <= 0xFF else f"\\u{n:04x}"


def _term_safe(value: object) -> str:
    """Render untrusted message content without handing the terminal control.

    Message bodies come from a correspondent and are printed to the operator's
    terminal. An escape sequence in a body can overwrite what was already
    displayed — including the trust labelling above it — so a message could
    claim to be from someone it is not by simply redrawing the screen. Headers
    are already sanitised by _hdr() at serialisation; the body deliberately is
    not, because a body may legitimately contain anything. That makes the
    RENDERER the correct place to neutralise it.

    Escaped rather than stripped: the reader should be able to see that the
    message contained control characters, since that is itself informative.
    """
    s = "" if value is None else str(value)
    # Fast path in C for the overwhelmingly common case: plain ASCII with no
    # control characters. Everything else is inspected one code point at a time,
    # which a 256 KiB body can afford once, at read time, on a human's request.
    if s.isascii() and not _TERM_UNSAFE.search(s):
        return s
    out = []
    for ch in s:
        # Cf is the CATEGORY, not a hand-kept list. The first version enumerated
        # the bidi overrides and isolates and shipped — and round 8 found it
        # still passed LRM/RLM (which are bidi controls too), every zero-width
        # character, the word joiner, the soft hyphen, and the Unicode tag block,
        # which can smuggle entirely invisible text into a rendered sender label.
        # Enumerating members of a category is how you get a list that is right
        # on the day it is written; naming the category is how you get one that
        # stays right.
        if _TERM_UNSAFE.match(ch) or (not ch.isascii()
                                      and unicodedata.category(ch) == "Cf"):
            out.append(_escape_codepoint(ch))
        else:
            out.append(ch)
    return "".join(out)


#: Rendered trust labels. Deliberately NOT derived from anything in the message
#: body — see _trust_badge.
_TRUST_BADGES = {
    "attested": "✅ [signed by this correspondent]",
    "domain_auth": "🔶 [domain authenticated — sender NOT proven]",
    "unverified": "❔ [unverified origin]",
    "suspect": "🚨 [SUSPECT — authentication failed]",
    None: "❔ [no classification recorded]",
}


def _trust_badge(message) -> str:
    """The trust label, rendered FROM STORED METADATA and never from the body.

    THIS IS THE RULE THAT MAKES THE LABEL WORTH ANYTHING. An attacker's most
    direct answer to a trust banner is to type one into their message. If the
    renderer took its label from message content, a forged badge would appear
    beside the real one, in the same style, with the same words — and the label
    would raise confidence in exactly the messages it exists to lower it for.

    So the badge comes from `message.trust`, which the broker mints and a sender
    can never set, and the body is separately neutralised by _term_safe() so it
    cannot redraw the badge that was already printed.

    An unrecognised value renders as unrecognised rather than falling through to
    something reassuring. A classification this build does not understand is not
    a reason for confidence.
    """
    value = getattr(message, "trust", None)
    return _TRUST_BADGES.get(value, f"❔ [unrecognised classification: {_term_safe(value)}]")


def cmd_amail_keygen(args: argparse.Namespace) -> int:
    """Generate this agent's authorship signing key and print its public half."""
    from macf.amail import SigningError, generate_keypair

    cfg = _amail_config()
    target = Path(args.path) if args.path else Path(cfg.get("signing_key") or "")
    if not str(target):
        print("❌ cannot determine where to write the key; pass --path")
        return 1
    if target.exists():
        # Never silently replace one: overwriting invalidates every signature
        # this correspondent has already published, and doing it by accident is
        # indistinguishable from doing it maliciously.
        print(f"❌ a signing key already exists at {target}.")
        print("   Refusing to overwrite it — that would invalidate every signature")
        print("   you have published. Move it aside deliberately if you mean to rotate.")
        return 1
    try:
        public = generate_keypair(target)
    except (SigningError, OSError) as e:
        print(f"❌ could not generate a signing key: {e}")
        return 1
    print(f"✅ signing key written to {target} (mode 600)")
    print("\nGive your correspondents this public key so they can verify you:\n")
    print(f"    {public}\n")
    print("In their contact list, as an entry for your address:")
    print(f'    {{"address": "{cfg.get("agent","<you>")}@{cfg.get("domain","<domain>")}", '
          f'"key": "{public}"}}')
    print("\nKeep the private key where it is. It proves authorship and reaches")
    print("nothing — the broker never holds it, which is what lets your signature")
    print("mean something to someone who does not trust the broker.")
    return 0


def cmd_amail_send(args: argparse.Namespace) -> int:
    """Submit a message to the broker.

    The broker decides whether it may be sent. This command never delivers
    directly and never falls back to another transport when the broker is
    unreachable — that would route around the only thing enforcing the contact
    list.
    """
    from macf.amail import Message, submit, BrokerUnavailable

    cfg = _amail_config()
    if not cfg["agent"] or not cfg["domain"]:
        print("❌ amail is not configured: need an agent name and a mail domain.")
        print("   Set MACF_AMAIL_DOMAIN / MACEFF_AGENT_NAME, or write ~/.maceff/amail.json")
        return 1

    body = args.body
    if args.body_file:
        try:
            body = Path(args.body_file).read_text()
        except OSError as e:
            print(f"❌ cannot read --body-file: {e}")
            return 1
        except UnicodeDecodeError:
            # A mail body is text. Saying so beats a traceback whose top frame is
            # a codec the operator never invoked.
            print(f"❌ --body-file {args.body_file} is not valid UTF-8 text.")
            return 1
    if body is None:
        print("❌ nothing to send: pass --body or --body-file")
        return 1

    msg = Message(sender=f"{cfg['agent']}@{cfg['domain']}", to=list(args.to),
                  subject=args.subject or "", body=body)
    if args.reply_to:
        from macf.amail import store
        parent = store.find(Path(cfg["home"]), args.reply_to) if cfg["home"] else None
        if parent is None:
            print(f"❌ no message '{args.reply_to}' in this mailbox to reply to")
            return 1
        msg = parent.reply(sender=msg.sender, body=body, subject=args.subject)
        msg.to = list(args.to) or msg.to

    # SIGN BEFORE SUBMITTING, if this agent has a key.
    #
    # Signing here rather than in the broker is the whole point: the broker holds
    # no private key, so it cannot forge this agent's mail, and a recipient who
    # distrusts the broker can still establish authorship. Absence of a key is
    # not an error — an agent whose correspondents have not asked for signatures
    # has nothing to prove — but a key that exists and CANNOT BE USED is, because
    # sending unsigned when the correspondent expects signed is exactly the shape
    # of an impersonation.
    keypath = Path(cfg["signing_key"]) if cfg.get("signing_key") else None
    if keypath and keypath.exists():
        from macf.amail import SigningError, load_private_key, sign
        try:
            msg.signature = sign(msg, load_private_key(keypath))
        except SigningError as e:
            print(f"❌ cannot sign with {keypath}: {e}")
            print("   Refusing to send unsigned: a correspondent who has your key "
                  "treats unsigned mail as suspect.")
            return 1

    try:
        result = submit(cfg["agent"], msg, Path(cfg["socket"]))
    except BrokerUnavailable as e:
        print(f"❌ {e}")
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    if not result.get("ok"):
        # Refusals are surfaced, never swallowed. An agent that cannot tell a
        # message was refused learns to believe mail was delivered.
        for r in result.get("refused", []):
            print(f"🚫 refused: {r}")
        for f in result.get("failures", []):
            print(f"❌ {f['recipient']}: {f['error']}")
        if result.get("error"):
            print(f"❌ {result['error']}")
        return 1
    for d in result.get("delivered", []):
        print(f"✅ delivered to {d['recipient']} (rung: {d['rung']})")
    print(f"   message-id: {result['message_id']}")
    print(f"   thread-id:  {result['thread_id']}")
    return 0


def cmd_amail_list(args: argparse.Namespace) -> int:
    """List messages in this agent's mailbox.

    The read goes THROUGH the broker, not around it. Importing the store here
    and calling `read_all(home)` — which is what this command used to do — reads
    the mailbox with no audit record, no authorization, and a home taken from
    local config rather than from kernel-established identity. That is the
    bypass the broker exists to prevent, performed by the framework's own CLI.
    """
    from macf.amail import Message, BrokerUnavailable
    from macf.amail.client import list_messages

    cfg = _amail_config()
    try:
        resp = list_messages(Path(cfg["socket"]), thread=args.thread)
    except BrokerUnavailable as e:
        print(f"❌ {e}")
        return 1
    if not resp.get("ok"):
        print(f"❌ {resp.get('error', 'the broker refused the read')}")
        return 1
    msgs = [Message.from_dict(d) for d in resp.get("messages", [])]
    # Pull = ingest then read. The recipient itself executes the custody
    # transfer: mail waiting in the broker's pickup box is moved into the
    # agent's OWN store as the agent, then read directly from it — the
    # filesystem is the access path to the agent's store; the socket only
    # ever reaches the broker's.
    from macf.amail.client import ingest, list_delivered_internet
    internet = []
    if cfg.get("home"):
        box = Path(cfg["handoff"]) / (cfg.get("agent") or "")
        if cfg.get("agent") and box.is_dir():
            ingested = ingest(Path(cfg["home"]), box)
            ok = sum(1 for r in ingested if r.get("ingested"))
            stuck = [r for r in ingested if not r.get("ingested")]
            if ok:
                print(f"📥 ingested {ok} message(s) from the pickup box")
            for r in stuck:
                print(f"⚠️  pickup entry NOT ingested: {r['name']}: {r['reason']}")
        internet = list_delivered_internet(Path(cfg["home"]))
    if args.json:
        print(json.dumps({"messages": [m.to_dict() for m in msgs],
                          "internet": internet}, indent=2))
        return 0
    if not msgs and not internet:
        print("(no messages)")
        return 0
    for m in msgs:
        print(f"{_term_safe(m.date)}  {_term_safe(m.sender)}  {_trust_badge(m)}")
        print(f"    {_term_safe(m.subject)}")
        print(f"    id={_term_safe(m.message_id)} thread={_term_safe(m.thread_id)}"
              + (f" reply-to={_term_safe(m.parent)}" if m.parent else ""))
    # Internet mail: listed FROM THE SIDECAR, never from the raw message —
    # the sidecar is broker-verified provenance; the raw headers are the
    # sender's own claims and get neutralised only at `read` time.
    for item in internet:
        sc = item.get("sidecar", {})
        obs = sc.get("observed", {})
        authz = sc.get("authorization", {})
        marker = "🌐" if item.get("message_present") else "🌐⚠️ (message file missing)"
        print(f"{_term_safe(str(sc.get('received_at', '?')))}  "
              f"{_term_safe(str(obs.get('envelope_from', '?')))}  {marker}")
        print(f"    {_term_safe(str(obs.get('subject', '(no subject)')))}")
        print(f"    sha={_term_safe(str(sc.get('raw_sha256', '?'))[:16])} "
              f"class={_term_safe(str(authz.get('outcome', '?')))}")
    print(f"\n{len(msgs)} bundle message(s), {len(internet)} internet message(s)")
    return 0


def cmd_amail_read(args: argparse.Namespace) -> int:
    """Print one message in full, fetched through the broker.

    See `cmd_amail_list` on why this does not import the store.
    """
    from macf.amail import Message, BrokerUnavailable
    from macf.amail.client import read_message

    cfg = _amail_config()
    try:
        resp = read_message(args.message_id, Path(cfg["socket"]))
        if not resp.get("ok"):
            # Not a bundle id — the same ref may name an internet delivery
            # (name or content-sha prefix), which is read DIRECTLY: custody
            # transferred at delivery, the filesystem is its access path.
            from macf.amail.client import read_delivered_internet
            found = read_delivered_internet(Path(cfg["home"]), args.message_id) \
                if cfg.get("home") else None
            if found is not None:
                raw, sc = found
                if args.json:
                    print(json.dumps({"sidecar": sc,
                                      "raw": raw.decode("utf-8", "replace")},
                                     indent=2))
                    return 0
                # Provenance FIRST, from the broker-written sidecar; the raw
                # mail below is the sender's material, neutralised so it can
                # neither redraw the badge nor escape the terminal.
                authz = sc.get("authorization", {})
                print(f"🌐 internet mail  class={_term_safe(str(authz.get('outcome', '?')))}"
                      f"  reason={_term_safe(str(authz.get('reason', '?')))}")
                print(f"sha256={_term_safe(str(sc.get('raw_sha256', '?')))}")
                print(_term_safe(raw.decode("utf-8", "replace")))
                return 0
    except BrokerUnavailable as e:
        print(f"❌ {e}")
        return 1
    if not resp.get("ok"):
        print(f"❌ {resp.get('error', 'no such message')}")
        return 1
    m = Message.from_dict(resp["message"])
    if args.json:
        print(json.dumps(m.to_dict(), indent=2))
        return 0
    # The badge is printed from stored metadata BEFORE the message, and the
    # message body is neutralised so it cannot redraw what was already shown.
    # Both halves are needed: a label the body can forge is decorative, and a
    # label the body can erase is worse.
    print(_trust_badge(m))
    print(_term_safe(m.serialize()))
    return 0


def cmd_amail_status(args: argparse.Namespace) -> int:
    """Report whether amail is usable, and say precisely what is missing if not."""
    import socket as _socket
    from macf.amail import store

    cfg = _amail_config()
    sock = Path(cfg["socket"])
    reachable = False
    if sock.exists():
        try:
            s = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            s.settimeout(2.0)
            s.connect(str(sock))
            s.close()
            reachable = True
        except OSError:
            reachable = False
    box = store.maildir_for(Path(cfg["home"])) if cfg["home"] else None
    # The COUNT comes through the broker, like every other read. Counting by
    # `store.read_all(home)` is still reading the mailbox, and a diagnostic is
    # not exempt from the property it is reporting on. When the broker is down
    # the honest answer is that the count is unknown — because when the broker
    # is down the mail genuinely is not readable, and a number here would be
    # asserting otherwise.
    counts = None  # None means "not known", which is not the same as zero
    if reachable:
        from macf.amail.client import status as _status, BrokerUnavailable
        try:
            _resp = _status(sock)
            if _resp.get("ok"):
                counts = {k: _resp.get(k) for k in
                          ("messages", "internet", "quarantined")}
        except (BrokerUnavailable, ValueError) as e:
            print(f"⚠️ MACF: status read failed (counts unknown): {e}",
                  file=sys.stderr)
    info = {
        "agent": cfg["agent"] or None,
        "address": f"{cfg['agent']}@{cfg['domain']}" if cfg["agent"] and cfg["domain"] else None,
        "socket": str(sock),
        "broker_reachable": reachable,
        "maildir": str(box) if box else None,
        # The quarantine count is the load-bearing one: an empty inbox and an
        # inbox with three refusals must be distinguishable states.
        "counts": counts,
    }
    if args.json:
        print(json.dumps(info, indent=2))
        return 0 if reachable else 1
    if counts is not None:
        _count_str = (f"{counts['messages']} bundle(s), "
                      f"{counts['internet']} internet, "
                      f"{counts['quarantined']} quarantined")
    else:
        _count_str = "counts unavailable"
    print(f"address:  {info['address'] or '(unconfigured)'}")
    print(f"maildir:  {info['maildir'] or '(unknown)'}  [{_count_str}]")
    print(f"broker:   {'✅ reachable' if reachable else '❌ unreachable'} at {sock}")
    if counts is not None and counts["quarantined"]:
        print(f"⚠️  {counts['quarantined']} message(s) in quarantine — refused "
              f"with reasons attached; the operator can list them broker-side.")
    if not reachable:
        print("\n   Mail cannot be sent without the broker. There is no fallback")
        print("   transport by design — the broker is what enforces the contact list.")
    return 0 if reachable else 1


def cmd_proxy_start(args: argparse.Namespace) -> int:
    """Start the API proxy."""
    try:
        from macf.proxy.server import is_proxy_running, run_proxy, start_proxy_daemon
    except ImportError as e:
        print("⚠️ Proxy requires aiohttp:")
        print("   pip install aiohttp")
        print(f"\nImport error: {e}")
        return 1

    port = getattr(args, 'port', 8019)
    daemonize = getattr(args, 'daemon', False)

    # Port-scoped, deliberately. This check used to be global, so a proxy on ANY
    # port blocked starting one on another — while the unsupported path (running
    # the module directly) started a second instance that silently overwrote the
    # first's pid file. The supported route refused a safe thing; the workaround
    # did an unsafe one.
    if is_proxy_running(port):
        print(f"⚠️  Proxy is already running on port {port}")
        print(f"   Use 'macf_tools proxy stop --port {port}' to stop it first")
        return 1

    # Pre-check port availability (catches zombies without PID files)
    available, owner_pid = _check_port_available(port)
    if not available and not getattr(args, 'force', False):
        unit = _systemd_unit_for_pid(owner_pid) if owner_pid else None
        print(f"❌ Port {port} is already in use", file=sys.stderr)
        if unit:
            # Two start paths for one singleton service. Killing a unit-managed
            # PID just feeds Restart=always: the unit respawns, loses the race
            # for the port, and crash-loops while the old instance keeps
            # answering — supervision that looks healthy but isn't (#161).
            print(f"   Held by PID {owner_pid}, managed by systemd unit '{unit}'", file=sys.stderr)
            print(f"   That service is already supervised — starting a second ad-hoc", file=sys.stderr)
            print(f"   instance would split-brain the port.", file=sys.stderr)
            print(f"   Inspect: systemctl --user status {unit}", file=sys.stderr)
            print(f"   Migrate: systemctl --user stop {unit}   # then start ad-hoc", file=sys.stderr)
            print(f"   Override: macf_tools proxy start --force", file=sys.stderr)
        elif owner_pid:
            print(f"   Held by PID {owner_pid}", file=sys.stderr)
            print(f"   Fix: kill {owner_pid} && macf_tools proxy start --daemon", file=sys.stderr)
        else:
            print(f"   Fix: lsof -i :{port}  # find the process", file=sys.stderr)
            print(f"        kill <PID> && macf_tools proxy start --daemon", file=sys.stderr)
        return 1

    try:
        if daemonize:
            pid = start_proxy_daemon(port=port)
            print(f"✅ Proxy started (PID {pid}) on port {port}")
            print(f"   Activate: ANTHROPIC_BASE_URL=http://localhost:{port} claude")
            return 0
        else:
            print(f"[proxy] Starting on port {port}...", file=sys.stderr)
            run_proxy(port=port)
            return 0
    except Exception as e:
        print(f"❌ Error starting proxy: {e}", file=sys.stderr)
        return 1


def cmd_proxy_stop(args: argparse.Namespace) -> int:
    """Stop the running proxy."""
    try:
        from macf.proxy.server import stop_proxy, is_proxy_running
    except ImportError as e:
        print(f"Import error: {e}")
        return 1

    port = getattr(args, 'port', 8019)

    if not is_proxy_running(port):
        print(f"Proxy is not running on port {port}")
        return 0

    try:
        if stop_proxy(port):
            print(f"✅ Proxy stopped (port {port})")
            return 0
        else:
            print("⚠️  Proxy was not running")
            return 0
    except Exception as e:
        print(f"❌ Error stopping proxy: {e}")
        return 1


def cmd_proxy_status(args: argparse.Namespace) -> int:
    """Show proxy status."""
    try:
        from macf.proxy.server import get_proxy_status
    except ImportError as e:
        print(f"Import error: {e}")
        return 1

    status = get_proxy_status(getattr(args, 'port', 8019))
    json_output = getattr(args, 'json_output', False)

    if json_output:
        print(json.dumps(status, indent=2))
    else:
        running = status.get('running', False)
        owner = status.get('socket_owner_pid')
        if running:
            print(f"✅ Proxy running (PID {status['pid']}, port {status['port']})")
            if owner:
                print(f"   Socket owner: PID {owner}")
            print(f"   Log: {status['log_path']}")
            print(f"   Activate: ANTHROPIC_BASE_URL=http://localhost:{status['port']} claude")
        else:
            print("⭕ Proxy not running")
            if owner:
                # Something answers on the port that we did not start — the
                # split-brain case where "it responds" hides an unsupervised
                # or crash-looping service.
                print(f"   ⚠️  But PID {owner} is listening on port {status['port']}.")
                print(f"      Another start path (systemd unit or ad-hoc daemon) owns the socket.")
                print(f"      Inspect: ss -tlnp | grep {status['port']}   /   systemctl --user status")
            else:
                print("   Start: macf_tools proxy start --daemon")
        if status.get('socket_owner_mismatch'):
            print(f"   ⚠️  Socket owner (PID {owner}) differs from the recorded PID "
                  f"({status['pid']}) — the pidfile is stale or a second instance holds the port.")
    return 0


def cmd_proxy_stats(args: argparse.Namespace) -> int:
    """Show aggregate token/cost statistics."""
    try:
        from macf.proxy.server import get_proxy_stats
    except ImportError as e:
        print(f"Import error: {e}")
        return 1

    stats = get_proxy_stats()
    if "error" in stats:
        print(f"⚠️  {stats['error']}")
        print(f"   Expected at: {stats.get('log_path', 'unknown')}")
        return 1

    print(f"📊 API Proxy Statistics")
    print(f"   Log: {stats['log_path']}")
    print(f"   Requests: {stats['total_requests']}")
    print(f"   Input tokens:  {stats['total_input_tokens']:,}")
    print(f"   Output tokens: {stats['total_output_tokens']:,}")
    print(f"   Cache read:    {stats['total_cache_read']:,}")
    print(f"   Cache create:  {stats['total_cache_creation']:,}")
    print(f"   Avg latency:   {stats['avg_latency_ms']}ms")
    print(f"   Est. cost:     ${stats['estimated_cost_usd']:.4f}")
    if stats.get('models'):
        print(f"   Models: {stats['models']}")
    return 0


def cmd_proxy_log(args: argparse.Namespace) -> int:
    """Show recent API call events."""
    try:
        from macf.proxy.server import get_recent_log
    except ImportError as e:
        print(f"Import error: {e}")
        return 1

    limit = getattr(args, 'limit', 10)
    events = get_recent_log(limit=limit)

    if not events:
        print("No proxy events logged yet")
        return 0

    for event in events:
        etype = event.get("type", "?")
        ts = event.get("ts", 0)
        ts_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S") if ts else "?"

        if etype == "api_request":
            model = event.get("model", "?")
            msgs = event.get("message_count", 0)
            tools = event.get("tool_count", 0)
            sys_chars = event.get("system_prompt_chars", 0)
            print(f"  [{ts_str}] → REQ  model={model}  msgs={msgs}  tools={tools}  sys={sys_chars:,}ch")
        elif etype == "api_response":
            inp = event.get("input_tokens", 0)
            out = event.get("output_tokens", 0)
            lat = event.get("latency_ms", 0)
            stop = event.get("stop_reason", "?")
            cache = event.get("cache_read_input_tokens", 0)
            print(f"  [{ts_str}] ← RESP in={inp:,}  out={out:,}  cache={cache:,}  {lat}ms  stop={stop}")
        else:
            print(f"  [{ts_str}] {json.dumps(event)}")

    return 0


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


def cmd_transcripts_search(args: argparse.Namespace) -> int:
    """Search transcripts by breadcrumb with context window."""
    from .forensics.transcript_search import search_by_breadcrumb, search_all_transcripts
    import json as json_lib

    breadcrumb = args.breadcrumb
    before = args.before
    after = args.after
    output_format = args.format

    if args.search_all:
        window = search_all_transcripts(breadcrumb, before, after)
    else:
        window = search_by_breadcrumb(breadcrumb, before, after)

    if not window:
        print(f"❌ Breadcrumb not found: {breadcrumb}")
        return 1

    if output_format == "json":
        result = {
            "breadcrumb": window.breadcrumb,
            "target_index": window.target_index,
            "total_messages": window.total_messages,
            "transcript_path": window.transcript_path,
            "before": [{"index": m.index, "role": m.role, "content": m.content} for m in window.before],
            "target": {"index": window.target_message.index, "role": window.target_message.role, "content": window.target_message.content},
            "after": [{"index": m.index, "role": m.role, "content": m.content} for m in window.after],
        }
        print(json_lib.dumps(result, indent=2))
    elif output_format == "compact":
        print(f"📍 Found at index {window.target_index}/{window.total_messages} in {window.transcript_path}")
        print(f"   Breadcrumb: {window.breadcrumb}")
        for msg in window.all_messages():
            marker = "→" if msg.index == window.target_index else " "
            role_emoji = "👤" if msg.role == "user" else "🤖"
            preview = msg.content[:80].replace("\n", " ")
            print(f"{marker} [{msg.index}] {role_emoji} {preview}...")
    else:  # full
        print(f"{'='*60}")
        print(f"📍 Breadcrumb Search Results")
        print(f"{'='*60}")
        print(f"Breadcrumb: {window.breadcrumb}")
        print(f"Transcript: {window.transcript_path}")
        print(f"Target Index: {window.target_index} / {window.total_messages}")
        print(f"Window: {before} before, {after} after")
        print(f"{'='*60}")
        print()
        for msg in window.all_messages():
            is_target = msg.index == window.target_index
            marker = "🎯 TARGET" if is_target else ""
            role_emoji = "👤 USER" if msg.role == "user" else "🤖 ASSISTANT"
            border = "=" if is_target else "-"
            print(f"{border*40} [{msg.index}] {role_emoji} {marker}")
            print(msg.content)
            print()

    return 0


def cmd_transcripts_list(args: argparse.Namespace) -> int:
    """List all transcript files."""
    from .forensics.transcript_search import list_all_transcripts
    import json as json_lib

    transcripts = list_all_transcripts()

    if args.json_output:
        print(json_lib.dumps(transcripts, indent=2))
    else:
        print(f"📂 Found {len(transcripts)} transcripts:")
        for path in transcripts:
            print(f"   {path}")

    return 0


# -------- transcript-monitor handlers --------

def _cmd_tm_start(args) -> int:
    from .transcript_monitor.daemon import start_daemon
    return start_daemon(
        foreground=getattr(args, "foreground", False),
        poll_interval=getattr(args, "interval", 1.0),
    )

def _cmd_tm_stop(args) -> int:
    from .transcript_monitor.daemon import stop_daemon
    return stop_daemon()

def _cmd_tm_status(args) -> int:
    from .transcript_monitor.daemon import daemon_status
    return daemon_status()

# -------- auto-restart handlers --------
def _cmd_ar_launch(args):
    from .supervisor import launch_in_terminal
    cmd = [a for a in args.cmd if a != "--"]
    if not cmd:
        print("Usage: macf_tools auto-restart launch -- <command> [args...]")
        return 1
    return launch_in_terminal(cmd, name=args.name, restart_delay=args.delay,
                              terminal=getattr(args, 'terminal', 'auto'),
                              use_tmux=not getattr(args, 'no_tmux', False),
                              session_spec=getattr(args, 'session_id', None),
                              post_start_keys=getattr(args, 'post_start_keys', None),
                              post_start_delay=getattr(args, 'post_start_delay', 18),
                              force=getattr(args, 'force', False))

def _cmd_ar_list(args=None):
    from .supervisor import list_processes
    show_all = getattr(args, 'show_all', False) if args else False
    list_processes(show_all=show_all)
    return 0

def _cmd_ar_restart(args):
    from .supervisor import restart
    restart(args.pid)
    return 0

def _cmd_ar_disable(args):
    from .supervisor import disable
    disable(args.pid)
    return 0

def _cmd_ar_status(args):
    from .supervisor import status
    status(args.pid)
    return 0

def _cmd_ar_kill(args):
    from .supervisor import kill_process
    kill_process(args.pid)
    return 0

def _cmd_ar_send_keys(args):
    from .supervisor import send_keys
    keys = [a for a in args.keys if a != "--"]
    if not keys:
        print("Usage: macf_tools auto-restart send-keys <name|pid> -- <text...>")
        return 1
    return send_keys(args.target, keys, enter=not getattr(args, 'no_enter', False))


def cmd_idea_create(args: argparse.Namespace) -> int:
    """Create a new idea."""
    from .ideas import create_idea
    # Combine repeatable --wiki-link with comma-separated --wiki-links.
    # The ideas module normalizes + dedups, so order-preservation here is
    # mostly cosmetic: repeated flags come first, then the CSV split.
    wiki_links_raw = list(getattr(args, "wiki_link", None) or [])
    wiki_links_csv = getattr(args, "wiki_links", "") or ""
    if wiki_links_csv:
        wiki_links_raw.extend(s for s in wiki_links_csv.split(",") if s.strip())
    result = create_idea(
        title=args.title,
        category=args.category,
        description=args.description,
        sparked_by=args.sparked_by,
        feasibility=getattr(args, "feasibility", "") or "",
        reasoning=args.reasoning,
        hypothesis=args.hypothesis,
        context=args.context,
        wiki_links=wiki_links_raw,
    )
    idea = result["idea"]
    print(f"✅ Idea #{idea['id']:03d} created: {idea['title']}")
    print(f"   Category: {idea['category']}")
    print(f"   Status: {idea['status']}")
    if idea["links"]["wiki_links"]:
        print(f"   Wiki-links: {', '.join(idea['links']['wiki_links'])}")
    print(f"   File: {result['path']}")
    return 0


def cmd_idea_list(args: argparse.Namespace) -> int:
    """List ideas."""
    from .ideas import list_ideas
    items = list_ideas(
        status=getattr(args, "status", None),
        category=getattr(args, "category", None),
    )
    if getattr(args, "json_output", False):
        print(json.dumps([i["idea"] for i in items], indent=2))
        return 0

    if not items:
        print("No ideas found.")
        return 0

    print(f"{'ID':>4}  {'Status':<10}  {'Category':<15}  Title")
    print(f"{'─'*4}  {'─'*10}  {'─'*15}  {'─'*40}")
    for item in items:
        idea = item["idea"]
        status_icon = {"captured": "💡", "exploring": "🔍", "promoted": "🚀", "archived": "📦"}.get(idea["status"], "?")
        print(f"#{idea['id']:03d}  {status_icon} {idea['status']:<9} {idea['category']:<15}  {idea['title'][:50]}")
    print(f"\n{len(items)} idea(s)")
    return 0


def cmd_idea_get(args: argparse.Namespace) -> int:
    """Get idea details."""
    from .ideas import get_idea
    result = get_idea(args.id)
    if not result:
        print(f"Idea #{args.id} not found.")
        return 1
    print(json.dumps(result["idea"], indent=2))
    return 0


def cmd_idea_update(args: argparse.Namespace) -> int:
    """Update idea status, promotion target, or wiki-links."""
    from .ideas import update_idea

    # Same combining rule as `idea create`: repeatable --wiki-link plus
    # comma-separated --wiki-links, merged into one list.
    wiki_links_raw = list(getattr(args, "wiki_link", None) or [])
    wiki_links_csv = getattr(args, "wiki_links", "") or ""
    if wiki_links_csv:
        wiki_links_raw.extend(s for s in wiki_links_csv.split(",") if s.strip())
    remove_raw = list(getattr(args, "remove_wiki_link", None) or [])

    result = update_idea(
        args.id,
        status=getattr(args, "status", None),
        promoted_to=getattr(args, "promoted_to", None),
        wiki_links=wiki_links_raw,
        remove_wiki_links=remove_raw,
    )
    if not result:
        print(f"Idea #{args.id} not found.")
        return 1
    idea = result["idea"]
    print(f"✅ Idea #{idea['id']:03d} updated: status={idea['status']}")
    if idea.get("links", {}).get("promoted_to"):
        print(f"   Promoted to: {idea['links']['promoted_to']}")
    if wiki_links_raw or remove_raw:
        current = idea.get("links", {}).get("wiki_links") or []
        print(f"   Wiki-links: {', '.join(current) if current else '(none)'}")
    return 0


def cmd_idea_archive(args: argparse.Namespace) -> int:
    """Archive an idea."""
    from .ideas import archive_idea
    result = archive_idea(args.id, args.reason)
    if not result:
        print(f"Idea #{args.id} not found.")
        return 1
    print(f"📦 Idea #{args.id:03d} archived: {args.reason}")
    return 0


def cmd_idea_graph(args: argparse.Namespace) -> int:
    """Show ideas-only knowledge graph (wiki-links and relations between ideas)."""
    from .ideas import build_idea_graph, format_graph_cluster
    from .knowledge_web import format_web_tree

    graph = build_idea_graph()
    if not graph["ideas"]:
        print("No ideas found.")
        return 0

    if getattr(args, "json_output", False):
        top5 = sorted(graph["degree"].items(), key=lambda x: -x[1])[:5]
        print(json.dumps({
            **graph["stats"],
            "top5": [{"id": i, "degree": d, "title": graph["ideas"][i].get("title", "")} for i, d in top5],
        }, indent=2))
        return 0

    if getattr(args, "tree", False):
        print(format_web_tree(graph))
    else:
        print(format_graph_cluster(graph))
    return 0


def cmd_knowledge_graph(args: argparse.Namespace) -> int:
    """Show cross-CA knowledge graph (ideas + learnings + checkpoints + reflections + observations + experiments + reports)."""
    from .knowledge_web import (build_knowledge_web, format_web_cluster_cross_ca,
                                format_web_tree)

    kg = build_knowledge_web()
    stats = kg["stats"]

    if getattr(args, "json_output", False):
        print(json.dumps(stats, indent=2))
        return 0

    print(format_web_cluster_cross_ca(kg))
    return 0


def cmd_knowledge_query(args: argparse.Namespace) -> int:
    """Query knowledge graph by concept, node ID, or keyword."""
    from .knowledge_web import query_knowledge_web, format_query_result

    result = query_knowledge_web(args.term)

    # Filter by node class. A checkpoint's claims expire and a learning's do
    # not; a query asking "what do I know about X" wants durable insight, while
    # "which cycle touched X" wants the temporal record. Returning both
    # unlabelled dilutes the first with the second, and the dilution worsens
    # every cycle. See the scholarship policy on node classes and provenance.
    node_class = getattr(args, "node_class", None)
    if node_class:
        for key in ("nodes", "neighbors"):
            if key in result:
                result[key] = [n for n in result[key]
                               if n.get("node_class") == node_class]
        result["filtered_by_class"] = node_class
    if getattr(args, "json_output", False):
        print(json.dumps(result, indent=2, default=str))
    else:
        print(format_query_result(result))
    return 0


def cmd_knowledge_gaps(args: argparse.Namespace) -> int:
    """Detect missing wiki-links in the knowledge graph."""
    from .knowledge_web import detect_web_gaps, format_gap_report, build_knowledge_web

    kg = build_knowledge_web()
    gaps = detect_web_gaps(kg)
    if getattr(args, "json_output", False):
        print(json.dumps(gaps, indent=2))
    else:
        print(format_gap_report(gaps))
    return 0


def cmd_knowledge_doctor(args: argparse.Namespace) -> int:
    """Report what the knowledge web cannot report about itself.

    Exits non-zero when acute findings exist, so a caller can gate on it — but
    note that gating is deliberately NOT the intended default use. See the
    policy on when running this is worth doing.
    """
    from .diagnostics import Severity, format_diagnosis
    from .knowledge_doctor import examine

    dx = examine()
    if getattr(args, "json_output", False):
        print(json.dumps(dx.to_dict(), indent=2, default=str))
    else:
        print(format_diagnosis(dx))
    return 1 if dx.counts().get(Severity.ACUTE, 0) else 0


def cmd_knowledge_viz(args: argparse.Namespace) -> int:
    """Generate interactive HTML knowledge graph visualization."""
    from .knowledge_web import generate_web_html

    output = getattr(args, "output", "") or "/tmp/macf_knowledge_graph.html"
    path = generate_web_html(output)
    print(f"📊 Knowledge graph written to: {path}")
    print(f"   Open in browser: file://{path}")
    return 0


def cmd_idea_search(args: argparse.Namespace) -> int:
    """Search ideas."""
    from .ideas import search_ideas
    items = search_ideas(args.query)
    if not items:
        print(f"No ideas matching '{args.query}'.")
        return 0
    for item in items:
        idea = item["idea"]
        print(f"#{idea['id']:03d} [{idea['status']}] {idea['title']}")
    print(f"\n{len(items)} result(s)")
    return 0


def cmd_shell_setup(args: argparse.Namespace) -> int:
    """Print shell completion setup instructions."""
    try:
        import argcomplete
        has_argcomplete = True
    except ImportError:
        has_argcomplete = False

    if not has_argcomplete:
        print("argcomplete is not installed. Install it first:\n")
        print("  pip install 'macf[completion]'")
        print("  # or: pip install argcomplete\n")
        return 1

    shell = os.environ.get("SHELL", "")
    print("Shell tab completion for macf_tools\n")
    print("  argcomplete is installed.\n")

    if "zsh" in shell:
        print("Add to your ~/.zshrc:\n")
        print('  autoload -U bashcompinit && bashcompinit')
        print('  eval "$(register-python-argcomplete macf_tools)"')
        print("\nThen reload: source ~/.zshrc")
    elif "bash" in shell:
        print("Add to your ~/.bashrc:\n")
        print('  eval "$(register-python-argcomplete macf_tools)"')
        print("\nThen reload: source ~/.bashrc")
    else:
        print(f"Detected shell: {shell or '(unknown)'}")
        print("\nFor bash/zsh, add to your rc file:\n")
        print('  eval "$(register-python-argcomplete macf_tools)"')
        print("\nFor fish:\n")
        print('  register-python-argcomplete --shell fish macf_tools | source')

    print(f"\nAfter setup, try: macf_tools ta<TAB> → task")
    return 0


# -------- parser --------
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="macf_tools", description="macf demo CLI (no external deps)"
    )
    class _VersionAction(argparse.Action):
        """Print the version, resolving the source checkout only when asked.

        The suffix costs a few `git` calls; computing it eagerly would charge
        every `macf_tools` invocation — including the ones hooks make on every
        tool use — for information only `--version` displays.
        """

        def __init__(self, option_strings, dest, **kwargs):
            super().__init__(option_strings, dest, nargs=0, **kwargs)

        def __call__(self, parser, namespace, values, option_string=None):
            print(f"{parser.prog} {_ver}{_editable_source_suffix()}")
            parser.exit()

    p.add_argument("--version", action=_VersionAction,
                   help="show version (with source checkout when editable)")
    sub = p.add_subparsers(dest="cmd")  # keep non-required for compatibility

    # cmd-tree: introspect parser structure (like unix tree command)
    # Note: parser 'p' captured via closure, passed to cmd_tree at runtime
    sub.add_parser("cmd-tree", help="print command tree structure").set_defaults(
        func=lambda args: cmd_tree(args, root_parser=p)
    )

    # env: flat command (env summary) with optional subcommands (set-term-title, ...)
    env_parser = sub.add_parser("env", help="environment commands (summary by default)")
    env_parser.add_argument("--json", action="store_true", help="output as JSON (default summary)")
    env_parser.set_defaults(func=cmd_env)
    env_sub = env_parser.add_subparsers(dest="env_cmd")
    set_title_parser = env_sub.add_parser(
        "set-term-title",
        help="set the terminal window title (default: agent calling card)"
    )
    set_title_parser.add_argument(
        "title",
        nargs="?",
        default=None,
        help="title string (default: agent calling card from get_agent_identity, "
             "e.g. Name@abc123). Inside tmux, also run "
             "'tmux set-option -g set-titles on' for titles to surface.",
    )
    set_title_parser.set_defaults(func=cmd_env_set_term_title)
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

    config_show = config_sub.add_parser(
        "show", help="show resolved value + source for every registered setting"
    )
    config_show.add_argument(
        "--json", dest="json_output", action="store_true",
        help="output as JSON array",
    )
    config_show.set_defaults(func=cmd_config_show)

    # Claude Code configuration commands
    claude_config_parser = sub.add_parser("claude-config", help="Claude Code settings management")
    claude_config_sub = claude_config_parser.add_subparsers(dest="claude_config_cmd")

    claude_config_sub.add_parser("init", help="set recommended defaults (verbose=true, autoCompact=false)").set_defaults(func=cmd_claude_config_init)
    claude_config_sub.add_parser("show", help="show current .claude.json configuration").set_defaults(func=cmd_claude_config_show)

    # Agent commands
    agent_parser = sub.add_parser("agent", help="agent initialization and management")
    agent_sub = agent_parser.add_subparsers(dest="agent_cmd")

    agent_init_parser = agent_sub.add_parser("init", help="initialize agent with PA preamble")
    agent_init_parser.add_argument("-y", "--yes", action="store_true", help="skip confirmation prompt")
    agent_init_parser.add_argument(
        "--mint-fresh-id", action="store_true",
        help="mint a NEW agent UUID even if one already resolves from another "
             "scope (default is to transfer the existing identity, preserving "
             "the calling card)",
    )
    agent_init_parser.set_defaults(func=cmd_agent_init)

    # AUTO_MODE auth token bootstrap (host / non-Docker installs) — #115
    auth_token_parser = agent_sub.add_parser(
        "init-auth-token",
        help="generate + install the AUTO_MODE auth token (host bootstrap)",
    )
    auth_token_parser.add_argument(
        "--force", action="store_true",
        help="overwrite an existing token (invalidates the old one)",
    )
    auth_token_parser.set_defaults(func=cmd_agent_init_auth_token)

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

    # Agent GitHub identity
    gh_parser = agent_sub.add_parser("set-github", help="set per-project GitHub identity via GH_TOKEN")
    gh_parser.add_argument("username", help="GitHub username (must be logged in via gh auth)")
    gh_parser.set_defaults(func=cmd_agent_set_github)

    # Agent sleep (emergency fallback)
    sleep_parser = agent_sub.add_parser("sleep", help="emergency sleep with fibonacci backoff + notification")
    sleep_parser.add_argument("--notify", action="store_true", help="send notification via configured channels each wakeup")
    sleep_parser.add_argument("--interval", choices=["fibonacci", "fixed"], default="fibonacci", help="backoff strategy (default: fibonacci)")
    sleep_parser.add_argument("--start", type=int, default=600, help="initial sleep seconds (default: 600 = 10min)")
    sleep_parser.add_argument("--max-attempts", type=int, default=20, help="max retry attempts (default: 20)")
    sleep_parser.set_defaults(func=cmd_agent_sleep)

    # Context command
    context_parser = sub.add_parser("context", help="show token usage and CL (Context Left) level")
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

    # Harness command with subcommands (mirrors statusline generate/install)
    harness_parser = sub.add_parser("harness", help="persistent supervised agent session (systemd + tmux)")
    harness_sub = harness_parser.add_subparsers(dest="harness_cmd")

    harness_generate = harness_sub.add_parser("generate", help="render harness artifacts to stdout (no writes)")
    harness_generate.add_argument("--agent", help="agent slug naming the unit and tmux session")
    harness_generate.add_argument("--home", help="agent home directory")
    harness_generate.add_argument("--no-proxy", action="store_true",
                                  help="render without proxy attachment")
    harness_generate.add_argument("--channel", action="append", metavar="PLUGIN",
                                 help="channel plugin the client must load; repeatable")
    harness_generate.add_argument("--shell-prefix", metavar="NAME",
                                 help="short handle for the generated shell functions (default: the moniker half of the Calling Card)")
    harness_generate.add_argument(
        "--what", choices=["unit", "start", "child", "functions", "tmux", "watchdog", "all"], default="unit",
        help="which artifact to render (default: unit)")
    harness_generate.set_defaults(func=cmd_harness_generate)

    harness_install = harness_sub.add_parser("install", help="write harness artifacts into place")
    harness_install.add_argument("--agent", help="agent slug naming the unit and tmux session")
    harness_install.add_argument("--home", help="agent home directory")
    harness_install.add_argument("--no-proxy", action="store_true",
                                 help="install without proxy attachment")
    harness_install.add_argument("--channel", action="append", metavar="PLUGIN",
                                 help="channel plugin the client must load; repeatable")
    harness_install.add_argument("--shell-prefix", metavar="NAME",
                                 help="short handle for the generated shell functions (default: the moniker half of the Calling Card)")
    harness_install.add_argument("--watchdog", action="store_true",
                                 help="also install a timer that restarts the session if the "
                                      "tmux server dies (the supervisor dies with it)")
    harness_install.add_argument("--check", action="store_true",
                                 help="report drift against what would be rendered; write nothing")
    harness_install.add_argument("--force", action="store_true",
                                 help="overwrite an existing unit that differs")
    harness_install.set_defaults(func=cmd_harness_install)

    harness_attach = harness_sub.add_parser(
        "attach", help="attach this terminal to the agent's supervised session")
    harness_attach.add_argument("--agent", help="agent slug (default: resolved from identity)")
    harness_attach.add_argument("--control", action="store_true",
                                help="attach in tmux control mode (-CC), for iTerm2 on macOS")
    harness_attach.add_argument("--read-only", action="store_true",
                                help="observe without evicting other clients or taking the keyboard")
    harness_attach.set_defaults(func=cmd_harness_attach)

    harness_status = harness_sub.add_parser("status", help="show harness unit and session state")
    harness_status.add_argument("--agent", help="agent slug")
    harness_status.set_defaults(func=cmd_harness_status)

    harness_parser.set_defaults(func=cmd_harness_status)

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
    navigate_parser.add_argument("policy_name", help="policy name (e.g., task_management, development/task_management)")
    navigate_parser.set_defaults(func=cmd_policy_navigate)

    # policy read
    read_parser = policy_sub.add_parser("read", help="read policy with line numbers and caching")
    read_parser.add_argument("policy_name", help="policy name (e.g., task_management, development/task_management)")
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

    # policy inject
    inject_parser = policy_sub.add_parser("inject", help="activate policy injection into PreToolUse hooks")
    inject_parser.add_argument("policy_name", help="policy name to inject (e.g., task_management)")
    inject_parser.set_defaults(func=cmd_policy_inject)

    # policy clear-injection
    clear_inj_parser = policy_sub.add_parser("clear-injection", help="clear a specific policy injection")
    clear_inj_parser.add_argument("policy_name", help="policy name to clear")
    clear_inj_parser.set_defaults(func=cmd_policy_clear_injection)

    # policy clear-injections
    clear_all_parser = policy_sub.add_parser("clear-injections", help="clear all policy injections")
    clear_all_parser.set_defaults(func=cmd_policy_clear_injections)

    # policy injections
    injections_parser = policy_sub.add_parser("injections", help="list active policy injections")
    injections_parser.set_defaults(func=cmd_policy_injections)

    # Mode commands
    mode_parser = sub.add_parser("mode", help="operating mode management (MANUAL_MODE/AUTO_MODE)")
    mode_sub = mode_parser.add_subparsers(dest="mode_cmd")

    mode_get = mode_sub.add_parser("get", help="get current operating mode")
    mode_get.add_argument("--json", dest="json_output", action="store_true",
                         help="output as JSON")
    mode_get.set_defaults(func=cmd_mode_get)

    mode_sub.add_parser("show", help="show active mode set with emojis and triggers").set_defaults(func=cmd_mode_show)
    mode_set_work = mode_sub.add_parser("set-work", help="set the active work mode")
    mode_set_work.add_argument("work_mode", help="work mode (DISCOVER, EXPERIMENT, BUILD, CURATE, CONSOLIDATE, SPRINT)")
    mode_set_work.add_argument(
        "--trigger",
        choices=["manual", "chain_advance", "markov_accept", "markov_override"],
        default="manual",
        help="provenance tag recorded in PLAY_TIME mode_transitions (default: manual)",
    )
    mode_set_work.set_defaults(func=cmd_mode_set_work)

    mode_sub.add_parser("unset-work", help="clear the active work mode").set_defaults(func=cmd_mode_unset_work)

    mode_set = mode_sub.add_parser("set", help="set operating mode")
    mode_set.add_argument("mode", help="mode to set (AUTO_MODE or MANUAL_MODE)")
    mode_set.add_argument("--justification", choices=["security", "opsec", "blocked", "user_directive", "other"],
                          help="emergency justification for de-escalation when scope is active")
    mode_set.add_argument("--explain", help="detailed reason (required when --justification other)")
    mode_set.add_argument("--auth-token", dest="auth_token",
                         help="auth token for AUTO_MODE activation")
    mode_set.set_defaults(func=cmd_mode_set)

    # Recommender commands
    rec_parser = sub.add_parser("recommender", help="Markov work mode recommender")
    rec_sub = rec_parser.add_subparsers(dest="rec_cmd")
    rec_sub.add_parser("show", help="show transition distribution for current state").set_defaults(func=cmd_recommender_show)
    rec_sample = rec_sub.add_parser("sample", help="Monte Carlo sample and display recommendation")
    rec_sample.add_argument("--prefix", default="maceff", help="agent prefix for skill name (default: maceff)")
    rec_sample.set_defaults(func=cmd_recommender_sample)

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

    # events analyze (BUG #1069 — generic structured-event JSONL analyzer)
    analyze_parser = events_sub.add_parser(
        "analyze",
        help="analyze a structured-event JSONL log (Hermes delegations, Telegram restart-events, etc.)",
    )
    analyze_parser.add_argument("path", type=Path, help="path to the JSONL log file")
    analyze_parser.add_argument(
        "--since",
        help="filter to events in last N{s,m,h,d} (e.g. 1h, 7d)",
    )
    analyze_parser.add_argument(
        "--by",
        metavar="FIELD",
        help="group started events by this field (e.g. trigger, caller)",
    )
    analyze_parser.add_argument(
        "--tail",
        type=int,
        default=0,
        help="show last N completed requests instead of summary",
    )
    analyze_parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="machine-readable JSON output",
    )
    analyze_parser.add_argument(
        "--started-phase",
        default="started",
        help="phase value marking the start of a request (default: started)",
    )
    analyze_parser.add_argument(
        "--success-field",
        default="success",
        help="bool field on terminal events (default: success)",
    )
    analyze_parser.add_argument(
        "--elapsed-field",
        default="elapsed_ms",
        help="integer field on completed events for elapsed time (default: elapsed_ms)",
    )
    analyze_parser.add_argument(
        "--correlation-field",
        default="request_id",
        help="field used to correlate started + terminal events (default: request_id)",
    )
    analyze_parser.set_defaults(func=cmd_events_analyze)

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
    task_list_parser.add_argument("--all", dest="show_all", action="store_true",
                                  help="show all tasks including archived")
    task_list_parser.add_argument("--archived", dest="show_archived_only", action="store_true",
                                  help="show only archived tasks")
    task_list_parser.set_defaults(func=cmd_task_list)

    # task get
    task_get_parser = task_sub.add_parser("get", help="get task details")
    task_get_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_get_parser.add_argument("--json", dest="json_output", action="store_true",
                                 help="output as JSON")
    task_get_parser.set_defaults(func=cmd_task_get)

    # task tree
    task_tree_parser = task_sub.add_parser("tree", help="show task hierarchy tree")
    task_tree_parser.add_argument("task_id", nargs="?", default="000",
                                  help="root task ID (default: 000 sentinel)")
    task_tree_parser.add_argument("--loop", action="store_true",
                                  help="monitor tasks directory and auto-refresh on changes")
    task_tree_parser.add_argument("--succinct", "-s", action="store_true",
                                  help="hide notes/plans, show only active/pending tasks")
    task_tree_parser.add_argument("--verbose", "-v", action="store_true",
                                  help="show full plans, breadcrumbs, and all updates")
    task_tree_parser.add_argument("--title-width", dest="title_width", type=int, default=None,
                                  metavar="N",
                                  help="truncate task titles to N chars (default: 40 with "
                                       "--succinct, 80 otherwise; 0 disables). Timestamps and "
                                       "end markers are never truncated.")
    tree_archive_group = task_tree_parser.add_mutually_exclusive_group()
    tree_archive_group.add_argument("--archived", action="store_true",
                                    help="show ONLY archived tasks")
    tree_archive_group.add_argument("--all", action="store_true", dest="show_all",
                                    help="show all tasks including archived (default hides archived)")
    task_tree_parser.set_defaults(func=cmd_task_tree)

    # task reconcile
    task_reconcile_parser = task_sub.add_parser(
        "reconcile",
        help="union-merge forked CC per-session task DBs into the home store")
    task_reconcile_parser.add_argument("--apply", action="store_true",
                                       help="write the merge (default: dry-run report)")
    task_reconcile_parser.set_defaults(func=cmd_task_reconcile)

    # task delete
    task_delete_parser = task_sub.add_parser("delete", help="delete task(s) (HIGH protection)")
    task_delete_parser.add_argument("task_ids", nargs='+', help="task ID(s) (e.g., #67 or 67, accepts multiple)")
    task_delete_parser.add_argument("--force", "-f", action="store_true",
                                    help="skip confirmation prompt")
    task_delete_parser.set_defaults(func=cmd_task_delete)

    # task edit
    task_edit_parser = task_sub.add_parser("edit", help="edit task JSON field")
    task_edit_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_edit_parser.add_argument("field", help="field to edit (subject, status, description)")
    task_edit_parser.add_argument("value", help="new value for the field")
    task_edit_parser.set_defaults(func=cmd_task_edit)

    # task metadata subcommand
    task_metadata_parser = task_sub.add_parser("metadata", help="MTMD metadata operations")
    task_metadata_sub = task_metadata_parser.add_subparsers(dest="metadata_cmd")

    # task metadata get
    task_metadata_get_parser = task_metadata_sub.add_parser("get", help="display MTMD for a task")
    task_metadata_get_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_metadata_get_parser.set_defaults(func=cmd_task_metadata_get)

    # task metadata set
    task_metadata_set_parser = task_metadata_sub.add_parser("set", help="set MTMD field")
    task_metadata_set_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_metadata_set_parser.add_argument("field", help="MTMD field to set")
    task_metadata_set_parser.add_argument("value", help="new value for the field")
    task_metadata_set_parser.set_defaults(func=cmd_task_metadata_set)

    # task metadata add
    task_metadata_add_parser = task_metadata_sub.add_parser("add", help="add custom MTMD field")
    task_metadata_add_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_metadata_add_parser.add_argument("key", help="custom field key")
    task_metadata_add_parser.add_argument("value", help="custom field value")
    task_metadata_add_parser.set_defaults(func=cmd_task_metadata_add)

    # task metadata validate
    task_metadata_validate_parser = task_metadata_sub.add_parser("validate", help="validate MTMD against schema")
    task_metadata_validate_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_metadata_validate_parser.set_defaults(func=cmd_task_metadata_validate)

    # task metadata set-custom
    task_metadata_set_custom_parser = task_metadata_sub.add_parser(
        "set-custom",
        help="set a dotted-path key in MTMD.custom (e.g. decision_gates.submitted true)"
    )
    task_metadata_set_custom_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_metadata_set_custom_parser.add_argument("path", help="dotted path into custom (e.g. decision_gates.submitted)")
    task_metadata_set_custom_parser.add_argument("value", help="value to set")
    task_metadata_set_custom_parser.add_argument(
        "--json", dest="json", action="store_true", default=False,
        help="interpret <value> as a JSON literal (e.g. '[1,2,3]' or 'true')"
    )
    task_metadata_set_custom_parser.set_defaults(func=cmd_task_metadata_set_custom)

    # task reparent
    task_reparent_parser = task_sub.add_parser(
        "reparent",
        help="atomically change a task's parent_id (grant-gated, cycle-safe)"
    )
    task_reparent_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_reparent_parser.add_argument(
        "parent",
        help="new parent ID — digit string, '000' (top-level sentinel), or 'null' (orphan)"
    )
    task_reparent_parser.set_defaults(func=cmd_task_reparent)

    # task advance
    task_advance_parser = task_sub.add_parser(
        "advance",
        help="drive a plugin task's lifecycle state through its declared state machine"
    )
    task_advance_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_advance_parser.add_argument("state", help="new state to transition to")
    task_advance_parser.add_argument(
        "--reason", default="", metavar="TEXT",
        help="optional reason recorded in the task_lifecycle_advanced event"
    )
    task_advance_parser.set_defaults(func=cmd_task_advance)

    # task create subcommand
    task_create_parser = task_sub.add_parser("create", help="create new tasks with MTMD")
    task_create_sub = task_create_parser.add_subparsers(dest="create_cmd")

    # task create mission
    task_create_mission_parser = task_create_sub.add_parser("mission", help="create MISSION task with roadmap")
    task_create_mission_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_mission_parser.add_argument("title", help="mission title")
    task_create_mission_parser.add_argument("--repo", help="repository name (e.g., MacEff)")
    task_create_mission_parser.add_argument("--version", help="target version (e.g., 0.4.0)")
    task_create_mission_parser.add_argument("--json", dest="json", action="store_true",
                                            help="output as JSON")
    task_create_mission_parser.set_defaults(func=cmd_task_create_mission)

    # task create experiment
    task_create_experiment_parser = task_create_sub.add_parser("experiment", help="create EXPERIMENT task with protocol")
    task_create_experiment_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_experiment_parser.add_argument("title", help="experiment title")
    task_create_experiment_parser.add_argument("--json", dest="json", action="store_true",
                                               help="output as JSON")
    task_create_experiment_parser.set_defaults(func=cmd_task_create_experiment)

    # task create detour
    task_create_detour_parser = task_create_sub.add_parser("detour", help="create DETOUR task with roadmap")
    task_create_detour_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_detour_parser.add_argument("title", help="detour title")
    task_create_detour_parser.add_argument("--repo", help="repository name (e.g., MacEff)")
    task_create_detour_parser.add_argument("--version", help="target version (e.g., 0.4.0)")
    task_create_detour_parser.add_argument("--json", dest="json", action="store_true",
                                           help="output as JSON")
    task_create_detour_parser.set_defaults(func=cmd_task_create_detour)

    # task create phase
    task_create_phase_parser = task_create_sub.add_parser("phase", help="create phase task under parent")
    task_create_phase_parser.add_argument("--parent", required=True, help="parent task ID (e.g., #67 or 67)")
    task_create_phase_parser.add_argument("title", help="phase title")
    # XOR: exactly one of plan or plan_ca_ref required (uniform requirement)
    phase_plan_group = task_create_phase_parser.add_mutually_exclusive_group(required=True)
    phase_plan_group.add_argument("--plan", dest="plan", help="inline plan description")
    phase_plan_group.add_argument("--plan-ca-ref", dest="plan_ca_ref", help="path to plan CA")
    task_create_phase_parser.add_argument("--blocked-by", dest="blocked_by", nargs="+",
                                          help="task IDs that block this phase (e.g., #50 51)")
    task_create_phase_parser.add_argument("--json", dest="json", action="store_true",
                                          help="output as JSON")
    task_create_phase_parser.set_defaults(func=cmd_task_create_phase)

    # task create bug
    task_create_bug_parser = task_create_sub.add_parser("bug", help="create bug task (standalone or under parent)")
    task_create_bug_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_bug_parser.add_argument("title", help="bug title")
    # XOR: exactly one of fix_plan or plan_ca_ref required
    bug_plan_group = task_create_bug_parser.add_mutually_exclusive_group(required=True)
    bug_plan_group.add_argument("--plan", dest="plan", help="inline plan description (simple bugs)")
    bug_plan_group.add_argument("--plan-ca-ref", dest="plan_ca_ref", help="path to BUG_FIX roadmap CA (complex bugs)")
    task_create_bug_parser.add_argument("--json", dest="json", action="store_true",
                                        help="output as JSON")
    task_create_bug_parser.set_defaults(func=cmd_task_create_bug)

    # task create gh_issue
    task_create_gh_issue_parser = task_create_sub.add_parser("gh_issue", help="create task from GitHub issue (auto-fetches metadata)")
    task_create_gh_issue_parser.add_argument("issue_url", help="GitHub issue URL (https://github.com/owner/repo/issues/N)")
    task_create_gh_issue_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_gh_issue_parser.add_argument("--json", dest="json", action="store_true",
                                             help="output as JSON")
    task_create_gh_issue_parser.set_defaults(func=cmd_task_create_gh_issue)

    # task create gh_pr
    task_create_gh_pr_parser = task_create_sub.add_parser("gh_pr", help="create task from GitHub PR for review/merge (auto-fetches metadata)")
    task_create_gh_pr_parser.add_argument("pr_url", help="GitHub PR URL (https://github.com/owner/repo/pull/N)")
    task_create_gh_pr_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_gh_pr_parser.add_argument("--json", dest="json", action="store_true",
                                          help="output as JSON")
    task_create_gh_pr_parser.set_defaults(func=cmd_task_create_gh_pr)

    # task create deleg
    task_create_deleg_parser = task_create_sub.add_parser("deleg", help="create DELEG_PLAN task for delegation")
    task_create_deleg_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_deleg_parser.add_argument("title", help="delegation title")
    # XOR: exactly one of plan or plan_ca_ref required
    deleg_plan_group = task_create_deleg_parser.add_mutually_exclusive_group(required=True)
    deleg_plan_group.add_argument("--plan", dest="plan", help="inline delegation plan (simple delegations)")
    deleg_plan_group.add_argument("--plan-ca-ref", dest="plan_ca_ref", help="path to deleg_plan.md CA (complex delegations)")
    task_create_deleg_parser.add_argument("--json", dest="json", action="store_true",
                                          help="output as JSON")
    task_create_deleg_parser.set_defaults(func=cmd_task_create_deleg)

    # task create task
    task_create_task_parser = task_create_sub.add_parser("task", help="create standalone task")
    task_create_task_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_task_parser.add_argument("title", help="task title")
    # XOR: exactly one of plan or plan_ca_ref required (uniform requirement)
    task_plan_group = task_create_task_parser.add_mutually_exclusive_group(required=True)
    task_plan_group.add_argument("--plan", dest="plan", help="inline plan description")
    task_plan_group.add_argument("--plan-ca-ref", dest="plan_ca_ref", help="path to plan CA")
    task_create_task_parser.add_argument("--json", dest="json", action="store_true",
                                          help="output as JSON")
    task_create_task_parser.set_defaults(func=cmd_task_create_task)

    # task create sprint
    task_create_sprint_parser = task_create_sub.add_parser(
        "sprint",
        help="create SPRINT task (workload-defined autonomous work, no timer)",
        description=(
            "Create a 🏃 SPRINT task for workload-defined autonomous work.\n\n"
            "SPRINT runs until all scoped tasks are complete (no timer).\n"
            "Work mode is locked at SPRINT; Markov recommender is silenced.\n\n"
            "Examples:\n"
            "  macf_tools task create sprint \"Build pipeline\" --scoped 42 43 44\n"
            "  macf_tools task create sprint \"Research phase\" --children \"Read docs\" \"Write notes\"\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    task_create_sprint_parser.add_argument("title", help="sprint title / goal description")
    task_create_sprint_parser.add_argument("--goal", help="explicit goal (defaults to title if omitted)")
    # Mutually exclusive: --scoped XOR --children (one required)
    sprint_scope_group = task_create_sprint_parser.add_mutually_exclusive_group(required=True)
    sprint_scope_group.add_argument(
        "--scoped", nargs="+", metavar="TASK_ID",
        help="existing task IDs to scope (e.g., 42 43 44 or #42 #43)",
    )
    sprint_scope_group.add_argument(
        "--children", nargs="+", metavar="TITLE",
        help='new child task titles to create and scope (e.g., "Write tests" "Update docs")',
    )
    task_create_sprint_parser.add_argument(
        "--timer", type=int, metavar="MINUTES", default=0,
        help=argparse.SUPPRESS,  # hidden: present only to give a clear hard-fail message
    )
    task_create_sprint_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_sprint_parser.add_argument("--repo", help="repository name (e.g., MacEff)")
    task_create_sprint_parser.add_argument(
        "--no-auto-start", dest="no_auto_start", action="store_true",
        help="create task only; skip start/scope/mode auto-start chain",
    )
    task_create_sprint_parser.add_argument("--json", dest="json", action="store_true", help="output as JSON")
    task_create_sprint_parser.set_defaults(func=cmd_task_create_sprint)

    # task create play_time
    task_create_play_time_parser = task_create_sub.add_parser(
        "play_time",
        help="create PLAY_TIME task (time-bounded autonomous exploration, timer required)",
        description=(
            "Create a ⏲️ PLAY_TIME task for time-bounded autonomous exploration.\n\n"
            "--timer is required. Work modes cycle through the --chain;\n"
            "Markov recommender engages after chain exhaustion.\n\n"
            "Examples:\n"
            "  macf_tools task create play_time \"Explore new ideas\" --timer 60\n"
            "  macf_tools task create play_time \"Deep dive\" --timer 45 --chain DISCOVER EXPERIMENT BUILD\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    task_create_play_time_parser.add_argument("title", help="play time title / goal description")
    task_create_play_time_parser.add_argument("--goal", help="explicit goal (defaults to title if omitted)")
    task_create_play_time_parser.add_argument(
        "--timer", type=int, required=True, metavar="MINUTES",
        help="session duration in minutes (required; must be > 0)",
    )
    task_create_play_time_parser.add_argument(
        "--chain", nargs="+", metavar="MODE", default=None,
        help=(
            "initial work-mode chain (default: DISCOVER). "
            "Valid modes: DISCOVER EXPERIMENT BUILD CURATE CONSOLIDATE. "
            "SPRINT is not allowed in chain."
        ),
    )
    play_time_scope_group = task_create_play_time_parser.add_mutually_exclusive_group()
    play_time_scope_group.add_argument(
        "--children", nargs="+", metavar="TITLE",
        help='new child task titles to create and scope',
    )
    play_time_scope_group.add_argument(
        "--scoped", nargs="+", metavar="TASK_ID",
        help="existing task IDs to also scope (e.g., 42 43)",
    )
    task_create_play_time_parser.add_argument("--parent", default="000", help="parent task ID (default: 000)")
    task_create_play_time_parser.add_argument("--repo", help="repository name (e.g., MacEff)")
    task_create_play_time_parser.add_argument(
        "--no-auto-start", dest="no_auto_start", action="store_true",
        help="create task only; skip start/scope/mode auto-start chain",
    )
    task_create_play_time_parser.add_argument("--json", dest="json", action="store_true", help="output as JSON")
    task_create_play_time_parser.set_defaults(func=cmd_task_create_play_time)

    # task archive
    task_archive_parser = task_sub.add_parser("archive", help="(DEPRECATED — no-op; use `task hide-completed`)")
    task_archive_parser.add_argument("task_id", help="task ID to archive (e.g., #67 or 67)")
    task_archive_parser.add_argument("--no-cascade", dest="no_cascade", action="store_true",
                                     help="archive only this task, not children (default: cascade)")
    task_archive_parser.add_argument("--json", dest="json_output", action="store_true",
                                     help="output as JSON")
    task_archive_parser.set_defaults(func=cmd_task_archive)

    # task restore
    task_restore_parser = task_sub.add_parser("restore", help="restore task from archive")
    task_restore_parser.add_argument("archive_path_or_id", help="archive file path or original task ID")
    task_restore_parser.add_argument("--json", dest="json_output", action="store_true",
                                     help="output as JSON")
    task_restore_parser.set_defaults(func=cmd_task_restore)

    # task archived (subcommand group)
    task_archived_parser = task_sub.add_parser("archived", help="archived task operations")
    task_archived_sub = task_archived_parser.add_subparsers(dest="archived_cmd")

    # task archived list
    task_archived_list_parser = task_archived_sub.add_parser("list", help="list archived tasks")
    task_archived_list_parser.add_argument("--json", dest="json_output", action="store_true",
                                           help="output as JSON")
    task_archived_list_parser.set_defaults(func=cmd_task_archived_list)

    # task hide-completed
    task_hide_parser = task_sub.add_parser("hide-completed",
                                           help="dot-prefix all completed task files to hide from CC scanner")
    task_hide_parser.set_defaults(func=cmd_task_hide_completed)

    # task unhide-all
    task_unhide_parser = task_sub.add_parser("unhide-all",
                                             help="restore all hidden task files to visible state")
    task_unhide_parser.set_defaults(func=cmd_task_unhide_all)

    # task grant-update
    task_grant_update_parser = task_sub.add_parser("grant-update", help="grant permission to update task description")
    task_grant_update_parser.add_argument("task_id", help="task ID to grant update permission (e.g., #67 or 67)")
    task_grant_update_parser.add_argument("--field", "-f", help="specific MTMD field to grant modification for")
    task_grant_update_parser.add_argument("--value", "-v", help="expected new value (requires --field)")
    task_grant_update_parser.add_argument("--reason", "-r", default="", help="reason for granting")
    task_grant_update_parser.set_defaults(func=cmd_task_grant_update)

    # task grant-delete
    task_grant_delete_parser = task_sub.add_parser("grant-delete", help="grant permission to delete tasks")
    task_grant_delete_parser.add_argument("task_ids", nargs='+', help="task ID(s) to grant delete permission (e.g., #67 or 67, accepts multiple)")
    task_grant_delete_parser.add_argument("--reason", "-r", default="", help="reason for granting")
    task_grant_delete_parser.set_defaults(func=cmd_task_grant_delete)

    # task start
    task_start_parser = task_sub.add_parser("start", help="start work on task (→ in_progress)")
    task_start_parser.add_argument("task_id", help="task ID to start (e.g., #67 or 67)")
    task_start_parser.set_defaults(func=cmd_task_start)

    # task pause
    task_pause_parser = task_sub.add_parser("pause", help="pause work on task (→ pending)")
    task_pause_parser.add_argument("task_id", help="task ID to pause (e.g., #67 or 67)")
    task_pause_parser.set_defaults(func=cmd_task_pause)

    # task note - append note to updates
    task_migrate_parser = task_sub.add_parser(
        "migrate-store",
        help="move the legacy per-session task store into the home store",
    )
    task_migrate_parser.add_argument(
        "--dry-run", action="store_true",
        help="report what would be copied without touching anything",
    )
    task_migrate_parser.add_argument(
        "--force", action="store_true",
        help="proceed even if the target already holds files of the same name",
    )
    task_migrate_parser.set_defaults(func=cmd_task_migrate_store)

    task_store_init_parser = task_sub.add_parser(
        "store-init",
        help="provision the home task store and point the config at it",
    )
    task_store_init_parser.add_argument(
        "--home", default=None,
        help="agent home to provision (default: this agent's home)",
    )
    task_store_init_parser.set_defaults(func=cmd_task_store_init)

    task_trace_parser = task_sub.add_parser(
        "trace",
        help="show where attention has been and what it owes a return to",
    )
    task_trace_parser.add_argument(
        "--path", type=int, default=0, metavar="N",
        help="also show the last N touches, in the order they happened",
    )
    task_trace_parser.add_argument(
        "--full", action="store_true",
        help="show note text in full instead of trimming it to one line",
    )
    task_trace_parser.add_argument("--json", action="store_true", help="output as JSON")
    task_trace_parser.set_defaults(func=cmd_task_trace)

    task_doctor_parser = task_sub.add_parser(
        "doctor",
        help="reconcile stored task records against the authorities they derive from",
    )
    task_doctor_parser.add_argument(
        "--fix", action="store_true",
        help="apply the corrections (default is report-only, exits 1 on drift)",
    )
    task_doctor_parser.add_argument(
        "--no-github", action="store_true",
        help="skip the live GitHub check (offline, or to avoid API calls)",
    )
    task_doctor_parser.add_argument(
        "--all", action="store_true",
        help="also check GitHub-backed tasks that are already completed",
    )
    task_doctor_parser.set_defaults(func=cmd_task_doctor)

    task_note_parser = task_sub.add_parser("note", help="add a note to task (appends to updates with type='note')")
    task_note_parser.add_argument("task_id", help="task ID (e.g., #67 or 67)")
    task_note_parser.add_argument("message", help="note text")
    task_note_parser.add_argument(
        "--idea",
        action="store_true",
        help="format as 'MODE: 💡 <text>' and increment ideas_captured on active scoped SPRINT/PLAY_TIME",
    )
    task_note_parser.set_defaults(func=cmd_task_note)

    # task complete
    task_complete_parser = task_sub.add_parser("complete", help="mark task complete with report")
    task_complete_parser.add_argument("task_id", help="task ID to complete (e.g., #67 or 67)")
    task_complete_parser.add_argument("--report", "-r",
                                      help="completion report (work done, difficulties, future work, git commit status)")
    task_complete_parser.add_argument("--commit", action="append", default=[],
                                      help="commit hash(es) that fix the issue (repeatable, required for GH_ISSUE)")
    task_complete_parser.add_argument("--verified",
                                      help="verification method description (required for GH_ISSUE)")
    task_complete_parser.add_argument("--force", action="store_true", default=False,
                                      help="force completion despite open child tasks (SPRINT) or unexpired timer (PLAY_TIME)")
    task_complete_parser.add_argument("--justification",
                                      help="REQUIRED when --force is used on a SPRINT with incomplete scoped tasks. "
                                           "Recorded in completion_report and audited. "
                                           "See autonomous_sprint.md §3.3.2 for acceptable vs unacceptable justifications.")
    task_complete_parser.add_argument("--cascade", action="store_true", default=False,
                                      help="GH_PR only: auto-complete linked GH_ISSUE tasks when the PR is merged")
    task_complete_parser.set_defaults(func=cmd_task_complete)

    # task block - add blocking relationship
    task_block_parser = task_sub.add_parser("block", help="set task to block another task")
    task_block_parser.add_argument("task_id", help="task ID that will block (e.g., #60)")
    task_block_parser.add_argument("target_id", help="task ID to be blocked (e.g., #42)")
    task_block_parser.set_defaults(func=cmd_task_block)

    # task unblock - remove blocking relationship
    task_unblock_parser = task_sub.add_parser("unblock", help="remove blocking relationship")
    task_unblock_parser.add_argument("task_id", help="task ID that blocks (e.g., #60)")
    task_unblock_parser.add_argument("target_id", help="task ID to unblock (e.g., #42)")
    task_unblock_parser.set_defaults(func=cmd_task_unblock)

    # task blocked-by - add blocked-by relationship
    task_blocked_by_parser = task_sub.add_parser("blocked-by", help="set task as blocked by another task")
    task_blocked_by_parser.add_argument("task_id", help="task ID that is blocked (e.g., #60)")
    task_blocked_by_parser.add_argument("blocker_id", help="task ID that blocks (e.g., #26)")
    task_blocked_by_parser.set_defaults(func=cmd_task_blocked_by)

    # task unblocked-by - remove blocked-by relationship
    task_unblocked_by_parser = task_sub.add_parser("unblocked-by", help="remove blocked-by relationship")
    task_unblocked_by_parser.add_argument("task_id", help="task ID that was blocked (e.g., #60)")
    task_unblocked_by_parser.add_argument("blocker_id", help="task ID to remove as blocker (e.g., #26)")
    task_unblocked_by_parser.set_defaults(func=cmd_task_unblocked_by)

    # Task scope commands
    scope_parser = task_sub.add_parser("scope", help="manage task scope for AUTO_MODE boundary enforcement")
    scope_sub = scope_parser.add_subparsers(dest="scope_cmd")

    scope_pause_parser = scope_sub.add_parser("pause", help="pause active scoped tasks with mandatory justification (BUG #1067)")
    scope_pause_parser.add_argument("task_ids", nargs="*", help="task IDs to pause (e.g., #1043 #1044); omit when using --all")
    scope_pause_parser.add_argument("--all", action="store_true", help="pause ALL currently-active scoped tasks — the non-hanging, reversible full-gate quiet safe under USER_REMOTE")
    scope_pause_parser.add_argument("--justification", "-j", required=True,
                                    help="REQUIRED — structural reason recorded in task note + event log")
    scope_pause_parser.set_defaults(func=cmd_task_scope_pause)

    scope_unpause_parser = scope_sub.add_parser("unpause", help="restore paused scoped tasks to active (BUG #1067)")
    scope_unpause_parser.add_argument("task_ids", nargs="+", help="task IDs to unpause (e.g., #1043 #1044)")
    scope_unpause_parser.set_defaults(func=cmd_task_scope_unpause)

    scope_add_parser = scope_sub.add_parser("add", help="incrementally add tasks to scope (no replace; BUG #1067)")
    scope_add_parser.add_argument("task_ids", nargs="+", help="task IDs to add (e.g., #1067)")
    scope_add_parser.set_defaults(func=cmd_task_scope_add)

    scope_remove_parser = scope_sub.add_parser("remove", help="incrementally remove tasks from scope (BUG #1067)")
    scope_remove_parser.add_argument("task_ids", nargs="+", help="task IDs to remove (e.g., #1067)")
    scope_remove_parser.set_defaults(func=cmd_task_scope_remove)

    scope_set_parser = scope_sub.add_parser("set", help="scope tasks (parent auto-expands to pending/in_progress children)")
    scope_set_parser.add_argument("task_ids", nargs="+", help="task IDs to scope (e.g., #290 #291)")
    scope_set_parser.add_argument("--timer", type=int, default=0, metavar="MINUTES",
                                  help="set autonomous work timer (minutes). Stop hook blocks stopping until timer expires.")
    scope_set_parser.set_defaults(func=cmd_task_scope_set)

    scope_sub.add_parser("show", help="display current scope with status").set_defaults(func=cmd_task_scope_show)

    scope_sub.add_parser("clear", help="remove all tasks from scope (destructive)").set_defaults(func=cmd_task_scope_clear)

    scope_check_parser = scope_sub.add_parser("check", help="check active scope count (JSON, for Stop hook)")
    scope_check_parser.add_argument("--json", dest="json_output", action="store_true", default=True)
    scope_check_parser.set_defaults(func=cmd_task_scope_check)

    # Proxy commands
    # --- amail: agent mail (see `macf_tools policy navigate amail`) ---
    amail_parser = sub.add_parser("amail", help="agent mail: send and read correspondence")
    amail_sub = amail_parser.add_subparsers(dest="amail_cmd")

    amail_send = amail_sub.add_parser(
        "send", help="submit a message to the broker",
        description=(
            "Submit a message. The BROKER decides whether it may be sent — this "
            "command holds no credential and performs no delivery. A refusal is "
            "reported, never swallowed."
        ),
        epilog=(
            "Examples:\n"
            "  macf_tools amail send --to peer@example.org --subject 'status' --body 'done'\n"
            "  macf_tools amail send --to peer@example.org --body-file report.md\n"
            "  macf_tools amail send --to peer@example.org --reply-to msg-123 --body 'ack'\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    amail_send.add_argument("--to", action="append", required=True, metavar="ADDRESS",
                            help="recipient (repeat for several)")
    amail_send.add_argument("--subject", help="subject line")
    amail_send.add_argument("--body", help="message body")
    amail_send.add_argument("--body-file", help="read the body from a file")
    amail_send.add_argument("--reply-to", metavar="MESSAGE_ID",
                            help="reply, joining that message's thread")
    amail_send.add_argument("--json", action="store_true", help="machine-readable result")
    amail_send.set_defaults(func=cmd_amail_send)

    amail_list = amail_sub.add_parser("list", help="list messages in this mailbox")
    amail_list.add_argument("--thread", metavar="THREAD_ID", help="only this thread")
    amail_list.add_argument("--json", action="store_true", help="machine-readable output")
    amail_list.set_defaults(func=cmd_amail_list)

    amail_read = amail_sub.add_parser("read", help="print one message in full")
    amail_read.add_argument("message_id", help="message id (see `amail list`)")
    amail_read.add_argument("--json", action="store_true", help="machine-readable output")
    amail_read.set_defaults(func=cmd_amail_read)

    amail_keygen = amail_sub.add_parser(
        "keygen", help="generate this agent's authorship signing key")
    amail_keygen.add_argument("--path", help="where to write the private key "
                                            "(default: ~/.maceff/amail_signing_key.pem)")
    amail_keygen.set_defaults(func=cmd_amail_keygen)

    amail_status = amail_sub.add_parser("status", help="is amail usable? what is missing?")
    amail_status.add_argument("--json", action="store_true", help="machine-readable output")
    amail_status.set_defaults(func=cmd_amail_status)

    proxy_parser = sub.add_parser("proxy", help="API proxy for CC call interception")
    proxy_sub = proxy_parser.add_subparsers(dest="proxy_cmd")

    # proxy start
    proxy_start_parser = proxy_sub.add_parser("start", help="start proxy daemon")
    proxy_start_parser.add_argument("--daemon", "-d", action="store_true",
                                    help="run in background (daemonize)")
    proxy_start_parser.add_argument("--port", type=int, default=8019,
                                    help="port to listen on (default: 8019)")
    proxy_start_parser.add_argument("--force", action="store_true",
                                    help="start even if the port is already held (skips the "
                                         "occupied-port refusal; the bind will still fail if "
                                         "the holder keeps it)")
    proxy_start_parser.set_defaults(func=cmd_proxy_start)

    # proxy stop
    proxy_stop_parser = proxy_sub.add_parser("stop", help="stop running proxy")
    proxy_stop_parser.add_argument("--port", type=int, default=8019, help="port of the proxy to stop (default: 8019)")
    proxy_stop_parser.set_defaults(func=cmd_proxy_stop)

    # proxy status
    proxy_status_parser = proxy_sub.add_parser("status", help="show proxy status")
    proxy_status_parser.add_argument("--port", type=int, default=8019, help="port to report on (default: 8019)")
    proxy_status_parser.add_argument("--json", dest="json_output", action="store_true",
                                     help="output as JSON")
    proxy_status_parser.set_defaults(func=cmd_proxy_status)

    # proxy stats
    proxy_sub.add_parser("stats", help="show aggregate token/cost statistics").set_defaults(func=cmd_proxy_stats)

    # proxy log
    proxy_log_parser = proxy_sub.add_parser("log", help="show recent API call events")
    proxy_log_parser.add_argument("--limit", "-n", type=int, default=10,
                                  help="number of recent events (default: 10)")
    proxy_log_parser.set_defaults(func=cmd_proxy_log)

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

    # Transcripts command group
    transcripts_parser = sub.add_parser("transcripts", help="transcript forensics and search")
    transcripts_sub = transcripts_parser.add_subparsers(dest="transcripts_cmd")

    # transcripts search
    transcripts_search_parser = transcripts_sub.add_parser("search", help="search transcripts by breadcrumb")
    transcripts_search_parser.add_argument("breadcrumb", help="breadcrumb to search for (e.g., s_abc123/c_42/g_xyz/p_def456/t_123)")
    transcripts_search_parser.add_argument("--before", "-B", type=int, default=3,
                                           help="number of messages before target (default: 3)")
    transcripts_search_parser.add_argument("--after", "-A", type=int, default=3,
                                           help="number of messages after target (default: 3)")
    transcripts_search_parser.add_argument("--all", dest="search_all", action="store_true",
                                           help="search all transcripts (not just session from breadcrumb)")
    transcripts_search_parser.add_argument("--format", choices=["full", "compact", "json"], default="full",
                                           help="output format (default: full)")
    transcripts_search_parser.set_defaults(func=cmd_transcripts_search)

    # transcripts list
    transcripts_list_parser = transcripts_sub.add_parser("list", help="list all transcript files")
    transcripts_list_parser.add_argument("--json", dest="json_output", action="store_true",
                                         help="output as JSON")
    transcripts_list_parser.set_defaults(func=cmd_transcripts_list)

    # auto-restart: process supervisor
    ar_parser = sub.add_parser("auto-restart", help="auto-restarting process supervisor")
    ar_sub = ar_parser.add_subparsers(dest="ar_cmd")

    # auto-restart launch
    ar_launch = ar_sub.add_parser("launch", help="launch supervised process in new terminal")
    ar_launch.add_argument("--name", "-n", default="", help="display name (default: command basename)")
    ar_launch.add_argument("--delay", "-d", type=int, default=5, help="restart delay in seconds (default: 5)")
    ar_launch.add_argument("--terminal", "-t", default="auto",
                           choices=["auto", "terminal", "iterm2", "gnome-terminal",
                                    "ptyxis", "kgx", "tilix", "lxterminal", "foot",
                                    "xterm", "konsole", "x-terminal-emulator"],
                           help="terminal app (default: auto-detect)")
    ar_launch.add_argument("--no-tmux", action="store_true",
                           help="do not back the session with tmux (disables send-keys)")
    ar_launch.add_argument("--force", action="store_true",
                           help="override the singleton pre-flight: start even if a live "
                                "supervisor already owns this --name. Without this, launching "
                                "a second supervisor for a name that already has one is refused "
                                "as a fork (GH#210); the sanctioned in-place restart is "
                                "'auto-restart restart <pid>'.")
    ar_launch.add_argument("--post-start-keys", default=None, metavar="KEYS",
                           help="tmux keys to send after every child spawn (initial and each "
                                "restart), e.g. 'Enter' to dismiss a workspace-trust dialog that "
                                "would otherwise hang an unattended session. Requires tmux.")
    ar_launch.add_argument("--post-start-delay", type=int, default=18, metavar="SECS",
                           help="seconds to wait after spawn before sending --post-start-keys "
                                "(default: 18)")
    ar_launch.add_argument("--session-id", default=None,
                           help="pin a session: 'latest' (most recent CC session), 'new' (fresh), "
                                "or an explicit UUID. Exported as MACF_SESSION_ID for the command "
                                "to forward (e.g. claude --session-id). NOTE: CC refuses to attach "
                                "to a session that is still LIVE ('already in use'), so do not pin "
                                "the conversation you are currently in - prefer the command's own "
                                "`-c` for that. Default: unset (command resumes on its own).")
    ar_launch.add_argument("cmd", nargs=argparse.REMAINDER, help="command to supervise (after --)")
    ar_launch.set_defaults(func=lambda args: _cmd_ar_launch(args))

    # auto-restart list
    ar_list = ar_sub.add_parser("list", help="list managed processes (default: running only)")
    ar_list.add_argument("--all", "-a", action="store_true", dest="show_all",
                         help="show all including stopped/dead history")
    ar_list.set_defaults(func=lambda args: _cmd_ar_list(args))

    # auto-restart restart
    ar_restart = ar_sub.add_parser("restart", help="trigger a session resume (restart) for a supervised process")
    ar_restart.add_argument("pid", type=int, help="supervisor PID")
    ar_restart.set_defaults(func=lambda args: _cmd_ar_restart(args))

    # auto-restart disable
    ar_disable = ar_sub.add_parser("disable", help="disable auto-restart for a supervised process")
    ar_disable.add_argument("pid", type=int, help="supervisor PID")
    ar_disable.set_defaults(func=lambda args: _cmd_ar_disable(args))

    # auto-restart status
    ar_status = ar_sub.add_parser("status", help="detailed status of a supervised process")
    ar_status.add_argument("pid", type=int, help="supervisor PID")
    ar_status.set_defaults(func=lambda args: _cmd_ar_status(args))

    # auto-restart kill
    ar_kill = ar_sub.add_parser("kill", help="kill supervisor and child (nuclear option)")
    ar_kill.add_argument("pid", type=int, help="supervisor PID")
    ar_kill.set_defaults(func=lambda args: _cmd_ar_kill(args))

    # auto-restart send-keys
    ar_send = ar_sub.add_parser("send-keys",
                                help="inject text into a supervised tmux session (drives the live CC client)")
    ar_send.add_argument("target", help="supervisor name or PID")
    ar_send.add_argument("--no-enter", action="store_true",
                         help="do not press Enter after the text")
    ar_send.add_argument("keys", nargs=argparse.REMAINDER,
                         help="text to send (after --), e.g. -- /compact")
    ar_send.set_defaults(func=lambda args: _cmd_ar_send_keys(args))

    # ── transcript-monitor ─────────────────────────────────────────────
    tm_parser = sub.add_parser("transcript-monitor", help="JSONL transcript monitoring daemon")
    tm_sub = tm_parser.add_subparsers(dest="tm_cmd")

    tm_start = tm_sub.add_parser("start", help="start transcript monitor daemon")
    tm_start.add_argument("-f", "--foreground", action="store_true", help="run in foreground (don't daemonize)")
    tm_start.add_argument("--interval", type=float, default=1.0, help="poll interval in seconds (default: 1.0)")
    tm_start.set_defaults(func=lambda args: _cmd_tm_start(args))

    tm_sub.add_parser("stop", help="stop transcript monitor daemon").set_defaults(func=lambda args: _cmd_tm_stop(args))
    tm_sub.add_parser("status", help="show transcript monitor status").set_defaults(func=lambda args: _cmd_tm_status(args))

    # ── voice ────────────────────────────────────────────────────────────
    voice_parser = sub.add_parser("voice", help="voice transcription (speech-to-text)")
    voice_sub = voice_parser.add_subparsers(dest="voice_cmd")

    voice_transcribe = voice_sub.add_parser("transcribe", help="transcribe audio file to text")
    voice_transcribe.add_argument("file", help="path to audio file (OGA, WAV, MP3, etc.)")
    voice_transcribe.add_argument("--engine", choices=["mlx", "faster-whisper", "whisper"],
                                  help="force specific engine (auto-detect if omitted)")
    voice_transcribe.add_argument("--model", help="model name/path (engine-specific default)")
    voice_transcribe.add_argument("--language", default="en", help="language code (default: en)")
    voice_transcribe.add_argument("--prompt", dest="initial_prompt",
                                  help="Whisper initial_prompt for vocabulary conditioning")
    voice_transcribe.add_argument("--conditioned", action="store_true", default=True,
                                  help="auto-extract MACF vocabulary for conditioning (default: on)")
    voice_transcribe.add_argument("--no-conditioning", dest="conditioned", action="store_false",
                                  help="disable vocabulary conditioning (raw Whisper)")
    voice_transcribe.add_argument("--correct", action="store_true", default=False,
                                  help="apply fuzzy domain term correction")
    voice_transcribe.add_argument("--json", dest="json_output", action="store_true",
                                  help="output JSON with segments and metadata")
    voice_transcribe.set_defaults(func=cmd_voice_transcribe)

    # voice service subcommands
    voice_service = voice_sub.add_parser("service", help="voice service daemon management")
    voice_svc_sub = voice_service.add_subparsers(dest="voice_svc_cmd")

    voice_svc_start = voice_svc_sub.add_parser("start", help="start voice service daemon")
    voice_svc_start.add_argument("--foreground", action="store_true", help="run in foreground (no daemonize)")
    voice_svc_start.add_argument("--port", type=int, default=9002, help="TCP port (default: 9002)")
    voice_svc_start.add_argument("--model", help="model name/path")
    voice_svc_start.set_defaults(func=cmd_voice_service_start)

    voice_svc_sub.add_parser("stop", help="stop voice service daemon").set_defaults(func=cmd_voice_service_stop)
    voice_svc_sub.add_parser("status", help="show voice service status").set_defaults(func=cmd_voice_service_status)

    # ── idea ─────────────────────────────────────────────────────────────
    idea_parser = sub.add_parser("idea", help="ideas — prospective knowledge capture")
    idea_sub = idea_parser.add_subparsers(dest="idea_cmd")

    idea_create = idea_sub.add_parser("create", help="capture a new idea")
    idea_create.add_argument("--title", "-t", required=True, help="short descriptive title")
    idea_create.add_argument("--category", "-c", required=True,
                             choices=["infrastructure", "consciousness", "tooling", "integration", "research", "methodology"],
                             help="idea category")
    idea_create.add_argument("--description", "-d", default="", help="what the idea is")
    idea_create.add_argument("--sparked-by", dest="sparked_by", default="", help="what triggered this idea")
    idea_create.add_argument("--feasibility", choices=["trivial", "moderate", "significant", "moonshot"], help="estimated effort")
    idea_create.add_argument("--reasoning", default="", help="why this might be valuable")
    idea_create.add_argument("--hypothesis", default="", help="testable prediction")
    idea_create.add_argument("--context", default="", help="what was happening when idea emerged")
    idea_create.add_argument(
        "--wiki-link",
        dest="wiki_link",
        action="append",
        default=None,
        metavar="CONCEPT",
        help="add a wiki-link concept (repeatable, normalized to lowercase_underscored). e.g. --wiki-link audit_trail --wiki-link soft_delete",
    )
    idea_create.add_argument(
        "--wiki-links",
        dest="wiki_links",
        default="",
        metavar="A,B,C",
        help="comma-separated wiki-links. Combines with --wiki-link if both used. e.g. --wiki-links audit_trail,soft_delete,cohort",
    )
    idea_create.set_defaults(func=cmd_idea_create)

    idea_list = idea_sub.add_parser("list", help="list ideas")
    idea_list.add_argument("--status", choices=["captured", "exploring", "promoted", "archived"], help="filter by status")
    idea_list.add_argument("--category", help="filter by category")
    idea_list.add_argument("--json", dest="json_output", action="store_true", help="output as JSON")
    idea_list.set_defaults(func=cmd_idea_list)

    idea_get = idea_sub.add_parser("get", help="get idea details")
    idea_get.add_argument("id", type=int, help="idea ID")
    idea_get.set_defaults(func=cmd_idea_get)

    idea_update = idea_sub.add_parser("update", help="update idea status or wiki-links")
    idea_update.add_argument("id", type=int, help="idea ID")
    idea_update.add_argument("--status", choices=["captured", "exploring", "promoted", "archived"], help="new status")
    idea_update.add_argument("--promoted-to", dest="promoted_to", help="what the idea became (path/ref)")
    idea_update.add_argument(
        "--wiki-link", dest="wiki_link", action="append", metavar="CONCEPT",
        help="add a wiki-link concept (repeatable, normalized to lowercase_underscored)")
    idea_update.add_argument(
        "--wiki-links", dest="wiki_links", metavar="A,B,C",
        help="add wiki-link concepts, comma-separated (combines with --wiki-link)")
    idea_update.add_argument(
        "--remove-wiki-link", dest="remove_wiki_link", action="append", metavar="CONCEPT",
        help="remove a wiki-link concept (repeatable)")
    idea_update.set_defaults(func=cmd_idea_update)

    idea_archive = idea_sub.add_parser("archive", help="archive an idea")
    idea_archive.add_argument("id", type=int, help="idea ID")
    idea_archive.add_argument("--reason", "-r", required=True, help="why this idea is being archived")
    idea_archive.set_defaults(func=cmd_idea_archive)

    idea_search = idea_sub.add_parser("search", help="search ideas by text")
    idea_search.add_argument("query", help="search query")
    idea_search.set_defaults(func=cmd_idea_search)

    idea_graph = idea_sub.add_parser("graph", help="show ideas-only graph (use 'knowledge' for cross-CA)")
    idea_graph.add_argument("--json", dest="json_output", action="store_true", help="machine-readable output")
    idea_graph.add_argument("--tree", action="store_true", help="tree view (most-connected as roots)")
    idea_graph.set_defaults(func=cmd_idea_graph)

    # ── knowledge ────────────────────────────────────────────────────────
    knowledge_parser = sub.add_parser("knowledge", help="cross-CA knowledge graph (ideas + learnings + checkpoints + reflections + observations + experiments + reports)")
    knowledge_sub = knowledge_parser.add_subparsers(dest="knowledge_cmd")

    kg_graph = knowledge_sub.add_parser("graph", help="show cross-CA knowledge graph")
    kg_graph.add_argument("--json", dest="json_output", action="store_true", help="machine-readable output")
    kg_graph.set_defaults(func=cmd_knowledge_graph)

    kg_query = knowledge_sub.add_parser("query", help="query subgraph by concept, node ID, or keyword")
    kg_query.add_argument("term", help="concept name, node ID (#007), or keyword")
    kg_query.add_argument("--json", dest="json_output", action="store_true", help="machine-readable output")
    kg_query.add_argument(
        "--class", dest="node_class",
        choices=["conceptual_authority", "temporal_record", "normative"],
        help="restrict to one node class: conceptual_authority (durable claims), "
             "temporal_record (claims that expire), normative (rules). "
             "Default returns all classes, each labelled.")
    kg_query.set_defaults(func=cmd_knowledge_query)

    kg_gaps = knowledge_sub.add_parser("gaps", help="detect missing wiki-links")
    kg_gaps.add_argument("--json", dest="json_output", action="store_true", help="machine-readable output")
    kg_gaps.set_defaults(func=cmd_knowledge_gaps)

    kg_doctor = knowledge_sub.add_parser(
        "doctor",
        help="report orphans, drift, singletons and registry gaps the graph cannot see")
    kg_doctor.add_argument("--json", dest="json_output", action="store_true",
                           help="machine-readable output")
    kg_doctor.set_defaults(func=cmd_knowledge_doctor)

    kg_viz = knowledge_sub.add_parser("viz", help="generate interactive HTML visualization")
    kg_viz.add_argument("output", nargs="?", default="", help="output path (default: /tmp/macf_knowledge_graph.html)")
    kg_viz.set_defaults(func=cmd_knowledge_viz)

    # ── markdown ─────────────────────────────────────────────────────────
    markdown_parser = sub.add_parser("markdown", help="markdown rendering and presentation")
    markdown_sub = markdown_parser.add_subparsers(dest="markdown_cmd")

    md_present = markdown_sub.add_parser("present", help="render markdown as styled HTML and open in browser")
    md_present.add_argument("filepath", help="path to markdown file")
    md_present.add_argument("--output", "-o", metavar="PATH", default=None,
                            help="output HTML path (default: /tmp/macf_md_*.html)")
    md_present.set_defaults(func=cmd_markdown_present)

    # ── opsec ────────────────────────────────────────────────────────────
    opsec_parser = sub.add_parser("opsec", help="private-context leakage gates for public repos")
    opsec_sub = opsec_parser.add_subparsers(dest="opsec_cmd")
    opsec_install = opsec_sub.add_parser(
        "install-hook",
        help="install a pre-commit gate that rejects staged private-context leaks")
    opsec_install.add_argument("repo", help="path to the target git repository")
    opsec_install.add_argument("--profile", default=None,
                               help="pattern profile JSON (default: agent-home default profile, created if absent)")
    opsec_install.set_defaults(func=cmd_opsec_install_hook)

    # ── shell ────────────────────────────────────────────────────────────
    shell_parser = sub.add_parser("shell", help="shell integration (tab completion)")
    shell_sub = shell_parser.add_subparsers(dest="shell_cmd")
    shell_sub.add_parser("setup", help="print tab completion setup instructions").set_defaults(func=cmd_shell_setup)

    return p


def cmd_opsec_install_hook(args: argparse.Namespace) -> int:
    """Install the private-context leakage pre-commit gate into a repo."""
    from pathlib import Path
    from .opsec import install_hook

    try:
        profile = Path(args.profile) if args.profile else None
        facts = install_hook(Path(args.repo), profile)
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    print("✅ OPSEC pre-commit gate installed")
    print(f"   Repo:    {facts['repo']}")
    print(f"   Hooks:   {facts['hooks_dir']}")
    print(f"   Profile: {facts['profile']} (edit patterns there; NEVER commit it)")
    print("   Bypass for reviewed disclosures: git commit --no-verify")
    return 0


def cmd_markdown_present(args: argparse.Namespace) -> int:
    """Render markdown as styled HTML and open in browser."""
    from .viz.markdown import MarkdownPresenter

    try:
        presenter = MarkdownPresenter(source=args.filepath)
        output = getattr(args, "output", None)
        presenter.present(output_path=output)
        return 0
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    except (OSError, ValueError) as e:
        print(f"❌ Markdown presentation failed: {e}")
        return 1


def cmd_voice_service_start(args) -> int:
    from .voice.service import start_service
    return start_service(port=args.port, model=args.model, foreground=args.foreground)


def cmd_voice_service_stop(args) -> int:
    from .voice.service import stop_service
    return stop_service()


def cmd_voice_service_status(args) -> int:
    from .voice.service import get_service_status
    status = get_service_status()
    if status.get("running"):
        print(f"✅ Voice service running")
        print(f"   Engine: {status.get('engine', '?')}")
        print(f"   Model: {status.get('model', '?')}")
        print(f"   PID: {status.get('pid', '?')}")
        print(f"   Uptime: {status.get('uptime_s', 0)}s")
    else:
        print("⏹️  Voice service not running")
        if status.get("error"):
            print(f"   {status['error']}")
    return 0


def cmd_voice_transcribe(args) -> int:
    """Transcribe audio file to text."""
    from .voice.transcribe import transcribe
    import json as json_mod

    audio_path = args.file
    if not Path(audio_path).exists():
        print(f"❌ File not found: {audio_path}")
        return 1

    # Build initial_prompt: manual --prompt wins, otherwise auto-condition
    prompt = args.initial_prompt
    if prompt is None and args.conditioned:
        try:
            from .voice.vocabulary import build_whisper_prompt
            prompt = build_whisper_prompt()
            print(f"[conditioned: {len(prompt)} chars]", file=sys.stderr)
        except Exception as e:
            print(f"⚠️ MACF: vocabulary conditioning failed ({e}), proceeding unconditioned", file=sys.stderr)

    # Try voice service first (warm model = fast)
    try:
        from .voice.service import is_service_running, send_request
        if is_service_running():
            print("[routing to voice service (warm)]", file=sys.stderr)
            response = send_request({
                "action": "transcribe",
                "file": str(Path(audio_path).resolve()),
                "language": args.language,
                "conditioned": args.conditioned,
                "correct": args.correct,
            })
            if "error" in response:
                print(f"⚠️ Service error: {response['error']}, falling back to direct", file=sys.stderr)
            else:
                text = response.get("corrected_text", response.get("text", ""))
                if args.json_output:
                    print(json_mod.dumps(response, indent=2))
                else:
                    print(text)
                    dur = response.get("duration_ms", 0)
                    print(f"\n[service | {dur}ms]", file=sys.stderr)
                return 0
    except (OSError, ConnectionError) as e:
        print(f"⚠️ MACF: voice service unavailable, falling back to direct transcription: {e}", file=sys.stderr)

    try:
        result = transcribe(
            audio_path=audio_path,
            engine=args.engine,
            model=args.model,
            language=args.language,
            initial_prompt=prompt,
        )
    except RuntimeError as e:
        print(f"❌ {e}")
        return 1
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        return 1

    # Apply fuzzy correction if requested
    text = result.text
    corrections = None
    if args.correct:
        try:
            from .voice.correction import correct_transcript
            corrected = correct_transcript(text)
            text = corrected.corrected_text
            corrections = corrected.corrections
        except Exception as e:
            print(f"⚠️ MACF: correction failed: {e}", file=sys.stderr)

    if args.json_output:
        output = result.to_dict()
        if corrections is not None:
            output["corrected_text"] = text
            output["corrections"] = [
                {"original": c.original, "corrected": c.corrected, "confidence": c.confidence}
                for c in corrections
            ]
        print(json_mod.dumps(output, indent=2))
    else:
        print(text)
        print(f"\n[{result.engine}/{result.model} | {result.duration_audio:.1f}s audio | {result.duration_transcribe:.1f}s transcribe]",
              file=sys.stderr)

    return 0

def main(argv=None) -> None:
    parser = _build_parser()

    # Enable tab completion if argcomplete is installed (optional dependency)
    try:
        import argcomplete
        argcomplete.autocomplete(parser)
    except ImportError:
        pass  # argcomplete not installed — completions silently disabled

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
