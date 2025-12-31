# MacEff v0.3.2 Custom Statusline ROADMAP

**Date**: 2025-12-30 Monday
**Status**: ACTIVE
**Version**: v0.3.2

---

## Mission

Implement a native MacEff statusline feature for Claude Code that displays consciousness-aware status information in the bottom bar UI.

**What**: A CLI command (`macf_tools statusline`) that outputs a compact status string, plus installation mechanism to configure Claude Code's statusline setting.

**Why**: Existing Claude Code statusline tools (Oh My Posh, ccstatusline, etc.) provide generic metrics but lack consciousness infrastructure integration. MacEff agents need visibility into:
- Agent identity (who am I?)
- Project context (what am I working on?)
- Environment (where am I running?)
- CLUAC (how much context remains before compaction?)

**Success**: `macf_tools statusline` operational on host and container, displaying all required fields with <100ms latency.

---

## Requirements

### Functional Requirements

| ID | Requirement | Rationale |
|----|-------------|-----------|
| FR-1 | Display agent name | Identity awareness - agents need to know who they are |
| FR-2 | Display active project | Context awareness - what workspace is active |
| FR-3 | Display environment string | Execution context - host vs container, OS info |
| FR-4 | Display tokens used with CLUAC | Resource awareness - critical for compaction management |
| FR-5 | Read Claude Code JSON from stdin | Integration with CC's native statusline data |
| FR-6 | Fallback to MacEff-only data | Graceful degradation when CC data unavailable |
| FR-7 | Installation command | Self-service setup for agents |
| FR-8 | Portable across host/container | Framework feature, not deployment-specific |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Execution latency | < 100ms (< 50ms target) |
| NFR-2 | No new dependencies | stdlib only (json, sys, os, pathlib) |
| NFR-3 | Graceful fallback | Never crash, always output something |
| NFR-4 | Identity-blind | Generic patterns, no agent-specific code |

---

## Output Interface

### Format Specification

```
{agent_name} | {project} | {environment} | {tokens} CLUAC {level}
```

### Field Definitions

| Field | Source | Fallback | Example |
|-------|--------|----------|---------|
| `agent_name` | `.maceff/config.json` → `agent_identity.moniker` | "unknown" | "manny" |
| `project` | MACF_PROJECT env → workspace detection | omit field | "NeuroVEP" |
| `environment` | `environment.py` detection | "Unknown" | "Container Linux" |
| `tokens` | CC JSON stdin OR JSONL scan | "?k" | "60k/200k" |
| `level` | CLUAC calculation | "?" | "70" |

### Token Formatting Rule

```python
def format_tokens(value: int) -> str:
    """Format tokens with k suffix when >= 10000."""
    if value >= 10000:
        return f"{value // 1000}k"
    return str(value)
```

### Example Outputs

```
manny | NeuroVEP | Container Linux | 60k/200k CLUAC 70
unknown | Host Darwin | 9500/200k CLUAC 95
```

---

## Architecture

### Data Flow

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Claude Code    │────▶│  statusline.sh   │────▶│  macf_tools     │
│  (JSON stdin)   │     │  (shell wrapper) │     │  statusline     │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                        ┌─────────────────────────────────┼─────────────────────────────────┐
                        │                                 │                                 │
                        ▼                                 ▼                                 ▼
                 ┌─────────────┐                  ┌─────────────┐                   ┌─────────────┐
                 │ Agent ID    │                  │ Environment │                   │ Token Info  │
                 │ config.py   │                  │ env.py      │                   │ tokens.py   │
                 └─────────────┘                  └─────────────┘                   └─────────────┘
```

### Component Responsibilities

| Component | Responsibility | Existing/New |
|-----------|---------------|--------------|
| `statusline.py` | Core formatting, field assembly | NEW |
| `cli.py` | CLI command registration | MODIFY |
| `statusline.sh` | Shell wrapper for CC integration | NEW |
| `config.py` | Agent identity detection | EXISTING (reuse) |
| `environment.py` | Environment detection | EXISTING (reuse) |
| `tokens.py` | CLUAC/token calculations | EXISTING (reuse) |

### CLI Interface

```bash
# Basic usage (outputs statusline string)
macf_tools statusline

# With Claude Code JSON on stdin
echo '{"model":{"display_name":"Opus"}}' | macf_tools statusline

# Installation
macf_tools statusline install [--local|--global]

