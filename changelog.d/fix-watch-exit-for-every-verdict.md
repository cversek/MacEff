### Fixed

- **The outside watch exits unhealthy on a dark channel or a held wake, instead of crashing** (`pd/watch.py`): the `DARK` and `HELD` verdicts had no exit code, so `exit_code` raised `KeyError` after the alert was sent, on every pass while either lasted. A test now requires a code for every verdict.
