---
name: maceff-role-duty
description: USE when declaring, noting, linking, completing or deferring a duty of a standing role ("add a duty", "the board plan is done", "mark the sections taught"). Duties are declarations that point at their implementations; this skill applies the roles policy's rules for horizon, evidence and cadence.
allowed-tools: Bash, Read
---

Work a duty the way the roles policy defines one: a declaration with time properties, pointing at the tasks that implement it.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate roles
```

Read the sections on what a duty is, lifecycle, time properties (due, horizon, cadence), and priority tiers.

---

## Questions to Extract from Policy Reading

1. **Declaration vs implementation** - What belongs in a duty's body, and what belongs in a task?
2. **Horizon** - When must a duty carry a horizon, who reasons it, from what questions, and where is the reasoning recorded?
3. **Cadence** - What grammar does the policy give, how does an occurrence get marked done, and how does the horizon apply to occurrences?
4. **Done** - What does `done` require, what evidence is acceptable, and what is the honest alternative when a duty is no longer owed?
5. **Tracks** - How does a duty point at in-flight work, and what does the role view show for it?
6. **Tiers** - What tier will this duty land in, and how can I ask why?
7. **Nesting** - May a duty have sub-duties, and what should be done instead?
8. **Boundaries** - What does the role's charter say it may do alone and what needs the operator's direction, and what does the policy say a duty never authorizes toward third parties?
9. **Engagement** - What does engaging a duty do to the other active duties, how is a deliberate parallel engagement declared, and what does the command show?

---

## Execution

- Declare: `macf_tools role duty add <role> "<title>" [--due|--cadence] --horizon <Nd> --why "<reasoning>" [--importance] [--depends-on] [--tracks]`.
- Take it up: `macf_tools role duty engage <duty> [--note] [--tracks N]` (the duty's task start: active, noted, its role focused, the others disengaged); several ids in one command for a parallel engagement.
- Point at work: `macf_tools role duty link <duty> <task ids>`; note progress: `macf_tools role duty note <duty> "<text>"`.
- A cadence occurrence: `macf_tools role duty note <duty> "<text>" --done-on YYYY-MM-DD`.
- Satisfied: `macf_tools role duty done <duty> --evidence <completed task id or CA path>`; no longer owed: `macf_tools role duty defer <duty> --reason "<why>"`.
- Explain: `macf_tools role duty why <duty>`.

---

## Critical Meta-Pattern

**Policy as API**: the horizon questions, the tier table and the evidence rule are the policy's; the verbs above enforce them and name the section when they refuse.
