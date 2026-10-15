### Added

- **A scheduled command declares its environment** (`pd/interface.py`, `pd/scheduler.py`, policy `persistent_layer` §10.4): `CommandRun.environment` is added to a run's fixed `PATH` and `HOME`, rendered with the same placeholders as a unit's environment and checked for unknown ones. A declared `PATH` or `HOME` overrides the default, and nothing else of the daemon's environment reaches a run. The mail clock as a schedule is its first user.
