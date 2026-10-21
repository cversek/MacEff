### Fixed

- **`test_tree_loop_watch.py` no longer takes down a CI worker** (`macf/tests/test_tree_loop_watch.py`): the test turned every `time.sleep` on its own thread into Ctrl+C for its whole duration, so a sleep anywhere but the watch loop escaped the loop's handler and pytest-xdist reported the worker down. Only the loop's own sleep is Ctrl+C now, and the clock is faked for the command's call only.
