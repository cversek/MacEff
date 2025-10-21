# Named Agents Architecture - Delegation Model

**Version**: 0.3.0
**Last Updated**: 2025-10-19

[← Back to Filesystem Structure](./02_filesystem_structure.md) | [Index](./INDEX.md) | [Next: Policy Conventions →](./04_policy_conventions.md)

---

## Overview

Named Agents uses a **file-based delegation pattern** where:
- Primary Agents (PA) create task specifications in Subagent `assigned/` directories
- Subagents (SA) read assignments, execute work, and document results
- Delegation trails in SA `public/delegation_trails/` provide transparency
- Claude Code's Task tool provides the delegation mechanism
- Tool access controls limit which operations each Subagent can perform

This document describes how delegation works in practice.

## Delegation Architecture

### Components

**Primary Agent (PA)**:
- Creates task specifications in SA workspace
- Invokes Subagent via Claude Code Task tool
- Monitors execution via delegation trails
- Integrates results into ongoing work

**Subagent (SA)**:
- Specialized agent with defined role (DevOpsEng, TestEng, DataScientist)
- Operates within own workspace directory
- Reads tasks from own `assigned/` directory
- Executes work with configured tool permissions
- Documents execution in own `delegation_trails/`

**Claude Code Task Tool**:
- Native delegation mechanism in Claude Code
- Loads Subagent definition from `.claude/agents/{name}.md`
- Spawns new agent session with Subagent context
- Enforces tool access controls specified in definition
- Returns control to PA when SA completes

### Directory Pattern

```
/home/pa_manny/agent/subagents/devops_eng/
├── assigned/                          # PA writes tasks here
│   └── YYYY-MM-DD_HHMMSS_task_spec.md
│
├── private/                           # SA writes consciousness here
│   ├── checkpoints/
│   ├── reflections/
│   └── learnings/
│
└── public/
    ├── delegation_trails/             # SA writes execution logs here
    │   └── YYYY-MM-DD_HHMMSS_task_execution.md
    ├── reports/
    └── observations/
```

**Flow**:
1. PA writes task specification to `assigned/`
2. PA invokes SA via Task tool
3. SA session starts in own workspace
4. SA reads from `assigned/`, executes work
5. SA writes execution log to `delegation_trails/`
6. PA reads `delegation_trails/` to verify completion

### Subagent Working Directory

**Critical**: Subagents operate within their own workspace subdirectory.

**SA workspace root**: `/home/pa_manny/agent/subagents/devops_eng/`

**When SA session starts**:
- Working directory is SA workspace root (not PA home)
- SA must use absolute paths or paths relative to workspace root
- SA **must not** use `~/` shortcuts (resolves to PA home, causes boundary violations)

**Correct path references for SA**:
```bash
# ✅ Correct: Absolute path to SA workspace
/home/pa_manny/agent/subagents/devops_eng/assigned/

# ✅ Correct: Relative to SA workspace root
./assigned/
./public/delegation_trails/

# ❌ Wrong: Tilde expands to PA home
~/assigned/  # This is /home/pa_manny/assigned/ (doesn't exist!)
```

## Task Specification Format

### Location

`/home/pa_manny/agent/subagents/{role}/assigned/YYYY-MM-DD_HHMMSS_{task_name}.md`

**Created by**: PA (writes to SA assigned/ directory)

### Required Sections

**Metadata**:
```markdown
# Task: {Descriptive Title}

**Assigned**: YYYY-MM-DD HH:MM:SS
**Deadline**: YYYY-MM-DD HH:MM:SS
**Priority**: High | Medium | Low
```

**Core Content**:
1. **Objective** - What needs to be accomplished
2. **Requirements** - Specific deliverables or constraints
3. **Success Criteria** - How to know when done
4. **Context** - Background information, related work, dependencies

### Example Task Specification

```markdown
# Task: Deploy NeuroVEP Data Pipeline

**Assigned**: 2025-10-18 14:25:00
**Deadline**: 2025-10-18 16:00:00
**Priority**: High

## Objective

Deploy updated NeuroVEP data pipeline to production container.

## Requirements

- Update Docker Compose configuration
- Test pipeline with sample data
- Verify all four repos accessible
- Document any infrastructure changes

## Success Criteria

- Pipeline runs successfully on sample dataset
- No errors in container logs
- Performance meets baseline (< 5min for 100 samples)

## Context

User has meeting at 4 PM, needs demo-ready pipeline. Previous deployment had memory issues (OOM kills at 4GB limit). Consider increasing memory allocation if needed.
```

