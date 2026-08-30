"""amail — agent mail.

Implements the protocol specified in the `amail` policy; read that first
(`macf_tools policy navigate amail`). The policy is the contract, this is one
implementation of it.

Module map:
    models    the message: locally-generated ids, thread id, parent pointer.
              No sequence numbers, deliberately.
    contacts  who an agent may send to. Rejects entries that encode a route.
    store     Maildir delivery, atomic via tmp/->new/ rename.
    audit     append-only decision log; refusals recorded as carefully as sends.
    broker    the enforcement point. Holds credentials; agents never do.
    client    agent-side submission. Powerless by design.
    crypto    per-correspondent authorship signing. v1.1.
    trust     what was actually proven about a message's origin. v1.1.

REQUIRES THE `amail` EXTRA, AND REFUSES TO LOAD WITHOUT IT.

Since v1.1 the protocol's inbound handling is built on verifying signatures and
classifying what that verification proved. Without a crypto backend none of that
can run — and the failure mode of running anyway is the one this framework keeps
finding: every message would classify as UNVERIFIED, the system would work, and
the authenticity guarantees would be absent rather than merely unused. An
operator would have a mail system whose trust labels were structurally incapable
of ever saying anything.

So the subsystem is ABSENT rather than DEGRADED. There is no configuration in
which amail runs without the machinery that makes its classifications mean
something, because a capability that is off is honest and a capability that is
present-but-hollow is not.

    pip install 'macf[amail]'
"""
try:
    import cryptography  # noqa: F401
except ImportError as _e:  # pragma: no cover - exercised by the extra's absence
    raise ImportError(
        "the amail subsystem requires the 'amail' extra, which is not installed.\n"
        "  pip install 'macf[amail]'\n"
        "amail refuses to load without it: since v1.1 inbound handling is built on "
        "signature verification, and running without a crypto backend would classify "
        "every message as unverified while appearing to work."
    ) from _e

# THIS LAYER ONLY. The package is landing in dependency order -- primitives
# first, then storage and policy, then the broker and client -- so that each
# change is small enough to review. Re-exports grow as each layer arrives;
# naming a module here before it exists would make the package unimportable,
# which is a worse failure than an incomplete surface.
from .models import Message, new_id
from .audit import AuditLog
from .trust import TrustClass
from .crypto import (

    SigningError, generate_keypair, load_private_key, public_key_line, sign, verify,
)
from .contacts import ContactBook, ContactListError
from . import models, audit, trust, crypto, ratelimit, transport
from .broker import Broker, BrokerConfig, DeliveryError, serve
from .client import submit, BrokerUnavailable
from .inbound import (
    InboundConfig, PushEligibilityError, SpoolError,
    process_spool, process_entry, reconcile,
)
from . import store, contacts, broker, client, deploy_config
from . import inbound, fetch, alerting, notices, criterion

__all__ = ["Message", "new_id", "AuditLog", "TrustClass",
           "ContactBook", "ContactListError",
           "models", "audit", "trust", "crypto", "ratelimit", "transport",
           "Broker", "BrokerConfig", "DeliveryError", "serve",
           "submit", "BrokerUnavailable",
           "InboundConfig", "PushEligibilityError", "SpoolError",
           "process_spool", "process_entry", "reconcile",
           "store", "contacts", "broker", "client", "deploy_config",
           "inbound", "fetch", "alerting", "notices", "criterion"]
