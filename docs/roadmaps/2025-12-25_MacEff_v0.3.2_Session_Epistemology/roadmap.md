# MacEff v0.3.2 - Session Identifier Epistemology ROADMAP

**Date**: 2025-12-25 Thursday
**Breadcrumb**: s_1b969d39/c_311/g_bf70468/p_3d47b051/t_1766714561
**Status**: ACTIVE
**Context**: Session ID variance discovered between hooks - need consistent identifier semantics

---

## Mission

Establish complete epistemology for Claude Code session/transcript identifiers, fix the session ID variance bug in breadcrumb generation, and document the identifier hierarchy for future development.

**WHY**: The `s_` field in breadcrumbs should reliably point to the active session file. Currently, `get_current_session_id()` uses file mtime which causes non-deterministic results when multiple session files are being written concurrently.

**SUCCESS**:
- All hooks report consistent session ID within a session
- Complete documentation of identifier semantics (session UUID, cycle, prompt UUID, delegation sidechain UUID)
- Clear understanding of `claude -c` behavior documented

---

## Phase 1: Session ID Variance Fix

**Goal**: Make session ID deterministic and consistent across all hooks

**Root Cause**:
- `macf/src/macf/utils/session.py:31-32` sorts by `st_mtime`
- When multiple `.jsonl` files exist, whichever was modified most recently wins
- After `claude -c`, BOTH old and new files are being written to concurrently

**Solution**: Query `session_started` event from event log (event-first architecture)

**Deliverables**:
- `get_current_session_id_from_events()` in event_queries.py
- Updated `get_current_session_id()` to use event query first

**Success Criteria**:
- [ ] All hooks in same session report identical `s_` value
- [ ] Test: `claude -c` restart shows consistent session ID post-restart
- [ ] No mtime-based session detection in hot path

**Breadcrumb** (when complete):

---

## Phase 2: Identifier Epistemology Documentation

**Goal**: Complete reference documentation for all MACF identifiers

**Deliverables**:
- `macf/docs/user/identifiers.md` - Complete reference

**Success Criteria**:
- [ ] All 5 breadcrumb components documented with semantics
- [ ] `claude -c` vs compaction behavior explained
- [ ] Delegation sidechain UUID tracking documented

**Breadcrumb** (when complete):

---

## Phase 3: Experimental Validation

**Goal**: Validate understanding through controlled experiments

**Experiments**:
- E1: `claude -c` - verify new session UUID, same cycle
- E2: `/compact` - verify same session UUID, new cycle
- E3: Multiple hooks in same session - verify consistent `s_`

**Success Criteria**:
- [ ] All experiments pass with documented results
- [ ] Any discrepancies investigated and resolved

**Breadcrumb** (when complete):

---

## Phase 4: Test Coverage

**Goal**: Prevent regression of session ID consistency

**Deliverables**:
- `test_session_id_consistency.py`
- `test_breadcrumb_components.py`

**Success Criteria**:
- [ ] Tests pass in CI
- [ ] Coverage for session ID edge cases

**Breadcrumb** (when complete):

---

## References

- Plan file: `/Users/cversek/.claude/plans/elegant-floating-panda.md`
- Current implementation: `macf/src/macf/utils/session.py`
- Breadcrumb generation: `macf/src/macf/utils/breadcrumbs.py`
- Exploration findings: Agent ab21edf, ace3628
