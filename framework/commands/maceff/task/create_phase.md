---
description: Create phase task under parent MISSION/DETOUR with policy-guided hierarchy notation
argument-hint: --parent N "Title"
allowed-tools: Bash
---

Create a new phase task as child of parent MISSION or DETOUR.

**Arguments**:
- `--parent N` (required): Parent task ID
- `Title` (required): Phase title (CLI will auto-add hierarchy prefix)

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

Navigate to sections covering: hierarchy notation, dependency system, phase relationships.

---

## Questions to Answer from Policy Reading

**Policy as API Principle**: These questions DISCOVER current policy patterns without prescribing them. As policies evolve, questions remain timeless by extracting information rather than encoding it.

After reading policy, you should be able to answer:

1. **Hierarchy Notation**: What prefix format does the policy specify for phase tasks?
   - How does policy define parent-child notation?
   - What does policy specify about parent_id metadata?

2. **MTMD Inheritance**: What metadata does policy say phases inherit from parent?
   - How does repository propagate?
   - How does version propagate?

3. **Dependency System**: How does policy define phase-parent relationships?
   - What blocking relationships does policy specify?
   - How does policy describe completion cascade?

4. **CLI Automation**: What does `task create phase` command provide automatically?
   - What prefix does CLI add according to policy?
   - What metadata is auto-populated?

---

## Execution

Using answers from policy reading:

1. **Create phase atomically**:
   ```bash
   macf_tools task create phase --parent N "Your Phase Title"
   ```

2. **Report** the task ID and hierarchy notation shown in CLI output

3. **Next steps**: Use `/maceff:task:start #{TASK_ID}` to begin phase work

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

---

**Meta-Pattern**: Policy as API - this command references policies via CLI tools without embedding content. As policies evolve, command stays current through dynamic policy reading.
