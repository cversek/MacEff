"""The pinned trust bundle (MIS-0004 R34): what the broker's outbound connections trust.

The operator declares a bundle of CA certificates and its SHA-256. :func:`pinned_context` returns a
TLS context that trusts that bundle and nothing else. The system trust store is never loaded, so a
chain any public CA would vouch for is refused unless the operator pinned that CA. A missing or empty
bundle, or one whose digest has drifted from the declaration, is refused before any connection is
made, with the reason.

Rotation is a declared procedure: add the new bundle beside the old, switch the declared path and
digest together, then remove the old. While the two disagree the context refuses (fails closed), and
the refusal names both digests.
"""
import hashlib
import ssl
from pathlib import Path
from typing import Union


class PinnedTrustError(RuntimeError):
    """The pinned bundle can't be used: missing, empty, unreadable, or not the one declared."""


def bundle_digest(path: Union[str, Path]) -> str:
    """The SHA-256, lowercase hex, of the bundle file's bytes, as the operator declares it."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pinned_context(path: Union[str, Path], declared_sha256: str) -> ssl.SSLContext:
    """A client TLS context trusting only the bundle at *path*, after checking its declared digest."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except OSError as e:
        raise PinnedTrustError(f"the pinned trust bundle {p} can't be read: {e}") from e
    if not data.strip():
        raise PinnedTrustError(f"the pinned trust bundle {p} is empty")
    actual = hashlib.sha256(data).hexdigest()
    if actual != (declared_sha256 or "").strip().lower():
        raise PinnedTrustError(
            f"the pinned trust bundle {p} has digest {actual}, but {declared_sha256!r} is declared; "
            f"refusing to connect until the declaration and the bundle agree (rotation: switch the "
            f"declared path and digest together)")
    # Built from scratch, not from create_default_context(): nothing here may load the system store.
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = True
    try:
        ctx.load_verify_locations(cadata=data.decode("ascii"))
    except (ssl.SSLError, UnicodeDecodeError, ValueError) as e:
        raise PinnedTrustError(f"the pinned trust bundle {p} holds no usable CA certificate: {e}") from e
    if not ctx.get_ca_certs():
        raise PinnedTrustError(f"the pinned trust bundle {p} holds no CA certificate")
    return ctx
