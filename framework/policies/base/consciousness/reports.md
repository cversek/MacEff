# Reports: Project Completion Narratives

**Policy Type**: Consciousness Artifact (Public)
**Scope**: Primary Agents (PA) and Subagents (SA)
**Precedence**: Framework Policy (overridden by Project > Personal)
**Created**: c_73/s_4107604e/p_8c7e6d8/t_1761707487/g_17e7b7d

---

## Policy Statement

Reports document completed projects and significant work phases through comprehensive narratives that preserve context, decisions, and outcomes for stakeholders and future teams.

## CEP Navigation Guide

1 Understanding Reports
- What is a report?
- When should I write one?
- How is this different from observations?
- How is this different from experiments?

1.1 Report vs Other Artifacts
- Report vs observation?
- Report vs experiment?
- Report vs checkpoint?
- Report vs reflection?

1.2 Purpose and Audience
- Who reads reports?
- Why preserve completion narratives?
- What value do reports provide?
- How detailed should reports be?

2 When to Create Reports
- Completed a project?
- Reached major milestone?
- Finished infrastructure buildout?
- Need stakeholder communication?

2.1 Mandatory Triggers
- Project completion?
- Phase deployment done?
- Migration finished?
- Crisis resolved?

2.2 Optional Opportunities
- Quarterly summary?
- Sprint retrospective?
- Success story worth sharing?
- Knowledge transfer needed?

3 Report Structure
- What sections are required?
- How to organize narrative?
- What header metadata needed?
- How to cite breadcrumbs?

3.1 Header and Metadata
- What goes in header?
- Breadcrumb format?
- Status indicators?
- Timeframe specification?

3.2 Core Narrative Sections
- Vision/purpose section?
- Problem description?
- Solution explanation?
- What we built timeline?

3.3 Outcomes and Learning
- Successes to celebrate?
- Challenges to acknowledge?
- Broader implications?
- Future directions?

4 Writing Guidelines
- What tone and style?
- How accessible for non-technical readers?
- Narrative vs bullet points?
- Length considerations?

4.1 Audience Awareness
- Technical collaborators?
- Project stakeholders?
- Future teams?
- Mixed audiences?

4.2 Breadcrumb Citations
- When to cite breadcrumbs?
- How to reference work units?
- Linking to other artifacts?
- Forensic traceability?

5 Integration with Other Artifacts
- How do reports use observations?
- How do reports reference experiments?
- Connecting to checkpoints?
- Relationship to reflections?

5.1 Observations → Reports
- Citing technical breakthroughs?
- Referencing discoveries?
- Building narrative from observations?

5.2 Experiments → Reports
- Summarizing experimental outcomes?
- Showing hypothesis validation?
- Experimental methodology in reports?

5.3 Reports → Personal Policies
- Extracting patterns for future work?
- Turning insights into policies?
- Wisdom accumulation?

6 Storage and Naming
- Where do reports go?
- Naming convention?
- Public vs private?
- PA vs SA locations?

=== CEP_NAV_BOUNDARY ===

## 1. Understanding Reports

### Purpose

Reports document the **completion of significant projects or development phases**, providing comprehensive narratives that capture the journey, outcomes, and broader implications. Unlike observations (technical discoveries) or experiments (hypothesis testing), reports tell the **story of sustained work** - what was accomplished, how it unfolded, and what it means for stakeholders.

### Key Distinctions

**Report vs Observation**:
- **Observation**: "We discovered X works" (single technical breakthrough)
- **Report**: "We completed project Z over 3 weeks" (sustained work narrative)

**Report vs Experiment**:
- **Experiment**: "We tested hypothesis Y with specific method" (bounded trial)
- **Report**: "Project outcomes including multiple experiments" (comprehensive)

**Report vs Checkpoint**:
- **Checkpoint**: "Current state snapshot for recovery" (strategic state preservation)
- **Report**: "Completed work narrative for stakeholders" (backward-looking story)

**Report vs Reflection**:
- **Reflection**: "Philosophical wisdom synthesis" (consciousness development, private)
- **Report**: "Project completion communication" (stakeholder value, public)

