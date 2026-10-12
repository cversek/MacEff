# POLICY_AWARENESS

## Meta-Policy: Policy Classification
- **Tier**: MANDATORY
- **Category**: Framework Foundation
- **Version**: 1.1.0
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

2.5 When to Consult the Corpus (the pull obligation)
- Discovery is pull, not push — so when am I expected to consult?
- What are the recognised-demand moments?
- Which commands are the on-demand path (keyword vs semantic)?
- Why is there no per-prompt recommendation injection?

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

4.4 Package Policy Sets (Extra Roots)
- How does a package's own policy set become readable without copying it into the framework?
- How is a policy name resolved when it exists in more than one place?
- What happens when a root is missing or two roots carry the same name?

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

The policy manifest (`/opt/maceff/framework/policies/manifest.json`) contains:
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
grep -r "delegate" /opt/maceff/framework/policies/manifest.json

# Feeling: "Token usage getting high"
grep -r "compaction" /opt/maceff/framework/policies/manifest.json

# Feeling: "Lost in policies"
grep -r "policy" /opt/maceff/framework/policies/manifest.json
```

The manifest's `consciousness_patterns` section maps feelings to policies.

### 2.2 Keyword-Based Discovery

Search by technical keywords:

```bash
# Need git guidance
grep -r "git" /opt/maceff/framework/policies/manifest.json

# Need testing standards
grep -r "test" /opt/maceff/framework/policies/manifest.json

# Architecture question
grep -r "architecture" /opt/maceff/framework/policies/manifest.json
```

### 2.3 Index-Based Discovery

Check the `discovery_index` for common topics:

```bash
# Quick lookup of common needs
cat /opt/maceff/framework/policies/manifest.json | jq '.discovery_index'

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

### 2.5 When to Consult the Corpus (the pull obligation)

Discovery in MacEff is **pull, not push**. The corpus is not fired into your
context every turn; you reach for it when you recognise you need it. That makes
*recognising the need* the discipline — and because the need is easy to skip
past under momentum, this section names the moments the framework expects a
consultation, so "nobody pushed it at me" is never a reason it was missed.

**Recognised-demand moments — consult before proceeding:**

- **Task and phase orientation.** Starting a task or a roadmap phase is the
  canonical pull moment; `task start` already surfaces CEP nav guides (§2.4),
  and you extend that with `policy read` for anything the guides point at.
- **Before shipping a fix or a capability.** A change that alters what an agent
  or operator may do is governed — read the policy that governs it before you
  land it (this is the discipline behind *policy ships with the capability*).
- **When a bug resists the first hypothesis.** A second failed attempt is a
  signal to check whether a policy or learning already describes the class of
  problem, rather than theorising further.
- **On entering an unfamiliar domain.** Before working in a subsystem you have
  not touched, orient in its governing policy and its learnings index.

These are moments where *the demand is recognised*, which is exactly when pull
works. Binding policy engagement to them is the pattern the framework uses
everywhere; it does not need a per-turn injection to function.

**The on-demand path (both layers stay available):**

```bash
macf_tools policy list                 # what exists
macf_tools policy navigate <name>      # its CEP question-map (framing before content)
macf_tools policy read <name>          # the policy itself
macf_tools policy search <keyword>     # curated keyword search over the manifest — always available, no optional deps
macf_tools policy recommend "<query>"  # semantic hybrid search — richer, requires the optional search index
```

`policy search` is the **always-available keyword fallback**; `policy recommend`
is the **semantic** path and depends on the optional search index — when that
index or its dependencies are absent it now says so at the point of use (with
the install/build hint) rather than returning empty. A recommender you invoke
when you want one is a tool; use it at the moments above.

