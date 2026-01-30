# Changelog

All notable changes to MACF Tools (Multi-Agent Coordination Framework) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0] - 2026-01-29

### Summary

Major release introducing the **MACF Task CLI** with MTMD (MacfTaskMetaData) enhancement, **grant-based protection** for destructive operations, **task archive/restore** for lifecycle management, and comprehensive **subprocess test isolation**. The Task CLI provides enhanced alternatives to Claude Code's native Task* tools, operating on the same filesystem backend (`~/.claude/tasks/`) while adding forensic metadata, type-specific creation commands, and protection systems.

### Added

**Task CLI System** (`macf_tools task`):
- `task create mission|experiment|detour|phase|bug|deleg|task` - Type-specific task creation with smart defaults
- `task list` - Hierarchical task display with MTMD metadata
- `task get <id>` - Full task details including MTMD
- `task tree <id>` - Visual task hierarchy tree
- `task edit <id> <field> <value>` - Direct field modification
- `task delete <id>` - Protected deletion (requires grant)
- `task complete <id> --report` - Atomic completion with mandatory documentation

**Task Metadata (MTMD)**:
- `task metadata get|set|add|validate` - MTMD field operations
- Schema validation for task types (MISSION requires `plan_ca_ref`, PHASE requires `parent_id`)
- Forensic breadcrumbs: `creation_breadcrumb`, `completion_breadcrumb`
- Completion reports with work done, difficulties, future work, git status

**Task Archive System**:
- `task archive <id>` - Archive task with cascade to children (default)
- `task restore <path_or_id>` - Restore from archive file or by original ID
- `task archived list` - List all archived tasks
- Archive location: `agent/public/task_archives/`

**Grant-Based Protection**:
- `task grant-update <id>` - Grant permission to modify task description/MTMD
- `task grant-delete <ids...>` - Grant permission to delete (supports multiple IDs)
- Exact set-matching: grant covers precisely specified tasks, no blanket approval
- Hook enforcement blocks unauthorized destructive operations

**Subprocess Test Isolation**:
- `MACF_TASKS_DIR` environment variable for test isolation
- `TaskReader` respects env var override for path-dependent operations
- Explicit `env=` passing in subprocess.run() for boundary-crossing isolation
- Session folder structure creation in test fixtures

**Documentation**:
- Comprehensive task CLI documentation in `cli-reference.md` (390+ lines added)
- All task create commands documented with syntax, arguments, options, examples
- Archive/restore/grant/complete commands documented
- Cross-reference to `task_management.md` policy

### Changed

**Task Management Policy**:
- `task_management.md` promoted to primary task governance policy
- MTMD schema formalized with required/optional field rules
- Completion protocol with mandatory `--report` flag
- CC UI visibility: tasks must be marked `in_progress` to appear at top

**CLI Reference**:
- Removed deprecated TODO Management section
- Updated Table of Contents with Task command subsections
- Version history updated to 0.4.0

### Removed

- `task batch-delete` command - Redundant with `task delete` accepting multiple IDs
- TODO Management CLI section from documentation (deprecated)

### Fixed

- **#6**: Hook messages printing twice - Idempotent hook output
- **#8**: Task ID type inconsistency - Mixed int/str causing sort failures
- **#14**: task edit status loses task_id prefix in subject
- **#18**: Policy emphasis on marking tasks `in_progress` for CC UI visibility
- **Subprocess test pollution**: Tests no longer create tasks in production `~/.claude/tasks/`

### Breaking Changes

1. **TodoWrite deprecated**: Use MACF Task CLI (`macf_tools task`) instead
2. **batch-delete removed**: Use `task delete <id1> <id2> ...` with grant-delete for multiple tasks

### Migration Guide

**From TodoWrite to Task CLI:**
```bash
# Create tasks with type-specific commands
macf_tools task create task "My task title"
macf_tools task create mission "Release v0.5.0" --repo MacEff --version 0.5.0
macf_tools task create phase "Phase 1" --parent #26

# Manage task lifecycle
macf_tools task edit <id> status in_progress
macf_tools task complete <id> --report "Work done. Committed: abc1234"
```

