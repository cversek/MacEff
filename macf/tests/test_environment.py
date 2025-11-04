"""
Test specifications for macf.utils.environment module.

Tests environment detection and rich system information formatting
with cross-platform compatibility (Mac, Linux, Windows).

Following pragmatic TDD principles - 4-6 focused tests per function.
"""

import os
from pathlib import Path
from unittest.mock import patch, Mock
import pytest

from macf.utils.environment import detect_execution_environment, get_rich_environment_string


class TestDetectExecutionEnvironment:
    """Test suite for detect_execution_environment() - moved from temporal.py."""

    def test_detects_container_environment(self, monkeypatch):
        """
        Test detection of MacEff container environment.

        When /.dockerenv exists, should return container string with username.
        """
        monkeypatch.setenv("MACEFF_USER", "testuser")

        with patch.object(Path, 'exists', return_value=True):
            result = detect_execution_environment()

        assert result == "MacEff Container (testuser)"

    def test_detects_container_with_user_fallback(self, monkeypatch):
        """
        Test container detection uses USER env var if MACEFF_USER missing.
        """
        monkeypatch.delenv("MACEFF_USER", raising=False)
        monkeypatch.setenv("USER", "fallbackuser")

        with patch.object(Path, 'exists', return_value=True):
            result = detect_execution_environment()

        assert result == "MacEff Container (fallbackuser)"

    def test_detects_maceff_host_system(self, tmp_path):
        """
        Test detection of MacEff project on host system.

        When "MacEff" appears in directory tree, should return host system marker.
        """
        # Create directory structure: /tmp/xyz/MacEff/tools/
        maceff_dir = tmp_path / "MacEff" / "tools"
        maceff_dir.mkdir(parents=True)

        with patch.object(Path, 'exists', return_value=False):  # Not container
            with patch.object(Path, 'cwd', return_value=maceff_dir):
                result = detect_execution_environment()

        assert result == "MacEff Host System"

    def test_fallback_to_generic_host(self, tmp_path):
        """
        Test fallback to generic host when no markers found.

        When not in container and no MacEff markers, should return generic.
        """
        generic_dir = tmp_path / "some" / "random" / "path"
        generic_dir.mkdir(parents=True)

        with patch.object(Path, 'exists', return_value=False):  # Not container
            with patch.object(Path, 'cwd', return_value=generic_dir):
                result = detect_execution_environment()

        assert result == "Host System"


class TestGetRichEnvironmentString:
    """Test suite for get_rich_environment_string() - new cross-platform function."""

    def test_mac_environment_formatting(self, monkeypatch):
        """
        Test rich environment string on Mac (Darwin).

        Should compose base + hostname + OS + version.
        """
        with patch('macf.utils.environment.detect_execution_environment', return_value="Host System"):
            with patch('macf.utils.environment.socket.gethostname', return_value="Craigs-MacBook-Pro.local"):
                with patch('macf.utils.environment.platform.system', return_value="Darwin"):
                    with patch('macf.utils.environment.platform.release', return_value="24.5.0"):
                        result = get_rich_environment_string()

        assert result == "Host System - Craigs-MacBook-Pro.local Darwin 24.5.0"

    def test_linux_environment_formatting(self):
        """
        Test rich environment string on Linux.

        Should work with Linux kernel versions.
        """
        with patch('macf.utils.environment.detect_execution_environment', return_value="MacEff Host System"):
            with patch('macf.utils.environment.socket.gethostname', return_value="dev-server"):
                with patch('macf.utils.environment.platform.system', return_value="Linux"):
                    with patch('macf.utils.environment.platform.release', return_value="5.15.0-76-generic"):
                        result = get_rich_environment_string()

        assert result == "MacEff Host System - dev-server Linux 5.15.0-76-generic"

    def test_windows_environment_formatting(self):
        """
        Test rich environment string on Windows.

        Should work with Windows version strings.
        """
        with patch('macf.utils.environment.detect_execution_environment', return_value="Host System"):
            with patch('macf.utils.environment.socket.gethostname', return_value="WIN-DESKTOP"):
                with patch('macf.utils.environment.platform.system', return_value="Windows"):
                    with patch('macf.utils.environment.platform.release', return_value="10"):
                        result = get_rich_environment_string()

        assert result == "Host System - WIN-DESKTOP Windows 10"

    def test_container_environment_formatting(self):
        """
        Test rich environment string in container context.

        Should preserve container username in output.
        """
        with patch('macf.utils.environment.detect_execution_environment', return_value="MacEff Container (maceff_user001)"):
            with patch('macf.utils.environment.socket.gethostname', return_value="docker-abc123"):
                with patch('macf.utils.environment.platform.system', return_value="Linux"):
                    with patch('macf.utils.environment.platform.release', return_value="6.2.0"):
                        result = get_rich_environment_string()

        assert result == "MacEff Container (maceff_user001) - docker-abc123 Linux 6.2.0"

    def test_graceful_fallback_on_hostname_failure(self):
        """
        Test safe failure when hostname unavailable.

        Should never crash - use fallback values.
        """
        with patch('macf.utils.environment.detect_execution_environment', return_value="Host System"):
            with patch('macf.utils.environment.socket.gethostname', side_effect=Exception("Network error")):
                with patch('macf.utils.environment.platform.system', return_value="Linux"):
                    with patch('macf.utils.environment.platform.release', return_value="5.15.0"):
                        result = get_rich_environment_string()

        # Should not crash, should use fallback
        assert "unknown-host" in result
        assert "Linux 5.15.0" in result

    def test_graceful_fallback_on_platform_failure(self):
        """
        Test safe failure when platform info unavailable.

        Should degrade gracefully with unknown values.
        """
        with patch('macf.utils.environment.detect_execution_environment', return_value="Host System"):
            with patch('macf.utils.environment.socket.gethostname', return_value="testhost"):
                with patch('macf.utils.environment.platform.system', side_effect=Exception("Platform error")):
                    with patch('macf.utils.environment.platform.release', side_effect=Exception("Version error")):
                        result = get_rich_environment_string()

        # Should not crash, should contain fallback values
        assert "testhost" in result
        assert "Unknown" in result
        assert "unknown" in result
