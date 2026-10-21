### Fixed

- **The session unit turns the client's idle compaction off** (`pd/session_unit.py`, MIS-0002-R126, policy `persistent_layer`). The policy said the harness adapter does this, but nothing called the switch; it existed only as `claude-config idle-compaction`. The unit now writes `idleCompaction: false` into the project it starts the client in, each start, unless the declaration's `keep_harness_idle_compaction` keeps it. A declaration it can't read keeps nothing. A client too old for the key, or one it can't find, is said, and the session starts anyway.
- **The daemon names its process `maceff_pd` on Linux** (`pd/names.py`, `pd/__main__.py`, MIS-0002-R06, policy `persistent_layer` 12.1). Before, a process listing showed the Python interpreter. Its command line is unchanged, so `pgrep -f macf.pd` still finds it. macOS has no call that renames a running process.

### Tests

- **Binding tests for MIS-0002 R06, R14, R42, R55, R57 and R126,** the rows sweep 7 found checked short. Each new test fails when the requirement breaks at the place it names:
  - a running daemon's listed name and sockets (R06);
  - a managed unit writing its liveness to its agent's own log at its declared interval (R14);
  - each declared route reaching its audience and no other (R42, R55);
  - the access path starting before the daemons through the outer tier's own `main` (R57);
  - the adapter turning idle compaction off, or keeping it (R126).
- **R42 stays planned:** `held_until_present` is declared but served nowhere, and the operator route is served only for `pd_unread_mail`.
