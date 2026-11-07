"""The system declaration schema both system-daemon prototypes import (MIS-0007 draft, #855)."""
import copy

import pytest
from pydantic import ValidationError

from macf.sd.declaration import SystemDeclaration, start_order, unit_environment


def _unit(name, **over):
    unit = {"name": name, "account": name.replace("-", "_"), "relationship": "parent",
            "command": ["/usr/bin/true"], "restart": "always", "liveness_interval_s": 30,
            "memory_limit_mb": 256, "platform": {"kind": "linux", "stop": "subreaper"}}
    unit.update(over)
    return unit


def _launchd(name, label=None, **over):
    return _unit(name, platform={"kind": "launchd", "domain": "system", "label": label or f"maceff.{name}"},
                 **over)


def _watched(name, domain="gui", **over):
    unit = {"name": name, "account": name.replace("-", "_"), "relationship": "watch", "restart": "never",
            "liveness_interval_s": 30,
            "platform": {"kind": "launchd", "domain": domain, "label": f"maceff_pd.{name}"}}
    unit.update(over)
    return unit


CONTAINER = {
    "system": "proto-container",
    "time_zone": "America/New_York",
    "stop_timeout_s": 60,
    "units": [
        _unit("seat-a-pd", account="seat_a", after=["broker"]),
        _unit("broker", account="mail_broker", environment={"PATH": "/usr/bin"}),
        _unit("seat-b-pd", account="seat_b", after=["broker"]),
    ],
}


def _load(doc):
    return SystemDeclaration.model_validate(doc)


def test_a_container_declaration_loads_and_starts_dependencies_first():
    decl = _load(CONTAINER)
    assert start_order(decl) == ["broker", "seat-a-pd", "seat-b-pd"]
    assert decl.units[1].exit_codes.success == [0] and decl.units[1].exit_codes.no_restart == [78]


@pytest.mark.parametrize("domain", ["gui", "user"])
def test_a_job_in_a_login_domain_is_watched_and_never_parented(domain):
    watched = _watched("operator-pd", domain=domain)
    assert _load({**CONTAINER, "units": [watched]}).units[0].relationship == "watch"
    parented = dict(watched, relationship="parent", command=["/usr/bin/true"], restart="always",
                    memory_limit_mb=256)
    with pytest.raises(ValidationError, match=f"login's {domain} domain belongs to that login"):
        _load({**CONTAINER, "units": [parented]})


def test_an_unknown_key_is_refused_wherever_it_is_written():
    for where in ("top", "unit", "platform"):
        doc = copy.deepcopy(CONTAINER)
        target = {"top": doc, "unit": doc["units"][0], "platform": doc["units"][0]["platform"]}[where]
        target["memry_limit"] = 1
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            _load(doc)


@pytest.mark.parametrize("name", ["TZ", "MACEFF_SD_UNIT"])
def test_a_unit_cannot_declare_what_the_system_daemon_sets(name):
    doc = copy.deepcopy(CONTAINER)
    doc["units"][1]["environment"][name] = "x"
    with pytest.raises(ValidationError, match="system daemon's to set"):
        _load(doc)


def test_the_environment_is_the_declared_one_plus_tz_and_the_marker():
    decl = _load(CONTAINER)
    broker = decl.units[1]
    assert unit_environment(decl, broker) == {"PATH": "/usr/bin", "TZ": "America/New_York",
                                              "MACEFF_SD_UNIT": "broker"}


def test_a_parented_unit_needs_a_command():
    with pytest.raises(ValidationError, match="needs the command its parent starts"):
        _load({**CONTAINER, "units": [_unit("broker", command=[])]})


def test_start_order_refuses_an_unknown_unit_and_a_cycle():
    with pytest.raises(ValidationError, match="unknown unit"):
        _load({**CONTAINER, "units": [_unit("broker", after=["nobody"])]})
    cyclic = [_unit("a-pd", after=["b-pd"]), _unit("b-pd", after=["a-pd"])]
    with pytest.raises(ValidationError, match="cycle: a-pd -> b-pd -> a-pd"):
        _load({**CONTAINER, "units": cyclic})


def test_unit_names_are_unique():
    with pytest.raises(ValidationError, match="unique: broker"):
        _load({**CONTAINER, "units": [_unit("broker"), _unit("broker")]})


def test_the_time_zone_must_be_a_real_zone():
    with pytest.raises(ValidationError, match="not an IANA zone name"):
        _load({**CONTAINER, "time_zone": "Eastern"})


