### Fixed

- **`macf_tools env` says which Claude Code the session runs, not only which is installed** (`cli.py`, `utils/paths.py`): the "CC Binary" line was found through the `claude` launcher, so it named the installed version, and an auto-update that came after a session started made it disagree with the session's own process and transcript. It is now "CC Installed", and a new "CC Running" line names the binary the session's process executes (from `CLAUDE_PID`), marked when it isn't the installed one. `macf_tools env --json` carries the same value as `cc_internal.cc_running` (#866).
