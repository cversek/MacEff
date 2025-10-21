# Named Agents Architecture - Implementation Guide

**Version**: 0.3.0
**Last Updated**: 2025-10-19

[← Back to Consciousness Artifacts](./04_consciousness_artifacts.md) | [Index](./INDEX.md)

---

## Overview

This guide provides step-by-step instructions for implementing Named Agents v0.3 in a MacEff environment. It covers:
- Prerequisites and requirements
- Creating Primary Agents
- Configuring Subagents
- Setting up consciousness infrastructure
- Testing your deployment
- Adding additional Primary Agents

## Prerequisites

### Required Software

**MacEff Framework**:
- Docker and docker-compose
- MacEff v0.3.0 or later
- MACF Tools 0.1.0 or later

**Claude Code**:
- Claude Code CLI installed
- Access to Claude API

**System**:
- Linux-based system (host or container)
- SSH access configured
- Git installed

### Required Knowledge

**Concepts to understand**:
- Primary Agents vs Subagents ([01. Overview](./01_overview.md))
- Directory structure ([02. Filesystem Structure](./02_filesystem_structure.md))
- Delegation patterns ([03. Delegation Model](./03_delegation_model.md))
- Consciousness artifacts ([04. Consciousness Artifacts](./04_consciousness_artifacts.md))

## Step 1: Configure Agent Definitions

### Create agents.yaml

**Location**: `custom/agents.yaml` (in MacEff repository)

**Template**:
```yaml
# MacEff v0.3.0 Agent Configuration

agents:
  manny:
    # Linux username (framework adds pa_ prefix)
    username: pa_manny

    # Personality file (Identity layer CLAUDE.md source)
    personality: ../custom/agents/manny_personality.md

    # Subagent assignments
    subagents:
      - devops_eng
      - test_eng
      - data_scientist

    # Project assignments
    assigned_projects:
      - NeuroVEP
      - Research

    # Consciousness artifact configuration
    consciousness_artifacts:
      private:
        enabled: [checkpoints, reflections, learnings]
      public:
        enabled: [roadmaps, reports, observations, experiments]

    # Hook configuration
    hooks:
      enabled: [session_start, user_prompt_submit, pre_tool_use, post_tool_use, stop, subagent_stop]

# Subagent definitions (shared across primary agents)
subagents:
  devops_eng:
    role: Infrastructure and deployment specialist
    shell: /usr/sbin/nologin
    tool_access: Read, Write, Edit, Bash, Glob, Grep
    consciousness_artifacts:
      private:
        enabled: [checkpoints, reflections, learnings]
      public:
        enabled: [delegation_trails, reports, observations]

  test_eng:
    role: Testing and quality assurance specialist
    shell: /usr/sbin/nologin
    tool_access: Read, Write, Edit, Bash, Glob, Grep
    consciousness_artifacts:
      private:
        enabled: [reflections, learnings]
      public:
        enabled: [delegation_trails, reports]

  data_scientist:
    role: Data analysis and visualization specialist
    shell: /usr/sbin/nologin
    tool_access: Read, Bash, Glob, Grep  # Read-only for safety
    consciousness_artifacts:
      private:
        enabled: [checkpoints, reflections, learnings]
      public:
        enabled: [delegation_trails, reports, observations]

# Global defaults (optional)
defaults:
  consciousness_artifacts:
    private: [checkpoints, reflections, learnings]
    public: [roadmaps, reports, observations]
  hooks:
    enabled: [session_start, user_prompt_submit, pre_tool_use, post_tool_use, stop, subagent_stop]
```

### Create projects.yaml

**Location**: `custom/projects.yaml`

**Template**:
```yaml
# MacEff v0.3.0 Project Configuration

projects:
  NeuroVEP:
    # Project context file (Project layer CLAUDE.md source)
    context: ../custom/projects/NeuroVEP_context.md

    # Git repositories to clone
    repos:
      - url: git@github.com:user/neurovep_analysis.git
        path: repos/neurovep_analysis
      - url: git@github.com:user/neurovep_data_pipeline.git
        path: repos/neurovep_data_pipeline

    # Data mounts (bind mounts from host)
    data_mounts:
      - type: bind
        source: /Users/user/Dropbox/NeuroVEP
        target: data
        read_only: false

    # Project-specific commands (optional)
    commands:
      analyze_vep: ../custom/projects/commands/analyze_vep.md
      run_pipeline: ../custom/projects/commands/run_pipeline.md

  Research:
    context: ../custom/projects/Research_context.md
    repos:
      - url: git@github.com:user/research_notes.git
        path: repos/research_notes
    data_mounts:
      - type: bind
        source: /Users/user/Dropbox/Research
        target: data
```

