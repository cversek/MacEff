---
name: maceff-assign-role
description: USE when the operator appoints the agent to a standing position (custody of a corpus, an assistantship for a term, an on-call seat) or says "assign a role". Runs the assignment ceremony the roles policy describes, interviewing the operator before anything is created.
allowed-tools: Bash, Read, AskUserQuestion
---

Assign a ROLE: a formal appointment with a tenure and a review date, not a task.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate roles
macf_tools policy read roles --from-nav-boundary
```

Read the sections on what a role is, assignment, time properties, and the store.

---

## Questions to Extract from Policy Reading

1. **Role vs task** - What makes a position a role rather than a task, and what does holding one as a task break?
2. **How many** - What does the policy say about how many roles an agent should hold, and what does the ceremony do when that is exceeded?
3. **What the ceremony collects** - Which facts must be gathered before a role exists?
4. **Review** - What is the review date for, and what does its horizon mean? How is a horizon reasoned when the operator does not supply one?
5. **Icons** - What icon shelf does the policy define, and how are icons offered?
6. **Charter** - What is the charter, what does its scaffold contain, and when is a role considered undescribed?
7. **First duties** - What must a dated or recurring duty carry, and who reasons it?

---

## Execution

1. Count the agent's active roles (`macf_tools role list`) and apply the policy's warning if the count exceeds its soft cap; ask the operator to confirm.
2. Interview the operator with AskUserQuestion for each fact the ceremony collects: title, tenure start and expiry, review date and its reasoned horizon, purpose and boundaries, resources, and the icon -- offering the three best-fit shelf icons for the described role plus Other.
3. Create the role with the collected facts (`macf_tools role create ...`), then open the scaffolded charter and replace its headings with the operator's sentences; add `[[wiki_links]]` for the concepts the role is about.
4. For each first duty the operator names, declare it (`macf_tools role duty add ...`), reasoning and recording the horizon per the policy when one is not given.
5. Show the result (`macf_tools role show <id>`) and offer to focus it (`maceff-role-focus`).

---

## Critical Meta-Pattern

**Policy as API**: the shelf, the cap, the horizon reasoning and the charter shape live in the roles policy. This skill asks for them; it does not restate them.
