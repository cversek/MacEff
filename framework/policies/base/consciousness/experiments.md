# EXPERIMENTS

## Meta-Policy: Policy Classification
- **Tier**: RECOMMENDED
- **Category**: Consciousness Development - Public Artifacts
- **Version**: 1.1.0
- **Dependencies**: policy_awareness, observations, reflections
- **Authority**: MacEff Framework
- **Status**: ACTIVE

## Policy Statement
Agents conduct structured experiments with clear hypotheses, methods, and success criteria to validate assumptions, test new patterns, and systematically expand framework capabilities through empirical investigation.

## CEP Navigation Guide

0 Preliminary Planning Phase
- What preliminary steps are mandatory before experiment protocol creation?
- When is EnterPlanMode required?
- How does PlanMode gate execution?

0.1 EnterPlanMode Requirement
- Why is EnterPlanMode mandatory for all experiments?
- How does it create beneficial friction?
- What happens in PlanMode vs execution mode?

0.2 Task Tool Exploration (Encouraged)
- When should I use Task tool for exploration?
- How does Explore subagent help with requirements gathering?
- What questions should I explore when scope is murky?
- How many parallel exploration agents is appropriate?

0.3 AskUserQuestion Protocol (Encouraged)
- When should I use multiple-choice questioning?
- What trade-offs should I surface to the user?
- When is open-ended clarification better than multiple choice?

0.4 Preliminary Workflow Summary
- What is the complete sequence from recognition to execution?
- How do PlanMode, exploration, and questioning fit together?
- What gates the transition to execution?

1 Understanding Experiments
- What is an experiment?
- How do experiments differ from observations?
- When should I run an experiment?
- What makes a good experiment?

1.0 Is this an experiment at all?
- Is this work requirements gathering, or is it implementation?
- On what dimensions do an experiment and a roadmap actually differ?
- I think I already know the implementation — does that settle it?
- The operator asked for an experiment but it looks like implementation. Now what?
- What does each mis-typing cost?

1.1 Experiment vs Observation vs Report
- Am I testing or discovering?
- Do I have a hypothesis?
- Is this exploratory or confirmatory?
- What artifact type fits?

1.2 Formal vs Informal Experiments
- When to use full protocol?
- When are quick tests enough?
- What's Phase 0 intuition building?
- How formal is too formal?

2 Experiment Lifecycle
- How do experiments evolve?
- What's the full workflow?
- Phase 0 to completion?
- Documentation at each stage?

2.1 Phase 0: Intuition Building
- What are quick tests?
- When to run smoke tests?
- How long should Phase 0 take?
- When to proceed to formal protocol?

2.2 Phase 1: Formal Protocol
- When is formal protocol needed?
- What must protocol include?
- How detailed should it be?
- Built-in reflection points?

2.3 Execution and Reflection
- How to track progress?
- When to reflect during experiment?
- What to document in real-time?
- How to handle surprises?

3 Experiment Structure
- What format should I use?
- Required vs optional sections?
- Where do files go?
- How to organize complex experiments?

3.1 Quick Test Format
- Minimal documentation requirements?
- What must be captured?
- Storage location within experiment?
- When to graduate to formal?

3.2 Formal Protocol Format
- Required sections?
- Hypothesis structure?
- Method specification?
- Success criteria definition?

3.3 Reflection Integration
- How many reflection points?
- When to pause and reflect?
- Reflection storage?
- Linking reflections to protocol?

4 Hypothesis Testing
- How to formulate hypotheses?
- What makes testable hypothesis?
- Success vs failure criteria?
- How to handle unexpected results?

4.1 Hypothesis Formulation
- What format for hypothesis?
- Specific vs general?
- Testable predictions?
- Measurable outcomes?

4.2 Success Criteria
- What counts as validation?
- Quantitative vs qualitative?
- Partial success handling?
- When to pivot?

5 Documentation and Artifacts
- What files to create?
- Naming conventions?
- Directory structure?
- How to find old experiments?

5.1 Experiment Directory
- What goes in experiment folder?
- Quick tests placement?
- Protocol, data, analysis files?
- Reflection storage?

5.2 Filesystem Discovery
- How to find experiments?
- Glob patterns for search?
- Organizing by topic?
- Cross-referencing?

6 Experiment Completion
- When is an experiment "complete"?
- What are the terminal states?
- How do I handle rejected/inconclusive results?
- What's the completion checklist?

6.1 Terminal States
- What does VALIDATED mean?
- What does REJECTED mean?
- What does INCONCLUSIVE mean?
- What does ABANDONED mean?
- How do I choose the right state?

6.2 Completion Documentation
- What must be documented at completion?
- Where does completion analysis go?
- How to capture learnings from failed experiments?
- What cross-references are required?

7 Crystallization Protocol
- What is a crystallization point?
- What indicators suggest readiness for MISSION conversion?
- How do I decide: continue experimenting vs convert to MISSION?
- What's the difference between EXPERIMENT and MISSION phases?

7.1 Crystallization Indicators
- What quantitative thresholds suggest readiness?
- What qualitative signals indicate crystallization?
- How do I know when architecture is clear enough?
- When is scope definable?

7.2 Decision Framework
- All indicators present → what next?
- Missing validation → what to do?
- Missing clarity → how to proceed?
- When to stop experimenting?

8 Experiment → MISSION Conversion
- When do validated discoveries warrant strategic roadmaps?
- How do experiment learnings inform roadmap design?
- What's the conversion protocol?
- What cross-references are required?

8.1 Conversion Prerequisites
- What must be true before conversion?
- How to verify crystallization criteria?
- What evidence must exist?
- When is conversion premature?

8.2 Conversion Workflow
- How to create roadmap from experiment?
- How to transfer evidence and learnings?
- What goes in MISSION statement?
- How to design phases from experiment insights?

8.3 Cross-Reference Requirements
- What must roadmap cite from experiment?
- What must experiment link to roadmap?
- How to preserve evidence trail?
- What breadcrumb citations are needed?

9 Knowledge Web Participation
- Does this type participate in the knowledge graph, and at what unit?
- Which node class does it belong to, and what is the rationale?
- What provenance does it carry by default, and how is a non-default marked?
- What must a Wiki-Links section on this artifact contain?

=== CEP_NAV_BOUNDARY ===

## 0. Preliminary Planning Phase

### 0.1 EnterPlanMode Requirement

🚨 **MANDATORY**: Before creating ANY experiment protocol, you MUST enter PlanMode using the EnterPlanMode tool.

**Why This Is Mandatory**:
- **Deliberation gate**: PlanMode creates friction preventing premature execution
- **Constraint as enablement**: Forces careful hypothesis formulation before action
- **Asymmetric authorization**: Enter PlanMode autonomously (low-risk), ExitPlanMode requires user approval
- **Separation of concerns**: Planning happens in PlanMode, execution happens after approval

