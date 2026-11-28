"""The egress rule (MIS-0004 R33): only the broker's account and declared people send mail.

On macOS a pf anchor (``render_pf_anchor``); on Linux an iptables chain (``render_iptables_rules``),
which a container's start step loads for both address families.

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
from typing import Callable, Dict, Iterable, List, Mapping, Sequence

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


def render_iptables_rules(allowed: Mapping[str, int],
                          ports: Sequence[int] = MAIL_PORTS) -> List[List[str]]:
    """The Linux chain's mail rules, as argument lists to follow ``-A <chain>``: an ACCEPT per
    allowed account on the mail ports, matched on the socket's owner, then a REJECT on the mail
    ports for every other owner. The same allow-list as the pf anchor, in the order iptables
    reads it. *allowed* maps each account name to its uid, resolved by the caller; nothing here
    needs root or reads the system.

    REJECT, not DROP: a refused account gets an immediate error, never a hang that reads as a
    network fault (and an effect probe reads it at once, MIS-0007-R22)."""
    if not allowed:
        raise ValueError("an allow-list with no accounts would refuse the broker too")
    for name, uid in allowed.items():
        _account(name)
        if isinstance(uid, bool) or not isinstance(uid, int) or uid < 0:
            raise ValueError(f"{name!r} has no usable uid ({uid!r})")
    port_spec = ",".join(str(int(p)) for p in ports)
    mail = ["-p", "tcp", "-m", "multiport", "--dports", port_spec]
    rules = [mail + ["-m", "owner", "--uid-owner", str(uid), "-j", "ACCEPT"]
             for _, uid in sorted(allowed.items(), key=lambda kv: kv[1])]
    # Plain REJECT, with no --reject-with: the same rule goes to iptables and ip6tables, and each
    # defaults to its own port-unreachable. icmp-port-unreachable is IPv4's alone, and ip6tables
    # refuses it, which would stop a container's start at the IPv6 table.
    rules.append(mail + ["-j", "REJECT"])
    return rules


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
