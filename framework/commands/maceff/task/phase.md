---
description: Create phase task under parent MISSION/DETOUR with policy-guided hierarchy notation
argument-hint: --parent N "Title"
allowed-tools: Read, Bash
---

Create a new phase task as child of parent MISSION or DETOUR.

**Arguments**:
- `--parent N` (required): Parent task ID
- `Title` (required): Phase title (will auto-add `[^#N]` prefix)

---

## Policy Engagement Protocol

**Read task management policy to understand phase hierarchy**:

1. `{FRAMEWORK_ROOT}/policies/base/development/task_management.md`
   - Read from beginning to `=== CEP_NAV_BOUNDARY ===`
   - Navigate to sections on hierarchy notation, dependency system

---

## Questions to Answer from Policy Reading

**Policy as API Principle**: These questions DISCOVER current policy patterns without prescribing them. As policies evolve, questions remain timeless by extracting information rather than encoding it.

After reading policy, you should be able to answer:

1. **Hierarchy Notation**: What prefix format identifies phase tasks?
   - How does `[^#N]` notation work?
   - What does policy specify about parent_id?

2. **MTMD Inheritance**: What metadata does phase inherit from parent?
   - How does repository propagate?
   - How does version propagate?

3. **Dependency System**: How do phases relate to parents in policy?
   - What's the blocking relationship?
   - How does completion cascade?

4. **CLI Automation**: What does `task create phase` command provide automatically?
   - What prefix is auto-added?
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

**Meta-Pattern**: Policy as API - this command references policies without embedding content. As policies evolve, command stays current through dynamic policy reading.
