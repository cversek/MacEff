"""The AUTO_MODE permission level is a policy decision, not a literal.

It hardcoded `bypassPermissions` — correct when chosen, because that was the only
way to get unattended operation. The client has since grown `auto`, which is not
another static level but a maintained CLASSIFIER covering the risk classes an
agent framework meets: secret-store writes, irreversible local destruction,
permission grants, audit tampering.

Under `bypassPermissions` none of it evaluates. The maximal level does not merely
grant more — it switches the classifier off and puts nothing in its place.

Configurable rather than newly hardcoded, because swapping one literal for
another repeats the defect a platform release later: correct at first, then
silently wrong, with no way to audit which deployments took the decision.
"""
import pytest

from macf.config import resolve_setting


class TestPermissionModeIsResolved:
    KEY = "MACF_AUTO_MODE_PERMISSION_MODE"
    PATH = "modes.auto.permission_mode"

    def test_defaults_to_the_clients_native_auto(self, monkeypatch):
        monkeypatch.delenv(self.KEY, raising=False)
        value, _source = resolve_setting(self.KEY, self.PATH, "auto")
        assert value == "auto"

    def test_a_deployment_can_still_declare_bypass(self, monkeypatch):
        """The escape hatch must exist — but it has to be stated."""
        monkeypatch.setenv(self.KEY, "bypassPermissions")
        value, source = resolve_setting(self.KEY, self.PATH, "auto")
        assert value == "bypassPermissions"
        assert source != "default", "a declared choice must not report as the default"

    def test_the_source_is_reported_so_the_choice_is_auditable(self, monkeypatch):
        """A permission decision with no discoverable origin is the defect itself."""
        monkeypatch.delenv(self.KEY, raising=False)
        _value, source = resolve_setting(self.KEY, self.PATH, "auto")
        assert source, "resolve_setting must name where the value came from"


class TestNoRemainingHardcodedBypass:
    def test_auto_mode_does_not_hardcode_a_permission_level(self):
        """Read the source: the literal must not sit in the AUTO_MODE branch.

        Asserted against the file because the branch also writes real settings,
        and a test that ran it would be testing the operator's machine.
        """
        import inspect
        import macf.cli as cli
        src = inspect.getsource(cli.cmd_mode_set)
        assert 'set_permission_mode("bypassPermissions")' not in src, \
            "the AUTO_MODE permission level is configurable, not a literal"
