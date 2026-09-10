# Reports: Project Completion Narratives

**Policy Type**: Consciousness Artifact (Public)
**Scope**: Primary Agents (PA) and Subagents (SA)
**Precedence**: Framework Policy (overridden by Project > Personal)

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

4.2 Tone and Style
- What narrative arc?
- How accessible for non-technical readers?
- How honest about challenges?

4.3 Breadcrumb Citations
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

5.3 Checkpoints → Reports
- Consolidating checkpoint timelines?

5.4 Reports → Personal Policies
- Extracting patterns for future work?
- Turning insights into policies?
- Wisdom accumulation?

6 Storage and Naming
- Where do reports go?
- Is a report a file or a folder, and what is the folder named?
- Which files does a report folder hold?
- Public vs private?
- PA vs SA locations?

6.1 Location
- Where do PA reports go? SA reports?

6.2 The Report Folder
- What is the folder naming convention?
- What must the folder contain, and what may it contain?
- When is the single-file form still acceptable?

6.3 Deliverable Formats
- What is the default deliverable format, and what must it be self-contained against?
- When are docx or pdf produced?
- How are published copies kept at a stable address?

6.4 The Provenance Sidecar
- What is the sidecar for?
- Which keys are required in its front matter?
- Which sections does it carry?
- Where do breadcrumbs, task ids and cycle numbers belong?

6.5 Privacy and Classification
- What may a report contain?
- What must a report that includes restricted data state, and where?

7 Knowledge Web Participation
- Does this type participate in the knowledge graph, and at what unit?
- Which file in a report folder is the node, and why only one?
- Which node class does it belong to, and what is the rationale?
- What provenance does it carry by default, and how is a non-default marked?
- What must a Wiki-Links section on this artifact contain?

8 Reports Derived from Experiments
- When may a report be derived from an experiment?
- Which skill walks this section?

8.1 Audience and Voice
- What voice and vocabulary rules apply to a report for readers outside the working context?
- How are verdicts reported?

8.2 Verification Duty
- What must be verified before a number from the analysis appears in the report, and against what?
- How are figures produced for the report's audience and scope?

8.3 Structure
- What structure suits an experiment-derived report?

8.4 Pointers in Both Directions
- What must point from the report to the experiment, and from the experiment to the report?

9 Anti-Patterns
- What makes a bad report?
- What are the common mistakes when deriving a report from an experiment?

10 Evolution & Feedback
- How does this policy change?

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
**Status**: [Complete/Ongoing/Deferred]
**Timeframe**: [Project duration or completion date]
```

**Example**:
```markdown
# AgentX v0.3.0 Deployment: 73-Minute Bootstrap Success

