### Changed

- **CI runs the full suite at three gates, in parallel** (`.github/workflows/test.yml`, `.github/workflows/macos.yml`, `pyproject.toml` test extras, policy `testing` §3.1): a push to a pull request runs the full suite on Python 3.12 under `pytest-xdist`, about two minutes where it took four and a half; the merge queue and main run both versions on the actual merge; nightly runs both, plus macOS, which also runs on a pull request touching `pd/` or `platform/`. Only a test marked flaky with its open issue is rerun, once. Agreed among the maintainers on #552.