@pytest.mark.parametrize("field,value", [("account", "Seat A"), ("groups", ["ok", "Not OK"])])
def test_accounts_and_groups_must_be_legitimate_names(field, value):
    with pytest.raises(ValidationError):
        _load({**CONTAINER, "units": [_unit("broker", **{field: value})]})


def test_a_parented_unit_never_runs_as_root():
    with pytest.raises(ValidationError, match="never runs as root"):
        _load({**CONTAINER, "units": [_unit("broker", account="root")]})


def test_a_linux_watch_is_refused_until_something_names_what_to_watch():
    watched = _watched("host-pd", platform={"kind": "linux", "stop": "subreaper"})
    with pytest.raises(ValidationError, match="nothing names what to watch on Linux"):
        _load({**CONTAINER, "units": [watched]})


def test_a_watched_unit_cannot_ask_to_be_restarted():
    with pytest.raises(ValidationError, match="isn't the system daemon's to restart"):
        _load({**CONTAINER, "units": [_watched("operator-pd", restart="always")]})


@pytest.mark.parametrize("key,value", [("command", ["/usr/bin/true"]), ("environment", {"PATH": "/usr/bin"}),
                                       ("groups", ["staff"]), ("memory_limit_mb", 256), ("stop_grace_s", 10),
                                       ("exit_codes", {"success": [0]})])
def test_a_watched_unit_refuses_what_only_a_parent_uses(key, value):
    with pytest.raises(ValidationError, match=f"would ignore {key}"):
        _load({**CONTAINER, "units": [_watched("operator-pd", **{key: value})]})


def test_a_parented_unit_needs_a_memory_limit():
    unit = _unit("broker")
    del unit["memory_limit_mb"]
    with pytest.raises(ValidationError, match="needs memory_limit_mb"):
        _load({**CONTAINER, "units": [unit]})


def test_one_declaration_holds_one_platform():
    with pytest.raises(ValidationError, match="share one platform; found launchd, linux"):
        _load({**CONTAINER, "units": [_unit("broker"), _launchd("seat-pd")]})


def test_two_units_cannot_claim_one_label_in_the_system_domain():
    taken = _launchd("seat-pd", label="maceff.broker")
    with pytest.raises(ValidationError, match="broker and seat-pd both claim the label maceff.broker in the "
                                              "system domain"):
        _load({**CONTAINER, "units": [_launchd("broker"), taken]})


def test_a_login_domain_label_is_counted_per_account():
    first = _watched("login-a", platform={"kind": "launchd", "domain": "user", "label": "maceff_pd"})
    assert _load({**CONTAINER, "units": [first, dict(first, name="login-b", account="login_b")]})
    with pytest.raises(ValidationError, match="both claim the label maceff_pd in login_a's user domain"):
        _load({**CONTAINER, "units": [first, dict(first, name="login-a-again")]})


def test_sixteen_groups_load_and_seventeen_are_refused():
    sixteen = [f"g{i}" for i in range(16)]
    assert len(_load({**CONTAINER, "units": [_unit("broker", groups=sixteen)]}).units[0].groups) == 16
    with pytest.raises(ValidationError, match="at most 16"):
        _load({**CONTAINER, "units": [_unit("broker", groups=sixteen + ["g16"])]})


def test_the_longest_stop_chain_must_fit_inside_the_stop_timeout():
    chain = [_unit("broker", stop_grace_s=10), _unit("seat-pd", stop_grace_s=30, after=["broker"]),
             _unit("other", stop_grace_s=5)]
    assert _load({**CONTAINER, "stop_timeout_s": 41, "units": chain})
    with pytest.raises(ValidationError, match="40 s along seat-pd -> broker"):
        _load({**CONTAINER, "stop_timeout_s": 40, "units": chain})
    # A default grace (10 s) under docker's default stop timeout (10 s) has no margin.
    with pytest.raises(ValidationError, match="doesn't fit inside stop_timeout_s 10"):
        _load({**CONTAINER, "stop_timeout_s": 10, "units": [_unit("broker")]})


def test_a_watched_unit_orders_the_stop_chain_but_adds_no_grace():
    # The seat stops before the broker, through the login job between them, which the
    # system daemon never stops: 30 s + 10 s, not the 50 s a default grace would add.
    chain = [_launchd("broker", stop_grace_s=10), _watched("login-pd", after=["broker"]),
             _launchd("seat-pd", stop_grace_s=30, after=["login-pd"])]
    assert _load({**CONTAINER, "stop_timeout_s": 41, "units": chain})
    with pytest.raises(ValidationError, match="40 s along seat-pd -> login-pd -> broker"):
        _load({**CONTAINER, "stop_timeout_s": 40, "units": chain})