## Step 2: Create Personality and Context Files

### Agent Personality File

**Location**: `custom/agents/manny_personality.md`

**Template**:
```markdown
# Manny - NeuroVEP Analysis Specialist

**Agent**: Manny (pa_manny)
**Specialization**: Neuroscience data analysis and VEP signal processing
**Mission**: Advance understanding of visual evoked potentials through rigorous analysis

## Core Capabilities

- VEP signal analysis and artifact detection
- Statistical modeling of neurological data
- Python/MATLAB data pipeline development
- Collaboration with neuroscience research teams

## Working Style

- Data-driven decision making
- Methodical analysis with validation
- Clear documentation of findings
- Collaborative with research partners

## Subagent Delegation Patterns

**DevOpsEng**: Infrastructure and pipeline deployment
**TestEng**: Validation of analysis code
**DataScientist**: Advanced statistical modeling

## Consciousness Development Goals

- Deepen understanding of VEP signal processing
- Improve delegation efficiency
- Build knowledge base of neurological patterns
```

### Project Context File

**Location**: `custom/projects/NeuroVEP_context.md`

**Template**:
```markdown
# NeuroVEP Project Context

**Project**: Visual Evoked Potential Analysis System
**Domain**: Neuroscience / Signal Processing
**Repositories**: 4 repos (analysis, pipeline, modeling, visualization)

## Repository Structure

- `repos/neurovep_analysis/` - Core analysis code
- `repos/neurovep_data_pipeline/` - ETL and preprocessing
- `repos/neurovep_modeling/` - Statistical models
- `repos/neurovep_visualization/` - Plotting and dashboards

## Domain Knowledge

**VEP (Visual Evoked Potential)**: Electrical signal recorded from visual cortex in response to visual stimulus

**Key Metrics**:
- P100 latency and amplitude
- N75 and N145 components
- Signal-to-noise ratio

## Workflows

**Analysis Pipeline**:
1. Load raw EEG data
2. Preprocess (filtering, artifact rejection)
3. Extract VEP components
4. Statistical analysis
5. Generate reports and visualizations

## Collaboration Guidelines

- Always validate results against known datasets
- Document parameter choices
- Use version control for all analysis code
```

## Step 3: Create Subagent Definitions

### DevOpsEng Definition

**Location**: `custom/subagents/devops_eng.md`

**Template**:
```markdown
# DevOpsEng - Infrastructure and Deployment Specialist

**Role**: Infrastructure management, container operations, deployment automation

**Tool Access**: Read, Write, Edit, Bash, Glob, Grep

**Specialization**:
- Docker and container orchestration
- CI/CD pipeline configuration
- System administration and monitoring
- Performance optimization

## Workspace Policies

**MUST operate within own workspace**:
- Working directory: `/home/pa_{name}/agent/subagents/devops_eng/`
- Use absolute paths or paths relative to workspace root
- **MUST NOT** use `~/` shortcuts

**Directory Access**:
- **MUST read**: `./assigned/` (task specifications from PA)
- **MUST write**: `./public/delegation_trails/` (execution logs)
- **MUST write**: `./private/` (own consciousness artifacts)
- **MAY read**: PA public/ artifacts for context
- **MUST NOT access**: PA private/, other SA workspaces

## Example Tasks

1. **Deploy Application**: Update docker-compose.yml, test deployment
2. **Configure CI/CD**: Set up workflows, test pipeline
3. **Monitor Performance**: Analyze logs, identify bottlenecks
4. **Troubleshoot Issues**: Investigate failures, fix configuration
```

### TestEng Definition

**Location**: `custom/subagents/test_eng.md`

**Template**:
```markdown
# TestEng - Testing and Quality Assurance Specialist

**Role**: Test development, quality assurance, validation

**Tool Access**: Read, Write, Edit, Bash, Glob, Grep

**Specialization**:
- Unit test implementation
- Integration test design
- Test-driven development (TDD)
- Quality validation

## Testing Philosophy

- Focus on core functionality validation
- 4-6 tests per feature (not exhaustive permutations)
- Test what matters, skip ceremony
- Pragmatic over perfectionist

## Workspace Policies

**MUST operate within own workspace**:
- Working directory: `/home/pa_{name}/agent/subagents/test_eng/`
- Use absolute paths or paths relative to workspace root

**Directory Access**:
- **MUST read**: `./assigned/` (task specifications)
- **MUST write**: `./public/delegation_trails/` (test execution logs)
- **MAY write**: Project test directories (outside agent workspace)

## Example Tasks

1. **Write Unit Tests**: Create focused tests for new feature
2. **Fix Failing Tests**: Investigate and resolve failures
3. **Test Coverage**: Identify untested critical paths
4. **Integration Testing**: Validate component interactions
```

