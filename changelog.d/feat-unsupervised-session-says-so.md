### Added

- **A session that isn't its primal daemon's unit says so at its start** (`hooks/handle_session_start.py`, policy `persistent_layer` §6.2): where an agent has a primal daemon declaration and the daemon doesn't confirm the session as its session unit, SessionStart adds one line saying the daemon won't restart it, or why its claim is unconfirmed. A confirmed session, and an agent with no daemon, hear nothing. Once every session has moved onto its daemon, no session says it, which makes the line the check for that move.
