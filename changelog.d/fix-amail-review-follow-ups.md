### Fixed

- **Three follow-ups from review of the amail setup series**: `amail status`'s listener line cites R47 as part of the MIS-0007 draft, not as an accepted row; `status --json` keeps `broker_kind` a short value (`supervised`, `agent-launched`, `launchd job`, `declared, daemon not installed`) with the sentence in a new `broker_supervision` key; and the broker config refuses two `peer_links` entries that differ only in case, where the last one used to win silently.
