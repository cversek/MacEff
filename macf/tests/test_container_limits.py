"""Declared container limits against the limits in force (MIS-0002-R61).

The shapes are a live deployment's, Oct 10: its limits live in an override file, so the
base compose file alone declares none.
"""
import json

import pytest

from macf.platform import container_limits as cl

GIB = 1024 ** 3
MERGED = {"mem_limit": "68719476736", "memswap_limit": "68719476736", "cpus": 24,
          "deploy": {"resources": {"reservations": {"devices": [{"driver": "nvidia"}]}}}}
INSPECT = {"HostConfig": {"Memory": 64 * GIB, "MemorySwap": 64 * GIB, "NanoCpus": 24_000_000_000},
           "Config": {"Labels": {cl.CONFIG_FILES_LABEL: "/d/docker-compose.yml,/d/docker-compose.override.yml",
                                 cl.SERVICE_LABEL: "manny-maceff"}}}


def test_limits_checked_after_recreate():
    """The merged declaration and the container agree: nothing to report."""
    assert cl.compare(cl.declared(MERGED), cl.in_force(INSPECT)) == []


def test_a_changed_limit_is_named_with_both_values():
    recreated = {"HostConfig": {"Memory": 32 * GIB, "MemorySwap": 64 * GIB, "NanoCpus": 24_000_000_000}}
    assert cl.compare(cl.declared(MERGED), cl.in_force(recreated)) == [
        "memory: declared 64 GiB, in force 32 GiB"]


def test_the_check_reads_every_config_file_the_container_was_made_from():
    """Reading the base file alone would report this container as unlimited."""
    calls = []

    def run(argv):
        calls.append(argv)
        if argv[:2] == ["docker", "inspect"]:
            return json.dumps([INSPECT])
        return json.dumps({"services": {"manny-maceff": MERGED}})
    assert cl.check_container("manny-maceff", run=run) == []
    assert calls[1][:6] == ["docker", "compose", "-f", "/d/docker-compose.yml", "-f", "/d/docker-compose.override.yml"]
    base_only = cl.declared({"deploy": {"resources": {"reservations": {}}}})
    assert cl.compare(base_only, cl.in_force(INSPECT)) == [
        "memory: declared none, in force 64 GiB", "CPUs: declared none, in force 24 CPUs"]


def test_no_limit_on_either_side_agrees():
    assert cl.compare(cl.declared({}), cl.in_force({"HostConfig": {"Memory": 0, "MemorySwap": 0, "NanoCpus": 0}})) == []


def test_docker_s_default_swap_is_not_a_difference():
    """Only mem_limit declared: docker sets memory plus swap to twice it by itself."""
    want = cl.declared({"mem_limit": "8g"})
    have = cl.in_force({"HostConfig": {"Memory": 8 * GIB, "MemorySwap": 16 * GIB}})
    assert cl.compare(want, have) == []


def test_the_deploy_form_is_read_too():
    want = cl.declared({"deploy": {"resources": {"limits": {"memory": "512m", "cpus": "1.5"}}}})
    assert want == cl.Limits(memory=512 * 1024 ** 2, memory_swap=0, nano_cpus=1_500_000_000)


@pytest.mark.parametrize("value,expected", [("64g", 64 * GIB), ("512m", 512 * 1024 ** 2), ("1.5G", int(1.5 * GIB)),
                                            (68719476736, 64 * GIB), ("68719476736", 64 * GIB), (None, 0), ("1024kb", 1024 ** 2)])
def test_memory_values_parse_as_compose_writes_them(value, expected):
    assert cl.parse_bytes(value) == expected


def test_a_container_compose_did_not_make_is_refused():
    def run(argv):
        return json.dumps([{"HostConfig": {}, "Config": {"Labels": {}}}])
    with pytest.raises(ValueError):
        cl.check_container("hand-made", run=run)
