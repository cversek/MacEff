### Fixed

- **Keys typed into an agent's session reach the agent's own pane, not whichever pane has focus** (`supervisor.py`): `inject compact`, `auto-restart send-keys`, the compaction follow-up and the post-start keys now target the pane whose process is the supervisor. Before, they targeted the tmux session, which means its active pane, so after someone split the window and worked in the new pane (a task-tree watch beside the agent, say), every `/compact` went into that pane and the agent never compacted. A session without such a pane falls back to the session as before.
