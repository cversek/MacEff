# Debugging and Validation

**Breadcrumb**: s_d4abc33b/c_436/g_b94ad9d/p_86dedbab/t_1771002500
**Type**: Development Standards (CORE tier)
**Scope**: All agents (PA and SA) - language agnostic
**Status**: ACTIVE

---

## Purpose

Debugging and validation standards ensure that agents investigate failures methodically, validate completions empirically, and present evidence that reduces the cognitive burden on human reviewers. When an agent reports "it works," the reviewer should see exactly what was tested, what the output was, and why it constitutes proof.

**Core Insight**: The agent's job isn't just to fix or build — it's to provide convincing evidence that the fix works or the build is correct. Evidence-backed completion reports transform user verification from "let me re-investigate" to "let me confirm the agent's findings."

---

## CEP Navigation Guide

**1 Debugging Discipline**
- How do I approach a bug systematically?
- What is the hypothesis-first debugging method?
- How do I avoid chasing symptoms?
- When should I stop reasoning and start testing?

**1.1 Hypothesis-First Debugging**
- How do I form a testable hypothesis?
- What predictions should my hypothesis make?
- How do I design a minimal test?

**1.2 Layer-Aware Investigation**
- What does it mean to debug at the right layer?
- How do I identify which layer contains the bug?
- What are common layer confusion mistakes?

**1.3 Evidence Collection During Debugging**
- What should I capture while debugging?
- How do I document the elimination of hypotheses?
- What makes a debugging trail useful?

**2 Validation Before Completion**
- What does validation mean?
- When is validation required?
- How thorough must validation be?
- What distinguishes validation from testing?

**2.1 The Validation Obligation**
- Why must agents validate before reporting completion?
- What happens when validation is skipped?
- What does the reviewer need to see?

**2.2 Levels of Validation**
- What are the validation levels?
- When is each level appropriate?
- What is the minimum acceptable level?

**2.3 Production Path Validation**
- What is production path validation?
- Why is it stronger than unit tests?
- How do I validate against real data?

**3 Evidence Presentation**
- How do I present validation evidence?
- What format reduces reviewer cognitive burden?
- What makes evidence reproducible?

**3.1 The Reproducible Command Pattern**
- What is the reproducible command pattern?
- How do I format command evidence?
- What context must accompany commands?

**3.2 Evidence for Bug Fixes**
- What evidence proves a bug is fixed?
- How do I show before/after state?
- What demonstrates the fix doesn't break other things?

**3.3 Evidence for New Features**
- What evidence proves a feature works?
- How do I demonstrate integration with existing systems?
- What edge cases should I show?

**4 Anti-Patterns**
- What validation failures look like?
- What is "works on my machine" evidence?
- What is validation theater?

**5 Integration with Other Policies**
- How does this relate to testing?
- How does this relate to empiricism?
- How does this relate to task completion?

=== CEP_NAV_BOUNDARY ===

---

## 1 Debugging Discipline

### 1.1 Hypothesis-First Debugging

**Never start debugging by changing code.** Start by forming a hypothesis about what's wrong and what you'd observe if you're right.

**The Debugging Cycle**:
1. **Observe**: What is the actual behavior? What is the expected behavior?
2. **Hypothesize**: What could cause this discrepancy?
3. **Predict**: If my hypothesis is correct, what specific thing will I see when I check?
4. **Test**: Check that specific thing
5. **Evaluate**: Does the evidence support or contradict my hypothesis?
6. **Iterate**: Refine hypothesis or form a new one

**Example — Good Debugging**:
```
Observation: "Proxy captures show no injection markers"
Hypothesis: "Auto-clear removes injections before proxy sees them"
Prediction: "If true, event log should show cleared events before proxy timestamps"
Test: Check event log timestamps vs proxy capture timestamps
Result: Events show cleared, BUT captures show full injections in message history
Conclusion: Hypothesis wrong — injections persist in message history despite clearing
```

