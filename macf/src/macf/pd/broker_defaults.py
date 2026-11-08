"""Every daemon's own broker, when its declaration says nothing more (persistent_layer 11.4).

The event stream is the daemon's own MQTT broker for every daemon (MIS-0002 R150 to R156). A
declaration may name its broker in full (``broker``): its port, the certificate authority and the
certificates, as an association does, whose members hold certificates the operator's authority
signed. When it names none, the daemon runs a broker of its own with nothing for anyone to do:

- **Its own certificate authority**, made by the daemon at first start, in its own home, with no
  root step. Its key never leaves the home (mode 0600, in a 0700 directory). It signs one
  certificate, the daemon's own, which serves as the broker's server certificate and as the
  daemon's client certificate. Nothing else trusts this authority, so only the daemon can connect.
- **A port derived from the card**, so two daemons on one host don't pick the same one by habit.
  A clash is still refused at install and start, naming whose (``broker_link.port_clash``), and
  the declaration then names a port.
- **A broker unit**, when the declaration declares none: the wrapper that runs mosquitto and beats
  only while it listens (``macf.pd.broker_unit``).
"""
import datetime
import hashlib
import os
import sys
from pathlib import Path
from typing import Dict, List

from macf.pd.broker import LOOPBACK, cert_name

#: The range the derived ports fall in: above the well-known and common development ports.
PORT_BASE, PORT_SPAN = 20000, 10000
#: How long the daemon's own certificates last, and how early before that they are made anew.
VALID_DAYS, RENEW_DAYS = 3650, 30
#: Where in the daemon's home its own authority and certificate live.
PKI_DIR = Path(".maceff") / "pd" / "broker"
#: Where mosquitto is installed: Linux packages, Homebrew on Apple silicon and on Intel.
BROKER_PATH = "/usr/sbin:/usr/bin:/sbin:/bin:/opt/homebrew/sbin:/opt/homebrew/bin:/usr/local/sbin:/usr/local/bin"


def default_port(card: str) -> int:
    """The port a daemon's own broker takes when its declaration names none."""
    digest = hashlib.sha256(cert_name(card).encode()).hexdigest()
    return PORT_BASE + int(digest[:8], 16) % PORT_SPAN


def pki_paths(home: Path) -> Dict[str, Path]:
    d = Path(home) / PKI_DIR
    return {"dir": d, "ca_cert": d / "authority.crt", "ca_key": d / "authority.key",
            "cert": d / "own.crt", "key": d / "own.key"}


def _fresh(cert_path: Path, now: datetime.datetime) -> bool:
    from cryptography import x509
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    except (OSError, ValueError):
        return False
    return cert.not_valid_after_utc - now > datetime.timedelta(days=RENEW_DAYS)


def _write_private(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.chmod(path, 0o600)


def ensure_own_pki(home: Path, card: str, now: datetime.datetime = None) -> Dict[str, Path]:
    """The daemon's own authority and certificate, made or renewed as needed; their paths."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    import ipaddress

    now = now or datetime.datetime.now(datetime.timezone.utc)
    p = pki_paths(home)
    p["dir"].mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(p["dir"], 0o700)
    if _fresh(p["ca_cert"], now) and _fresh(p["cert"], now) and p["ca_key"].exists() and p["key"].exists():
        return p
    pem = serialization.PrivateFormat.PKCS8
    nopass = serialization.NoEncryption()
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"{cert_name(card)} broker authority")])
    until = now + datetime.timedelta(days=VALID_DAYS)
    ca_cert = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
               .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(until)
               .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
               .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False,
                                            key_encipherment=False, data_encipherment=False,
                                            key_agreement=False, key_cert_sign=True, crl_sign=True,
                                            encipher_only=False, decipher_only=False), critical=True)
               .sign(ca_key, hashes.SHA256()))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cert_name(card))]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(until)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(LOOPBACK)),
                                                        x509.DNSName("localhost")]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH,
                                                  ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(ca_key, hashes.SHA256()))
    _write_private(p["ca_key"], ca_key.private_bytes(serialization.Encoding.PEM, pem, nopass))
    _write_private(p["key"], key.private_bytes(serialization.Encoding.PEM, pem, nopass))
    _write_private(p["ca_cert"], ca_cert.public_bytes(serialization.Encoding.PEM))
    _write_private(p["cert"], cert.public_bytes(serialization.Encoding.PEM))
    return p


def default_section(home: Path, card: str):
    """The broker section a declaration that names none gets: its own authority and certificate."""
    from macf.pd.interface import BrokerSection
    p = ensure_own_pki(home, card)
    return BrokerSection(port=default_port(card), certificate_authority_file=str(p["ca_cert"]),
                         server_certificate_file=str(p["cert"]), server_key_file=str(p["key"]),
                         client_certificate_file=str(p["cert"]), client_key_file=str(p["key"]))


#: The modules every daemon's own broker needs, each with the distribution that provides it.
BROKER_MODULES = {"paho.mqtt.client": "paho-mqtt", "cryptography": "cryptography"}


def missing_dependencies(find=None) -> List[str]:
    """The distributions the broker needs that this interpreter can't import. An editable install
    made before they became core dependencies doesn't gain them when the checkout moves on."""
    import importlib.util
    find = find or importlib.util.find_spec
    missing = []
    for module, dist in BROKER_MODULES.items():
        try:
            found = find(module) is not None
        except ImportError:
            found = False
        if not found:
            missing.append(dist)
    return missing


def dependency_remedy(missing: List[str], executable: str = sys.executable) -> str:
    """Why the daemon can't start without *missing*, and the command that installs them into the
    interpreter it runs on."""
    import macf
    # An editable install runs from its checkout: the nearest directory above holding pyproject.toml.
    project = next((p for p in Path(macf.__file__).resolve().parents if (p / "pyproject.toml").exists()), None)
    install = (f"{executable} -m pip install -e {project}" if project is not None
               else f"{executable} -m pip install --upgrade macf")
    return (f"this daemon's interpreter ({executable}) lacks {', '.join(missing)}, which every daemon's "
            f"own broker needs (persistent_layer 11.4); an editable install doesn't gain new "
            f"dependencies when its checkout updates. Install them, then start again: {install}")


def with_own_broker(declaration, home: Path, card: str):
    """*declaration*, with the daemon's own broker where it names none, and the broker unit where
    it declares none. A declaration that names its broker in full keeps it as it is."""
    import pwd
    update = {}
    if declaration.broker is None:
        update["broker"] = default_section(home, card)
    if not any(u.name == "broker" for u in declaration.units):
        update["units"] = list(declaration.units) + [broker_unit(card, pwd.getpwuid(os.getuid()).pw_name)]
    return declaration.model_copy(update=update) if update else declaration


def broker_unit(card: str, account: str):
    """The broker unit a declaration that declares none gets: the wrapper, run as the daemon's own
    account, with the interpreter the daemon itself runs."""
    from macf.pd.interface import Unit
    return Unit(name="broker", kind="service",
                command=[sys.executable, "-m", "macf.pd.broker_unit", "{runtime_dir}/" + card + ".broker/mosquitto.conf"],
                account=account, restart="always", liveness_interval_s=60, memory_limit_mb=64,
                environment={"HOME": "{agent_home}", "MACEFF_AGENT_HOME_DIR": "{agent_home}", "PATH": BROKER_PATH})
