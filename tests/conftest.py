"""
Pytest configuration for agent_events_log tests.
"""

import pytest
from pathlib import Path


@pytest.fixture(autouse=True)
def setup_log_path(request):
    """
    Auto-use fixture that sets log path from temp_log_file fixture if present.

    This allows tests to use temp_log_file fixture without explicitly passing it
    to the agent_events_log functions.
    """
    # Check if test has temp_log_file or populated_log fixture
    if 'temp_log_file' in request.fixturenames:
        temp_log_file = request.getfixturevalue('temp_log_file')
        from macf.agent_events_log import set_log_path
        set_log_path(temp_log_file)
        yield
        set_log_path(None)  # Reset after test
    elif 'populated_log' in request.fixturenames:
        populated_log = request.getfixturevalue('populated_log')
        from macf.agent_events_log import set_log_path
        set_log_path(populated_log)
        yield
        set_log_path(None)  # Reset after test
    else:
        yield
