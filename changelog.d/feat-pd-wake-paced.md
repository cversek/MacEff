### Added

- **An agent paces its own keystroke wake** (`pd/interface.py`, `pd/daemon.py`, `pd/notifier.py`, `pd/wake.py`, `pd/cli.py`, policy `persistent_layer` §1.9 and §12.3, `macf/docs/developer/primal_daemon_interface.md`).
  - **The command:** `macf_tools pd wake --refractory 5m --reason "<why>"` sets how long the wake rests after each wake. `--declared` goes back to the declared window, and `pd wake` alone shows the window in force and where it came from.
  - **The declaration:** `wake_refractory_s` (default 600, the ten minutes the operator kept) and an optional `wake_refractory_floor_s`, which no pace goes under. Only the declaration sets the floor, never the control socket; in a container, root renders the declaration.
  - **On the socket:** a `pace` request, asked by the new `agent` asker kind or by the operator. It acts on no unit. It is recorded like every act (`pd_control` with act `pace` and an empty unit, the asker, the reason and the asking process), and in `pd_wake_paced` with the window it replaced, before the daemon answers. A pace that can't be recorded isn't set.
  - **Across restarts:** the next daemon reads the newest `pd_wake_paced` of its agent back at its start and keeps it, naming where it came from. A floor declared above it since then wins, and the daemon says so.
  - A status reply carries the window, wherever a session unit has a keystroke wake.