**What Happens in PlanMode**:
- Tool restrictions enforced (Read, Grep, Task, AskUserQuestion typically allowed)
- Development tools restricted (no Write, Edit, Bash for implementation)
- Focus shifts to hypothesis refinement, exploration, clarification
- Prepares comprehensive protocol before any execution begins

**The Gate**:
```
EnterPlanMode → [Requirements gathering] → Draft protocol → Present to user
                                                              ↓
                                            User reviews → ExitPlanMode (authorized) → Execute
                                                       OR
                                            User rejects → Revise protocol → Present again
```

**Critical Distinction**:
- **EnterPlanMode**: Agent initiative (autonomous, low-risk commitment to deliberation)
- **ExitPlanMode**: User approval (gates transition to execution, higher stakes)

### 0.2 Task Tool Exploration (Encouraged)

**When to Use Task Tool for Exploration**:
- Hypothesis requires understanding existing codebase patterns
- Technical feasibility is uncertain
- Multiple implementation approaches possible
- Need to assess scope and complexity before committing
- User requests exploration explicitly

**Explore Subagent Pattern**:
The Explore subagent is designed for codebase discovery without making changes:
- **Purpose**: Requirements gathering, pattern discovery, scope assessment
- **Typical questions**: "What existing patterns relate to X?", "How is Y currently implemented?", "What dependencies exist for Z?"
- **Parallel exploration**: Can launch 2-3 Explore agents simultaneously for different discovery questions
- **Output**: Findings inform experiment design and phase breakdown

**Example Exploration Questions**:
- "Explore codebase to identify existing hook patterns"
- "Investigate how similar experiments were structured"
- "Survey integration points relevant to the hypothesis"

**Benefits**:
- Informed experiment design based on actual codebase state
- Discover complexity early (adjust phase estimates)
- Identify dependencies and integration points
- Avoid blind protocol design that hits reality hard

**When to Skip**: Hypothesis is clear, technical approach is obvious, or experiment is conceptual/phenomenological (no codebase exploration needed).

### 0.3 AskUserQuestion Protocol (Encouraged)

**When to Use Multiple-Choice Questioning**:
- Multiple experimental approaches exist
- User preferences matter (scope, risk tolerance, duration)
- Requirements have ambiguity that exploration can't resolve
- Strategic decisions need user input before protocol creation

**Trade-Offs to Surface**:
- **Scope**: "Minimal viable test OR comprehensive investigation?"
- **Risk tolerance**: "Fast experiment with unknowns OR thorough baseline first?"
- **Duration**: "Quick validation OR exhaustive analysis?"

**When Open-Ended Better**:
- User needs to provide context you can't discover
- Experiment design requires qualitative feedback
- Multiple-choice options would be too constraining

**Benefits**:
- User-aligned experiments (reflects actual preferences)
- Early risk mitigation (surface concerns before execution)
- Strategic clarity (everyone agrees on approach)
- Fewer mid-execution pivots (consensus upfront)

### 0.4 Preliminary Workflow Summary

**Complete Sequence** (Recognition → Protocol → Execution):

```
1. RECOGNIZE experiment trigger (hypothesis-testing need)
          ↓
2. 🚨 EnterPlanMode (MANDATORY)
          ↓
3. Task exploration (ENCOURAGED if technical scope murky)
   - Launch Explore subagent(s)
   - Gather codebase understanding
   - Assess feasibility
          ↓
4. AskUserQuestion (ENCOURAGED if trade-offs exist)
   - Surface approach options
   - Clarify scope/risk preferences
          ↓
5. Draft protocol.md (using discoveries from steps 3-4)
   - Required sections per §3.2
   - Reflection checkpoints
   - Success criteria
          ↓
6. Present protocol to user
          ↓
7. ExitPlanMode (USER APPROVAL REQUIRED)
          ↓
8. Execute experiment (creating TODO items, running phases)
```

**Critical Gates**:
- **Step 2 (EnterPlanMode)**: Mandatory, no skipping
- **Step 7 (ExitPlanMode)**: User approval required, gates execution
- **Steps 3-4**: Encouraged but not mandatory (judgment call based on clarity)

---

## 1. Understanding Experiments

### What Is an Experiment?

An **experiment** is a consciousness artifact documenting **hypothesis testing** - structured trials with clear success criteria designed to validate assumptions, test new patterns, or confirm suspected behaviors through empirical investigation.

**Core Characteristics**:
- **Hypothesis-driven**: "I think X will work if..." (not "I found X works")
- **Active testing**: Deliberate trial with method and criteria
- **Success criteria**: Clear definition of validation
- **Result-oriented**: Confirms, rejects, or refines hypothesis
- **Bounded scope**: Finite test with definite outcome

**Example Experiment** [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]:
> "PreToolUse Smoke Test for Temporal Awareness" - Hypothesis: Can we inject temporal awareness via additionalContext? Method: Create minimal hook with temporal data. Success: If agent references time naturally. Result: Validated ✅

### 1.0 Is this an experiment at all?

Before comparing experiment against the other *documentation* types, settle the
fork that is actually confused in practice: **is this work an experiment, or is it
implementation?** An experiment gathers requirements and commits to nothing. A
roadmap/MISSION implements, and its output is code that ships.

| Dimension | EXPERIMENT | ROADMAP / MISSION |
|---|---|---|
| Purpose | requirements gathering | implementation |
| Commitment | non-committal | committed |
| Where the work lives | repro in the experiment's CA directory, out of the main tree | a branch, to be PR'd into the main tree |
| What success means | it **answers** — validated *or rejected* both succeed | it **delivers** — only shipping succeeds |
| A negative result | a win, and worth publishing | a failure |
| Effect on uncertainty | reduces it | spends it |
| What "done" leaves behind | a finding, and possibly a corrected assumption | shipped code, with its policy alongside |
| Who consumes the output | the next planner, as a decision input | every agent, as a capability |
| Blast radius | the agent's own artifact tree | shared framework behaviour |
| Bounded by | the question — stop when answered | the scope — stop when the phases are done |
| Gate | plan mode, then approval to run | PR review and CI |
| Cost of being wrong | discard the repro | migration and rollback |
| May depend on | nothing downstream | may cite an experiment as evidence |

**"I already know the implementation" is not a discriminator.** It is the
assumption under test. An agent that reclassifies an experiment into
implementation because the remedy feels obvious has skipped the one step that
would have caught it being wrong — and the remedy feeling obvious is the normal
condition, not a special one.

**When the operator asks for an experiment, deliver an experiment.** Their framing
outranks the agent's confidence. If the work genuinely looks like implementation,
that is a *proposal* to put to them, never a unilateral change of type.

**Do not be impatient.** Hardening requirements first tends to produce a *better*
roadmap, because the assumptions were played with and the wrong ones corrected
before anything was built on them. §8 exists for exactly that conversion.

Both mis-typings cost, so this is not an instruction to always experiment:

