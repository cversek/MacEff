### Fixed

- **`claude-config idle-compaction` acts on the session's project, wherever it runs** (`macf/utils/claude_settings.py`, `cli.py`, policy `persistent_layer` section 2; MIS-0002-R126, #722).
  - **Before:** outside a hook it read and wrote the settings of the directory it ran in, so from inside another checkout `status` reported that checkout, and `off` changed settings no session reads.
  - **Now:** it takes the project from the session unit's `--project-dir`, then the harness's installed project, falls back to the old lookup only where neither names one, and says which it used.
