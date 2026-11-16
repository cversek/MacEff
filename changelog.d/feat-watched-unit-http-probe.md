### Added

- **A program that isn't MacEff code can be judged by an HTTP probe or its own health check** (`pd/watched_unit.py`, policy `persistent_layer` §3.2): `--probe <loopback url>` beats while the URL answers below 500, and `--check '<command>'` while the check exits 0, as alternatives to a heartbeat file. Probes reach loopback only, follow no redirect and ignore proxies. A failed probe or check says why on stderr once per transition, and probes run off the wrapper's loop so a hung one never delays a stop (#977, #978).