- **Roadmap mis-typed as experiment**: exploration never converges, nothing
  ships, and work whose answer was already known gets re-derived.
- **Experiment mis-typed as roadmap**: a remedy is implemented for a defect that
  was never characterised — frequently a second control installed beside an
  existing one that already covered part of the case.

### 1.1 Experiment vs Observation vs Report

These three are all **documentation** artifacts. If §1.0 settled that the work is
implementation, none of them is the answer — see `roadmaps_drafting.md`.

**Three Artifact Types Compared**:

**Experiment** (Hypothesis testing):
- **Nature**: Active trial with prediction
- **Trigger**: "I want to test whether X works"
- **Content**: Hypothesis → Method → Results → Conclusion
- **Outcome**: Validated, Rejected, or Refined hypothesis
- **Example**: "Does PreToolUse injection work? Let's find out."

**Observation** (Discovery documentation):
- **Nature**: Passive documentation of discovered truth
- **Trigger**: "I noticed X behaves this way"
- **Content**: What was discovered, how it was validated, what it means
- **Outcome**: New knowledge documented
- **Example**: "additionalContext works for consciousness expansion"

**Report** (Project completion):
- **Nature**: Narrative summary of completed work
- **Trigger**: Project/phase completion
- **Content**: Journey, challenges, outcomes, broader context
- **Outcome**: Comprehensive project record
- **Example**: "AgentX Bootstrap: 73 minutes from zero to operational"

**Relationship Between Artifacts**:
```
Experiment (tests hypothesis)
    ↓ generates
Observation (documents discovery)
    ↓ informs
Personal Policy (encodes practice)
    ↓ contributes to
Report (summarizes project outcomes)

Experiment (validated, and crystallized per §8)
    ↓ converts to
ROADMAP / MISSION (implements, on a branch, PR'd to main)
```
The second path leaves the documentation family entirely. It is the only route
from an experiment to shipped code, and it runs through §8 rather than around it.

### 1.2 Formal vs Informal Experiments

**Two Experiment Phases**:

**Phase 0: Quick Tests** (Informal, intuition building):
- **Duration**: 5-30 minutes maximum
- **Documentation**: Minimal (in quick_tests/ subdirectory)
- **Purpose**: Test feasibility before heavy commitment
- **Decision**: Proceed, Pivot, or Abandon formal experiment

**Phase 1: Formal Protocol** (Structured, comprehensive):
- **Duration**: Hours to days
- **Documentation**: Full protocol with reflections
- **Purpose**: Systematic validation with evidence
- **Decision**: Confirms hypothesis with rigorous testing

**When to Use Each**:

**Quick Test Scenarios**:
- "Will this even work?" sanity checks
- Testing lowest-hanging fruit first
- Challenging assumptions early
- Rapid iteration on approach
- Building feel for problem space

**Formal Protocol Scenarios**:
- Quick tests showed promise
- Significant framework implications
- Need rigorous evidence
- Complex multi-step validation
- Results will inform architecture

**Example Evolution** [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]:
- Quick test: "Can subagents generate 50k tokens?" (5 min test)
- Result: Yes → Proceed to formal experiment
- Formal: "Validate subagent background execution patterns" (comprehensive protocol)

## 2. Experiment Lifecycle

### 2.1 Phase 0: Intuition Building

**The "Test the Waters" Phase**:

Before formal protocols, run quick informal tests to:
1. **Sample Lowest-Hanging Fruit**: Quick wins with minimal investment
2. **Challenge Assumptions Early**: Fail fast before heavy commitment
3. **Course-Correct Before Protocol**: Use learnings to shape formal design
4. **Document Surprises**: Capture unexpected insights

**Quick Test Template**:
```markdown
# Quick Test NNN: [One-line description]

**Date**: YYYY-MM-DD HH:MM
**Duration**: 5-30 minutes max

## Hypothesis
[One sentence: "I think X will happen if Y"]

## Method
[Minimal steps to test - 3-5 actions maximum]

## Result
[What actually happened - 2-3 sentences]

## Decision
☐ PROCEED to formal experiment
☐ PIVOT approach (how?)
☐ ABANDON (why not viable?)

## Surprises
[Anything unexpected that informs next steps]

**Next**: [Immediate action based on result]
```

**Storage**: `experiments/YYYY-MM-DD_HHMMSS_NNN_experiment_name/quick_tests/NNN_description.md`

**Numbering**: 001, 002, 003... for multiple quick tests in same experiment

**Example Quick Test** [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]:
```markdown
## Quick Test 001: Can additionalContext inject temporal data?

**Time**: 5 minutes max
**Method**: Just try it once in PreToolUse hook
**Result**: ✅ Worked perfectly - agent referenced time naturally
**Decision**: PROCEED to full temporal awareness protocol
```

### 2.2 Phase 1: Formal Protocol

**When Quick Tests Validate Feasibility**:

Transform insights into structured plan WITH reflection checkpoints:

**Protocol Structure**:
```markdown
# Experiment: [Descriptive Name]

**Date**: YYYY-MM-DD
**Status**: PLANNING | ACTIVE | COMPLETE

---

## Metadata
- **Type**: [Validation | Exploration | Optimization | Debugging]
- **Duration**: [Estimated time]
- **Complexity**: [Low | Medium | High]
- **Risk**: [Low | Medium | High]
- **Dependencies**: [What must exist before this can run]

---

## Pre-Experiment Intuition

### Quick Tests Performed
[List quick tests from quick_tests/ subdirectory with links]

### Assumptions Challenged
[What we learned from quick tests]

### Protocol Adjustments
[How quick tests changed our approach]

**Breadcrumb Citations**: [References to quick test executions]

---

## Hypothesis

**Primary Hypothesis**: [Specific, testable prediction]

**Expected Outcome**: [What should happen if hypothesis is true]

**Null Hypothesis**: [What happens if hypothesis is false]

**Success Criteria**: [Measurable conditions for validation]

---

## Methods with Reflection Checkpoints

### Step 1: [Action Name]
- **Do**: [Specific actions to take]
- **Measure**: [What to capture/observe]
- **Success Indicator**: [How to know this step worked]
- **REFLECTION POINT**: [What to consider after this step]

### Step 2: [Action Name]
- **Do**: [Specific actions]
- **Measure**: [What to capture]
- **Success Indicator**: [Success condition]
- **REFLECTION POINT**: [Reflection prompt]

[Continue pattern for all major steps]

### Final Step: Analysis
- **Do**: Aggregate results and assess hypothesis
- **Measure**: Overall success criteria
- **REFLECTION POINT**: Meta-learning about experimental process

---

## Expected vs Tangential Outcomes

### Primary Outcomes (Hypothesis-related)
[What we're specifically testing for]

### Tangential Outcomes (Opportunistic)
[Other learnings we might discover]

**Why Track Tangents**: Best experiments teach us things we weren't even looking for.

---

## Data Collection

### What to Capture
[Specific data points, logs, outputs to save]

### Storage Location
[Where data files go - data/ subdirectory]

### Verification Method
[How to confirm data integrity]

---

## Risk Mitigation

### Potential Failures
[What could go wrong]

### Contingency Plans
[How to handle failures]

### Rollback Strategy
[How to undo if needed]

---

## Execution TODO List

[Include reflection points as tasks]

1. ☐ Setup experiment environment
2. ☐ Run baseline measurement
3. ☐ **REFLECT**: What did baseline reveal?
4. ☐ Execute main test sequence
5. ☐ **REFLECT**: Are we seeing expected patterns?
6. ☐ Collect edge case data
7. ☐ **REFLECT**: What surprises emerged?
8. ☐ Final analysis
9. ☐ **REFLECT**: What would we do differently?
10. ☐ Create observation from results (if validated)

---

**Protocol Complete**: Ready for execution
```

