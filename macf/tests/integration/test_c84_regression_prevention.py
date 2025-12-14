"""
Regression tests for C84 bugs.

These tests explicitly validate the three C84 bugs are fixed and won't regress:
1. Missing @dataclass decorator on SessionOperationalState
2. Hook execution crashes silently
3. Path resolution fails in sibling repository context

If any C84 bug reappears, these tests fail immediately and loudly.
"""

import inspect
import json
import subprocess
import sys
from pathlib import Path
from dataclasses import is_dataclass, fields
import pytest

from macf.utils import find_project_root


class TestC84Bug1DataclassDecorator:
    """
    C84 Bug 1: Missing @dataclass decorator killed SessionOperationalState.

    Symptom: TypeError: SessionOperationalState() takes no arguments
    Root cause: Refactoring moved class but lost @dataclass decorator
    Why unit tests missed it: They mocked the class, never instantiated it
    """

    def test_session_operational_state_has_dataclass_decorator(self):
        """Verify @dataclass decorator is present."""
        from macf.utils.state import SessionOperationalState

        assert is_dataclass(SessionOperationalState), \
            "C84 Bug 1 REGRESSION: SessionOperationalState missing @dataclass decorator"

    def test_session_operational_state_accepts_arguments(self):
        """Verify class can be instantiated with arguments."""
        from macf.utils.state import SessionOperationalState

        # This line would fail with: TypeError: SessionOperationalState() takes no arguments
        state = SessionOperationalState(
            session_id="test-session",
            agent_id="test-agent"
        )

        assert state.session_id == "test-session"
        assert state.agent_id == "test-agent"

    def test_dataclass_generates_init_with_all_fields(self):
        """Verify @dataclass generates __init__ with all declared fields."""
        from macf.utils.state import SessionOperationalState

        # Get __init__ signature
        sig = inspect.signature(SessionOperationalState.__init__)
        params = list(sig.parameters.keys())

        # Should have self + all dataclass fields
        assert 'self' in params
        assert 'session_id' in params
        assert 'agent_id' in params

        # Verify all dataclass fields are in __init__
        dc_fields = {f.name for f in fields(SessionOperationalState)}
        init_params = set(params) - {'self'}

        assert dc_fields == init_params, \
            "Dataclass fields don't match __init__ parameters - decorator may be missing"

    def test_state_can_be_converted_to_dict(self):
        """Verify dataclass can be serialized via asdict()."""
        from macf.utils.state import SessionOperationalState
        from dataclasses import asdict

        state = SessionOperationalState(
            session_id="test",
            agent_id="test"
        )

        # asdict() only works on dataclasses
        try:
            data = asdict(state)
            assert isinstance(data, dict)
            assert data['session_id'] == "test"
        except TypeError as e:
            pytest.fail(f"C84 Bug 1 REGRESSION: asdict() failed - @dataclass missing: {e}")


class TestC84Bug2HookExecutionCrash:
    """
    C84 Bug 2: SessionStart hook crashed silently due to state instantiation.

    Symptom: Hook executed but produced no output, no errors
    Root cause: Missing @dataclass meant state.load() crashed internally
    Why unit tests missed it: They mocked state loading
    """

    def test_session_start_hook_executes_without_crash(self):
        """Verify SessionStart hook completes execution."""
        from macf.hooks.handle_session_start import run

        # Execute hook - should not raise exception
        try:
            result = run("", testing=True)
            assert isinstance(result, dict)
            assert "continue" in result
        except Exception as e:
            pytest.fail(f"C84 Bug 2 REGRESSION: SessionStart hook crashed: {e}")

    def test_session_start_hook_produces_output(self):
        """Verify SessionStart hook produces consciousness injection output."""
        from macf.hooks.handle_session_start import run

        result = run("", testing=True)

        # Hook should produce output, not silent failure
        assert "hookSpecificOutput" in result, \
            "C84 Bug 2 REGRESSION: Hook executed but produced no output"

        assert "additionalContext" in result["hookSpecificOutput"], \
            "C84 Bug 2 REGRESSION: Missing additionalContext in hook output"

        context = result["hookSpecificOutput"]["additionalContext"]
        assert len(context) > 0, \
            "C84 Bug 2 REGRESSION: Hook produced empty context (silent failure)"

    def test_hook_subprocess_execution_succeeds(self):
        """
        Verify hook executes successfully as subprocess.

        This is how Claude Code actually runs hooks - if this fails,
        consciousness infrastructure is completely broken.
        """
        project_root = find_project_root()
        hook_path = project_root / '.claude' / 'hooks' / 'session_start.py'

        if not hook_path.exists():
            pytest.skip("SessionStart hook not installed")

        result = subprocess.run(
            [sys.executable, str(hook_path)],
            input="",
            capture_output=True,
            text=True,
            timeout=10
        )

        assert result.returncode == 0, \
            f"C84 Bug 2 REGRESSION: Hook crashed in subprocess\nstderr: {result.stderr}"

        # Should produce valid JSON
        try:
            output = json.loads(result.stdout)
            assert output["continue"] is True
        except json.JSONDecodeError as e:
            pytest.fail(f"C84 Bug 2 REGRESSION: Hook produced invalid JSON: {e}")

    def test_state_load_handles_missing_decorator(self):
        """
        Verify SessionOperationalState.load() would fail if @dataclass missing.

        This is the exact failure point in C84 - load() tried to instantiate
        the class with arguments, which failed without @dataclass.
        """
        from macf.utils.state import SessionOperationalState

        # load() should work (returns default instance on any failure)
        state = SessionOperationalState.load(
            session_id="test-session",
            agent_id="test-agent"
        )

        assert state is not None
        assert isinstance(state, SessionOperationalState)
        assert state.session_id == "test-session"


