### Added

- **`macf_tools amail outbox`: what the broker holds for its peers** (`readiness.outbox`, amail policy 2.1.2): each message waiting for a retry with its recipient and age, and each one a peer refused with the reason the peer gave; by default only the asking agent's own (`--all` for every agent's, `--json`). A waiting message keeps no reason, so the view points at `amail peer check` for the current one.
