#!/usr/bin/env python3
"""Tests for AUTO_MODE detection."""

import pytest

from macf.utils import detect_auto_mode


def test_returns_default_when_nothing_configured(monkeypatch):
    """Returns default when nothing configured."""
    # Clear all environment variables
    monkeypatch.delenv("MACF_AUTO_MODE", raising=False)

    # Mock find_project_root to return non-existent path
    from pathlib import Path
    monkeypatch.setattr("macf.utils.find_project_root", lambda: Path("/nonexistent"))

    enabled, source, confidence = detect_auto_mode("test-session")

    assert enabled is False
    assert source == "default"
    assert confidence == 0.0


def test_detects_environment_variable_true(monkeypatch):
    """Detects environment variable for true."""
    monkeypatch.setenv("MACF_AUTO_MODE", "true")

    enabled, source, confidence = detect_auto_mode("test-session")

    assert enabled is True
    assert source == "env"
    assert confidence == 0.9


def test_detects_environment_variable_false(monkeypatch):
    """Detects environment variable for false."""
    monkeypatch.setenv("MACF_AUTO_MODE", "false")

    enabled, source, confidence = detect_auto_mode("test-session")

    assert enabled is False
    assert source == "env"
    assert confidence == 0.9


def test_returns_valid_tuple_format():
    """Returns valid tuple format (bool, str, float)."""
    enabled, source, confidence = detect_auto_mode("test-session")

    assert isinstance(enabled, bool)
    assert isinstance(source, str)
    assert isinstance(confidence, float)


def test_confidence_scores_in_valid_range(monkeypatch):
    """Confidence scores are in 0.0-1.0 range."""
    # Test various scenarios
    scenarios = [
        ("true", "env", 0.9),
        ("false", "env", 0.9),
        ("", "default", 0.0),
    ]

    for env_value, expected_source, expected_confidence in scenarios:
        if env_value:
            monkeypatch.setenv("MACF_AUTO_MODE", env_value)
        else:
            monkeypatch.delenv("MACF_AUTO_MODE", raising=False)
            monkeypatch.setattr("macf.utils.find_project_root", lambda: __import__('pathlib').Path("/nonexistent"))

        enabled, source, confidence = detect_auto_mode("test-session")

        assert 0.0 <= confidence <= 1.0, f"Confidence {confidence} out of range"
        assert source == expected_source
