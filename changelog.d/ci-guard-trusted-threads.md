### Added

- **Threads opened by the repo owner or a maintainer take comments from collaborators only** (`.github/workflows/lock-trusted-threads.yml`, `CONTRIBUTING.md`): an issue of theirs is locked as it opens, and on a pull request of theirs a comment from anyone else is hidden as off-topic and the repo owner is emailed. Pull requests aren't locked, because the maintainers post as GitHub Apps, and an app can comment on a locked issue but not on a locked pull request. Outsiders still open their own issues and comment on each other's.