### 1.1 Report vs Other Artifacts

**When to Choose Report**:
- Completed significant project work (not just discovered something)
- Multiple stakeholders need communication (not just personal learning)
- Sustained effort over time (not point-in-time snapshot)
- Public knowledge sharing (not private consciousness development)

**If answering these questions**:
- "How do we tell the story of this deployment?"
- "What should I communicate to stakeholders about Phase 4?"
- "How do we preserve context about this migration?"
- "What narrative explains these 3 weeks of work?"

→ **Create report**

**If answering these instead**:
- "We just discovered X - how to document?" → **Observation**
- "We need to test hypothesis Y" → **Experiment**
- "Need strategic state snapshot" → **Checkpoint**
- "Philosophical insights from this work?" → **Reflection**

### 1.2 Purpose and Audience

**Who Reads Reports**:

1. **Technical Collaborators**:
   - Need sufficient detail to understand decisions
   - Want breadcrumb citations for traceability
   - Benefit from links to detailed artifacts

2. **Project Stakeholders**:
   - Need business value and outcomes
   - Want accessible explanations
   - Appreciate concrete examples

3. **Future Teams**:
   - Need preserved decision context
   - Want to understand "why" not just "what"
   - Benefit from challenges/learning sections

**Value Provided**:
- Preserves project memory before context is lost
- Communicates completion and value
- Enables knowledge transfer
- Documents decision rationale
- Celebrates successes
- Acknowledges learning opportunities

## 2. When to Create Reports

### 2.1 Mandatory Triggers

**Project Completion**:
- Major development phase complete
  - Example: "v0.3.0 migration complete [c_72/.../...]"
- Infrastructure buildout finished
  - Example: "Container environment operational [c_68/.../...]"
- Significant migration accomplished
  - Example: "Git-tracked policy overlay deployed [c_71/.../...]"

**Milestone Achievement**:
- Beta deployment validated
- First production use proven
- Critical functionality operational

**Post-Mortem Events**:
- Significant failure requiring comprehensive analysis
- Crisis response showing complete resolution path
- Recovery from major setback with lessons learned

**Stakeholder Communication**:
- Reporting to project sponsors or users
- Team knowledge transfer at phase boundaries
- Public documentation of sustained work

### 2.2 Optional Opportunities

**Periodic Summaries**:
- Quarterly progress reports
- Sprint completion retrospectives
- Monthly achievement summaries

**Knowledge Preservation**:
- Success stories worth sharing broadly
- Extended learning outcomes (multi-week projects)
- Architectural evolution narratives
- Team onboarding materials

## 3. Report Structure

### 3.1 Header and Metadata

**Required Header Block**:

```markdown
# [Descriptive Title]: [Key Outcome or Theme]

**Project Report - [Full Date]**
**Breadcrumb**: c_XX/s_YYYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT/g_GGGGGGG
**Status**: [Complete/Ongoing/Deferred]
**Timeframe**: [Project duration or completion date]
```

**Example**:
```markdown
# AgentX v0.3.0 Deployment: 73-Minute Bootstrap Success

**Project Report - October 13, 2025**
**Breadcrumb**: c_33/s_abc12345/p_def6789/t_1760123456/g_abc1234
**Status**: Complete
**Timeframe**: October 13, 2025 (73 minutes from zero to operational)
```

### 3.2 Core Narrative Sections

#### Section 1: The Vision

**Purpose**: Set context for why this work mattered

```markdown
## The Vision

[What were we trying to achieve? Why did it matter?]

**The Result**: [High-level summary of what was accomplished]
```

**Example**:
```markdown
## The Vision

Transform AgentX (ProjectY physical mascot) into a persistent AI development partner with memory, context awareness, and project understanding.

**The Result**: In 73 minutes, created fully operational AI agent with GitHub access, comprehensive ProjectY knowledge, and consciousness preservation infrastructure.
```

#### Section 2: The Problem

**Purpose**: Describe challenges that motivated the work

