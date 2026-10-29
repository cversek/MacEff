"""A container's declared resource limits against the limits in force (MIS-0002-R61).

A recreate is where limits drift: a compose file edited and not applied, an override
file left out of the command that recreated the container, a ``docker update`` that
the files never learned of. After each recreate the persistent layer compares the two
(MIS-0002-R61 (layer_MUST_check_limits_after_recreate)).

**Declared** is the merged compose configuration of every file the container was
created from, which Docker records in the label
``com.docker.compose.project.config_files``. Reading one compose file alone is the
mistake this module exists to avoid: a deployment that keeps its limits in an override
file reads as unlimited. **In force** is ``docker inspect``'s HostConfig.

Three limits: memory, memory plus swap, and CPUs. Zero means "none" on both sides, so
an undeclared limit and an unset one agree.
"""
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

CONFIG_FILES_LABEL = "com.docker.compose.project.config_files"
SERVICE_LABEL = "com.docker.compose.service"

Runner = Callable[[List[str]], str]


@dataclass(frozen=True)
class Limits:
    memory: int = 0         # bytes; 0 = no limit
    memory_swap: int = 0    # bytes, memory plus swap; 0 = not set
    nano_cpus: int = 0      # CPUs x 1e9; 0 = no limit


_SUFFIX = {"b": 1, "k": 1024, "m": 1024 ** 2, "g": 1024 ** 3, "t": 1024 ** 4}


def parse_bytes(value) -> int:
    """A compose memory value as bytes: an integer, or a string such as '64g' or '512m'."""
    if value in (None, ""):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().lower().removesuffix("b") or "0"
    if text[-1] in _SUFFIX and text[:-1].replace(".", "", 1).isdigit():
        return int(float(text[:-1]) * _SUFFIX[text[-1]])
    return int(float(text))


def declared(service: Dict) -> Limits:
    """The limits a merged compose service declares, from either form: the service keys
    (``mem_limit``, ``memswap_limit``, ``cpus``) or ``deploy.resources.limits``. A value
    in the service keys wins, as docker compose applies it."""
    limits = ((service.get("deploy") or {}).get("resources") or {}).get("limits") or {}
    memory = parse_bytes(service.get("mem_limit")) or parse_bytes(limits.get("memory"))
    cpus = service.get("cpus") or limits.get("cpus") or 0
    return Limits(memory=memory, memory_swap=parse_bytes(service.get("memswap_limit")),
                  nano_cpus=int(round(float(cpus) * 1e9)))


def in_force(inspect: Dict) -> Limits:
    host = inspect.get("HostConfig") or {}
    return Limits(memory=int(host.get("Memory") or 0),
                  memory_swap=int(host.get("MemorySwap") or 0),
                  nano_cpus=int(host.get("NanoCpus") or 0))


def _show(field: str, value: int) -> str:
    if value == 0:
        return "none"
    if field == "nano_cpus":
        return f"{value / 1e9:g} CPUs"
    return f"{value / 1024 ** 3:g} GiB"


def compare(want: Limits, have: Limits) -> List[str]:
    """One line per limit that differs, naming both values; empty when they agree.

    Docker sets memory plus swap to twice the memory when only the memory is given, so
    an undeclared swap limit is not compared against that default."""
    lines = []
    for field, label in (("memory", "memory"), ("memory_swap", "memory plus swap"), ("nano_cpus", "CPUs")):
        a, b = getattr(want, field), getattr(have, field)
        if field == "memory_swap" and a == 0:
            continue
        if a != b:
            lines.append(f"{label}: declared {_show(field, a)}, in force {_show(field, b)}")
    return lines


def _run(argv: List[str]) -> str:
    return subprocess.run(argv, capture_output=True, text=True, check=True, timeout=60).stdout


def check_container(name: str, run: Runner = _run) -> List[str]:
    """Compare a running container with the compose files it was created from."""
    inspect = json.loads(run(["docker", "inspect", name]))[0]
    labels = (inspect.get("Config") or {}).get("Labels") or {}
    files = [f for f in (labels.get(CONFIG_FILES_LABEL) or "").split(",") if f]
    service = labels.get(SERVICE_LABEL)
    if not files or not service:
        raise ValueError(f"{name} was not created by docker compose: no config files label")
    argv = ["docker", "compose"]
    for f in files:
        argv += ["-f", f]
    config = json.loads(run(argv + ["config", "--format", "json"]))
    return compare(declared(config["services"][service]), in_force(inspect))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m macf.platform.container_limits",
                                     description="Compare a container's declared and in-force limits.")
    parser.add_argument("container")
    args = parser.parse_args(argv)
    try:
        lines = check_container(args.container)
    except (subprocess.SubprocessError, OSError, ValueError, KeyError, IndexError) as e:
        print(f"{args.container}: cannot compare limits: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    if lines:
        print(f"{args.container}: limits differ from its compose files:\n  " + "\n  ".join(lines))
        return 1
    print(f"{args.container}: limits in force match its compose files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
