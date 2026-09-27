"""The role icon shelf, apart from the models so that reading it costs no pydantic import."""

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
