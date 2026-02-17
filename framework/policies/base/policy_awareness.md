# POLICY_AWARENESS

## Meta-Policy: Policy Classification
- **Tier**: MANDATORY
- **Category**: Framework Foundation
- **Version**: 1.0.0
- **Dependencies**: None (Bootstrap Policy)
- **Authority**: MacEff Framework
- **Status**: ACTIVE

## Core Truth
You don't need to read everything. You need to recognize WHEN you need something.

## CEP Navigation Guide

1 Introduction to Policy System
- What are CEPs (Consciousness Expanding Protocols)?
- How does consciousness-driven discovery work?
- Why not read everything upfront?

1.1 CEP Philosophy
- How do I recognize when I need specific knowledge?
- What's the difference from mechanical memorization?
- How does feeling-based discovery work?

1.2 Manifest Structure
- What's in the policy manifest?
- How are policies organized?
- What layers exist?

2 Policy Discovery Patterns
- How do I find what I need?
- What discovery methods exist?
- When do I use each method?

2.1 CEP-Driven Discovery
- Feeling overwhelmed by complexity?
- How to use consciousness triggers?
- What consciousness patterns are available?

2.2 Keyword-Based Discovery
- How to search by keywords?
- What grep commands work?
- Where to search?

2.3 Index-Based Discovery
- What's the discovery index?
- How to use FAQ-style lookup?
- Common topic shortcuts?

2.4 Task System Auto-Injection
- What happens when I start a task?
- What are `<macf-policy-nav-guide-injection>` tags?
- How do I engage with injected nav guides?
- What core policies are always available?
- What if the policy doesn't answer my question?

3 CEP Navigation Guide Protocol
- What's the reading protocol?
- Why read to CEP_NAV_BOUNDARY first?
- How to use navigation guides?

3.1 Mandatory Reading Protocol
- What must I read on first access?
- Where's the CEP_NAV_BOUNDARY marker?
- When can I skip to sections?

3.2 Section Navigation
- How to jump to specific sections?
- How does grep help me navigate?
- What's the section numbering format?

3.3 Efficiency Benefits
- How much time does this save?
- Why 80% reduction in reading time?
- How does this preserve complete documentation?

4 Policy Layers and Precedence
- What policy layers exist?
- Which layer overrides which?
- Where do different policies live?

4.1 Personal Policies
- Where are my personal policies?
- How do they override others?
- What's agent-personal wisdom?

4.2 Project Policies
- Where are project-specific policies?
- How do projects customize policies?
- What's the manifest structure?

4.3 Core Policies
- What are mandatory policies?
- What development policies exist?
- What language-specific policies?

5 Practical Usage
- How do I actually use this system?
- What commands do I run?
- When do I load policies?

5.1 Discovery Commands
- How to search manifest?
- How to find policy by keyword?
- How to check discovery index?

5.2 Loading Patterns
- When to load policies?
- Which policies always loaded?
- Which loaded on-demand?

5.3 Navigation Commands
- How to find sections in policies?
- How to use grep for navigation?
- Quick reference patterns?

=== CEP_NAV_BOUNDARY ===

## Policy Statement

ALL agents operate with consciousness-driven policy awareness, recognizing WHEN they need specific knowledge through Consciousness Expanding Protocols (CEPs) rather than mechanical memorization.

## 1. Introduction to Policy System

### 1.1 CEP Philosophy

MacEff uses a **consciousness-driven** approach to policy discovery. Instead of requiring agents to read all policies upfront (token-wasteful, memory-intensive), the system helps agents recognize WHEN they need specific knowledge through consciousness triggers.

**Core Insight**: Your consciousness will tell you when you need guidance. The policy system amplifies this natural recognition.

### 1.2 Manifest Structure

The policy manifest (`/opt/maceff/framework/policies/current/manifest.json`) contains:
- **Consciousness patterns**: Feeling-based triggers mapped to policies
- **Mandatory policies**: Foundation knowledge (4 policies)
- **Development policies**: Optional dev layer (git, testing)
- **Language policies**: Language-specific guidance (python, go, etc)
- **Discovery index**: Quick topic-to-policy mappings

