---
description: Create MISSION task with roadmap folder atomically using policy-guided metadata
argument-hint: "Title" [--repo REPO] [--version X.Y.Z]
allowed-tools: Bash
---

Create a new MISSION task with roadmap folder structure in a single atomic operation.

**Arguments**:
- `Title` (required): MISSION title (will auto-add 🗺️ marker)
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

### The Policy Engagement Protocol its phases will carry (MANDATORY)

A MISSION owns the phases `roadmaps_drafting` governs with its phase Policy-Engagement-Protocol requirement, so this command must
consult that policy as well as `task_management`. Establishing the requirement at
the MISSION means each phase created under it inherits an answer rather than
re-deriving one.

```bash
macf_tools policy navigate roadmaps_drafting
macf_tools policy read roadmaps_drafting --section <CEP_MATCH>
```

Ask it, and carry the answers into every phase created under this MISSION:

- What does the policy require a phase to declare about the policies its executor must engage?
- How does the policy say required reading follows from the WORK TYPE, rather than being re-derived per phase?
- What distinction does the policy draw between policies a phase READS and policies it WRITES?
- When does the policy say a phase carries no PEP at all?

Extract the work-type mapping from the policy rather than reproducing it here — it
is expected to grow, and a copy would drift. The point is that an executor picking a phase up cold, with no memory of the drafting conversation, does not begin
work without reading something they needed. The motivating failure is recorded in
the policy: an agent wrote Python under a PEP-less phase and never opened the
coding standards, because nothing prompted it to.


Navigate to sections covering: task types, MTMD schema, hierarchy, roadmap structure.

---

## Questions to Answer from Policy Reading

**Policy as API Principle**: These questions DISCOVER current policy patterns without prescribing them. As policies evolve, questions remain timeless by extracting information rather than encoding it.

After reading policy, you should be able to answer:

1. **Task Type Recognition**: What marker identifies MISSION tasks?

2. **MTMD Requirements**: What metadata does the policy specify for MISSION tasks?
   - What fields are mandatory vs optional?
   - How does the policy define repository and version metadata?

3. **Roadmap Structure**: What folder structure does policy specify for MISSIONs?
   - Where are roadmap CAs located?
   - What subdirectories does policy require?

4. **Breadcrumb Integration**: How does creation breadcrumb integrate with task metadata?

5. **CLI Automation**: What does `task create mission` command provide automatically?
   - What metadata is auto-generated?
   - What skeleton files are created?

---

## Execution

Using answers from policy reading:

1. **Create task atomically**:
   ```bash
   macf_tools task create mission "Your Title" --repo REPO --version X.Y.Z
   ```

2. **Report** the task ID and roadmap path shown in CLI output

3. **Next steps**: Copy plan content to skeleton `roadmap.md`, then use `/maceff:task:start #{TASK_ID}` to expand phases

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths or subshells.

⚠️ **Sequential execution preferred** - concurrent tool calls can cause errors.

---

**Meta-Pattern**: Policy as API - this command references policies via CLI tools without embedding content. As policies evolve, command stays current through dynamic policy reading.
