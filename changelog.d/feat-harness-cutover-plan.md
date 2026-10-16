### Added

- **`macf_tools harness cutover` prints the plan for moving a session onto its primal daemon** (`pd/cutover.py`, `cli.py`, policy `persistent_layer` §6.3): read-only. It checks the staged declaration (validates, names the agent, declares a session unit with a long enough `stop_grace_s`), the daemon, the legacy harness and session, and any mail clock beside the daemon's own. It then lists the steps, in the order the host's first move used, and the rollback, naming only units installed on this host. Exit 0 when every check holds. `--json` prints the plan as data.
