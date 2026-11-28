### Changed

- **The sprint policy says not to block on long-running commands.** Under the agent posture (`autonomous_sprint`), a test suite, a CI wait, a build or a poll is started in the background and the agent works ahead on the next ready scoped task, reading the result when it reports; a foreground wait loop is the failure, since it spends the sprint's time on nothing and leaves the stop gate nagging.
