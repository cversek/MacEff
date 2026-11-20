### Fixed

- **Two liveness tests wait for the heartbeat with a deadline** (`tests/test_pd_liveness.py`): a fixed 50 ms wait for the writer thread flaked on a loaded macOS runner (#993, #994).
