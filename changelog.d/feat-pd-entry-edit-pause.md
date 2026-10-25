### Added

- **`pd entry edit`, `pause` and `resume`** (`macf/src/macf/pd/`). The scheduler's design promised that an agent "creates, lists, edits, pauses and removes" its own entries, and only add, list, show and remove existed.
  - **Edit** changes an entry's time, purpose or missed-run policy and keeps its id. A new time starts the entry's clock again.
  - **Pause** stops an entry firing without forgetting it. **Resume** lets it fire again from the moment of resuming, so instants that fell during the pause aren't fired late.
  - Each is an event in the log (`pd_entry_changed`, `pd_entry_paused`, `pd_entry_resumed`), and the entries held are what the events fold to, so a restarted daemon holds the same state.
  - Edit and resume are taken only from the agent's live session and start in the client's `ask` list beside `add`. Pause, like remove, only stops work, so the operator may also do it.
  - Explained in `persistent_layer` §10.6. Each binding was shown by planting its defect: a paused entry firing, a resume making up the pause, an edit taken from outside the session.