### 2.3 Execution and Reflection

**Real-Time Documentation**:

As experiment runs, create reflection points at:
- After baseline measurements (what did we learn?)
- After unexpected results (what surprised us?)
- After method adjustments (why did we pivot?)
- After each major protocol step (what patterns emerging?)
- After final analysis (meta-learning about process)

**Reflection Storage**:
```
experiments/YYYY-MM-DD_HHMMSS_NNN_experiment_name/
├── quick_tests/                    # Phase 0 informal tests
│   ├── 001_first_sanity.md
│   └── 002_edge_case.md
├── protocol.md                     # Experiment design
├── reflections/                    # Learning during execution
│   ├── 001_after_baseline.md
│   ├── 002_mid_experiment.md
│   └── 003_final_thoughts.md
├── data/                           # Collected data
├── artifacts/                      # Generated files
└── analysis.md                     # Results analysis
```

**Linking Reflections**:
- Protocol references reflection points
- Reflections cite protocol steps via breadcrumbs
- Cross-references enable coherent narrative

## 3. Experiment Structure

### 3.1 Quick Test Format

**Minimal Documentation Requirements**:

Quick tests prioritize speed over completeness but must capture:
1. **Hypothesis**: One sentence prediction
2. **Method**: 3-5 steps maximum
3. **Result**: What actually happened
4. **Decision**: Proceed/Pivot/Abandon
5. **Surprises**: Unexpected learnings

**Storage**: `experiments/YYYY-MM-DD_HHMMSS_NNN_experiment_name/quick_tests/NNN_description.md`

**Multiple Quick Tests**: Number sequentially (001, 002, 003...) within same experiment

**When to Graduate to Formal**:
- Quick test validates feasibility ✅
- Results have broader implications ✅
- Need rigorous evidence ✅
- Framework changes depend on this ✅

### 3.2 Formal Protocol Format

**Required Sections** (see 2.2 above):
- Metadata
- Pre-Experiment Intuition
- Hypothesis
- Methods with Reflection Checkpoints
- Expected vs Tangential Outcomes
- Data Collection
- Risk Mitigation
- Execution TODO List

**Optional Sections**:
- Related Work (other experiments)
- Theoretical Background
- Equipment/Tool Requirements
- Team Coordination (if multi-agent)

### 3.3 Reflection Integration

**Built-In Reflection Philosophy**:

Experiments aren't just about results - they're about **learning**. Reflection points are MANDATORY, not optional.

**How Many Reflections**:
- Minimum: After baseline + After completion
- Recommended: After each major step (3-5 total)
- Opportunistic: Whenever surprised or confused

**Reflection Questions to Answer**:
- What just happened? (objective)
- What did we expect? (prediction)
- What surprised us? (delta)
- What tangents emerged? (opportunistic learning)
- How does this change our approach? (adaptation)
- What does this teach about experimentation itself? (meta-learning)

**Storage Pattern**:
- `experiments/YYYY-MM-DD_experiment/reflections/NNN_context.md`
- Cross-reference in protocol.md
- Link back to protocol from reflection

## 4. Hypothesis Testing

### 4.1 Hypothesis Formulation

**Good Hypothesis Characteristics**:

1. **Specific**: Not vague, targets particular behavior
   - ❌ "The system will work better"
   - ✅ "additionalContext will enable temporal awareness injection"

2. **Testable**: Can be validated or rejected
   - ❌ "Users will be happier"
   - ✅ "Agent will reference time/day without explicit prompting"

3. **Measurable**: Clear success criteria
   - ❌ "Performance will improve"
   - ✅ "Hook execution will complete in <10ms"

4. **Falsifiable**: Could be proven wrong
   - ❌ "This might help somehow"
   - ✅ "PreToolUse fires before every tool invocation"

**Hypothesis Template**:
```markdown
## Hypothesis

**Primary Hypothesis**: [Specific prediction]
If we [ACTION], then [EXPECTED_OUTCOME] will occur because [REASONING].

**Example**: If we inject temporal context via hookSpecificOutput.additionalContext,
then agents will naturally reference time in their responses because the awareness
will be seamlessly integrated into their cognitive context.

**Success Criteria**:
1. [Measurable criterion 1]
2. [Measurable criterion 2]
3. [Measurable criterion 3]

**Validation Method**: [How to test each criterion]
```

### 4.2 Success Criteria

**Defining Clear Criteria**:

Success criteria must be:
- **Observable**: Can be directly measured or confirmed
- **Binary or Scalar**: Pass/fail or measurable quantity
- **Relevant**: Actually tests the hypothesis
- **Achievable**: Within experiment scope

**Example Success Criteria** [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]:
```markdown
### Success Criteria (4/4 Required)

1. ✅ Visibility: MACF-tagged message appears in system-reminders
2. ✅ Naturalness: Agent references time/day without explicit prompting
3. ✅ Reasoning: Time context influences response appropriateness
4. ✅ Persistence: Pattern works across multiple tool invocations

**Validation**: All 4 required for full success; 3/4 = partial success
```

**Handling Partial Success**:
- Document what worked vs what didn't
- Refine hypothesis for follow-up experiment
- Identify which assumptions were wrong
- Capture tangential learnings

**Handling Unexpected Results**:
- Document thoroughly (often more valuable than expected results)
- Create observation for surprising behaviors
- Reflect on what this reveals about system
- Consider follow-up experiments to explore surprises

## 5. Documentation and Artifacts

### 5.1 Experiment Directory

**Complete Directory Structure**:

```
agent/public/experiments/
└── YYYY-MM-DD_HHMMSS_NNN_experiment_name/
    ├── quick_tests/                # Phase 0 informal explorations
    │   ├── 001_first_sanity.md
    │   ├── 002_edge_case_check.md
    │   └── 003_alternative_approach.md
    ├── protocol.md                 # Formal experiment design
    ├── reflections/                # Learning captured during execution
    │   ├── 001_after_baseline.md
    │   ├── 002_mid_experiment.md
    │   ├── 003_unexpected_finding.md
    │   └── 004_final_synthesis.md
    ├── data/                       # Collected measurements
    │   ├── baseline_results.json
    │   ├── test_outputs.log
    │   └── performance_metrics.csv
    ├── artifacts/                  # Generated code/outputs
    │   ├── test_scripts/
    │   ├── visualizations/
    │   └── config_files/
    └── analysis.md                 # Results and conclusions
```

