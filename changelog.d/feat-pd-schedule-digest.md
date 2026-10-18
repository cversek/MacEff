### Added

- **On a host, a schedule changed since `pd install` isn't run until it's installed again** (MIS-0002-R33, `persistent_layer` 10.4). `pd install` records each schedule's digest, and a daemon over a home declaration doesn't run a schedule added or changed since, says so, and raises the new `pd_schedule_changed` notice. It detects a change a run made to its own schedules; it can't prevent one, since the log is the same user's.
