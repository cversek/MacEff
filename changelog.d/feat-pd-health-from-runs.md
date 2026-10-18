### Added

- **`pd status` says how each schedule's runs are going** (MIS-0002-R17, R18, `persistent_layer` 11.2). The readout reads each schedule's cron and the scheduler's events when it's asked, and calls each schedule ok, failed, due, overdue, running, not run, or none owed. While the daemon answers, an overdue run, late from the oldest firing it owes, makes it read unhealthy. The JSON carries `schedules` and `runs`.