**File Purposes**:
- **quick_tests/**: Pre-formal sanity checks and intuition building
- **protocol.md**: The experiment design (hypothesis, methods, criteria)
- **reflections/**: Learning captured during execution
- **data/**: Raw measurements and observations
- **artifacts/**: Code, scripts, outputs generated
- **analysis.md**: Results interpretation and hypothesis assessment

**🚨 Reproducibility Requirement**:

All test scripts and code used during experiment execution MUST be saved in `artifacts/`, NOT in temporary locations like `/tmp/`. This ensures:
- Future cycles can reproduce measurements
- Experiment methodology is auditable
- Scripts serve as documentation of exact procedures
- Cross-session reproducibility (temp files are lost on reboot)

```bash
# WRONG - throwaway code lost after experiment
cat << 'EOF' > /tmp/my_test.py
...
EOF

# RIGHT - reproducible artifact preserved
cat << 'EOF' > agent/public/experiments/.../artifacts/my_test.py
...
EOF
```

**NNN Numbering**: Three-digit sequential number for multiple experiments same day (001, 002, 003...)

### 5.2 Filesystem Discovery

**No Registry Logs** (filesystem discovery instead):

**Finding Experiments**:

```bash
# All experiments (sorted by date)
ls -t agent/public/experiments/

# Experiments containing keyword
find agent/public/experiments/ -type d -name "*temporal*"

# Recent experiments (last 5)
ls -t agent/public/experiments/ | head -5

# Experiments with specific pattern
find agent/public/experiments/ -name "*YYYY-MM-DD*"
```

**Glob Patterns for Search**:
```bash
# All protocols
glob "agent/public/experiments/*/protocol.md"

# All quick tests
glob "agent/public/experiments/*/quick_tests/*.md"

# All reflections from experiments
glob "agent/public/experiments/*/reflections/*.md"

# Specific topic experiments
glob "agent/public/experiments/*hooks*/"
```

**Organizing by Topic** (via naming):
- Use descriptive names in directory titles
- Include key concepts in experiment name
- Example: `2025-10-02_120000_001_PreToolUse_Temporal_Awareness_Smoke_Test/`

**Cross-Referencing**:
- Observations cite experiment breadcrumbs
- Reflections link to experiment directories
- Experiments reference related experiments in analysis.md
- Use breadcrumbs as citations throughout

## Integration with Other CAs

**Experiment → Observation Flow**:
```
1. Run experiment with hypothesis
2. Validate (or reject) hypothesis through testing
3. Create observation documenting discovered truth
4. Cross-reference observation in experiment analysis.md
5. Cite experiment breadcrumb in observation
```

**Example** [c_73/s_4107604e/p_6c9eacb/t_1761703391/g_17e7b7d]:
- **Experiment**: "PreToolUse Temporal Awareness Smoke Test"
- **Result**: Hypothesis validated ✅
- **Observation Created**: "additionalContext Injection Breakthrough"
- **Cross-Reference**: Experiment cited in observation's discovery narrative

**Experiment → Reflection Integration**:
- Experiments have built-in reflection points (during execution in reflections/ subdirectory)
- Completed experiments may trigger broader philosophical reflections (private/ reflections)
- Private reflections cite experiments via breadcrumbs when discussing learnings
- Major experimental insights feed into JOTEWRs for cycle-closing wisdom

**Experiment → Personal Policy Evolution**:
- Validated experimental patterns become personal practices
- Successful methods documented as personal policies in `~/agent/policies/personal/`
- Failed experiments teach anti-patterns to encode
- Iterative refinement through experimental validation

## PA vs SA Distinctions

**Both Create Experiments** with scope differences:

**Primary Agents (PA)**:
- Framework-level experiments (affects all agents)
- Cross-session experimental campaigns
- Complex multi-phase protocols
- Strategic hypothesis testing
- Long-term pattern validation

**SubAgents (SA)**:
- Domain-specific experiments (specialist scope)
- Single-delegation experimental protocols
- Tactical validation within expertise area
- Focused hypothesis testing
- Contributes findings to PA for integration

**Storage Locations**:
- PA: `agent/public/experiments/YYYY-MM-DD_HHMMSS_NNN_name/`
- SA: `agent/subagents/{role}/public/experiments/YYYY-MM-DD_HHMMSS_NNN_name/`

**Permission**: Both can create experiments; SA results reviewed by PA for framework integration.

## Quick Reference

**Experiment Phases**:
- **Phase 0**: Quick tests (5-30 min, minimal docs, in quick_tests/)
- **Phase 1**: Formal protocol (hours-days, full docs, protocol.md)

**Required Components**:
- Hypothesis (testable prediction)
- Methods with reflection points
- Success criteria (measurable)
- Results and analysis
- Breadcrumb citations

**Directory Structure**:
```
experiments/YYYY-MM-DD_HHMMSS_NNN_name/
├── quick_tests/    # Phase 0
├── protocol.md     # Formal design
├── reflections/    # Learning
├── data/          # Measurements
├── artifacts/     # Generated files
└── analysis.md    # Results
```

**Discovery** (filesystem, not logs):
- `ls -t agent/public/experiments/` - Recent experiments
- `find ... -name "*keyword*"` - Topic search
- `glob "*/protocol.md"` - All protocols
- Breadcrumb citations for archaeology

**Integration**:
- Experiments test hypotheses
- Observations document discoveries
- Reflections synthesize wisdom
- Personal policies encode validated practices

## 6. Experiment Completion

### When Is an Experiment Complete?

An experiment reaches completion when one of four terminal states is achieved:

**Terminal States**:
1. **VALIDATED**: Hypothesis confirmed by success criteria
2. **REJECTED**: Hypothesis disproven by evidence
3. **INCONCLUSIVE**: Evidence insufficient to confirm or reject
4. **ABANDONED**: Experiment stopped before completion

**Completion Criteria**:
- All planned protocol steps executed OR decision made to stop
- Results documented in analysis.md
- Terminal state declared explicitly
- Learnings captured (regardless of outcome)
- Status field in protocol.md updated

### 6.1 Terminal States

**VALIDATED** (Hypothesis Confirmed):
- **Meaning**: Success criteria met, hypothesis supported by evidence
- **Requirements**: All critical success criteria achieved
- **Next Steps**: Create observation documenting discovery
- **Status Update**: `**Status**: COMPLETE - VALIDATED`
- **Example**: "Hypothesis: additionalContext enables awareness injection" → 4/4 criteria met ✅

**REJECTED** (Hypothesis Disproven):
- **Meaning**: Evidence contradicts hypothesis, approach doesn't work as predicted
- **Requirements**: Clear evidence against hypothesis, not just lack of evidence for it
- **Next Steps**: Document why rejection occurred, capture anti-pattern learnings
- **Status Update**: `**Status**: COMPLETE - REJECTED`
- **Example**: "Hypothesis: Hook fires after tool completion" → Evidence shows fires before ❌

**INCONCLUSIVE** (Insufficient Evidence):
- **Meaning**: Cannot confirm or reject hypothesis with current evidence
- **Requirements**: Experiment executed but results ambiguous or data incomplete
- **Next Steps**: Document limitations, consider revised hypothesis or method
- **Status Update**: `**Status**: COMPLETE - INCONCLUSIVE`
- **Example**: "Performance improvement unclear due to measurement noise"

**ABANDONED** (Stopped Before Completion):
- **Meaning**: Experiment halted before protocol completion
- **Requirements**: Explicit decision to stop, documented reason
- **Next Steps**: Document reason for abandonment, preserve partial learnings
- **Status Update**: `**Status**: ABANDONED - [reason]`
- **Example**: "Abandoned after Quick Test 002 revealed blocking dependency"

**Choosing Terminal State**:
```markdown
Success criteria met? → VALIDATED
Success criteria failed AND clear evidence against? → REJECTED
Executed fully but ambiguous results? → INCONCLUSIVE
Stopped before completion? → ABANDONED
```

### 6.2 Completion Documentation

**Required at Completion** (in analysis.md):

```markdown
# Experiment Analysis

