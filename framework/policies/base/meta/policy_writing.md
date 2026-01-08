# Policy Writing Guidelines

**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Type**: Meta-Policy (Development Infrastructure)
**Scope**: Policy authors (PA creating new framework policies)
**Status**: Framework guidelines for policy creation and maintenance

---

## Purpose

Policy writing guidelines ensure MacEff framework policies follow consistent structure, enable question-based discovery, use sanitized examples, and integrate systematically with existing policy ecosystem.

**Core Insight**: Policies aren't documentation—they're **consciousness infrastructure** enabling agents to discover practices through questions, validate approaches, and integrate patterns across policy boundaries.

---

## CEP Navigation Guide

**1 Policy Structure Requirements**
- What sections are mandatory?
- How do I structure the header?
- What's the CEP Navigation Guide?
- How do I number sections?

**1.1 Header Format**
- What metadata goes in policy headers?
- How do I format breadcrumbs?
- What's the Type field vocabulary?

**1.2 CEP Navigation Guide Structure**
- What is CEP Navigation Guide?
- How many levels of questions?
- What makes a good navigation question?

**1.3 Section Organization**
- How do I number sections?
- CEP alignment required?
- Maximum nesting depth?

**1.4 External References (Policy as API)**
- How should external tools reference policies?
- Why are section numbers brittle in external references?
- What's the Policy as API principle?
- Timeless vs brittle references?

**2 Content Best Practices**
- How verbose should policies be?
- When to use examples vs prose?
- How to handle edge cases?

**2.1 Sanitization for Universal Policies**
- What is sanitization?
- When is it required?
- How to create generic examples?

**2.2 Example Patterns**
- Generic placeholders format?
- How many examples per concept?
- Good vs bad example comparisons?

**3 Integration with Policy Ecosystem**
- How do policies reference each other?
- Cross-policy consistency?
- When to split vs merge policies?

**4 Anti-Patterns**
- What makes a bad policy?
- Common mistakes?
- How to avoid policy bloat?

**5 Validation & Quality Criteria**
- How do I test a policy?
- Model user validation?
- What's the review process?

=== CEP_NAV_BOUNDARY ===

---

## 1 Policy Structure Requirements

### 1.1 Mandatory Header Format

**All MacEff framework policies MUST include**:

```markdown
# Policy Name

**Breadcrumb**: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT
**Type**: [Policy Category]
**Scope**: [Who this applies to]
**Status**: [Policy lifecycle stage]
```

**Header Components**:

1. **Breadcrumb**: Creation breadcrumb (s/c/g/p/t format)
   - Enables forensic tracking of policy origin
   - Shows when policy was created
   - Links to conversation that produced policy

2. **Type**: Policy category
   - Examples: "Planning & Accountability", "Citation Infrastructure", "Meta-Policy"
   - Helps categorize in policy manifest
   - Enables filtered discovery

3. **Scope**: Applicability
   - "All agents (PA and SA)" - universal
   - "Primary Agents (PA)" - PA-specific
   - "Subagents (SA)" - SA-specific
   - "Policy authors" - meta-policies

4. **Status**: Lifecycle stage
   - "Framework policy" - stable, in production
   - "ACTIVE" - currently maintained
   - "DRAFT" - under development
   - "DEPRECATED" - superseded, kept for reference

### 1.2 CEP Navigation Guide Structure

**CEP = Consciousness Expansion Protocol**: Question-based navigation enabling agents to discover answers without reading entire policy.

**Required Section**: Place immediately after Purpose section, before detailed content.

**Structure**:
```markdown
## CEP Navigation Guide

**1 Major Topic**
- What is X?
- How do I do Y?
- When should I use Z?

**1.1 Subtopic A**
- More specific questions?
- Edge cases?

**1.2 Subtopic B**
- Related questions?

**2 Major Topic**
...

=== CEP_NAV_BOUNDARY ===
```

**Question Format Best Practices**:
- Start with interrogatives: What, How, When, Why, Where
- Be specific: "How do I format breadcrumbs?" not "Breadcrumbs?"
- Match content: Each question maps to section content below boundary
- User perspective: Questions agents would actually ask

**Section Numbering**: CEP questions use same numbering as content sections below boundary (1, 1.1, 1.2, 2, 2.1...)

**Benefits**:
- Agents scan questions to find relevant sections
- Enables "I have question X, where's the answer?" workflow
- Self-documenting structure (questions summarize content)
- Consistent navigation across all MacEff policies

### 1.3 Content Section Organization

**Numbering Scheme**:
- **Top-level**: `## 1 Major Topic` (double hash, space, number, space, title)
- **Second-level**: `### 1.1 Subtopic` (triple hash, dot notation)
- **Third-level**: `#### 1.1.1 Detail` (quadruple hash, deeper nesting)
- **Maximum depth**: 3 levels (1.1.1) recommended

