### Changed

- **The recipe for a stranded session is in the policy** (GH#1073, `persistent_layer` 5.1): a session that runs under its daemon but can't work is found and fixed from `pd status`, its `probable cause:` line, the declared `USER` and `LOGNAME`, the operator's daemon restart and a unit restart, and `/login` only if it still reads expired. Recorded from one real case end to end, so the next operator need not reconstruct it.