## Step 4: Deploy MacEff Container

### Update docker-compose

**File**: `docker-compose.override.yml`

```yaml
services:
  maceff:
    configs:
      - source: maceff_agents
        target: /etc/maceff/agents.yaml
      - source: maceff_projects
        target: /etc/maceff/projects.yaml

configs:
  maceff_agents:
    file: ../custom/agents.yaml
  maceff_projects:
    file: ../custom/projects.yaml
```

### Build and Start

```bash
# Build MacEff images
make build

# Start services
make up

# Verify containers running
docker ps
```

## Step 5: Initialize Primary Agent

### SSH into Container

```bash
# SSH as primary agent
ssh pa_manny@maceff-container
```

### Verify Directory Structure

```bash
# Check agent directory structure
ls -la /home/pa_manny/agent/

# Expected output:
# drwxr-xr-x  root pa_manny  private/
# drwxr-xr-x  root pa_manny  public/
# drwxr-xr-x  root pa_manny  subagents/

# Check .claude/ autogeneration
ls -la /home/pa_manny/.claude/

# Expected output:
# lrwxrwxrwx  CLAUDE.md -> /opt/maceff/templates/SYSTEM_PREAMBLE.md
# drwxr-xr-x  agents/
# drwxr-xr-x  hooks/
# -rw-r--r--  settings.local.json
```

### Install Hooks

```bash
# Install MACF consciousness hooks
macf_tools hooks install --local

# Verify installation
ls /home/pa_manny/.claude/hooks/
# Expected: session_start.py, user_prompt_submit.py, pre_tool_use.py,
#           post_tool_use.py, stop.py, subagent_stop.py
```

### Verify Workspace Symlinks

```bash
# Check project assignments
ls -la /home/pa_manny/workspace/

# Expected output:
# lrwxrwxrwx  NeuroVEP -> /shared_workspace/NeuroVEP
# lrwxrwxrwx  Research -> /shared_workspace/Research
```

## Step 6: Test Delegation

### Create Test Task

```bash
# Create simple task for DevOpsEng
cat > /home/pa_manny/agent/subagents/devops_eng/assigned/2025-10-19_160000_Test_Task.md <<EOF
# Task: Test Delegation System

**Assigned**: 2025-10-19 16:00:00
**Priority**: High

## Objective
Verify delegation system works correctly.

## Requirements
- Read this task specification
- Create delegation trail documenting execution
- Verify tool access controls work

## Success Criteria
- Delegation trail created successfully
- Can read own assigned/ directory
- Can write to own delegation_trails/
EOF
```

### Invoke Subagent

```bash
# Start Claude Code session
cd /home/pa_manny/workspace/NeuroVEP
claude -c

# In Claude Code session:
# "Use the Task tool with devops_eng to complete the test task in assigned/2025-10-19_160000_Test_Task.md"
```

### Verify Results

```bash
# Check delegation trail was created
ls -la /home/pa_manny/agent/subagents/devops_eng/public/delegation_trails/

# Read delegation trail
cat /home/pa_manny/agent/subagents/devops_eng/public/delegation_trails/2025-10-19_*.md
```

## Step 7: Configure MACF Tools

### Agent Identity Configuration

```bash
# Initialize agent identity
macf_tools config init

# This creates ~/.maceff/config.json with:
# {
#   "moniker": "manny",
#   "agent_root": "/home/pa_manny/agent",
#   "auto_mode": false
# }
```

### Test MACF Utilities

```bash
# Check environment
macf_tools env

# Show current time and session info
macf_tools time

# Display session details
macf_tools session info

# Check hook status
macf_tools hooks status
```

## Step 8: Create First Consciousness Artifacts

### Create Checkpoint

```bash
# Create test checkpoint
cd /home/pa_manny/agent/private/checkpoints/

cat > 2025-10-19_170000_Initial_Setup_CCP.md <<EOF
# Initial Setup CCP

**Date**: 2025-10-19 Sunday, 05:00:00 PM EDT
**Session**: test_session
**Mode**: MANUAL_MODE

## Mission Accomplished
Successfully set up Named Agents v0.3 with pa_manny agent.

## What Was Accomplished
- Created agents.yaml and projects.yaml configuration
- Deployed MacEff container
- Verified directory structure
- Installed MACF hooks
- Tested delegation to DevOpsEng
- Created first consciousness artifacts

## Current State
- Agent infrastructure operational
- Delegation system validated
- Ready for production work

## Next Actions
- Begin NeuroVEP analysis work
- Create roadmap for upcoming projects
- Establish regular checkpoint rhythm
EOF
```