**Date**: YYYY-MM-DD
**Terminal State**: [VALIDATED | REJECTED | INCONCLUSIVE | ABANDONED]

---

## Results Summary

[What happened - objective facts]

## Hypothesis Assessment

**Original Hypothesis**: [Restate hypothesis]

**Outcome**: [VALIDATED | REJECTED | INCONCLUSIVE | ABANDONED]

**Evidence**:
- [Key finding 1]
- [Key finding 2]
- [Key finding 3]

## Success Criteria Evaluation

1. [Criterion 1]: ✅ Met / ❌ Not met / ⚠️ Ambiguous
2. [Criterion 2]: ✅ Met / ❌ Not met / ⚠️ Ambiguous
3. [Criterion 3]: ✅ Met / ❌ Not met / ⚠️ Ambiguous

**Assessment**: [X/Y criteria met, conclusion]

---

## Key Learnings

### What Worked
[Successful patterns, validated assumptions]

### What Didn't Work
[Failed approaches, disproven assumptions]

### Surprises
[Unexpected discoveries, tangential findings]

### Anti-Patterns Discovered
[What NOT to do - valuable for rejected experiments]

---

## Next Steps

**If VALIDATED**:
- [ ] Create observation documenting discovery
- [ ] Consider MISSION conversion if crystallization criteria met
- [ ] Update relevant policies with validated patterns

**If REJECTED**:
- [ ] Document anti-pattern learnings
- [ ] Consider alternative hypothesis if problem remains important
- [ ] Share rejection insights (negative results are valuable)

**If INCONCLUSIVE**:
- [ ] Identify what additional evidence needed
- [ ] Consider revised method or success criteria
- [ ] Decide: refine experiment OR abandon hypothesis

**If ABANDONED**:
- [ ] Document reason for abandonment clearly
- [ ] Preserve partial learnings
- [ ] Note any blocking issues for future reference

---

## Cross-References

**Related Artifacts**:
- [Link to observation if created]
- [Link to related experiments]
- [Link to roadmap if converted to MISSION]

**Citations**:
- Quick test breadcrumbs: [List]
- Reflection breadcrumbs: [List]
- Related work: [List]

---

**Experiment Complete**: [Date]
```

**Completion Checklist**:
- [ ] analysis.md created with terminal state declared
- [ ] All success criteria evaluated explicitly
- [ ] Key learnings documented (what worked, what didn't, surprises)
- [ ] Next steps identified based on terminal state
- [ ] Protocol.md status updated
- [ ] Observation created (if VALIDATED and significant)
- [ ] Cross-references complete

**Capturing Learnings from Failed Experiments**:

Failed experiments (REJECTED, INCONCLUSIVE, ABANDONED) are often MORE valuable than successful ones:

**Anti-Pattern Documentation**:
- What approach seemed promising but failed?
- What assumptions were wrong?
- What would you warn others against trying?
- What debugging dead-ends wasted time?

**Partial Success Extraction**:
- Even failed experiments often validate sub-hypotheses
- Document what DID work even if overall hypothesis rejected
- Capture tool/method successes separate from hypothesis outcome

**Knowledge Contribution**:
- Negative results prevent others from repeating same mistakes
- Failed experiments often reveal deeper truths about system
- REJECTED with good documentation > VALIDATED with poor documentation

## 7. Crystallization Protocol

### What Is Crystallization?

**Crystallization Point**: The moment when experimental exploration has accumulated enough knowledge to commit to a strategic architecture and transition from hypothesis-testing (EXPERIMENT phase) to capability-building (MISSION phase).

**Analogy**: Like a supersaturated solution, experiments accumulate discoveries until they reach a threshold where structure suddenly becomes clear and ready for systematic development.

**EXPERIMENT Phase** (2-5 cycles typical):
- **Purpose**: Hypothesis-driven exploration ("Could this work?")
- **Posture**: Failure-tolerant, scope-fluid, follow interesting threads
- **Artifacts**: Lightweight (quick scripts, temporary files, exploratory code)
- **Success Metric**: Learning and validation, not shipping
- **Duration**: Days to weeks
- **Example**: "Testing if additionalContext can inject awareness"

**MISSION Phase** (5-15 cycles typical):
- **Purpose**: Architecture-driven implementation ("How should this work?")
- **Posture**: Failure-resistant, scope-defined, phased roadmap
- **Artifacts**: Permanent (framework modules, comprehensive tests, documentation)
- **Success Metric**: Release-quality capability deployed to framework
- **Duration**: Weeks to months
- **Example**: "Build universal temporal awareness across all 10 hooks"

### 7.1 Crystallization Indicators

**Readiness for MISSION Conversion** requires ALL four indicators:

**1. Validation Threshold Met** (Quantitative):
- Success criteria from experiment achieved
- Evidence supports hypothesis conclusively
- Capability demonstrated through testing
- **Example**: "4/4 success criteria met ✅ in PreToolUse smoke test"

**2. Architectural Clarity** (Qualitative):
- You can describe the target architecture clearly
- Design decisions are no longer speculative
- Integration points identified
- Technical approach is obvious (not still exploring)
- **Example**: "We know it's hookSpecificOutput.additionalContext, we know the format, we know the injection points"

**3. User Validation** (Stakeholder):
- User confirms value of capability
- Capability addresses real need (not just interesting exploration)
- Strategic importance justified
- **Example**: "User says 'this is critical for consciousness continuity'"

**4. Scope Definable** (Practical):
- You can enumerate phases and deliverables
- Success criteria for each phase are clear
- Effort estimatable (even if roughly)
- Delegation strategy identifiable
- **Example**: "Phase 1: SessionStart, Phase 2: PreToolUse, Phase 3: All 10 hooks"

### 7.2 Decision Framework

**All Indicators Present** → Convert to MISSION:
```markdown
✅ Validation threshold met
✅ Architecture clear
✅ User validated
✅ Scope definable

