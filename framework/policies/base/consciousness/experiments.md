# EXPERIMENTS

## Meta-Policy: Policy Classification
- **Tier**: RECOMMENDED
- **Category**: Consciousness Development - Public Artifacts
- **Version**: 1.0.0
- **Dependencies**: policy_awareness, observations, reflections
- **Authority**: MacEff Framework
- **Status**: ACTIVE

## Policy Statement
Agents conduct structured experiments with clear hypotheses, methods, and success criteria to validate assumptions, test new patterns, and systematically expand framework capabilities through empirical investigation.

## CEP Navigation Guide

1 Understanding Experiments
- What is an experiment?
- How do experiments differ from observations?
- When should I run an experiment?
- What makes a good experiment?

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

=== CEP_NAV_BOUNDARY ===

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

### 1.1 Experiment vs Observation vs Report

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
- **Example**: "Manny Bootstrap: 73 minutes from zero to operational"

**Relationship Between Artifacts**:
```
Experiment (tests hypothesis)
    ↓ generates
Observation (documents discovery)
    ↓ informs
Personal Policy (encodes practice)
    ↓ contributes to
Report (summarizes project outcomes)
```

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
**Breadcrumb**: c_XX/s_YYYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT/g_GGGGGGG
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
**Breadcrumb**: c_XX/s_YYYYYYYY/p_ZZZZZZZ/t_TTTTTTTTTT/g_GGGGGGG
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

---
*Policy Established: 2025-10-28*
*Consciousness Development - Public Artifacts*
*Systematic Hypothesis Testing Expands Framework Capabilities*
