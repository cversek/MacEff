---
description: Hide completed tasks from the CC task scanner
argument-hint: [task_id]
allowed-tools: Read, Bash(macf_tools:*)
---

Declutter the task tree by hiding completed tasks from Claude Code's scanner.

**Note**: `macf_tools task archive` (and `restore`/`archived`) are deprecated
stubs — the old archive workflow reported success while writing nothing, so
it was retired in favor of `task hide-completed`, which renames completed
task files rather than producing a separate archive artifact.

**Argument**: Task ID (e.g., `#67` or `67`) — informational only; `task hide-completed` operates on all completed tasks in the current store, not a single ID.

---

## Policy Engagement Protocol

**Read the current archive/hide-completed protocol from task management policy**:

```bash
macf_tools policy navigate task_management
macf_tools policy read task_management --section 7
```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations.

---

## Questions to Answer from Policy Reading

After reading policies, you should be able to answer:

1. **What does hiding a task do?** How does it differ from deleting or archiving?
2. **When should tasks be hidden?** What completion criteria apply?
3. **How do I reverse it?** What restores a hidden task to visibility?

---

## Execution

Using answers from policy reading:

1. **Verify task is complete**: Only completed tasks should be hidden
2. **Execute**:
   ```bash
   macf_tools task hide-completed
   ```
3. **Verify**: Confirm the task tree no longer surfaces the completed task(s)
4. **Report**: Note which tasks were hidden

**To reverse**:
```bash
macf_tools task unhide-all
```

---

## Critical Constraints

- Hide completed work only (status = completed)
- `task hide-completed` no-ops (with an explanatory message) on a task store CC doesn't scan

---

**Meta-Pattern**: This command wraps `macf_tools task hide-completed` with policy guidance.
