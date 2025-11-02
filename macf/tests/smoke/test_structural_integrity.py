"""
Smoke tests for structural integrity.

These tests catch silent failures from refactoring - missing decorators,
broken imports, structural changes that break instantiation.

Fast execution (<5s) makes them suitable for pre-commit hooks.

References C84 Bug 1: Missing @dataclass decorator killed SessionOperationalState
instantiation silently - all unit tests passed because they mocked everything.
"""

import inspect
from dataclasses import is_dataclass
import pytest


def test_session_operational_state_is_dataclass():
    """
    Verify SessionOperationalState has @dataclass decorator.

    C84 Bug 1: Missing @dataclass meant class couldn't be instantiated with arguments.
    Unit tests passed because they mocked the class. This test validates the actual
    class definition has required decorator.
    """
    from macf.utils.state import SessionOperationalState

    assert is_dataclass(SessionOperationalState), \
        "SessionOperationalState missing @dataclass decorator - will fail on instantiation"


def test_session_operational_state_instantiates():
    """
    Verify SessionOperationalState can be instantiated with arguments.

    C84 Bug 1: Without @dataclass, __init__() doesn't accept arguments.
    This test fails loudly: TypeError: SessionOperationalState() takes no arguments
    """
    from macf.utils.state import SessionOperationalState

    # This should NOT raise TypeError
    state = SessionOperationalState(
        session_id="test-session-123",
        agent_id="test-agent"
    )

    assert state.session_id == "test-session-123"
    assert state.agent_id == "test-agent"


def test_session_operational_state_has_required_fields():
    """
    Verify SessionOperationalState has expected fields for hook integration.

    Catches regressions where refactoring removes critical state fields.
    """
    from macf.utils.state import SessionOperationalState

    state = SessionOperationalState(session_id="test", agent_id="test")

    # Critical fields used by hooks
    required_fields = [
        'session_id',
        'agent_id',
        'auto_mode',
        'auto_mode_source',
        'compaction_count',
        'pending_todos',
        'session_started_at'
    ]

    for field in required_fields:
        assert hasattr(state, field), f"Missing required field: {field}"


def test_all_hook_modules_importable():
    """
    Verify all hook handler modules can be imported.

    Catches import errors that would cause hooks to fail silently.
    Missing imports, circular dependencies, syntax errors all caught here.
    """
    hook_modules = [
        'macf.hooks.handle_session_start',
        'macf.hooks.handle_pre_tool_use',
        'macf.hooks.handle_post_tool_use',
        'macf.hooks.handle_user_prompt_submit',
        'macf.hooks.handle_stop',
        'macf.hooks.handle_subagent_stop',
    ]

    for module_name in hook_modules:
        try:
            __import__(module_name)
        except ImportError as e:
            pytest.fail(f"Hook module {module_name} import failed: {e}")


def test_all_hook_handlers_have_run_function():
    """
    Verify all hook handlers export run() function.

    Installed hooks call run() from package modules. Missing run() means
    hook execution fails silently with AttributeError.
    """
    hook_modules = [
        'macf.hooks.handle_session_start',
        'macf.hooks.handle_pre_tool_use',
        'macf.hooks.handle_post_tool_use',
        'macf.hooks.handle_user_prompt_submit',
        'macf.hooks.handle_stop',
        'macf.hooks.handle_subagent_stop',
    ]

    for module_name in hook_modules:
        module = __import__(module_name, fromlist=['run'])
        assert hasattr(module, 'run'), f"{module_name} missing run() function"
        assert callable(module.run), f"{module_name}.run is not callable"


def test_state_save_load_cycle():
    """
    Verify state can be saved and loaded without corruption.

    Catches serialization issues - fields that can't be JSON serialized,
    dataclass fields with incompatible defaults, etc.
    """
    import tempfile
    from pathlib import Path
    from macf.utils.state import SessionOperationalState
    from macf.utils.paths import get_session_dir
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as tmpdir:
        # Mock session directory to use temp location
        session_dir = Path(tmpdir) / "test-session"
        session_dir.mkdir()

        with patch('macf.utils.state.get_session_dir', return_value=session_dir):
            # Create and save state
            original = SessionOperationalState(
                session_id="test-session",
                agent_id="test-agent",
                auto_mode=True,
                compaction_count=5
            )

            save_result = original.save()
            assert save_result, "State save failed"

            # Load state back
            loaded = SessionOperationalState.load(
                session_id="test-session",
                agent_id="test-agent"
            )

            # Verify critical fields preserved
            assert loaded.session_id == original.session_id
            assert loaded.agent_id == original.agent_id
            assert loaded.auto_mode == original.auto_mode
            assert loaded.compaction_count == original.compaction_count


def test_critical_utils_modules_importable():
    """
    Verify critical utils modules can be imported without circular dependencies.

    Refactoring can introduce import cycles that only manifest at runtime.
    """
    critical_modules = [
        'macf.utils.state',
        'macf.utils.paths',
        'macf.utils.session',
        'macf.utils.temporal',
        'macf.utils.artifacts',
        'macf.utils.manifest',
    ]

    for module_name in critical_modules:
        try:
            __import__(module_name)
        except ImportError as e:
            pytest.fail(f"Critical utils module {module_name} import failed: {e}")
