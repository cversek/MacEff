### Fixed

- **A restarted daemon never adopts a unit from a record made before the host's last boot** (`pd/core.py`, policy `persistent_layer` §11.1): adoption matched a pid and its start time, and on Linux a start time counts clock ticks since boot, so after a reboot a new process could carry the pid and ticks an old record names, and be taken for the unit. A record older than the boot time (`btime`) is now started fresh. macOS records a UTC start time and is unaffected. Two tests; the check planted out fails one.
