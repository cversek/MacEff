"""MIS-0004 R34: the broker's outbound connections verify servers against a pinned trust bundle.

A pinned bundle is a file of CA certificates the operator declares together with its SHA-256. The
context trusts that bundle and nothing else: the system store is never loaded, so a chain a public
CA would vouch for is refused unless the operator pinned that CA. A missing bundle or one whose
digest has drifted refuses before any connection is made. Rotation: add the new bundle beside the
old, switch the declared digest, remove the old; a mismatch during the switch fails closed.
"""
import datetime
import hashlib
import http.server
import ssl
import threading
import urllib.request

import pytest

pytest.importorskip("cryptography")
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
import ipaddress

from macf.amail.pinned_tls import PinnedTrustError, bundle_digest, pinned_context


def _ca(name):
    key = ec.generate_private_key(ec.SECP256R1())
    subj = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(subj).issuer_name(subj).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return key, cert


def _leaf(ca_key, ca_cert):
    key = ec.generate_private_key(ec.SECP256R1())
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "loopback")]))
            .issuer_name(ca_cert.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(ca_key, hashes.SHA256()))
    return key, cert


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


@pytest.fixture
def pki(tmp_path):
    ca_key, ca = _ca("pinned test CA")
    other_key, other = _ca("unpinned test CA")
    bundle = tmp_path / "bundle.pem"
    bundle.write_bytes(_pem(ca))
    return {"ca": (ca_key, ca), "other": (other_key, other), "bundle": bundle, "dir": tmp_path}


def _serve(pki, signer):
    key, cert = _leaf(*pki[signer])
    d = pki["dir"]
    (d / f"{signer}.crt").write_bytes(_pem(cert))
    (d / f"{signer}.key").write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                       serialization.PrivateFormat.PKCS8,
                                                       serialization.NoEncryption()))

    class Ok(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Ok)
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    sctx.load_cert_chain(d / f"{signer}.crt", d / f"{signer}.key")
    httpd.socket = sctx.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _get(ctx, httpd):
    url = f"https://127.0.0.1:{httpd.server_address[1]}/"
    with urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx)).open(url, timeout=5) as r:
        return r.read()


def test_pinned_bundle(pki):
    """An accepted chain under the pinned CA; a chain from any other CA refused; digest drift refused."""
    ctx = pinned_context(pki["bundle"], bundle_digest(pki["bundle"]))
    good = _serve(pki, "ca")
    try:
        assert _get(ctx, good) == b"ok"
    finally:
        good.shutdown()
    bad = _serve(pki, "other")
    try:
        with pytest.raises(Exception) as e:
            _get(ctx, bad)
        assert "CERTIFICATE_VERIFY_FAILED" in str(e.value)
    finally:
        bad.shutdown()
    with pytest.raises(PinnedTrustError, match="digest"):
        pinned_context(pki["bundle"], "0" * 64)


def test_the_system_trust_store_is_never_loaded(pki):
    """Only the pinned CA is trusted: a public CA's chain would be refused unless the operator pinned it."""
    ctx = pinned_context(pki["bundle"], bundle_digest(pki["bundle"]))
    subjects = [c["subject"] for c in ctx.get_ca_certs()]
    assert len(subjects) == 1 and "pinned test CA" in str(subjects[0])
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname


def test_a_missing_or_empty_bundle_refuses(pki):
    with pytest.raises(PinnedTrustError, match="bundle"):
        pinned_context(pki["dir"] / "absent.pem", "0" * 64)
    empty = pki["dir"] / "empty.pem"
    empty.write_bytes(b"")
    with pytest.raises(PinnedTrustError):
        pinned_context(empty, hashlib.sha256(b"").hexdigest())


def test_rotation_adds_beside_switches_digest_then_removes(pki):
    """During a switch the old digest no longer matches the new bundle: it fails closed until switched."""
    new = pki["dir"] / "bundle-next.pem"
    new.write_bytes(_pem(pki["other"][1]))
    old_digest = bundle_digest(pki["bundle"])
    with pytest.raises(PinnedTrustError, match="digest"):
        pinned_context(new, old_digest)
    ctx = pinned_context(new, bundle_digest(new))
    srv = _serve(pki, "other")
    try:
        assert _get(ctx, srv) == b"ok"
    finally:
        srv.shutdown()


def test_the_http_transport_uses_the_pinned_context(pki):
    from macf.amail.transport import HttpTransport
    ctx = pinned_context(pki["bundle"], bundle_digest(pki["bundle"]))
    t = HttpTransport("https://127.0.0.1:1/", tls_context=ctx)
    assert t.tls_context is ctx
    with pytest.raises(ValueError, match="opener"):
        HttpTransport("https://127.0.0.1:1/", tls_context=ctx, opener=lambda *a, **k: None)


def _deploy(tmp_path, **extra):
    import yaml
    from macf.amail.deploy_config import BrokerDeployConfig
    a = tmp_path / "addressing.yaml"
    a.write_text(yaml.safe_dump({"domain": "box.local",
                                 "agents": {"wren": {"home": str(tmp_path / "w"), "uid": 1002, "contacts": []}}}))
    return BrokerDeployConfig.model_validate({
        "addressing_path": str(a), "audit_path": str(tmp_path / "a.jsonl"),
        "inbound_quarantine": str(tmp_path / "q"), "inbound_handoff": str(tmp_path / "h"),
        "transport_endpoint": "https://127.0.0.1:1/", **extra}).to_broker_config()


def test_the_deployment_declares_the_bundle_and_its_digest(pki, tmp_path):
    from macf.amail.deploy_config import ConfigError
    cfg = _deploy(tmp_path, trust_bundle=str(pki["bundle"]), trust_bundle_sha256=bundle_digest(pki["bundle"]))
    assert cfg.transport.tls_context is not None
    with pytest.raises(ConfigError, match="digest"):
        _deploy(tmp_path, trust_bundle=str(pki["bundle"]), trust_bundle_sha256="0" * 64)
    with pytest.raises(ConfigError, match="together"):
        _deploy(tmp_path, trust_bundle=str(pki["bundle"]))


def test_an_undeclared_bundle_is_announced_until_enforcement(tmp_path, capsys):
    cfg = _deploy(tmp_path)
    assert cfg.transport.tls_context is None
    assert "no pinned trust bundle" in capsys.readouterr().err
