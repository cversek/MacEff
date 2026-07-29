

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