# Options
macf_tools statusline --show-model      # Include model name
macf_tools statusline --show-branch     # Include git branch
macf_tools statusline --compact         # Minimal format
```

---

## Phase Breakdown

### Phase 1: Core Command & Formatting

**Goal**: Create working `macf_tools statusline` that outputs formatted string

**Scope**:
- New `statusline.py` utility module
- CLI command registration in `cli.py`
- Field formatting functions
- stdin JSON parsing

**Deliverables**:
- `macf_tools statusline` outputs correct format
- Handles CC JSON stdin
- Falls back gracefully without stdin

**Success Criteria**:
- [ ] Output matches format specification
- [ ] Works with empty stdin
- [ ] Works with valid CC JSON
- [ ] Execution < 50ms

**Delegation**: DevOpsEng specialist for CLI implementation

---

### Phase 2: Installation Mechanism

**Goal**: Create `macf_tools statusline install` for self-service setup

**Scope**:
- Shell wrapper script creation
- Settings.json modification
- Path resolution for host/container

**Deliverables**:
- `statusline.sh` wrapper script
- `macf_tools statusline install` command
- Auto-configuration of `.claude/settings.local.json`

**Success Criteria**:
- [ ] Install works on macOS host
- [ ] Install works in Linux container
- [ ] Settings.json correctly updated
- [ ] Existing settings preserved

**Delegation**: DevOpsEng specialist for installation logic

---

### Phase 3: Project Detection

**Goal**: Auto-detect active project from workspace context

**Scope**:
- Project detection heuristics
- Optional display flags
- Git branch detection (optional)

**Detection Priority**:
1. `MACF_PROJECT` env var (explicit override)
2. `projects.yaml` lookup (container deployments)
3. Directory name heuristic (parent of `.claude/`)

**Success Criteria**:
- [ ] Project detected from env var
- [ ] Project detected from directory
- [ ] Graceful "omit" when unknown

**Delegation**: Can be done inline (simpler logic)

---

### Phase 4: Testing

**Goal**: Comprehensive test coverage

**Scope**:
- Unit tests for formatting functions
- Integration tests for CLI
- Performance benchmarks

**Test Matrix**:

| Test Case | Input | Expected |
|-----------|-------|----------|
| Basic format | All fields | Full statusline |
| No project | Missing project | Project field omitted |
| Empty stdin | No CC JSON | MacEff-only data |
| Malformed JSON | Invalid JSON | Graceful fallback |
| Large tokens | 150000 | "150k" |
| Small tokens | 5000 | "5000" |

**Success Criteria**:
- [ ] 10+ tests passing
- [ ] Performance < 100ms
- [ ] All edge cases covered

**Delegation**: TestEng specialist

---

### Phase 5: Documentation

**Goal**: User-facing documentation

**Scope**:
- User guide for statusline feature
- CLI reference update
- Example configurations

**Deliverables**:
- `macf/docs/user/statusline.md`
- CLI reference section in `cli-reference.md`

**Success Criteria**:
- [ ] Installation instructions clear
- [ ] Configuration options documented
- [ ] Troubleshooting guide included

**Delegation**: Can be done inline

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `macf/src/macf/utils/statusline.py` | CREATE | Core formatting logic |
| `macf/src/macf/cli.py` | MODIFY | Add statusline commands |
| `macf/src/macf/scripts/statusline.sh` | CREATE | Shell wrapper |
| `macf/tests/test_statusline.py` | CREATE | Test suite |
| `macf/docs/user/statusline.md` | CREATE | User documentation |
| `macf/docs/user/cli-reference.md` | MODIFY | Add CLI docs |

---

## Existing Infrastructure to Reuse

| Module | Function | Purpose |
|--------|----------|---------|
| `utils/tokens.py` | `get_token_info()` | Token counts, CLUAC |
| `utils/tokens.py` | `format_token_context_minimal()` | Existing minimal format |
| `utils/environment.py` | `detect_execution_environment()` | Host vs container |
| `utils/environment.py` | `get_rich_environment_string()` | Full env string |
| `config.py` | `ConsciousnessConfig.agent_id` | Agent identity |

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| CC JSON schema changes | Medium | Low | Defensive parsing with fallbacks |
| Performance degradation | Low | Medium | Cache agent identity, profile hot paths |
| Path differences host/container | Medium | Medium | Use existing portable path utilities |
| Missing config files | Medium | Low | Graceful fallback to defaults |

---

## Recovery Context

**If resuming after context loss**:
1. Read this roadmap
2. Check TODO list for current phase
3. Review `macf/src/macf/utils/statusline.py` if exists
4. Run `macf_tools statusline --help` to check implementation state

**Key Decisions Made**:
- Native MacEff script (not Oh My Posh integration)
- Claude Code statusline only (not hooks)
- Portable framework feature (host + container)
