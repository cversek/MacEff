#!/usr/bin/env python3
"""
Unit tests for token/context awareness formatting utilities.

Tests DRY formatting functions:
- format_token_context_minimal()
- format_token_context_full()
- get_boundary_guidance()
"""

import pytest

from macf.utils import (
    format_token_context_minimal,
    format_token_context_full,
    get_boundary_guidance,
)
from macf.utils.tokens import get_cluac_weather


def test_format_token_context_minimal_structure():
    """Minimal format returns one-line CLUAC indicator."""
    token_info = {
        'tokens_used': 120000,
        'tokens_remaining': 80000,
        'percentage_used': 60.0,
        'cluac_level': 40
    }

    result = format_token_context_minimal(token_info)

    # Validate structure (not exact string)
    assert "CLUAC" in result
    assert "40" in result
    assert "60%" in result
    assert result.count('\n') == 0  # Single line


def test_format_token_context_full_all_fields():
    """Full format includes all token fields with emoji header."""
    token_info = {
        'tokens_used': 120000,
        'tokens_remaining': 80000,
        'percentage_used': 60.0,
        'cluac_level': 40
    }

    result = format_token_context_full(token_info)

    # Validate multi-line structure with emoji
    assert "📊 TOKEN/CONTEXT AWARENESS" in result
    assert "Tokens Used:" in result
    assert "120,000" in result  # Comma formatting
    assert "CLUAC Level:" in result
    assert "40" in result
    assert "60.0%" in result
    assert "Remaining:" in result
    assert "80,000" in result
    assert result.count('\n') > 0  # Multi-line


def test_boundary_guidance_manual_mode_cluac2():
    """MANUAL mode CLUAC<=2 returns emergency stop message."""
    result = get_boundary_guidance(cluac=2, auto_mode=False)

    assert result is not None
    assert "EMERGENCY" in result
    assert "MANUAL" in result
    assert "STOP" in result.upper()


def test_boundary_guidance_auto_mode_cluac5():
    """AUTO mode CLUAC<=5 returns preparation message."""
    result = get_boundary_guidance(cluac=5, auto_mode=True)

    assert result is not None
    assert "PREPARATION MODE" in result
    assert "AUTO" in result
    assert "CCP" in result


def test_boundary_guidance_none_when_cluac_high():
    """No warnings above CLUAC 10."""
    # Test various high CLUAC values
    assert get_boundary_guidance(cluac=11, auto_mode=False) is None
    assert get_boundary_guidance(cluac=50, auto_mode=True) is None
    assert get_boundary_guidance(cluac=100, auto_mode=False) is None


def test_boundary_guidance_mode_aware_branching():
    """MANUAL vs AUTO return different messages for same CLUAC."""
    manual_msg = get_boundary_guidance(cluac=2, auto_mode=False)
    auto_msg = get_boundary_guidance(cluac=2, auto_mode=True)

    # Both should return messages
    assert manual_msg is not None
    assert auto_msg is not None

    # But they should differ in content
    assert manual_msg != auto_msg
    assert "MANUAL" in manual_msg
    assert "AUTO" in auto_msg

    # MANUAL says STOP, AUTO says write artifacts
    assert "STOP" in manual_msg.upper()
    assert ("CCP" in auto_msg or "artifacts" in auto_msg)


def test_get_cluac_weather_affirmative_framing():
    """Weather function returns affirmative emoji+phrase for each CLUAC band."""
    # Fresh context (70+)
    assert "🌅" in get_cluac_weather(100)
    assert "🌅" in get_cluac_weather(70)
    assert "Fresh" in get_cluac_weather(85)

    # Abundance mode (40-69)
    assert "🌤️" in get_cluac_weather(69)
    assert "🌤️" in get_cluac_weather(40)
    assert "Abundance" in get_cluac_weather(55)

    # Well-invested (15-39)
    assert "🌆" in get_cluac_weather(39)
    assert "🌆" in get_cluac_weather(15)
    assert "invested" in get_cluac_weather(25)

    # Navigate to shore (5-14)
    assert "🌙" in get_cluac_weather(14)
    assert "🌙" in get_cluac_weather(5)
    assert "shore" in get_cluac_weather(10)

    # Ready to jump (<5)
    assert "🪂" in get_cluac_weather(4)
    assert "🪂" in get_cluac_weather(1)
    assert "jump" in get_cluac_weather(2)