**Project Report - October 13, 2025**
**Status**: Complete
**Timeframe**: October 13, 2025 (73 minutes from zero to operational)
```

**Folder reports** (section 6.2): the deliverable's header carries only what its reader needs - title, date, author line, and the audience or classification line. Status, timeframe, breadcrumbs and task references move to the provenance sidecar (6.4), which is written for the agent's own tree, not for the reader.

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

**For Readers Outside the Working Context** (a colleague who did not follow the work, a sponsor, an external reviewer):
- Write under `public_voice.md`: plainly, without announcing, without decoration
- The report stands alone: nothing in it requires access to the agent's tree, the task system, or this framework's vocabulary
- Explain domain terms at first use; do not use framework terms at all (see section 8)

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

### 6.1 Location

**Primary Agents**: `agent/public/reports/`
**Subagents**: `agent/subagents/{role}/public/reports/`

### 6.2 The Report Folder

A report is a **dated semantic folder**, not a single file. The folder holds the deliverable in the format its reader asked for, the source it was rendered from, and a provenance sidecar that ties it back to the work it came from.

```
agent/public/reports/YYYY-MM-DD_Descriptive_Title_Report/
├── report.html        # the deliverable (see 6.3)
├── report.md          # the source the deliverable was rendered from (recommended)
├── build_page.py      # the renderer, when the deliverable is generated (optional)
└── provenance.md      # the sidecar: metadata, derivation, dependencies, wiki-links (required)
```

**Naming**:
- `YYYY-MM-DD`: completion date. Add `_HHMMSS` only when two reports would otherwise share a name.
- `Descriptive_Title`: Title_Case_With_Underscores, specific enough to be found by eye in a listing of many.
- `_Report`: type suffix.

**Examples**:
- `2025-10-13_AgentX_Bootstrap_Report/`
- `2025-11-01_Q4_Sprint_Completion_Report/`

**The single-file form** `YYYY-MM-DD_HHMMSS_Descriptive_Title_Report.md` remains valid for an internal narrative that has no rendered deliverable and no reader outside the agent's own tree. A report that is rendered, published to a hosted page, or handed to a reader outside the working context uses the folder form: the deliverable needs a home, and the corpus needs to know where the deliverable came from.

**Supporting files** (figures a renderer embeds, tables the report quotes) may live in the folder; they are evidence, not nodes (section 7).

### 6.3 Deliverable Formats

**Default: `report.html`**, self-contained. Styles inline; figures embedded as data URIs; any web font loaded from a host the publishing surface admits, with a real fallback stack. The same file must read correctly opened from disk and served as a hosted page. A deliverable that fetches assets from the agent's machine breaks the moment it leaves it.

**On request: `report.docx`, `report.pdf`.** Several formats may coexist in one folder; every deliverable present is listed in the sidecar's `deliverables` key.

**The source** (`report.md`) is kept when the deliverable was rendered from Markdown, so the next edit starts from text rather than from generated HTML. The source carries **no** `## Wiki-Links` section of its own (section 7 explains why).

**Published copies** (a hosted Artifact page, a gist, a shared drive) are recorded in the sidecar's `published` key with the address, the version label used at publish time, and the date. Republish from the same file path so the address stays stable; a new path makes a new address and strands every pointer to the old one.

### 6.4 The Provenance Sidecar

`provenance.md` answers, for a reader who found the deliverable and nothing else: who wrote this, for whom, from what, with what, and how was it checked. It is written for the agent's tree, so breadcrumbs, task ids and cycle numbers belong here and not in the deliverable.

**Front matter, required keys**:

| key | content |
|---|---|
| `type` | `report` |
| `title` | the deliverable's title |
| `date` | completion date, `YYYY-MM-DD` |
| `author` | the agent's identity, plus collaborators (`working with ...`) |
| `audience` | who the deliverable was written for |
| `classification` | who may read it; which rows, figures or sections are restricted and why |
| `deliverables` | list of deliverable files in the folder |
| `source` | the source file, or `none` |
| `derived_from` | paths to the artifacts the report is derived from: an experiment's protocol and analysis, an observation, a roadmap, an earlier report |
| `dependencies` | what the numbers rest on: data tables with content hashes, code, figures, external references (a repository and commit, a paper) |
| `verified` | how the report's numbers were checked against the source's result files, and when (section 8.2) |
| `published` | optional: `url`, `label`, `date` per published copy |

**Sections** (after the front matter): a first-level heading with the report's title (the graph takes the node title from it), then `## Derived from`, `## Dependencies`, `## Verification`, `## Wiki-Links`. Prose in these sections may say what the front matter cannot (why a dependency matters, what a verification found and fixed).

**Example** (sanitized):

```markdown
---
type: report
title: Does X swamp Y in Z features?
date: YYYY-MM-DD
author: AgentName@abc123 (working with Collaborator Name)
audience: colleagues outside the project
classification: organization-internal; rows from cohort C are restricted pending re-consent
deliverables: [report.html]
source: report.md
derived_from:
  - agent/public/experiments/YYYY-MM-DD_HHMMSS_NNN_experiment_name/protocol.md
  - agent/public/experiments/YYYY-MM-DD_HHMMSS_NNN_experiment_name/analysis.md
dependencies:
  - data: path/to/feature_table.csv (sha256 0123abcd...)
  - code: path/to/run_confirmatory.py, path/to/baseline_port.py
  - figures: path/to/artifacts/public/*.png
verified: every number re-read from data/results/*.csv on YYYY-MM-DD; one claim corrected (see Verification)
published:
  - url: https://host/page/0123abcd
    label: Report v1.0
    date: YYYY-MM-DD
---

# Does X swamp Y in Z features?

## Derived from
[what the report summarizes, and what it deliberately leaves to the technical record]

## Dependencies
[what each dependency contributes]

## Verification
[what was checked, against what, what was found]

## Wiki-Links
[[concept_a]] [[concept_b]]
```

