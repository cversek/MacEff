### Added

- **A session the daemon adopted reports waiting on a person** (`pd/core.py`; MIS-0002-R21). Claude Code's own daemon hosts an adopted session, which writes no liveness, so no beat carried a dialog it showed. The core now reads what it waits on from the event log by its session id, every few seconds, and moves the unit to waiting on a person and back.

### Fixed

- **A wait shows and clears within seconds, not an interval late** (`pd/liveness.py`, #728). The session unit's beat said what the session waits on only once per liveness interval, so at 120 s a question stood unreported for two minutes and the tray kept its waiting glyph two minutes after it was answered. Between beats the heartbeat now checks every 5 s whether that changed, and beats at once when it has.