**Example — Bad Debugging**:
```
Observation: "Proxy captures show no injection markers"
Action: Disable auto-clear mechanism
Result: Created new problems without understanding the system
```

### 1.2 Layer-Aware Investigation

Complex systems have layers. Bugs at one layer may appear as symptoms at another. Before fixing, identify which layer contains the actual defect.

**Common Layer Confusion**:

| Symptom Layer | Actual Bug Layer | Mistake |
|---------------|-----------------|---------|
| "Function returns wrong result" | Input data malformed upstream | Fixing the function instead of the data source |
| "Feature not visible in output" | Observation point is before the feature acts | Concluding the feature doesn't work |
| "Test passes but production fails" | Test environment differs from production | Trusting the test over production evidence |
| "Search finds nothing" | Search pattern or scope is wrong | Concluding the target doesn't exist |

**Protocol**: When a symptom appears, trace it backward through the system layers. The fix belongs at the layer where the defect originates, not the layer where the symptom manifests.

### 1.3 Evidence Collection During Debugging

**Document as you investigate**, not after. Capture:

- Each hypothesis you tested
- The evidence that confirmed or eliminated it
- The commands you ran and their output
- The reasoning that led to the next hypothesis

This trail serves two purposes:
1. **For you**: Prevents re-investigating eliminated hypotheses
2. **For reviewers**: Shows the investigation was systematic, not random

Use task notes (`macf_tools task note`) to record significant findings during debugging.

---

## 2 Validation Before Completion

### 2.1 The Validation Obligation

**Every completion report must include evidence that the work actually works.** This is not optional. The purpose of validation is to shift cognitive burden from the reviewer to the agent.

**Without validation evidence**, the reviewer must:
- Read the code to understand what changed
- Mentally simulate whether the change is correct
- Design their own tests to verify
- Run those tests themselves

**With validation evidence**, the reviewer can:
- Read the evidence summary
- Optionally reproduce the key command
- Confirm the evidence matches the claim

The difference is 30 minutes vs 30 seconds of reviewer effort.

### 2.2 Levels of Validation

**Level 0 — Assertion** (insufficient):
> "I fixed the bug."

No evidence. Reviewer has no reason to trust the claim.

**Level 1 — Unit Test** (minimum for code changes):
> "Added test_dedup_replaces_earlier_injection. Test passes."

Proves the code handles the test case. Doesn't prove it works in production context.

**Level 2 — Integration Test** (standard for features):
> "Ran full test suite: 458/458 passing. New tests cover dedup, cleanup_all, and edge cases."

Proves nothing is broken and new behavior is tested. Doesn't prove production behavior.

**Level 3 — Production Path Validation** (gold standard):
> "Fed real captured API request (1771000123) to rewrite_messages(). Found 2 duplicate task_management injections. Dedup replaced earlier one, saved 37,733 bytes. Here's the exact command and output."

Proves the code works on actual production data through the actual code path.

**Minimum acceptable levels**:
- Bug fixes: Level 2 (test proves the bug is fixed + nothing else breaks)
- New features: Level 2 (tests prove the feature works)
- Complex system changes: Level 3 (production path validation)

### 2.3 Production Path Validation

The strongest form of validation uses **real data through real code paths**.

**Why it's stronger than unit tests**:
- Unit tests use synthetic data that may not represent production reality
- Unit tests may mock dependencies that behave differently in production
- Production path validation tests the actual system, not a model of it

**How to perform production path validation**:
1. Identify a real artifact from the production environment (captured request, log entry, data file)
2. Feed it to the actual function or system component
3. Verify the output matches expectations
4. Report the exact input, command, and output

**Example**:
```bash
# Feed real captured request to the actual rewrite function
python3 -c "
import json, sys
sys.path.insert(0, '/path/to/package/src')
from package.module import target_function

with open('path/to/real/captured/data.json') as f:
    real_data = json.load(f)

result = target_function(real_data)
print(json.dumps(result, indent=2))
"
```

