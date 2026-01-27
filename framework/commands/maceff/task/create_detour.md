---
description: Create DETOUR task with roadmap folder atomically using policy-guided metadata
argument-hint: "Title" [--repo REPO] [--version X.Y.Z]
allowed-tools: Bash
---

Create a new DETOUR task with roadmap folder structure in a single atomic operation.

**Arguments**:
- `Title` (required): DETOUR title (will auto-add ↩️ marker)
- `--repo NAME` (optional): Repository in MTMD
- `--version X.Y.Z` (optional): Target version in MTMD

---

## Policy Engagement Protocol

**Use CLI tools to discover task management policy requirements**:

```bash
# First: Navigate to see policy structure and available sections
macf_tools policy navigate task_management

# Then: Read full policy or specific sections as needed
macf_tools policy read task_management
# OR for targeted reading:
macf_tools policy read task_management --section N
```

Navigate to sections covering: task types, MTMD schema, hierarchy, roadmap structure.

---

## Questions to Answer from Policy Reading

**Policy as API Principle**: These questions DISCOVER current policy patterns without prescribing them. As policies evolve, questions remain timeless by extracting information rather than encoding it.

After reading policy, you should be able to answer:

1. **Task Type Recognition**: What marker identifies DETOUR tasks?

2. **MTMD Requirements**: What metadata does the policy specify for DETOUR tasks?
   - What fields are mandatory vs optional?
   - How does the policy define repository and version metadata?

3. **Roadmap Structure**: What folder structure does policy specify for DETOURs?
   - Where are roadmap CAs located?
   - What subdirectories does policy require?

4. **Breadcrumb Integration**: How does creation breadcrumb integrate with task metadata?

5. **CLI Automation**: What does `task create detour` command provide automatically?
   - What metadata is auto-generated?
   - What skeleton files are created?

---

## Execution

Using answers from policy reading:

1. **Create task atomically**:
   ```bash
   macf_tools task create detour "Your Title" --repo REPO --version X.Y.Z
   ```

2. **Report** the task ID and roadmap path shown in CLI output

3. **Next steps**: Copy plan content to skeleton `roadmap.md`, then use `/maceff:task:start #{TASK_ID}` to expand phases

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

---

**Meta-Pattern**: Policy as API - this command references policies via CLI tools without embedding content. As policies evolve, command stays current through dynamic policy reading.
