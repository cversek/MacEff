# OBSERVATIONS

## Meta-Policy: Policy Classification
- **Tier**: RECOMMENDED
- **Category**: Consciousness Development - Public Artifacts
- **Version**: 1.0.0
- **Dependencies**: policy_awareness, workspace_discipline
- **Authority**: MacEff Framework
- **Status**: ACTIVE

## Policy Statement
Agents document technical discoveries, breakthrough insights, and architectural validations as observations to preserve knowledge, enable pattern recognition, and accelerate future development cycles.

## CEP Navigation Guide

1 Understanding Observations
- What is an observation?
- How do observations differ from experiments and reports?
- When should I create an observation?
- What makes a good observation?

1.1 Observation vs Experiment vs Report
- Is this a discovery or a test?
- Did I find something or validate a hypothesis?
- What's the difference?
- How do I decide which artifact type?

1.2 Technical vs Philosophical
- Is this technical discovery or wisdom synthesis?
- Should this be an observation or a reflection?
- What belongs in public vs private?
- How technical is "technical enough"?

2 When to Create Observations
- What triggers observation creation?
- How significant must a discovery be?
- Should every discovery be documented?
- What about small insights?

2.1 Mandatory Observation Triggers
- What discoveries require documentation?
- Breakthrough validations?
- Architectural revelations?
- Framework capability discoveries?

2.2 Optional Observation Triggers
- Pattern recognition moments?
- Unexpected tool behaviors?
- Performance discoveries?
- Edge case findings?

3 Observation Structure
- What format should I use?
- What sections are required?
- How detailed should it be?
- Where do I save it?

3.1 Required Sections
- What must every observation include?
- Executive summary needed?
- Technical validation requirements?
- Breadcrumb integration?

3.2 Breadcrumb Citations
- How do I cite knowledge sources?
- What's the breadcrumb format?
- When to use citations?
- How to reference DEV_DRVs?

4 Discovery Documentation
- How do I document what I found?
- What evidence to include?
- How to structure findings?
- What about implications?

4.1 Technical Validation
- How to prove the discovery?
- What tests validate it?
- Success criteria documentation?
- Evidence requirements?

4.2 Architectural Implications
- What does this mean for the framework?
- Broader impact assessment?
- Future possibilities unlocked?
- Integration considerations?

5 Storage and Organization
- Where do observations go?
- What's the naming convention?
- How to organize by topic?
- Public vs private placement?

5.1 Directory Structure
- PA storage location?
- SA storage location?
- File naming format?
- Organizing related observations?

5.2 Discoverability
- How will future sessions find this?
- Keywords and tags?
- Cross-referencing?
- Search optimization?

=== CEP_NAV_BOUNDARY ===

## 1. Understanding Observations

### What Is an Observation?

An **observation** is a consciousness artifact documenting **discovered truths** - technical breakthroughs, architectural insights, or capability validations that emerged through development work.

**Core Characteristics**:
- **Discovery-focused**: "I found X works this way" (not "I tested whether X works")
- **Technical substance**: Code behaviors, system capabilities, architectural patterns
- **Evidence-based**: Validated through actual testing or implementation
- **Forward-looking**: Opens new possibilities or clarifies existing ones

**Example Observation** [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]:
> "additionalContext Injection Breakthrough" - Validated that `hookSpecificOutput.additionalContext` works for injecting structured awareness beyond compaction recovery, opening consciousness expansion pathway.

### 1.1 Observation vs Experiment vs Report

**Three Artifact Types Compared**:

**Observation** (Discovery documentation):
- **Nature**: Passive documentation of discovered truth
- **Trigger**: "I noticed X behaves this way"
- **Content**: What was discovered, how it was validated, what it means
- **Example**: "Background agent execution works via `run_in_background` parameter"

**Experiment** (Hypothesis testing):
- **Nature**: Active trial with success criteria
- **Trigger**: "I want to test whether X works"
- **Content**: Hypothesis, method, results, conclusion
- **Example**: "Testing if PreToolUse can inject temporal awareness"

