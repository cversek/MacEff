Create a MacEff-compliant roadmap by reading policies for structure guidelines, then drafting according to established patterns.

**Argument**: Brief description of the roadmap topic

---

## Policy Reading (MANDATORY)

Before drafting, read these policies to understand requirements:

1. **Roadmap Drafting Guidelines**:
   - `{FRAMEWORK_ROOT}/policies/base/consciousness/roadmaps_drafting.md`
   - Extracts: Structure requirements, phase patterns, success criteria format

2. **Path Portability** (for framework roadmaps):
   - `{FRAMEWORK_ROOT}/policies/base/meta/path_portability.md`
   - Extracts: Portable path conventions, `{FRAMEWORK_ROOT}` placeholder usage

---

## Questions to Answer from Policy Reading

After reading policies, **report answers to user before any state-changing tools**:

1. **What preliminary steps does roadmaps_drafting.md require?**
   - What must happen before drafting begins?
   - What exploration or user interaction is specified?

2. **What folder structure does the policy specify?**
   - Where do roadmaps go?
   - What subdirectories are required?

3. **What sections must a roadmap contain?**
   - Header format and required fields
   - Phase structure requirements
   - Success criteria format

4. **What path conventions apply to framework roadmaps?**
   - How should policies be referenced?
   - What patterns are prohibited?

---

## Execution

After reporting policy-extracted answers:

1. **Follow preliminary requirements** as specified by policy
2. **Create artifacts** per policy-specified structure
3. **Apply content requirements** extracted from policy
4. **Verify against policy checklist** before completion

---

## Critical Constraints

🚨 **Never use naked `cd` commands** - causes session failures. Use absolute paths.

⚠️ **Path portability required** - Use `{FRAMEWORK_ROOT}` for policy references.

---

**Meta-Pattern**: This command points to policies, doesn't embed them. When policies evolve, command stays current through Policy as API approach.
