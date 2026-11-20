### Changed

- **`harness list` says when an agent's Claude login has run out or is about to** (#883): under the row, `login: LOGIN-EXPIRED: its refresh grant ended 2 h ago: run /login in its session`. It reads the daemon's recorded login check from the agent's own event log and judges it against the time of the listing, the way the watch does, so an agent whose login lapsed is seen before its session fails a turn. An agent with a healthy or undated login gets no extra line, and `--json` carries the same text in a `login` field.
