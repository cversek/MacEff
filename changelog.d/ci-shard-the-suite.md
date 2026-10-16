### Changed

- **CI splits the suite across four runners per Python version** (`.github/workflows/test.yml`, `macf/tests/conftest.py`, policy `testing` §3.1): `MACF_TEST_SHARD=i/n` keeps the tests whose id hashes to shard i, and the required checks `test (3.10)` and `test (3.12)` pass only when every shard did. The policy now describes the gate MacEff actually has: a personal account's repository can't have a merge queue, so main's ruleset requires a branch to be up to date before it merges.
