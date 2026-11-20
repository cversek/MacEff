### Fixed

- **Two `ids renumber` tests no longer depend on the group of the temp directory they run under.** On macOS and the BSDs a new file takes its directory's group, so under a temp base owned by another group (`wheel`, for one) the test tree didn't carry the process's group and the plan came back empty. The tree now sets its group explicitly. Part of #1000.
