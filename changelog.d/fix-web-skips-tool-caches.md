### Fixed

- **The knowledge web skips test and lint caches** (`knowledge_web.py`, policy `scholarship`, the rule on tools' directories). `.pytest_cache`, `.mypy_cache` and `.ruff_cache` hold files no agent writes, but pytest's own `README.md` in a tool folder's `.pytest_cache` was walked as an artifact and counted as an orphan. Two such files were showing as orphans on the Harbor Master's tree.
