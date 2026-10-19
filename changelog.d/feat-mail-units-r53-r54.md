### Changed

- **In a container, the mail broker and its inbound watcher are units of the broker account's own primal daemon, and the aged sweep is its schedule** (`docker/scripts/start.py`, `macf/models/agent_spec.py`, `macf/amail/daemons/inbound.py`, policy `persistent_layer` 10.1; MIS-0002-R53, R54).
  - **Before:** the amail step started the broker, the watcher and a watchdog once each, and nothing restarted them.
  - **Services can declare a daemon:** a service in `agents.yaml` may now declare `primal_daemon` with a `calling_card`. Start-up writes the account's identity, renders the declaration owned by root, and starts the daemon as the account.
  - **The watcher:** it beats its liveness to the daemon, and no longer sweeps (`AMAIL_WATCH_SWEEP_INTERVAL` is gone).
  - **The sweep:** `inbound sweep --quiet` prints only when it alerts, so it runs as a schedule with `wake_when: stdout`.
  - **Stuck mail:** a stuck message is a failed sweep run. It's recorded, `pd status` shows the schedule as `FAILED`, and `inbound health` exits unhealthy. Nothing alerts a person on it yet.
  - **Health:** `inbound health` reports a watchdog but no longer requires one.
  - **Refused at load:** a unit that runs `inbound sweep` or `inbound watchdog`, and a service unit under another account.
- **A deployment must declare `services.amail_broker.primal_daemon` before taking this version.** Without it the amail step fails by name, and the broker doesn't run. `docs/arch_v0.3_named_agents/APPENDIX_A_YAML_SCHEMAS.md` shows the block.
