---
name: maceff-generative-self-motivation
description: "Invoke at gate points when the Markov recommender suggests BUILD mode, or when an experiment has validated a hypothesis and implementation is warranted. Sets BUILD work mode. In AUTO_MODE, building typically follows experimentation — prototypes live inside experiment CAs."
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Transition into BUILD mode — implement validated designs and promote experiment prototypes.

---

## When to Invoke

- Markov recommender suggests transition to BUILD at a gate point
- An experiment has validated a hypothesis and produced a prototype ready for promotion
- A roadmap phase has clear implementation specs
- The user has explicitly authorized code changes to a project repo

---

## Policy Engagement

```bash
macf_tools policy navigate mode_system
```

Read the sections that answer: "What are work modes?" and "How does BUILD relate to EXPERIMENT in the natural cycle?"

---

## Set Work Mode

```bash
macf_tools mode set-work BUILD
```

---

## ULTRATHINK Reflection

Before creating tasks, pause and think deeply:

1. **Has this been validated by experiment?** BUILD should follow EXPERIMENT in the natural cycle. If not — consider experimenting first.
2. **What's the smallest shippable unit?** Prefer working code over perfect architecture.
3. **Where does this code live?** Prototypes in experiment CAs. Production code in project repos (requires authorization in AUTO_MODE).
4. **What tests will prove it works?** Define success criteria before writing code.
5. **Am I authorized to touch this repo?** In AUTO_MODE, check whether project repo changes were explicitly authorized.

---

## Execution

1. Record the transition in task notes: "BUILD mode activated via maceff-generative-self-motivation. Building: {what}. Validated by: {experiment/authorization}."
2. Create implementation tasks with concrete deliverables
3. Write code — ship working implementations, not plans
4. Test before reporting completion
5. Commit with clear messages linking to MISSION/experiment

---

## Accountability

If you were recommended BUILD but chose a different mode, you MUST justify in task notes:
"Recommender suggested BUILD (p=X%). Override: chose {MODE} because {reason}."

---

## Anti-Pattern: The Unvalidated Build

Building without prior experimentation risks implementing the wrong thing. If you can't cite an experiment or explicit user authorization that validates this build — pause and ask whether an experiment should come first.
