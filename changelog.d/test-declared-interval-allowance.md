### Fixed

- **Daemon test units declare a liveness interval a loaded runner can meet** (`tests/test_primal_daemon.py`): the stand-ins declared and reported 0.05 s, so the daemon called a unit overdue after 0.15 s of silence, less than a busy runner can pause a process. A running unit was then ended as hung and restarted, which read as a unit that exited 0 under `on-failure` coming back. The stand-ins still beat every 0.05 s but now declare at least 0.5 s, so silence must last 1.5 s. A test about staleness passes `declared_interval` itself.
