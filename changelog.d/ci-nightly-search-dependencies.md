### Changed

- **CI runs the search tests nightly** (`.github/workflows/test.yml`, #740). The tests that need lancedb and sentence-transformers skipped in CI, so the one proving a local search writes nothing to disk ran only where it failed. A `search-dependencies` job installs the `recommend` extra, with CPU-only torch, and runs `test_gmail.py`, `test_hybrid_search.py` and `test_policy_roots.py`, on the nightly schedule and by hand.
