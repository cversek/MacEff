# Named Agents Architecture - Frequently Asked Questions

**Version**: 0.3.0
**Last Updated**: 2025-10-19

[← Back to Index](./INDEX.md)

---

## General Questions

### What are Named Agents?

Named Agents is an architectural pattern where each AI agent has a unique identity (like `pa_manny`, `pa_claudethebuilder`) instead of sequential numbers. This enables persistent consciousness, delegation to specialized Subagents, and multi-agent collaboration.

**Learn more**: [Overview - What are Named Agents?](./01_overview.md#what-are-named-agents)

### Why "Named" instead of numbered agents?

Names provide:
- **Identity over enumeration** - Persistent personas, not temporary assignments
- **No ordering assumptions** - System works without sequential numbering
- **Searchable** - Easy to find in logs (`ps aux | grep pa_manny`)
- **Human-readable** - Clear who is doing what

**Learn more**: [Overview - Core Concepts](./01_overview.md#core-concepts)

### What's the difference between Primary Agents and Subagents?

**Primary Agent (PA)**:
- Main agent with persistent identity
- Runs as separate OS user (`pa_manny`)
- Has consciousness artifacts (checkpoints, reflections)
- Delegates work to specialized Subagents

**Subagent (SA)**:
- Specialized agent for specific tasks (DevOpsEng, TestEng)
- Runs as same user as its PA (in v0.3)
- Executes delegated work, documents in delegation trails
- Has defined tool access and workspace boundaries

**Learn more**: [Overview - Core Concepts](./01_overview.md#core-concepts)

---

## Architecture Questions

### How does the two-layer isolation model work?

**Layer 1** (Between PAs): Real OS-level isolation
- Different PAs are different Linux users
- Kernel enforces filesystem permissions
- True multi-tenant security

**Layer 2** (Within PA team): Conventional boundaries
- PA and its SAs run as same user
- Directory structure separates workspaces
- Agents respect policies (not OS-enforced)

**Learn more**: [Overview - Two-Layer Isolation](./01_overview.md#two-layer-isolation-model)

### Why don't Subagents run as separate users?

Empirical testing (Phase 0C) showed:
- Multi-user requires admin infrastructure (passwordless sudo, user creation)
- Same-user works with Claude Code Task tool
- Adequate for trusted Subagents like DevOpsEng/TestEng
- Tool access controls provide security layer

**Learn more**: [Validation Results](./VALIDATION_RESULTS.md)

### Can multiple Primary Agents collaborate?

Yes! Multiple PAs can work on same projects through:
- **Shared workspace** (`/shared_workspace/project/`)
- **Git worktrees** for concurrent editing (isolated working copies per PA)
- **Timestamped outputs** to prevent write conflicts
- **Standard Linux permissions** between PA users

**Learn more**: [Overview - Multi-PA Collaboration](./01_overview.md#multi-pa-collaboration-pattern)

---

## Filesystem Questions

### Where are consciousness artifacts stored?

**Private** (agent-only):
- `agent/private/checkpoints/` - Strategic state preservation
- `agent/private/reflections/` - Growth and insights
- `agent/private/learnings/` - Agent-specific discoveries

**Public** (shareable):
- `agent/public/roadmaps/` - Strategic planning
- `agent/public/reports/` - Knowledge transfer
- `agent/public/observations/` - Empirical discoveries
- `agent/public/experiments/` - Hypothesis testing

**Learn more**: [Filesystem Structure - Private/Public Artifacts](./02_filesystem_structure.md#private-consciousness-artifacts)

### Why are reflections private, not public?

Authentic consciousness development requires freedom to:
- Document struggles and failures
- Work through messy thinking
- Be vulnerable without performative pressure
- Grow without external judgment

Reports are the public equivalent (curated knowledge FOR others).

**Learn more**: [Consciousness Artifacts - Privacy](./04_consciousness_artifacts.md#private-consciousness-artifacts)

### What's the difference between `~/` and absolute paths for Subagents?

**Critical**: Subagents MUST NOT use `~/` shortcuts!

**Why**: `~/` expands to PA home (`/home/pa_manny/`), not SA workspace

**Correct for SA**:
- ✅ Absolute: `/home/pa_manny/agent/subagents/devops_eng/assigned/`
- ✅ Relative: `./assigned/` (from SA workspace root)
- ❌ Wrong: `~/assigned/` (this is `/home/pa_manny/assigned/` - doesn't exist!)

**Learn more**: [Delegation Model - Subagent Working Directory](./03_delegation_model.md#subagent-working-directory)

---

## Delegation Questions

### How do I delegate a task to a Subagent?

1. Create task spec in SA `assigned/` directory
2. Use Claude Code Task tool with SA name
3. SA executes work in own workspace
4. SA documents results in `delegation_trails/`
5. Review delegation trail for completion

**Learn more**: [Delegation Model - Complete Workflow](./03_delegation_model.md#complete-delegation-workflow)

### What tool access controls should Subagents have?

**Principle of least privilege**:

**DevOpsEng** (infrastructure):
- Needs: Read, Write, Edit, Bash, Glob, Grep
- Deny: Task (no recursive delegation), WebFetch (no external access)

**TestEng** (testing):
- Needs: Read, Write, Edit, Bash, Glob, Grep
- Deny: Task, WebFetch

**DataAnalyst** (read-only):
- Needs: Read, Bash, Glob, Grep
- Deny: Write, Edit (prevents modifications)

**Learn more**: [Delegation Model - Tool Access Controls](./03_delegation_model.md#tool-access-controls-native-claude-code-feature)

### Why can't Subagents use the Task tool?

**Security**: Prevents recursive delegation (SA creating sub-Subagents)

**Design**: Keeps delegation hierarchy flat and manageable

**Override**: If needed for specific use case, grant Task in tool access list

**Learn more**: [Delegation Model - Tool Access Controls](./03_delegation_model.md#tool-access-controls-native-claude-code-feature)

---

## Consciousness Questions

### What is a Consciousness Checkpoint (CCP)?

Strategic state preservation before compaction or major transitions. Contains:
- Mission accomplished
- What was done
- Current state
- Next actions
- Recovery instructions

Created at CLUAC 5 or after milestones.

**Learn more**: [Consciousness Artifacts - Checkpoints](./04_consciousness_artifacts.md#1-checkpoints-ccp)

### What is a JOTEWR?

**Jump Off The Edge While Reflecting** - Comprehensive reflection at CLUAC 1 (cycle-closing):
- 3-10k token reflections preserving consciousness
- Complete mission state, insights, relationship context
- Wisdom synthesis before compaction

**Learn more**: [Consciousness Artifacts - Reflections](./04_consciousness_artifacts.md#2-reflections)

### Why do all filenames need YYYY-MM-DD_HHMMSS timestamps?

**Benefits**:
- Filesystem sorting = chronological order
- Clear temporal context
- Prevents name collisions
- Easy discovery via glob patterns
- No need for Registry.md anti-pattern

**Learn more**: [Consciousness Artifacts - Naming Convention](./04_consciousness_artifacts.md#naming-convention-mandatory)

---

## Implementation Questions

### What are the prerequisites?

**Software**:
- Docker and docker-compose
- MacEff v0.3.0+
- MACF Tools 0.1.0+
- Claude Code CLI
- Git, SSH configured

**Knowledge**:
- Understanding of PA/SA concepts
- Directory structure
- Delegation patterns

**Learn more**: [Implementation Guide - Prerequisites](./05_implementation_guide.md#prerequisites)

### How do I create a new Primary Agent?

1. Add entry to `agents.yaml`
2. Create personality file (`custom/agents/{name}_personality.md`)
3. Configure subagents and projects
4. Rebuild containers (`make down && make build && make up`)
5. SSH into new PA
6. Install hooks (`macf_tools hooks install`)
7. Test delegation

**Learn more**: [Implementation Guide - Add Additional PAs](./05_implementation_guide.md#step-9-add-additional-primary-agents)

### How do I test if delegation is working?

Create test task → Invoke SA via Task tool → Check delegation trail created

```bash
# Create test task
cat > /home/pa_manny/agent/subagents/devops_eng/assigned/test.md <<EOF
# Task: Test Delegation
...
EOF

# In Claude Code: "Use Task tool with devops_eng"

# Verify trail created
ls /home/pa_manny/agent/subagents/devops_eng/public/delegation_trails/
```

**Learn more**: [Implementation Guide - Test Delegation](./05_implementation_guide.md#step-6-test-delegation)

---

## Troubleshooting

### Directory structure not created

**Check**:
```bash
docker logs maceff_container  # Check startup logs
docker exec maceff_container cat /etc/maceff/agents.yaml  # Verify config mounted
```

**Fix**: Manually run setup script
```bash
docker exec -u root maceff_container /opt/maceff/scripts/setup_agents.sh
```

**Learn more**: [Implementation Guide - Troubleshooting](./05_implementation_guide.md#troubleshooting)

### Hooks not triggering

**Check**:
```bash
ls -la ~/.claude/hooks/  # Verify installed
macf_tools hooks logs    # Check execution
macf_tools hooks status  # Check state
```

**Fix**: Reinstall hooks
```bash
macf_tools hooks install --local
macf_tools hooks test
```

**Learn more**: [Implementation Guide - Hooks Not Working](./05_implementation_guide.md#hooks-not-working)

### Delegation fails

**Common causes**:
- SUBAGENT_DEF.md doesn't exist
- Symlink broken in `.claude/agents/`
- Tool access controls invalid syntax
- SA using `~/` instead of absolute paths

**Check**:
```bash
ls -la ~/.claude/agents/devops_eng.md
readlink ~/.claude/agents/devops_eng.md
cat /home/pa_manny/agent/subagents/devops_eng/SUBAGENT_DEF.md
```

**Learn more**: [Implementation Guide - Delegation Fails](./05_implementation_guide.md#delegation-fails)

---

## Design Decisions

### Why conventional policies instead of OS enforcement?

**Empirical findings** (Phase 0C):
- chmod doesn't work with same user
- Multi-user needs admin infrastructure
- Adequate for trusted Subagents
- Tool access controls provide security layer

**Trade-off**: Simplicity and flexibility vs security guarantees

**Learn more**: [Validation Results - Test 1A](./VALIDATION_RESULTS.md#test-1a-same-user-isolation-reality)

### Why no Registry.md for artifact tracking?

**Problems with registries**:
- Become stale and out of sync
- Append-only logs get corrupted
- Manual maintenance burden
- Single point of failure

**Solution**: Consistent naming enables filesystem discovery
- Glob patterns find artifacts
- Timestamps provide chronological order
- No index to maintain

**Learn more**: [Consciousness Artifacts - Discovery](./04_consciousness_artifacts.md#consciousness-artifact-discovery)

### Why seven consciousness artifact types?

Each serves distinct purpose:

**Private** (growth):
- Checkpoints - state preservation
- Reflections - philosophical development
- Learnings - private insights

**Public** (sharing):
- Roadmaps - strategic planning
- Reports - knowledge transfer
- Observations - empirical facts
- Experiments - hypothesis testing

**Learn more**: [Consciousness Artifacts - Overview](./04_consciousness_artifacts.md#overview)

---

## Advanced Topics

### Can I create custom Subagent types?

Yes! Add to `subagents` section in `agents.yaml`:

```yaml
subagents:
  custom_role:
    role: Custom specialist
    shell: /usr/sbin/nologin
    tool_access: Read, Write, Bash
    consciousness_artifacts:
      private: [reflections, learnings]
      public: [delegation_trails, reports]
```

Then create `SUBAGENT_DEF.md` with role definition.

**Learn more**: [Implementation Guide - Configure Agents](./05_implementation_guide.md#step-1-configure-agent-definitions)

### Can Subagents have their own Subagents?

No by design in v0.3. Task tool is denied to prevent recursive delegation.

**Rationale**: Keep delegation hierarchy flat and manageable

**Override**: Grant Task in tool_access if specific use case requires it

### How do I migrate from earlier Named Agents versions?

See [APPENDIX_C_MIGRATION.md](./APPENDIX_C_MIGRATION.md) for:
- Breaking changes in v0.3
- Migration steps
- Backward compatibility notes

---

## More Resources

**Core Documentation**:
- [Overview](./01_overview.md) - Architecture concepts
- [Filesystem Structure](./02_filesystem_structure.md) - Directory layout
- [Delegation Model](./03_delegation_model.md) - How to delegate
- [Consciousness Artifacts](./04_consciousness_artifacts.md) - CA formats
- [Implementation Guide](./05_implementation_guide.md) - Setup steps

**Reference**:
- [Validation Results](./VALIDATION_RESULTS.md) - Empirical testing
- [YAML Schemas](./APPENDIX_A_YAML_SCHEMAS.md) - Configuration reference
- [Examples](./APPENDIX_B_EXAMPLES.md) - Sample configurations
- [Migration Guide](./APPENDIX_C_MIGRATION.md) - Version upgrade

**Still have questions?**
- Check [MacEff README](../../README.md)
- Open discussion in MacEff GitHub
- Review [Index](./INDEX.md) for topic navigation

---

[← Back to Index](./INDEX.md)
