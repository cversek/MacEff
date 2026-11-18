### Fixed

- **A late check entry under `report` is reported, not run** (`pd/scheduler.py`, MIS-0002-R25): an entry's missed-run policy is once, skip or report, and `report` acted like `once` for a check, starting its program after a missed firing. It now records the firing and raises its notice, and starts nothing. A wake entry under `report` already only notified.