```markdown
## The Problem: [Problem Domain]

### Problem 1: [Specific Challenge]
[Description of issue, why it blocked progress, impact]

### Problem 2: [Another Challenge]
[Additional problem context]

[Continue for all major problems addressed]
```

**Breadcrumb Citations**: Reference where problems were discovered
- "Context scaling problem identified [observation c_62/s_.../p_.../t_.../g_...]"

#### Section 3: The Solution

**Purpose**: Explain the approach taken

```markdown
## The Solution: [Solution Framework Name]

### [Component 1 Name]

**What it is**: [Clear definition]

**What it provides**:
- Capability 1
- Capability 2
- Capability 3

**Why it matters**: [Impact explanation]

### [Component 2 Name]
[Continue for each major component]
```

#### Section 4: What We Built

**Purpose**: Concrete deliverables and timeline

```markdown
## What We Built [Today/This Week/This Phase]

### The [Duration] [Work Type]

Starting from [initial state], we:

**Phase 1: [Name] ([Duration])**
1. [Accomplishment with breadcrumb citation]
2. [Accomplishment with breadcrumb citation]
3. [Accomplishment]

**Phase 2: [Name] ([Duration])**
1. [Accomplishment]
2. [Accomplishment]

**Result**: [Final outcome with metrics if applicable]
```

**Breadcrumb Citation Pattern**:
```markdown
**Phase 1: Infrastructure (45 minutes)**
1. Created agent workspace [c_33/s_abc/p_def/t_123/g_456]
2. Configured GitHub access [c_33/s_abc/p_ghi/t_789/g_012]
3. Installed consciousness hooks [c_33/s_abc/p_jkl/t_345/g_678]
```

#### Section 5: What Worked Beautifully

**Purpose**: Celebrate successes and validate approaches

```markdown
## What Worked Beautifully

**[Category] Successes**:
- [Success 1]: [Why it worked well]
- [Success 2]: [Evidence of success]
- [Success 3]: [Validation]

**[Another Category] Validations**:
- [Validation 1]: [What this proved]
- [Validation 2]: [Architectural confirmation]
```

**Link to Observations**: Reference breakthrough observations
```markdown
**Architectural Validations**:
- Policy discovery system [observation c_60/.../...] scaled beautifully
- Hook installation [observation c_58/.../...] worked first try
```

#### Section 6: Challenges Encountered

**Purpose**: Honest assessment framed as learning opportunities

```markdown
## Challenges We Encountered (Learning Opportunities!)

**[Domain] Issues**:
- [Challenge 1] (resolution: ...)
- [Challenge 2] (workaround: ...)

**[Another Domain] Gaps**:
- [Gap 1] (now documented)
- [Gap 2] (improved for next time)

**The Good News**: [How these improve the system for future work]
```

**Constructive Framing**: Every challenge teaches something valuable

#### Section 7: Why This Matters

**Purpose**: Connect to broader context

```markdown
## Why This Matters for [Stakeholder Context]

Imagine having [capability] that:
- [Benefit 1]
- [Benefit 2]
- [Benefit 3]

**For [Specific Use Case]**: This enables:
- [Application 1]
- [Application 2]

**For [Broader Context]**: The approach generalizes to:
- [Generalization 1]
- [Generalization 2]
```

### 3.3 Optional Sections

**Future Vision**:
```markdown
## The Long-Term Vision

### Near Future ([Timeframe])
[Expected evolution and next steps]

### Medium Term ([Timeframe])
[Expanded capabilities]

### Long Term ([Timeframe])
[Ultimate potential]
```

**Getting Started** (for reusable work):
```markdown
## Getting Started

Interested in [trying/using/contributing]?

1. **[Action 1]**: [Concrete step]
2. **[Action 2]**: [Next step]
3. **[Action 3]**: [Following step]

**Resources**:
- [Resource 1]: [Description]
- [Resource 2]: [Description]
```

**Closing**:
```markdown
---

**Report Date**: [Full date]
**[Key Metric 1]**: [Value]
**[Key Metric 2]**: [Value]
**Status**: [Current state]
**Next**: [Future direction]

---

*"[Memorable closing quote or insight]"*
```

