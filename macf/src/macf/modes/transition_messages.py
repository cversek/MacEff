"""Behavioral-reinforcement messages printed on mode transitions (idea #091).

A mode change alters what the agent should and should not do. Printing a short
"here is what this mode means for you" line at every transition keeps behavior
aligned with the mode rather than relying on the agent to remember across a long
session. The USER_REMOTE switch message is the exemplar this generalizes: every
operational and work-mode transition should carry the same kind of reinforcement.

Operator directive (Telegram, c_14): "helpful behavior reinforcement messages
should be put at every mode transition."
"""

# Operational-mode reinforcement. USER_REMOTE prints its own richer switch
# message at the transition site (the exemplar); the entry here is the one-line
# form for echo/consistency.
OPERATIONAL_REINFORCEMENT = {
    "AUTO_MODE": (
        "🤖 AUTO_MODE — operate autonomously within your scoped work. Valid stops: "
        "scope complete, blocked needing operator input, wind-down at low context, "
        "or an unrecoverable error. Do local work freely; outward or irreversible "
        "actions (push, PR, merge, deletes) still prompt — batch them for the gate."
    ),
    "MANUAL_MODE": (
        "✋ MANUAL_MODE — await operator direction. Do not self-scope new work; "
        "report and stop at decision points."
    ),
    "USER_REMOTE": (
        "📡 USER_REMOTE — operator on a remote channel, CLI unattended. Never use "
        "tools that block on CLI input (AskUserQuestion, Ask-list commands) — they "
        "hang the session. Talk via the remote channel; hold pushes."
    ),
}

# Work-mode reinforcement — what the mode obligates the agent to do.
WORK_REINFORCEMENT = {
    "DISCOVER": (
        "🔍 DISCOVER — explore and map the territory before committing to a build; "
        "capture what you find so the exploration isn't lost."
    ),
    "EXPERIMENT": (
        "🧪 EXPERIMENT — form a testable hypothesis and design its control BEFORE "
        "building; a prototype without a hypothesis is just a build."
    ),
    "BUILD": (
        "🔨 BUILD — implement against a validated hypothesis; prototypes live inside "
        "the experiment CA, not scattered across the tree."
    ),
    "CURATE": (
        "📋 CURATE — preserve knowledge: learnings, ideas, indexes, cross-references. "
        "Perishable insight first."
    ),
    "CONSOLIDATE": (
        "✍️ CONSOLIDATE — synthesize scattered findings into coherent artifacts; "
        "connect them into the knowledge web."
    ),
    "SPRINT": (
        "🏃 SPRINT — work the scoped set to completion; the Markov recommender is "
        "silent. Complete each task the moment its work finishes."
    ),
}


def transition_reinforcement(mode: str) -> str:
    """Return the behavioral-reinforcement line for a mode transition.

    Args:
        mode: the mode being transitioned INTO (e.g. "AUTO_MODE", "BUILD").

    Returns:
        A short reinforcement string, or "" for an unknown mode (callers print
        nothing rather than a blank line).
    """
    if not mode:
        return ""
    key = mode.upper()
    return OPERATIONAL_REINFORCEMENT.get(key) or WORK_REINFORCEMENT.get(key, "")