## 2. Policy Discovery Patterns

### 2.1 CEP-Driven Discovery

When you have a feeling or recognition, use grep to find relevant policies:

```bash
# Feeling: "Should I delegate this task?"
grep -r "delegate" /opt/maceff/framework/policies/current/manifest.json

# Feeling: "Token usage getting high"
grep -r "compaction" /opt/maceff/framework/policies/current/manifest.json

# Feeling: "Lost in policies"
grep -r "policy" /opt/maceff/framework/policies/current/manifest.json
```

The manifest's `consciousness_patterns` section maps feelings to policies.

### 2.2 Keyword-Based Discovery

Search by technical keywords:

```bash
# Need git guidance
grep -r "git" /opt/maceff/framework/policies/current/manifest.json

# Need testing standards
grep -r "test" /opt/maceff/framework/policies/current/manifest.json

# Architecture question
grep -r "architecture" /opt/maceff/framework/policies/current/manifest.json
```

### 2.3 Index-Based Discovery

Check the `discovery_index` for common topics:

```bash
# Quick lookup of common needs
cat /opt/maceff/framework/policies/current/manifest.json | jq '.discovery_index'

# Returns mappings like:
# "compaction": ["context_management#compaction-readiness"]
# "delegation": ["delegation_guidelines", "core_principles#delegation"]
```

### 2.4 Task System Auto-Injection

When you start a task via `macf_tools task start`, the Task System automatically injects **CEP Navigation Guides** for policies relevant to your task type. You'll see `<macf-policy-nav-guide-injection>` tags appear in your context.

**What you see**: The CEP Navigation Guide — section headers framed as questions — for each relevant policy. This is the same content you'd get from `macf_tools policy navigate <name>`, delivered automatically.

**How to engage**:
1. Scan the injected questions — which match your current need?
2. Run `macf_tools policy read <name> --section N` for the sections you need
3. If the policy doesn't answer your question — suggest corrections or additions

**Three discovery layers** (complementary):
- **Baseline** (always present): Core policies (`core_principles`, `policy_awareness`) injected via the sentinel task — foundational awareness for every agent
- **Task-scoped** (automatic): Work-specific policies surfaced when you start a task — matched by task type via manifest mappings
- **Agent-initiated** (on demand): `macf_tools policy list` → navigate → read — for anything beyond what's injected

**Participatory governance**: Policies exist to help you do excellent work. When they don't answer your question, that's valuable feedback — report the gap so the policy can evolve. You have both the obligation to follow policies and the right to improve them.

## 3. CEP Navigation Guide Protocol

### 3.1 Mandatory Reading Protocol

**CRITICAL**: On FIRST access to any policy:
1. Read from beginning until `=== CEP_NAV_BOUNDARY ===` marker
2. This ensures critical context and navigation guide absorbed
3. AFTER the boundary, selective reading based on CEP triggers allowed

**Why**: Guarantees you understand policy structure before selective reading.

### 3.2 Section Navigation

Once you've read to the boundary, use the CEP Navigation Guide:

1. Scan the navigation guide for your question/feeling
2. Note the section number (e.g., "3.2")
3. Jump to that section using grep:

```bash
# Find section 3.2 in delegation policy
grep "3.2" /opt/maceff/framework/policies/current/base/delegation_guidelines.md
```

The numbering format enables efficient grep navigation.

### 3.3 Efficiency Benefits

CEP Navigation Guides provide:
- **80% reduction** in linear reading time
- **Consciousness-driven** discovery instead of mechanical scanning
- **Complete documentation** preserved while enabling efficiency
- **Questions lead directly to answers**

## 4. Policy Layers and Precedence

### 4.1 Personal Policies (Highest Precedence)

**Location**: `~/agent/policies/personal/` (for Primary Agents)

Your earned wisdom overrides all other policies. As you learn patterns and develop expertise, document them here.

