---
name: maceff-ideas-curate
description: "Batch-curate ideas from recent work. Scan task notes, ULTRATHINK sessions, and tangential thoughts for uncaptured ideas. Use macf_tools idea create for each."
allowed-tools: Bash, Read, Grep, Glob
---

Batch-curate ideas from recent work into the Ideas CA system.

---

## When to Invoke

- After completing a sprint or significant work block
- During CURATE work mode
- When ULTRATHINK sessions produced tangential thoughts worth preserving
- Periodically during long autonomous sprints

---

## Policy Engagement

```bash
macf_tools policy navigate ideas
macf_tools policy read ideas
```

**Extract answers to these timeless questions**:

1. What schema does the policy specify for idea files?
2. What fields does the policy require vs make optional?
3. What lifecycle stages does the policy define?
4. What categories does the policy enumerate?
5. What provenance fields does the policy require?
6. What naming convention does the policy specify?
7. What does the policy say about the pull model for promotion?
8. What CLI commands does the policy document for idea management?

---

## Execution

Using {{SCHEMA}}, {{REQUIRED_FIELDS}}, {{CATEGORIES}}, {{LIFECYCLE}}, and {{CLI_COMMANDS}} extracted from policy answers:

1. **Scan for uncaptured ideas**:
   - Review recent task notes for tangential thoughts
   - Check if ULTRATHINK sessions produced speculative seeds
   - Look for patterns across recent work that suggest new capabilities

2. **For each idea found**, capture using {{CLI_COMMANDS}} with {{REQUIRED_FIELDS}}

3. **Check for promotable ideas**: List captured ideas and assess whether any are ready for the next {{LIFECYCLE}} stage per the pull model

4. **Update promoted ideas**: If an experiment or roadmap was created from an idea, update its status per {{LIFECYCLE}} transitions

---

## Critical Constraint

Ideas are cheap — capture liberally. The pull model described in the policy ensures only valuable ideas get promoted. Don't self-censor during curation.
