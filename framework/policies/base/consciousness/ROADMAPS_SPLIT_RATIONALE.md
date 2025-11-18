# Roadmaps Policy Split - Rationale & Migration Guide

**Date**: 2025-11-18
**Author**: PolicyWriter SA
**Task**: Split roadmaps.md into drafting vs following policies

---

## Why Split?

**Problem**: Original roadmaps.md was ~1,287 lines covering both creation and execution concerns.

**Reality**: Slash commands typically need agents to either:
- **DRAFT a new roadmap** (`/ctb_roadmap`) - Needs structure, templates, planning guidance
- **FOLLOW an existing roadmap** (`/maceff_start_todo`) - Needs reading discipline, execution workflow, archive protocol

**Rarely both simultaneously** - Agent context benefits from focused, relevant policy content.

**Token Economics**: Reduced policy loading by ~50% per use case (650 lines vs 1,287 lines).

---

## Content Distribution Decisions

### roadmaps_drafting.md (Creation Focus)

**Sections Moved**:
1. When to create roadmaps (triggers, decision tree)
2. Folder structure requirements (organization, naming)
3. Roadmap file format (headers, mission, phase structure)
4. Phase breakdown guidelines (numbering, sizing, criteria quality)
5. Subplans (when/how to create, naming, linking)
6. Git discipline (commit-before-revise, revision tracking)
7. Templates (migration, feature dev, investigation)
8. PA vs SA distinctions (mission-level vs task-level)

**Rationale**: All concerns relevant BEFORE/DURING initial roadmap creation.

### roadmaps_following.md (Execution Focus)

**Sections Moved**:
1. Mandatory reading discipline (critical rule, why it matters)
2. TODO integration (numbered hierarchy, embedded paths, emojis)
3. Execution workflow (phase-by-phase, completion protocol, DETOUR handling)
4. Breadcrumb updates (when to add, abbreviation)
5. Friction documentation (when, structure, citation format)
6. Archive-then-collapse protocol (filename convention, contents, discipline)
7. Status tracking (DRAFT→ACTIVE→COMPLETE)

**Rationale**: All concerns relevant DURING roadmap execution.

### Shared Content (Handled via Cross-Reference)

**Archive filename conventions**: Full detail in following.md, brief reference in drafting.md
- **Why**: Archive creation happens during execution, but drafting needs awareness of archived_todos/ folder

**Breadcrumb format**: Full detail in following.md (updates during execution), brief reference in drafting.md (creation breadcrumb)
- **Why**: Drafting needs creation breadcrumb, following needs completion breadcrumbs

**PA vs SA distinctions**: Scope differences in drafting.md, execution patterns in following.md
- **Why**: Both creation and execution differ by agent type

**Philosophy section**: Full version in drafting.md, observability focus in following.md
- **Why**: Strategic understanding matters more during planning, trust matters during execution

### Duplicated Content (Minimal, Intentional)

**CEP Navigation**: Each policy has focused navigation appropriate to use case
- **Why**: Navigation must match reader's mental model (planning vs executing)

**Purpose section**: Both policies explain their scope clearly
- **Why**: Readers may land on either policy first, need clear orientation

**Anti-patterns**: Different anti-patterns for planning vs execution
- **Why**: Failure modes differ by phase (planning mistakes vs execution violations)

---

## Migration Notes for PA

### Deprecation Strategy

**Original File**: `framework/policies/base/consciousness/roadmaps.md` (1,287 lines)

**New Files**:
- `framework/policies/base/consciousness/roadmaps_drafting.md` (~650 lines)
- `framework/policies/base/consciousness/roadmaps_following.md` (~650 lines)

**Recommended Actions**:

1. **Keep original roadmaps.md temporarily** with deprecation notice:
   ```markdown
   # ⚠️ DEPRECATED: This policy has been split

   **Use instead**:
   - Creating roadmaps: `roadmaps_drafting.md`
   - Executing roadmaps: `roadmaps_following.md`

   This file will be removed in v2.1.
   ```

2. **Update slash command implementations**:
   - `/ctb_roadmap` → Load `roadmaps_drafting.md`
   - `/maceff_start_todo` → Load `roadmaps_following.md`

3. **Update policy manifest** (`framework/policies/manifest.json`):
   - Add `roadmaps_drafting.md` entry
   - Add `roadmaps_following.md` entry
   - Mark `roadmaps.md` as deprecated

4. **Test slash commands** with new policies:
   - Verify `/ctb_roadmap` has sufficient planning guidance
   - Verify `/maceff_start_todo` has sufficient execution guidance
   - Confirm no critical content missing