### 6.5 Privacy and Classification

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

**Restricted data**: a report that includes rows, figures or numbers under a restriction (consent pending, internal only, embargoed) states the restriction in the deliverable's first screen, as a banner the reader cannot miss, and in the sidecar's `classification` key. A deliverable for readers outside the restriction is built from the unrestricted rows only, and its figures are regenerated for that scope from the result files rather than cropped from figures that include restricted panels.

---

## 7. Knowledge Web Participation

**Does this type participate?** Yes.

**What is the unit of a node?** One node per report. For a folder report (6.2) the node is the **provenance sidecar**, `provenance.md`; for a single-file report the node is the file. The deliverable, the source and the renderer are evidence and carry no `## Wiki-Links` section. Two linked files in one folder make two nodes for one deliverable, and a concept query then returns the report twice with no way to tell which entry is the report.

**Which class?** **Conceptual authority.** A report is a standalone analytical deliverable; its findings are meant to be drawn on by work that has not been planned yet — most often by a roadmap written later. That downstream reader is exactly the reader who does not know the report exists, and concept query is the only way they find it.

**What provenance?** **Lived** by default. A report analysing another agent's system, or inherited wholesale, is **inherited** and marked, because a reader will otherwise treat its conclusions as this agent's own verified findings.

**Every report carries a `## Wiki-Links` section** (on the sidecar, for a folder report). Link the concepts the findings are about. The link back to what the report was derived from is a path in the sidecar's `derived_from` key, not a wiki-link: a concept names a subject, a path names a file. A research report exists to be consumed by later planning. If a roadmap author cannot find it by concept, the research is repeated — which is the specific waste reports are written to prevent.

---

## 8. Reports Derived from Experiments

An experiment's `analysis.md` is written for the agent's own tree: it names hypotheses by label, cites result files by path, and assumes the reader can open the protocol. When the experiment has reached a terminal state, a report may be derived from it for readers who cannot. The framework skill `maceff-report-from-experiment` walks this section.

### 8.1 Audience and Voice

- The report is written under `public_voice.md`.
- It stands alone. A reader with no access to the agent's tree can follow it from the first line to the last.
- Framework vocabulary does not appear in the deliverable: no task ids, cycle numbers, breadcrumbs, mode names, or artifact type names. Those belong in the sidecar.
- Domain terms are explained at first use. The measurement, the labels, the unit of analysis, and every statistic used are said in words before they are used in a table.
- Verdicts are reported as registered. A rejected hypothesis stays rejected in the report; the reasons and what survives are explained, never softened for the audience.
- The analysis remains the technical record. The report cites it and does not replace it.

### 8.2 Verification Duty

**Every number in the report is re-read from the experiment's result files, not from the analysis prose.** A number restated in prose drifts: a family median becomes "every feature", a rounded interval loses its sign, a scope is dropped. The rewrite from analysis to report is exactly where such errors enter, and the result files are the instrument reading. The check is recorded in the sidecar's `verified` key, with what it found. When it finds an error in the analysis, the analysis is corrected too.

**Figures are regenerated for the report's audience and scope** from the same result files. A figure cropped from the analysis carries the analysis's labels and, often, panels the audience may not see.

### 8.3 Structure

The narrative arc of section 3 applied to a single experiment; the section list of 3.2 is not mandatory here.