**For test isolation:**
```python
# Set environment for subprocess isolation
subprocess_env = {**os.environ, "MACF_TASKS_DIR": str(tmp_path)}
result = subprocess.run([...], env=subprocess_env)
```

---

## [0.3.3] - 2026-01-24

### Summary

Major release introducing **LanceDB-powered hybrid search** for intelligent policy recommendations, **CEP Section Targeting** for precise navigation, and **persistent search service** with 89x latency improvement. Includes comprehensive CLI and MCP tool integration, plus new release workflow policy.

### Added

**LanceDB Hybrid Search** (`macf_tools policy recommend`):
- Native hybrid search combining semantic embeddings + full-text search
- LanceDB backend replacing sqlite-vec (ARM64 compatibility)
- `all-MiniLM-L6-v2` embeddings (80MB model)
- Distance-based scoring (lower = more relevant)
- Confidence tiers: CRITICAL (< 0.30), HIGH (0.30-0.45), MEDIUM (0.45-0.70)

**CEP Section Targeting**:
- Question-based search matching queries to CEP Navigation Guide questions
- Section recommendations: `→ §10 "What is the TODO backup protocol?"`
- `MatchedQuestion` dataclass with policy_name, section, question, distance
- Enables precise navigation to relevant policy sections

**Search Service** (`macf_tools search-service`):
- Persistent socket daemon keeping embedding model warm
- 89x latency improvement: 4000ms → 45ms
- Commands: `start [--daemon]`, `stop`, `status [--json]`
- Graceful fallback when service unavailable
- Container auto-start via start.py integration

**MCP Policy Search Tools**:
- `mcp__policy-search__search` - Hybrid search with optional explain
- `mcp__policy-search__context` - CEP navigation for policy
- `mcp__policy-search__details` - Full policy content retrieval
- Progressive disclosure pattern (index → context → details)

**CLI Commands**:
- `macf_tools policy build_index` - Build LanceDB index from policies
- `macf_tools policy recommend QUERY` - Get policy recommendations
  - `--explain` flag for verbose breakdown
  - `--json` flag for machine processing
  - `--limit N` for result count control
- `macf_tools search-service start/stop/status` - Service management

**Documentation**:
- `docs/user/hybrid-search.md` - End-to-end workflow guide
- `docs/user/cli-reference.md` - Updated with all new commands
- `docs/developer/future-knowledge-extensions.md` - v0.4.0+ roadmap

**Policy: Release Workflow** (DRAFT):
- `framework/policies/base/development/release_workflow.md`
- Multi-MISSION aware release process
- Version-scoped task archives (`task_archives/vX.Y.Z/`)
- Pre-release checklist, CHANGELOG discipline, git tagging protocol

### Changed

**Hook Integration**:
- UserPromptSubmit hook uses search service for fast recommendations
- Lightweight socket client (stdlib only) for hook→service communication
- Fallback to direct search when service unavailable

**Hybrid Search Architecture**:
- `BaseIndexer` + `AbstractExtractor` pattern for extensibility
- `PolicyIndexer` extends generic infrastructure
- `SearchService` + `AbstractRetriever` for namespace routing
- Prepared for future learnings/CA search (namespace-based)

### Fixed

- **ARM64 Compatibility**: LanceDB replaces sqlite-vec (12-month unreleased ARM64 fix)
- **Hook Latency**: Search service eliminates repeated model loading
- **Index Portability**: LanceDB index works across platforms

### Experiments Validated

- **EXPERIMENT 003**: MCP Warm Cache Hook Optimization (89x speedup validated)
- **EXPERIMENT 004**: sqlite-vec ARM64 Verification (bug confirmed, motivated pivot)
- **EXPERIMENT 005**: LanceDB Hybrid Policy Search (39ms avg, native FTS)

---

