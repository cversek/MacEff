### Added

- **`macf_tools harness cutover --run` carries the move out, from outside the session it stops** (`pd/cutover.py`, `cli.py`, policy `persistent_layer` §6.3): it starts the printed plan as a transient user unit, which runs each step's commands in order and waits for the daemon to report the session unit running. Any failing command, or a unit not running within 300 s, undoes the steps it reached, last first; a saved declaration left by an earlier attempt stops the plan, and this agent's orphaned transcript monitors are ended with the legacy session. An unready plan starts nothing.
