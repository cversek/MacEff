---
description: Create EXPERIMENT task with protocol folder atomically using policy-guided metadata
argument-hint: "Title"
allowed-tools: Bash
---

Create a new EXPERIMENT task with protocol folder structure in a single atomic operation.

**Arguments**:
- `Title` (required): EXPERIMENT title (will auto-add 🧪 marker and NNN number)

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

Navigate to sections covering: task types, MTMD schema, experiment numbering.

---

## Questions to Answer from Policy Reading

**Policy as API Principle**: These questions DISCOVER current policy patterns without prescribing them. As policies evolve, questions remain timeless by extracting information rather than encoding it.

After reading policy, you should be able to answer:

1. **Task Type Recognition**: What marker identifies EXPERIMENT tasks?

2. **Numbering Protocol**: How does the policy handle experiment numbering?
   - What format (NNN) does policy specify?
   - How is auto-increment handled?

3. **Protocol Structure**: What folder structure does policy specify for EXPERIMENTs?
   - Where are protocol CAs located?
   - What file naming pattern applies?

4. **Breadcrumb Integration**: How does creation breadcrumb integrate with task metadata?

5. **CLI Automation**: What does `task create experiment` command provide automatically?
   - What metadata is auto-generated?
   - What skeleton files are created?

---

## Execution

Using answers from policy reading:

1. **Create task atomically**:
   ```bash
   macf_tools task create experiment "Your Title"
   ```

2. **Report** the task ID, experiment number (NNN), and protocol path shown in CLI output

3. **Next steps**: Copy plan content to skeleton `protocol.md`, then use `/maceff:task:start #{TASK_ID}` to begin work

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

---

**Meta-Pattern**: Policy as API - this command references policies via CLI tools without embedding content. As policies evolve, command stays current through dynamic policy reading.
