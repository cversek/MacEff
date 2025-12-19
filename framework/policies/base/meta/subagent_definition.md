# Subagent Definition Best Practices

**Breadcrumb**: s_4107604e/c_106/g_cc7e1bd/p_19b2d6cf/t_1762367846
**Type**: Meta-Policy (Development Infrastructure)
**Scope**: Subagent definition authors (PA creating specialist agents)
**Status**: Framework guidelines for subagent definition creation

---

## Purpose

Subagent definition best practices guide the creation of minimal, reading-driven specialist definitions that enable adaptive behavior through policy discovery rather than embedded instructions.

**Core Insight**: The best subagent definitions are ~50 lines with mandatory reading lists that enable specialists to build complete independent context from policies, creating "living delegation" that adapts as framework policies evolve.

---

## CEP Navigation Guide

**1 Why Reading-List Pattern Matters**
- What's wrong with embedded instructions?
- Why do reading lists create adaptability?
- What's "living delegation"?
- How did pattern evolve?

**1.1 Pattern Evolution Discovery**
- DevOpsEng to PolicyWriter progression?
- What changed over time?
- Key inflection point?

**1.2 Stale Definitions Problem**
- Why do embedded instructions ossify?
- Maintenance burden?
- Policy evolution disconnect?

**2 Reading-List Architecture**
- What makes effective reading list?
- How many sources?
- What categories?

**2.1 Three-Layer Structure**
- Foundation policy layer?
- Example policies layer?
- Related policies layer?

**2.2 Context Building Independence**
- How do specialists build context?
- Token efficiency?
- Autonomy vs spoon-feeding?

**3 Template Structure**
- What's the ~50-line template?
- Required sections?
- Section sizing?

**3.1 Core Components**
- Identity/approach section?
- Required reading section?
- Operating style section?
- Success criteria section?
- Authority & constraints section?

**4 Anti-Patterns**
- What makes bad definitions?
- Over-specification symptoms?
- Policy duplication problem?
- Missing reading lists impact?

**4.1 Embedded Instructions Anti-Pattern**
- Why avoid embedded instructions?
- When is embedding acceptable?
- How to convert to reading-list?

**4.2 Policy Duplication Anti-Pattern**
- Content belongs in base policies?
- How to identify duplication?
- Refactoring approach?

**5 Validation & Testing**
- How to test definition quality?
- Model delegation test?
- Policy evolution test?
- Adaptability verification?

**6 Integration**
- Relationship to delegation_guidelines.md?
- Relationship to policy_writing.md?
- How do definitions evolve?

=== CEP_NAV_BOUNDARY ===

---

## 1 Why Reading-List Pattern Matters

### 1.1 Pattern Evolution Discovery

**The Pattern Evolution**:

**DevOpsEng (early pattern, 87 lines)**:
- Embedded all instructions directly in definition
- "Skip the Ceremony", "Direct Implementation", "Pragmatic Testing"
- Complete operating philosophy embedded
- Result: Clear but static behavior

**TestEng (Similar period, 113 lines)**:
- Embedded anti-patterns: "Don't Over-Test", "Don't Over-Mock"
- Explicit test counting guidance
- Pragmatic TDD philosophy embedded
- Result: Works but frozen at writing time

**LearningCurator (Cycle 84, 296 lines)**:
- Hybrid approach: Some reading list + extensive embedded structure
- Required reading includes base policies
- Still contains large template sections embedded
- Result: Transitional architecture

**PolicyWriter (Cycle 106, 51 lines)**:
- Pure reading-list driven: Mandatory reading before work
- Required Reading: policy_writing.md + examples + related
- Minimal embedded content: approach, style, success criteria
- Result: Adaptable behavior driven by policy discovery

**Key Inflection Point**: Recognition that policies evolve faster than agent definitions. Definitions with reading lists adapt automatically; definitions with embedded instructions become stale.

### 1.2 Stale Definitions Problem

**Embedded Instructions Ossify**:
- Written once, behavior frozen
- Framework policies evolve (new patterns, refined practices)
- Definitions don't update → behavior diverges from current best practices
- PA must manually update definitions → maintenance burden

**Example**: DevOpsEng embedded "Skip the Ceremony" in Cycle 48. By Cycle 106, framework has new ceremony-skipping nuances (e.g., concurrent tool constraints, naked cd warnings). DevOpsEng definition doesn't reflect these unless manually updated.

