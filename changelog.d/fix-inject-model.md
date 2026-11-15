### Added

- **An agent can switch its own model: `macf_tools inject model NAME --reason TEXT`** (`supervisor.py`, `compact_followup.py`, `stop_bypass.py`, `utils/claude_settings.py`, policy `capability_boundaries` §5.1).
  - **Why:** an operator may want one model for planning and another for execution, or ask for a switch from a phone, where `/model` can't be typed into the agent's terminal.
  - **What it types:** only `/model` with a known alias (opus, sonnet, haiku, fable, default) or a model id, optionally `[1m]`. Anything else, and a bare `/model` (which opens a picker nobody can answer), is refused before a key is pressed.
  - **Recorded:** `--reason` is required and goes into a `model_change_asked` event with the model.
  - **Takes effect like `/compact`:** the queued `/model` passes the Stop gates once, and the follower that wakes an agent after a compaction now also waits for a turn's end, so the agent gets one prompt on its new model. `--then` and `--no-then` work as for compact.
  - **Always allowed:** `Bash(macf_tools inject model:*)` joins the permanent allow list, never a bare `inject` wildcard.
