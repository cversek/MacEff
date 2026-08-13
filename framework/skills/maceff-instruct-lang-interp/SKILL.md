---
name: maceff-instruct-lang-interp
description: Interpret an operator instruction-language (IL) directive — a dense, uppercase, terminator-bearing instruction issued mid-work. Use when a message looks like a directive rather than prose, when an unfamiliar directive token appears, or when unsure whether something was an instruction or a comment.
allowed-tools: Bash, Read, Grep
---

Interpret an inbound IL directive and discharge it correctly.

---

## When to Invoke

- A message contains something shaped like a directive rather than prose
- A directive token appears that you do not recognise
- You are unsure whether an utterance was an instruction, an aside, or affect
- A directive arrives mid-work and you must decide what to do with the work in flight

---

## Policy Engagement

```bash
macf_tools policy navigate instruction_language
macf_tools policy navigate task_management
```

Read the sections that answer:

- (instruction_language) "What is the canonical form of a directive, and how do I recognise one whose token I have never seen?"
- (instruction_language) "What do the terminators mean, and what is the safe default for each when the token is unknown?"
- (instruction_language) "How is a token's meaning resolved, and what do I do when I cannot resolve it?"
- (instruction_language) "How many obligations may a form carry, and how do I verify I discharged it rather than half of it?"
- (instruction_language) "How is a directive absorbed while work is in flight, and what decides whether it preempts or waits?"
- (task_management) "How does an inbound directive bind to the work stack, and what must I read to know which frames are open?"

---

## The Interpretation

Using what the policy prescribes, answer in order:

1. **Is this IL at all?** Apply the policy's recognition rule — including its guard against false positives — before treating anything as a directive. A misread affect marker and an unread instruction are both failures, in opposite directions.
2. **What are its parts?** Decompose the directive per the canonical form. Do not infer structure the policy does not define.
3. **What does it mean?** Resolve the token within this operator–agent pair's vocabulary. If it does not resolve, run the loop the policy prescribes for unknown forms — and note that the loop's value depends on staying cheap for the operator.
4. **When is it serviced?** Determine the service discipline from what the policy says governs it, not from how urgent the wording feels.
5. **What is the one obligation?** Name it explicitly, then discharge it. If the directive appears to carry two, resolve that per the policy rather than doing both informally.
6. **Where does the frame go?** Bind the directive and the work it interrupted to the work stack as the task policy prescribes, so neither survives only in context.

---

## Verify Before Reporting

- The obligation you named has produced whatever durable evidence the policy requires — check, do not assume.
- The interrupted work is recorded somewhere that survives losing this context.
- If you inferred a meaning, the inference was stated to the operator and durably recorded, not merely acted upon.

---

## Anti-Pattern: Silent Prose-Reading

Treating an unrecognised directive as ordinary conversation. The whole point of a
recognisable shape is that an unknown token is *queryable* rather than invisible —
reading it as prose drops an instruction while feeling like comprehension.
