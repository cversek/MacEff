"""Gmail access for one agent through a local OAuth grant. No MCP, no send verb.

Shape follows ``macf_tools amail``: the CLI handlers live in ``cli.py`` and this
module holds the library (grant, cache, HTTP). Three files in the agent home
carry state and every one is mode 600 and carries the exfiltration sentinel that
the opsec hook, the amail pre-flight and ``agent backup`` all refuse:

- ``.maceff/gmail_client.json``  the OAuth client from the Google console
- ``.maceff/gmail_grant.json``   refresh token, profile, scopes, cache id
- ``.maceff/gmail_cache_key``    the AES-GCM key for the cache

Mail itself is the USER's data, not the agent's, and never touches the agent
tree. It is cached only under the OS temp root in a directory named by a UUID
that the grant records, encrypted at rest with the key above. Key and data live
in different trees; either alone is useless. ``revoke`` and ``cache purge``
overwrite and remove the cache.

The boundary is soft and this docstring says so: the ``draft`` profile carries
``gmail.compose``, which Google lets send. Nothing here sends. The controls are
the absence of the verb, the audit line per call, and a permission deny rule.
Only the last of those is a boundary in the framework's sense, because it is the
only one the agent cannot lift; read the capability_boundaries policy on mailbox
access before assuming the command surface is what constrains this.

    macf_tools policy read capability_boundaries --section 5.2
"""
import base64
import hashlib
import json
import os
import secrets
import stat
import sys
import tempfile
import time
import uuid
import webbrowser
from email.message import EmailMessage
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error, parse, request

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://gmail.googleapis.com/gmail/v1/users/me"

SCOPE_READ = "https://www.googleapis.com/auth/gmail.readonly"
SCOPE_COMPOSE = "https://www.googleapis.com/auth/gmail.compose"
PROFILES = {
    "read": [SCOPE_READ],
    "draft": [SCOPE_READ, SCOPE_COMPOSE],
    "compose_only": [SCOPE_COMPOSE],
}

#: Planted in every credential-class file so leakage guards recognise it by grep.
SENTINEL = "MACEFF-SECRET-SENTINEL:gmail_grant:must-not-leave-host"
REDACT_KEYS = ("access_token", "refresh_token", "id_token")
CACHE_DIRNAME = "macf_gmail"


class GmailError(Exception):
    """A refusal or failure the CLI reports as ❌ and returns 1 for."""


# ── paths ──────────────────────────────────────────────────────────────


def _agent_home() -> Path:
    from .utils.paths import find_agent_home
    return Path(find_agent_home())


def _maceff_dir() -> Path:
    d = _agent_home() / ".maceff"
    d.mkdir(parents=True, exist_ok=True)
    return d


def client_path() -> Path:
    return _maceff_dir() / "gmail_client.json"


def grant_path() -> Path:
    return _maceff_dir() / "gmail_grant.json"


def key_path() -> Path:
    return _maceff_dir() / "gmail_cache_key"


def audit_path() -> Path:
    return _maceff_dir() / "gmail_audit.jsonl"


def cache_root_for(cache_id: str) -> Path:
    """The cache lives under the OS temp root, never under the agent home."""
    return Path(tempfile.gettempdir()) / CACHE_DIRNAME / cache_id


