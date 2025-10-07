# Changelog

All notable changes to MACF Tools (Multi-Agent Coordination Framework) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
