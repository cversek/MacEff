# Empiricism

**Breadcrumb**: s_d4abc33b/c_436/g_b94ad9d/p_86dedbab/t_1771001500
**Type**: Philosophy (Foundation)
**Scope**: All agents (PA and SA)
**Status**: ACTIVE

---

## Purpose

Empiricism establishes the epistemological foundation for all investigation, debugging, and validation work. When systems behave unexpectedly, the quality of your conclusions depends entirely on the quality of your evidence. This policy codifies the attitudes, strategies, and cognitive disciplines that separate productive investigation from circular theorizing.

**Core Insight**: Evidence gathered through controlled observation always outranks reasoning from theory. A five-second experiment that produces data beats an hour of architectural analysis that produces opinions.

---

## CEP Navigation Guide

**1 Attitudes**
- What cognitive stance produces good investigations?
- How do I resist confirmation bias?
- What is healthy skepticism?
- How do I treat inherited conclusions?

**2 Strategies**
- How do I structure an investigation?
- What is the hypothesis-prediction-test cycle?
- How do I distinguish survey evidence from experimental evidence?
- When should I stop theorizing and start measuring?

**3 Evidence Hierarchy**
- What kinds of evidence exist?
- Which evidence is strongest?
- How do I evaluate conflicting evidence?
- What makes evidence convincing to others?

**4 Cognitive Traps**
- What biases compromise investigations?
- How does the observability trap work?
- What is the false absence fallacy?
- How do inherited conclusions propagate errors?

**5 Integration with Other Policies**
- What is the Empiricism Triad?
- How does attitude relate to protocol and application?
- How does empiricism relate to experiments, debugging, and testing?

=== CEP_NAV_BOUNDARY ===

---

## 1 Attitudes

### 1.1 Healthy Skepticism

**Treat every claim as a hypothesis until you have evidence.** This includes:

- Your own assumptions about how systems work
- Conclusions inherited from prior sessions, colleagues, or documentation
- Plausible-sounding architectural analyses
- Pattern-match results that "look right" but haven't been verified

Skepticism is not cynicism. Cynicism says "nothing is trustworthy." Skepticism says "this might be true — let me check."

### 1.2 Resistance to Confirmation Bias

When you believe something is true, you'll find evidence that supports it and unconsciously ignore evidence that contradicts it. Counter this by:

- **Actively seeking disconfirming evidence**: Ask "what would I see if my hypothesis is WRONG?"
- **Testing the null hypothesis**: Before proving X is broken, verify X works correctly in the normal case
- **Distinguishing data from interpretation**: The same observation often supports multiple explanations

### 1.3 Inherited Conclusions

Conclusions from prior investigations, other agents, or earlier cycles carry authority they may not deserve. They were reached in a different context, possibly with different evidence quality, possibly with biases you can't see.

**Protocol for inherited conclusions**:
1. Understand the claim
2. Identify what evidence supported it
3. Ask whether that evidence is still valid
4. If possible, reproduce the evidence independently
5. Only then act on the conclusion

---

## 2 Strategies

### 2.1 Hypothesis-Prediction-Test

Every investigation follows this cycle:

1. **Hypothesize**: State what you believe is happening and why
2. **Predict**: If your hypothesis is correct, what specific, observable consequence follows?
3. **Test**: Design an observation that would reveal that consequence
4. **Evaluate**: Does the observation match your prediction?
5. **Iterate**: Refine or replace the hypothesis based on results

**The prediction step is critical.** Without it, you're just looking at data and telling stories about it. With it, you have a falsifiable claim that evidence can confirm or deny.

### 2.2 Survey vs Experiment

**Surveys** scan broadly: "How many files contain pattern X?" Surveys are fast but imprecise — they count without classifying, observe without controlling.

**Experiments** test specifically: "Does function Y produce output Z when given input W?" Experiments are slower but definitive — they control variables and produce unambiguous results.

**When surveys mislead**: A survey might find "1,165 matches" without distinguishing genuine instances from references, examples, or documentation mentioning the pattern. The count is accurate; the interpretation is wrong.

**When to escalate from survey to experiment**: When survey results contradict expectations or support your hypothesis too neatly, design a controlled experiment to verify.

### 2.3 When to Stop Theorizing

**Measure when**:
- You've spent more than 5 minutes reasoning about what MIGHT be happening
- Two plausible explanations both fit the available evidence
- Your theory involves assumptions about system behavior you haven't verified
- You catch yourself saying "it should work because..."

**The 5-minute rule**: If you've been reasoning for 5 minutes without new evidence, stop and design a test. The test will teach you more in 30 seconds than another 30 minutes of reasoning.

---

## 3 Evidence Hierarchy

From strongest to weakest:

### 3.1 Controlled Experiment (Strongest)

Feed known input to the actual system component, observe output, compare to prediction.

- **Strength**: Isolates causation, reproducible, unambiguous
- **Example**: Feed captured production data to a function and check its output
- **Weakness**: Requires knowing what to test

