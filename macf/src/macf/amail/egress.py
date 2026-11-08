"""The macOS egress rule (MIS-0004 R33): only the broker's account and declared people send mail.

pf's ``user`` keyword matches the owner of the socket, so the rule follows the account, not the
network the host happens to be on. It is an allow-list, because a deny-list fails open for any
account whose rule is missing: one ``pass`` per allowed account on the mail ports, then a ``block``
for everyone else. The rules load into an anchor under ``com.apple/``, which macOS's own pf.conf
already evaluates, so no system file is edited.

Rendering needs no root. Loading, and reading back what pf enforces, do: those are the operator's
steps, and :func:`probe` says "unknown" whenever it can't read pf rather than guess.
"""
import re
import time
from typing import Callable, Dict, Iterable, Sequence

ANCHOR = "com.apple/maceff.amail.egress"
#: SMTP, SMTPS, submission, IMAPS: the ports mail leaves and is fetched on.
MAIL_PORTS: Sequence[int] = (25, 465, 587, 993)
_ACCOUNT = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,31}")


def _account(name: str) -> str:
    if not isinstance(name, str) or not _ACCOUNT.fullmatch(name):
        raise ValueError(f"{name!r} is not an account name pf can match")
    return name


def render_pf_anchor(broker_account: str, human_accounts: Iterable[str],
                     ports: Sequence[int] = MAIL_PORTS) -> str:
    """The anchor's rules: a pass per allowed account, then a block for every other socket owner."""
    allowed = [_account(broker_account)] + sorted({_account(h) for h in human_accounts} - {broker_account})
    port_set = "{ " + " ".join(str(int(p)) for p in ports) + " }"
    lines = [f"# MacEff amail egress (MIS-0004 R33), anchor {ANCHOR}: only these accounts open the mail ports"]
    lines += [f"pass out quick proto tcp to any port {port_set} user {a}" for a in allowed]
    lines.append(f"block return out quick proto tcp to any port {port_set}")
    return "\n".join(lines) + "\n"


def install_steps(rules_file: str) -> str:
    """The operator's root steps, as one block: load the anchor, enable pf, show what it holds."""
    return (f"sudo pfctl -a {ANCHOR} -f {rules_file} && sudo pfctl -E && "
            f"sudo pfctl -a {ANCHOR} -s rules")


def uninstall_steps() -> str:
    """The operator's root step that removes it again, in one go."""
    return f"sudo pfctl -a {ANCHOR} -F all"


def probe(run: Callable[[Sequence[str]], str], now: Callable[[], float] = time.time) -> Dict[str, object]:
    """Whether the rule is in force: "enforced" (pf enabled and the anchor holds its block),
    "not enforced", or "unknown" when pf can't be read (it needs root). Always stamped."""
    at = now()
    try:
        info = run(["pfctl", "-s", "info"])
        rules = run(["pfctl", "-a", ANCHOR, "-s", "rules"])
    except Exception as e:  # noqa: BLE001 - any failure to read pf is "unknown", never a guess
        return {"state": "unknown", "why": f"pf could not be read: {e}", "at": at}
    enabled = "Status: Enabled" in (info or "")
    has_block = "block return out quick proto tcp" in (rules or "")
    state = "enforced" if enabled and has_block else "not enforced"
    why = "pf is enabled and the anchor holds its block" if state == "enforced" else (
        "pf is disabled" if not enabled else f"the anchor {ANCHOR} holds no block rule")
    return {"state": state, "why": why, "at": at}