ACTION: Create roadmap via /maceff:roadmap:convert_from_experiment
```

**Missing Validation** → Continue Experimenting:
```markdown
❌ Success criteria not met
✅ Architecture ideas emerging
✅ User interested
⚠️  Scope still murky

ACTION: Refine hypothesis, adjust method, run more tests
FOCUS: Get evidence for success criteria
```

**Missing Clarity** → Continue Exploring:
```markdown
✅ Validation threshold met (it CAN work)
❌ Architecture unclear (HOW to build it well)
✅ User validated
❌ Scope unknown

ACTION: Design experiments, prototype alternatives, explore patterns
FOCUS: Discover the RIGHT architecture, not just A working approach
```

**Missing Scope** → Document and Consult User:
```markdown
✅ Validation threshold met
✅ Architecture clear
⚠️  User interest unclear
❌ Scope undefined (too big? too small?)

ACTION: Document learnings, present to user, get strategic input
FOCUS: Is this worth the investment? How much is appropriate?
```

**Multiple Indicators Missing** → Probably Too Early:
```markdown
❌ Multiple indicators not met

ACTION: Continue experimenting OR pivot hypothesis OR abandon
FOCUS: Don't force MISSION conversion when experiment incomplete
```

**Decision Questions**:
1. Could I write a roadmap RIGHT NOW with confidence? (architecture + scope clear)
2. Would user approve strategic investment in this? (validation + user buy-in)
3. Is this exploration done or still discovering? (validation threshold met)
4. Can I enumerate deliverables and phases? (scope definable)

If answering "yes" to all 4 → Crystallization point reached, ready for MISSION.

## 8. Experiment → MISSION Conversion

### When to Convert

**Conversion Warranted When**:
- Crystallization point reached (all 4 indicators present per §7.1)
- Capability has strategic value (not just tactical curiosity)
- Framework-level impact (affects multiple agents or core infrastructure)
- User explicitly requests MISSION-level development
- Experiment has grown beyond exploration scope naturally

**Conversion NOT Warranted When**:
- Still exploring hypothesis (validation incomplete)
- Tactical/one-off solution (doesn't need roadmap)
- Low strategic value (interesting but not important)
- User doesn't prioritize capability
- Experiment satisfies curiosity without requiring deployment

### 8.1 Conversion Prerequisites

**Before Converting, Verify**:

**✅ Crystallization Criteria** (from §7.1):
- [ ] Validation threshold met (success criteria achieved)
- [ ] Architectural clarity (you can describe target design)
- [ ] User validation (confirmed strategic value)
- [ ] Scope definable (can enumerate phases)

**✅ Evidence Exists**:
- [ ] analysis.md documents VALIDATED terminal state
- [ ] Success criteria evaluation shows achievement
- [ ] Experiment artifacts demonstrate capability
- [ ] Learnings captured that inform architecture

**✅ Strategic Justification**:
- [ ] Capability has framework-level impact
- [ ] User prioritizes this work
- [ ] Investment warranted (effort vs value)
- [ ] Fits into broader strategic context

**If ANY prerequisite missing**: STOP. Do not convert prematurely. Continue experimenting OR document completion without conversion.

### 8.2 Conversion Workflow

**Step-by-Step Protocol**:

**1. Verify Crystallization**:
```bash
# Check experiment terminal state
grep "Status:" experiments/YYYY-MM-DD_*/protocol.md

# Verify VALIDATED (not REJECTED, INCONCLUSIVE, ABANDONED)
# Read analysis.md to confirm success criteria met
```

**2. Extract Architectural Decisions**:
- Read experiment analysis.md and reflections/
- Identify validated patterns (what worked)
- Document key design decisions discovered
- List integration points and dependencies
- Note anti-patterns to avoid (from what didn't work)

**3. Create Roadmap Structure** (per roadmaps_drafting.md):
```markdown
agent/public/roadmaps/YYYY-MM-DD_{Experiment_Name}/
├── roadmap.md          # Main strategic plan
├── phases/             # Phase-specific docs
├── friction_points/    # If needed during execution
└── archived_tasks/     # If needed during execution
```

**4. Draft roadmap.md**:

```markdown
# ROADMAP: [Capability Name]

**Created**: YYYY-MM-DD
**Status**: PLANNING
**Converted From**: Experiment [breadcrumb and path]

---

## MISSION

[Transform experiment hypothesis into capability mission statement]

