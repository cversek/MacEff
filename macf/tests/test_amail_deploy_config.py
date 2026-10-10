"""MIS-0002-R76 (config_MUST_accept_old_hypervisor_value).

The mail system's deploy configuration keeps accepting ``hypervisor``, the old
name for what MIS-0002 calls the primal daemon, as a host tier's supervision.
A rename of the value must not strand a deployment that still writes the old one.
"""
import macf.amail.deploy_config as dc
from macf.amail.deploy_config import AddressingConfig

from test_amail_host_tier import addressing  # the real file's shape, shared with that suite


def test_hypervisor_value_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(dc, "CONTAINER_MARKER", tmp_path / "no-dockerenv")
    cfg = AddressingConfig.model_validate(addressing("host", "hypervisor"))
    assert cfg.supervision == "hypervisor"
