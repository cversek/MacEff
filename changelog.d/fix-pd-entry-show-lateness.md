### Fixed

- **`pd entry show <id>` says when the entry last fired and how late** (`macf/src/macf/pd/cli.py`, `macf/src/macf/pd/daemon.py`, `macf/src/macf/pd/entries.py`, policy `persistent_layer` 10.6): the `pd_entry_due` notice points there, and it printed no firing, so a wake that came three hours late read the same as one on time. The daemon now gives each entry it lists its newest `pd_entry_fired` from the event log, still the only store, as `last_fired`, and the command prints a `last fired:` line: the instant it fired for, `fired 3h 0m late` or `on time` within the minute's grace, and the earlier firings it stood for. `pd entry list --json` carries the same field.

### Changed

- **MIS-0002: the entry halves of R25 and R34 bound, both rows to passing** (`framework/mis/MIS-0002-persistent-layer.md`, `macf/tests/test_pd_entries.py`; editorial under policy `mis` 8.1). New tests show that the daemon's socket refuses an entry whose missed-run policy is anything but once, skip or report, and records nothing (R25), and that an entry fired late raises `pd_entry_due` through the channel's own record and the command its pointer names states how late it fired (R34). Each was checked by planting a defect at the row's entry point and watching it fail. No requirement changed.