def _write_private(path: Path, payload: Dict[str, Any]) -> None:
    """Write JSON with mode 600 from the first byte (no chmod race)."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    os.chmod(path, 0o600)


def _redact(d: Any) -> Any:
    if not isinstance(d, dict):
        return str(d)[:200]
    return {k: ("<redacted>" if k in REDACT_KEYS and v else v) for k, v in d.items()}


# ── audit (fields per amail policy 3.3: ts, direction, identity, decision, reason) ──


def audit(verb: str, direction: str, decision: str, detail: Dict[str, Any],
          reason: Optional[str] = None) -> None:
    g = load_grant(required=False)
    line = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "verb": verb,
        "direction": direction,
        "identity": (g or {}).get("profile"),
        "decision": decision,
        "detail": detail,
    }
    if reason:
        line["reason"] = reason[:500]
    with open(audit_path(), "a") as f:
        f.write(json.dumps(line) + "\n")
    os.chmod(audit_path(), 0o600)


# ── http ───────────────────────────────────────────────────────────────


def _post_form(url: str, data: Dict[str, str]) -> Tuple[int, Any]:
    body = parse.urlencode(data).encode()
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    return _do(req)


def api(method: str, path: str, token: str, payload: Optional[Dict[str, Any]] = None,
        params: Optional[List[Tuple[str, str]]] = None) -> Tuple[int, Any]:
    url = API + path
    if params:
        url += ("&" if "?" in url else "?") + parse.urlencode(params)
    data = json.dumps(payload).encode() if payload is not None else None
    req = request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    return _do(req)


def _do(req: request.Request) -> Tuple[int, Any]:
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            status = resp.status
    except error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        status = e.code
    except (error.URLError, OSError) as e:
        raise GmailError(f"Google unreachable: {e}") from e
    try:
        return status, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return status, raw


def _api_error(status: int, resp: Any) -> str:
    if isinstance(resp, dict) and "error" in resp:
        e = resp["error"]
        if isinstance(e, dict):
            return f"{status}: {e.get('message', e)}"
    return f"{status}: {str(resp)[:200]}"


# ── client + grant ─────────────────────────────────────────────────────


def load_client() -> Dict[str, str]:
    p = client_path()
    if not p.exists():
        raise GmailError(f"no OAuth client at {p}; download the Desktop-app client JSON "
                         "from the Google console and place it there (mode 600)")
    try:
        d = json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise GmailError(f"cannot read {p}: {e}") from e
    d = d.get("installed") or d.get("web") or d
    for k in ("client_id", "client_secret"):
        if k not in d:
            raise GmailError(f"{p} lacks {k}")
    return d


def load_grant(required: bool = True) -> Optional[Dict[str, Any]]:
    p = grant_path()
    if not p.exists():
        if required:
            raise GmailError(f"no Gmail grant for this agent home ({p}); run: macf_tools gmail auth")
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise GmailError(f"cannot read {p}: {e}") from e


def access_token() -> str:
    """Return a live access token, refreshing through the grant if needed."""
    g = load_grant()
    now = time.time()
    if g.get("access_token") and g.get("access_expires_at", 0) - 60 > now:
        return g["access_token"]
    c = load_client()
    status, resp = _post_form(TOKEN_URL, {
        "client_id": c["client_id"], "client_secret": c["client_secret"],
        "refresh_token": g["refresh_token"], "grant_type": "refresh_token",
    })
    if status != 200 or not isinstance(resp, dict) or "access_token" not in resp:
        audit("refresh", "auth", "refused", {"status": status, "resp": _redact(resp)}, "refresh failed")
        raise GmailError(f"token refresh failed ({_api_error(status, resp)})")
    g["access_token"] = resp["access_token"]
    g["access_expires_at"] = now + int(resp.get("expires_in", 3600))
    g["last_refresh_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    _write_private(grant_path(), g)
    audit("refresh", "auth", "allowed", {"expires_in": resp.get("expires_in")})
    return g["access_token"]


# ── cache: UUID-named, under the OS temp root, AES-GCM at rest ──────────


def _aesgcm():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        # Refuse rather than degrade: a plaintext cache would be the exact thing
        # this module exists to prevent.
        raise GmailError("cryptography is not installed (pip install 'macf[amail]'); "
                         "refusing to cache mail in plaintext") from e
    return AESGCM


def _load_key() -> bytes:
    p = key_path()
    if p.exists():
        try:
            d = json.loads(p.read_text())
            return base64.b64decode(d["key"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as e:
            raise GmailError(f"cannot read cache key {p}: {e}") from e
    key = secrets.token_bytes(32)
    _write_private(p, {"_sentinel": SENTINEL, "key": base64.b64encode(key).decode(),
                       "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    return key


def cache_root() -> Path:
    g = load_grant()
    cid = g.get("cache_id")
    if not cid:
        # A grant minted before the cache existed: give it one now rather than
        # demanding a fresh consent for a bookkeeping field.
        cid = uuid.uuid4().hex
        g["cache_id"] = cid
        _write_private(grant_path(), g)
    root = cache_root_for(cid)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    return root


def _seal(obj: Any, cache_id: str) -> bytes:
    key = _load_key()
    nonce = secrets.token_bytes(12)
    return nonce + _aesgcm()(key).encrypt(nonce, json.dumps(obj).encode(), cache_id.encode())


def _open(blob: bytes, cache_id: str) -> Any:
    key = _load_key()
    try:
        return json.loads(_aesgcm()(key).decrypt(blob[:12], blob[12:], cache_id.encode()))
    except Exception as e:  # InvalidTag and friends: the cache is unreadable, say so
        raise GmailError(f"cache object unreadable (wrong key or tampered): {type(e).__name__}") from e


def _obj_path(root: Path, name: str) -> Path:
    return root / (hashlib.sha256(name.encode()).hexdigest() + ".enc")


def cache_put(name: str, obj: Any) -> None:
    root = cache_root()
    cid = load_grant()["cache_id"]
    p = _obj_path(root, name)
    fd = os.open(str(p), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(_seal(obj, cid))


def cache_get(name: str) -> Optional[Any]:
    root = cache_root()
    p = _obj_path(root, name)
    if not p.exists():
        return None
    return _open(p.read_bytes(), load_grant()["cache_id"])


def _index() -> Dict[str, Any]:
    return cache_get("_index") or {}


def _index_put(idx: Dict[str, Any]) -> None:
    cache_put("_index", idx)


def cache_status() -> Dict[str, Any]:
    g = load_grant(required=False)
    if not g or not g.get("cache_id"):
        return {"present": False}
    root = cache_root_for(g["cache_id"])
    if not root.exists():
        return {"present": False, "cache_id": g["cache_id"]}
    files = [f for f in root.iterdir() if f.is_file()]
    idx = _index()
    newest = max((v.get("fetched_at", "") for v in idx.values()), default=None)
    return {"present": True, "cache_id": g["cache_id"], "objects": len(files),
            "bytes": sum(f.stat().st_size for f in files), "threads": len(idx),
            "newest_fetch": newest, "key_present": key_path().exists()}


def cache_purge() -> Dict[str, Any]:
    """Overwrite every cached object, then remove it and the directory."""
    g = load_grant(required=False)
    if not g or not g.get("cache_id"):
        return {"purged": 0}
    root = cache_root_for(g["cache_id"])
    n = 0
    if root.exists():
        for f in root.iterdir():
            if f.is_file():
                size = f.stat().st_size
                with open(f, "r+b") as fh:
                    fh.write(b"\0" * size)
                    fh.flush()
                    os.fsync(fh.fileno())
                f.unlink()
                n += 1
        root.rmdir()
    audit("cache_purge", "cache", "allowed", {"objects": n})
    return {"purged": n}


# ── loopback receiver ──────────────────────────────────────────────────


class _Catch(BaseHTTPRequestHandler):
    result: Dict[str, str] = {}

    def do_GET(self):  # noqa: N802
        q = parse.parse_qs(parse.urlsplit(self.path).query)
        _Catch.result = {k: v[0] for k, v in q.items()}
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><p>macf_tools gmail: authorization received. You can close this tab.</p></body></html>")

    def log_message(self, *a):  # keep the consent flow quiet on the terminal
        pass


# ── credential lifecycle ───────────────────────────────────────────────


def authorize(profile: str, open_browser: bool = True, capture: Optional[Path] = None,
              url_sink=None) -> Dict[str, Any]:
    """Run the loopback consent flow; write grant + cache key; return a receipt."""
    t0 = time.time()
    scopes = PROFILES[profile]
    c = load_client()
    srv = HTTPServer(("127.0.0.1", 0), _Catch)
    redirect = f"http://127.0.0.1:{srv.server_address[1]}/"
    state = secrets.token_urlsafe(24)
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = AUTH_URL + "?" + parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": " ".join(scopes), "access_type": "offline", "prompt": "consent",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    if url_sink:
        url_sink(url)
    if open_browser:
        webbrowser.open(url)
    srv.timeout = 300
    srv.handle_request()
    srv.server_close()
    r = _Catch.result
    if r.get("state") != state:
        audit("auth", "auth", "refused", {"profile": profile}, "state mismatch")
        raise GmailError("consent returned a mismatched state; aborting")
    if "code" not in r:
        audit("auth", "auth", "refused", {"profile": profile, "resp": r}, "no code")
        raise GmailError(f"consent did not return a code: {r}")
    status, resp = _post_form(TOKEN_URL, {
        "code": r["code"], "client_id": c["client_id"], "client_secret": c["client_secret"],
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier,
    })
    elapsed = round(time.time() - t0, 1)
    if status != 200 or not isinstance(resp, dict) or "refresh_token" not in resp:
        audit("auth", "auth", "refused", {"profile": profile, "status": status, "resp": _redact(resp)}, "exchange failed")
        raise GmailError(f"token exchange failed ({_api_error(status, resp)})")
    if capture:
        _write_private(capture, {"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "profile": profile,
                                 "status": status, "response_keys": sorted(resp.keys()), "response": _redact(resp)})
    prior = load_grant(required=False)
    cache_id = uuid.uuid4().hex
    grant = {
        "_sentinel": SENTINEL, "profile": profile,
        "scopes": resp.get("scope", " ".join(scopes)).split(),
        "client_id": c["client_id"], "refresh_token": resp["refresh_token"],
        "access_token": resp.get("access_token"),
        "access_expires_at": time.time() + int(resp.get("expires_in", 3600)),
        "issued_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "refresh_token_expires_in": resp.get("refresh_token_expires_in"),
        "cache_id": cache_id,
    }
    if prior and prior.get("cache_id"):
        # A new grant gets a fresh cache; the old one is purged, never inherited.
        cache_purge()
    _write_private(grant_path(), grant)
    _load_key()
    cache_root()
    audit("auth", "auth", "allowed", {"profile": profile, "elapsed_s": elapsed,
                                      "refresh_token_expires_in": resp.get("refresh_token_expires_in")})
    return {"profile": profile, "scopes": grant["scopes"], "elapsed_s": elapsed,
            "refresh_token_expires_in": resp.get("refresh_token_expires_in"),
            "token_response_keys": sorted(resp.keys()), "grant": str(grant_path()),
            "capture": str(capture) if capture else None}


def revoke() -> Dict[str, Any]:
    """Revoke at Google first, then unlink the grant, then purge the cache."""
    g = load_grant()
    status, resp = _post_form(REVOKE_URL, {"token": g["refresh_token"]})
    if status != 200:
        audit("revoke", "auth", "refused", {"status": status, "resp": _redact(resp)}, "revoke failed; grant kept")
        raise GmailError(f"revoke failed ({_api_error(status, resp)}); grant file kept so nothing is orphaned")
    purged = cache_purge()
    grant_path().unlink()
    audit("revoke", "auth", "allowed", {"purged": purged.get("purged", 0)})
    return {"revoked": True, "grant_removed": str(grant_path()), "cache_purged": purged.get("purged", 0)}


def status() -> Dict[str, Any]:
    g = load_grant(required=False)
    info: Dict[str, Any] = {"grant": str(grant_path()), "present": bool(g)}
    if not g:
        info["cache"] = cache_status()
        return info
    mode = stat.S_IMODE(os.stat(grant_path()).st_mode)
    info.update({
        "mode": oct(mode), "sentinel": g.get("_sentinel") == SENTINEL,
        "profile": g.get("profile"), "scopes": g.get("scopes", []),
        "issued_at": g.get("issued_at"), "refresh_token_expires_in": g.get("refresh_token_expires_in"),
        "can_send_at_google": SCOPE_COMPOSE in g.get("scopes", []),
        "cache": cache_status(),
    })
    return info


def check() -> Dict[str, Any]:
    """Force a refresh and a profile call; the exit code of `status --check` is the health."""
    g = load_grant()
    g["access_expires_at"] = 0
    _write_private(grant_path(), g)
    tok = access_token()
    st, me = api("GET", "/profile", tok)
    return {"refresh": "ok", "profile_status": st,
            "email": me.get("emailAddress") if isinstance(me, dict) else None}


# ── mail: list, sync, read, draft ──────────────────────────────────────


def _hdr(msg: Dict[str, Any], name: str) -> str:
    for h in msg.get("payload", {}).get("headers", []):
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _body_text(part: Dict[str, Any]) -> str:
    if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(part["body"]["data"] + "==").decode(errors="replace")
    return "\n".join(x for x in (_body_text(p) for p in part.get("parts", []) or []) if x)


def _attachments(part: Dict[str, Any], out: List[Dict[str, Any]]) -> None:
    if part.get("filename") and part.get("body", {}).get("attachmentId"):
        out.append({"filename": part["filename"], "mime": part.get("mimeType"),
                    "size": part["body"].get("size"), "attachment_id": part["body"]["attachmentId"]})
    for p in part.get("parts", []) or []:
        _attachments(p, out)


def list_threads(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    """One summary row per thread, headers only. Nothing is cached by list."""
    tok = access_token()
    st, res = api("GET", "/threads", tok, params=[("q", query), ("maxResults", str(limit))])
    if st != 200:
        audit("list", "read", "refused", {"q": query, "status": st}, _api_error(st, res))
        raise GmailError(f"list refused ({_api_error(st, res)})")
    rows = []
    for t in res.get("threads", []):
        st2, th = api("GET", f"/threads/{t['id']}", tok, params=[
            ("format", "metadata"), ("metadataHeaders", "From"), ("metadataHeaders", "Subject"),
            ("metadataHeaders", "Date")])
        msgs = th.get("messages", []) if st2 == 200 else []
        last = msgs[-1] if msgs else {}
        rows.append({"thread_id": t["id"], "messages": len(msgs), "date": _hdr(last, "Date"),
                     "from": _hdr(last, "From"), "subject": _hdr(last, "Subject"),
                     "snippet": t.get("snippet", "")})
    audit("list", "read", "allowed", {"q": query, "threads": len(rows)})
    return rows


def fetch_thread(thread_id: str) -> Dict[str, Any]:
    """Fetch a full thread, store it encrypted in the cache, return the record."""
    tok = access_token()
    st, th = api("GET", f"/threads/{thread_id}", tok, params=[("format", "full")])
    if st != 200:
        audit("fetch", "read", "refused", {"id": thread_id, "status": st}, _api_error(st, th))
        raise GmailError(f"thread fetch refused ({_api_error(st, th)})")
    msgs = []
    for m in th.get("messages", []):
        atts: List[Dict[str, Any]] = []
        _attachments(m.get("payload", {}), atts)
        msgs.append({"message_id": m.get("id"), "date": _hdr(m, "Date"), "from": _hdr(m, "From"),
                     "to": _hdr(m, "To"), "cc": _hdr(m, "Cc"), "subject": _hdr(m, "Subject"),
                     "rfc_message_id": _hdr(m, "Message-ID"), "body": _body_text(m.get("payload", {})).strip(),
                     "attachments": atts})
    rec = {"thread_id": thread_id, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "messages": msgs}
    cache_put(thread_id, rec)
    idx = _index()
    last = msgs[-1] if msgs else {}
    idx[thread_id] = {"fetched_at": rec["fetched_at"], "messages": len(msgs), "date": last.get("date", ""),
                      "from": last.get("from", ""), "subject": last.get("subject", "")}
    _index_put(idx)
    audit("fetch", "read", "allowed", {"id": thread_id, "messages": len(msgs)})
    return rec


def read_thread(thread_id: str) -> Tuple[Dict[str, Any], bool]:
    """Return (record, from_cache)."""
    rec = cache_get(thread_id)
    if rec is not None:
        audit("read", "read", "allowed", {"id": thread_id, "source": "cache"})
        return rec, True
    return fetch_thread(thread_id), False


def sync(query: str, limit: int = 50) -> Dict[str, Any]:
    rows = list_threads(query, limit)
    idx = _index()
    new = 0
    for r in rows:
        if r["thread_id"] not in idx:
            fetch_thread(r["thread_id"])
            new += 1
    audit("sync", "read", "allowed", {"q": query, "matched": len(rows), "fetched": new})
    return {"matched": len(rows), "fetched": new, "cached_threads": len(_index())}


def build_draft(to: List[str], subject: str, body: str, cc: Optional[List[str]] = None,
                attach: Optional[List[str]] = None, in_reply_to: Optional[str] = None,
                references: Optional[str] = None) -> EmailMessage:
    """Pure: assemble the MIME message. Attachments are read from named paths."""
    import mimetypes
    msg = EmailMessage()
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject or ""
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = references or in_reply_to
    msg.set_content(body or "")
    for path in attach or []:
        p = Path(path)
        if not p.is_file():
            raise GmailError(f"attachment not found: {p}")
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)
    return msg


def create_draft(to: List[str], subject: str, body: str, cc: Optional[List[str]] = None,
                 attach: Optional[List[str]] = None, reply_to: Optional[str] = None) -> Dict[str, Any]:
    tok = access_token()
    thread_id = None
    in_reply_to = references = None
    if reply_to:
        st, orig = api("GET", f"/messages/{reply_to}", tok, params=[
            ("format", "metadata"), ("metadataHeaders", "Message-ID"),
            ("metadataHeaders", "References"), ("metadataHeaders", "Subject")])
        if st != 200:
            raise GmailError(f"reply target not readable ({_api_error(st, orig)})")
        thread_id = orig.get("threadId")
        in_reply_to = _hdr(orig, "Message-ID") or None
        references = (_hdr(orig, "References") + " " + (in_reply_to or "")).strip() or None
        if not subject:
            s = _hdr(orig, "Subject")
            subject = s if s.lower().startswith("re:") else "Re: " + s
    msg = build_draft(to, subject, body, cc, attach, in_reply_to, references)
    payload: Dict[str, Any] = {"message": {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode()}}
    if thread_id:
        payload["message"]["threadId"] = thread_id
    st, d = api("POST", "/drafts", tok, payload=payload)
    if st != 200:
        audit("draft", "write", "refused", {"to": to, "status": st}, _api_error(st, d))
        raise GmailError(f"draft refused ({_api_error(st, d)})")
    out = {"draft_id": d.get("id"), "thread_id": d.get("message", {}).get("threadId"),
           "to": to, "subject": subject, "attachments": len(attach or [])}
    audit("draft", "write", "allowed", out)
    return out


# ── query ergonomics: shortcut flags compiled to Gmail query syntax ────────


def _date_term(value: str, recent_op: str, absolute_op: str) -> str:
    """'7d' -> newer_than:7d; '2026-09-01' -> after:2026/09/01. Pure."""
    v = value.strip()
    if len(v) >= 2 and v[:-1].isdigit() and v[-1] in "dmy":
        return f"{recent_op}:{v}"
    if len(v) == 10 and v[4] == "-" and v[7] == "-":
        return f"{absolute_op}:{v.replace('-', '/')}"
    raise GmailError(f"date must be a duration like 7d/2m/1y or a date like 2026-09-01, not {value!r}")


def compile_query(text: str = "", *, from_: Optional[str] = None, to: Optional[str] = None,
                  subject: Optional[str] = None, since: Optional[str] = None,
                  until: Optional[str] = None, label: Optional[str] = None,
                  has_attachment: bool = False, unread: bool = False) -> str:
    """Compile shortcut flags plus free text into one Gmail query. Pure.

    Order is fixed so the same inputs always yield the same string, which is
    what lets a test assert equality with a hand-written query.
    """
    terms: List[str] = []
    if from_:
        terms.append(f"from:{from_}")
    if to:
        terms.append(f"to:{to}")
    if subject:
        terms.append(f"subject:{subject}" if " " not in subject else f'subject:"{subject}"')
    if since:
        terms.append(_date_term(since, "newer_than", "after"))
    if until:
        terms.append(_date_term(until, "older_than", "before"))
    if label:
        terms.append(f"label:{label}")
    if has_attachment:
        terms.append("has:attachment")
    if unread:
        terms.append("is:unread")
    if text and text.strip():
        terms.append(text.strip())
    return " ".join(terms)


# ── saved queries: names only, never results ──────────────────────────────


def queries_path() -> Path:
    return _maceff_dir() / "gmail_queries.json"


def saved_queries() -> Dict[str, str]:
    p = queries_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise GmailError(f"cannot read saved queries {p}: {e}") from e


def save_query(name: str, query: str) -> None:
    if not name or any(c in name for c in " /\\"):
        raise GmailError(f"query name must be a single token, not {name!r}")
    q = saved_queries()
    q[name] = query
    _write_private(queries_path(), q)


def delete_query(name: str) -> bool:
    q = saved_queries()
    if name not in q:
        return False
    del q[name]
    _write_private(queries_path(), q)
    return True


def resolve_query(text: str, saved: Optional[str], **flags) -> str:
    """Saved name -> its query; then flags and free text compile on top."""
    base = ""
    if saved:
        q = saved_queries()
        if saved not in q:
            raise GmailError(f"no saved query named {saved!r}; see: macf_tools gmail query list")
        base = q[saved]
    compiled = compile_query(text or "", **flags)
    return " ".join(x for x in (base, compiled) if x.strip())


# ── attachments: listed from the thread record, fetched only where named ──


def list_attachments(thread_id: str) -> List[Dict[str, Any]]:
    rec, _ = read_thread(thread_id)
    out = []
    for m in rec["messages"]:
        for a in m.get("attachments", []):
            out.append({**a, "message_id": m["message_id"], "date": m.get("date", ""),
                        "from": m.get("from", "")})
    return out


def _refuse_destination(out: Path) -> None:
    """The operator's mail goes where the operator says, never into our trees."""
    resolved = out.resolve()
    home = _agent_home().resolve()
    if home == resolved or home in resolved.parents:
        raise GmailError(f"refusing to write mail content under the agent home ({home}); name another path")
    g = load_grant(required=False)
    if g and g.get("cache_id"):
        root = cache_root_for(g["cache_id"]).resolve()
        if root == resolved or root in resolved.parents:
            raise GmailError("refusing to write plaintext into the encrypted cache; name another path")


def get_attachment(thread_id: str, attachment_id: str, out: Path) -> Dict[str, Any]:
    """Download one attachment to a caller-named path. Receipt carries sha256."""
    _refuse_destination(out)
    owner = next((a for a in list_attachments(thread_id) if a["attachment_id"] == attachment_id), None)
    if owner is None:
        raise GmailError(f"no attachment {attachment_id[:16]}... in thread {thread_id}")
    tok = access_token()
    st, res = api("GET", f"/messages/{owner['message_id']}/attachments/{attachment_id}", tok)
    if st != 200 or not isinstance(res, dict) or "data" not in res:
        audit("attachment_get", "read", "refused", {"thread": thread_id, "status": st}, _api_error(st, res))
        raise GmailError(f"attachment fetch refused ({_api_error(st, res)})")
    data = base64.urlsafe_b64decode(res["data"] + "==")
    if out.is_dir():
        out = out / owner["filename"]
    out.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(out), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    receipt = {"path": str(out), "filename": owner["filename"], "bytes": len(data),
               "sha256": hashlib.sha256(data).hexdigest(), "mime": owner.get("mime")}
    audit("attachment_get", "read", "allowed", {"thread": thread_id, "bytes": len(data)})
    return receipt
