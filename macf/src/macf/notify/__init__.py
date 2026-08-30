"""Notification delivery -- telling an agent something while it is not asking.

Every other hook in this framework is REACTIVE: it runs because the agent did
something. This package is the first capability class that is not.

`macf_tools policy navigate notification_delivery`
"""
from .adapter import DeliveryResult, deliver, deliver_and_publish
from .liveness import ABSENT, ALIVE, STALE, UNREADABLE, Liveness
from .notice import Notice, amail_notice, daemon_notice

__all__ = [
    "DeliveryResult",
    "deliver",
    "deliver_and_publish",
    "Notice",
    "amail_notice",
    "daemon_notice",
    "Liveness",
    "ALIVE",
    "STALE",
    "ABSENT",
    "UNREADABLE",
]
