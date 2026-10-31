### Fixed

- **Closing a sprint or play-time session fills its log wherever the CLI runs** (`cli.py`): `task complete` found `sprint_log.md` or `play_log.md` by reading the task's `plan_ca_ref` against the working directory. But `task create` stores that path relative to the agent home, so a CLI run from a project directory found nothing and left the log's Final Synthesis and scope table unfilled, with no warning. A relative `plan_ca_ref` now resolves against the agent home, and a close that still finds no log says so on stderr.
