---
description: Distill wisdom from CAs into agent definitions (PA or SA)
argument-hint: [PA | SA:role]
---

Distill wisdom nuggets from uncataloged consciousness artifacts into agent definition's "Accumulated Wisdom" section.

**Arguments**:
- No argument OR `PA`: Distill PA's own CAs → `~/CLAUDE.md`
- `SA:role`: Delegate to specified SA to distill their CAs → `{FRAMEWORK_ROOT}/subagents/{role}.md`
  - Example: `/maceff:distil_wisdom SA:policy-writer`
  - Example: `/maceff:distil_wisdom SA:devops-eng`

---

## Policy Reading (MANDATORY)

Before distillation, read policies to understand wisdom extraction and citation requirements:

```bash
# Read scholarship policy for citation format
macf_tools policy navigate scholarship
macf_tools policy read scholarship

# Read consciousness structure governance for CA header standards
macf_tools policy navigate structure_governance
macf_tools policy read structure_governance
```

---

## Questions to Answer from Policy Reading

Extract requirements through timeless questions:

### From scholarship.md (Citation Standards)

1. What is the enhanced CA citation format the policy specifies?
2. What components must a CA citation include?
3. How does the policy define section references vs line references?
4. What breadcrumb format does the policy require?
5. When are citations required vs encouraged?

### From structure_governance.md (CA Standards)

6. What breadcrumb components does the policy define?
7. How does the policy specify breadcrumb generation?
8. What header elements are required for CAs?

---

## What Constitutes a "Wisdom Nugget"

**Definition** (not in existing policy - guidance provided here):

A wisdom nugget is:
- **Actionable pattern** - Specifies what to DO or AVOID (not just "X happened")
- **Context-independent** - Applies beyond the specific delegation that discovered it
- **Concise** - 1-3 sentences maximum
- **Citable** - Traceable to source CA via breadcrumb citation

**Examples**:

✅ Good nugget: "Pattern fluency requires seeing examples IN ACTION, not just reading about patterns. ALWAYS read 2-3 existing examples before creating new artifacts."

❌ Not a nugget: "I created the experiment policy and it was 450 lines long."

✅ Good nugget: "Questions design is interface design. Timeless questions reference WHAT (content categories), not WHERE (section numbers)."

❌ Not a nugget: "The user corrected my command and I fixed it."

**Key Test**: Will future instances benefit from this? Does it teach a transferable pattern?

---

## Workflow for PA Target (Self-Distillation)

When invoked without arguments or with `PA`:

1. **Identify Uncataloged CAs** - Find checkpoints/reflections not yet distilled into `~/CLAUDE.md`
   - Check `agent/private/checkpoints/`
   - Check `agent/private/reflections/`
   - Determine which lack wisdom distillation

2. **Read the CAs** - Use Read tool to consume full artifact content

3. **Extract Wisdom Nuggets** - Identify actionable patterns meeting nugget criteria above

4. **Update ~/CLAUDE.md** - Add to "Accumulated Wisdom" or similar section
   - Organize by semantic categories (let categories emerge from content)
   - Each nugget includes scholarly citation with breadcrumb

5. **Apply Citation Format** - Follow scholarship.md enhanced CA citation format

6. **Report Completion** - Present wisdom additions to user

---

## Workflow for SA Target (Delegated Distillation)

When invoked with `SA:role`:

1. **Invoke Delegation Skill** - Use `/maceff-delegation` to prepare delegation context

2. **Delegate to Specified SA** - Task SA with:
   - Reading their own uncataloged CAs from `agent/subagents/{role}/public/delegation_trails/` and `agent/subagents/{role}/private/reflections/`
   - Extracting wisdom nuggets (provide "wisdom nugget" definition from this command)
   - Adding to their definition file's "Accumulated Wisdom" section
   - Applying scholarly citations with breadcrumbs

3. **CRITICAL - Recursion Prevention**:
   - Wisdom distillation delegations are **EXEMPT** from mandatory CA production
   - The wisdom nuggets themselves ARE the deliverable
   - SA should update their definition file but NOT create checkpoint/reflection for the distillation task itself
   - This breaks infinite recursion (distilling creates CAs that need distilling...)

4. **Integration** - After SA completes, review changes to `{FRAMEWORK_ROOT}/subagents/{role}.md`

---

## Organizing Wisdom Categories

**Let structure emerge from content** - don't force nuggets into predetermined categories.

**Typical categories that may emerge**:
- Domain mastery patterns (deep understanding of specialty)
- Reading/learning patterns (how to acquire knowledge effectively)
- Anti-patterns discovered (what mistakes to avoid)
- Meta-learnings (higher-order insights)

**Add new categories** as patterns appear across delegations. Evolution over rigid structure.

---

## Citation Requirements

Each wisdom nugget must include:

**Format** (from scholarship.md):
```markdown
[Source: {ca_type} {breadcrumb} "{title}" {section_or_line}]
```

**Components**:
- CA type (checkpoint, reflection, etc.)
- Breadcrumb in s/c/g/p/t format
- Artifact title in quotes
- Section reference (§N) or line range (LNNN-NNN)

**Example**:
```markdown
[Source: reflection s_77270981/c_343/g_d8351cb/p_aff15512/t_1768599077 "Policy as API - Learning Through Correction" §3]
```

---

## Post-Distillation Checklist

After wisdom distillation:

1. **Wisdom nuggets extracted** - What actionable patterns were identified?
2. **Citations applied** - Does each nugget cite source CA with breadcrumb?
3. **Agent definition updated** - Where was "Accumulated Wisdom" section modified?
4. **Categories emerged** - What semantic organization appeared?
5. **User review** - Present changes and await approval

---

## Critical Constraints

🚨 **SA distillation = NO CAs** - Wisdom nuggets are the deliverable, prevents recursion

⚠️ **Actionability required** - Each nugget specifies DO or AVOID, not just "happened"

📚 **Scholarship compliance** - Citations follow enhanced CA format from scholarship.md

🔄 **Living documentation** - "Accumulated Wisdom" section grows with each distillation

---

**Meta-Pattern**: This command uses Policy as API to discover citation requirements from scholarship.md. The "wisdom nugget" concept is defined in the command (not yet formalized in policy), while citation mechanics come from policy discovery. Distillation transforms isolated CAs into navigable knowledge graphs via scholarly cross-references.