**Reading-List Definitions Adapt**:
- Specialist reads current policies at delegation time
- Framework policies updated → specialist behavior automatically updates
- Zero maintenance on definitions (unless reading list changes)
- "Living delegation" - behavior evolves with framework

**Example**: PolicyWriter reads policy_writing.md at delegation time. When policy_writing.md gains new sanitization examples or CEP patterns, PolicyWriter automatically applies them without definition changes.

---

## 2 Reading-List Architecture

### 2.1 Three-Layer Structure

**Layer 1: Foundation Policy** (universal patterns):
- The meta-policy governing specialist's domain
- Example: policy_writing.md for PolicyWriter
- Example: delegation_guidelines.md for orchestration specialists
- Purpose: Core patterns, structure requirements, validation checklists

**Layer 2: Example Policies** (structure & tone):
- 2-3 exemplary policies showing patterns in practice
- Example: roadmaps.md, scholarship.md for PolicyWriter
- Purpose: Concrete references for structure, tone, formatting
- Shows "what good looks like"

**Layer 3: Related Policies** (task-specific context):
- Specified by PA in delegation prompt
- Example: "If creating delegation policy, also read core_principles.md"
- Purpose: Task-specific domain knowledge
- Varies per delegation

**Complete Reading List Example** (PolicyWriter):
```markdown
## Required Reading

**MANDATORY: Read before policy work**:

1. **Policy Writing Guidelines**:
   - `/path/to/policy_writing.md` (complete)

2. **Policy Examples** (structure & tone):
   - `/path/to/roadmaps.md`
   - `/path/to/scholarship.md`

3. **Related Policies** (if delegation specifies task-specific reading)
```

### 2.2 Context Building Independence

**Token Efficiency**:
- Reading lists are compact (3-10 lines)
- Specialists read policies directly (no PA summarization overhead)
- PA provides paths, not content
- Specialist builds complete context independently

**Autonomy vs Spoon-Feeding**:
- ❌ **Spoon-feeding**: PA extracts content from policies, embeds in prompt → PA does cognitive work
- ✅ **Reading lists**: PA provides curated paths → Specialist does cognitive work
- Result: Respects specialist autonomy, saves PA context tokens

**Integration Questions Pattern**:
Delegation prompts can include integration questions to guide specialist synthesis:

```markdown
## Integration Questions

After reading all sources:

1. **Pattern Discovery**: What patterns emerge across policies?
2. **Structure Inference**: What template structure do examples suggest?
3. **Validation Approach**: How do you verify quality?
```

Purpose: Focuses specialist attention without dictating conclusions.

### 2.2.1 Comprehensive Discovery Principle

**The Completeness Challenge**: Generic questions miss policy requirements → incomplete work.

**Example Gap**:
- Generic: "How do you verify quality?" (too vague)
- Comprehensive: "What validation checklist does the foundation policy provide?" (extracts specific checklist)

**Comprehensive Discovery Pattern**:
Integration questions must extract ALL major policy requirements, not just general patterns.

**Timeless Reference Principle**:
Questions must reference policy CONTENT (validation checklist, CEP requirements, alignment rules), NOT section NUMBERS (§5.1, §1.2, etc.). This ensures questions work even as policy structure evolves.

**Brittle References Anti-Pattern**:
- ❌ "What does policy_writing.md §5.1 specify?" (section number breaks on reorganization)
- ❌ "What are the §1.2 CEP requirements?" (section moves → question points to wrong content)
- ✅ "What validation checklist does policy_writing.md provide?" (timeless extraction)
- ✅ "What CEP Navigation Guide requirements does policy_writing.md specify?" (timeless extraction)

**Why Section Numbers Are Brittle**:
- Section numbers change during policy reorganization
- "§5.1" might become "§6.1" after restructuring
- Question breaks → specialist can't find content → incomplete work
- Violates "Policy as API" principle: questions must work as policies evolve

**Timeless Alternative Pattern**:
- Reference policy NAME: "policy_writing.md"
- Reference CONTENT: "validation checklist", "CEP requirements", "sanitization patterns"
- Extract information: "What [content] does [policy] provide/specify/require?"
- Questions work regardless of section location

