### Added

- **`harness list --verbose` prints each agent's attach command** (`utils/roster.py`): under every row with a calling card, the exact `macf_tools harness attach <card>` line, so reaching a session no longer means reconstructing its tmux socket or session name by hand (#976).
