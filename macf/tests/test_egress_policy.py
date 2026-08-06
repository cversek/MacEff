"""Tests for declarative egress policy: inheritance, refusal, and enforcement.

The property under test is unusual, so it is worth stating plainly. Egress policy
exists because **a restriction on what an agent may reach cannot be enforced by the
component the agent is supposed to reach.** An allowlist held by a mail broker is
not defeated by a flaw in the broker; it is defeated by the agent opening its own
socket and never consulting it. Enforcement therefore has to live somewhere the
agent cannot edit, keyed on an identity it cannot forge.

That shapes what these tests must check, and it is not primarily "does the rule get
built correctly". The expensive failure is a deployment that *believes* it is
restricted and is not — so the tests below spend most of their effort on the
refusal paths: what happens when a policy is declared and cannot be installed.

Every invariant carries a negative control. A check never observed failing is not
a check, and this module exists because a security property held for a full cycle
while being false.

``docker/scripts/start.py`` is a container entrypoint rather than an importable
module, so it is loaded by path here, matching the sibling provisioning tests.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from macf.models.agent_spec import (
    AgentsConfig,
    AgentSpec,
    DefaultsConfig,
    EgressPolicy,
)

START_PY = Path(__file__).resolve().parents[2] / "docker" / "scripts" / "start.py"


@pytest.fixture(scope="module")
def start_module():
    """Load start.py by path; it lives outside the importable package."""
    spec = importlib.util.spec_from_file_location("maceff_start_egress", START_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config(agents: dict, defaults: dict | None = None) -> AgentsConfig:
    """Build an AgentsConfig from terse dicts, so tests read as configuration."""
    payload = {
        "agents": {
            name: {"username": name, "personality": "agents/x.md", **body}
            for name, body in agents.items()
        },
        "subagents": {},
    }
    if defaults is not None:
        payload["defaults"] = defaults
    return AgentsConfig(**payload)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class TestEgressSchema:
    def test_absent_everywhere_is_backward_compatible(self):
        """A config written before this field existed must not change meaning.

        This is the control that lets the feature ship: every pre-existing
        deployment validates unchanged and installs no rules.
        """
        spec = AgentSpec(username="pa_x", personality="agents/x.md")
        assert spec.egress is None

        defaults = DefaultsConfig()
        assert defaults.egress is None

    def test_empty_deny_list_is_a_valid_explicit_exemption(self):
        """Exemption must be expressible, because some account legitimately needs
        the ports — a broker, for one. What matters is that it is *written*."""
        assert EgressPolicy(deny_tcp_ports=[]).deny_tcp_ports == []

    @pytest.mark.parametrize(
        "ports, reason",
        [
            ([0], "port 0 names no destination"),
            ([65536], "above the 16-bit range"),
            ([-1], "negative"),
            ([25, 25], "duplicate would install two identical rules"),
            (["25"], "string would stringify into the rule and match nothing"),
            ([True], "bool is an int subclass and would silently become port 1"),
        ],
    )
    def test_unusable_port_values_are_refused(self, ports, reason):
        """A typo in a port number fails OPEN — the rule lands on a port nothing
        uses and the intended port stays reachable — so it must be caught at
        validation rather than discovered by an audit."""
        with pytest.raises(ValidationError):
            EgressPolicy(deny_tcp_ports=ports)

    def test_valid_mail_ports_accepted(self):
        policy = EgressPolicy(deny_tcp_ports=[25, 465, 587])
        assert policy.deny_tcp_ports == [25, 465, 587]


# ---------------------------------------------------------------------------
# Resolution: who ends up restricted
# ---------------------------------------------------------------------------


class TestEgressResolution:
    def test_agent_inherits_defaults(self, start_module):
        """The load-bearing case. An account added later, by someone who never
        read this policy, is covered because it did not have to opt in."""
        config = _config(
            {"a1": {}, "a2": {}},
            defaults={"egress": {"deny_tcp_ports": [25, 465, 587]}},
        )
        resolved = start_module.resolve_egress_policies(config)
        assert resolved == {"a1": [25, 465, 587], "a2": [25, 465, 587]}

    def test_agent_override_wins(self, start_module):
        config = _config(
            {"a1": {}, "a2": {"egress": {"deny_tcp_ports": [2525]}}},
            defaults={"egress": {"deny_tcp_ports": [25]}},
        )
        resolved = start_module.resolve_egress_policies(config)
        assert resolved == {"a1": [25], "a2": [2525]}

    def test_explicit_empty_override_exempts(self, start_module):
        """An exemption must actually exempt, or the escape hatch is a lie."""
        config = _config(
            {"a1": {}, "broker": {"egress": {"deny_tcp_ports": []}}},
            defaults={"egress": {"deny_tcp_ports": [25]}},
        )
        resolved = start_module.resolve_egress_policies(config)
        assert "broker" not in resolved
        assert resolved == {"a1": [25]}

    def test_no_declaration_resolves_to_nothing(self, start_module):
        """NEGATIVE CONTROL for the whole feature: with nothing declared, no agent
        is restricted, so apply_egress_policy has nothing to enforce and cannot
        fail a deployment that never asked for this."""
        config = _config({"a1": {}, "a2": {}})
        assert start_module.resolve_egress_policies(config) == {}

    def test_ports_are_deduplicated_and_ordered(self, start_module):
        """Rule text is compared by tests and read by humans; unstable ordering
        makes both harder and buys nothing."""
        config = _config({"a1": {"egress": {"deny_tcp_ports": [587, 25, 465]}}})
        assert start_module.resolve_egress_policies(config) == {"a1": [25, 465, 587]}


# ---------------------------------------------------------------------------
# Enforcement: the refusal paths
# ---------------------------------------------------------------------------


class TestEgressEnforcementRefuses:
    """The expensive direction is a deployment that believes it is restricted.

    Each test here plants one reason enforcement cannot happen and asserts that
    provisioning ABORTS. Logging a warning and continuing would produce exactly
    the failure this feature exists to prevent, one layer lower.
    """

    def test_missing_binary_aborts_provisioning(self, start_module, monkeypatch):
        monkeypatch.setattr(start_module.shutil, "which", lambda _name: None)
        config = _config({"a1": {}}, defaults={"egress": {"deny_tcp_ports": [25]}})

        with pytest.raises(RuntimeError, match="not installed in this image"):
            start_module.apply_egress_policy(config)

    def test_no_net_admin_aborts_provisioning(self, start_module, monkeypatch):
        """iptables present but unusable is the realistic failure: the package is
        in the image and the container was started without the capability."""
        monkeypatch.setattr(start_module.shutil, "which", lambda name: f"/sbin/{name}")
        monkeypatch.setattr(
            start_module.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(
                returncode=3, stdout="", stderr="Permission denied (you must be root)"
            ),
        )
        config = _config({"a1": {}}, defaults={"egress": {"deny_tcp_ports": [25]}})

        with pytest.raises(RuntimeError, match="NET_ADMIN"):
            start_module.apply_egress_policy(config)

    def test_unknown_account_aborts_provisioning(self, start_module, monkeypatch):
        monkeypatch.setattr(start_module.shutil, "which", lambda name: f"/sbin/{name}")
        monkeypatch.setattr(
            start_module.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )

        def _no_such_user(_name):
            raise KeyError(_name)

        monkeypatch.setattr(start_module.pwd, "getpwnam", _no_such_user)
        config = _config({"a1": {}}, defaults={"egress": {"deny_tcp_ports": [25]}})

        with pytest.raises(RuntimeError, match="does not exist"):
            start_module.apply_egress_policy(config)

    def test_privileged_uid_aborts_provisioning(self, start_module, monkeypatch):
        """An agent sharing an identity with the operator cannot be filtered
        without filtering the operator — the rule is not merely ineffective, it is
        inexpressible. Refusing is the only honest response."""
        monkeypatch.setattr(start_module.shutil, "which", lambda name: f"/sbin/{name}")
        monkeypatch.setattr(
            start_module.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )
        monkeypatch.setattr(
            start_module.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=0)
        )
        config = _config({"a1": {}}, defaults={"egress": {"deny_tcp_ports": [25]}})

        with pytest.raises(RuntimeError, match="system or privileged account"):
            start_module.apply_egress_policy(config)

    def test_shared_uid_aborts_provisioning(self, start_module, monkeypatch):
        """Two accounts on one uid means a rule matching one silently matches the
        other — in either direction, which is a surprise waiting in a log."""
        monkeypatch.setattr(start_module.shutil, "which", lambda name: f"/sbin/{name}")
        monkeypatch.setattr(
            start_module.subprocess,
            "run",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr=""),
        )
        monkeypatch.setattr(
            start_module.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=1002)
        )
        config = _config(
            {"a1": {}, "a2": {}}, defaults={"egress": {"deny_tcp_ports": [25]}}
        )

        with pytest.raises(RuntimeError, match="share uids"):
            start_module.apply_egress_policy(config)

    def test_rule_absent_after_install_aborts_provisioning(
        self, start_module, monkeypatch
    ):
        """THE MOST IMPORTANT REFUSAL. Every command succeeds, and the readback
        does not show the rule.

        This is the shape of the defect that motivated the whole phase: an
        operation that reports success while the thing it claims to have done is
        absent. Asking iptables what it installed is a second observation; trusting
        the exit code of the command that installed it is one variable twice.
        """
        monkeypatch.setattr(start_module.shutil, "which", lambda name: f"/sbin/{name}")
        monkeypatch.setattr(
            start_module.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=1002)
        )

        def _run(cmd, *a, **k):
            # Everything succeeds, but the chain reads back empty.
            if len(cmd) > 1 and cmd[1] == "-S":
                return SimpleNamespace(returncode=0, stdout="-N MACEFF_EGRESS\n", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(start_module.subprocess, "run", _run)
        config = _config({"a1": {}}, defaults={"egress": {"deny_tcp_ports": [25]}})

        with pytest.raises(RuntimeError, match="absent from"):
            start_module.apply_egress_policy(config)


class TestEgressEnforcementSucceeds:
    def test_nothing_declared_installs_nothing_and_does_not_raise(
        self, start_module, monkeypatch
    ):
        """POSITIVE CONTROL for the refusals above: with no policy declared, none
        of that machinery runs. Without this, every refusal test would still pass
        if apply_egress_policy raised unconditionally."""
        called = []
        monkeypatch.setattr(
            start_module.subprocess,
            "run",
            lambda *a, **k: called.append(a) or SimpleNamespace(returncode=0, stdout="", stderr=""),
        )
        start_module.apply_egress_policy(_config({"a1": {}}))
        assert called == [], "no declaration must mean no iptables invocation at all"

    def test_installs_owner_matched_rule_per_agent_on_both_families(
        self, start_module, monkeypatch
    ):
        """The rule must key on uid, cover the declared ports, and be installed for
        IPv4 AND IPv6.

        The address-family half is not pedantry: skipping ip6tables because a
        container has no IPv6 today is precisely how a probe certifies a host that
        a later network change reopens.
        """
        monkeypatch.setattr(start_module.shutil, "which", lambda name: f"/sbin/{name}")
        monkeypatch.setattr(
            start_module.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=1002)
        )

        invocations = []

        def _run(cmd, *a, **k):
            invocations.append(cmd)
            if len(cmd) > 1 and cmd[1] == "-S":
                return SimpleNamespace(
                    returncode=0,
                    stdout=(
                        "-N MACEFF_EGRESS\n"
                        "-A MACEFF_EGRESS -p tcp -m multiport --dports 25,465,587 "
                        "-m owner --uid-owner 1002 -j REJECT\n"
                    ),
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(start_module.subprocess, "run", _run)
        config = _config({"a1": {}}, defaults={"egress": {"deny_tcp_ports": [25, 465, 587]}})
        start_module.apply_egress_policy(config)

        appends = [c for c in invocations if len(c) > 1 and c[1] == "-A"]
        assert len(appends) == 2, "one append per address family"

        binaries = {c[0] for c in appends}
        assert binaries == {"iptables", "ip6tables"}

        for cmd in appends:
            assert "--uid-owner" in cmd and cmd[cmd.index("--uid-owner") + 1] == "1002"
            assert cmd[cmd.index("--dports") + 1] == "25,465,587"
            assert "REJECT" in cmd, "REJECT, not DROP: a hang is indistinguishable from a network fault"

    def test_rebuild_is_idempotent(self, start_module, monkeypatch):
        """Startup runs on every container boot. Flushing the chain before
        rebuilding is what keeps a restart from stacking duplicate rules."""
        monkeypatch.setattr(start_module.shutil, "which", lambda name: f"/sbin/{name}")
        monkeypatch.setattr(
            start_module.pwd, "getpwnam", lambda name: SimpleNamespace(pw_uid=1002)
        )
        invocations = []

        def _run(cmd, *a, **k):
            invocations.append(cmd)
            if len(cmd) > 1 and cmd[1] == "-S":
                return SimpleNamespace(
                    returncode=0,
                    stdout="-A MACEFF_EGRESS -m owner --uid-owner 1002 -j REJECT\n",
                    stderr="",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        monkeypatch.setattr(start_module.subprocess, "run", _run)
        config = _config({"a1": {}}, defaults={"egress": {"deny_tcp_ports": [25]}})
        start_module.apply_egress_policy(config)

        flushes = [c for c in invocations if len(c) > 1 and c[1] == "-F"]
        assert len(flushes) == 2, "chain flushed once per address family before rebuild"