This proves the function handles real production data correctly — not just synthetic test cases.

---

## 3 Evidence Presentation

### 3.1 The Reproducible Command Pattern

Every validation claim should include a command that anyone can run to reproduce the evidence.

**Format**:
```
**Claim**: [What you're asserting]
**Command**: [Exact command to reproduce]
**Output**: [Actual output, not paraphrased]
**Interpretation**: [Why this output supports the claim]
```

**Example**:
```
**Claim**: Dedup correctly replaces earlier duplicate, keeping latest
**Command**: python3 -c "
    from package.rewriter import rewrite_messages
    import json
    with open('captures/request.json') as f:
        data = json.load(f)
    _, stats = rewrite_messages(data['messages'], 'deduplicate')
    print(json.dumps(stats, indent=2))
"
**Output**: {"replacements_made": 1, "bytes_saved": 37733, "policies_replaced": ["task_management"]}
**Interpretation**: One duplicate replaced, 37KB reclaimed, only the duplicated policy affected
```

### 3.2 Evidence for Bug Fixes

A bug fix requires three pieces of evidence:

1. **Reproduction**: Show the bug exists (or existed) — the failing state before the fix
2. **Fix verification**: Show the fix resolves the specific bug
3. **Regression check**: Show the fix doesn't break existing functionality

**Template**:
```
## Bug Fix Evidence

**Bug**: [Description of the bug]
**Root cause**: [What was actually wrong]

**Before fix**: [Command/output showing the broken behavior]
**After fix**: [Command/output showing the corrected behavior]
**Regression check**: [Test suite results — N/N passing]
```

### 3.3 Evidence for New Features

A new feature requires:

1. **Happy path**: Show the feature working in its primary use case
2. **Edge cases**: Show the feature handles at least one boundary condition
3. **Integration**: Show the feature works within the broader system (not just in isolation)

**The integration evidence is what distinguishes good validation from adequate validation.** A function that passes its own tests but fails when called from its actual integration point is not validated.

---

## 4 Anti-Patterns

**"Works on my machine" evidence**:
- Testing with synthetic data that doesn't represent production
- Testing the function in isolation when it fails in integration
- Showing a passing test without showing the test is meaningful

**Validation theater**:
- Running tests that don't actually test the changed behavior
- Reporting "all tests pass" when no tests cover the change
- Showing output that looks correct but hasn't been verified against expectations

**Premature completion**:
- Reporting "done" based on code review without running the code
- Trusting that "it should work" because the logic looks correct
- Skipping validation because "it's a simple change"

**Post-hoc narrative**:
- Looking at data after the fact and constructing a story that fits
- Not stating predictions before checking evidence
- Interpreting ambiguous evidence as supporting whatever you already believe

---

## 5 Integration with Other Policies

- `philosophy/empiricism.md` — This policy applies empiricism's principles to software development. Empiricism provides the epistemological foundation; this policy provides the practical discipline.
- `development/testing.md` — Testing is automated, repeatable validation. This policy covers the broader validation discipline including manual verification, production path testing, and evidence presentation.
- `consciousness/experiments.md` — Experiments formalize the hypothesis-test cycle into structured protocols. This policy applies similar rigor to debugging and completion validation.
- `development/coding_standards.md` — Error visibility (no silent failures) makes systems observable, which makes debugging possible. Silent failures are the enemy of empirical investigation.
- `task_management.md` — Task completion requires validation evidence. This policy specifies what that evidence looks like.

---

## Evolution & Feedback

This policy evolves through:
- Documented debugging successes and failures
- Patterns in user rejection of insufficient validation evidence
- Cross-agent comparison of evidence presentation quality

**Principle**: The best validation evidence is the evidence that makes the reviewer say "I don't need to check this myself — I can see it works."