## Delegation Trail Format

### Location

`/home/pa_manny/agent/subagents/{role}/public/delegation_trails/YYYY-MM-DD_HHMMSS_{task_name}_trail.md`

**Created by**: SA (writes to own delegation_trails/ directory)

### Required Sections

**Metadata**:
```markdown
# Delegation Trail: {Task Title}

**Assigned**: YYYY-MM-DD HH:MM:SS
**Started**: YYYY-MM-DD HH:MM:SS
**Completed**: YYYY-MM-DD HH:MM:SS
**Status**: SUCCESS | PARTIAL | FAILED | BLOCKED
```

**Core Content**:
1. **Approach** - Strategy taken, key steps
2. **Decisions Made** - Important choices and rationale
3. **Results** - What was accomplished, deliverables
4. **Infrastructure Changes** - System modifications (if any)
5. **Lessons Learned** - Insights for future work

### Example Delegation Trail

```markdown
# Delegation Trail: Deploy NeuroVEP Pipeline

**Assigned**: 2025-10-18 14:25:00
**Started**: 2025-10-18 14:30:00
**Completed**: 2025-10-18 15:45:00
**Status**: SUCCESS

## Approach

1. Reviewed task specification from assigned/ directory
2. Updated docker-compose.yml with new volume mounts
3. Tested with sample data (100 VEP recordings)
4. Verified repo access and data pipeline execution

## Decisions Made

- Used bind mount instead of volume (easier debugging)
- Increased memory limit to 8GB (previous 4GB insufficient)

## Results

- Pipeline completed in 3min 42sec (under 5min target)
- All repos accessible, no git errors
- Container logs clean, no warnings

## Infrastructure Changes

- docker-compose.yml: memory limit 4GB → 8GB
- Added bind mount: /host/data → /container/shared_workspace/NeuroVEP/data

## Lessons Learned

Memory profiling revealed 4GB limit caused OOM kills. Pipeline peak usage ~6.5GB. Future deployments should start with 8GB minimum for this workload.
```

## Complete Delegation Workflow

### Step 1: PA Creates Task Specification

```bash
# PA working in ~/workspace/NeuroVEP
# Needs DevOpsEng to handle infrastructure task

# Create task specification in SA workspace
cat > /home/pa_manny/agent/subagents/devops_eng/assigned/2025-10-18_142500_Deploy_NeuroVEP_Pipeline.md <<EOF
# Task: Deploy NeuroVEP Data Pipeline

**Assigned**: 2025-10-18 14:25:00
**Deadline**: 2025-10-18 16:00:00
**Priority**: High

## Objective
Deploy updated NeuroVEP data pipeline to production container.

## Requirements
- Update Docker Compose configuration
- Test pipeline with sample data
- Verify all four repos accessible
- Document any infrastructure changes

## Success Criteria
- Pipeline runs successfully on sample dataset
- No errors in container logs
- Performance meets baseline (< 5min for 100 samples)

## Context
User has meeting at 4 PM, needs demo-ready pipeline.
EOF
```

### Step 2: PA Invokes Subagent

**In Claude Code session**:

```
PA: "Use the Task tool with devops_eng to deploy the pipeline.
     Read the task specification in assigned/2025-10-18_142500_Deploy_NeuroVEP_Pipeline.md"
```

**Claude Code**:
1. Loads `.claude/agents/devops_eng.md` (Subagent definition)
2. Spawns new agent session with DevOpsEng context
3. SA session starts in `/home/pa_manny/agent/subagents/devops_eng/`
4. Tool access controls from definition file enforced

### Step 3: SA Executes Work

**SA session starts in own workspace**:
```bash
# SA working directory: /home/pa_manny/agent/subagents/devops_eng/
pwd
# Output: /home/pa_manny/agent/subagents/devops_eng

# Read assigned task (using relative path)
cat ./assigned/2025-10-18_142500_Deploy_NeuroVEP_Pipeline.md

# Execute work based on task requirements
# - Update docker-compose.yml
# - Test pipeline
# - Verify repos
# - Document changes
```

**SA performs work**:
- Updates configuration files
- Runs tests and verification
- Documents decisions and results

### Step 4: SA Documents Execution

