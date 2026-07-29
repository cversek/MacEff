

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
