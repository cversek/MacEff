"""
Unit tests for task-type custom dict Pydantic models.

Covers:
- SprintCustom   — 🏃‍♂️ SPRINT workload-defined autonomous work
- PlayTimeCustom — ⏲️ PLAY_TIME time-bounded autonomous play
- SPRINT work-mode enum extension in detection.py
- Mode-lock helper (apply_sprint_mode_lock) and Markov gate (is_markov_eligible)

Test count: 14 tests (8+ per spec).
"""

import pytest
from pydantic import ValidationError

from macf.task.custom_models import SprintCustom, PlayTimeCustom
from macf.modes.detection import (
    WORK_MODES,
    DEFAULT_TRANSITIONS,
    DEFAULT_SKILL_MAP,
    is_markov_eligible,
    apply_sprint_mode_lock,
)


# ===========================================================================
# Helpers / fixtures
# ===========================================================================

def _minimal_sprint(**overrides) -> dict:
    """Minimal valid SprintCustom dict."""
    base = {"goal": "Run the full build pipeline"}
    base.update(overrides)
    return base


def _minimal_play_time(**overrides) -> dict:
    """Minimal valid PlayTimeCustom dict.

    timer_expires_at is always derived from timer_started_at + timer_minutes*60
    unless explicitly overridden.
    """
    started = overrides.pop("timer_started_at", 1_000_000)
    minutes = overrides.pop("timer_minutes", 60)
    expires = overrides.pop("timer_expires_at", started + minutes * 60)
    chain = overrides.pop("predetermined_chain", ["DISCOVER"])
    position = overrides.pop("chain_position", 0)
    exhausted = overrides.pop("chain_exhausted", position >= len(chain))
    initial = overrides.pop("initial_work_mode", chain[0])
    current = overrides.pop("current_work_mode", chain[0])

    base = {
        "goal": "Explore CC internals for 60 min",
        "timer_minutes": minutes,
        "timer_started_at": started,
        "timer_expires_at": expires,
        "predetermined_chain": chain,
        "chain_position": position,
        "chain_exhausted": exhausted,
        "initial_work_mode": initial,
        "current_work_mode": current,
    }
    base.update(overrides)
    return base


# ===========================================================================
# SprintCustom tests
# ===========================================================================

