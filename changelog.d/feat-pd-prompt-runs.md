### Added

- **The primal daemon runs prompt schedules in an isolated session** (MIS-0002-R31, R32, `persistent_layer` 10.4). Each run is Claude Code in print mode, in a fresh directory, with the schedule's declared tools as its only permissions, written from the declaration before every run. Anything else that would prompt is denied at once, and a run that was denied anything fails and raises the new `pd_run_failed` notice, which a declaration with such a run must route to the agent. A prompt run into a named live session isn't run yet.
