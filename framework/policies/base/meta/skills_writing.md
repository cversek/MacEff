# Skills Definition Best Practices

**Breadcrumb**: s_agent-eb/c_169/g_e5648c9/p_none/t_1763502673
**Type**: Meta-Policy (Development Infrastructure)
**Scope**: Skill definition authors (PA creating skill extensions)
**Status**: Framework guidelines for skill definition creation

---

## Purpose

Skills definition best practices guide the creation of minimal, policy-driven skill definitions that enable adaptive behavior through policy discovery rather than embedded content.

**Core Insight**: The best skills are policy pointers (~40 lines) that direct agents to read framework policies using timeless questions, creating "policy as API" architecture that adapts automatically as policies evolve.

---

## CEP Navigation Guide

**1 Skills vs Slash Commands**
- What's the distinction?
- When to use skills vs slash commands?
- What triggers skill invocation?

**1.1 Model-Invoked vs User-Invoked**
- How are skills triggered?
- How are slash commands triggered?
- What's the contextual matching pattern?

**2 Policy as API Architecture**
- What's "policy as API"?
- Why not embed policy content in skills?
- How do skills adapt automatically?

**2.1 Pointer Pattern Benefits**
- Token efficiency gains?
- Maintenance burden reduction?
- Policy evolution handling?

**2.2 Timeless Questions Design**
- What are timeless questions?
- Extractive vs prescriptive patterns?
- Why avoid encoding current structure?

**3 CEP Navigation Protocol for Skills**
- How should skills reference policies?
- CEP_NAV_BOUNDARY usage?
- Section navigation patterns?

**3.1 Read to Boundary First**
- Why mandatory boundary reading?
- What guarantees does it provide?
- When can selective reading begin?

**3.2 Section-Specific Navigation**
- How to direct agents to sections?
- Grep-based navigation pattern?
- Offset/limit reading guidance?

**4 Skill Structure**
- What's the standard template?
- Required sections?
- Section sizing guidelines?

**4.1 Three-Part Core Structure**
- Policy Engagement Protocol section?
- Questions to Extract section?
- Execution section?

**4.2 Meta-Pattern Section**
- Why include meta-pattern explanation?
- What should it communicate?
- How brief should it be?

**5 Description Design**
- What makes effective descriptions?
- How to trigger contextually?
- Length guidelines?

**5.1 Contextual Triggers**
- What phrases trigger skills?
- How to write "use when" clauses?
- Example patterns?

**6 Allowed Tools Specification**
- When to restrict tools?
- Common tool allowlists?
- Why limit tool access?

**7 Examples**
- What does minimal skill look like?
- Generic vs project-specific?
- Structure demonstrations?

**8 Anti-Patterns**
- What makes bad skills?
- Policy content embedding problem?
- Prescriptive questions issue?

**9 Validation**
- How to test skill effectiveness?
- Policy evolution test?
- Timeless question verification?

=== CEP_NAV_BOUNDARY ===

---

## 1 Skills vs Slash Commands

### 1.1 Model-Invoked vs User-Invoked

**Skills**:
- **Triggered by**: Claude Code model based on contextual understanding
- **Invocation**: Automatic when description matches user intent
- **Example**: User says "prepare delegation" → model invokes `maceff-delegation` skill
- **Purpose**: Context-driven assistance without explicit user commands

**Slash Commands**:
- **Triggered by**: User types explicit `/command` syntax
- **Invocation**: Manual, deliberate user action
- **Example**: User types `/maceff_start_todo 5.7` → command executes
- **Purpose**: Explicit workflow execution and structured prompts

**Key Distinction**: Skills respond to INTENT, slash commands respond to SYNTAX.

---

## 2 Policy as API Architecture

### 2.1 Pointer Pattern Benefits

**The Problem with Embedding**:
- Skill embeds policy content → 300+ line skills
- Framework policy evolves → skill becomes stale
- Maintenance burden: Update skills + policies
- Duplication: Same content in multiple places