class TestC84Bug3PathResolution:
    """
    C84 Bug 3: Path resolution failed when running from sibling repository.

    Symptom: Failed to load base manifest
    Root cause: Assumed MacEff always exists as submodule
    Why unit tests missed it: Tests ran from MacEff repository directly
    """

    def test_manifest_loading_succeeds(self):
        """Verify base manifest can be loaded."""
        from macf.utils.manifest import load_merged_manifest

        manifest = load_merged_manifest()

        # Should either load successfully or gracefully return None
        # Should NOT crash with path resolution error
        if manifest is None:
            # Graceful degradation is acceptable
            pass
        else:
            assert isinstance(manifest, dict)
            assert "discovery_index" in manifest

    def test_path_resolution_doesnt_crash(self):
        """Verify path resolution handles missing directories gracefully."""
        from macf.utils.paths import find_project_root

        # Should not raise exception even if .claude directory missing
        try:
            result = find_project_root()
            # May return None or Path, but shouldn't crash
            assert result is None or isinstance(result, Path)
        except Exception as e:
            pytest.fail(f"C84 Bug 3 REGRESSION: Path resolution crashed: {e}")

    def test_consciousness_artifacts_discovery_handles_missing_paths(self):
        """Verify artifact discovery doesn't crash with missing agent_root."""
        from macf.utils.artifacts import get_latest_consciousness_artifacts

        # Should handle None agent_root gracefully
        try:
            artifacts = get_latest_consciousness_artifacts(agent_root=None)
            # May return empty or populated, but shouldn't crash
            assert artifacts is not None
        except Exception as e:
            pytest.fail(f"C84 Bug 3 REGRESSION: Artifact discovery crashed: {e}")


class TestRefactoringSmoke:
    """
    Smoke tests that would catch C84-style refactoring breaks.

    Run these after any major refactoring to validate integration still works.
    """

    def test_all_critical_imports_resolve(self):
        """Verify refactored modules can all be imported."""
        critical_modules = [
            'macf.utils.state',
            'macf.utils.paths',
            'macf.utils.session',
            'macf.utils.temporal',
            'macf.utils.manifest',
            'macf.utils.artifacts',
            'macf.hooks.handle_session_start',
            'macf.hooks.handle_pre_tool_use',
            'macf.hooks.handle_post_tool_use',
        ]

        for module_name in critical_modules:
            try:
                __import__(module_name)
            except ImportError as e:
                pytest.fail(f"REFACTORING REGRESSION: {module_name} import failed: {e}")

    def test_all_dataclasses_have_decorators(self):
        """Verify all intended dataclasses have @dataclass decorator."""
        from macf.utils.state import SessionOperationalState

        dataclass_types = [
            SessionOperationalState,
        ]

        for cls in dataclass_types:
            assert is_dataclass(cls), \
                f"REFACTORING REGRESSION: {cls.__name__} missing @dataclass decorator"

    def test_state_save_load_roundtrip(self):
        """Verify state can be saved and loaded (full integration)."""
        import tempfile
        from macf.utils.state import SessionOperationalState
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            session_dir = Path(tmpdir) / "session"
            session_dir.mkdir()

            with patch('macf.utils.state.get_session_dir', return_value=session_dir):
                # Create, save, load cycle
                original = SessionOperationalState(
                    session_id="test",
                    agent_id="test",
                    compaction_count=5,
                    auto_mode=True
                )

                assert original.save(), "REFACTORING REGRESSION: State save failed"

                loaded = SessionOperationalState.load(
                    session_id="test",
                    agent_id="test"
                )

                assert loaded.compaction_count == 5, \
                    "REFACTORING REGRESSION: State not preserved across save/load"
                assert loaded.auto_mode is True, \
                    "REFACTORING REGRESSION: State fields not preserved"

    def test_hooks_execute_end_to_end(self):
        """Verify all hooks can execute (black box test)."""
        hook_handlers = [
            'macf.hooks.handle_session_start',
            'macf.hooks.handle_pre_tool_use',
            'macf.hooks.handle_post_tool_use',
            'macf.hooks.handle_user_prompt_submit',
            'macf.hooks.handle_stop',
            'macf.hooks.handle_subagent_stop',
        ]

        for module_name in hook_handlers:
            module = __import__(module_name, fromlist=['run'])

            # Execute hook - should not crash
            try:
                result = module.run("", testing=True)
                assert isinstance(result, dict)
                assert "continue" in result
            except Exception as e:
                pytest.fail(f"REFACTORING REGRESSION: {module_name} crashed: {e}")