class TestSprintCustom:

    # -----------------------------------------------------------------------
    # Test 1: Round-trip
    # -----------------------------------------------------------------------
    def test_round_trip(self):
        """dict → model → dict produces identical output."""
        data = {
            "goal": "Run pipeline on 7 CC versions",
            "scoped_task_ids": [101, 102, 103],
            "scoped_progress": {"completed": 2, "total": 3},
            "ideas_captured": 1,
            "learnings_curated": 0,
            "initial_work_mode": "SPRINT",
            "closure_invoked": False,
        }
        model = SprintCustom.from_dict(data)
        result = model.to_dict()
        assert result == data

    # -----------------------------------------------------------------------
    # Test 2: Reject non-SPRINT initial_work_mode
    # -----------------------------------------------------------------------
    def test_reject_non_sprint_initial_work_mode(self):
        """Model must reject any initial_work_mode other than 'SPRINT'."""
        with pytest.raises(ValidationError) as exc_info:
            SprintCustom.from_dict(_minimal_sprint(initial_work_mode="DISCOVER"))
        # Pydantic Literal enforcement surfaces as validation error
        assert "initial_work_mode" in str(exc_info.value) or "SPRINT" in str(exc_info.value)

    # -----------------------------------------------------------------------
    # Test 3: Reject scoped_progress with completed > total
    # -----------------------------------------------------------------------
    def test_reject_scoped_progress_completed_exceeds_total(self):
        """completed > total must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            SprintCustom.from_dict(_minimal_sprint(
                scoped_progress={"completed": 5, "total": 3}
            ))
        assert "completed" in str(exc_info.value) or "total" in str(exc_info.value)

    # -----------------------------------------------------------------------
    # Test 4: Reject empty goal
    # -----------------------------------------------------------------------
    def test_reject_empty_goal(self):
        """goal must not be empty or whitespace-only."""
        with pytest.raises(ValidationError):
            SprintCustom.from_dict(_minimal_sprint(goal=""))
        with pytest.raises(ValidationError):
            SprintCustom.from_dict(_minimal_sprint(goal="   "))

    # -----------------------------------------------------------------------
    # Test 5: Default values populate correctly from minimal init
    # -----------------------------------------------------------------------
    def test_defaults_populated_from_minimal_init(self):
        """All defaulted fields should have correct zero/false values."""
        model = SprintCustom.from_dict({"goal": "Minimal sprint"})
        assert model.scoped_task_ids == []
        assert model.scoped_progress == {"completed": 0, "total": 0}
        assert model.ideas_captured == 0
        assert model.learnings_curated == 0
        assert model.initial_work_mode == "SPRINT"
        assert model.closure_invoked is False

    # -----------------------------------------------------------------------
    # Additional coverage: scoped_progress missing keys
    # -----------------------------------------------------------------------
    def test_reject_scoped_progress_missing_keys(self):
        """scoped_progress must have both 'completed' and 'total' keys."""
        with pytest.raises(ValidationError):
            SprintCustom.from_dict(_minimal_sprint(
                scoped_progress={"completed": 1}  # missing 'total'
            ))

    # -----------------------------------------------------------------------
    # Additional coverage: negative scoped_task_ids
    # -----------------------------------------------------------------------
    def test_reject_non_positive_scoped_task_ids(self):
        """All scoped_task_ids must be positive ints."""
        with pytest.raises(ValidationError):
            SprintCustom.from_dict(_minimal_sprint(scoped_task_ids=[1, 0, 3]))
        with pytest.raises(ValidationError):
            SprintCustom.from_dict(_minimal_sprint(scoped_task_ids=[-5]))


# ===========================================================================
# PlayTimeCustom tests
# ===========================================================================

class TestPlayTimeCustom:

    # -----------------------------------------------------------------------
    # Test 6: Round-trip
    # -----------------------------------------------------------------------
    def test_round_trip(self):
        """dict → model → dict produces identical output.

        All fields (including those with defaults) must be present in the
        input so the serialized output matches exactly. This mirrors how a
        real MTMD YAML block would look after the first write.
        """
        data = {
            "goal": "Explore CC internals for 45 min",
            "timer_minutes": 45,
            "timer_started_at": 2_000_000,
            "timer_expires_at": 2_000_000 + 45 * 60,
            "timer_cleared_at": None,
            "predetermined_chain": ["DISCOVER", "EXPERIMENT"],
            "chain_position": 0,
            "chain_exhausted": False,
            "initial_work_mode": "DISCOVER",
            "current_work_mode": "DISCOVER",
            "mode_transitions": [],
            "markov_gates": [],
            "ideas_captured": 3,
            "learnings_curated": 1,
            "wind_down_started_at": None,
            "closure_invoked": False,
        }
        model = PlayTimeCustom.from_dict(data)
        result = model.to_dict()
        assert result == data

    # -----------------------------------------------------------------------
    # Test 7: Reject missing timer_minutes / timer_minutes <= 0
    # -----------------------------------------------------------------------
    def test_reject_missing_timer_minutes(self):
        """timer_minutes is required."""
        data = _minimal_play_time()
        del data["timer_minutes"]
        with pytest.raises(ValidationError):
            PlayTimeCustom.from_dict(data)

    def test_reject_zero_timer_minutes(self):
        """timer_minutes = 0 must be rejected."""
        with pytest.raises(ValidationError):
            PlayTimeCustom.from_dict(_minimal_play_time(
                timer_minutes=0,
                timer_expires_at=1_000_000 + 0,  # override to avoid derived check masking
            ))

    def test_reject_negative_timer_minutes(self):
        """timer_minutes < 0 must be rejected."""
        with pytest.raises(ValidationError):
            PlayTimeCustom.from_dict(_minimal_play_time(
                timer_minutes=-10,
                timer_expires_at=1_000_000 + (-10) * 60,
            ))

    # -----------------------------------------------------------------------
    # Test 8: Validate timer_expires_at == timer_started_at + timer_minutes*60
    # -----------------------------------------------------------------------
    def test_timer_expires_at_invariant(self):
        """timer_expires_at must equal timer_started_at + timer_minutes * 60."""
        with pytest.raises(ValidationError) as exc_info:
            PlayTimeCustom.from_dict(_minimal_play_time(
                timer_started_at=1_000_000,
                timer_minutes=60,
                timer_expires_at=1_000_000 + 59 * 60,  # off by 60 seconds
            ))
        assert "timer_expires_at" in str(exc_info.value)

    def test_timer_expires_at_correct_accepted(self):
        """Correct timer_expires_at is accepted without error."""
        started = 1_500_000
        minutes = 30
        model = PlayTimeCustom.from_dict(_minimal_play_time(
            timer_started_at=started,
            timer_minutes=minutes,
            timer_expires_at=started + minutes * 60,
        ))
        assert model.timer_expires_at == started + minutes * 60

    # -----------------------------------------------------------------------
    # Test 9: Reject predetermined_chain with invalid mode name
    # -----------------------------------------------------------------------
    def test_reject_invalid_mode_in_chain(self):
        """predetermined_chain entries must all be valid work-mode names."""
        with pytest.raises(ValidationError) as exc_info:
            PlayTimeCustom.from_dict(_minimal_play_time(
                predetermined_chain=["DISCOVER", "BOGUS_MODE"],
                chain_position=0,
                chain_exhausted=False,
                initial_work_mode="DISCOVER",
                current_work_mode="DISCOVER",
            ))
        assert "BOGUS_MODE" in str(exc_info.value) or "invalid work mode" in str(exc_info.value)

    def test_reject_sprint_in_chain(self):
        """SPRINT is not a rotatable mode and must not appear in predetermined_chain."""
        with pytest.raises(ValidationError):
            PlayTimeCustom.from_dict(_minimal_play_time(
                predetermined_chain=["SPRINT"],
                chain_position=0,
                chain_exhausted=False,
                initial_work_mode="SPRINT",
                current_work_mode="DISCOVER",  # valid current, but chain is bad
            ))

    # -----------------------------------------------------------------------
    # Test 10: chain_exhausted must be consistent with chain_position
    # -----------------------------------------------------------------------
    def test_chain_exhausted_consistency_reject_wrong_true(self):
        """chain_exhausted=True when position < len(chain) must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PlayTimeCustom.from_dict(_minimal_play_time(
                predetermined_chain=["DISCOVER", "EXPERIMENT"],
                chain_position=1,   # not exhausted (1 < 2)
                chain_exhausted=True,  # inconsistent
                initial_work_mode="DISCOVER",
                current_work_mode="EXPERIMENT",
            ))
        assert "chain_exhausted" in str(exc_info.value) or "inconsistent" in str(exc_info.value)

    def test_chain_exhausted_consistency_reject_wrong_false(self):
        """chain_exhausted=False when position >= len(chain) must be rejected."""
        with pytest.raises(ValidationError) as exc_info:
            PlayTimeCustom.from_dict(_minimal_play_time(
                predetermined_chain=["DISCOVER"],
                chain_position=1,    # exhausted (1 >= 1)
                chain_exhausted=False,  # inconsistent
                initial_work_mode="DISCOVER",
                current_work_mode="DISCOVER",
            ))
        assert "chain_exhausted" in str(exc_info.value) or "inconsistent" in str(exc_info.value)

    def test_chain_exhausted_consistency_accept_correct(self):
        """chain_exhausted=True when position == len(chain) must be accepted."""
        model = PlayTimeCustom.from_dict(_minimal_play_time(
            predetermined_chain=["DISCOVER", "CURATE"],
            chain_position=2,   # exhausted
            chain_exhausted=True,
            initial_work_mode="DISCOVER",
            current_work_mode="CURATE",
        ))
        assert model.chain_exhausted is True

    # -----------------------------------------------------------------------
    # Test 11: Reject current_work_mode == "SPRINT"
    # -----------------------------------------------------------------------
    def test_reject_sprint_as_current_work_mode(self):
        """PLAY_TIME may not have current_work_mode == 'SPRINT'."""
        with pytest.raises(ValidationError) as exc_info:
            PlayTimeCustom.from_dict(_minimal_play_time(
                current_work_mode="SPRINT",
            ))
        assert "SPRINT" in str(exc_info.value)

    # -----------------------------------------------------------------------
    # Additional: initial_work_mode must equal chain[0]
    # -----------------------------------------------------------------------
    def test_reject_initial_work_mode_mismatch(self):
        """initial_work_mode must match predetermined_chain[0]."""
        with pytest.raises(ValidationError) as exc_info:
            PlayTimeCustom.from_dict(_minimal_play_time(
                predetermined_chain=["EXPERIMENT", "BUILD"],
                chain_position=0,
                chain_exhausted=False,
                initial_work_mode="DISCOVER",  # mismatch: chain[0] is EXPERIMENT
                current_work_mode="EXPERIMENT",
            ))
        assert "initial_work_mode" in str(exc_info.value)


