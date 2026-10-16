### Changed

- **CI runs the full suite at three gates, in parallel** (`.github/workflows/test.yml`, `.github/workflows/macos.yml`, `pyproject.toml` test extras, policy `testing` §3.1): a push to a pull request runs the full suite on Python 3.12 under `pytest-xdist` (the tests ran in 157 s on CI, where they took about 270; the whole job about 3.5 minutes, from 5); the merge queue and main run both versions on the actual merge; nightly runs both, plus macOS, which also runs on a pull request touching `pd/` or `platform/`. Only a test marked flaky with its open issue is rerun, once. Agreed among the maintainers on #552.

### Fixed

- **A stopped heartbeat writes nothing more** (`pd/liveness.py`): `Heartbeat.stop` now waits for a beat already under way, so no liveness is recorded for a loop that has ended. The first macOS run caught it.
- **The tree loop's tests no longer interrupt other threads** (`tests/test_tree_loop_watch.py`): their fake clock and Ctrl+C sleep apply to the test's own thread only. Patched for the whole process, any other thread that slept during the test got the KeyboardInterrupt, and a parallel test worker reported itself interrupted.
