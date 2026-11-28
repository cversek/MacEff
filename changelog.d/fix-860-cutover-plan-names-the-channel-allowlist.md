### Fixed

- **`harness cutover`'s plan names a channel the client will not load.** With no organization allowlist set, Claude Code admits only its default channel plugins, so a declared channel from another marketplace loads and stays silent, and the primal daemon falls back to keystroke wakes. The plan now says so before the move, naming the managed settings file and what to list in it, and does not hold the move: the allowlist is the host operator's file to write, and the session works without a channel. Part of #860 (item 12).