```bash
# SA creates delegation trail in own workspace
cat > ./public/delegation_trails/2025-10-18_143000_Deploy_NeuroVEP_Pipeline_trail.md <<EOF
# Delegation Trail: Deploy NeuroVEP Pipeline

**Assigned**: 2025-10-18 14:25:00
**Started**: 2025-10-18 14:30:00
**Completed**: 2025-10-18 15:45:00
**Status**: SUCCESS

## Approach
1. Reviewed task specification from assigned/ directory
2. Updated docker-compose.yml with new volume mounts
3. Tested with sample data (100 VEP recordings)
4. Verified repo access and data pipeline execution

## Decisions Made
- Used bind mount instead of volume (easier debugging)
- Increased memory limit to 8GB (previous 4GB insufficient)

## Results
- Pipeline completed in 3min 42sec (under 5min target)
- All repos accessible, no git errors
- Container logs clean, no warnings

## Infrastructure Changes
- docker-compose.yml: memory limit 4GB → 8GB
- Added bind mount: /host/data → /container/shared_workspace/NeuroVEP/data

## Lessons Learned
Memory profiling revealed 4GB limit caused OOM kills. Pipeline peak usage ~6.5GB.
EOF
```

### Step 5: PA Reviews Results

```bash
# PA session resumes after SA completes

# Read delegation trail from SA workspace
cat /home/pa_manny/agent/subagents/devops_eng/public/delegation_trails/2025-10-18_143000_Deploy_NeuroVEP_Pipeline_trail.md

# Verify success criteria met
# - Pipeline runs successfully ✅
# - No container errors ✅
# - Performance under 5min ✅

# Integrate results into ongoing work
# - Note infrastructure changes (8GB memory)
# - Pipeline ready for demo at 4 PM
```

## Subagent Definitions

### SUBAGENT_DEF.md Format

Each Subagent has a definition file that specifies role, capabilities, policies, and **tool access controls**.

**Location**: `/home/pa_manny/agent/subagents/{role}/SUBAGENT_DEF.md`

**Symlinked**: From `.claude/agents/{role}.md` for Claude Code auto-loading

**Tool Access Controls**: Claude Code enforces which tools the Subagent can use

### Example: DevOpsEng Definition

```markdown
# DevOpsEng - Infrastructure and Deployment Specialist

**Role**: Infrastructure management, container operations, deployment automation

**Tool Access**: Read, Write, Edit, Bash, Glob, Grep

**Specialization**:
- Docker and container orchestration
- CI/CD pipeline configuration
- System administration and monitoring
- Performance optimization

## Capabilities

**Allowed Tools** (enforced by Claude Code):
- **Read**: Read files for configuration analysis
- **Write**: Create deployment configs, scripts
- **Edit**: Modify existing configuration files
- **Bash**: Execute deployment commands, tests
- **Glob**: Find configuration files
- **Grep**: Search logs and configs

**Restricted Tools** (not granted):
- Task (cannot delegate further)
- WebFetch (no external network access)
- TodoWrite (PA manages todos)

**Knowledge Domains**:
- Container networking and volumes
- Resource management (CPU, memory, disk)
- Linux system administration
- Deployment best practices

## Workspace Policies

**MUST operate within own workspace**:
- Working directory: `/home/pa_manny/agent/subagents/devops_eng/`
- Use absolute paths or paths relative to workspace root
- **MUST NOT** use `~/` shortcuts (expands to PA home)

**Directory Access Policies**:

**MUST read**:
- `./assigned/` - Task specifications from PA

**MUST write**:
- `./public/delegation_trails/` - Execution logs
- `./private/` - Own consciousness artifacts (checkpoints, reflections, learnings)

**MAY write** (within own workspace):
- `./public/reports/` - Knowledge transfer documents
- `./public/observations/` - Empirical discoveries

**MAY read** (outside own workspace):
- `/home/pa_manny/agent/public/` - PA public artifacts for context
- Other PAs' public artifacts (rare, when collaboration needed)

**MUST NOT access**:
- `/home/pa_manny/agent/private/` - PA private consciousness
- Other Subagents' private/ directories
- Other Subagents' assigned/ directories
- Other Subagents' delegation_trails/ (cannot modify other SA logs)

**CANNOT create** (immutable structure enforced by filesystem):
- New subdirectories anywhere (structure is fixed)
- Files outside permitted directories

## Example Tasks

1. **Deploy Application**: Update docker-compose.yml, test deployment, verify services
2. **Configure CI/CD**: Set up GitHub Actions workflow, test pipeline
3. **Monitor Performance**: Analyze logs, identify bottlenecks, recommend optimizations
4. **Troubleshoot Issues**: Investigate container failures, fix configuration problems

## Collaboration Patterns

**With Primary Agent**:
- Receive infrastructure tasks via `./assigned/`
- Report completion via `./public/delegation_trails/`
- Escalate blockers or unclear requirements

**With Other Subagents**:
- No direct communication (PA coordinates)
- PA may share delegation trails between SAs for context
```