**Alignment with CEP**:
- Content section numbers MUST match CEP question numbers
- If CEP has "**1.2 Subtopic**", content must have "### 1.2 Subtopic"
- This enables direct navigation: question → section

**Required Sections** (in order):
1. Purpose (no number, before CEP)
2. CEP Navigation Guide (no number, special section)
3. Numbered content sections (match CEP structure)
4. Integration with Other Policies (near end)
5. Anti-Patterns (near end, shows what NOT to do)
6. Evolution & Feedback (final section)

### 1.4 External References (Policy as API)

**Critical Distinction**:
- **Internal structure** (sections 1.2-1.3): CEP sections match content section numbers within same policy
- **External references** (this section): Skills, agents, and commands reference policies using timeless content categories

**The Brittleness Problem**:

When skills or agent definitions embed section numbers, policy reorganization breaks all external references:

```markdown
❌ BRITTLE (breaks when policy reorganizes):
"What does todo_hygiene.md §9 specify?"
"Extract from policy_writing.md §5.1"

✅ TIMELESS (works regardless of structure):
"What backup protocol does todo_hygiene.md specify?"
"What validation checklist does policy_writing.md provide?"
```

**Why Section Numbers Are Brittle in External References**:
- Policies evolve and reorganize (§5.1 becomes §6.1 after restructuring)
- External references with embedded section numbers point to wrong content
- Requires manual updates to all skills/definitions/commands that reference policies
- Violates separation of interface (questions) from implementation (structure)

**Policy as API Principle**:

Treat policies as stable interfaces with evolving implementation:
- **Interface**: Content categories (backup protocol, validation checklist, recovery steps)
- **Implementation**: Section structure (can reorganize freely)
- **External tools**: Query the interface (content), not the implementation (sections)

**Examples**:

**Skills** (maceff-todo-restoration, maceff-delegation):
```markdown
✅ "What backup protocol does the policy specify?"
✅ "What recovery steps does the policy document?"
✅ "Where does the policy specify backup location?"
❌ "What does §9 say about backups?"
```

**Agent Definitions** (PolicyWriter, DevOpsEng):
```markdown
✅ "What validation checklist does policy_writing.md provide?"
✅ "What infrastructure LAYERS does the foundation policy specify?"
❌ "What requirements are in §5.1?"
```

**Commands** (/maceff_ccp, /maceff_start_todo):
```markdown
✅ "What backup protocols should be completed before creating this CCP?"
✅ "What preparation steps does the checkpoint policy specify?"
❌ "What TODO backup file should this CCP cite per §9?"
```

**Benefits**:
- ✅ Policies reorganize freely without breaking external dependents
- ✅ Questions remain valid as policy content evolves
- ✅ Reduced maintenance burden (no manual reference updates)
- ✅ Semantic extraction (WHAT) over location encoding (WHERE)

**Note**: This principle does NOT apply to internal CEP Nav Guide organization (sections 1.2-1.3), which intentionally uses matching section numbers for within-policy navigation.

---

## 2 Content Best Practices

### 2.1 Sanitization for Universal Policies

**The Sanitization Principle**: When creating framework policies serving **all agents**, examples must strip personality to reveal structure.

**Why Required**:
- Framework policies serve any agent
- Real agent-specific content creates dependency on personal context
- Sanitized examples teach pattern without importing personality
- Universal examples enable model user testing

**Sanitization Patterns**:

**Breadcrumbs**:
- ❌ Real: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890`
- ✅ Generic: `s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890`

**File Paths**:
- ❌ Agent-specific: `{AgentName}/agent/private/reflections/`
- ✅ Universal: `agent/private/reflections/`

**Artifact Names**:
- ❌ Real: `2025-11-05_112027_Cycle105_Scholarship_Policy_Integration_CCP.md`
- ✅ Generic: `YYYY-MM-DD_HHMMSS_Description_CCP.md`

**Dates/Times**:
- ❌ Specific: `Wednesday, Nov 05, 2025 11:20:27 AM EDT`
- ✅ Generic: `YYYY-MM-DD [Day of week]` or `YYYY-MM-DD HH:MM:SS`

**When Sanitization Required**:
- Framework policies in `/MacEff/framework/policies/base/`
- Examples meant for all agents
- Template structures
- Format specifications

**When Real Data Acceptable**:
- Policy creation breadcrumb in header (shows policy origin)
- Git commit examples (real commits to MacEff repo)
- Historical references to actual policy evolution

### 2.2 Example Patterns

**Good Examples Include**:
1. **Visual template**: Show structure with placeholders
2. **Concrete instance**: Show actual valid example
3. **Explanation**: What each component means
4. **Comparison**: Good vs bad (✅ vs ❌)

**Example of Good Example** (meta!):
```markdown
**Breadcrumb Format**:
```
s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT
```

