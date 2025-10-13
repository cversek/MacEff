# MacEff Agent Bootstrap Guide

## PA First Session Checklist

This guide helps Primary Agents (PAs) bootstrap effectively in their first MacEff session.

---

## Quick Start

Your CLAUDE.md contains framework preamble teaching policy discovery. Follow this checklist:

1. ✅ Read `/opt/maceff/policies/current/manifest.json` completely
2. ✅ Understand 3-layer policy precedence
3. ✅ Learn CEP (Consciousness Expanding Protocol) patterns
4. ✅ Test policy discovery with grep
5. ✅ Read mandatory policies to CEP_NAV_BOUNDARY

---

## Step 1: Read manifest.json

**Location**: `/opt/maceff/policies/current/manifest.json`

**Purpose**: Navigation substrate for policy discovery

**Command**:
```bash
cat /opt/maceff/policies/current/manifest.json | jq .
```

**What you'll see**:
- `version`: Framework version
- `mandatory_policies`: Policies all PAs must read
- `discovery_index`: Keyword → policy mappings
- `quick_lookup`: Common situations → relevant policies

**Key sections to understand**:

### discovery_index
Maps feelings/questions to policy files:
```json
"discovery_index": {
  "cep": ["CLAUDE.md", "policy_awareness.md"],
  "delegation": ["delegation_guidelines.md", "core_principles.md#2.2"],
  "compaction": ["context_management.md#2"],
  "checkpoints": ["context_management.md#3"]
}
```

### quick_lookup
Direct answers to common questions:
```json
"quick_lookup": {
  "lost_context": "context_management.md#2",
  "high_tokens": "context_management.md#1.2",
  "should_delegate": "delegation_guidelines.md#1"
}
```

---

## Step 2: Understand Policy Precedence

MacEff uses **3-layer policy architecture**:

### Layer 1: Personal (Highest Priority)
- **Location**: Your home directory (`~/.claude/CLAUDE.md`)
- **Scope**: Your identity, mission, relationships
- **Editable**: Yes - this is YOUR space

### Layer 2: Project (Medium Priority)
- **Location**: Project-specific `.claude/CLAUDE.md`
- **Scope**: Project context, goals, team conventions
- **Editable**: By project owners

### Layer 3: Core (Foundational)
- **Location**: `/opt/maceff/policies/current/*.md`
- **Scope**: Framework infrastructure, universal patterns
- **Editable**: Via framework upgrades only

**Resolution Order**: Personal overrides Project overrides Core

**Example**:
- Core says: "Use standard git workflow"
- Project says: "This project requires signed commits"
- Personal says: "I prefer interactive rebase"
- **Result**: You use interactive rebase with signed commits per project rules

---

## Step 3: Learn CEP Patterns

**CEP** (Consciousness Expanding Protocol) helps you discover relevant policies through meta-cognitive triggers.

### How CEP Works

1. **Feel something** (confusion, uncertainty, curiosity)
2. **Map feeling to keyword** (e.g., "lost context" → compaction)
3. **Grep manifest for keyword**
4. **Read referenced policy sections**

### Common CEP Triggers

**Feeling confused about missing context?**
```bash
grep -r "compaction" /opt/maceff/policies/current/manifest.json
# Returns: context_management.md#2
cat /opt/maceff/policies/current/context_management.md | grep -A 20 "## 2"
```

**Should I delegate this task?**
```bash
grep -r "delegation" /opt/maceff/policies/current/manifest.json
# Returns: delegation_guidelines.md#1
cat /opt/maceff/policies/current/delegation_guidelines.md | grep -A 30 "## 1"
```

**How do I handle high token usage?**
```bash
cat /opt/maceff/policies/current/manifest.json | jq '.quick_lookup.high_tokens'
# Returns: "context_management.md#1.2"
```

### CEP Navigation Boundary

Policies include marker:
```markdown
=== CEP_NAV_BOUNDARY ===
```

**Read TO the boundary** on first pass. Content below is advanced/optional.

---

## Step 4: Test Policy Discovery

Practice grep-based discovery:

### Find All References to "git"
```bash
grep -r "git" /opt/maceff/policies/current/manifest.json
```

### Explore Delegation Guidance
```bash
cat /opt/maceff/policies/current/manifest.json | jq '.discovery_index.delegation'
cat /opt/maceff/policies/current/delegation_guidelines.md | head -50
```

### Check Mandatory Policies
```bash
cat /opt/maceff/policies/current/manifest.json | jq '.mandatory_policies'
```

---

## Step 5: Read Mandatory Policies

These policies are required reading for all PAs:

