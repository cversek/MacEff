"""Role and Duty records, as the roles policy defines them.

Closed schemas (``extra="forbid"``): a mistyped key in a role file is a control
the author believes exists and does not. Constraints that are not obvious carry
their reason in the validator, where the next reader meets them.
"""
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .cadence import CadenceError, parse_cadence, parse_horizon_minutes

ID_RE = re.compile(r"^[0-9a-f]{6}$")

ROLE_STATES = ("active", "paused", "expired", "retired")
ROLE_MACHINE = {
    "active": ["paused", "expired", "retired"],
    "paused": ["active", "expired", "retired"],
    "expired": [],
    "retired": [],
}

DUTY_STATES = ("pending", "active", "done", "deferred")
DUTY_MACHINE = {
    "pending": ["active", "done", "deferred"],
    "active": ["done", "deferred", "pending"],
    "deferred": ["pending", "active"],
    "done": [],
}

IMPORTANCE = ("critical", "high", "normal", "low")

# The ten-icon shelf from the policy. A vocabulary, not a constraint: the
# operator's own glyph is always accepted by the record.
ICON_SHELF = {
    "🎓": "teaching, academic",
    "🎩": "steward, officer",
    "🧢": "coach, trainer",
    "⛑️": "on-call, safety, operations",
    "👑": "lead, owner",
    "🪖": "guard, security",
    "📚": "librarian, custodian",
    "🗄️": "archivist",
    "🔬": "researcher, analyst",
    "⚖️": "reviewer, adjudicator",
}


def _check_id(v: str) -> str:
    if not ID_RE.match(v or ""):
        raise ValueError(f"id must be six lowercase hex characters, not {v!r}")
    return v


class Update(BaseModel):
    """One timestamped note, the same shape a task update has.

    ``done_on`` marks a completed occurrence of a cadence duty; ``kind`` tells
    the reader what the touch was (note, start, done, defer, review, ...), so
    'last serviced' can be computed without parsing prose.
    """
    model_config = ConfigDict(extra="forbid")

    breadcrumb: str
    description: str = ""
    at: str                                   # ISO-8601 local time, second precision
    agent: Optional[str] = None
    kind: str = "note"
    done_on: Optional[date] = None


class Role(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    icon: str = "🎭"
    state: str = "active"
    tenure_start: date
    expires: Optional[date] = None
    review_by: Optional[date] = None
    review_horizon: Optional[str] = None      # 14d, reasoned like a duty's
    charter_ref: str = "charter.md"
    resources: List[str] = Field(default_factory=list)
    wiki_links: List[str] = Field(default_factory=list)
    updates: List[Update] = Field(default_factory=list)

    _id = field_validator("id")(_check_id)

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in ROLE_STATES:
            raise ValueError(f"role state must be one of {ROLE_STATES}, not {v!r}")
        return v

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title is required")
        return v.strip()

    @field_validator("review_horizon")
    @classmethod
    def _review_horizon(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            parse_horizon_minutes(v)
        return v

    @model_validator(mode="after")
    def _review_needs_horizon(self) -> "Role":
        # A review date without a horizon has no approach mark and no gate;
        # the policy makes the horizon a reasoned property, never a default.
        if self.review_by is not None and self.review_horizon is None:
            raise ValueError("review_by needs review_horizon (see the roles policy on the review horizon)")
        return self

    def last_serviced(self) -> Optional[Update]:
        return self.updates[-1] if self.updates else None


class Duty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role_id: str
    title: str
    body: str = ""
    state: str = "pending"
    importance: str = "normal"
    meta: bool = False                                    # the role's own upkeep: charter, review, migration
    due: Optional[datetime] = None
    horizon: Optional[str] = None
    cadence: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    tracks: List[str] = Field(default_factory=list)      # task ids, open work
    evidence: List[str] = Field(default_factory=list)    # task ids or CA paths, at done
    wiki_links: List[str] = Field(default_factory=list)
    updates: List[Update] = Field(default_factory=list)

    _id = field_validator("id")(_check_id)
    _role_id = field_validator("role_id")(_check_id)

    @field_validator("state")
    @classmethod
    def _state(cls, v: str) -> str:
        if v not in DUTY_STATES:
            raise ValueError(f"duty state must be one of {DUTY_STATES}, not {v!r}")
        return v

    @field_validator("importance")
    @classmethod
    def _importance(cls, v: str) -> str:
        if v not in IMPORTANCE:
            raise ValueError(f"importance must be one of {IMPORTANCE}, not {v!r}")
        return v

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("title is required")
        return v.strip()

    @field_validator("horizon")
    @classmethod
    def _horizon(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            parse_horizon_minutes(v)
        return v

    @field_validator("cadence")
    @classmethod
    def _cadence(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                parse_cadence(v)
            except CadenceError as e:
                raise ValueError(str(e)) from e
        return v

    @field_validator("depends_on")
    @classmethod
    def _deps(cls, v: List[str]) -> List[str]:
        return [_check_id(d) for d in v]

    @model_validator(mode="after")
    def _time_rules(self) -> "Duty":
        # Horizon belongs to the duty: a dated or recurring duty with no
        # horizon can never become DUE_SOON, so the record refuses it. The
        # policy section on reasoning a horizon is the remedy, not a default.
        if (self.due is not None or self.cadence is not None) and self.horizon is None:
            raise ValueError("a duty with due or cadence needs a horizon (roles policy: reasoning a horizon)")
        if self.state == "done" and not self.evidence:
            raise ValueError("a done duty needs at least one evidence pointer (roles policy: done requires evidence)")
        if self.id in self.depends_on:
            raise ValueError("a duty cannot depend on itself")
        return self

    def horizon_minutes(self) -> Optional[int]:
        return parse_horizon_minutes(self.horizon) if self.horizon else None

    def last_serviced(self) -> Optional[Update]:
        return self.updates[-1] if self.updates else None

    def done_on_dates(self) -> List[date]:
        return [u.done_on for u in self.updates if u.done_on is not None]


def dump(model: BaseModel) -> Dict[str, Any]:
    """JSON-ready dict with dates as ISO strings."""
    return model.model_dump(mode="json", exclude_none=True)
