### Fixed

- **A `/compact` the framework typed no longer reads as the operator after the compaction** (`utils/input_origin.py`, #653): `typed_by_framework` read only the current cycle's events, but `inject compact` records its keystroke in the cycle that ends and the client writes the command's row in the one that starts, so the transcript monitor counted the framework's `/compact` as operator activity and cleared USER_IDLE. The record is now looked for across the boundary, bounded by the existing ten-minute window.
