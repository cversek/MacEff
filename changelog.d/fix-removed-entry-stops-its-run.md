### Fixed

- **Removing an entry stops its check still running** (`pd/scheduler.py`, `pd/daemon.py`, #760). Removal dropped the entry but left a check of it running, and if that run then failed it raised `pd_run_failed` for an entry already revoked. The run is now stopped and reads `stopped: its entry was removed`, which owes no failure notice (#746).
