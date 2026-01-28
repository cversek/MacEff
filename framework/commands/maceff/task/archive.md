---
description: Archive completed task with cascade to disk
argument-hint: [task_id]
allowed-tools: Read, Bash(macf_tools:*)
---

Archive a completed task (and its children by default) to disk for long-term storage.

**Argument**: Task ID (e.g., `#67` or `67`)

---

## Policy Engagement Protocol

**Read archive protocol from task management policy**:

```bash
macf_tools policy navigate task_management
macf_tools policy read task_management --section 7
```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations.

---

## Questions to Answer from Policy Reading

After reading policies, you should be able to answer:

1. **What is the archive directory structure?** Where do archives go?
2. **What is cascade behavior?** How are child tasks handled?
3. **What metadata is preserved?** What MTMD fields are captured?
4. **When should tasks be archived?** What completion criteria apply?

---

## Execution

Using answers from policy reading:

1. **Verify task is complete**: Only completed tasks should be archived
2. **Execute archive**:
   ```bash
   macf_tools task archive #TASK_ID
   ```
3. **Verify**: Check archive was created successfully
4. **Report**: Show archive location and any cascaded children

**Options**:
- `--no-cascade` - Archive only the specified task, not children

---

## Critical Constraints

- Archive completed work only (status = completed)
- Cascade is the default - use `--no-cascade` to archive single task
- Archives are stored in `agent/public/task_archives/`

---

**Meta-Pattern**: This command wraps `macf_tools task archive` with policy guidance.
