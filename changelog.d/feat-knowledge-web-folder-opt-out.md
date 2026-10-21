### Added

- **A folder can opt out of the knowledge web** (`knowledge_web.py`, `knowledge_doctor.py`, `cli.py`, policy `scholarship` §3.5.5): an empty `.not-in-knowledge-web` file in a folder under `agent/private` or `agent/public`, or a subagent's, takes the whole folder out of the walk, for material that is not an artifact, such as an archive or a scratch dump. The exclusion is never silent: `knowledge doctor` names each excluded folder in a note, and `knowledge status --json` lists them under `opted_out`. It is not a way to hide orphans; a folder of linkless artifacts stays in the web.