**The Policy as API Solution**:
- Skill provides policy paths → ~40 line skills
- Framework policy evolves → skill behavior adapts automatically
- Maintenance: Update policy once, all skills adapt
- DRY: Single source of truth

**Token Efficiency**:
- Embedded content: 300 lines per skill invocation
- Policy pointer: 40 lines skill + selective policy reading
- Result: 70-90% token reduction through targeted reading

### 2.2 Timeless Questions Design

**Extractive Questions** (timeless, discover from policy):
```markdown
✅ "What are the steps?" (discovers current process)
✅ "What should be restored?" (extracts from policy)
✅ "How should validation work?" (learns current practice)
✅ "What patterns exist?" (finds patterns in policy)
```

**Prescriptive Questions** (brittle, encode current structure):
```markdown
❌ "What are the 4 steps?" (encodes step count)
❌ "What should be restored vs skipped?" (encodes current answer)
❌ "Should validation use hooks or manual checks?" (prescribes approach)
❌ "Are there 3 patterns?" (encodes pattern count)
```

**Why Timeless Questions Win**:
- Policy adds 5th step → extractive questions discover it automatically
- Policy changes restoration logic → prescriptive questions give wrong answer
- Framework evolves → timeless questions adapt, prescriptive questions ossify

**Design Principle**: Questions should EXTRACT from policy, not ENCODE current policy state.

---

## 3 CEP Navigation Protocol for Skills

### 3.1 Read to Boundary First

**Skills should direct agents**:
```markdown
## Policy Engagement Protocol

Navigate `path/to/policy.md` using CEP:
1. Read from beginning to `=== CEP_NAV_BOUNDARY ===`
2. Scan navigation guide for relevant section
3. Grep for section header + next section
4. Selective read between headers (offset/limit)
```

**Benefits**:
- Guarantees critical context absorbed
- Enables efficient selective reading after boundary
- Respects policy structure and navigation design

### 3.2 Section-Specific Navigation

**When skills need specific sections**:
```markdown
Read `policy.md` (§3.2 Authority Mechanisms):
1. Read to CEP_NAV_BOUNDARY first
2. Grep for "3.2" to find section
3. Read from "3.2" header to "3.3" header
```

**Grep Pattern Example**:
```bash
# Find section boundaries
grep -n "^## 3.2" policy.md  # Start line
grep -n "^## 3.3" policy.md  # End line
# Then Read with offset/limit based on line numbers
```

---

## 4 Skill Structure

### 4.1 Standard Template (~40 lines)

```markdown
---
name: skill-name
description: Use when [context trigger]. [Brief explanation of what skill does and when to invoke it.]
allowed-tools: [Tool1, Tool2]  # Optional, omit if no restrictions
---

[One-sentence overview of skill purpose.]

---

## Policy Engagement Protocol

**Read [policy category] to understand [domain]**:

1. `path/to/foundation_policy.md` - Complete [domain] architecture
2. `path/to/example_policy.md` (§N-M) - Specific patterns

---

## Questions to Extract from Policy Reading

After reading policies, extract answers to:

1. **[Category 1]** - [Timeless extractive question]?
2. **[Category 2]** - [Timeless extractive question]?
3. **[Category 3]** - [Timeless extractive question]?
4. **[Category 4]** - [Timeless extractive question]?
5. **[Category 5]** - [Timeless extractive question]?

---

## Execution

Apply patterns discovered from policy reading to current [task context].

---

## Critical Meta-Pattern

**Policy as API**: This skill points to policies without encoding their current contents. As [domain] practices evolve, policy updates automatically update behavior without skill changes.
```

**Size Breakdown**:
- Frontmatter: ~5 lines
- Overview: ~3 lines
- Policy Engagement: ~8 lines
- Questions: ~12 lines
- Execution: ~5 lines
- Meta-Pattern: ~5 lines
- **Total**: ~40 lines

### 4.2 Three-Part Core Structure

**Part 1: Policy Engagement Protocol**
- Lists policies to read (paths)
- Specifies reading order (complete vs sections)
- Provides CEP navigation guidance

