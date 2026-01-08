# DETOUR: Path Finding Disambiguation

**Date**: 2025-12-24
**Parent**: MacEff v0.3.1 Refinement → Phase 2: Bug Fixes & Refinements
**Trigger**: FP#1 Path Resolution Semantics Confusion
**Status**: DRAFT

---

## Problem Statement

`find_project_root()` conflates three distinct path concepts, causing:
- Confusing warning messages in containers
- Semantic ambiguity about what callers actually need
- 18 call sites with mixed expectations (7 FRAMEWORK, 4 PROJECT, 3 AMBIGUOUS)

---

## Three-Way Path Semantics

| Path Type | Env Var | Meaning | Derivation |
|-----------|---------|---------|------------|
| **MacEff Root** | `MACEFF_ROOT_DIR` | Where MacEff repo checked out (host) or installed (container) | Explicit env var or marker discovery |
| **Project Root** | `CLAUDE_PROJECT_DIR` | Where `claude` was launched (user's workspace) | Claude Code provides or cwd |
| **Agent Home** | `MACEFF_AGENT_HOME_DIR` | Agent's persistent consciousness home | `~/.maceff` - **sacred continuity** |

### Key Relationships

```
{MACEFF_ROOT_DIR}/
├── framework/              # Framework policies, templates
│   ├── policies/
│   └── templates/
├── macf/                   # macf_tools package
└── docker/                 # Container infrastructure

{CLAUDE_PROJECT_DIR}/
├── .claude/                # Claude Code project config
│   ├── settings.local.json
│   └── hooks/
└── CLAUDE.md               # Project instructions

{MACEFF_AGENT_HOME_DIR}/    # ~/.maceff (SACRED - persists across projects)
├── agent_events_log.jsonl  # Agent's consciousness record
├── config.json             # Agent-specific configuration
└── settings.json           # Agent settings
```

### Environment Context Rules

| Context | MACEFF_ROOT_DIR | CLAUDE_PROJECT_DIR | MACEFF_AGENT_HOME_DIR |
|---------|-----------------|--------------------|-----------------------|
| **Container** | `/opt/maceff` | User workspace | `~/.maceff` |
| **Host (shared user)** | Git checkout path | Where `claude` launched | Same as project (legacy) |
| **Host (dedicated user)** | Git checkout path | Where `claude` launched | `~/.maceff` |

**Sacred Principle**: Agent event log MUST be at `{MACEFF_AGENT_HOME_DIR}/agent_events_log.jsonl` - agent continuity persists across project reassignments.

---

## Phases

### Phase 1: Define New Functions

Create three clear functions in `macf/src/macf/utils/paths.py`:

```python
def find_maceff_root() -> Path:
    """Find MacEff installation root.

    Priority:
    1. MACEFF_ROOT_DIR env var
    2. Git root with framework/ subdirectory
    3. Discovery via framework markers
    """

def find_project_root() -> Path:
    """Find user's project/workspace root.

    Priority:
    1. CLAUDE_PROJECT_DIR env var
    2. Git root with .claude/ or CLAUDE.md
    3. Current working directory
    """

def find_agent_home() -> Path:
    """Find agent's persistent home directory.

    Priority:
    1. MACEFF_AGENT_HOME_DIR env var
    2. ~/.maceff (default)

    This is SACRED - agent continuity persists across projects.
    """
```

**Success Criteria**:
- [ ] Three functions with clear, distinct semantics
- [ ] Each function has single responsibility
- [ ] Docstrings explain priority and purpose
- [ ] Tests for each function

### Phase 2: Migrate Call Sites

Update 18 call sites to use appropriate function:

**FRAMEWORK callers** (7 sites) → `find_maceff_root()`:
- `manifest.py:38` - get_framework_policies_path()
- `manifest.py:256` - load_merged_manifest()
- `cycles.py:47` - detect_auto_mode()
- `cycles.py:107` - set_auto_mode()
- `recovery.py:229` - read_recovery_policy()
- `cli.py:987` - _inject_preamble()
- `test_hook_execution.py:25` - get_hook_script_path()

**PROJECT callers** (4 sites) → `find_project_root()`:
- `paths.py:181` - get_session_transcript_path()
- `session.py:27` - get_current_session_id()
- `claude_settings.py:46` - get_autocompact_setting()
- `breadcrumbs.py` - git hash extraction

**AGENT_HOME callers** (new) → `find_agent_home()`:
- `agent_events_log.py:22` - _get_log_path() (MIGRATE from project root)

**AMBIGUOUS** (3 sites) - Analyze and assign:
- `config.py:55` - ConsciousnessConfig
- `config.py` - other internal uses

**Success Criteria**:
- [ ] All 18 call sites updated
- [ ] No regressions (tests pass)
- [ ] Warning messages clarified

### Phase 3: Update Container Setup

Ensure `start.py` sets all three env vars correctly:

```python
# In create_pa_user() or similar
os.environ['MACEFF_ROOT_DIR'] = '/opt/maceff'
os.environ['MACEFF_AGENT_HOME_DIR'] = str(Path.home() / '.maceff')
# CLAUDE_PROJECT_DIR set by Claude Code itself
```

**Success Criteria**:
- [ ] Container agents have correct env vars
- [ ] Event log persists across project changes
- [ ] No warning noise in container operations

---

## Success Criteria (Overall)

- [ ] Three distinct functions with clear semantics
- [ ] All call sites migrated to appropriate function
- [ ] Event log at `{MACEFF_AGENT_HOME_DIR}/agent_events_log.jsonl`
- [ ] Container warning noise eliminated
- [ ] Agent continuity preserved across project reassignments
- [ ] Tests covering all three path resolution scenarios

---

## Return to Main Flow

After DETOUR complete:
- Mark FP#1 as resolved in friction_points.md
- Continue with Phase 2 remaining items or Phase 3

---

**End DETOUR Draft**