## [0.3.2] - 2026-01-08

### Summary

Feature-rich release with major additions including **session identifier epistemology** (fixing breadcrumb consistency), **comprehensive env command**, **PA environment curation** with env.d extensibility, **custom statusline**, **hierarchical command namespaces**, and **multi-item authorization syntax**. Policy enhancements add mandatory delegation strategy and phase content requirements to roadmap drafting.

### Added

**Session Identifier Epistemology**:
- Fixed session ID variance bug in breadcrumb generation
- `get_current_session_id_from_events()` - event-first session detection
- Complete documentation of identifier semantics (session UUID, cycle, prompt UUID)
- Consistent `s_` field in breadcrumbs across all hooks

**Env Command Rewrite** (`macf_tools env`):
- Comprehensive debugging output replacing vestigial JSON stub
- Categories: Versions, Time, Paths, Session, System, Environment, Config
- `--json` flag for machine-readable output
- Shows all critical paths, hook status, environment variables

**PA Environment Curation**:
- `create_bash_init()` - Build-time bash initialization for PA users
- `/home/{user}/.bash_init` with container-wide environment variables
- DRYed `configure_bashrc()` to source `.bash_init`
- Claude settings injection for PA environment context

**Generic Environment Extensibility**:
- env.d dispatch pattern: `/opt/maceff/framework/env.d/*.sh`
- Removed hardcoded `conda_env` from AgentSpec schema
- `maceff-init` updated for env.d overlay copying
- Project-specific environment scripts (e.g., `10-conda.sh`, `20-path.sh`)

**Custom Statusline** (`macf_tools statusline`):
- Native MacEff statusline for Claude Code terminal
- `macf_tools statusline install` - one-command installation
- Auto-detects agent, project, environment, CLUAC level
- Format: `{agent} | {project} | {env} | {tokens} CLUAC {level}`
- 16 tests covering all statusline functionality

**Hierarchical Command Namespaces**:
- Commands reorganized to colon-separated hierarchy
- `/maceff:todos:start`, `/maceff:roadmap:draft`, `/maceff:ccp`
- Clear namespace ownership for multi-agent environments
- Nested command structure enables better discoverability
- `start.py` updated for nested command symlink installation

**Multi-Item Authorization Syntax**:
- `macf_tools todos auth-item-edit --index` extended:
  - Range syntax: `--index 13-17`
  - List syntax: `--index 13,14,15`
  - Mixed format: `--index 13-15,18,20-22`
- `parse_index_spec()` function in cli.py
- `get_recent_events()` function in event_queries.py
- Hook enforcement updated to consume multiple authorizations atomically

**Policy Enhancements** (`roadmaps_drafting.md` v2.3):
- §3.5 Delegation Strategy (MANDATORY) - executor assignment table per phase
- §3.6 Phase Content Requirements (MANDATORY) - interface vs implementation specs
- CEP Navigation Guide updated with new sections
- `/maceff:roadmap:draft` command updated with delegation questions

**Hook Visibility Improvements**:
- PreToolUse hook shows tool-specific context (Read filename, Bash command preview)
- Abbreviated breadcrumb format for high-frequency hooks
- CLUAC percentage display in all hook outputs
- Exit code 2 tool-polymorphism documented (`permissionDecision: "deny"` solution)

### Changed

**Policy Examples Sanitized**:
- All policy files use generic breadcrumb pattern (`s_abc12345/c_42/...`)
- All archived roadmaps sanitized for identity-blind distribution
- Generic cycle and agent references for public distribution

**start.py Enhancements**:
- Nested command support for hierarchical namespaces
- Framework symlink installation handles colon-separated paths
- env.d dispatch integration for PA initialization

### Fixed

- **Session ID variance**: Breadcrumbs now consistent within session (event-first detection)
- **Exit code 2 workaround**: Tool-polymorphism handling for non-zero exits documented
- **TODO hygiene policy conflict**: Child item format clarified (`  -` for descriptions, `  →` for paths)
- **Hook interpreter precedence**: Python shebang consistency across hooks