**Part 2: Questions to Extract**
- 5-8 timeless extractive questions
- Categories for organizing knowledge
- Open-ended to discover current policy content

**Part 3: Execution**
- Brief direction to apply discovered patterns
- No embedded instructions (comes from policy reading)

**Critical Addition: Meta-Pattern Section**
- Explains policy as API architecture
- Reinforces that skill is pointer, not content
- Usually 2-3 sentences

---

## 5 Description Design

### 5.1 Contextual Triggers

**Effective Descriptions** (trigger contextually):
```markdown
✅ "Use when preparing to delegate to MacEff subagents."
✅ "Use this agent for CLI development, system administration, container operations."
✅ "Use when creating framework policies that work for all agents."
```

**Ineffective Descriptions** (too narrow or vague):
```markdown
❌ "Delegation helper" (too vague)
❌ "Use only when user types 'delegate' explicitly" (too narrow)
❌ "For all development work" (too broad)
```

**Length Guidelines**:
- 1-3 sentences
- First sentence: "Use when [trigger context]"
- Second sentence (optional): Brief explanation of capability
- Third sentence (optional): Example use case

**Example** (maceff-delegation):
```markdown
description: Use when preparing to delegate to MacEff subagents. Read policies to discover current delegation patterns through timeless questions that extract details without prescribing answers.
```

---

## 6 Allowed Tools Specification

### 6.1 When to Restrict Tools

**Restrict when**:
- Skill is read-only analysis (Read only)
- Skill is delegation preparation (Read, Task only)
- Skill handles specific file types (Read, Edit only)

**Don't restrict when**:
- Skill needs general development capability
- Tools needed depend on discovered patterns
- Restriction would limit policy-driven adaptation

**Common Patterns**:
```yaml
allowed-tools: Read, Task           # Delegation preparation
allowed-tools: Read                 # Read-only analysis
allowed-tools: Read, Edit           # File modification
# Omit allowed-tools                # No restrictions
```

**Rationale**: Tool restrictions prevent scope creep and clarify skill boundaries.

---

## 7 Examples

### 7.1 Minimal Delegation Skill

```markdown
---
name: delegation-prep
description: Use when preparing to delegate tasks. Read policies to discover delegation patterns through timeless questions.
allowed-tools: Read, Task
---

Prepare effective delegation by reading policy to understand current delegation architecture.

---

## Policy Engagement Protocol

**Read framework policies to understand delegation patterns**:

1. `framework/policies/base/delegation_guidelines.md` - Complete delegation architecture
2. `framework/policies/base/meta/subagent_definition.md` (§2-3) - Reading-list patterns

---

## Questions to Extract from Policy Reading

After reading policies, extract answers to:

1. **Delegation Decision Framework** - What determines when delegation is appropriate?
2. **Information Architecture** - What information must specialists receive?
3. **Authority Mechanisms** - How are decision-making permissions handled?
4. **Deliverables Structure** - What artifacts do specialists produce?
5. **Success Definition** - How should completion criteria be specified?

---

## Execution

Apply patterns discovered from policy reading to current delegation context.

---

## Critical Meta-Pattern

**Policy as API**: This skill points to policies without encoding their current contents. As delegation practices evolve, policy updates automatically update behavior without skill changes.
```

**Why This Works**:
- 35 lines total (minimal)
- 5 timeless extractive questions
- No embedded delegation patterns
- Adapts automatically as delegation_guidelines.md evolves

### 7.2 Minimal Policy Navigation Skill