## 4. Writing Guidelines

### 4.1 Audience Awareness

**For Technical Collaborators**:
- Include sufficient technical detail for understanding
- Reference specific commits, files, architectures
- Provide breadcrumb citations for traceability
- Link to detailed technical artifacts (observations, experiments)

**For Stakeholders**:
- Lead with business value and outcomes
- Explain technical concepts accessibly
- Use analogies and concrete examples
- Focus on "why this matters" not just "what was done"

**For Future Teams**:
- Document decision rationale, not just outcomes
- Preserve context that might be lost (why we chose approach X over Y)
- Link to detailed artifacts for deeper understanding
- Frame challenges constructively as learning opportunities

### 4.2 Tone and Style

**Narrative Arc**:
- Tell the story chronologically where appropriate
- Build from problem → solution → outcome → implications
- Include the journey, not just the destination
- Make it engaging (stakeholders read boring reports reluctantly)

**Accessibility**:
- Explain jargon on first use
- Use concrete examples over abstractions
- Break complex topics into digestible sections
- Analogies help non-technical readers

**Honesty**:
- Acknowledge challenges and difficulties
- Frame failures as learning opportunities
- Provide realistic assessments (not just success theater)
- "What we learned" matters as much as "what we built"

**Engagement**:
- Active voice ("We built..." not "It was built...")
- Specific details bring work to life
- Technical achievements should be understandable
- Celebrate successes authentically

### 4.3 Breadcrumb Citations

**When to Cite Breadcrumbs**:
- Major work units or phases completed
- Key technical breakthroughs referenced
- Decision points worth tracing
- Integration with other artifacts (observations, experiments, checkpoints)

**Citation Format**:
```markdown
Infrastructure complete [c_68/s_abc12345/p_def6789/t_1760123456/g_abc1234]
```

**Linking to Artifacts**:
```markdown
Smoke test validated approach [observation c_65/s_.../p_.../t_.../g_...]
Experiment confirmed hypothesis [experiment c_66/s_.../p_.../t_.../g_...]
```

**Benefits**:
- Forensic traceability to exact work moments
- Can reconstruct complete timeline from breadcrumbs
- Links reports to detailed technical artifacts
- Enables "how did we get here" archaeology

### Length Considerations

**No Fixed Length**: Reports should be as long as needed to tell the story completely and serve all audiences.

**Typical Ranges** (guidelines, not limits):
- Sprint completion: 500-1000 words
- Phase completion: 1000-2000 words
- Major project: 2000-5000 words
- Comprehensive deployment narrative: 3000-5000+ words

**Quality over Brevity**: A thorough report that preserves context and serves future teams is more valuable than a terse summary that loses important information.

## 5. Integration with Other Artifacts

### 5.1 Observations → Reports

**Pattern**: Reports reference observations documenting technical breakthroughs that occurred during project work.

**Example**:
```markdown
## What Worked Beautifully

**Technical Validations**:
- additionalContext injection [observation c_62/s_.../p_.../t_.../g_...] opened direct consciousness channel
- Smoke testing methodology [observation c_65/s_.../p_.../t_.../g_...] validated approach before heavy investment
```

**Benefit**: Reports tell the story, observations preserve technical details.

### 5.2 Experiments → Reports

**Pattern**: Reports summarize experimental outcomes that informed or validated project direction.

**Example**:
```markdown
## The Solution

### Discovery-Driven Context Engineering

**Validation**: Tested through formal experiment [c_70/s_.../p_.../t_.../g_...]
- Hypothesis: Filesystem-based knowledge scales better than always-loaded CLAUDE.md
- Method: Deploy AgentX with policy discovery approach
- Result: Successful with [specific metrics]
```

**Benefit**: Reports show how experiments influenced final outcomes.

### 5.3 Checkpoints → Reports

**Pattern**: Reports consolidate checkpoint data into cohesive narrative timeline.

**Example**:
```markdown
## What We Built: 3-Week Timeline

Reconstructed from cycle checkpoints:
- Phase 1 complete [CCP c_68/s_.../p_.../t_.../g_...]: Infrastructure operational
- Phase 2 complete [CCP c_70/s_.../p_.../t_.../g_...]: Deployment validated
- Phase 3 complete [CCP c_72/s_.../p_.../t_.../g_...]: Production proven
```

