

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


class TestUpstreamErrorBodyCaptured:
    """A 4xx status without its body is not a diagnosis.

    The middleware logged upstream_error_status with detail="" hardcoded. When
    a 429 arrived, we could see that it happened but not what it said -- and
    the distinction mattered enormously: a long-context-credits 429 makes the
    client permanently clamp its context window to 200K, while an ordinary rate
    limit is harmless. Same status, opposite meaning, no way to tell them apart.
    """

    def _log(self, tmp_path, monkeypatch, response):
        import asyncio, json
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
        from macf.proxy import server

        class FakeRequest(dict):
            method = "POST"
            path = "/v1/messages"
            headers = {}

        async def handler(_req):
            return response

        mw = server._make_error_middleware()
        asyncio.run(mw(FakeRequest(), handler))

        log = tmp_path / ".maceff" / "agent_api_log.jsonl"
        if not log.exists():
            log = next(tmp_path.rglob("agent_api_log.jsonl"))
        recs = [json.loads(x) for x in log.read_text().splitlines() if x.strip()]
        return [r for r in recs if r.get("kind") == "upstream_error_status"][-1]

    def test_body_is_recorded(self, tmp_path, monkeypatch):
        class Resp:
            status = 429
            body = b'{"error":{"message":"Extra usage is required for long context"}}'
        rec = self._log(tmp_path, monkeypatch, Resp())
        assert "long context" in rec["detail"]

    def test_streaming_body_is_named_not_silently_empty(self, tmp_path, monkeypatch):
        class Resp:
            status = 429
            body = None
        rec = self._log(tmp_path, monkeypatch, Resp())
        assert rec["detail"], "an empty detail is indistinguishable from 'no body existed'"
        assert "streaming" in rec["detail"]


class TestQueryStringReachesUpstreamLive:
    """End-to-end proof, against a real upstream, that ?beta=true survives.

    The source-level assertions above catch the regression, but only this
    catches it if the URL is ever built somewhere new. Verified to FAIL when
    request.path_qs is reverted to request.path -- an assertion never observed
    failing is not evidence.
    """

    def test_query_string_and_entitlement_headers_survive(self, tmp_path, monkeypatch):
        import asyncio, json
        from aiohttp import web, ClientSession
        monkeypatch.setenv("MACEFF_AGENT_HOME_DIR", str(tmp_path))
        from macf.proxy import server

        seen = {}

        async def echo(request):
            seen["path_qs"] = request.path_qs
            seen["beta"] = request.headers.get("anthropic-beta")
            seen["auth"] = request.headers.get("authorization")
            return web.json_response({"ok": True})

        async def scenario():
            up = web.Application()
            up.router.add_route("*", "/{p:.*}", echo)
            r1 = web.AppRunner(up); await r1.setup()
            s1 = web.TCPSite(r1, "127.0.0.1", 8741); await s1.start()

            monkeypatch.setattr(server, "ANTHROPIC_API_URL", "http://127.0.0.1:8741")
            r2 = web.AppRunner(server._create_app()); await r2.setup()
            s2 = web.TCPSite(r2, "127.0.0.1", 8742); await s2.start()
            try:
                async with ClientSession() as c:
                    await c.post(
                        "http://127.0.0.1:8742/v1/messages?beta=true",
                        data=json.dumps({"model": "claude-opus-5", "messages": []}),
                        headers={
                            "anthropic-beta": "context-1m-2025-08-07",
                            "authorization": "Bearer test-token",
                            "content-type": "application/json",
                        },
                    )
            finally:
                await r2.cleanup(); await r1.cleanup()

        asyncio.run(scenario())

        # The query string carries the beta opt-in. Dropping it caused upstream
        # to answer as if the long-context entitlement were absent.
        assert seen["path_qs"] == "/v1/messages?beta=true"
        # Entitlement also rides on these; the hop-by-hop filter must not eat them.
        assert seen["beta"] == "context-1m-2025-08-07"
        assert seen["auth"] == "Bearer test-token"