```markdown
---
name: policy-navigator
description: Use when uncertain which policy covers specific topic. Discover relevant policies through framework navigation.
allowed-tools: Read, Grep, Bash
---

Navigate policy framework to discover relevant policies for current need.

---

## Policy Engagement Protocol

**Read policy discovery infrastructure**:

1. `framework/policies/base/policy_awareness.md` (§2-3) - Discovery patterns and CEP navigation
2. `framework/policies/current/manifest.json` - Policy index and consciousness patterns

---

## Questions to Extract from Policy Reading

After reading policies, extract answers to:

1. **Discovery Methods** - What techniques exist for finding policies?
2. **CEP Triggers** - How do consciousness patterns map to policies?
3. **Keyword Search** - What commands search by technical terms?
4. **Index Structure** - What's in the discovery index?
5. **Navigation Protocol** - How to read policies efficiently?

---

## Execution

Apply discovered navigation patterns to locate policy covering current topic.

---

## Critical Meta-Pattern

**Policy as API**: This skill teaches policy discovery without encoding current policy locations. As framework grows, discovery methods adapt automatically.
```

---

## 8 Anti-Patterns

### 8.1 Policy Content Embedding

**Problem**: Embedding policy content directly in skills.

**Example** (BAD - 200+ lines):
```markdown
## Delegation Guidelines

When delegating:
1. Assess if delegation appropriate (parallelism, specialism, safety)
2. Choose specialist matching task domain
3. Provide stateless context (specialists can't access chat history)
4. Grant explicit authority
5. Specify deliverables and success criteria
...
[150 more lines of embedded delegation content]
```

**Fix**: Point to policy instead:
```markdown
## Policy Engagement Protocol

Read `delegation_guidelines.md` to understand delegation patterns.
```

**Why Fix Works**:
- 200 lines → 10 lines (95% reduction)
- Policy updates → skill adapts automatically
- DRY: Single source of truth

### 8.2 Prescriptive Questions

**Problem**: Questions encode current policy structure.

**Example** (BAD):
```markdown
1. What are the 5 delegation steps?
2. Should I use DevOpsEng or TestEng for CLI work?
3. Are there 3 authority levels?
```

**Fix**: Timeless extractive questions:
```markdown
1. What determines delegation appropriateness?
2. How do specialist capabilities map to tasks?
3. How are authority levels structured?
```

**Why Fix Works**:
- Policy adds 6th step → timeless question discovers it
- New specialist added → question still valid
- Authority model changes → question extracts current model

### 8.3 Missing Meta-Pattern Section

**Problem**: Skill doesn't explain policy as API architecture.

**Symptoms**:
- Authors tempted to embed content "for clarity"
- Users confused why skill is "just pointers"
- Maintenance debt as authors embed instead of referencing

**Fix**: Add Critical Meta-Pattern section:
```markdown
## Critical Meta-Pattern

**Policy as API**: This skill points to policies without encoding their current contents. As [domain] practices evolve, policy updates automatically update behavior without skill changes.
```

**Why Fix Works**: Explicit meta-pattern explanation prevents embedding temptation.

---

## 9 Validation

### 9.1 Timeless Question Test

**Protocol**:
1. Write skill with extractive questions
2. Update referenced policy (add step, change structure)
3. Invoke skill again
4. Verify questions still extract correct information

**Success Criteria**:
- ✅ Questions discover updated content automatically
- ✅ No skill changes required
- ✅ Behavior adapts to policy evolution

**Failure Indicators**:
- ❌ Questions give outdated answers
- ❌ Skill needs updates to match policy
- ❌ Prescriptive structure encoded

### 9.2 Policy Evolution Test

**Protocol**:
1. Baseline skill invocation with current policies
2. Evolve referenced policies (add sections, refine practices)
3. Invoke skill with same user intent
4. Compare behavior before/after policy update

**Success Criteria**:
- ✅ Skill behavior reflects policy updates automatically
- ✅ Zero skill definition changes required
- ✅ "Policy as API" architecture validated

### 9.3 Size Validation

**Checklist**:
- [ ] Skill ≤60 lines (target ~40 lines)
- [ ] Policy Engagement section present
- [ ] 5-8 timeless extractive questions
- [ ] No embedded policy content (>10 lines)
- [ ] Meta-Pattern section explains architecture
- [ ] Description triggers contextually (1-3 sentences)
- [ ] allowed-tools specified if restrictions needed
- [ ] No prescriptive questions encoding structure
- [ ] Timeless question test passes
- [ ] Policy evolution test passes