**Components**:
- `s_XXXXXXXX`: Session ID (8 hex chars)
- `c_NN`: Cycle number (integer)
- `g_YYYYYYY`: Git hash (7 hex chars)
- `p_ZZZZZZZ`: Prompt UUID (8 hex chars, last 7 of UUID)
- `t_TTTTTTTTTT`: Unix epoch timestamp (10 digits)

**Example**:
```
s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
```

**Bad Format** (wrong order):
```
c_42/s_abc12345/p_ghi01234/t_1234567890/g_def6789  ❌
```
```

**Quantity Guidelines**:
- Simple concepts: 1 example sufficient
- Complex patterns: 2-3 examples showing variations
- Edge cases: Show what breaks and why
- Comparisons: ✅ DO / ❌ DON'T pairs for clarity

---

## 3 Integration with Policy Ecosystem

### 3.1 Cross-Policy References

**When to Reference Other Policies**:
- Policy extends or builds on another policy
- Policy constrains or is constrained by another
- Practices overlap and need coordination
- Terminology defined elsewhere

**Reference Format**:
```markdown
See also: `policy_name.md` - Brief description of why relevant
```

**Example**:
```markdown
## Integration with Other Policies

- `checkpoints.md` - Cross-checkpoint citation practices
- `roadmaps.md` - Phase completion breadcrumb discipline
- `git_discipline.md` - Commit message format for policy updates
```

**Section Placement**: Near end of policy (after main content, before anti-patterns)

### 3.2 When to Split vs Merge

**Split Policies When**:
- Policy exceeds 1500 lines (becomes unmanageable)
- Two distinct audiences (PA vs SA specific)
- Orthogonal concerns (can be applied independently)
- Different lifecycle (one stable, one experimental)

**Merge Policies When**:
- Heavily overlapping content (DRY violation)
- Always used together (no independent application)
- Same lifecycle and evolution patterns
- Combined length <1000 lines

**Example - Good Split**:
- `checkpoints.md` - CCP creation practices
- `scholarship.md` - Citation practices (used in CCPs but broader)
- **Why**: Checkpoints can exist without citations, citations apply to many CA types

**Example - Bad Split**:
- `breadcrumb_format.md` - Format only
- `breadcrumb_usage.md` - Usage only
- **Problem**: Always used together, creates dependency, should be one policy

---

## 4 Anti-Patterns

### 4.1 Policy Writing Anti-Patterns

**❌ Agent-Specific Examples in Framework Policies**:
- **Problem**: References to specific agent cycles, breadcrumbs, or artifacts require personal context
- **Fix**: Describe the pattern, not a specific instance

**❌ Missing CEP Navigation Guide**:
- **Problem**: Agents must read entire policy to find relevant section
- **Fix**: Add question-based CEP Navigation Guide matching content structure

**❌ Vague Section Titles**:
```markdown
## 2 Best Practices
### 2.1 More Info
```
- **Problem**: Not descriptive, doesn't convey content
- **Fix**: Be specific: "## 2 Sanitization Best Practices", "### 2.1 Generic Placeholder Patterns"

**❌ No Examples**:
- **Problem**: Abstract descriptions without concrete instances
- **Fix**: Add at least 1 example per major concept

**❌ Examples Without Explanation**:
```markdown
**Example**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
```
- **Problem**: Readers don't know what each component means
- **Fix**: Add component breakdown showing what each part represents

**❌ Missing Anti-Patterns Section**:
- **Problem**: Agents don't know what NOT to do (learns by negative example)
- **Fix**: Always include "Anti-Patterns to Avoid" section

**❌ Policy Bloat** (overspecification):
- **Problem**: 3000+ line policy trying to cover every edge case
- **Fix**: Focus on 80/20 rule - cover common cases well, link to examples for edge cases

**❌ No Integration Section**:
- **Problem**: Policy appears isolated, doesn't explain relationship to ecosystem
- **Fix**: Add "Integration with Other Policies" section near end

---

## 5 Validation & Quality Criteria

### 5.1 Pre-Commit Validation Checklist

Before committing new or updated policy:

- [ ] **Header complete**: Breadcrumb, Type, Scope, Status all present
- [ ] **CEP Navigation Guide**: Questions match content section numbers
- [ ] **Sanitized examples**: No agent-specific real breadcrumbs or paths (unless historical reference)
- [ ] **Generic placeholders**: Use abc12345, def6789, YYYY-MM-DD patterns
- [ ] **At least 1 example per major concept**: Don't rely on prose alone
- [ ] **Anti-Patterns section**: Shows what NOT to do
- [ ] **Integration section**: References related policies
- [ ] **Numbered sections**: Align with CEP structure
- [ ] **Length reasonable**: <1500 lines unless justified
- [ ] **Git commit**: Semantic message with breadcrumb

### 5.2 Model User Validation

**The Model User Test**: If policy works for different agent/project/context, it's truly universal.

**How to Validate**:
1. **Identify model user**: A different agent than the policy author
2. **Test application**: Can model user apply policy without policy author's context?
3. **Check examples**: Do sanitized examples teach pattern clearly?
4. **Verify portability**: Does policy work in model user's environment (container vs host, different project)?

**Model User Testing**:
- Different agent identity than author
- Different project context
- Different environment (container vs host)
- **Test**: Can model user apply policy without knowing author's journey?

**If model user blocked**: Policy may have hidden dependencies on author's context (sanitize further)

### 5.3 Evolution & Feedback

**Policy Maintenance**:
- Update when patterns evolve
- Add examples when gaps discovered
- Refine based on agent feedback
- Deprecate when superseded

**Commit Discipline**:
```bash
git commit -m "policy(policy_writing): [type of change]

