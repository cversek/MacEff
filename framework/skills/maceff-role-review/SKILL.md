---
name: maceff-role-review
description: USE when a role's review date approaches or arrives (the tree or a hook shows a review mark), when a tenure expires, or when the operator asks whether a standing position still stands. The tenure ritual from the roles policy.
allowed-tools: Bash, Read, AskUserQuestion
---

Review a role: confirm with the operator that the appointment still stands and its charter still describes it, then record the outcome.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate roles
```

Read the sections on lifecycle (the review ritual), time properties (the review horizon), the calendar, and knowledge web participation.

---

## Questions to Extract from Policy Reading

1. **What a review decides** - What questions does the ritual answer, and what dispositions can it end in?
2. **Undescribed roles** - What does the policy say about a charter that is still the scaffold, and what should the review do about it?
3. **Expiry** - What happens to a role whose expiry has passed with no review, and what does the verb make agree?
4. **Renewal** - Is a renewed appointment the same role or a new one, and how does the new one cite the old?
5. **The next date** - How is the next review date and its horizon reasoned?
6. **Duties at review** - What should happen to duties nobody has serviced, and what does deferral require?

---

## Execution

1. `macf_tools role show <id> --all` and read the charter; note duties unserviced past their horizon.
2. Ask the operator (AskUserQuestion) whether the appointment continues, whether the charter is still true, and what the next review date should be; reason its horizon with them.
3. Record: `macf_tools role review <id> --outcome "<what was concluded>" [--next YYYY-MM-DD --next-horizon <Nd>] [--expire | --retire]`.
4. Update the charter and any duties the review changed (`maceff-role-duty`); if the role was renewed as a new appointment, run `maceff-assign-role` and cite the old role in the new charter.

---

## Critical Meta-Pattern

**Policy as API**: the ritual's questions and dispositions are the policy's; this skill schedules the conversation and records what it decides.
