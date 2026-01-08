# MISSION: MacEff v0.3.1 Refinement & Bug Fix Phase

**Date**: 2025-12-22 (Monday)
**Status**: ACTIVE
**Context**: Post v0.3.0 release stabilization and enhancement cycle

---

## Mission

Build upon the v0.3.0 foundation with targeted refinements, bug fixes, and documentation improvements. This release cycle focuses on polish rather than major features, addressing issues discovered during deployment validation while completing deferred enhancements.

The v0.3.0 release shipped Named Agents Architecture, Event-First Architecture, and Policy CLI Suite. v0.3.1 continues this work by improving discoverability (search indexing), fixing friction points as they emerge, and ensuring documentation matches implementation reality.

Success means: stable framework operation, improved policy discovery via search indexing, comprehensive documentation, and any friction points from v0.3.0 deployment resolved.

---

## Phase 1: Search Index Foundation

**Goal**: Enable faster policy discovery through keyword-to-section indexing.

**Deliverables**:
- Search index generation for policy manifest
- Keyword extraction from policy content
- Integration with `macf_tools policy search`

**Success Criteria**:
- [ ] Search index generated from policy manifest
- [ ] Keyword-to-section mapping implemented
- [ ] `policy search <keyword>` returns section-level results
- [ ] Tests covering search functionality

---

## Phase 2: Bug Fixes & Refinements

**Goal**: Address issues discovered during v0.3.0 deployment and usage.

**Deliverables**:
- Fixes for reported friction points
- Hook edge case handling
- Container operation improvements

**Success Criteria**:
- [ ] No critical bugs from v0.3.0 deployment
- [ ] Friction points documented and resolved
- [ ] All existing tests continue passing

**Note**: This phase expands as issues are discovered. Items added as sub-phases (2.1, 2.2, etc.) when specific bugs identified.

---

## Phase 3: Documentation Polish

**Goal**: Ensure documentation is comprehensive, accurate, and accessible.

**Deliverables**:
- CHANGELOG updates for v0.3.1
- README improvements across repositories
- User guide refinements

**Success Criteria**:
- [ ] CHANGELOG reflects all v0.3.1 changes
- [ ] README accurately describes current capabilities
- [ ] No documentation-reality gaps
- [ ] Quick start guides tested and validated

---

## Release Criteria

**v0.3.1 ships when**:
- [ ] Phase 1 (Search Index) complete or explicitly deferred
- [ ] Phase 2 (Bug Fixes) has no critical open items
- [ ] Phase 3 (Docs) reflects accurate state
- [ ] All tests passing (307+ baseline from v0.3.0)
- [ ] CHANGELOG.md updated with v0.3.1 section

---

## References

- Prior release: [v0.3.0 CHANGELOG](../../CHANGELOG.md)
- Named Agents Architecture: [docs/arch_v0.3_named_agents/INDEX.md](../../arch_v0.3_named_agents/INDEX.md)
- Policy CLI: [macf/docs/user/cli-reference.md](../../../macf/docs/user/cli-reference.md)
