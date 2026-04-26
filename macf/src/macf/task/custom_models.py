"""
Pydantic models for task-type custom dicts.

Each class validates the `custom` field of MacfTaskMetaData for a specific
task type. These are opt-in validators — the MTMD `custom` field remains a
plain dict for all other task types.

Supported task types:
- SprintCustom   — 🏃‍♂️ SPRINT: workload-defined autonomous work (no timer)
- PlayTimeCustom — ⏲️ PLAY_TIME: time-bounded autonomous play

Policy spec:
  framework/policies/base/operations/autonomous_sprint.md  (SPRINT)
  framework/policies/base/operations/play_time.md          (PLAY_TIME)
  framework/policies/base/development/task_management.md §2.6, §2.7
"""

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from ..modes.detection import WORK_MODES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_work_mode_names() -> set[str]:
    """Return the set of all known work-mode names."""
    return set(WORK_MODES.keys())


# ---------------------------------------------------------------------------
# SprintCustom — 🏃‍♂️ SPRINT task type
# ---------------------------------------------------------------------------

class SprintCustom(BaseModel):
    """
    Validates the ``custom`` dict for a SPRINT task.

    SPRINT is workload-defined autonomous work:
    - NO timer (timer fields are absent by design)
    - Work mode locked at SPRINT throughout
    - Stop hook nags about uncompleted scoped tasks
    - Markov recommender is disabled while SPRINT mode is active

    Policy: autonomous_sprint.md, task_management.md §2.6
    """

    goal: str = Field(..., description="One-sentence statement of sprint objective")
    scoped_task_ids: list[int] = Field(
        default_factory=list,
        description="Task IDs explicitly scoped to this sprint",
    )
    scoped_progress: dict[str, int] = Field(
        default_factory=lambda: {"completed": 0, "total": 0},
        description="Completion counters: {completed, total}",
    )
    ideas_captured: int = Field(default=0, description="Count of 💡-prefix notes added")
    learnings_curated: int = Field(default=0, description="Count of learning files created")
    initial_work_mode: Literal["SPRINT"] = Field(
        default="SPRINT",
        description="Always SPRINT for this task type — enforced as literal",
    )
    closure_invoked: bool = Field(
        default=False,
        description="True once the sprint completion sequence has run",
    )

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

    @field_validator("goal")
    @classmethod
    def goal_non_empty_and_bounded(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("goal must not be empty")
        if len(v) > 500:
            raise ValueError(f"goal exceeds 500 chars (got {len(v)})")
        return v

    @field_validator("scoped_task_ids")
    @classmethod
    def scoped_task_ids_all_positive(cls, v: list[int]) -> list[int]:
        for tid in v:
            if tid <= 0:
                raise ValueError(f"scoped_task_ids must all be positive ints; got {tid}")
        return v

    @field_validator("scoped_progress")
    @classmethod
    def scoped_progress_valid(cls, v: dict[str, int]) -> dict[str, int]:
        if "completed" not in v or "total" not in v:
            raise ValueError("scoped_progress must have keys 'completed' and 'total'")
        completed = v["completed"]
        total = v["total"]
        if completed < 0 or total < 0:
            raise ValueError("scoped_progress values must be >= 0")
        if completed > total:
            raise ValueError(
                f"scoped_progress.completed ({completed}) must be <= total ({total})"
            )
        return v

    @field_validator("ideas_captured", "learnings_curated")
    @classmethod
    def counts_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("count fields must be >= 0")
        return v

    # -----------------------------------------------------------------------
    # Round-trip helpers
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict suitable for embedding in MTMD ``custom``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SprintCustom":
        """Deserialize from plain dict (e.g., from parsed MTMD YAML)."""
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# PlayTimeCustom — ⏲️ PLAY_TIME task type
# ---------------------------------------------------------------------------

class PlayTimeCustom(BaseModel):
    """
    Validates the ``custom`` dict for a PLAY_TIME task.

    PLAY_TIME is time-bounded autonomous exploration:
    - MANDATORY timer (timer_minutes > 0)
    - Predetermined chain of work modes the agent declares upfront
    - Markov recommender engages ONLY after chain exhaustion
    - Stop hook fires timer gate + Markov + T-15 wind-down

    Design decisions (documented for future maintainers):
    - chain_exhausted is VALIDATED for consistency with chain_position
      rather than auto-derived, because MTMD is serialized/deserialized from
      YAML and the value should always be an explicit committed state.
      Inconsistent values (e.g., chain_exhausted=True when position < len)
      are rejected outright.
    - current_work_mode may not be SPRINT; PLAY_TIME uses rotatable modes only.
      If mode locking is needed, the agent should be in a SPRINT task instead.

    Policy: play_time.md, task_management.md §2.7
    """

    goal: str = Field(..., description="One-sentence statement of play session objective")

    # Timer fields (all required at creation time)
    timer_minutes: int = Field(..., description="Session duration in minutes (> 0)")
    timer_started_at: int = Field(..., description="Epoch second when timer started")
    timer_expires_at: int = Field(..., description="Epoch second when timer expires (= started + minutes*60)")
    timer_cleared_at: Optional[int] = Field(
        default=None,
        description="Epoch second when timer was manually cleared (null = still running)",
    )

    # Predetermined chain
    predetermined_chain: list[str] = Field(
        default_factory=lambda: ["DISCOVER"],
        description="Ordered list of work-mode names the agent will cycle through",
    )
    chain_position: int = Field(
        default=0,
        description="0-indexed pointer into predetermined_chain (0 = not started)",
    )
    chain_exhausted: bool = Field(
        default=False,
        description="True when chain_position >= len(predetermined_chain); Markov takes over",
    )

    # Live mode state
    initial_work_mode: str = Field(
        ...,
        description="First mode of the session; must equal predetermined_chain[0]",
    )
    current_work_mode: str = Field(
        ...,
        description="Current work mode; must be a valid mode name; must not be SPRINT",
    )
    mode_transitions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Log of mode transitions (schema may evolve — any dict accepted)",
    )
    markov_gates: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Log of Markov gate decisions (schema may evolve — any dict accepted)",
    )

    # Progress counters
    ideas_captured: int = Field(default=0, description="Count of 💡-prefix notes added")
    learnings_curated: int = Field(default=0, description="Count of learning files created")

    # Lifecycle
    wind_down_started_at: Optional[int] = Field(
        default=None,
        description="Epoch when T-15 wind-down sequence began (null = not started)",
    )
    closure_invoked: bool = Field(
        default=False,
        description="True once the play_time completion sequence has run",
    )

    # -----------------------------------------------------------------------
    # Field-level validators
    # -----------------------------------------------------------------------

    @field_validator("goal")
    @classmethod
    def goal_non_empty_and_bounded(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("goal must not be empty")
        if len(v) > 500:
            raise ValueError(f"goal exceeds 500 chars (got {len(v)})")
        return v

    @field_validator("timer_minutes")
    @classmethod
    def timer_minutes_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"timer_minutes must be > 0; got {v}")
        return v

    @field_validator("predetermined_chain")
    @classmethod
    def chain_non_empty_and_valid_modes(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("predetermined_chain must not be empty")
        valid = _valid_work_mode_names()
        # SPRINT is a locked mode — it cannot appear in PLAY_TIME's rotatable chain
        rotatable = valid - {"SPRINT"}
        for mode in v:
            if mode not in rotatable:
                if mode == "SPRINT":
                    raise ValueError(
                        "SPRINT may not appear in predetermined_chain; "
                        "SPRINT mode is reserved for the SPRINT task type "
                        "and is not a rotatable PLAY_TIME mode"
                    )
                raise ValueError(
                    f"predetermined_chain contains invalid work mode '{mode}'; "
                    f"valid rotatable modes: {sorted(rotatable)}"
                )
        return v

    @field_validator("chain_position")
    @classmethod
    def chain_position_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"chain_position must be >= 0; got {v}")
        return v

    @field_validator("current_work_mode")
    @classmethod
    def current_work_mode_not_sprint(cls, v: str) -> str:
        if v == "SPRINT":
            raise ValueError(
                "PLAY_TIME current_work_mode may not be SPRINT; "
                "SPRINT mode is reserved for the SPRINT task type"
            )
        valid = _valid_work_mode_names()
        if v not in valid:
            raise ValueError(
                f"current_work_mode '{v}' is not a valid work mode; "
                f"valid modes: {sorted(valid)}"
            )
        return v

    @field_validator("ideas_captured", "learnings_curated")
    @classmethod
    def counts_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("count fields must be >= 0")
        return v

    # -----------------------------------------------------------------------
    # Model-level validators (cross-field)
    # -----------------------------------------------------------------------

    @model_validator(mode="after")
    def validate_timer_expires_at(self) -> "PlayTimeCustom":
        """timer_expires_at must equal timer_started_at + timer_minutes * 60."""
        expected = self.timer_started_at + self.timer_minutes * 60
        if self.timer_expires_at != expected:
            raise ValueError(
                f"timer_expires_at ({self.timer_expires_at}) must equal "
                f"timer_started_at + timer_minutes*60 = {expected}"
            )
        return self

    @model_validator(mode="after")
    def validate_chain_position_bounds(self) -> "PlayTimeCustom":
        """chain_position must be 0 <= position <= len(chain)."""
        n = len(self.predetermined_chain)
        if self.chain_position > n:
            raise ValueError(
                f"chain_position ({self.chain_position}) must be <= "
                f"len(predetermined_chain) ({n})"
            )
        return self

    @model_validator(mode="after")
    def validate_chain_exhausted_consistency(self) -> "PlayTimeCustom":
        """chain_exhausted must equal (chain_position >= len(predetermined_chain) - 1).

        Updated semantics (Phase 8 friction fix): "exhausted" means the agent
        is currently at the LAST chain entry (no more advances are possible),
        not "advanced past the end" (which never happens — there's no
        chain[N] to advance to). With the old `>=` (no -1), chain_exhausted
        could never reach True via advance_play_time_chain, leaving Markov
        gating perpetually disabled.

        For chain of length 1: position=0 already satisfies the condition
        (already at the last entry).

        Design choice: REJECT inconsistent values rather than silently coercing.
        This makes stale/corrupt MTMD visible at deserialization time instead of
        silently propagating wrong state through hook logic.
        """
        n = len(self.predetermined_chain)
        expected_exhausted = self.chain_position >= max(0, n - 1)
        if self.chain_exhausted != expected_exhausted:
            raise ValueError(
                f"chain_exhausted={self.chain_exhausted} is inconsistent: "
                f"chain_position={self.chain_position}, len(chain)={n}, "
                f"expected chain_exhausted={expected_exhausted}"
            )
        return self

    @model_validator(mode="after")
    def validate_initial_work_mode(self) -> "PlayTimeCustom":
        """initial_work_mode must equal predetermined_chain[0]."""
        expected = self.predetermined_chain[0]
        if self.initial_work_mode != expected:
            raise ValueError(
                f"initial_work_mode='{self.initial_work_mode}' must equal "
                f"predetermined_chain[0]='{expected}'"
            )
        return self

    # -----------------------------------------------------------------------
    # Round-trip helpers
    # -----------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict suitable for embedding in MTMD ``custom``."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlayTimeCustom":
        """Deserialize from plain dict (e.g., from parsed MTMD YAML)."""
        return cls.model_validate(data)
