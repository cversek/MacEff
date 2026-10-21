### Changed

- **`events query` is the readable reader of the event log** (`eventlog/reader.py`, `cli.py`, policy `persistent_layer` 11.1; MIS-0002 landing, Phase 10). It prints one line per event, `HH:MM:SS  event  summary`, from a summary table of the events read most (wakes, units, notices, tool calls, prompts, permission dialogs) with a generic fallback; `-v` prints every field, and `--json` one JSON line per event.
  - `--event` repeats and takes globs; `--after` and `--before` take `30m`, `2h`, `09:00`, an ISO time or an epoch; `--limit` keeps the newest N; `--follow` prints new events until Ctrl+C.
  - A time-bounded query reads newest first and stops at its cutoff, not at the end of the log.
  - `events history` prints through the same formatter. The old multi-line output is gone, with no compatibility mode, by the dev-phase rule.
  - `-v` dates a line as the default line does: no date on an event from today.
  - 14 tests; nine planted defects each caught, plus five from review, each failing a test that goes through the command: `--follow` started anywhere but before the scan, `--follow` ignoring `--before`, and either line form losing today.
