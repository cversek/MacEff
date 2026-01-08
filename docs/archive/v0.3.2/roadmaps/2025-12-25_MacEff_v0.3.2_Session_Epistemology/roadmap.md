# MacEff v0.3.2 - Session Identifier Epistemology ROADMAP

**Date**: 2025-12-25 Thursday
**Breadcrumb**: s_abc12345/c_42/g_def6789/p_ghi01234/t_1234567890
**Status**: COMPLETE
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
- [x] All hooks in same session report identical `s_` value
- [x] Test: `claude -c` restart shows consistent session ID post-restart
- [x] No mtime-based session detection in hot path

**Breadcrumb**: s_abc12345/c_42/g_5f083be [C311]

---

## Phase 2: Identifier Epistemology Documentation

**Goal**: Complete reference documentation for all MACF identifiers

**Deliverables**:
- `macf/docs/user/identifiers.md` - Complete reference

**Success Criteria**:
- [x] All 5 breadcrumb components documented with semantics
- [x] `claude -c` vs compaction behavior explained
- [x] Delegation sidechain UUID tracking documented

**Breadcrumb**: s_abc12345/c_42/g_bf8431f [C312]

---

## Phase 3: Experimental Validation

**Goal**: Validate understanding through controlled experiments

**Experiments**:
- E1: `claude -c` - verify new session UUID, same cycle
- E2: `/compact` - verify same session UUID, new cycle
- E3: Multiple hooks in same session - verify consistent `s_`

**Success Criteria**:
- [x] All experiments pass with documented results
- [x] Any discrepancies investigated and resolved

**Breadcrumb**: s_abc12345/c_42/g_6ffe691 [C312]

**Results**:
- E1: `claude -c` creates new session file, same cycle (C311 verified)
- E2: `/compact` triggers compaction, cycle increments (C311→C312 transition)
- E3: All hooks report consistent `s_1b969d39` after fix

---

## Phase 4: Test Coverage

**Goal**: Prevent regression of session ID consistency

**Deliverables**:
- `test_session_id_consistency.py`
- `test_breadcrumb_components.py`

**Success Criteria**:
- [x] Tests pass in CI
- [x] Coverage for session ID edge cases

**Breadcrumb**: s_abc12345/c_42/g_e6f345b [C312]

**Notes**:
- 323 tests passing (322 + 1 fixed)
- test_session.py covers session ID extraction (8 tests)
- test_time_cli.py updated to allow MACF fallback warnings

---

## References

- Plan file: `/Users/cversek/.claude/plans/elegant-floating-panda.md`
- Current implementation: `macf/src/macf/utils/session.py`
- Breadcrumb generation: `macf/src/macf/utils/breadcrumbs.py`
- Exploration findings: Agent ab21edf, ace3628
