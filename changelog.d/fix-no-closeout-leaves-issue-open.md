### Fixed
- `task complete --no-closeout` on a GH_ISSUE task now leaves the issue open. It used to skip only the comment, and still closed the issue when a given commit was on main.
