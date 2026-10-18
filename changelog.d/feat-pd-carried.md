### Added

- **The primal daemon reports what each restart and compaction carried, changed and lost** (MIS-0002-R47, `persistent_layer` 11.2). After the daemon restarts, after the session unit restarts, and a minute after a compaction, one `pd_carried` event lists the three, and the agent is owed the `pd_carried` notice pointing to it. A delivered notice opens a turn, so an AUTO_MODE agent resumes after any compaction. A daemon with a session unit that doesn't route `pd_carried` to the agent warns at start.
