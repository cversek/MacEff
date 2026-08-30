---
description: Convert validated experiment into MISSION roadmap
argument-hint: [experiment_id_or_path]
---

Convert a validated experiment into a MISSION roadmap.

**Argument**: the experiment's task id, or the path to its CA directory.

---

## Policy Engagement

```bash
macf_tools policy navigate experiments
macf_tools policy navigate roadmaps_drafting
macf_tools policy navigate task_management
```

Read the sections that answer these. Report the answers before any
state-changing tool call.

**From `experiments.md`** — is this experiment ready, and what carries over:
1. What terminal states exist, and which one does conversion require? How is it
   recorded, and where?
2. What must be true before conversion is appropriate at all — and what does the
   policy say about converting too early?
3. What evidence must the experiment have produced, and what of it must the
   roadmap carry?
4. What must each document cite about the other?

**From `roadmaps_drafting.md`** — where the work goes and in what order:
5. Where is the plan drafted, and at what point is `roadmap.md` written relative
   to pinning? *(Getting this order wrong destroys work — ask before assuming.)*
6. What must a roadmap contain, and how are phases specified?
7. What does the policy forbid putting inside a phase?
8. What happens after the plan is approved but before implementation begins?

**From `task_management.md`** — what pinning creates:
9. What does pinning produce, and what ordering constraint does it carry?

---

## Execution

Apply what the policies answered, in the order they specify.

An experiment that fails question 1 or 2 is not converted — say so and stop.
Conversion produces a plan and a task hierarchy; it is not authorization to
implement (question 8).

Create that hierarchy by invoking `/maceff:task:create_mission` and
`/maceff:task:create_phase`, not the raw CLI. This command previously named no
concrete creation step and left it to judgement, which is how a roadmap produced
here came to carry no PEP on any phase while the sibling drafting path carried
one on every phase.

**Policy Engagement Protocol on Phases (MANDATORY)**:

Ask `roadmaps_drafting` these, and carry the answers into every phase you create:

- What does the policy require a phase to declare about the policies its executor must engage?
- How does the policy say required reading follows from the WORK TYPE, rather than being re-derived per phase?
- What distinction does the policy draw between policies a phase READS and policies it WRITES?
- When does the policy say a phase carries no PEP at all?

Extract the work-type mapping from the policy rather than reproducing it here — it
is expected to grow, and a copy would drift from it. The point of the mapping is
that an executor picking a phase up cold, with no memory of the drafting
conversation, does not begin work without reading something they needed.


## Wiki-Links

Consult the roadmaps drafting policy on knowledge web participation. Prefer
concepts the source experiment already used, so the evidence trail exists in the
graph and not only in citations.