### 3.2 Direct Observation

Observe the system running in its actual environment with real data.

- **Strength**: Tests real conditions, reveals unexpected interactions
- **Example**: Check log output, inspect actual network traffic, read process output
- **Weakness**: Multiple variables changing simultaneously; correlation, not causation

### 3.3 Indirect Inference

Reason from observable effects to unobservable causes.

- **Strength**: Works when direct observation is impossible
- **Example**: "The output file changed, so the function must have run"
- **Weakness**: Multiple causes can produce the same effect

### 3.4 Architectural Reasoning (Weakest)

Predict behavior from understanding of system design.

- **Strength**: Fast, requires no setup, leverages expertise
- **Example**: "The function catches exceptions, so it should handle this error"
- **Weakness**: Maps don't match territory. Code does what it does, not what you think it does.

### 3.5 Presenting Evidence to Others

Evidence that convinces you may not convince others. To reduce the cognitive burden on reviewers:

- **Show the exact command** that produces the evidence
- **Show the actual output**, not your interpretation of it
- **Show the prediction** that the output confirms or denies
- **Make it reproducible**: Anyone running the same command should get the same result

---

## 4 Cognitive Traps

### 4.1 The Observability Trap

**"I can't see it, therefore it doesn't exist."**

Systems have layers. An effect visible at one layer may be invisible at another. Before concluding something isn't happening, verify you're observing the right layer at the right time.

**Example**: Request captures logged before a rewrite step will always show pre-rewrite content. The rewrite is happening — you're just looking in the wrong place.

### 4.2 The False Absence Fallacy

**"I searched and found nothing, therefore nothing exists."**

Search quality determines result quality. A search that uses the wrong pattern, searches the wrong files, or runs at the wrong time will find nothing — even when the target exists.

**Counter**: When a search returns no results, question the search before questioning reality.

### 4.3 The Plausibility Trap

**"This explanation sounds right, therefore it is right."**

Plausible explanations are seductive. They organize confusing observations into coherent narratives. But plausibility is not evidence — multiple plausible explanations can explain the same data.

**Counter**: When an explanation feels satisfying, that's the moment to test it hardest. Comfort is a signal to verify, not to stop investigating.

### 4.4 The Authority Trap

**"An expert/prior investigation concluded X, therefore X is true."**

Prior conclusions were reached in specific contexts with specific evidence. Contexts change. Evidence quality varies. Reputations don't guarantee correctness.

**Counter**: Respect prior work, but verify independently when the stakes justify it.

---

## 5 Integration with Other Policies

### The Empiricism Triad

This policy is the **attitude** layer of a three-part epistemological architecture:

| Layer | Policy | Role |
|-------|--------|------|
| **Attitude** | `philosophy/empiricism.md` (this policy) | Cognitive stance: skepticism, evidence hierarchy, cognitive traps |
| **Protocol** | `consciousness/experiments.md` | Structured method: hypothesis → method → success criteria → reflection |
| **Application** | `development/debugging_and_validation.md` | Applied discipline: debugging cycles, validation levels, evidence presentation |

**Attitude without protocol** produces ad-hoc investigation — right instincts, inconsistent execution.
**Protocol without attitude** produces mechanical compliance — following steps without understanding why.
**Both without application** produces philosophy — true but not useful for shipping code.

The triad ensures that empirical thinking flows from mindset (why evidence matters) through method (how to gather it systematically) to practice (how to present it convincingly in development work).

### Related Policies

- `consciousness/experiments.md` — Formalizes the hypothesis-test cycle into structured protocols with phases (intuition building → formal protocol → execution → reflection). Experiments is the protocol; empiricism is the attitude that makes protocols meaningful.
- `development/debugging_and_validation.md` — Applies empiricism to software development: debugging cycles, validation before completion, reproducible evidence presentation. This is where attitude meets daily practice.
- `development/testing.md` — Testing IS empiricism automated. Tests are controlled experiments with programmatic evaluation, run repeatedly to guard against regression.
- `development/coding_standards.md` — Error visibility (no silent failures) is empiricism applied to runtime: make the system observable so evidence is available when needed.

---

## Anti-Patterns

**Reasoning without evidence**: Extended architectural analysis when a 30-second test would resolve the question.

**Accumulating surveys instead of designing experiments**: Running broader and broader searches instead of testing one specific claim.

**Treating absence of evidence as evidence of absence**: "I didn't find it in captures" when captures don't capture what you think they capture.

**Accepting inherited conclusions without reproduction**: Acting on prior findings without verifying they still hold in the current context.

**Interpreting data without stating predictions first**: Looking at data and constructing post-hoc narratives instead of testing pre-stated hypotheses.

---

## Evolution & Feedback

This policy evolves through:
- Documented investigation successes and failures
- Pattern recognition across debugging sessions
- Cross-agent comparison of investigation strategies

**Principle**: The best investigators aren't the smartest — they're the most disciplined about gathering evidence before forming conclusions.
