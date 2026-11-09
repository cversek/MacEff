### Changed

- **Session start states its context's size, and warns past the inline limit** (`hooks/handle_session_start.py`, #802). Claude Code shows a hook's additionalContext inline up to about 10,000 characters (observed: the smallest payload it moved to a file was 10,254 bytes) and keeps a longer one in a file, showing the model a preview. Every session start now records its context's size in the hook log (`CONTEXT_SIZE`, with the path: startup, resume, migration or compaction), and one past the limit warns on stderr that the model reads only a preview.
