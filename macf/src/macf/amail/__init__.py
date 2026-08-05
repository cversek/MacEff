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
"""
from .models import Message, new_id
from .contacts import ContactBook, ContactListError
from .audit import AuditLog
from .broker import Broker, BrokerConfig, DeliveryError, serve
from .client import submit, BrokerUnavailable
from . import store

__all__ = [
    "Message", "new_id",
    "ContactBook", "ContactListError",
    "AuditLog",
    "Broker", "BrokerConfig", "DeliveryError", "serve",
    "submit", "BrokerUnavailable",
    "store",
]
