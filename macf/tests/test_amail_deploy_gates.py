"""Two startup refusals, each demonstrated in BOTH polarities.

A refusal nobody has watched fire is a painted bulb: the code path exists, the
message reads well, and nothing has ever established that it happens. These are
the two the deployment phase owes.
"""
from pathlib import Path

import pytest
from pydantic import ValidationError

from macf.amail import deploy_config as dc


class TestAStalePackageSaysSoInsteadOfRejectingKeys:
    """The failure being replaced is a MISDIAGNOSIS, not a missing check.

    A container editable-installs macf from a submodule. When the pin lags the
    config, every field the newer models added is unknown to the older models
    and `extra="forbid"` refuses it — correctly, while describing the wrong
    thing. The operator reads "unknown key" and edits a config that is fine.
    """

    def test_a_package_behind_the_config_refuses(self, tmp_path):
        with pytest.raises(dc.StalePackageError) as e:
            dc.assert_package_current("99.0.0", tmp_path / "broker.yaml")
        assert "THE CONFIG IS NOT THE PROBLEM" in str(e.value)
        assert dc.running_macf() in str(e.value)

    def test_a_current_package_is_accepted(self, tmp_path):
        dc.assert_package_current("0.1.0", tmp_path / "broker.yaml")

    def test_the_same_version_is_accepted(self, tmp_path):
        dc.assert_package_current(dc.running_macf(), tmp_path / "broker.yaml")

    def test_no_declaration_means_no_check(self, tmp_path):
        """Optional on purpose: a deployment that never declares a minimum must
        keep starting, or adding the gate breaks every existing config."""
        dc.assert_package_current(None, tmp_path / "broker.yaml")

    def test_a_dev_suffix_is_not_treated_as_older(self, tmp_path):
        """`0.5.1.dev0` claims to be 0.5.1's line. Refusing a development
        checkout for not being a final release would fire the check on exactly
        the deployments that need it least."""
        assert dc._version_tuple("0.5.1.dev0") == dc._version_tuple("0.5.1")

    def test_the_error_names_the_pin_and_not_the_file(self, tmp_path):
        """The remedy is not in the file the reader is looking at, so the
        message has to send them somewhere else explicitly."""
        with pytest.raises(dc.StalePackageError) as e:
            dc.assert_package_current("99.0.0", tmp_path / "broker.yaml")
        assert "Advance the checkout" in str(e.value)

    def test_it_is_a_ConfigError_so_existing_handlers_catch_it(self):
        """Entry points already catch ConfigError and exit 2. Subclassing means
        the new refusal cannot fall through as an unhandled traceback."""
        assert issubclass(dc.StalePackageError, dc.ConfigError)


class TestUnknownKeysOfferTheStaleHypothesis:
    def _bad(self, extra_key, tmp_path):
        try:
            dc.BrokerDeployConfig.model_validate(
                {"addressing_path": str(tmp_path / "a.yaml"), extra_key: 1})
        except ValidationError as e:
            return dc.explain_validation_error("cfg.yaml", e)
        raise AssertionError("expected a validation error")

    def test_an_unknown_key_mentions_the_running_package(self, tmp_path):
        msg = self._bad("definitely_not_a_field", tmp_path)
        assert "definitely_not_a_field" in msg
        assert "THE PACKAGE IS BEHIND THE CONFIG" in msg

    def test_it_offers_two_causes_rather_than_asserting_one(self, tmp_path):
        """A misspelling produces the identical signature. A diagnostic that
        confidently names the wrong cause is worse than one naming two."""
        msg = self._bad("typoed_key", tmp_path)
        assert "misspelled" in msg and "advance the checkout" in msg

    def test_an_ordinary_validation_error_gets_no_stale_hint(self):
        """Only unknown KEYS carry this signature. A MISSING required field
        does not, and suggesting a stale package there sends the reader
        nowhere — the config really is what needs editing."""
        try:
            dc.BrokerDeployConfig.model_validate({})
        except ValidationError as e:
            msg = dc.explain_validation_error("cfg.yaml", e)
        assert "THE PACKAGE IS BEHIND THE CONFIG" not in msg


class TestAnAgentWithNoAccountRefusesTheStartup:
    """C3's missing-uid arm. The uid table IS the authentication table, so a
    declared account that does not exist must not be guessed at.

    Exercised on `AgentAddressing`, which is where a deployment names its
    agents — the broker config points at the addressing file rather than
    carrying the roster itself.
    """

    def test_a_missing_account_refuses(self):
        with pytest.raises(ValidationError) as e:
            dc.AgentAddressing.model_validate(
                {"account": "definitely-no-such-account-here"})
        assert "does not exist on this system" in str(e.value)
        assert "refusing to guess its uid" in str(e.value)

    def test_an_existing_account_is_accepted(self):
        """THE PAIRED ACCEPTANCE. A refusal with no matching acceptance proves
        only that the path can raise, not that it discriminates."""
        import getpass, os
        a = dc.AgentAddressing.model_validate({"account": getpass.getuser()})
        assert a.uid == os.getuid()
        assert a.home == Path(os.path.expanduser("~"))

    def test_a_declared_uid_that_disagrees_with_the_account_refuses(self):
        """Neither value is trusted over the other: the mismatch itself is the
        fault, because the declared value would become an auth table entry."""
        import getpass
        with pytest.raises(ValidationError) as e:
            dc.AgentAddressing.model_validate(
                {"account": getpass.getuser(), "uid": 999999})
        assert "refused rather than resolved" in str(e.value)

    def test_a_declared_home_that_disagrees_refuses(self):
        import getpass
        with pytest.raises(ValidationError) as e:
            dc.AgentAddressing.model_validate(
                {"account": getpass.getuser(), "home": "/nowhere/at/all"})
        assert "has home" in str(e.value)

    def test_neither_account_nor_uid_refuses(self):
        """Silence is not a default. Guessing an identity is the one thing an
        authentication table may never do."""
        with pytest.raises(ValidationError) as e:
            dc.AgentAddressing.model_validate({})
        assert "declare `account`" in str(e.value)
