### Added

- **Container start names each agent's pickup box in its own `amail.json`** (`docker/scripts/start.py`, policy `amail` §2.3, 1.4.2): from the addressing entry that provisions the box, it writes `handoff` and `agent` into the agent's `.maceff/amail.json`. Other keys are kept, and the file stays the agent's, 0600. A seat's primal daemon gets identity variables only from the outer tier, so without the file it watched a guessed path and saw no mail.
