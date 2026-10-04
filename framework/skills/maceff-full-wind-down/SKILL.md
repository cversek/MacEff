---
name: maceff-full-wind-down
description: "Use when a cycle is closing: the AUTO_MODE wind-down threshold is reached, or the operator asks for the wind-down. Dispatches the wind-down sequence through each step's own skill, in the order and under the conditions the wind-down protocol gives, and records every step it skips or shortens."
---

Run the full wind-down: one dispatch through the skills that curate, checkpoint and reflect, coordinated by policy.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate autonomous_operation
macf_tools policy read autonomous_operation --section <CEP_MATCH>
```

`<CEP_MATCH>` is the section whose navigation questions ask about the wind-down. Each dispatched skill brings its own engagement protocol; the answers below decide how those run inside the context that is left.

---

## Questions to Extract from Policy Reading

1. **Sequence** - What steps does the wind-down run, which skill performs each, and why does each come where it does?
2. **Conditions** - Which steps are conditional or sized by the context window, and when is each condition evaluated?
3. **Reading** - What reading does each step owe its policies, and what gives way when context is short?
4. **Gates** - Which of the dispatched skills' gates print and continue, and which wait for the operator?
5. **Exceptions** - What else may interrupt the sequence, and where is a skipped or shortened step recorded?
6. **Freshness** - What must be re-queried before the checkpoint, and what is committed together?
7. **Ending** - How does the sequence end, and which compaction route applies here?

---

## Execution

1. Find the task the wind-down is filed under (`macf_tools task trace`) and note the context level on entry.
2. For each step in order: evaluate its condition now, then invoke its skill with the Skill tool, passing the size the protocol gives; or record why it is skipped or shortened.
3. Note each step's exit context level, and every exception, on that task.
4. Finish as the protocol specifies, and say which compaction route applies.

---

## Critical Meta-Pattern

**Policy as API**: the order, conditions, sizes and exceptions live in the wind-down protocol, not in this skill. When the protocol changes, this dispatcher follows it unchanged.