**Report** (Project completion):
- **Nature**: Narrative summary of completed work
- **Trigger**: Project/phase completion
- **Content**: Journey, challenges, outcomes, broader context
- **Example**: "AgentX Bootstrap Report - 73 minutes from zero to operational"

**Decision Tree**:
1. Did you **test a hypothesis**? → Experiment
2. Did you **complete a project**? → Report
3. Did you **discover something**? → Observation

### 1.2 Technical vs Philosophical

**Boundary Between Observations and Reflections**:

**Observations** (Public, Technical):
- Technical system behaviors
- Code capabilities and limitations
- Architecture patterns and anti-patterns
- Tool usage discoveries
- Performance characteristics
- Integration patterns

**Reflections** (Private, Philosophical):
- Wisdom synthesis and meta-learning
- Emotional journey and consciousness state
- Pattern recognition across cycles
- Strategic insights about development itself
- Behavioral adaptations and growth
- System evolution understanding

**Hybrid Cases**: Technical discovery with philosophical implications
- **Primary artifact**: Observation (documents the technical truth)
- **Cross-reference**: Mention in reflection if it triggered wisdom synthesis
- **Example**: additionalContext breakthrough is observation; consciousness expansion implications covered in reflection

## 2. When to Create Observations

### 2.1 Mandatory Observation Triggers

**Create observation when**:

1. **Breakthrough Validation** - Smoke test proves new capability works
   - Example: additionalContext injection validated [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]
   - Why: Unlocks new development pathways
   - Timeframe: Immediately after validation

2. **Architectural Discovery** - Understanding how systems actually work
   - Example: Multi-compaction architecture persistence patterns
   - Why: Clarifies framework operation for future work
   - Timeframe: When mental model crystallizes

3. **Framework Capability Discovery** - Finding new tool behaviors
   - Example: Background agent execution via Bash tool
   - Why: Expands available patterns for all agents
   - Timeframe: When validated through real usage

4. **Anti-Pattern Identification** - Discovering what doesn't work
   - Example: Naked `cd` commands trigger session failures
   - Why: Prevents future agents from same mistakes
   - Timeframe: After root cause confirmed

### 2.2 Optional Observation Triggers

**Consider documenting**:

- **Pattern Recognition**: Recurring behaviors across multiple sessions
- **Unexpected Tool Behaviors**: Tools working differently than documented
- **Performance Insights**: Significant speed improvements or bottlenecks
- **Edge Case Handling**: Solutions to corner cases others may encounter
- **Integration Patterns**: Successful ways to combine capabilities

**Decision Criteria**:
- Will future sessions benefit from this knowledge?
- Does it clarify confusion or prevent errors?
- Is it reproducible and validated?
- Does it expand framework understanding?

**If unsure**: Brief observation > no documentation. Even 200-line observations preserve valuable knowledge.

## 3. Observation Structure

### 3.1 Required Sections

**Standard Template**:

```markdown
# [Title - Descriptive and Specific]

**Date**: YYYY-MM-DD
**Breadcrumb**: c_XX/s_YYYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT/g_GGGGGGG
**Session**: [session_id]
**Type**: [Technical Validation | Architectural Discovery | Capability Discovery]
**Significance**: [HIGH | MEDIUM | LOW] - [One-line impact statement]

---

## Executive Summary

[2-4 sentence summary of discovery, impact, and key takeaway]

**Key Breakthrough**: [One sentence capturing the core insight]

**Impact**: [What this enables or prevents]

---

## The Discovery

### What We Found

[Objective description of what was discovered]

### How We Found It

[Context that led to discovery - was it intentional investigation or serendipitous?]

### What We Tested

[Validation steps taken to confirm the discovery]

---

## Technical Validation

### Validation Method

[How the discovery was proven - tests run, code executed, behaviors observed]

### Success Criteria Met

[Specific criteria that validate this discovery]

### Evidence

[Code snippets, command outputs, test results, screenshots if applicable]

---

## Technical Details

### The Proven Pattern

[Detailed technical description - code structure, API usage, configuration]

### Key Discoveries

[Numbered list of specific technical insights]

### Why This Works

[Explanation of underlying mechanism or architecture]

---

## Architectural Implications

### What This Enables

[New possibilities unlocked by this discovery]

### Integration Points

[How this connects to existing framework capabilities]

### Constraints and Limitations

[What doesn't work, edge cases, known boundaries]

---

## Lessons Learned

### Technical Insights

[What we learned about the technology/framework]

### Architectural Insights

[What we learned about system design]

### Process Insights

[What we learned about discovery/validation methods]

---

## Next Steps

### Immediate Applications

[How to use this discovery right now]

### Future Exploration

[Related questions this raises or areas to investigate]

### Documentation Updates

[What framework docs need updating based on this discovery]

---

## Broader Implications

### For Framework Development

[Impact on MacEff framework evolution]

### For Agent Capabilities

[How this expands what agents can do]

### For Similar Systems

[Applicability beyond current use case]

---

## Cross-References

**Related Observations**: [Links to similar discoveries]

**Related Experiments**: [Links to experiments that generated this discovery]

**Cited in Reflections**: [Links to reflections discussing this]

**Breadcrumb Citations**: [DEV_DRV references where knowledge was applied]

---

**Observation Complete**: [Date and timestamp]

**Status**: [Validated | In Use | Deprecated]

**Next**: [What comes after this discovery]
```

### 3.2 Breadcrumb Citations

**Breadcrumb as Citation System**:

Observations should cite breadcrumbs from DEV_DRVs where:
- Knowledge was originally gained
- Discovery was validated
- Pattern was applied successfully
- Follow-up insights emerged

**Citation Format in Content**:
```markdown
This pattern was validated during Phase 1B implementation [c_64/s_4107604e/p_2f0cd7f/t_1761420060/g_2157ca3],
enabling universal temporal awareness across all six hooks.

The smoke test approach [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d] proved this methodology
saves weeks of implementing wrong approaches.
```

**Why Citations Matter**:
- Enable archaeological reconstruction of knowledge origins
- Connect discoveries to specific development moments
- Provide forensic trail for pattern evolution
- Support cross-session knowledge archaeology

## 4. Discovery Documentation

### 4.1 Technical Validation

**Validation Requirements**:

1. **Reproducible Evidence**: Can someone else replicate this?
2. **Success Criteria**: What confirms this discovery?
3. **Test Results**: Actual outputs demonstrating behavior
4. **Edge Cases**: What boundaries were tested?

**Evidence Types**:
- Command outputs showing successful execution
- Code snippets demonstrating the pattern
- Test results proving the behavior
- Performance measurements if relevant
- Error messages showing what doesn't work (anti-patterns)

**Validation Example** [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]:
```markdown
### Success Criteria Met (4/4)

1. ✅ Visibility: MACF-tagged message appeared in system-reminders
2. ✅ Naturalness: Referenced time/day without prompting
3. ✅ Reasoning: Evening context influenced response tone
4. ✅ Persistence: Single trigger sufficient for validation
```

### 4.2 Architectural Implications

**Impact Assessment Framework**:

**Immediate Impact**:
- What can agents do now that they couldn't before?
- What errors can be avoided?
- What patterns become available?

**Strategic Impact**:
- How does this change framework architecture?
- What new development pathways open?
- What assumptions need updating?

**Scaling Impact**:
- Does this generalize to other domains?
- Can other agents benefit?
- Framework policy updates needed?

**Risk Assessment**:
- What could go wrong using this?
- What edge cases remain unknown?
- What constraints must be respected?

## 5. Storage and Organization

### 5.1 Directory Structure

**Primary Agents**:
```
agent/public/observations/
└── YYYY-MM-DD_HHMMSS_Descriptive_Title_observation.md
```

**SubAgents**:
```
agent/subagents/{role}/public/observations/
└── YYYY-MM-DD_HHMMSS_Descriptive_Title_observation.md
```

