### Changed

- **Unsent feedback drafts are said before they block a restart** (`utils/feedback_drafts.py`, `pd/cli.py`, `supervisor.py`, #903). A draft makes `inject exit` refuse, and nothing mentioned one before that. `pd status` now says how many drafts the client holds and how old the oldest is, and `inject exit`'s refusal gives each draft's title and age, so the operator can decide from that message alone. The drafts are only read; sending or discarding one stays the operator's decision.
