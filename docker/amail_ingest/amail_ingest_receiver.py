#!/opt/maceff-venv/bin/python
"""amail ingest RECEIVER -- the real thing the stub stood in for.

Replaces amail_ingest_stub.py once M2/M3/M4 were read from the stub's log
(2026-08-15: edge enforcement confirmed within-subject, service tokens
admitted, JWT assertion present on service-token auth -- see the gate
measurements experiment record).

Trust model -- the JWT check is the HARD CONDITION that
made the tunnel design acceptable, because the inbound surface stays real in
two places Access cannot cover:

  (a) Access is configuration, not structure: a dashboard edit can silently
      ungate the hostname. A valid assertion cannot be minted without
      Cloudflare's signing key, so requests arriving through a drifted-open
      gate still fail here.
  (b) This listener binds 127.0.0.1, but any co-resident uid can reach it.
      A local forger cannot produce a Cloudflare-signed assertion either.

So: NO valid Cf-Access-Jwt-Assertion (RS256 against the team JWKS, aud
pinned, exp enforced) => 403, logged, nothing written. The payload is then
integrity-checked (sha256 recomputed over the decoded bytes and compared to
the Worker's claim) and spooled for the broker. The receiver makes NO trust
decision about the MAIL -- observed metadata stays trusted:false all the way
to the broker, per the courier-not-a-guard division.

The assertion's common_name (which token authenticated) is logged on every
accepted request. Once the production token exists, INGEST_PIN_COMMON_NAME
may be set to pin it -- a finer gate on top of aud.

Config (env):
  INGEST_TEAM_DOMAIN       e.g. https://billowing-fire-e7c8.cloudflareaccess.com
  INGEST_AUD               the Access application audience tag (64 hex)
  INGEST_PIN_COMMON_NAME   optional; refuse tokens other than this one
  AMAIL_INGEST_PORT        default 8025 (same port the stub held)
  AMAIL_INGEST_LOG         default /var/lib/amail_ingest/ingest_receiver.jsonl
  AMAIL_INGEST_SPOOL       default /var/lib/amail_ingest/spool
  INGEST_JWKS_URL          override for tests (default <team>/cdn-cgi/access/certs)

Fail-closed everywhere: unknown kid triggers ONE JWKS refetch then refusal;
JWKS unreachable at request time refuses rather than accepting unverified;
oversized Content-Length refused before the body is read; sha256 mismatch
refused so a corrupted or tampered payload is never spooled as mail.
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import jwt as pyjwt
from jwt import PyJWKClient

TEAM_DOMAIN = os.environ.get("INGEST_TEAM_DOMAIN", "").rstrip("/")
AUD = os.environ.get("INGEST_AUD", "")
PIN_CN = os.environ.get("INGEST_PIN_COMMON_NAME") or None
BIND = ("127.0.0.1", int(os.environ.get("AMAIL_INGEST_PORT", "8025")))
LOG_PATH = Path(os.environ.get("AMAIL_INGEST_LOG",
                               "/var/lib/amail_ingest/ingest_receiver.jsonl"))
SPOOL = Path(os.environ.get("AMAIL_INGEST_SPOOL",
                            "/var/lib/amail_ingest/spool"))
JWKS_URL = os.environ.get("INGEST_JWKS_URL",
                          f"{TEAM_DOMAIN}/cdn-cgi/access/certs")

# 5 MB raw (the Worker's operator-chosen gate; see its comment for the rationale) * 4/3 base64 + JSON envelope, rounded up.
# Defends the disk; the Worker's gate is tighter and fails first in the
# normal path.
MAX_BODY = 8 * 1024 * 1024

_jwks_client = None


def jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        # PyJWKClient caches keys and refetches on unknown kid (bounded).
        _jwks_client = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwks_client


def log_event(record: dict) -> None:
    record["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def verify_assertion(token: str) -> dict:
    """Return validated claims or raise. Alg pinned to RS256: an assertion
    claiming any other algorithm is refused unexamined -- alg-confusion is
    the classic JWT break and the pin is the whole defense."""
    signing_key = jwks_client().get_signing_key_from_jwt(token)
    claims = pyjwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=AUD,
        options={"require": ["exp", "iat", "aud"]},
    )
    if PIN_CN and claims.get("common_name") != PIN_CN:
        raise pyjwt.InvalidTokenError("token common_name not the pinned one")
    return claims


class IngestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "amail-ingest-receiver/0.1"

    def _reply(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self, code: int, why: str, extra: dict = None) -> None:
        log_event({"outcome": "refused", "code": code, "why": why,
                   "client": "%s:%d" % self.client_address[:2],
                   **(extra or {})})
        self._reply(code, {"accepted": False, "why": why})

    def do_POST(self):
        if self.path != "/inbound":
            return self._refuse(404, "no such endpoint")

        # ---- The hard condition: a valid assertion, or nothing else runs --
        token = self.headers.get("Cf-Access-Jwt-Assertion")
        if not token:
            return self._refuse(403, "no Access assertion presented")
        # Specific types, per the coding standards' Error Visibility Stance:
        # a broad catch here would make a BUG in this verification code
        # indistinguishable from a forged token -- both would 403 as
        # "assertion rejected", and the instrument stops discriminating.
        # InvalidTokenError covers every verdict PyJWT can reach about the
        # token itself; PyJWKClientError + OSError cover the JWKS fetch
        # failing, which is OUR outage, not their forgery -- distinct log
        # detail, same refusal (fail closed either way). Anything else
        # propagates: ThreadingHTTPServer surfaces it as a 500 + traceback,
        # which is the correct loudness for an unanticipated failure.
        try:
            claims = verify_assertion(token)
        except pyjwt.InvalidTokenError as exc:
            return self._refuse(403, "assertion rejected",
                                {"detail": str(exc)[:200]})
        except (pyjwt.PyJWKClientError, OSError) as exc:
            return self._refuse(403, "assertion unverifiable (JWKS fetch failed)",
                                {"detail": str(exc)[:200]})

        # ---- Size gate before reading the stream ---------------------------
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            return self._refuse(413, f"content-length {length} outside (0, {MAX_BODY}]",
                                {"common_name": claims.get("common_name")})

        # ---- Payload: parse, integrity-check, spool ------------------------
        try:
            payload = json.loads(self.rfile.read(length))
            raw_b64 = payload["raw_b64"]
            claimed_sha = payload["raw_sha256"]
            schema = payload["schema"]
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError) as exc:
            return self._refuse(400, "body is not an amail.inbound payload",
                                {"detail": type(exc).__name__,
                                 "common_name": claims.get("common_name")})
        if schema != "amail.inbound/v1":
            return self._refuse(400, f"unknown schema {schema!r}",
                                {"common_name": claims.get("common_name")})

        import base64
        import binascii
        try:
            raw = base64.b64decode(raw_b64, validate=True)
        except (binascii.Error, TypeError, ValueError) as exc:
            return self._refuse(400, "raw_b64 does not decode",
                                {"detail": type(exc).__name__,
                                 "common_name": claims.get("common_name")})
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha != claimed_sha:
            # Tampered or corrupted in flight; never spool it as mail.
            return self._refuse(400, "sha256 mismatch",
                                {"claimed": claimed_sha, "actual": actual_sha,
                                 "common_name": claims.get("common_name")})

        # Dir 2770, files 0640: the receiver is the spool's sole AUTHOR of
        # entries; the broker's dedicated uid reads them by group AND removes
        # them at terminal disposition -- consuming a spool requires directory
        # write, which the first live run proved by failing exactly there
        # (handoff completed, unlink refused, entry honestly in-flight).
        # Group-write does mean the broker COULD author an entry; the boundary
        # that matters -- agents cannot touch the spool -- holds either way,
        # since no agent uid is in the broker's group.
        SPOOL.mkdir(parents=True, exist_ok=True, mode=0o2770)

        # Dedupe (see the design record): a lost response makes the sending MTA
        # retry the same mail -- ordinary at-least-once behaviour. The hash
        # is already in the envelope, so recognise the retry and answer
        # SUCCESS: a refusal here would make the MTA retry forever, which is
        # the opposite of what "we already have it" means.
        for prior in SPOOL.glob(f"*_{actual_sha[:16]}.eml"):
            if hashlib.sha256(prior.read_bytes()).hexdigest() == actual_sha:
                log_event({"outcome": "duplicate", "sha256": actual_sha,
                           "spool": prior.name,
                           "common_name": claims.get("common_name")})
                return self._reply(200, {"accepted": True,
                                         "raw_sha256": actual_sha,
                                         "duplicate": True})

        stamp = time.strftime("%Y%m%dT%H%M%S")
        base = SPOOL / f"{stamp}_{actual_sha[:16]}"
        base.with_suffix(".eml").write_bytes(raw)
        meta = {
            "received_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "raw_sha256": actual_sha,
            "raw_size": len(raw),
            "auth": {"common_name": claims.get("common_name"),
                     "aud": claims.get("aud"), "iat": claims.get("iat")},
            # The Worker's observations, still explicitly untrusted; the
            # broker is the authorization layer, not this receiver.
            "observed": payload.get("observed", {}),
            "posted_at": payload.get("posted_at"),
        }
        base.with_suffix(".json").write_text(json.dumps(meta, indent=1))
        for p in (base.with_suffix(".eml"), base.with_suffix(".json")):
            p.chmod(0o640)

        log_event({"outcome": "accepted", "sha256": actual_sha,
                   "size": len(raw), "common_name": claims.get("common_name"),
                   "spool": base.name})
        self._reply(200, {"accepted": True, "raw_sha256": actual_sha})

    # Anything that is not POST /inbound is refused loudly.
    def do_GET(self):
        self._refuse(405, "POST only")
    do_PUT = do_DELETE = do_PATCH = do_GET

    def log_message(self, fmt, *args):
        pass


def main() -> int:
    if not TEAM_DOMAIN or not AUD:
        print("refusing to start: INGEST_TEAM_DOMAIN and INGEST_AUD are "
              "required -- a receiver that cannot verify must not listen",
              file=sys.stderr)
        return 1
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(BIND, IngestHandler)
    print(f"amail ingest receiver on http://{BIND[0]}:{BIND[1]} "
          f"(aud {AUD[:12]}..., jwks {JWKS_URL}, "
          f"pin_cn {PIN_CN or 'none'})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
