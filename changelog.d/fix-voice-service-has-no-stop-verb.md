### Fixed

- **The voice service takes no stop request, and doesn't echo a path it refuses** (`voice/service.py`, part of #868). Its port answers any local caller, so a `shutdown` request let anyone stop it, and the error for a missing file named the path, which answered "does this path exist?" for whoever asked. `shutdown` is now refused with the way to stop it, `macf_tools voice service stop` stops it by signal from its own account, and the error says only that the audio file can't be read.
