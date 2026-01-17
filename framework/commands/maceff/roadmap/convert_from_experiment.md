---
description: Convert validated experiment into MISSION roadmap
argument-hint: [experiment_path]
---

Convert a **validated experiment** into a **MISSION roadmap**, transferring learnings and creating strategic capability development structure.

**Argument**: Path to experiment directory (e.g., `agent/public/experiments/YYYY-MM-DD_HHMMSS_NNN_name/`)

---

## Policy Reading (MANDATORY)

Before conversion, read these policies to understand requirements:

1. **Experiments Policy** - Completion, crystallization, conversion workflow:
   ```bash
   macf_tools policy navigate experiments
   macf_tools policy read experiments
   ```

2. **Roadmap Drafting Guidelines** - Structure, phases, success criteria:
   ```bash
   macf_tools policy navigate roadmaps_drafting
   macf_tools policy read roadmaps_drafting
   ```

**Why CLI tools**: Caching prevents redundant reads, line numbers enable precise citations.

---

## Questions to Answer from Policy Reading

After reading policies, **report answers to user before any state-changing tools**:

### From experiments.md (Experiment Completion & Crystallization)

1. **What terminal states does the policy define?**
   - Which terminal state is required for MISSION conversion?
   - Where is terminal state documented?

2. **What crystallization indicators must be present?**
   - What are the indicators the policy specifies?
   - How do I verify each indicator is met?
   - What happens if indicators are missing?

3. **What evidence requirements does the policy specify?**
   - What must analysis.md contain?
   - What success criteria evaluation is needed?
   - What files must exist in experiment directory?

4. **What conversion workflow does the policy document?**
   - What steps are specified for conversion?
   - What architectural extraction is required?
   - How to transform hypothesis into MISSION?

5. **What cross-reference requirements are mandatory?**
   - What must roadmap cite from experiment?
   - What must experiment link back to roadmap?
   - What breadcrumb citations are required?

### From roadmaps_drafting.md (Roadmap Structure)

6. **What folder structure does the policy specify?**
   - Where do roadmaps go?
   - What subdirectories are required?
   - What naming convention is used?

7. **What sections must a roadmap contain?**
   - What header format is required?
   - What MISSION format is specified?
   - What phase structure is mandatory?

8. **How should phases be designed?**
   - What must each phase contain?
   - How to derive phases from experiment insights?
   - What success criteria format is required?

9. **What delegation strategy format does the policy require?**
   - What executor options exist?
   - What rationale accompanies assignments?

10. **What TODO integration does the policy specify?**
    - How are roadmaps integrated with TODO lists?
    - What embedding format is required?
    - When should implementation begin?

---

## Execution

After reporting policy-extracted answers:

1. **Validate Prerequisites** - Verify experiment meets crystallization criteria from policy
2. **Extract Learnings** - Read experiment artifacts as specified by policy
3. **Create Roadmap Structure** - Follow folder structure from policy
4. **Draft roadmap.md** - Apply MISSION and phase requirements from policy
5. **Establish Cross-References** - Follow bidirectional citation requirements from policy
6. **Report Completion** - Present roadmap and await user authorization

🚨 **CRITICAL**: Conversion creates roadmap only. DO NOT begin implementation. User must review roadmap and explicitly authorize via `/maceff:todos:start [MISSION]`.

---

## Post-Conversion Checklist (MANDATORY)

After roadmap created, verify these requirements from policy:

1. **Roadmap folder created** - What structure does policy specify?
2. **roadmap.md drafted** - What sections does policy require?
3. **Evidence Base cited** - What experiment references are mandatory?
4. **Bidirectional cross-references** - What must both documents contain?
5. **TODO structure proposed** - What integration format does policy specify?
6. **🛑 STOP** - Report completion and AWAIT user authorization

**Policy Discovery**: Navigate experiments and roadmaps_drafting to extract conversion workflow and structure requirements.

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

⚠️ **Path portability required** - Use `{FRAMEWORK_ROOT}` for policy references.

🚫 **No premature execution** - Roadmap creation ≠ authorization to begin work.

---

**Meta-Pattern**: Policy as API - this command uses timeless extractive questions to discover conversion requirements from policies. Policies evolve, command adapts automatically.
