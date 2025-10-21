# APPENDIX A: YAML Schema Reference

**Version**: 0.3.0
**Last Updated**: 2025-10-21
**Status**: Complete (Phase 1B Implementation)

---

## Overview

This appendix provides complete YAML schema specifications for Named Agents v0.3 configuration files. These schemas are implemented as **Pydantic models** that provide runtime validation with clear error messages.

**Configuration Files**:
- `agents.yaml` - Primary Agent and Subagent definitions
- `projects.yaml` - Project workspace configurations

**Model Location**: `/macf/src/macf/models/`
- `agent_spec.py` - AgentsConfig, AgentSpec, SubagentSpec
- `project_spec.py` - ProjectsConfig, ProjectSpec

---

## agents.yaml Schema

### Root Structure

```yaml
agents:
  <agent_name>:
    # AgentSpec fields

subagents:
  <subagent_name>:
    # SubagentSpec fields

defaults:  # Optional
  # DefaultsConfig fields
```

### AgentSpec Fields

**Required Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `username` | string | Linux username for the agent (e.g., `pa_manny`) |
| `personality` | string | Path to personality file (Identity layer CLAUDE.md source) |

**Optional Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `subagents` | list[string] | `[]` | List of assigned subagent names |
| `assigned_projects` | list[string] | `[]` | List of assigned project names |
| `consciousness_artifacts` | ConsciousnessArtifactsConfig | `null` | Consciousness artifact configuration |
| `hooks` | dict | `null` | Hook configuration (enabled list, etc.) |

### SubagentSpec Fields

**Required Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `role` | string | Description of subagent's role and specialization |
| `tool_access` | string | Comma-separated list of allowed tools (e.g., `"Read, Write, Edit, Bash"`) |

**Optional Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `shell` | string | `/usr/sbin/nologin` | Shell for subagent |
| `consciousness_artifacts` | ConsciousnessArtifactsConfig | `null` | Consciousness artifact configuration for subagent |

**Important**: `tool_access` must be a comma-separated **string**, not a list. Example:
- ✅ Correct: `"Read, Write, Edit, Bash"`
- ❌ Wrong: `["Read", "Write", "Edit", "Bash"]`

### ConsciousnessArtifactsConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `private` | list[string] | `null` | Private artifact types (checkpoints, reflections, learnings) |
| `public` | list[string] | `null` | Public artifact types (roadmaps, reports, observations, experiments, delegation_trails) |

### DefaultsConfig Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `consciousness_artifacts` | ConsciousnessArtifactsConfig | `null` | Default consciousness artifact configuration |
| `hooks` | dict | `null` | Default hook configuration |

### Complete agents.yaml Example

```yaml
agents:
  manny:
    username: pa_manny
    personality: ../custom/agents/manny_personality.md
    subagents: [devops_eng, test_eng]
    assigned_projects: [NeuroVEP, DataPipeline]
    consciousness_artifacts:
      private: [checkpoints, reflections, learnings]
      public: [roadmaps, reports, observations]
    hooks:
      enabled: [session_start, stop, user_prompt_submit]

  claudethebuilder:
    username: pa_claudethebuilder
    personality: ../custom/agents/builder_personality.md
    subagents: [devops_eng, test_eng]
    assigned_projects: [MacEff, ClaudeTheBuilder]
    consciousness_artifacts:
      private: [checkpoints, reflections, learnings]
      public: [roadmaps, reports, observations, experiments]

subagents:
  devops_eng:
    role: Infrastructure and deployment specialist
    tool_access: Read, Write, Edit, Bash, Glob, Grep
    consciousness_artifacts:
      public: [delegation_trails]

  test_eng:
    role: Test-driven development and quality assurance
    tool_access: Read, Write, Edit, Bash
    consciousness_artifacts:
      public: [delegation_trails]

defaults:
  consciousness_artifacts:
    private: [checkpoints, reflections, learnings]
    public: [roadmaps, reports, observations]
  hooks:
    enabled: [session_start, stop]
```

---

## projects.yaml Schema

### Root Structure

```yaml
projects:
  <project_name>:
    # ProjectSpec fields
```

### ProjectSpec Fields

**Required Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `context` | string | Path to project context file (Project layer CLAUDE.md source) |

**Optional Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `repos` | list[RepoMount] | `[]` | Git repositories to clone into project workspace |
| `data_mounts` | list[DataMount] | `[]` | Data directory mounts (bind mounts from host) |
| `commands` | dict[string, string] | `null` | Project-specific slash commands (name → path mapping) |

### RepoMount Fields

**Required Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Git repository URL (e.g., `git@github.com:user/repo.git`) |
| `path` | string | Relative path within project workspace (e.g., `repos/backend`) |

### DataMount Fields

**Required Fields**:

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Mount type (e.g., `bind`) |
| `source` | string | Source path on host filesystem |
| `target` | string | Target path within project (relative, e.g., `data`) |