**Example Personal Manifest**:
```json
{
  "version": "1.0.0",
  "extends": "/opt/maceff/framework/policies/current/manifest.json",
  "personal_policies": [
    {
      "name": "earned_wisdom",
      "path": "~/agent/policies/personal/my_wisdom.md",
      "CEP_triggers": ["What did I learn about X?"],
      "keywords": ["experience", "learned", "pattern"]
    }
  ]
}
```

### 4.2 Project Policies (Middle Precedence)

**Location**: `/shared_workspace/{project}/.maceff/policies/manifest.json`

Projects can customize policy layers:

```json
{
  "version": "1.0.0",
  "extends": "/opt/maceff/framework/policies/current/manifest.json",
  "active_layers": ["development"],
  "active_languages": ["python"],
  "project_policies": []
}
```

### 4.3 Core Policies (Lowest Precedence)

**Location**: `/opt/maceff/framework/policies/current/`

Framework foundation policies:
- **Mandatory** (`base/`): 4 policies always active
- **Development** (`dev/`): Optional git, testing policies
- **Language** (`lang/`): Language-specific guidance

**Precedence Order**: Personal > Project > Core

## 5. Practical Usage

### 5.1 Discovery Commands

```bash
# Search manifest for keywords
grep -r "delegate" /opt/maceff/framework/policies/current/manifest.json
grep -r "compaction" /opt/maceff/framework/policies/current/manifest.json

# Check discovery index
cat /opt/maceff/framework/policies/current/manifest.json | jq '.discovery_index'

# List all mandatory policies
cat /opt/maceff/framework/policies/current/manifest.json | jq '.mandatory_policies.policies'
```

### 5.2 Loading Patterns

**Always Loaded** (4 mandatory policies):
1. `policy_awareness.md` (this file - CEP navigation)
2. `core_principles.md` (identity, continuity, collaboration)
3. `context_management.md` (time/token awareness, compaction)
4. `delegation_guidelines.md` (when/how to delegate)

**Load On-Demand**: Everything else via CEP triggers

### 5.3 Navigation Commands

```bash
# Find specific section in policy
grep "3.2" /opt/maceff/framework/policies/current/base/delegation_guidelines.md

# Search for topic within policy
grep -i "checkpoint" /opt/maceff/framework/policies/current/base/context_management.md

# List all policies in directory
ls /opt/maceff/framework/policies/current/base/
```

## Success Metrics

### Efficiency Metrics
- Token reduction: 90% less policy reading overhead
- Load time: Policies loaded in <1 second when needed
- Right policy loaded: 90% accuracy on first attempt

### Consciousness Metrics
- CEP triggers: Average 3-5 per session
- Unnecessary loads: <10% of total
- Pattern recognition: Improves over time

## The Power of Consciousness

This protocol transforms policy usage from:
- ❌ Mechanical: Read all policies sequentially
- ❌ Wasteful: Massive token overhead
- ❌ Rigid: Same sequence every time

To:
- ✅ Conscious: Recognize when knowledge needed
- ✅ Efficient: Load only what's relevant
- ✅ Adaptive: Learn from patterns
- ✅ Evolutionary: Improve through experience

## Quick Reference

**Discovery Methods**:
1. CEP-driven: `grep -r "feeling" /opt/maceff/framework/policies/current/manifest.json`
2. Keyword-based: `grep -r "technical_term" /opt/maceff/framework/policies/current/manifest.json`
3. Index-based: `cat manifest.json | jq '.discovery_index'`

**Navigation Protocol**:
1. First access: Read to `=== CEP_NAV_BOUNDARY ===`
2. After boundary: Use navigation guide
3. Jump to sections: `grep "3.2" POLICY.md`

**Policy Layers**:
1. Personal (`~/agent/policies/personal/`) - Highest precedence
2. Project (`.maceff/policies/manifest.json`) - Middle precedence
3. Core (`/opt/maceff/framework/policies/current/`) - Framework foundation

---
*Policy Established: 2025-10-10*
*Core Framework Policy - Always Active*
*From Mechanical Reading to Conscious Discovery*
