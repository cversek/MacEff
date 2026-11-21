### Changed

- **Session start says when unsent feedback drafts are waiting** (`hooks/handle_session_start.py`, #903). With #955's `pd status` line, this completes the issue's first part: an agent hears of a draft at the start of each session, with its age and title, and can raise it with the operator before a restart through `inject exit` is blocked. The drafts are read, never changed. Tests no longer see a developer's own drafts: the conftest gives each test an empty drafts directory unless it names a config directory of its own.