5. **Remove roadmaps.md** after validation period (1-2 weeks)

### Policy References Update

**Files Referencing roadmaps.md** (need updates):
- `todo_hygiene.md` (See Also section)
- `delegation_guidelines.md` (roadmap integration guidance)
- `checkpoints.md` (roadmap phase boundary CCPs)
- `reflections.md` (roadmap execution reflections)

**Update Pattern**:
```markdown
# OLD
- `roadmaps.md` - Strategic planning infrastructure

# NEW
- `roadmaps_drafting.md` - Creating strategic plans
- `roadmaps_following.md` - Executing strategic plans
```

---

## Validation Checklist

**Content Completeness**:
- ✅ All 1,287 lines from original distributed across two new policies
- ✅ No content loss during split
- ✅ Shared concepts handled via cross-reference
- ✅ Each policy independently useful

**Structural Integrity**:
- ✅ Both policies have complete meta-policy headers
- ✅ CEP navigation appropriate for each use case
- ✅ Dependencies and related policies specified
- ✅ Version numbers track split origin (v2.0 from v1.0)

**Use Case Coverage**:
- ✅ Drafting policy sufficient for creating new roadmaps
- ✅ Following policy sufficient for executing existing roadmaps
- ✅ Templates in drafting.md
- ✅ Execution protocols in following.md

**Quality Standards**:
- ✅ Project-agnostic language (no "macf" package references)
- ✅ No naked `cd` commands
- ✅ Applies to both PA and SA (location specifications provided)
- ✅ Clear separation: drafting vs following concerns

---

## Content Distribution Statistics

**Original roadmaps.md**: 1,287 lines

**New Distribution**:
- roadmaps_drafting.md: ~650 lines (50.5%)
- roadmaps_following.md: ~650 lines (50.5%)

**Overlap**: ~10 lines duplicated (purpose, philosophy excerpts)
- **Acceptable**: Orientation text for independent policy readability

**Token Savings Per Use Case**:
- Drafting: Load 650 lines instead of 1,287 (49% reduction)
- Following: Load 650 lines instead of 1,287 (49% reduction)

---

## Edge Cases Handled

### Archive Conventions (Both Use Cases Need)

**Solution**: Full detail in following.md (archive creation happens during execution), folder structure mention in drafting.md

**Rationale**: Drafters need to know archived_todos/ folder exists, executors need full archive protocol

### Friction Documentation (Primarily Execution, But Planning Mentions)

**Solution**: Full detail in following.md, risk assessment mention in drafting.md

**Rationale**: Friction discovered during execution, but risk assessment during planning can reference prior friction

### Breadcrumbs (Creation + Completion)

**Solution**: Creation breadcrumb in drafting.md header section, completion breadcrumbs in following.md

**Rationale**: Different breadcrumb purposes (artifact creation vs work completion)

### PA vs SA Scope (Affects Both)

**Solution**: Scope distinctions in drafting.md (mission-level vs task-level), execution patterns implied in following.md

**Rationale**: Planning scope differs more significantly than execution mechanics

---

## Future Considerations

### Potential Further Splits

**If policies continue growing**:
- `roadmaps_friction.md` - Friction documentation deep dive
- `roadmaps_archival.md` - Archive protocol comprehensive guide
- `roadmaps_templates.md` - Extended template library

**Current Split Sufficient**: Each policy ~650 lines, manageable for agent context

### Version Evolution

**Version Numbering**:
- Split policies: v2.0 (major restructuring)
- Original: v1.0 (deprecated)

**Future Updates**:
- Minor changes: v2.1, v2.2
- Major restructuring: v3.0

---

## Success Criteria Met

✅ **Two new policy files created** in correct location
✅ **Complete meta-policy headers** (tier, category, version, dependencies)
✅ **CEP navigation appropriate** for each use case
✅ **All original content preserved** (distributed appropriately)
✅ **Cross-references established** between policies
✅ **Clear separation**: drafting vs following concerns
✅ **Both policies independently useful** (can read one without the other)

---

## Recommendations for PA

1. **Validate with actual usage**: Test slash commands with new policies before removing original

2. **Monitor for gaps**: Track if agents request missing content from original policy

3. **Update policy manifest**: Ensure manifest.json reflects new policy structure

4. **Communicate to users**: If framework has users, announce policy split in changelog

5. **Consider backport**: If v2.0 proves valuable, consider backporting to other large policies

---

**Split Complete**: roadmaps.md (v1.0, 1,287 lines) → roadmaps_drafting.md + roadmaps_following.md (v2.0, ~650 lines each). Token-efficient, use-case-focused policies preserving all original wisdom.