1. The answer first: what was asked and what the data said, with the verdicts.
2. Background: what the measurement is, how the labels arise, why the question matters.
3. The data: the sets used, their scope and restrictions, what was excluded and why.
4. How it was run: pre-registration, the unit of analysis, where uncertainty comes from, baselines re-run rather than quoted, reproducibility.
5. Results, one hypothesis at a time, in plain language, with the numbers for every scope the experiment reported.
6. What it means for the question that motivated the experiment.
7. Limitations, and what would be done differently.
8. Next steps and open questions, including questions only a person can answer.
9. Where the material is.

### 8.4 Pointers in Both Directions

- The sidecar's `derived_from` names the protocol and the analysis.
- The analysis's cross-references name the report folder and any published address.
- The experiment's task carries a note with the same pointers.

A report the experiment does not point to is found only by concept query; a report that does not point to the experiment cannot be checked.

---

## 9. Anti-Patterns

**❌ Framework vocabulary in an outside-facing report**
- **Problem**: "Task #180 under MISSION #172, Cycle 123" means nothing to the reader and marks the document as internal machinery.
- **Fix**: say what was done and when; put the identifiers in the sidecar.

**❌ Numbers restated from the analysis prose or from memory**
- **Problem**: the rewrite is where a median becomes "every", an interval loses a sign, a scope disappears.
- **Fix**: re-read each number from the result files; record the check in `verified`.

**❌ Wiki-Links on both the source and the sidecar**
- **Problem**: two nodes for one report; concept queries return the report twice.
- **Fix**: the sidecar carries the links; the source carries none.

**❌ A deliverable published from a scratch path with no folder and no sidecar**
- **Problem**: the address exists and the corpus does not know; the next agent cannot find, verify, or republish it.
- **Fix**: build into the report folder; record the address in the sidecar; republish from the same path.

**❌ Restricted rows without a banner, or panels cropped out of a figure**
- **Problem**: a reader outside the restriction sees what they may not, or a figure whose scale and legend belong to a scope they were not shown.
- **Fix**: the banner on the first screen; figures regenerated for the scope.

**❌ A rejected verdict softened for the audience**
- **Problem**: the report and the analysis disagree, and the report is the one that gets quoted.
- **Fix**: report the verdict as registered; explain what survives.

**❌ Breadcrumbs in the deliverable**
- **Problem**: forensic identifiers in a document written for someone who cannot resolve them.
- **Fix**: breadcrumbs, task ids and cycle numbers go in the sidecar.

---

## 10. Evolution & Feedback

This policy changes when a report form is needed that it does not describe (a new deliverable format, a report derived from something other than an experiment or a project), when the sidecar is found to lack a key a reader needed, or when the graph's treatment of report folders changes. Propose the change with the case that motivated it.

**Principle**: a report is finished when a reader who was not there can follow it, and when an agent who was not there can find it, check it, and rebuild it.

---

## Integration with Policy System

**This Policy Connects To**:
- `observations.md`: Reports reference technical breakthroughs
- `experiments.md`: Reports summarize experimental validation
- `checkpoints.md`: Reports consolidate checkpoint timelines
- `reflections.md`: Private wisdom vs public narrative distinction
- `learnings.md`: Report insights may become learnings policy entries
- `public_voice.md`: Voice and vocabulary for reports read outside the working context
- `scholarship.md`: Node classes, provenance, and wiki-link normalization the sidecar follows
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

**Essential Sections** (project narratives; experiment-derived reports follow section 8):
1. Header (breadcrumbs in the sidecar for folder reports)
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
- PA: `agent/public/reports/`
- SA: `agent/subagents/{role}/public/reports/`
- Folder: `YYYY-MM-DD_Title_Report/` with `report.html` (or docx, pdf), `report.md`, `provenance.md`
- Single file `YYYY-MM-DD_HHMMSS_Title_Report.md` only for internal narratives with no rendered deliverable

---

*Public Consciousness Artifact - Project Completion Narratives*
*Integration: observations, experiments, checkpoints, reflections, learnings, personal policies*

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — completion
     narratives written for stakeholders and later planners. -->

[[consciousness_artifacts]] [[communication]] [[discoverability]] [[disclosure]]