class TestWindowClampDetector:
    """The 200K-window clamp is silent on the client side; the proxy must not be.

    This is the instrument that would have collapsed a months-long hunt into one
    log line. It is tested for the property that actually matters: it fires
    BEFORE the ~167K compaction point, so the warning arrives while the session
    is still alive to act on it.
    """

    def _reset(self):
        from macf.proxy import server
        server._window_warned = False

    def test_fires_before_the_167k_compaction_point(self):
        """A warning that arrives after the symptom is useless."""
        from macf.proxy import server
        assert server.WINDOW_WARN_AT < 167_000, (
            "warn threshold must sit below the observed ~167K compaction point"
        )

    def test_warns_when_context_crosses_threshold(self, capsys):
        from macf.proxy import server
        self._reset()
        server._warn_if_approaching_clamp({"input_tokens": 160_000})
        err = capsys.readouterr().err
        assert "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL" in err, (
            "the warning must name the remedy, not just report a number"
        )
        assert "160,000" in err

    def test_silent_below_threshold(self, capsys):
        from macf.proxy import server
        self._reset()
        server._warn_if_approaching_clamp({"input_tokens": 1_000})
        assert capsys.readouterr().err == ""

    def test_sums_cache_tokens_not_just_input_tokens(self, capsys):
        """input_tokens alone is ~2 on a cached turn; summing is the whole point."""
        from macf.proxy import server
        self._reset()
        server._warn_if_approaching_clamp({
            "input_tokens": 2,
            "cache_read_input_tokens": 155_000,
            "cache_creation_input_tokens": 1_000,
        })
        assert "156,002" in capsys.readouterr().err

    def test_warns_only_once_per_process(self, capsys):
        from macf.proxy import server
        self._reset()
        server._warn_if_approaching_clamp({"input_tokens": 160_000})
        capsys.readouterr()
        server._warn_if_approaching_clamp({"input_tokens": 170_000})
        assert capsys.readouterr().err == ""

    def test_wired_into_log_event_for_api_responses(self, capsys, tmp_path,
                                                    monkeypatch):
        """Negative control on the wiring: the detector is useless if unreachable."""
        from macf.proxy import server
        self._reset()
        monkeypatch.setattr(server, "get_log_path",
                            lambda: tmp_path / "proxy.jsonl")
        server._log_event({"type": "api_response",
                           "usage": {"input_tokens": 160_000}})
        assert "_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL" in capsys.readouterr().err

    def test_log_event_does_not_recurse(self, capsys, tmp_path, monkeypatch):
        """The detector logs an event itself; that must not re-enter the guard."""
        from macf.proxy import server
        self._reset()
        monkeypatch.setattr(server, "get_log_path",
                            lambda: tmp_path / "proxy.jsonl")
        server._log_event({"type": "api_response",
                           "usage": {"input_tokens": 160_000}})
        import json as _json
        lines = (tmp_path / "proxy.jsonl").read_text().strip().split("\n")
        kinds = [_json.loads(x)["type"] for x in lines]
        assert kinds.count("window_clamp_watch") == 1
        assert kinds.count("api_response") == 1


class TestCaptureBounded:
    """Capture must not be able to fill the disk or kill the request it observes.

    Shipped unbounded and unguarded: measured 117MB/427 files after one session,
    with the request-side write sitting OUTSIDE the handler's try block.
    """

    def _mk(self, tmp_path, n, size=1000):
        import os as _os
        for i in range(n):
            f = tmp_path / f"{1000+i}_m_request.json"
            f.write_text("x" * size)
            _os.utime(f, (1000 + i, 1000 + i))  # deterministic age ordering
        return sorted(tmp_path.glob("*.json"))

    def test_cap_default_and_override(self, monkeypatch):
        from macf.proxy import server
        monkeypatch.delenv("MACF_PROXY_CAPTURE_MAX_MB", raising=False)
        assert server._capture_cap_bytes() == server.CAPTURE_MAX_MB * 1024 * 1024
        monkeypatch.setenv("MACF_PROXY_CAPTURE_MAX_MB", "3")
        assert server._capture_cap_bytes() == 3 * 1024 * 1024

    def test_zero_disables_the_bound(self, monkeypatch, tmp_path):
        """0 must mean unbounded, not 'evict everything'."""
        from macf.proxy import server
        monkeypatch.setenv("MACF_PROXY_CAPTURE_MAX_MB", "0")
        self._mk(tmp_path, 5)
        server._capture_evict(tmp_path)
        assert len(list(tmp_path.glob("*.json"))) == 5

    def test_garbage_env_falls_back_to_default(self, monkeypatch):
        from macf.proxy import server
        monkeypatch.setenv("MACF_PROXY_CAPTURE_MAX_MB", "not-a-number")
        assert server._capture_cap_bytes() == server.CAPTURE_MAX_MB * 1024 * 1024

    def test_evicts_oldest_first_until_under_cap(self, monkeypatch, tmp_path):
        from macf.proxy import server
        # 10 files x 1000B = ~10KB; cap to roughly 4KB worth
        self._mk(tmp_path, 10, size=1000)
        monkeypatch.setattr(server, "_capture_cap_bytes", lambda: 4000)
        server._capture_evict(tmp_path)
        left = sorted(p.name for p in tmp_path.glob("*.json"))
        assert sum(p.stat().st_size for p in tmp_path.glob("*.json")) <= 4000
        # the SURVIVORS must be the newest ones
        assert left == sorted(f"{1000+i}_m_request.json" for i in range(6, 10))

    def test_write_failure_returns_false_and_does_not_raise(self, tmp_path):
        """A full/read-only disk must degrade to 'no capture', not fail the request."""
        from macf.proxy import server
        blocked = tmp_path / "afile"
        blocked.write_text("not a directory")
        assert server._capture_write(blocked, "x.json", "data") is False

    def test_writes_bytes_payload(self, tmp_path):
        from macf.proxy import server
        assert server._capture_write(tmp_path, "r.raw", b"\x00\x01raw") is True
        assert (tmp_path / "r.raw").read_bytes() == b"\x00\x01raw"

    def test_eviction_is_amortised_not_every_write(self, tmp_path, monkeypatch):
        """Scanning the dir on every write would add O(n) stats to the hot path."""
        from macf.proxy import server
        calls = []
        monkeypatch.setattr(server, "_capture_evict", lambda c: calls.append(1))
        server._capture_writes = 0
        for i in range(server._CAPTURE_EVICT_EVERY):
            server._capture_write(tmp_path, f"f{i}.json", "x")
        assert len(calls) == 1