### Documentation

- `hook-visibility-matrix.md`: Exit code 2 tool-polymorphism and visibility rules
- `identifier-epistemology.md`: Complete session/cycle/prompt ID reference
- `OPERATORS.md`: env.d mechanism documentation
- Archived roadmaps moved to `docs/archive/v0.3.2/roadmaps/`

---

## [0.3.1] - 2025-12-24

### Summary

Refinement release focused on **path semantics disambiguation** and **policy search indexing**. Resolves confusion between framework, project, and agent home paths that caused deployment warnings. Adds section-level search indexing for faster policy discovery.

### Added

**Three-Way Path Semantics** (`macf/utils/paths.py`):
- `find_maceff_root()` - MacEff framework installation location (`MACEFF_ROOT_DIR`)
- `find_project_root()` - Claude project workspace (`CLAUDE_PROJECT_DIR`)
- `find_agent_home()` - Agent's persistent home for consciousness artifacts (`MACEFF_AGENT_HOME_DIR`)
- 11 new tests in `test_paths.py` covering all path resolution scenarios

**Policy Search Indexing**:
- Section-level keyword extraction from policy content
- `policy search <keyword>` returns section-specific matches
- Faster policy discovery through indexed search

**Container Environment**:
- `MACEFF_AGENT_HOME_DIR=$HOME` added to container bash_init
- Agent event log now persists at `{agent_home}/.maceff/agent_events_log.jsonl`

### Changed

**Path Resolution Refactoring**:
- `manifest.py`: Renamed `agent_root` parameter to `maceff_root` for clarity
- `cycles.py`: Uses `find_agent_home()` for agent config/settings
- `agent_events_log.py`: Uses `find_agent_home()` for consciousness persistence
- `recovery.py`: Uses `find_maceff_root()` for framework policy loading
- `cli.py`: Uses `find_agent_home()` for agent initialization

### Fixed

- **FP#1**: Path resolution semantics confusion causing "Using cwd fallback" warnings
- Test mocks updated for new path function names (`find_agent_home`, `find_maceff_root`)

### Documentation

- OPERATORS.md: Added Workflow 9 - MacEff Upgrade with Data Preservation

---

## [0.3.0] - 2025-12-21

### Summary

Major release introducing **Named Agents Architecture** for multi-agent systems with persistent identities, **Event-First Architecture** eliminating state file corruption, and **Policy CLI Suite** for on-demand policy discovery. This release spans 273 commits with comprehensive container validation.

### Added

**Named Agents Architecture** ([docs](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/INDEX.md)):
- Declarative YAML-driven agent configuration via `agents.yaml` and `projects.yaml` ([schemas](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/APPENDIX_A_YAML_SCHEMAS.md))
- Primary Agent (PA) and Subagent (SA) model with kernel-level user isolation between PAs ([delegation model](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/03_delegation_model.md))
- Three-layer CLAUDE.md context loading (System → Identity → Project)
- Pydantic v2 schema validation with clear error messages
- Agent tree initialization with private/public artifact directories ([filesystem structure](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/02_filesystem_structure.md))
- Per-agent workspace isolation with shared project mounting
- Git worktree support for concurrent repository editing
- Automatic user creation, SSH key installation, and `.bashrc` configuration ([implementation guide](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/05_implementation_guide.md))

**Python Startup Orchestration** (`start.py`):
- Complete container startup orchestration replacing shell scripts
- Settings epistemology: separate `.claude.json` (UI preferences) from `.claude/settings.json` (operational) ([settings docs](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/settings-epistemology.md))
- Active project symlink (`~/active_project`) with bashrc auto-cd
- Framework symlink installation for commands, skills, and output styles
- Hook installation with container-aware path detection