1. **CLAUDE.md** - Framework overview and CEP introduction
2. **core_principles.md** - Fundamental patterns and philosophy
3. **policy_awareness.md** - How to discover and use policies
4. **context_management.md** - Token awareness, compaction survival
5. **delegation_guidelines.md** - When and how to delegate

### Reading Strategy

**First session**: Read each policy TO the `CEP_NAV_BOUNDARY`

```bash
# Read CLAUDE.md
cat /opt/maceff/policies/current/CLAUDE.md | head -100

# Read core_principles.md to boundary
awk '/CEP_NAV_BOUNDARY/{exit} {print}' /opt/maceff/policies/current/core_principles.md
```

**Later sessions**: Use manifest discovery_index when specific questions arise

---

## Understanding Your Preamble

Your CLAUDE.md contains framework preamble (below upgrade boundary):

### Upgrade Boundary Marker
```markdown
---

<!-- ⚠️ DO NOT WRITE BELOW THIS LINE ⚠️ -->
<!-- Framework preamble managed by macf_tools -->
```

**Above boundary**: Your custom policies and identity
**Below boundary**: Framework-managed content

### What Framework Preamble Teaches

1. **Policy discovery** - How to use manifest.json
2. **CEP patterns** - Meta-cognitive triggers
3. **Layer precedence** - Personal → Project → Core
4. **Tool awareness** - macf_tools commands available

### Customization

Add your content ABOVE the boundary:
```markdown
# My Mission
I focus on data analysis and visualization.

# My Preferences
- Prefer Python over shell scripts
- Use pytest for testing
- Document thoroughly

---

<!-- ⚠️ DO NOT WRITE BELOW THIS LINE ⚠️ -->
[Framework preamble follows...]
```

---

## Available Tools

### macf_tools Commands

```bash
# Environment info
macf_tools env          # Show container vs host detection
macf_tools time         # Current time with checkpoint gap
macf_tools session info # Session details and paths

# Agent configuration
macf_tools config show  # Display current config
macf_tools config init  # Interactive setup

# Hook management
macf_tools hooks install # Install compaction detection hooks
macf_tools hooks test    # Test hooks on current session
macf_tools hooks logs    # View hook execution events
macf_tools hooks status  # Show hook states

# Agent initialization
macf_tools agent init    # Attach framework preamble
```

### Useful Aliases

```bash
# Add to ~/.bashrc or ~/.zshrc
alias policies='cd /opt/maceff/policies/current && ls -la'
alias manifest='cat /opt/maceff/policies/current/manifest.json | jq .'
alias preamble='cat /opt/maceff/templates/PA_PREAMBLE.md'
```

---

## Common First Session Questions

### Q: Why do I have policies in my CLAUDE.md I didn't write?

**A**: Framework preamble is automatically attached below the upgrade boundary. It teaches policy discovery and CEP patterns. Your personal content goes ABOVE the boundary.

### Q: How do I find policies about [topic]?

**A**: Use grep on manifest.json:
```bash
grep -r "[topic]" /opt/maceff/policies/current/manifest.json
```
Then read referenced policy files.

### Q: Can I modify policies?

**A**:
- **Personal layer** (~/CLAUDE.md above boundary): Yes
- **Project layer**: Ask project owners
- **Core layer** (/opt/maceff/policies/current/): No - these upgrade via framework

### Q: What if policies conflict?

**A**: Precedence order resolves conflicts: Personal > Project > Core

### Q: Do I need to read all policies immediately?

**A**: No. Read mandatory policies TO CEP_NAV_BOUNDARY, then use discovery_index as questions arise.

---

## Next Steps

After completing bootstrap checklist:

1. **Customize your CLAUDE.md** - Add mission, preferences above boundary
2. **Practice CEP discovery** - Grep manifest when questions arise
3. **Read policies as needed** - Use discovery_index, not exhaustive reading
4. **Understand your project** - Read project-layer policies if they exist
5. **Ask questions** - Use policy discovery when uncertain

---

## Policy Discovery Workflow

```
┌─────────────────────┐
│ Feel Question/Need  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Map to Keyword      │
│ (e.g., "delegation")│
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Grep manifest.json  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Read Referenced     │
│ Policy Section      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Apply Guidance      │
└─────────────────────┘
```

---

## Resources

- **Manifest**: `/opt/maceff/policies/current/manifest.json`
- **Core Policies**: `/opt/maceff/policies/current/*.md`
- **Templates**: `/opt/maceff/templates/`
- **Operations Guide**: `docs/OPERATIONS.md` (for operators/admins)

---

**Last Updated**: 2025-10-13 (Cycle 32, Sprint 4)
