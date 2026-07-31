"""Tier-1 request-size telemetry (cversek/MacEff#162).

A long-lived session died unrecoverably at the client's request-size wall: the
client refused to serialize, `/compact` failed the same way (it takes the same
path), and `/clear` — total context loss — was the only exit. The proxy log
proved the rejection was client-side but could not show *what* had grown,
because it recorded only counts (message_count, tool_count), never bytes.
"""
import json

import pytest

import macf.proxy.server as server
from macf.proxy.server import _block_byte_census, _extract_request_meta


@pytest.fixture(autouse=True)
def _reset_warn_state(monkeypatch):
    monkeypatch.setattr(server, "_request_size_warned", False, raising=False)
    monkeypatch.delenv("MACF_PROXY_CAPTURE_DIR", raising=False)


def _body(messages, **kw):
    return json.dumps({"model": "m", "messages": messages, "system": "", **kw}).encode()


def test_request_bytes_matches_serialized_size():
    body = _body([{"role": "user", "content": "hi"}])
    assert _extract_request_meta(body)["request_bytes"] == len(body)


def test_census_attributes_nested_image_payload():
    """The bytes live in source.data — a top-level len() would undercount."""
    census = _block_byte_census([
        {"role": "user", "content": [
            {"type": "text", "text": "x" * 10},
            {"type": "image", "source": {"type": "base64", "data": "A" * 5000}},
        ]},
    ])
    assert census["image"] > 5000
    assert census["image"] > census["text"] * 10


def test_census_counts_tool_results_separately():
    census = _block_byte_census([
        {"role": "user", "content": [{"type": "tool_result", "content": "B" * 2000}]},
    ])
    assert census["tool_result"] > 2000
    assert "image" not in census


def test_census_handles_plain_string_content():
    """Not every message uses content blocks."""
    assert _block_byte_census([{"role": "a", "content": "hello"}])["text"] == 5


def test_census_survives_malformed_blocks():
    """Telemetry must never be the thing that breaks a request."""
    census = _block_byte_census([{"role": "u", "content": ["not-a-dict", None]}])
    assert isinstance(census, dict)


def test_unparseable_body_still_records_size():
    """A body too large or malformed to parse is exactly what we want logged."""
    meta = _extract_request_meta(b"{not json")
    assert meta["parse_error"] is True
    assert meta["request_bytes"] == len(b"{not json")


def test_warning_fires_once_above_threshold(capsys, monkeypatch):
    monkeypatch.setattr(server, "_request_size_warned", False, raising=False)
    server._warn_if_request_growing(int(server.CLIENT_REQUEST_WALL_BYTES * 0.9))
    first = capsys.readouterr().err
    server._warn_if_request_growing(server.CLIENT_REQUEST_WALL_BYTES)
    second = capsys.readouterr().err
    assert "% of the client's" in first
    assert second == "", "warning must be one-shot, not per-request noise"


def test_no_warning_below_threshold(capsys, monkeypatch):
    monkeypatch.setattr(server, "_request_size_warned", False, raising=False)
    server._warn_if_request_growing(1024)
    assert capsys.readouterr().err == ""


def test_ratio_zero_disables_the_warning(monkeypatch):
    monkeypatch.setenv("MACF_PROXY_SIZE_WARN_RATIO", "0")
    assert server._request_warn_at() == 0
