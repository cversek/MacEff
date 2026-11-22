### Added

- **`amail status` lists the mail setup piece by piece, each missing one with its fix** (`amail/readiness.py`, amail policy 2.1.2): the address, the signing key, signing every message, the agent's key in the registry (with the declaration to run), how the broker is supervised (a declared unit of its own daemon, a launchd job of its own, or agent-launched, pointing at `amail broker-unit`), the listener as a declared crossing (MIS-0007 R47), and each peer link with its agents and the mail waiting for it and refused by it (pointing at `amail peer check`). Read-only; in `--json` as `setup`.

### Fixed

- **`amail status` names how the broker is actually run**: the broker line said "agent-launched" whenever the client may start a broker, including when a launchd job runs it; it now says what the supervision piece found.