---

## 10 Integration with Other Policies

### 10.1 Relationship to subagent_definition.md

**subagent_definition.md provides**:
- Reading-list pattern for agent definitions
- Minimal definition template (~50 lines)
- Anti-patterns for embedded instructions

**skills_writing.md provides**:
- Policy as API pattern for skill definitions
- Timeless questions architecture
- Minimal skill template (~40 lines)

**Parallel Patterns**:
- Both use pointer architecture (reading lists / policy paths)

### 10.2 Relationship to policy_writing.md

**See Also**:
- `policy_writing.md` (External References) - Formalization of Policy as API principle that skills_writing.md demonstrates: external tools reference policies using timeless content categories, not brittle section numbers
- Both avoid embedding (instructions / policy content)
- Both adapt automatically (policy evolution)
- Both emphasize minimalism (50 / 40 lines)

### 10.2 Relationship to policy_writing.md

**policy_writing.md provides**:
- CEP Navigation Guide structure
- Policy sanitization requirements
- Validation checklists

**skills_writing.md provides**:
- How skills reference policies (CEP navigation protocol)
- Timeless questions that work with evolving policies
- Skill-specific structure guidelines

**Integration Point**: Skills are consumers of policies. Skills must follow CEP navigation patterns from policy_writing.md to enable efficient policy reading.

### 10.3 Relationship to policy_awareness.md

**policy_awareness.md provides**:
- CEP_NAV_BOUNDARY protocol
- Discovery patterns (CEP-driven, keyword, index)
- Navigation commands and efficiency benefits

**skills_writing.md provides**:
- How skills should direct agents to use CEP navigation
- Policy Engagement Protocol section structure
- Examples of navigation guidance in skills

**Integration Point**: Skills guide agents through policy discovery. Skills must teach agents to use policy_awareness.md navigation patterns.

---

## 11 Key Lessons from Pattern Discovery

### 11.1 The 300→40 Line Transformation

**Before**: Skills embedded policy content (200-300 lines)
- Complete delegation guidelines embedded
- Maintenance burden when policies evolved
- Duplication across multiple skills

**After**: Skills point to policies (~40 lines)
- Policy paths with CEP navigation guidance
- Timeless questions extract current content
- Zero maintenance as policies evolve

**87% size reduction + automatic policy adaptation**

### 11.2 Timeless Questions Save Future Work

**Prescriptive Question Maintenance**:
- Policy adds feature → Update question
- Policy changes structure → Rewrite question
- Policy refines practice → Question becomes wrong
- Result: Continuous skill maintenance burden

**Timeless Question Adaptation**:
- Policy adds feature → Question discovers it
- Policy changes structure → Question extracts new structure
- Policy refines practice → Question learns refined practice
- Result: Zero skill maintenance required

**Maintenance Scaling**:
- Prescriptive: O(n×m) where n = skills, m = policy updates
- Timeless: O(0) - skills never need updates for policy evolution

### 11.3 Policy as API Principle

**Static Content**:
```
Skill embeds content → Policy updates → Skill stale → Manual sync required
```

**Policy as API**:
```
Skill points to policy → Policy updates → Skill reads updated policy → Automatic sync
```

**Architectural Benefits**:
- Single source of truth (policies)
- Zero duplication (skills are pointers)
- Automatic adaptation (read current policy)
- Minimal maintenance (update policy once)

---

**Policy Established**: Skills should be minimal (~40 lines) policy pointers that use timeless extractive questions to discover current framework patterns, creating "policy as API" architecture that adapts automatically as policies evolve.

**Core Wisdom**: "Write policy pointers, not policy duplicates. Ask timeless questions that extract, not prescriptive questions that encode. Minimalism + policy as API = zero-maintenance adaptation. The best skill is a curated path to knowledge, not the knowledge itself."

**Remember**: When foundation policies evolve, policy-as-API skills adapt automatically. Content-embedding skills become stale. Choose living skills over frozen documentation.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