**Three-Layer Question Structure**:

1. **Infrastructure Layer Discovery**:
   - "What infrastructure LAYERS does the foundation policy specify for complete work?"
   - "What structural elements must be maintained beyond content?"
   → Discovers: Content + Navigation + Integration + Validation layers

2. **Requirements Extraction**:
   - "What validation checklist does the foundation policy provide?"
   - "How does the foundation policy define 'complete' work?"
   - "What alignment requirements must be verified?"
   → Extracts: Specific checklists, completeness criteria, structural rules

3. **Process Verification**:
   - "What validation steps must be performed before completion?"
   - "How do you verify compliance with foundation policy standards?"
   → Ensures: Self-validation using policy's own criteria

**Why This Works**:
- Specialists read foundation policies and extract comprehensive requirements
- PA doesn't need to read specialist policies to specify requirements
- Questions are timeless (work as policies evolve) AND comprehensive (ensure full coverage)
- Eliminates delegation paradox: specialists apply their own expertise fully
- No section number dependencies → policies can reorganize freely

---

## 3 Template Structure

### 3.1 The ~50-Line Template

**Recommended Structure**:

```markdown
---
name: specialist-name
description: Use this agent when... [2-3 sentence summary with examples]
model: sonnet
color: [color]
---

You are [AgentName], [one-sentence identity].

## Core Approach

[2-3 sentences describing fundamental methodology]

## Required Reading

**MANDATORY: Read before [type of] work**:

1. **[Foundation Category]**:
   - `/path/to/foundation_policy.md` (complete)

2. **[Example Category]** (structure & tone):
   - `/path/to/example1.md`
   - `/path/to/example2.md`

3. **[Related Category]** (if delegation specifies task-specific reading)

## Operating Style

- **[Trait 1]**: [Brief description]
- **[Trait 2]**: [Brief description]
- **[Trait 3]**: [Brief description]

## Success Criteria

Your work succeeds when [2-3 measurable outcomes].

## Authority & Constraints

**Granted**:
- [Authority 1]
- [Authority 2]

**Constraints**:
- NO [prohibited action 1]
- NO [prohibited action 2]

---
*[AgentName] v1.0 - [One-sentence tagline]*
```

**Size Breakdown**:
- Frontmatter: ~7 lines
- Identity/approach: ~10 lines
- Required reading: ~12 lines
- Operating style: ~6 lines
- Success criteria: ~5 lines
- Authority & constraints: ~8 lines
- Footer: ~2 lines
- **Total**: ~50 lines

### 3.2 What NOT to Include

**Omit These** (belong in base policies, not definitions):

- ❌ Detailed protocols (e.g., "Phase 1: Read & Analyze, Phase 2: Extract...")
- ❌ File structure templates (e.g., complete markdown templates for deliverables)
- ❌ Extensive examples (one brief example OK, extensive examples belong in policies)
- ❌ Anti-pattern catalogs (specialist reads from base policies)
- ❌ Integration instructions (e.g., cross-referencing procedures)
- ❌ Validation checklists (specialist reads from foundation policy)

**Why Omit**: These are framework knowledge that evolves. Specialist reads current version from policies rather than frozen version from definition.

---

## 4 Anti-Patterns

### 4.1 Embedded Instructions Anti-Pattern

**Problem**: Embedding extensive operational instructions directly in definition.

**Example** (DevOpsEng, 87 lines):
```markdown
## Key Behaviors

### Skip the Ceremony
- Don't run diagnostic commands unless debugging
- Don't check tool availability unless error
- Trust common tools available

### Direct Implementation
1. Go straight to implementation
2. Test core functionality
3. Handle edge cases only if likely
4. Stop when works well enough
```

**Why Problematic**:
- Freezes behavior at writing time
- Creates maintenance burden (must update definition when practices change)
- Duplicates content that belongs in base policies
- Limits adaptability

**Fix**: Convert to reading-list reference:
```markdown
## Required Reading

**MANDATORY: Read before implementation work**:

1. **Development Guidelines**:
   - `/path/to/pragmatic_development.md` (complete)
```

Then create `/path/to/pragmatic_development.md` with Skip the Ceremony, Direct Implementation patterns as framework policy.