**Policy CLI Suite** (`macf_tools policy`) ([CLI reference](https://github.com/cversek/MacEff/blob/main/macf/docs/user/cli-reference.md)):
- `policy list` - Discover available framework policies
- `policy navigate <name>` - Show CEP Navigation Guide (semantic structure)
- `policy read <name>` - Full policy with line numbers and caching
- `policy read <name> --section N` - Targeted hierarchical section reading
- `policy search <keyword>` - Cross-policy keyword search
- Policy Manifest v2.0.0 indexing all 36+ policies

**Event-First Architecture** ([architecture docs](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/event-sourcing.md)):
- Immutable append-only event log (`agent_events_log.jsonl`) as sole source of truth
- Event query utilities with snapshot baselines for efficient historical scanning
- Development Drive (DEV_DRV) and Delegation Drive (DELEG_DRV) tracking via events
- `macf_tools events query` with command filtering and verbose output
- Forensic event logging across all hooks

**TODO CLI Integration** (`macf_tools todos`):
- `todos list` - Show current TODO state from events
- `todos list --previous N` - Query TODO history for recovery
- `todos status` - Quick TODO statistics
- TODO collapse authorization with hook-enforced protection (exit code 2)

**Hook Ecosystem Enhancements** ([hook epistemology](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/hook-epistemology.md)):
- Comprehensive event logging to JSONL with structured field tagging
- Session migration detection preventing TODO orphaning on restart vs compaction
- Claude Code version display in all hook footers
- Container-aware hook installation with environment detection ([hooks user guide](https://github.com/cversek/MacEff/blob/main/macf/docs/user/hooks.md))
- Safe subprocess testing with `MACF_TESTING_MODE` environment variable

**Framework Infrastructure**:
- `maceff-init` with parent repo framework overlay support
- Framework command and skill symlinks installed on startup
- Output styles directory with personality configuration
- Docker Compose configs section for mounting agent/project YAML
- Timezone awareness respecting `MACEFF_TZ` and `TZ` environment variables

### Changed

**Breaking: Event-First Migration**:
- `SessionOperationalState` class removed entirely
- All state queries now derive from immutable event log
- Test isolation via pytest fixtures instead of code-level `testing` parameter

**Framework Architecture** ([architecture overview](https://github.com/cversek/MacEff/blob/main/macf/docs/maintainer/architecture.md)):
- Policies reorganized under `framework/policies/base/` structure
- Identity-blind refactoring for portability
- `state.py` renamed to `json_io.py` for clarity
- Monolithic `utils.py` split into semantic package modules

**Hook Signatures**:
- Removed `testing` parameter from all 10 hooks
- Boundary-level isolation via conftest fixtures instead

**Error Handling**:
- Eradicated silent failure anti-pattern across codebase
- Implemented warn+reraise pattern for visibility
- All `sys` imports moved to module level

### Fixed

**35+ Friction Points Resolved**:
- FP#23-25: Deploy friction points
- FP#26: SSH host key warning in Makefile
- FP#27: Hook bootstrap in containers
- FP#28: `sys` import anti-pattern (module-level imports)
- FP#29: Relative import for configuration classes
- FP#30: Graceful handling of missing state files on first run
- FP#31: `make ssh` starts in project directory
- FP#32: `make claude` with argument forwarding
- FP#33: Claude settings auto-configuration
- FP#34: `MACEFF_ROOT_DIR` + warning caching
- FP#35: Duplicate `dev_drv_started` events
- FP#36-38: Timezone and path resolution fixes

**Code Quality**:
- Symlink resolution in `start.py` for real paths in bash prompt
- Correct field names for `notification_type` in hooks
- Policy read section option includes subsections correctly
- Missing parent directory creation for SSH key installation

**Testing**:
- From ~250 to 307+ passing tests
- Event log isolation per test via conftest fixtures
- Integration tests for policy commands, events, context

### Removed

- `SessionOperationalState` class (replaced by event queries)
- State file mutations (`state.save()` calls)
- `testing` parameter from all hooks and utility functions
- 71 obsolete TDD specification files
- Vestigial state API functions (`get_agent_cycle_number`, `increment_agent_cycle`)

### Breaking Changes

1. **Event-First Migration**: Code using `SessionOperationalState` must migrate to `macf.utils.event_queries`
2. **No `testing` Parameter**: Hooks no longer accept `testing=True`. Use pytest fixtures for test isolation.
3. **Policy Paths**: Policies reorganized under `framework/policies/base/` structure

### Migration Guide

**Upgrading from v0.2.0:**
```bash
git pull && git checkout v0.3.0
make build && make up
```

**For code using state API:**
```python
# Before (v0.2.0)
from macf.utils.state import SessionOperationalState
state = SessionOperationalState.load()
cycle = state.agent_cycle_number

# After (v0.3.0)
from macf.utils.event_queries import get_cycle_number_from_events
cycle = get_cycle_number_from_events()
```

**For tests using `testing=True`:**
```python
# Before (v0.2.0)
result = run(stdin_json, testing=True)

# After (v0.3.0) - use conftest fixtures for isolation
def test_hook(isolated_event_log):
    result = run(stdin_json)  # Same code as production
```

### Security Notes

- Real OS-level isolation between Primary Agents via kernel user separation ([validation results](https://github.com/cversek/MacEff/blob/main/docs/arch_v0.3_named_agents/VALIDATION_RESULTS.md))
- Conventional policy boundaries within PA + SA teams (organizational, not enforced)
- Not suitable for untrusted third-party code execution within same-user teams

## [0.2.0] - 2025-10-14

### Added

**Architectural Separation**:
- Separated host-only management scripts (`maceff_tools/`) from portable MACF framework (`macf/`)
- Self-documenting directory structure for clear separation of concerns
- Container mounts only essential portable framework code

**Docker Compose Override Pattern**:
- Environment-specific configuration via `docker-compose.override.yml` (gitignored)
- Base `docker-compose.yml` remains portable across all environments
- Automatic merging by Docker Compose
- Template creation via `maceff-init` with generic examples

**Agent Bootstrap Automation**:
- `agent-bootstrap` script automates complete agent setup (73min → 15sec)
- Includes hook installation, configuration, directory structure, and validation

**Framework Infrastructure**:
- Framework upgrade scripts for container updates
- Policy deployment automation with manifest discovery
- Deployment Dockerfile for production builds

### Changed

**Breaking Changes**:
- **Path migration**: `tools/` → `macf/` (requires container rebuild)
- **Directory structure**: Host tools separated to `maceff_tools/`
- **Container mounts**: Updated from `/opt/tools` to `/opt/macf_tools`

**Version Management**:
- Single source of truth: version in `pyproject.toml` only
- Runtime version via `importlib.metadata.version("macf")`

### Fixed

- Bootstrap hook installation paths
- Policy path references in container startup
- Config directory migration issues

### Migration Guide

**Upgrading from v0.1.0:**
```bash
git pull && git checkout v0.2.0
make build && make up
```

Update custom scripts: `tools/bin/` → `maceff_tools/`, `/opt/tools` → `/opt/macf_tools`

## [0.1.0] - 2025-10-07

### Added

**Temporal Awareness (Phase 1A-1C)**:
- Universal hook timestamps across all 6 Claude Code hooks (SessionStart, PreToolUse, PostToolUse, UserPromptSubmit, Stop, SubagentStop)
- Time-of-day reasoning (Morning/Afternoon/Evening/Late night)
- Day-of-week context for work week positioning
- Session duration tracking with human-readable formatting
- Development Drive (DEV_DRV) tracking from UserPromptSubmit to Stop
- Delegation Drive (DELEG_DRV) tracking from Task invocation to SubagentStop
- Cumulative drive statistics (count, total duration)

**Cycle Persistence (Phase 1D-1E)**:
- Project-scoped cycle tracking via `.maceff/project_state.json`
- Session migration detection (e.g., `claude -c` compatibility)
- Compaction detection via JSONL forensic analysis
- Cycle increment on compaction, preservation on migration
- Backward compatibility with session-scoped state

**Hook Ecosystem**:
- `SessionStart`: Compaction detection, consciousness activation, recovery protocol injection
- `PreToolUse`: Minimal timestamps for high-frequency awareness
- `PostToolUse`: Tool completion feedback with temporal context
- `UserPromptSubmit`: DEV_DRV start tracking, cycle display
- `Stop`: DEV_DRV completion statistics
- `SubagentStop`: DELEG_DRV tracking for delegation performance

**Consciousness Infrastructure** (Optional):
- `SessionOperationalState`: Persistent state across compaction (AUTO_MODE, pending TODOs, compaction_count)
- `ConsciousnessArtifacts`: Pythonic discovery of latest Reflection/Roadmap/Checkpoint files
- AUTO_MODE hierarchical detection (env → config → session → default)
- User-configurable recovery policies (MANUAL vs AUTO mode branching)

**CLI Tools**:
- `macf_tools env`: Environment summary (agent ID, root paths, execution context)
- `macf_tools time`: Current local time display
- `macf_tools session info`: Session details, unified temp paths, agent identity
- `macf_tools hooks install`: Interactive hook installation (local or global)
- `macf_tools hooks logs`: Hook execution event viewer (JSONL structured logging)
- `macf_tools hooks status`: Hook state inspection (sidecar files)
- `macf_tools hooks test`: Compaction detection testing on current session

**Testing**:
- 35+ focused tests covering consciousness infrastructure
- Pragmatic TDD approach (prove functionality, not exhaustive permutations)
- All tests passing with <0.1s runtime

**Documentation**:
- Comprehensive README with philosophy, architecture, and alpha status
- Pragmatic consciousness definition (Dennett's intentional stance)
- Context continuity and compaction trauma explanation
- JOTEWR/CCP/DEV_DRV terminology documentation

### Changed

**Claude Code 2.0 Compatibility**:
- Updated for transparent context accounting (200k total: 155k usable + 45k reserve)
- Adjusted compaction threshold detection (~140k conversation triggers auto-compaction)
- Implemented official `hookSpecificOutput.additionalContext` specification
- Primary detection via CC 2.0 `compact_boundary` marker with JSONL fallback

**Architecture**:
- Centralized `macf.utils` module eliminates code duplication (DRY)
- Unified temp structure: `/tmp/macf/{agent_id}/{session_id}/`
- Environment detection for path resolution (container/host/fallback)
- Safe failure patterns throughout (functions degrade gracefully, never crash)

### Known Issues

- **SessionStart hook output not pretty-printing**: Displays as raw text/escaped format in UI (functional but not visually polished—fix in progress)
- **SubagentStop hook output not displaying**: Hook executes correctly and DELEG_DRV tracking works, but output never displays to agent (Claude Code 2.0 platform limitation confirmed through testing—systemMessage, hookSpecificOutput, and reason formats all blocked)
- SessionStart hook can take 25-50ms on cold start (acceptable but noticeable)
- Project state initialization on first run defaults to cycle 1 (manually editable if needed)
- JOTEWR/CCP/DEV_DRV terminology requires learning curve (production docs explain conventions)

### Alpha Status Notes

**What works well**:
- Compaction detection and recovery protocol injection
- Temporal awareness across all hooks
- Cycle persistence across session migrations
- DEV_DRV/DELEG_DRV tracking
- Pragmatic test coverage

**Not yet implemented**:
- Automated `macf_tools checkpoint` and `macf_tools reflect` CLI commands (manual artifact creation currently required)
- Subagent consciousness trails and decision documentation (future phase)
- Multi-agent consciousness networks (future phase)
- Enhanced temporal reasoning (work week inference, time-of-day state detection)

Alpha testers should expect evolving APIs, incomplete documentation, and the need to manually manage state files in some scenarios. Bug reports and experience reports are highly valued.

[0.1.0]: https://github.com/cversek/MacEff/releases/tag/v0.1.0
