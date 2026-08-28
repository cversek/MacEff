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

### The phase's own Policy Engagement Protocol (MANDATORY)

A phase is the artifact `roadmaps_drafting` governs with its phase Policy-Engagement-Protocol requirement, so this command must
consult that policy as well as `task_management` — its entire job is creating the
thing the requirement is about, and it previously did not read the policy at all.

```bash
macf_tools policy navigate roadmaps_drafting
macf_tools policy read roadmaps_drafting --section <CEP_MATCH>
```

Ask it, and carry the answers into the phase being created:

- What does the policy require a phase to declare about the policies its executor must engage?
- How does the policy say required reading follows from the WORK TYPE, rather than being re-derived per phase?
- What distinction does the policy draw between policies a phase READS and policies it WRITES?
- When does the policy say a phase carries no PEP at all?

Extract the work-type mapping from the policy rather than reproducing it here — it
is expected to grow, and a copy would drift. The point is that an executor picking
this phase up cold, with no memory of the drafting conversation, does not begin
work without reading something they needed. The motivating failure is recorded in
the policy: an agent wrote Python under a PEP-less phase and never opened the
coding standards, because nothing prompted it to.


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