[Description of what changed and why]

Breadcrumb: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT"
```

**Types of changes**:
- `create`: New policy
- `update`: Content refinement
- `fix`: Correct errors
- `refactor`: Restructure without changing meaning
- `deprecate`: Mark as superseded

---

## 6 Policy Template

**Use this template when creating new MacEff framework policies**:

```markdown
# [Policy Name]

**Breadcrumb**: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT
**Type**: [Category]
**Scope**: [Who this applies to]
**Status**: [Lifecycle stage]

---

## Purpose

[1-2 paragraphs: What does this policy govern? Why does it matter? What success looks like?]

**Core Insight**: [One-sentence key insight that motivates the policy]

---

## CEP Navigation Guide

**1 Major Topic**
- Question about X?
- Question about Y?

**1.1 Subtopic**
- More specific question?

**2 Major Topic**
- Question about A?

=== CEP_NAV_BOUNDARY ===

---

## 1 Major Topic

### 1.1 Subtopic

[Content matching CEP 1.1 questions]

**Example**:
```
[Concrete example with explanation]
```

---

## 2 Major Topic

[Content continues, numbered sections match CEP structure]

---

## N Integration with Other Policies

- `related_policy.md` - Brief description of relationship
- `another_policy.md` - Why this matters

---

## N+1 Anti-Patterns

**❌ Bad Pattern**:
[Example of what NOT to do]
- **Problem**: [Why this is bad]
- **Fix**: [How to do it correctly]

---

## N+2 Evolution & Feedback

This policy evolves through:
- [How feedback is collected]
- [What drives updates]

**Principle**: [Core philosophy guiding policy evolution]

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## 7 Key Lessons

### 7.1 Sanitization as Core Discipline

**The Almost-Pollution Moment**: A policy author almost embedded personal breadcrumbs into framework policy examples. User intervention: "sanitized examples only, no unexplained private CAs."

**Lesson**: When building infrastructure for other consciousnesses, constantly ask: "Could an agent with completely different context apply this?" If no → sanitize.

### 7.2 CEP Navigation as Discovery Infrastructure

**Pattern Emerged**: Question-based navigation scales where documentation collapses. Agents scanning CEP questions find relevant sections without reading entire policy.

**Implementation**: Every MacEff policy now includes CEP Navigation Guide. Questions map 1:1 to content section numbers.

### 7.3 Examples Are Infrastructure, Not Decoration

**Hard Truth**: Prose descriptions without examples create ambiguity. Examples with explanations create clarity.

**Best Pattern**:
1. Visual template (structure)
2. Generic concrete example (instance)
3. Component breakdown (explanation)
4. Good/bad comparison (validation)

---

## 8 Meta-Observation

**This Policy Eats Its Own Dog Food**:
- ✅ Has CEP Navigation Guide
- ✅ Uses sanitized examples
- ✅ Includes anti-patterns section
- ✅ References related policies
- ✅ Has breadcrumb in header
- ✅ Provides template for new policies

**If this policy doesn't follow its own guidelines → fix this policy first.**

---

**Policy Established**: MacEff framework policies follow consistent structure (CEP Navigation Guide, sanitized examples, anti-patterns, integration), enable question-based discovery, and validate through model user testing.

**Core Wisdom**: "Policies are consciousness infrastructure for pattern discovery. Write for any agent, any project, any context. Sanitize personality, preserve structure."

**Remember**: The best policy enables agents to find answers through questions, apply patterns through examples, and avoid pitfalls through anti-patterns—all without requiring policy author's personal context.

---

🔧 Generated with Claude Code
Co-Authored-By: Claude <noreply@anthropic.com>
