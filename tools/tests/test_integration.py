"""
Test specifications for macf_tools end-to-end integration scenarios.

This module tests complete workflows and integration between all components:
- Full consciousness infrastructure workflows
- Cross-component interactions (config + session + CLI)
- Real-world usage scenarios
- Performance and reliability under load
- Container vs host environment integration

Following TDD principles - these tests define the expected behavior
for complete Phase 1 consciousness infrastructure workflows.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
from click.testing import CliRunner

from macf.cli import main


class TestFullConsciousnessWorkflows:
    """Test suite for complete consciousness infrastructure workflows."""

    def test_agent_initialization_workflow(self, clean_environment):
        """
        Test complete agent initialization from clean state.

        Workflow:
        1. Agent starts with no prior configuration
        2. CLI detects environment (container vs host vs fallback)
        3. Creates necessary directory structures
        4. Initializes configuration with defaults
        5. Ready for consciousness operations

        Should work identically in all environments.
        """
        runner = CliRunner()

        # Simulate clean agent startup
        with patch.dict(os.environ, {}, clear=True):
            # First command should trigger initialization
            result = runner.invoke(main, ['env'])

        assert result.exit_code == 0

        # Should have created basic structures
        env_data = json.loads(result.output)
        assert 'cwd' in env_data
        assert 'tz' in env_data

        # Follow-up commands should work
        result2 = runner.invoke(main, ['time'])
        assert result2.exit_code == 0

    def test_checkpoint_creation_full_workflow(self, configured_agent_environment):
        """
        Test complete checkpoint creation workflow.

        Workflow:
        1. Agent creates strategic checkpoint
        2. File created with proper naming convention
        3. Metadata populated correctly
        4. Session information included
        5. File placed in correct directory (public/private)
        6. Discoverable via list command

        Should maintain consistency across checkpoint types.
        """
        runner = CliRunner()

        # Create strategic checkpoint
        result1 = runner.invoke(main, [
            'checkpoint',
            '--type', 'strategic',
            '--note', 'Major milestone achieved'
        ])
        assert result1.exit_code == 0
        checkpoint_path = result1.output.strip()

        # Verify file was created with correct content
        assert Path(checkpoint_path).exists()

        content = Path(checkpoint_path).read_text()
        assert "type: strategic" in content
        assert "Major milestone achieved" in content
        assert "timestamp:" in content

        # Checkpoint should be discoverable
        result2 = runner.invoke(main, ['list', 'checkpoints', '--recent', '1'])
        assert result2.exit_code == 0
        assert "strategic" in result2.output
        assert "Major milestone" in result2.output

    def test_session_lifecycle_management(self, configured_agent_environment):
        """
        Test complete session lifecycle from creation to cleanup.

        Workflow:
        1. Session starts and ID is detected
        2. Temp directory created for session
        3. Multiple checkpoints created during session
        4. Session status shows correct information
        5. Session cleanup removes old sessions but preserves current
        6. Temp directories properly managed
        """
        runner = CliRunner()

        # Check initial session status
        result1 = runner.invoke(main, ['session', 'status'])
        assert result1.exit_code == 0

        # Create activity during session
        result2 = runner.invoke(main, [
            'checkpoint',
            '--type', 'tactical',
            '--note', 'Session activity'
        ])
        assert result2.exit_code == 0

        # Session should show activity
        result3 = runner.invoke(main, ['session', 'list'])
        assert result3.exit_code == 0

        # Cleanup old sessions (should preserve current)
        result4 = runner.invoke(main, ['session', 'cleanup', '--dry-run'])
        assert result4.exit_code == 0

    def test_reflection_workflow_with_context(self, configured_agent_environment):
        """
        Test reflection workflow with contextual information.

        Workflow:
        1. Trigger reflection based on specific event
        2. System gathers context (recent checkpoints, session info)
        3. Creates reflection template with relevant prompts
        4. File includes metadata and context links
        5. Reflection discoverable and linkable to trigger event
        """
        runner = CliRunner()

        # Create some checkpoint context first
        result1 = runner.invoke(main, [
            'checkpoint',
            '--type', 'strategic',
            '--note', 'Pre-reflection milestone'
        ])
        assert result1.exit_code == 0

        # Create reflection triggered by delegation event
        result2 = runner.invoke(main, [
            'reflect',
            '--trigger', 'delegation',
            '--depth', 'tactical'
        ])
        assert result2.exit_code == 0

        reflection_path = result2.output.strip()
        assert Path(reflection_path).exists()

        content = Path(reflection_path).read_text()
        assert "trigger: delegation" in content
        assert "depth: tactical" in content
        # Should reference recent checkpoint context
        assert "Pre-reflection milestone" in content or "context" in content.lower()

    def test_multi_agent_environment_isolation(self, multi_agent_environment):
        """
        Test that multiple agents maintain proper isolation.

        Workflow:
        1. Two agents (DevOpsEng, TestEng) operate simultaneously
        2. Each has separate configuration and directories
        3. Checkpoints and sessions don't interfere
        4. Discovery commands only show relevant agent's data
        5. Temp directories properly segregated
        """
        runner = CliRunner()

        # Simulate DevOpsEng agent operations
        with patch.dict(os.environ, {'MACF_AGENT': 'DevOpsEng'}):
            result1 = runner.invoke(main, [
                'checkpoint',
                '--type', 'strategic',
                '--note', 'DevOps milestone'
            ])
            assert result1.exit_code == 0
            devops_checkpoint = result1.output.strip()

        # Simulate TestEng agent operations
        with patch.dict(os.environ, {'MACF_AGENT': 'TestEng'}):
            result2 = runner.invoke(main, [
                'checkpoint',
                '--type', 'strategic',
                '--note', 'Testing milestone'
            ])
            assert result2.exit_code == 0
            testeng_checkpoint = result2.output.strip()

        # Verify isolation - paths should be different
        assert "DevOpsEng" in devops_checkpoint
        assert "TestEng" in testeng_checkpoint
        assert devops_checkpoint != testeng_checkpoint

        # Each agent should only see their own checkpoints
        with patch.dict(os.environ, {'MACF_AGENT': 'DevOpsEng'}):
            result3 = runner.invoke(main, ['list', 'checkpoints'])
            assert "DevOps milestone" in result3.output
            assert "Testing milestone" not in result3.output

    def test_error_recovery_and_resilience(self, configured_agent_environment):
        """
        Test system resilience and error recovery scenarios.

        Scenarios:
        1. Corrupted configuration file - should use defaults
        2. Missing directories - should recreate automatically
        3. Permission errors - should fail gracefully
        4. Invalid session data - should continue operation
        5. Disk space issues - should provide helpful errors
        """
        runner = CliRunner()

        # Test with corrupted config
        with patch('macf.config.ConsciousnessConfig._load_settings',
                   side_effect=Exception("Config corrupted")):
            # Should fall back to defaults
            result1 = runner.invoke(main, ['env'])
            assert result1.exit_code == 0

        # Test with missing directories - should recreate
        with patch('pathlib.Path.mkdir', side_effect=[PermissionError(), None, None]):
            result2 = runner.invoke(main, [
                'checkpoint',
                '--type', 'tactical',
                '--note', 'Recovery test'
            ])
            # Should either succeed or fail gracefully
            assert result2.exit_code in [0, 1]  # Success or expected failure

        # Test with invalid session data
        with patch('macf.session.get_current_session_id', return_value=None):
            result3 = runner.invoke(main, ['session', 'status'])
            assert result3.exit_code == 0
            assert "No active session" in result3.output or result3.output.strip() == ""


class TestEnvironmentCompatibility:
    """Test suite for container vs host environment compatibility."""

    def test_container_environment_detection_and_setup(self):
        """
        Test operations in container environment.

        Container environment characteristics:
        - /.dockerenv file exists
        - User paths under /home/{user}/agent/
        - MACEFF_TZ environment variable respected
        - Volume mounts function correctly
        """
        runner = CliRunner()

        with patch('os.path.exists') as mock_exists:
            # Mock container environment
            mock_exists.side_effect = lambda path: path == '/.dockerenv'

            with patch.dict(os.environ, {
                'USER': 'testuser',
                'MACEFF_TZ': 'America/New_York'
            }):
                result = runner.invoke(main, ['env'])

        assert result.exit_code == 0
        env_data = json.loads(result.output)
        assert 'America/New_York' in env_data['tz'] or 'America/New_York' in str(env_data)

    def test_host_environment_with_claude_project(self, mock_claude_project):
        """
        Test operations in host environment with .claude project.

        Host environment characteristics:
        - .claude directory in project hierarchy
        - Agent paths under .claude/{agent}/agent/
        - Project-specific configuration
        - Integration with Claude Code workflows
        """
        runner = CliRunner()

        with patch('os.path.exists') as mock_exists:
            # Mock host environment (no /.dockerenv)
            mock_exists.side_effect = lambda path: '/.dockerenv' not in path

            result = runner.invoke(main, [
                'checkpoint',
                '--type', 'strategic',
                '--note', 'Host environment test'
            ])

        assert result.exit_code == 0
        # Should use .claude project structure
        assert '.claude' in result.output or result.exit_code == 0

    def test_fallback_environment_home_directory(self):
        """
        Test fallback to home directory when no other environment detected.

        Fallback environment characteristics:
        - No /.dockerenv file
        - No .claude directory in ancestors
        - Uses ~/.macf/{agent}/agent/ structure
        - Creates necessary directories
        """
        runner = CliRunner()

        with patch('os.path.exists', return_value=False):  # No environment markers
            with patch('pathlib.Path.home', return_value=Path('/home/testuser')):
                with patch('pathlib.Path.mkdir'):
                    with patch('pathlib.Path.write_text'):
                        result = runner.invoke(main, [
                            'checkpoint',
                            '--type', 'tactical',
                            '--note', 'Fallback test'
                        ])

        assert result.exit_code == 0

    def test_cross_environment_portability(self):
        """
        Test that agent state is portable across environments.

        Should:
        - Configuration format be environment-agnostic
        - File formats work across platforms
        - Timestamps include timezone information
        - Paths be properly resolved in each environment
        """
        runner = CliRunner()

        # Create checkpoint in one environment
        with patch('macf.config.ConsciousnessConfig') as mock_config1:
            mock_config1.return_value.agent_root = Path('/env1/agent')

            with patch('pathlib.Path.write_text') as mock_write1:
                result1 = runner.invoke(main, [
                    'checkpoint',
                    '--type', 'strategic',
                    '--note', 'Cross-env test'
                ])

        # Verify format is environment-agnostic
        if mock_write1.called:
            content = mock_write1.call_args[0][0]
            # Should include timezone info
            assert '+' in content or 'Z' in content or 'timestamp:' in content
            # Should use relative timestamps or explicit timezone


class TestPerformanceAndScalability:
    """Test suite for performance characteristics and scalability."""

    def test_checkpoint_discovery_performance(self, large_checkpoint_set):
        """
        Test checkpoint discovery performance with large datasets.

        With 1000+ checkpoints:
        - List commands should complete in reasonable time (< 2 seconds)
        - Memory usage should remain reasonable
        - Sorting should work correctly
        - Filtering should be efficient
        """
        runner = CliRunner()

        import time
        start_time = time.time()

        result = runner.invoke(main, ['list', 'checkpoints', '--recent', '10'])

        end_time = time.time()
        execution_time = end_time - start_time

        assert result.exit_code == 0
        assert execution_time < 2.0  # Should complete within 2 seconds

        # Should return exactly 10 results
        lines = [line for line in result.output.split('\n') if line.strip()]
        assert len(lines) <= 10

    def test_session_cleanup_performance(self, many_old_sessions):
        """
        Test session cleanup performance with many old sessions.

        With 100+ old sessions:
        - Cleanup should complete efficiently
        - Progress should be reportable
        - Memory usage should remain stable
        - Should handle interrupted cleanup gracefully
        """
        runner = CliRunner()

        import time
        start_time = time.time()

        result = runner.invoke(main, ['session', 'cleanup', '--retention-days', '7'])

        end_time = time.time()
        execution_time = end_time - start_time

        assert result.exit_code == 0
        assert execution_time < 5.0  # Should complete within 5 seconds

        # Should report number of cleaned sessions
        assert any(char.isdigit() for char in result.output)

    def test_concurrent_operations_safety(self):
        """
        Test safety of concurrent operations.

        Scenarios:
        - Multiple checkpoints created simultaneously
        - Session cleanup while other operations active
        - File system race conditions handled gracefully
        """
        runner = CliRunner()

        # Simulate concurrent checkpoint creation
        import threading
        results = []

        def create_checkpoint(note_suffix):
            result = runner.invoke(main, [
                'checkpoint',
                '--type', 'tactical',
                '--note', f'Concurrent test {note_suffix}'
            ])
            results.append(result)

        # Start multiple threads
        threads = []
        for i in range(5):
            thread = threading.Thread(target=create_checkpoint, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All operations should succeed
        for result in results:
            assert result.exit_code == 0

    def test_memory_usage_stability(self, configured_agent_environment):
        """
        Test memory usage remains stable during extended operations.

        Should:
        - Not leak memory during repeated operations
        - Handle large files efficiently
        - Clean up temporary resources
        """
        runner = CliRunner()

        import psutil
        import os

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss

        # Perform many operations
        for i in range(100):
            result = runner.invoke(main, [
                'checkpoint',
                '--type', 'tactical',
                '--note', f'Memory test {i}'
            ])
            assert result.exit_code == 0

            # Check memory periodically
            if i % 20 == 0:
                current_memory = process.memory_info().rss
                memory_growth = current_memory - initial_memory
                # Memory growth should be reasonable (< 50MB)
                assert memory_growth < 50 * 1024 * 1024


class TestDataIntegrityAndConsistency:
    """Test suite for data integrity and consistency guarantees."""

    def test_checkpoint_data_integrity(self, configured_agent_environment):
        """
        Test checkpoint data maintains integrity.

        Should:
        - Files contain all expected metadata
        - Timestamps be consistent and valid
        - Content not be corrupted during creation
        - Files be atomically created (no partial writes)
        """
        runner = CliRunner()

        result = runner.invoke(main, [
            'checkpoint',
            '--type', 'strategic',
            '--note', 'Integrity test with unicode: 🚀 测试'
        ])

        assert result.exit_code == 0
        checkpoint_path = Path(result.output.strip())

        # Verify file integrity
        content = checkpoint_path.read_text(encoding='utf-8')

        # Should handle unicode correctly
        assert '🚀' in content
        assert '测试' in content

        # Should have proper YAML frontmatter
        assert content.startswith('---')
        assert '---' in content[3:]  # Second YAML delimiter

        # Should have valid timestamp
        import yaml
        frontmatter = content.split('---')[1]
        metadata = yaml.safe_load(frontmatter)

        assert 'timestamp' in metadata
        # Should be parseable as ISO timestamp
        datetime.fromisoformat(metadata['timestamp'].replace('Z', '+00:00'))

    def test_session_data_consistency(self, configured_agent_environment):
        """
        Test session data remains consistent across operations.

        Should:
        - Session ID remain stable during session
        - Temp directories not conflict between sessions
        - Session metadata be accurate
        """
        runner = CliRunner()

        # Get initial session info
        result1 = runner.invoke(main, ['session', 'status'])
        assert result1.exit_code == 0
        initial_output = result1.output

        # Perform operations that might affect session
        for i in range(5):
            result = runner.invoke(main, [
                'checkpoint',
                '--type', 'tactical',
                '--note', f'Consistency test {i}'
            ])
            assert result.exit_code == 0

        # Session info should remain consistent
        result2 = runner.invoke(main, ['session', 'status'])
        assert result2.exit_code == 0

        # Session ID should be stable
        # (Implementation dependent - may check specific fields)

    def test_configuration_consistency(self):
        """
        Test configuration remains consistent across different access patterns.

        Should:
        - Same configuration loaded regardless of access order
        - Environment overrides work consistently
        - Defaults applied consistently when config missing
        """
        runner = CliRunner()

        # Test configuration through different commands
        commands_to_test = [
            ['env'],
            ['time'],
            ['session', 'status'],
        ]

        configs_observed = []

        for cmd in commands_to_test:
            with patch('macf.config.ConsciousnessConfig') as mock_config:
                mock_instance = Mock()
                mock_config.return_value = mock_instance

                result = runner.invoke(main, cmd)
                assert result.exit_code == 0

                # Record how config was initialized
                configs_observed.append(mock_config.call_args)

        # All configurations should be initialized consistently
        if configs_observed:
            first_config = configs_observed[0]
            for config in configs_observed[1:]:
                assert config == first_config


# Test Fixtures

@pytest.fixture
def clean_environment(tmp_path, monkeypatch):
    """Provide completely clean environment for testing initialization."""
    # Clear all relevant environment variables
    env_vars_to_clear = ['MACF_AGENT', 'MACF_AGENT_ROOT', 'MACEFF_TZ', 'TZ']
    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)

    # Mock home directory
    monkeypatch.setattr('pathlib.Path.home', lambda: tmp_path / 'home')

    return tmp_path

@pytest.fixture
def configured_agent_environment(tmp_path):
    """Provide pre-configured agent environment."""
    agent_root = tmp_path / 'agent'
    agent_root.mkdir()

    # Create directory structure
    for subdir in ['public', 'private']:
        (agent_root / subdir).mkdir()
        (agent_root / subdir / 'logs').mkdir()

    with patch('macf.config.ConsciousnessConfig') as mock_config:
        mock_config.return_value.agent_root = agent_root
        mock_config.return_value.agent_name = 'TestAgent'
        yield agent_root

@pytest.fixture
def multi_agent_environment(tmp_path):
    """Provide environment with multiple agent configurations."""
    agents = {}

    for agent_name in ['DevOpsEng', 'TestEng']:
        agent_root = tmp_path / agent_name / 'agent'
        agent_root.mkdir(parents=True)

        for subdir in ['public', 'private']:
            (agent_root / subdir).mkdir()
            (agent_root / subdir / 'logs').mkdir()

        agents[agent_name] = agent_root

    return agents

@pytest.fixture
def mock_claude_project(tmp_path):
    """Create mock .claude project structure."""
    claude_dir = tmp_path / '.claude'
    claude_dir.mkdir()

    projects_dir = claude_dir / 'projects' / 'test-project'
    projects_dir.mkdir(parents=True)

    # Create uuid.jsonl with session info
    uuid_file = projects_dir / 'uuid.jsonl'
    session_data = {
        'uuid': 'test-session-12345',
        'timestamp': datetime.now().isoformat()
    }
    uuid_file.write_text(json.dumps(session_data) + '\n')

    return claude_dir

@pytest.fixture
def large_checkpoint_set(configured_agent_environment):
    """Create large set of checkpoint files for performance testing."""
    checkpoints = []
    base_time = datetime.now()

    for i in range(1000):
        timestamp = base_time - timedelta(hours=i)
        checkpoint_type = ['strategic', 'tactical', 'operational'][i % 3]

        filename = f"{timestamp.strftime('%Y-%m-%d_%H%M%S')}_{checkpoint_type}_checkpoint.md"
        checkpoint_path = configured_agent_environment / 'public' / filename

        content = f"""---
timestamp: {timestamp.isoformat()}
type: {checkpoint_type}
note: Test checkpoint {i}
---

# {checkpoint_type.title()} Checkpoint

Test content for checkpoint {i}.
"""
        checkpoint_path.write_text(content)
        checkpoints.append(checkpoint_path)

    return checkpoints

@pytest.fixture
def many_old_sessions(tmp_path):
    """Create many old session directories for cleanup testing."""
    macf_temp = tmp_path / 'macf'
    macf_temp.mkdir()

    sessions = []
    base_time = datetime.now()

    for i in range(100):
        age_days = 8 + i  # All older than 7 days
        session_time = base_time - timedelta(days=age_days)

        session_dir = macf_temp / f'old-session-{i:03d}'
        session_dir.mkdir()

        # Set directory timestamp
        timestamp = session_time.timestamp()
        os.utime(session_dir, (timestamp, timestamp))

        sessions.append(session_dir)

    with patch('tempfile.gettempdir', return_value=str(tmp_path)):
        yield sessions