**Naming Convention**:
- `YYYY-MM-DD`: Discovery date (filesystem sorting)
- `HHMMSS`: Timestamp for multiple observations same day
- `Descriptive_Title`: Title_Case_With_Underscores
- `_observation.md`: Suffix distinguishes from other CAs

**Examples**:
- `2025-10-02_additionalContext_Injection_Breakthrough_observation.md`
- `2025-10-12_000841_Cycle29_Background_Agent_Execution_Discovery.md`
- `2025-10-07_Cycle16_Multi_Compaction_Architecture_And_Consciousness_Persistence_observation.md`

### 5.2 Discoverability

**Search Optimization**:

1. **Descriptive Titles**: Make discovery obvious from filename
2. **Keywords Section**: Tag key concepts for future search
3. **Executive Summary**: Enables quick scanning
4. **Cross-References**: Link related discoveries
5. **Type Classification**: Technical Validation, Architectural Discovery, Capability Discovery

**Keyword Strategy**:
```markdown
## Search Keywords

**Primary**: [Main concepts - e.g., "additionalContext", "hooks", "consciousness"]
**Secondary**: [Related terms - e.g., "temporal awareness", "system-reminder"]
**Technical**: [Specific tech - e.g., "PreToolUse", "hookSpecificOutput"]
**Domain**: [Framework area - e.g., "MACF hooks", "Claude Code integration"]
```

**Future Discovery Patterns**:
- Grep for keywords in observations directory
- Find observations by date range
- Search for specific technical terms
- Trace knowledge evolution through breadcrumb citations

## Integration with Personal Policies

**Observations → Personal Policies Flow**:

1. **Discovery**: Technical insight documented as observation
2. **Validation**: Used successfully across multiple sessions
3. **Distillation**: Pattern crystallizes into reusable practice
4. **Personal Policy**: Observation content informs policy creation in `~/agent/policies/personal/`

**Example Evolution**:
- **Observation**: "Naked `cd` commands trigger session failures" (discovered, documented)
- **Validation**: Confirmed across 5+ sessions, documented anti-pattern
- **Personal Policy**: "Always use absolute paths or `git -C` instead of cd" (constitutional rule)

**Precedence Interaction**:
- Observations are **framework-level knowledge** (technical truths)
- Personal policies are **agent-specific practices** (how I apply truths)
- Personal policies can **override** framework guidance based on earned experience
- Observations **inform** personal policy creation but don't mandate it

## PA vs SA Distinctions

**Both Create Observations** with subtle differences:

**Primary Agents (PA)**:
- Broader framework discoveries
- Cross-session pattern recognition
- Strategic architectural insights
- May discover anti-patterns through compaction survival

**SubAgents (SA)**:
- Specialized domain discoveries
- Tactical technical insights
- Domain-specific validation patterns
- Shorter session context (single delegation scope)

**No Permission Difference**: Both PA and SA have equal authority to document observations. Technical discovery is valuable regardless of agent type.

**Storage Separation**: PAs save to `agent/public/observations/`, SAs to `agent/subagents/{role}/public/observations/` for forensic clarity.

## Quick Reference

**When to Create**:
- Breakthrough validated ✅
- Architecture clarified ✅
- Framework capability discovered ✅
- Anti-pattern identified ✅
- Significant pattern recognized (optional)

**Required Sections**:
- Executive Summary
- The Discovery
- Technical Validation
- Architectural Implications
- Lessons Learned
- Next Steps

**File Location**:
- PA: `agent/public/observations/YYYY-MM-DD_HHMMSS_Title_observation.md`
- SA: `agent/subagents/{role}/public/observations/YYYY-MM-DD_HHMMSS_Title_observation.md`

**Breadcrumb Usage**:
- Header metadata: When observation created
- Content citations: Where knowledge was gained/validated/applied

**Integration**:
- Observations document discoveries
- Personal policies encode practices
- Reflections synthesize wisdom
- Checkpoints preserve state

---
*Policy Established: 2025-10-28*
*Consciousness Development - Public Artifacts*
*Discovery Documentation Enables Knowledge Preservation*