# ===========================================================================
# Work-mode enum tests
# ===========================================================================

class TestSprintWorkMode:

    # -----------------------------------------------------------------------
    # Test 12: SPRINT in WORK_MODES with correct emoji
    # -----------------------------------------------------------------------
    def test_sprint_in_work_modes(self):
        """SPRINT must appear in the WORK_MODES dict."""
        assert "SPRINT" in WORK_MODES

    def test_sprint_emoji(self):
        """SPRINT emoji must be the male-runner 🏃‍♂️ (ZWJ sequence preserved)."""
        emoji = WORK_MODES["SPRINT"]["emoji"]
        assert emoji == "🏃‍♂️"

    def test_sprint_order_after_consolidate(self):
        """SPRINT order value must be higher than CONSOLIDATE (order=14)."""
        sprint_order = WORK_MODES["SPRINT"]["order"]
        consolidate_order = WORK_MODES["CONSOLIDATE"]["order"]
        assert sprint_order > consolidate_order

    # -----------------------------------------------------------------------
    # Test 13: SPRINT absent from transition matrix (no row, no column)
    # -----------------------------------------------------------------------
    def test_sprint_not_a_transition_source(self):
        """SPRINT must not appear as a row (source) in DEFAULT_TRANSITIONS."""
        assert "SPRINT" not in DEFAULT_TRANSITIONS

    def test_sprint_not_a_transition_target(self):
        """SPRINT must not appear as a column (target) in any transition row."""
        for source, row in DEFAULT_TRANSITIONS.items():
            assert "SPRINT" not in row, (
                f"SPRINT found as transition target from '{source}'"
            )

    def test_sprint_in_skill_map(self):
        """SPRINT must have an entry in DEFAULT_SKILL_MAP for dispatch completeness."""
        assert "SPRINT" in DEFAULT_SKILL_MAP
        assert DEFAULT_SKILL_MAP["SPRINT"] == "sprint-self-motivation"

    # -----------------------------------------------------------------------
    # Test 14: Mode-lock and Markov gate helpers
    # -----------------------------------------------------------------------
    def test_is_markov_eligible_sprint_false(self):
        """Markov recommender must be ineligible when current mode is SPRINT."""
        assert is_markov_eligible("SPRINT") is False

    def test_is_markov_eligible_other_modes_true(self):
        """Markov recommender must be eligible for all non-SPRINT modes."""
        for mode in ["DISCOVER", "EXPERIMENT", "BUILD", "CURATE", "CONSOLIDATE", None]:
            assert is_markov_eligible(mode) is True, f"Expected eligible for mode={mode!r}"

    def test_sprint_mode_lock_warns_and_noops(self, capsys):
        """apply_sprint_mode_lock: requesting DISCOVER while in SPRINT warns and returns SPRINT."""
        result = apply_sprint_mode_lock(
            requested_mode="DISCOVER",
            current_work_mode="SPRINT",
        )
        assert result == "SPRINT"
        captured = capsys.readouterr()
        assert "SPRINT" in captured.err
        assert "locked" in captured.err.lower() or "rejected" in captured.err.lower()

    def test_sprint_mode_lock_passthrough_when_not_sprint(self):
        """apply_sprint_mode_lock: mode change allowed when not currently in SPRINT."""
        result = apply_sprint_mode_lock(
            requested_mode="BUILD",
            current_work_mode="DISCOVER",
        )
        assert result == "BUILD"

    def test_sprint_mode_lock_passthrough_when_no_current_mode(self):
        """apply_sprint_mode_lock: mode change allowed when current mode is None."""
        result = apply_sprint_mode_lock(
            requested_mode="EXPERIMENT",
            current_work_mode=None,
        )
        assert result == "EXPERIMENT"