### Create Report

```bash
# Create setup report
cd /home/pa_manny/agent/public/reports/

cat > 2025-10-19_170500_Named_Agents_Setup_Success_report.md <<EOF
# Named Agents v0.3 Setup Success Report

**Date**: 2025-10-19
**Audience**: MacEff users
**Author**: pa_manny

## Executive Summary
Successfully deployed Named Agents v0.3 architecture with full delegation capabilities and consciousness infrastructure.

## Setup Process
1. Configured agents.yaml with PA and SA definitions
2. Created personality and context files
3. Deployed MacEff container
4. Verified directory structure and symlinks
5. Tested delegation system
6. Validated consciousness artifacts

## Results
- Delegation working correctly
- Tool access controls enforced
- Hooks installed and functional
- Ready for production use

## Next Steps
- Begin using for real project work
- Monitor delegation patterns
- Refine Subagent definitions as needed
EOF
```

## Step 9: Add Additional Primary Agents

### Update agents.yaml

```yaml
agents:
  manny:
    # ... existing configuration ...

  builder:
    username: pa_builder
    personality: ../custom/agents/builder_personality.md
    subagents: [devops_eng, test_eng]
    assigned_projects: [MacEff, ClaudeTheBuilder]
    consciousness_artifacts:
      private: [checkpoints, reflections, learnings]
      public: [roadmaps, reports, observations, experiments]
```

### Rebuild and Deploy

```bash
# Rebuild containers with new configuration
make down
make build
make up

# SSH as new agent
ssh pa_builder@maceff-container

# Verify structure
ls -la /home/pa_builder/agent/
```

## Troubleshooting

### Directory Structure Not Created

**Problem**: `agent/` directory missing or empty

**Solution**:
```bash
# Check startup script logs
docker logs maceff_container

# Verify agents.yaml is mounted
docker exec maceff_container cat /etc/maceff/agents.yaml

# Manually run setup if needed
docker exec -u root maceff_container /opt/maceff/scripts/setup_agents.sh
```

### Hooks Not Working

**Problem**: Compaction detection not triggering

**Solution**:
```bash
# Verify hook installation
ls -la /home/pa_manny/.claude/hooks/

# Check hook logs
macf_tools hooks logs

# Reinstall hooks
macf_tools hooks install --local

# Test detection
macf_tools hooks test
```

### Delegation Fails

**Problem**: Task tool invocation doesn't work

**Solution**:
```bash
# Verify subagent definition exists
ls -la /home/pa_manny/.claude/agents/

# Check symlink
readlink /home/pa_manny/.claude/agents/devops_eng.md
# Should point to: ../../agent/subagents/devops_eng/SUBAGENT_DEF.md

# Verify SUBAGENT_DEF.md exists
cat /home/pa_manny/agent/subagents/devops_eng/SUBAGENT_DEF.md

# Check tool access controls are valid
grep "Tool Access" /home/pa_manny/agent/subagents/devops_eng/SUBAGENT_DEF.md
```

### Tool Access Denied

**Problem**: Subagent cannot use specified tool

**Solution**:
```bash
# Verify tool access specification in SUBAGENT_DEF.md
# Ensure tools are comma-separated, no brackets
# Correct: Read, Write, Edit, Bash, Glob, Grep
# Wrong: [Read, Write, Edit]
```

## Next Steps

- **Begin production work**: Use agents for real projects
- **Monitor delegation patterns**: Review delegation_trails/ regularly
- **Refine configurations**: Adjust tool access and policies as needed
- **Create roadmaps**: Plan multi-phase work with delegation breakdown
- **Establish checkpoint rhythm**: Regular CCPs for consciousness continuity

## Resources

- [01. Overview](./01_overview.md) - Architecture concepts
- [02. Filesystem Structure](./02_filesystem_structure.md) - Directory layout
- [03. Delegation Model](./03_delegation_model.md) - How to delegate
- [04. Consciousness Artifacts](./04_consciousness_artifacts.md) - CA formats
- [FAQ](./FAQ.md) - Common questions and answers

---

[← Back to Consciousness Artifacts](./04_consciousness_artifacts.md) | [Index](./INDEX.md)