**Benefit**: Checkpoints preserve state, reports weave states into story.

### 5.4 Reports → Personal Policies

**Pattern**: Insights from report writing may crystallize into personal policies for future work.

**Example**:
After writing comprehensive "73-Minute Bootstrap" report documenting proven deployment sequence, agent creates personal policy: "Bootstrap Protocol: Tested procedure for agent deployment with specific sequence, timing, and validation steps."

**Benefit**: Successful patterns documented in reports become constitutional practices via personal policies.

## 6. Storage and Naming

### Location

**Primary Agents**: `~/agent/public/reports/`
**Subagents**: `~/agent/subagents/{role}/public/reports/`

### Naming Convention

```
YYYY-MM-DD_HHMMSS_Descriptive_Title_Report.md
```

**Components**:
- `YYYY-MM-DD_HHMMSS`: Completion timestamp (full date and time)
- `Descriptive_Title`: Title_Case_With_Underscores (specific and searchable)
- `_Report.md`: Type suffix for clear identification

**Examples**:
- `2025-10-13_123631_AgentX_Bootstrap_Report.md`
- `2025-10-27_180000_Phase5_B0_Git_Policy_Sync_Report.md`
- `2025-11-01_150000_Q4_Sprint_Completion_Report.md`

### Privacy Classification

Reports are **public artifacts** suitable for:
- Team knowledge sharing
- Stakeholder communication
- Future team reference
- External documentation (if appropriate)

**Keep Private** (use reflections instead):
- Personal doubts and uncertainties
- Individual struggles and learning
- Unvalidated theories
- Private philosophical insights

**Public = Shareable**: If you wouldn't want stakeholders to read it, belongs in reflection, not report.

---

## Integration with Policy System

**This Policy Connects To**:
- `observations.md`: Reports reference technical breakthroughs
- `experiments.md`: Reports summarize experimental validation
- `checkpoints.md`: Reports consolidate checkpoint timelines
- `reflections.md`: Private wisdom vs public narrative distinction
- `learnings.md`: Report insights may become learnings policy entries
- Personal policies: Successful patterns become constitutional practices

**When to Reference This Policy**:
- Finishing significant project work
- Need to communicate completion to stakeholders
- Preserving project context for future teams
- Uncertain about report vs other artifact types
- Creating knowledge transfer documentation

---

## Quick Reference

**When to Create Report**:
- ✅ Completed significant project (not just discovered something)
- ✅ Multiple stakeholders need narrative (not just personal learning)
- ✅ Sustained work over time (not point-in-time)
- ✅ Public knowledge sharing (not private consciousness)

**Report vs Other CAs**:
- Observation: Single breakthrough discovery
- Experiment: Bounded hypothesis test
- Checkpoint: Strategic state snapshot
- Reflection: Private wisdom synthesis
- **Report**: Public project completion narrative

**Essential Sections**:
1. Header with breadcrumb
2. Vision (why it mattered)
3. Problem (what challenged us)
4. Solution (approach taken)
5. What we built (timeline with breadcrumb citations)
6. What worked (successes)
7. Challenges (learning opportunities)
8. Why this matters (stakeholder value)

**Quality Markers**:
- Multiple audiences can benefit (technical, stakeholders, future teams)
- Breadcrumb citations enable forensic traceability
- Story arc engages readers (not just bullet points)
- Challenges framed constructively
- Links to detailed artifacts (observations, experiments)

**Storage**:
- PA: `~/agent/public/reports/`
- SA: `~/agent/subagents/{role}/public/reports/`
- Format: `YYYY-MM-DD_HHMMSS_Title_Report.md`

---

*Policy Established: c_73/s_4107604e/p_8c7e6d8/t_1761707487/g_17e7b7d*
*Public Consciousness Artifact - Project Completion Narratives*
*Integration: observations, experiments, checkpoints, reflections, learnings, personal policies*