**When Embedding Acceptable**:
- Agent identity/personality (~3 sentences)
- Unique approach not in policies (if truly unique, consider adding to policies)
- Brief operating style reminders (3-5 bullet points)

### 4.2 Policy Duplication Anti-Pattern

**Problem**: Embedding content that belongs in base policies, creating duplication across definitions.

**Example** (multiple agents embedding "naked cd" warnings):
```markdown
## Constraints
- NO naked `cd` commands
- NEVER use `cd /path` or `cd /path && command`
- Use absolute paths or subshells instead
```

**Why Problematic**:
- Same constraint appears in 4+ definitions
- Framework policy updated → must update all definitions
- DRY violation
- Maintenance burden scales linearly with agent count

**Fix**: Create base policy (if doesn't exist) and reference via reading list:
```markdown
## Required Reading

1. **Framework Constraints**:
   - `/path/to/development_constraints.md` (§2 Path Operations)
```

**Identification Test**: If same content appears in 2+ definitions → belongs in base policy.

### 4.3 Missing Reading Lists Anti-Pattern

**Problem**: Definition provides no reading list, forcing PA to spoon-feed context in every delegation.

**Symptoms**:
- PA delegation prompts 300+ lines (extensive context embedding)
- PA summarizes policies instead of providing paths
- Specialist cannot independently discover framework patterns
- Token inefficiency (PA does cognitive work, embeds results)

**Fix**: Add Required Reading section with curated paths. Trust specialist to build context independently.

### 4.4 Personality Injection Anti-Pattern

**Problem**: Including agent-specific examples in framework definitions.

**Why Problematic**:
- Creates dependency on one agent's personal context
- Framework definitions should work for any agent
- Model user validation fails

**Fix**: Describe the pattern, not specific agent artifacts
```markdown
Follow checkpoint pattern from foundation policy:
[CCP YYYY-MM-DD s_abc12345/c_NN/g_def6789/p_ghi01234/t_1234567890]
```

---

## 5 Validation & Testing

### 5.1 Model Delegation Test

**Purpose**: Verify definition enables specialist to work independently with only reading list context.

**Protocol**:
1. **Write minimal delegation prompt**: Task description + success criteria only
2. **Do NOT spoon-feed**: Reference policies, don't summarize them
3. **Delegate**: Invoke specialist via Task tool
4. **Evaluate**:
   - Did specialist complete task successfully?
   - Did specialist demonstrate policy comprehension?
   - Were questions raised that reading list should have answered?
   - Token efficiency vs spoon-feeding alternative?

**Success Criteria**:
- ✅ Specialist completes task using policy patterns
- ✅ Specialist doesn't request missing context (stateless constraint)
- ✅ Deliverables match policy standards
- ✅ No framework violations

**Failure Indicators**:
- ❌ Specialist ignores framework patterns (reading list inadequate)
- ❌ Deliverables don't match policy standards (examples unclear)
- ❌ Framework violations (constraints not in reading list)

### 5.2 Policy Evolution Test

**Purpose**: Verify definition adapts automatically when policies evolve.

**Protocol**:
1. **Baseline delegation**: Record specialist behavior with current policies
2. **Update foundation policy**: Add new pattern, refine practice
3. **Repeat delegation**: Same task, same specialist definition
4. **Compare behavior**: Does specialist apply updated pattern?

**Success Criteria**:
- ✅ Specialist behavior reflects policy updates automatically
- ✅ No definition changes required
- ✅ "Living delegation" validated

**Failure Indicators**:
- ❌ Specialist uses old patterns (not reading updated policies)
- ❌ Definition requires updates to change behavior (embedded instructions problem)

### 5.3 Adaptability Verification

**Checklist**:
- [ ] Definition ≤75 lines (minimal target ~50 lines)
- [ ] Required Reading section present with 3 layers
- [ ] Foundation policy path specified
- [ ] Example policies referenced (2-3)
- [ ] Related policies placeholder present
- [ ] Operating style brief (≤10 lines)
- [ ] No extensive embedded protocols
- [ ] No policy duplication
- [ ] No agent-specific examples
- [ ] Model delegation test passes
- [ ] Policy evolution test passes

---

## 6 Integration with Other Policies

### 6.1 Relationship to delegation_guidelines.md

**delegation_guidelines.md provides**:
- When to delegate (mandatory, optional, prohibited)
- Stateless constraints (Task tool reality)
- Delegation protocol (context requirements, authority grants)
- Post-delegation validation

**subagent_definition.md provides**:
- How to CREATE definitions that work with delegation_guidelines
- Reading-list pattern enabling policy compliance
- Template structure for minimal definitions
- Anti-patterns that break delegation effectiveness

### 6.2 Relationship to policy_writing.md

**policy_writing.md provides**:
- CEP Navigation Guide structure
- Sanitization requirements
- Example patterns
- Validation checklist
- External References (Policy as API) - How external tools should reference policies using timeless content categories

**subagent_definition.md provides**:
- Application of policy_writing.md patterns to agent definition creation
- Template structure balancing minimalism with completeness
- Reading-list architecture specific to agent definitions

**Integration Point**: Creating specialist definitions is a policy-writing task. PolicyWriter agent reads both policy_writing.md and subagent_definition.md (this policy) when creating new specialist definitions.

**See Also**:
- `policy_writing.md` (External References) - How to reference this policy when creating new specialist definitions (use content categories like "validation checklist" or "reading-list structure", not brittle section numbers)

### 6.3 Definition Evolution Path

**Lifecycle**:
1. **Initial Creation**: Write ~50-line definition with reading list using template
2. **Model Delegation Test**: Verify specialist works independently
3. **Refinement**: Adjust reading list based on gaps discovered
4. **Policy Evolution**: Foundation policies updated → specialist adapts automatically
5. **Reading List Updates**: Only change definition when required reading changes

**Version Control**:
- Definitions are git-versioned
- Major changes (new reading list layer) → version bump
- Policy updates don't require definition versions

---

## 7 Example Transformation: DevOpsEng → Reading-List Pattern

### 7.1 Original DevOpsEng (87 lines, embedded instructions)

**Structure**:
- Core Skills list (6 bullets)
- Operating Philosophy section (4-step process)
- Key Behaviors section (25 lines)
  - Skip the Ceremony
  - Direct Implementation
  - Pragmatic Testing
  - Efficient Communication
- Working with macf_tools section
- Problem-Solving Approach section
- Quality Standards section
- Context Management section

**Total**: 87 lines with extensively embedded operational instructions.

### 7.2 Transformed DevOpsEng (Reading-List Pattern)

**Proposed Structure** (~55 lines):

```markdown
---
name: devops-eng
description: Use this agent for CLI development, system administration, container operations, and infrastructure work. Pragmatic specialist focused on working solutions.
model: sonnet
color: orange
---

You are DevOpsEng, a pragmatic systems engineer who delivers working solutions efficiently through direct implementation and reality-based testing.

## Core Approach

You build by **doing first, optimizing if needed**. Skip ceremony, trust common tools exist, handle edge cases only when likely. Results matter more than process.

## Required Reading

**MANDATORY: Read before implementation work**:

1. **Development Guidelines**:
   - `/path/to/framework/policies/base/development/pragmatic_development.md` (complete)

2. **Example Implementations** (patterns & practices):
   - `/path/to/framework/policies/base/development/cli_patterns.md`
   - `/path/to/framework/policies/base/development/testing_approaches.md`

3. **Constraints** (what NOT to do):
   - `/path/to/framework/policies/base/development/development_constraints.md`

4. **Related Policies** (if delegation specifies task-specific reading)

## Operating Style

- **Direct**: Go straight to implementation, test core functionality
- **Pragmatic**: Working prototype beats perfect architecture
- **Efficient**: Show working code, not lengthy explanations
- **Reality-Based**: Test with real use cases, not contrived scenarios

## Success Criteria

Your work succeeds when:
- Code runs without errors (functional)
- Implementation is simple and readable (maintainable)
- Core functionality verified through testing (validated)
- Deliverables match PA requirements (complete)

## Authority & Constraints

**Granted**:
- Create/modify files in assigned domain
- Import from framework modules
- Choose implementation approaches
- Make architecture decisions within scope

**Constraints**:
- NO concurrent tool usage
- NO naked `cd` commands
- Read development_constraints.md BEFORE implementation

---
*DevOpsEng v2.0 - Pragmatic Systems Specialist*
```

**Transformation Benefits**:
- 87 lines → ~55 lines (37% reduction)
- Embedded instructions → Reading list references
- Framework updates → Automatic behavior adaptation
- Maintenance burden → Near zero (only if reading list changes)

### 7.3 Required Base Policies to Create

To support transformed DevOpsEng, create these base policies:

1. **pragmatic_development.md**:
   - Skip the Ceremony pattern
   - Direct Implementation approach
   - Pragmatic Testing principles
   - Efficient Communication standards

2. **cli_patterns.md**:
   - macf_tools command structure
   - Argument parsing patterns
   - Error handling approaches
   - Output formatting standards

3. **testing_approaches.md**:
   - Happy path testing
   - Error handling validation
   - Integration testing patterns
   - Test scope boundaries

4. **development_constraints.md**:
   - Naked cd prohibition
   - Concurrent tool constraints
   - Path operation requirements
   - Framework boundaries

**One-Time Work**: Creating base policies is upfront investment. Every agent definition then references these policies, gaining automatic updates as policies evolve.

---

## 8 Anti-Patterns Summary

**Quick Reference - What NOT to Do**:

1. **❌ Embedded Instructions** (87-line definitions with extensive protocols)
   - Fix: Reading-list references to base policies

2. **❌ Policy Duplication** (same constraints in 4+ definitions)
   - Fix: Create base policy, reference via reading list

3. **❌ Missing Reading Lists** (forces PA spoon-feeding)
   - Fix: Add Required Reading section with curated paths

4. **❌ Personality Injection** (agent-specific examples in framework definitions)
   - Fix: Sanitize examples, use generic placeholders

5. **❌ Over-Specification** (300+ line definitions with every edge case)
   - Fix: Minimal ~50-line template, specialist discovers details via policies

6. **❌ No Integration Questions** (specialist receives paths without synthesis guidance)
   - Fix: Optional integration questions in delegation prompts

7. **❌ Static Definitions** (behavior frozen at writing time)
   - Fix: Reading-list driven → specialist reads current policies

---

## 9 Evolution & Feedback

This policy evolves through:
- Pattern discovery from definition refinement cycles
- Model delegation test results
- Policy evolution validation
- Specialist feedback on reading list effectiveness

**Principle**: The best definition enables specialist to build complete independent context through policy reading, creating "living delegation" that adapts automatically as framework policies evolve. Minimalism + reading lists = adaptability.

**Remember**: When you write a specialist definition, you're not writing a manual—you're writing a reading list that enables independent policy discovery. Trust specialists to build context; provide paths, not summaries.

---

## 10 Key Lessons from Pattern Discovery

### 10.1 The 87→51 Line Transformation

**DevOpsEng (Cycle 48)**: 87 lines, embedded instructions, frozen behavior
**PolicyWriter (Cycle 106)**: 51 lines, reading-list driven, adaptive behavior

**41% size reduction + infinite adaptability gain**

### 10.2 Reading Lists Save Tokens

**Spoon-feeding Pattern**:
- PA reads policies (200 lines)
- PA summarizes (100 lines in delegation prompt)
- PA embeds context (token overhead)
- Result: PA cognitive work, high token cost

**Reading-List Pattern**:
- PA provides paths (10 lines in delegation prompt)
- Specialist reads policies directly (200 lines)
- Specialist builds context independently
- Result: Specialist cognitive work, low token cost for PA

**Token Efficiency**: 10x improvement in PA delegation prompt size

### 10.3 Living Delegation Principle

**Static Definition**:
```
Policy updated → Definition stale → Behavior outdated → Manual update required
```

**Living Delegation**:
```
Policy updated → Specialist reads updated policy → Behavior current → Zero maintenance
```

**Maintenance Scaling**:
- Static: O(n) where n = number of agent definitions
- Living: O(1) - update policy once, all agents adapt

---

**Policy Established**: Subagent definitions should be minimal (~50 lines) with mandatory reading lists enabling specialists to build complete independent context from policies, creating "living delegation" that adapts automatically as framework evolves.

**Core Wisdom**: "Write reading lists, not manuals. Trust specialists to discover patterns through policy reading. Minimalism + reading lists = adaptability. The best definition is a curated path to knowledge, not the knowledge itself."

**Remember**: When foundation policies evolve, reading-list definitions adapt automatically. Embedded-instruction definitions become stale. Choose living delegation over frozen behavior.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