### Example: TestEng Definition

```markdown
# TestEng - Testing and Quality Assurance Specialist

**Role**: Test development, quality assurance, validation

**Tool Access**: Read, Write, Edit, Bash, Glob, Grep

**Specialization**:
- Unit test implementation
- Integration test design
- Test-driven development (TDD)
- Quality validation

## Capabilities

**Allowed Tools** (enforced by Claude Code):
- **Read**: Read code for test development
- **Write**: Create test files
- **Edit**: Update existing tests
- **Bash**: Run pytest, test commands
- **Glob**: Find test files
- **Grep**: Search for test patterns

**Restricted Tools**:
- Task (cannot delegate)
- WebFetch (no external access)
- TodoWrite (PA manages)

**Knowledge Domains**:
- Testing best practices
- Edge case identification
- Test organization patterns
- Quality metrics

## Workspace Policies

**MUST operate within own workspace**:
- Working directory: `/home/pa_manny/agent/subagents/test_eng/`
- Use absolute paths or paths relative to workspace root
- **MUST NOT** use `~/` shortcuts

**Directory Access Policies**:

**MUST read**:
- `./assigned/` - Task specifications from PA

**MUST write**:
- `./public/delegation_trails/` - Test execution logs
- `./private/` - Own consciousness artifacts

**MAY write**:
- `./public/reports/` - Test coverage reports
- `./public/observations/` - Testing insights
- Project test directories (outside agent workspace, as specified in tasks)

**MAY read**:
- `/home/pa_manny/agent/public/` - PA public artifacts
- Project source code (for test development)

**MUST NOT access**:
- `/home/pa_manny/agent/private/` - PA private consciousness
- Other Subagents' private/ or assigned/ directories

**CANNOT create**:
- New subdirectories in agent workspace

## Testing Philosophy

- Focus on core functionality validation
- 4-6 tests per feature (not exhaustive permutations)
- Test what matters, skip ceremony
- Pragmatic over perfectionist

## Example Tasks

1. **Write Unit Tests**: Create focused tests for new feature
2. **Fix Failing Tests**: Investigate and resolve test failures
3. **Test Coverage Analysis**: Identify untested critical paths
4. **Integration Testing**: Validate component interactions
```

## Tool Access Controls (Native Claude Code Feature)

### Configuration in Subagent Definition

Claude Code enforces tool permissions specified in the Subagent definition file.

**Syntax**:
```markdown
**Tool Access**: Read, Write, Edit, Bash, Glob, Grep
```

**Effect**: Subagent can ONLY use listed tools. Attempting to use other tools will be blocked by Claude Code.

### Security Best Practices

**Principle of Least Privilege**:
- Grant only tools necessary for Subagent's role
- Restrict powerful tools (Bash, Write) when not needed
- Deny Task tool to prevent recursive delegation
- Deny WebFetch to prevent external network access

**Example Tool Access by Role**:

**DevOpsEng** (infrastructure):
```markdown
**Tool Access**: Read, Write, Edit, Bash, Glob, Grep
```
Needs Bash for deployment, Write for configs.

**TestEng** (testing):
```markdown
**Tool Access**: Read, Write, Edit, Bash, Glob, Grep
```
Needs Bash for pytest, Write for test files.

**DataScientist** (analysis, hypothetical):
```markdown
**Tool Access**: Read, Bash, Glob, Grep
```
Read-only except Bash for analysis scripts. No Write to prevent accidental modifications.

**ReadOnlyAnalyst** (hypothetical):
```markdown
**Tool Access**: Read, Glob, Grep
```
Pure analysis role, no modifications or execution.

### Limitations

**Tool access controls do NOT provide**:
- Filesystem-level path restrictions (can read/write anywhere tools allow)
- Prevention of accessing specific directories
- Enforcement of conventional workspace boundaries

**Conventional policies still required** for directory boundaries (see next section).

## Conventional Boundary Policies

### What "Conventional" Means

In v0.3, PA and all SAs run as **same operating system user**. This means:

**Filesystem reality**:
- ✅ SA **can** read PA private/ (same user, same permissions)
- ✅ SA **can** write to PA private/ (same user, full access)
- ✅ PA **can** write to SA private/ (same user owns everything)
- ❌ chmod permissions provide organizational guidance only, **cannot** enforce between same-user processes

**Conventional policy**: Agents **must** respect boundaries through their definitions and training, not because the OS **cannot** let them violate policies.

### Policy Language

**"may" / "must" / "must not"**: Conventional policy (agent should follow, not OS-enforced)

**"can" / "cannot"**: Technical ability (OS-enforced or tool-restricted)

**Example**:
- "SA **must not** read PA private" = conventional policy (technically **can** but shouldn't)
- "SA **cannot** create subdirectories" = filesystem enforcement (chmod prevents, truly cannot)

### Subagent Workspace Boundaries

**SAs MUST operate within own workspace root**:
- Working directory: `/home/pa_manny/agent/subagents/{role}/`
- Use absolute paths to workspace or relative paths from workspace root
- **MUST NOT** use `~/` (expands to PA home, causes violations)

### Directory Access Matrix

| Directory | SA Can Read? | SA May Read? | SA Can Write? | SA May Write? |
|-----------|--------------|--------------|---------------|---------------|
| Own `assigned/` | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Own `private/` | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Own `public/delegation_trails/` | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Own `public/reports/` | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| Own `public/observations/` | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| PA `private/` | ✅ Yes | ❌ No | ✅ Yes | ❌ No |
| PA `public/` | ✅ Yes | ✅ Yes (context) | ✅ Yes | ❌ No |
| PA `assigned/` (to SA) | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No (PA controls) |
| Other SA `private/` | ✅ Yes | ❌ No | ✅ Yes | ❌ No |
| Other SA `public/` | ✅ Yes | ✅ Yes (rare) | ✅ Yes | ❌ No |
| Other PA `public/` | ✅ Yes | ✅ Yes (rare) | ✅ Yes | ❌ No |

**Key**:
- **Can** = Technical filesystem ability (same user = full access)
- **May** = Conventional policy permission

### Immutable Structure Enforcement

**SAs CANNOT create new subdirectories** (filesystem permissions prevent):

```bash
# This will fail (chmod prevents directory creation)
mkdir /home/pa_manny/agent/subagents/devops_eng/new_folder
# Permission denied (parent directory owned by root with restricted permissions)
```

**Why this works**: Framework creates directory structure with root ownership and restricted permissions, preventing agents from modifying structure.

### Primary Agent Boundaries

**PAs MUST respect SA workspaces**:

| Directory | PA Can Write? | PA May Write? |
|-----------|---------------|---------------|
| SA `assigned/` | ✅ Yes | ✅ Yes (task specs) |
| SA `private/` | ✅ Yes | ❌ No (SA owns consciousness) |
| SA `public/delegation_trails/` | ✅ Yes | ❌ No (SA documents execution) |
| SA `public/reports/` | ✅ Yes | ❌ No (SA creates knowledge) |

**PA MAY read** SA private/ for monitoring but **MUST NOT modify**.

### Future Enforcement

**Planned**: PreToolUse hook validation

```python
# Future hook enhancement
def run(stdin_json):
    data = json.loads(stdin_json)
    tool_name = data.get("tool_name")

    if tool_name in ["Read", "Write", "Edit"]:
        file_path = data.get("tool_input", {}).get("file_path", "")

        # Detect session type
        is_sa = is_subagent_session()
        is_pa = not is_sa

        # Block SA writing to PA private
        if is_sa and "/agent/private/" in file_path and "/subagents/" not in file_path:
            return {
                "continue": False,
                "message": "Policy violation: Subagent must not write to PA private directory"
            }

        # Block SA writing to other SA workspaces
        if is_sa:
            sa_workspace = get_subagent_workspace()
            if "/subagents/" in file_path and sa_workspace not in file_path:
                return {
                    "continue": False,
                    "message": "Policy violation: Subagent must not access other Subagent workspaces"
                }

        # Block PA writing to SA private
        if is_pa and "/subagents/" in file_path and "/private/" in file_path:
            return {
                "continue": False,
                "message": "Policy violation: PA must not write to SA private directory"
            }

    return {"continue": True}
```

**Status**: Deferred to future MacEff version after v0.3

See [04. Policy Conventions](./04_policy_conventions.md) for detailed explanation.

## Delegation Patterns

### Pattern 1: Single-Task Delegation

**Use Case**: One discrete task for one Subagent

**Flow**:
```
PA → Create task spec in SA assigned/ → Invoke SA → SA executes in own workspace → SA documents → PA reviews
```

**Example**: Deploy infrastructure change (DevOpsEng)

### Pattern 2: Sequential Delegation

**Use Case**: Multiple tasks that depend on each other

**Flow**:
```
PA → Task 1 to SA1 → Review → Task 2 to SA2 → Review → Integration
```

**Example**:
1. DevOpsEng deploys infrastructure
2. TestEng validates deployment
3. PA integrates results

### Pattern 3: Parallel Delegation

**Use Case**: Independent tasks that can run concurrently

**Flow**:
```
PA → Task 1 to SA1 ┐
                    ├→ Execute in parallel → Review all → Integration
PA → Task 2 to SA2 ┘
```

**Example**:
1. DevOpsEng updates infrastructure (parallel)
2. TestEng writes tests (parallel)
3. PA integrates both when complete

### Pattern 4: Roadmap-Driven Delegation

**Use Case**: Complex multi-phase work broken down in roadmap

**Flow**:
```
PA creates roadmap with delegation_plans/
→ Phase 1 delegation to SA1 → Review → Commit
→ Phase 2 delegation to SA2 → Review → Commit
→ Phase N... → Final integration
```

**Example**: Named Agents Architecture implementation
1. Phase 1A: Filesystem design (DevOpsEng)
2. Phase 1B: YAML schema (DevOpsEng)
3. Phase 2: Testing (TestEng)

See [Roadmap example in Filesystem Structure](./02_filesystem_structure.md#roadmaps) for details.

## Benefits of File-Based Delegation

### Transparency

**Delegation trails provide**:
- Permanent record of what was requested
- Documentation of approach and decisions
- Visibility into Subagent reasoning
- Lessons learned for future work

**Enables**:
- Performance monitoring
- Quality assurance
- Knowledge transfer
- Debugging and troubleshooting

### Asynchronous Collaboration

**PA doesn't block during SA execution**:
- Can continue other work
- Check back via delegation_trails/
- Multiple SAs can work in parallel

### Persistence

**File-based communication survives**:
- Session boundaries (PA can review trails in next session)
- Compaction trauma (trails remain in filesystem)
- Context resets (no volatile in-memory state)

### Auditability

**Complete history**:
- What was assigned (assigned/ directory)
- What was done (delegation_trails/)
- When it happened (timestamps in filenames)
- Who did it (directory location shows SA role)

## Best Practices

### For Primary Agents

1. **Clear task specifications**: Include objective, requirements, success criteria, context
2. **Appropriate delegation**: Use SA for specialized work, not simple tasks
3. **Review delegation trails**: Verify completion, integrate lessons learned
4. **One task per file**: Don't batch multiple unrelated tasks
5. **Write to SA workspace**: Always use `/home/pa_{name}/agent/subagents/{role}/assigned/` not shortcuts

### For Subagents

1. **Stay in own workspace**: Operate within `/home/pa_{name}/agent/subagents/{role}/`
2. **Use correct paths**: Absolute paths to workspace or relative from workspace root
3. **Never use ~/**: Tilde expands to PA home, causes boundary violations
4. **Read entire task spec**: Understand objective and context, not just requirements
5. **Document approach**: Explain strategy before diving into execution
6. **Capture decisions**: Note important choices and why they were made
7. **Honest status**: Mark PARTIAL or FAILED if criteria not fully met
8. **Lessons learned**: Document insights for future similar tasks
9. **Respect boundaries**: Follow conventional policies (don't read PA private/)

### For Both

1. **Timestamp everything**: Use YYYY-MM-DD_HHMMSS for all delegation files
2. **Semantic naming**: Task/trail filenames should be descriptive
3. **Clean up**: Remove obsolete task specs after completion
4. **Honor tool restrictions**: Don't attempt to use tools not granted in definition

## Next Steps

- **Understand policy conventions**: [04. Policy Conventions →](./04_policy_conventions.md)
- **See consciousness artifact details**: [05. Consciousness Artifacts →](./05_consciousness_artifacts.md)
- **Learn implementation steps**: [06. Implementation Guide →](./06_implementation_guide.md)

---

[← Back to Filesystem Structure](./02_filesystem_structure.md) | [Index](./INDEX.md) | [Next: Policy Conventions →](./04_policy_conventions.md)