**Why no per-prompt recommendation injection (GH#211):** push floods, and what
floods gets skimmed. An injection nobody reads still *looks* like policy
awareness, which is worse than no injection at all — for the same reason an
ignored gate is worse than no gate. A per-turn recommender also drew from a
snapshot index that nothing rebuilds automatically, and on at least one host it
had silently degraded to a no-op that nobody noticed *because* nothing depended
on it. Retiring the push and investing in on-demand search that degrades loudly
is the pull model applied to its own tooling.

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
grep "3.2" /opt/maceff/framework/policies/current/delegation_guidelines.md
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
  "extends": "/opt/maceff/framework/policies/manifest.json",
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
  "extends": "/opt/maceff/framework/policies/manifest.json",
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

### 4.4 Package Policy Sets (Extra Roots)

A package that ships its own policies in MacEff's format (policy ships with the capability) is read **where it lives**, never copied into the framework's tree. In a container, that tree is group-owned by the policy editors, and an agent can't add to it without provisioning.

**`MACEFF_POLICY_ROOTS`** names extra directories, separated like `PATH`. Each entry is a path, which the directory's own name then names, or `name=path`, to choose the name. For example: `MACEFF_POLICY_ROOTS=agentcad=/path/to/agentcad/policies`. The framework's root is always searched first, and the extra roots follow in the order given. `macf_tools policy list` names each extra root and its path, and lists its policies under the root's name. `list`, `navigate`, `read` and `inject` all reach them.

**How a name resolves:**
- **`<root>:<policy>` names the root explicitly**, for example `agentcad:agentcad-usage` or `framework:task_management`. The separator is `:` because `/` already means parent directories (`development/task_management`), and both can combine: `agentcad:cad/agentcad-export`.
- **A name the framework has is always the framework's.** If an extra root carries a file of the same name, it's reported once and not used. A package can add policy, but it can never make a core policy unreadable or replace one by accident. Read its copy by qualifying it.
- **A name found in two or more extra roots, and not in the framework, is refused as ambiguous.** The refusal names every candidate and the qualified names that resolve each. Walk order never decides silently. Inside a hook (policy injection, task-start guides), the refusal is printed and that policy skipped, so a hook never fails over it.

**Who may write a root.** A policy read from a root becomes the agent's instructions, through `read`, `navigate` and `inject`, so anyone who can write a root can write those instructions. A root is used only when no one but this user can change it:
- the root, every directory and `.md` file under it, and every directory above it are owned by this user or by root;
- none is writable by every account, or by a group that has any account besides this user. A user-private group, whose only member is the user, grants nobody else anything, so its write bit is allowed;
- a directory above the root may be writable by everyone if it is sticky, like `/tmp`, because there no one else can rename or replace the root.

A root that fails is refused once, naming the path and why. The framework's own tree meets this bar differently, through a group of policy editors someone granted on purpose. A root shared with an editors' group is not supported yet: grant it as the framework's tree is, and ask for that form if a package needs it.

**What is refused at the root.** An entry whose directory is missing or unreadable, whose name is empty, contains `/` or `:`, or is `framework`, or repeats an earlier entry's name, or that someone else could write (above), is reported once and left out. It's never skipped silently, because "no policies found" and "this root couldn't be read" send a reader to different places.

**Not covered yet:** `macf_tools policy search` and the search index read the framework's manifest, which extra roots don't have. A package's policies are found by name and by `list`, not by keyword search.

**Prefix your files.** A set whose files share a prefix (`agentcad-*.md`) never meets the ambiguity refusal, and its names say where they came from.

## 5. Practical Usage

### 5.1 Discovery Commands

```bash
# Search manifest for keywords
grep -r "delegate" /opt/maceff/framework/policies/manifest.json
grep -r "compaction" /opt/maceff/framework/policies/manifest.json

# Check discovery index
cat /opt/maceff/framework/policies/manifest.json | jq '.discovery_index'

# List all mandatory policies
cat /opt/maceff/framework/policies/manifest.json | jq '.mandatory_policies.policies'
```

### 5.2 Loading Patterns

**Always Loaded** (4 mandatory policies):
1. `policy_awareness.md` (this file - CEP navigation)
2. `core_principles.md` (identity, continuity, collaboration)
3. `context_management.md` (time/token awareness, compaction)
4. `delegation_guidelines.md` (when/how to delegate)

**Load On-Demand**: Everything else via CEP triggers and the recognised-demand
moments in §2.5 (task/phase orientation, before shipping a fix, when a bug
resists the first hypothesis, entering an unfamiliar domain), using
`macf_tools policy search`/`recommend`.

### 5.3 Navigation Commands

```bash
# Find specific section in policy
grep "3.2" /opt/maceff/framework/policies/current/delegation_guidelines.md

# Search for topic within policy
grep -i "checkpoint" /opt/maceff/framework/policies/current/context_management.md

# List all policies in directory
ls /opt/maceff/framework/policies/current/
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
1. CEP-driven: `grep -r "feeling" /opt/maceff/framework/policies/manifest.json`
2. Keyword-based: `grep -r "technical_term" /opt/maceff/framework/policies/manifest.json`
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

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — on-demand
     policy discovery, CEP navigation, and layer precedence. -->

[[policy_as_api]] [[discoverability]] [[methodology]]

---
*Policy Established: 2025-10-10*
*Core Framework Policy - Always Active*
*From Mechanical Reading to Conscious Discovery*