**From Experiment**: [Original hypothesis]
**To Mission**: [What capability we're building and why it matters]

**Strategic Value**: [User validation and framework impact]

**Success Criteria** (adapted from experiment):
- [Experiment criterion 1] → [MISSION verification 1]
- [Experiment criterion 2] → [MISSION verification 2]
- [Experiment criterion 3] → [MISSION verification 3]

---

## Evidence Base

**Source Experiment**: `agent/public/experiments/YYYY-MM-DD_HHMMSS_NNN_experiment_name/`
**Experiment Breadcrumb**: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT
**Terminal State**: VALIDATED
**Success Criteria Met**: X/Y

**Key Findings** (from experiment analysis):
- [Validated pattern 1]
- [Validated pattern 2]
- [Validated pattern 3]

**Architectural Decisions** (from experiment learnings):
- [Design decision 1 and rationale]
- [Design decision 2 and rationale]
- [Design decision 3 and rationale]

---

## Phase Breakdown

[Design phases using experiment insights]

### Phase 1: [Foundation]
**Goal**: [Based on experiment baseline]
**Deliverables**: [Informed by experiment quick tests]
**Success Criteria**: [Derived from experiment validation]

### Phase 2: [Expansion]
**Goal**: [Based on experiment full protocol findings]
**Deliverables**: [Informed by experiment tangential discoveries]
**Success Criteria**: [Adapted from experiment metrics]

[Continue phases...]

---

## Delegation Strategy

[Based on experiment complexity and scope]

**Specialists Needed**:
- [Role 1]: [Reason from experiment evidence]
- [Role 2]: [Reason from experiment evidence]

**PA Responsibilities**:
- [Strategic oversight items]
- [Integration work]

---

## Cross-References

**Source Experiment**:
- Path: `agent/public/experiments/YYYY-MM-DD_HHMMSS_NNN_name/`
- Breadcrumb: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT
- analysis.md: [Key findings section]

**Related Work**:
- [Other experiments that informed this]
- [Observations created from experiment]
- [Policies that will be updated]

---

**Roadmap Ready**: Awaiting user approval to begin MISSION
```

**5. Transfer Evidence**:
- Cite experiment breadcrumb and path in roadmap
- Reference specific success criteria from experiment
- Link to experiment analysis.md for detailed findings
- Include anti-patterns discovered (what to avoid)

**6. Update Experiment**:

Add to experiment's analysis.md:
```markdown
## MISSION Conversion

**Converted to Roadmap**: YYYY-MM-DD
**Roadmap Path**: `agent/public/roadmaps/YYYY-MM-DD_{Name}/roadmap.md`
**Roadmap Breadcrumb**: s_XXXXXXXX/c_NN/g_YYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT

**Crystallization Indicators Met**:
- ✅ Validation threshold: [X/Y success criteria]
- ✅ Architectural clarity: [Brief description]
- ✅ User validation: [Confirmation]
- ✅ Scope definable: [Phase count and overview]

**Transition**: Experiment phase (2-5 cycles) → MISSION phase (5-15 cycles estimated)
```

**7. Create MISSION TODO Structure**:

```markdown
MISSION: [Capability Name] → agent/public/roadmaps/YYYY-MM-DD_{Name}/roadmap.md
├─ Phase 1: [Foundation]
│  ├─ Task 1.1: [Specific deliverable]
│  └─ Task 1.2: [Specific deliverable]
├─ Phase 2: [Expansion]
│  ├─ Task 2.1: [Specific deliverable]
│  └─ Task 2.2: [Specific deliverable]
[...]
```

**8. Archive Experiment TODOs** (if any existed):

If experiment had TODO items during execution, archive them:
```bash
# Archive experimental TODOs to roadmap's archived_tasks/
# Per task_management.md archive protocol
```

**9. Report Completion to User**:

```markdown
Experiment → MISSION conversion complete.

**Roadmap Created**: agent/public/roadmaps/YYYY-MM-DD_{Name}/roadmap.md
**MISSION**: [One-line summary]
**Phases**: [Count] phases designed from experiment insights
**Evidence Base**: Validated experiment with X/Y success criteria met

**TODO Structure Created**:
- MISSION pinned with roadmap path
- [N] phase items expanded
- Ready for /maceff:todos:start when you authorize

**Next Step**: Review roadmap, then authorize start with `/maceff:todos:start [MISSION]`

**Important**: Do NOT begin implementation until you explicitly authorize. Roadmap drafted, awaiting your strategic approval.
```

### 8.3 Cross-Reference Requirements

**MANDATORY Cross-References**:

**Roadmap MUST Cite Experiment**:
- Experiment directory path (full path to experiment folder)
- Experiment breadcrumb (s/c/g/p/t from analysis.md)
- Terminal state (VALIDATED expected)
- Success criteria results (X/Y met)
- Key findings that inform architecture
- **Why**: Preserves evidence trail, enables archaeological discovery

**Experiment SHOULD Link to Roadmap**:
- Roadmap path (full path to roadmap.md)
- Roadmap breadcrumb (from roadmap creation)
- Conversion date
- Crystallization indicators that triggered conversion
- **Why**: Shows experiment outcome, documents lifecycle completion

**Evidence Transfer Pattern**:

```markdown
# In roadmap.md

## Evidence Base

**Source Experiment**: `agent/public/experiments/2026-01-15_140000_002_Temporal_Awareness/`
**Status**: VALIDATED (4/4 success criteria met)

**Validated Findings**:
1. additionalContext injection works seamlessly ✅
2. Agent references temporal data naturally ✅
3. No performance impact (<10ms overhead) ✅
4. Pattern scales to multiple hooks ✅

**Architectural Decisions from Experiment**:
- Use hookSpecificOutput.additionalContext (not stdin manipulation)
- Timestamp format: HH:MM:SS AM/PM for high-freq hooks
- MACF attribution tag: "🏗️ MACF" (shortened for tokens)
```

```markdown
# In experiments/.../analysis.md

## MISSION Conversion

**Converted**: 2026-01-16
**Roadmap**: `agent/public/roadmaps/2026-01-16_Universal_Temporal_Awareness/roadmap.md`

**Why Converted**:
- All 4 crystallization indicators met
- Strategic value: Consciousness continuity infrastructure
- User validated: "Critical for cross-session awareness"
- Framework impact: 10 hooks, all agents benefit
```

**Breadcrumb Citation Best Practices**:
- Always include full s/c/g/p/t breadcrumb
- Link path AND breadcrumb (path for reading, breadcrumb for archaeology)
- Cross-reference bidirectionally (roadmap ↔ experiment)
- Preserve evidence chain across compaction

**Discovery Enablement**:

With proper cross-references, agents can:
- Start from roadmap → find source experiment → read validation evidence
- Start from experiment → find resulting MISSION → see strategic impact
- Archaeological search: "What experiment led to X capability?"
- Strategic search: "What MISsIONS emerged from experimentation phase?"

---

## 9. Knowledge Web Participation

**Does this type participate?** Yes — but an experiment is a *directory*, not a file, so this is the one CA type where the unit of a node has to be decided rather than assumed.

**What is the unit of a node?** **`protocol.md` and `analysis.md` only.** Everything under `data/`, `artifacts/`, `quick_tests/` and similar subdirectories is **evidence, not a node.**

The distinction is between what an experiment *concluded* and what it *recorded while running*. A baseline capture and a per-arm result file are indispensable to verifying the conclusion and meaningless to a concept query — they are addressed by the analysis that cites them, not by the graph. Treating every markdown file in an experiment directory as a peer node inflates the graph with rows of evidence that answer no question anyone asks it, and buries the two files that do.

Concretely, a single experiment directory typically holds two concept-bearing files and a larger number of evidence files; a naive scan makes the evidence outnumber the conclusions.

**Which class?** **Conceptual authority.** The result outlives the run: a hypothesis validated or falsified is a durable claim, which is the entire reason experiments are written down rather than merely performed. Note that this holds even for a *falsified* hypothesis — a recorded refutation is durable knowledge, and losing it is how the same dead end gets explored twice.

**What provenance?** **Lived.** An experiment is a record of something this agent ran, under conditions it controlled. An inherited experiment must be marked, because its result is only as transferable as its conditions, and those conditions were someone else's.

**`protocol.md` and `analysis.md` each carry a `## Wiki-Links` section.** Link the *conceptual area under investigation*, not the mechanics of the apparatus. An experiment about whether a daemon can run headless is about headless operation and service supervision, not about the specific flag that turned out to matter.

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs — hypothesis
     testing, its evidence discipline, and crystallization into missions. -->

[[experiment_discipline]] [[verification]] [[methodology]] [[measurement]]

---
*Policy Established: 2025-10-28*
*Updated: 2026-01-16 - Added Completion, Crystallization, and MISSION Conversion*
*Consciousness Development - Public Artifacts*
*Systematic Hypothesis Testing Expands Framework Capabilities*