**Optional Fields**:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `read_only` | boolean | `false` | Whether mount is read-only |

### Complete projects.yaml Example

```yaml
projects:
  NeuroVEP:
    context: ../custom/projects/NeuroVEP_context.md
    repos:
      - url: git@github.com:user/neurovep_analysis.git
        path: repos/neurovep_analysis
      - url: git@github.com:user/neurovep_viz.git
        path: repos/neurovep_viz
    data_mounts:
      - type: bind
        source: /Users/user/Dropbox/NeuroVEP
        target: data
        read_only: false
    commands:
      analyze_vep: ../custom/projects/commands/analyze_vep.md
      generate_report: ../custom/projects/commands/generate_report.md

  MacEff:
    context: ../custom/projects/MacEff_context.md
    repos:
      - url: git@github.com:cversek/MacEff.git
        path: repos/MacEff
    commands:
      build_container: ../custom/projects/commands/build_container.md
```

---

## Validation Rules

### agents.yaml Validation

**Root Level**:
- ✅ Both `agents` and `subagents` sections are **required**
- ✅ `defaults` section is optional

**AgentSpec Validation**:
- ✅ `username` and `personality` are **required**
- ✅ `subagents` and `assigned_projects` default to empty lists if omitted
- ✅ `consciousness_artifacts` and `hooks` are optional

**SubagentSpec Validation**:
- ✅ `role` and `tool_access` are **required**
- ✅ `tool_access` must be a comma-separated **string**, not a list
- ✅ `shell` defaults to `/usr/sbin/nologin` if omitted

### projects.yaml Validation

**Root Level**:
- ✅ `projects` section is **required**

**ProjectSpec Validation**:
- ✅ `context` is **required**
- ✅ `repos`, `data_mounts`, and `commands` default to empty/null if omitted

**RepoMount Validation**:
- ✅ `url` and `path` are **required**

**DataMount Validation**:
- ✅ `type`, `source`, and `target` are **required**
- ✅ `read_only` defaults to `false` if omitted

---

## Common Validation Errors

### Error: Missing Required Field

```
ValidationError: 1 validation error for AgentSpec
personality
  Field required [type=missing, input_value={'username': 'pa_manny'}, input_type=dict]
```

**Solution**: Add the missing required field to your YAML configuration.

### Error: tool_access Must Be String

```
ValidationError: 1 validation error for SubagentSpec
tool_access
  tool_access must be a comma-separated string
```

**Solution**: Change `tool_access: ["Read", "Write"]` to `tool_access: "Read, Write"` (string format).

### Error: Missing Required Section

```
ValidationError: 1 validation error for AgentsConfig
agents
  Field required [type=missing, input_value={'subagents': {...}}, input_type=dict]
```

**Solution**: Ensure both `agents` and `subagents` sections exist in agents.yaml.

---

## Using Pydantic Models in Python

### Loading and Validating Configurations

```python
from pathlib import Path
import yaml
from macf.models import AgentsConfig, ProjectsConfig

# Load agents.yaml
agents_path = Path("/etc/maceff/agents.yaml")
with agents_path.open() as f:
    agents_data = yaml.safe_load(f)

# Validate with Pydantic (raises ValidationError if invalid)
agents_config = AgentsConfig(**agents_data)

# Access validated data
for agent_name, agent_spec in agents_config.agents.items():
    print(f"Agent: {agent_name}")
    print(f"  Username: {agent_spec.username}")
    print(f"  Subagents: {agent_spec.subagents}")

# Load projects.yaml
projects_path = Path("/etc/maceff/projects.yaml")
with projects_path.open() as f:
    projects_data = yaml.safe_load(f)

projects_config = ProjectsConfig(**projects_data)
```

### Error Handling

```python
from pydantic import ValidationError

try:
    agents_config = AgentsConfig(**agents_data)
except ValidationError as e:
    print("Invalid agents.yaml configuration:")
    print(e)
    # e.errors() provides structured error details
    for error in e.errors():
        print(f"  Field: {error['loc']}")
        print(f"  Error: {error['msg']}")
```

---

## Schema Evolution

**Version Compatibility**: These schemas correspond to Named Agents v0.3 architecture.

**Future Extensions**: Additional optional fields may be added in future versions while maintaining backward compatibility with v0.3 configurations.

**Validation Strategy**: Pydantic models provide fail-fast validation with actionable error messages, preventing deployment of invalid configurations.

---

## References

- **Model Implementation**: `/macf/src/macf/models/`
  - `agent_spec.py` - Agent configuration models
  - `project_spec.py` - Project configuration models
- **Test Suite**: `/macf/tests/`
  - `test_agent_spec.py` - Agent model validation tests
  - `test_project_spec.py` - Project model validation tests
- **Startup Script**: `/docker/scripts/start.py` - Uses these models for container initialization

---

**Navigation**:
- [← Back to INDEX](./INDEX.md)
- [Implementation Guide →](./05_implementation_guide.md)
