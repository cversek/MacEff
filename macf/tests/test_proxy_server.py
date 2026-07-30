

class TestClientMaxSize:
    """The proxy must not impose a stricter body limit than upstream.

    aiohttp's web.Application defaults to client_max_size=1 MiB and rejects
    larger bodies with 413 before any handler runs. Claude Code renders any
    413 as "Request too large (max 32MB)" and its only recovery is stripping
    images/documents — so a media-free session wedges permanently.
    """

    def test_app_configured_above_aiohttp_default(self):
        from macf.proxy.server import _create_app, MAX_REQUEST_BYTES
        assert MAX_REQUEST_BYTES > 1024 * 1024
        app = _create_app()
        assert app._client_max_size == MAX_REQUEST_BYTES

    def test_limit_overridable_by_env(self, monkeypatch):
        monkeypatch.setenv("MACF_PROXY_MAX_REQUEST_BYTES", "12345678")
        import importlib
        from macf.proxy import server
        importlib.reload(server)
        try:
            assert server.MAX_REQUEST_BYTES == 12345678
        finally:
            monkeypatch.delenv("MACF_PROXY_MAX_REQUEST_BYTES", raising=False)
            importlib.reload(server)


class TestFailurePathObservability:
    """Failures must appear in the same log readers already watch.

    The original bug survived months because every instrument sat AFTER
    `await request.read()` — the exact call that fails on oversized bodies.
    An empty log was read as "the request never arrived" when it meant
    "the request died upstream of the instruments".
    """

    def test_rejection_is_logged_with_unambiguous_kind(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
        from macf.proxy import server

        class FakeRequest(dict):
            method = "POST"
            path = "/v1/messages"
            content_length = 8200

        server._log_error_event(FakeRequest(), 413,
                                "request_too_large_REJECTED_BY_THIS_PROXY", "too big")

        import json
        lines = (tmp_path / ".maceff" / "agent_api_log.jsonl").read_text().splitlines()
        rec = json.loads(lines[-1])
        assert rec["type"] == "api_error"
        assert rec["status"] == 413
        # names the culprit, so silence can never again be read as innocence
        assert "REJECTED_BY_THIS_PROXY" in rec["kind"]
        assert rec["client_max_size"] == server.MAX_REQUEST_BYTES

    def test_error_logging_is_idempotent_per_request(self, tmp_path, monkeypatch):
        """Handler diagnosis + middleware catch = one failure, one record."""
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
        from macf.proxy import server

        class FakeRequest(dict):
            method = "POST"
            path = "/v1/messages"
            content_length = 8200

        req = FakeRequest()
        server._log_error_event(req, 413, "precise_diagnosis", "from handler")
        server._log_error_event(req, 413, "http_exception", "from middleware")

        lines = (tmp_path / ".maceff" / "agent_api_log.jsonl").read_text().splitlines()
        assert len(lines) == 1

    def test_startup_logs_effective_limits(self, tmp_path, monkeypatch):
        """Silent defaults are invisible policy — log what is actually in force."""
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
        from macf.proxy import server

        server._log_effective_config(8019, "127.0.0.1")

        import json
        rec = json.loads((tmp_path / ".maceff" / "agent_api_log.jsonl").read_text().splitlines()[-1])
        assert rec["type"] == "proxy_start"
        assert rec["client_max_size"] == server.MAX_REQUEST_BYTES
        assert rec["port"] == 8019


class TestQueryStringPreservation:
    """The upstream URL must carry the client's query string.

    Both handlers built target_url from `request.path`, which silently drops
    everything after `?`. The client sends `/v1/messages?beta=true`; upstream
    therefore never saw the long-context beta flag. A beta request stripped of
    its flag is the shape that draws a 429 — and one 429 latches a sticky,
    process-lifetime clamp of the client's context window from 1M down to 200K.
    The client then refuses to send at ~180K while its own banner still shows
    1M, fabricating "Prompt is too long" locally without calling the API.

    Nothing about that failure points back here, so it is asserted at the source.
    """

    def _handler_sources(self):
        import inspect
        from macf.proxy import server
        src = inspect.getsource(server)
        return [
            line for line in src.splitlines()
            if "target_url" in line and "ANTHROPIC_API_URL" in line
        ]

    def test_handlers_exist(self):
        # Guards the assertions below against silently matching nothing.
        assert len(self._handler_sources()) >= 2

    def test_no_handler_uses_bare_request_path(self):
        for line in self._handler_sources():
            assert "request.path_qs" in line, (
                f"target_url must preserve the query string, got: {line.strip()}"
            )
            assert "{request.path}" not in line


class TestRewriteGate:
    """The advertised gate and the enforced gate must be the same value.

    The startup banner reported `rewrite_enabled` from MACF_PROXY_REWRITE while
    the request path called rewrite_messages unconditionally — so the proxy
    printed rewrite=off while rewriting every request. A reported value that
    diverges from the enforced value, with nothing reconciling them, is the
    antipattern this whole investigation kept rediscovering.
    """

    def test_gate_defaults_off(self, monkeypatch):
        monkeypatch.delenv("MACF_PROXY_REWRITE", raising=False)
        from macf.proxy.server import _rewrite_enabled
        assert _rewrite_enabled() is False

    def test_gate_accepts_truthy_spellings(self, monkeypatch):
        from macf.proxy.server import _rewrite_enabled
        for val in ("on", "1", "true", "yes", "ON", " True "):
            monkeypatch.setenv("MACF_PROXY_REWRITE", val)
            assert _rewrite_enabled() is True, val
        for val in ("off", "0", "false", "no", ""):
            monkeypatch.setenv("MACF_PROXY_REWRITE", val)
            assert _rewrite_enabled() is False, val

    def test_request_path_consults_the_same_helper_as_the_banner(self):
        import inspect
        from macf.proxy import server
        src = inspect.getsource(server)
        # The banner reports it...
        assert '"rewrite_enabled": _rewrite_enabled()' in src
        # ...and the request path must gate on it, not run unconditionally.
        assert "if _rewrite_enabled():" in src
        gated = src.split("if _rewrite_enabled():", 1)[1]
        assert "rewrite_messages(messages)" in gated.split("# 3.", 1)[0]
