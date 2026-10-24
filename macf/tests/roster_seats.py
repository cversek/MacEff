"""Four Lumen-like seats in a fixture /home, shared by the roster, match and completion tests.

The shape of the Lumen container: one account per seat, ``pa_lumen`` for the first and
``pa_lumenN`` for the rest, an ``agents.yaml`` whose first key is ``lumen``. That key is
the case the matcher's alias rule exists for: it is a prefix of every seat's moniker.
The uuids are neutral.
"""
import json
from dataclasses import dataclass
from pathlib import Path

from macf.utils.roster import RosterEntry, local_roster

SEATS = [
    # account,     key,      moniker,        uuid
    ("pa_lumen",  "lumen",  "LumenMacEff",  "a1b2c3"),
    ("pa_lumen2", "lumen2", "Lumen2MacEff", "d4e5f6"),
    ("pa_lumen3", "lumen3", "Lumen3MacEff", "0a1b2c"),
    ("pa_lumen4", "lumen4", "Lumen4MacEff", "3c4d5e"),
]


def write_seat(homes: Path, account: str, moniker: str, uuid: str, published: bool = True) -> Path:
    """An agent home: its card files, its public tree, and (optionally) a units summary."""
    home = homes / account
    (home / ".maceff").mkdir(parents=True)
    (home / ".maceff" / "config.json").write_text(
        json.dumps({"agent_identity": {"calling_card": moniker}}))
    (home / ".maceff_primary_agent.id").write_text(f"{uuid}-0000-4000-8000-000000000000\n")
    (home / "agent" / "public" / "pd").mkdir(parents=True)
    if published:
        (home / "agent" / "public" / "pd" / "units.json").write_text(json.dumps({
            "version": 1, "agent": f"{moniker}@{uuid}", "published_at": 1.0,
            "units": [{"name": "session", "kind": "session", "memory_limit_mb": 512,
                       "restart": "always", "optional": False}]}))
    return home


def write_agents_yaml(path: Path) -> Path:
    lines = ["agents:"]
    for account, key, moniker, _uuid in SEATS:
        lines += [f"  {key}:", f"    username: {account}",
                  f"    display_name: {moniker.replace('MacEff', ' MacEff')}"]
    path.write_text("\n".join(lines) + "\n")
    return path


@dataclass(frozen=True, kw_only=True)
class Fixture:
    homes: Path
    runtime: Path
    units: Path
    agents_yaml: Path

    def roster(self, **kwargs):
        """``local_roster`` over this fixture, a peer's view unless ``uid`` says otherwise."""
        import os
        kwargs.setdefault("uid", os.getuid() + 100000)
        kwargs.setdefault("account_of", by_dirname)
        kwargs.setdefault("agents_yaml", self.agents_yaml)
        return local_roster(homes=self.homes, runtime=self.runtime, unit_dir=self.units, **kwargs)


def build(tmp_path: Path, published: bool = True) -> Fixture:
    """The fixture's homes, empty runtime and unit directories, and agents.yaml."""
    homes = tmp_path / "home"
    homes.mkdir()
    for account, _key, moniker, uuid in SEATS:
        write_seat(homes, account, moniker, uuid, published=published)
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    units = tmp_path / "units"
    units.mkdir()
    return Fixture(homes=homes, runtime=runtime, units=units,
                   agents_yaml=write_agents_yaml(tmp_path / "agents.yaml"))


def by_dirname(home: Path, _uid: int) -> str:
    """In a container a home's name is its account; the fixture's owner is the test user."""
    return home.name


def peer_roster(tmp_path: Path, **kwargs):
    """The roster as one seat's peer sees it: none of the homes is this account's."""
    return build(tmp_path).roster(**kwargs)


def seats(endpoint: str = "local") -> list:
    """The four seats as entries, without touching a filesystem (the matcher's input)."""
    out = []
    for account, key, moniker, uuid in SEATS:
        aliases = (key, account) if key.casefold() != moniker.casefold() else (account,)
        out.append(RosterEntry(card=f"{moniker}@{uuid}", moniker=moniker, uuid=uuid, account=account,
                               display_name=moniker.replace("MacEff", " MacEff"),
                               session_kind="daemon", state="running", endpoint=endpoint,
                               home=f"/home/{account}", aliases=aliases))
    return out
