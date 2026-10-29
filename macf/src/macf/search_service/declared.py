"""Whether a primal daemon runs the search service as a declared unit.

A declared search unit is supervised: its daemon starts it, restarts it and reads its
liveness. A copy started by hand beside it would take the port first and leave the unit
failing to bind, unsupervised work in its place. So the manual start asks here first.

Read from the declarations themselves, without validating them: the question is only
which unit's command names the module, and a reader that refused a declaration over a
field it does not need would answer "none" for a unit that runs.

No heavy imports: the CLI asks here before it imports the model's dependencies.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

#: What a unit's command must contain for it to run the search service.
SEARCH_MODULE = "macf.search_service"


@dataclass(frozen=True)
class DeclaredSearchUnit:
    unit: str
    declaration: Path
    agent: str = ""

    def describe(self) -> str:
        who = f" of {self.agent}" if self.agent else ""
        return f"unit '{self.unit}'{who} (declared in {self.declaration})"


def runs_search(command) -> bool:
    """Whether a unit's command (a list of arguments) runs the search service."""
    return SEARCH_MODULE in " ".join(str(a) for a in (command or []))


def _declarations(own_home: Optional[Path], rendered_root: Optional[Path]) -> Iterable[Path]:
    from macf.pd.names import RENDERED_DECLARATIONS, declaration_path
    seen = []
    if own_home is not None:
        seen.append(declaration_path(Path(own_home)))
    root = Path(rendered_root) if rendered_root is not None else RENDERED_DECLARATIONS
    try:
        seen.extend(sorted(p / "declaration.json" for p in root.iterdir()))
    except OSError:
        pass            # no deployment renders declarations here (a host), or none readable
    out = []
    for p in seen:
        if p not in out:
            out.append(p)
    return out


def find_declared_search_unit(own_home: Optional[Path] = None,
                              rendered_root: Optional[Path] = None) -> Optional[DeclaredSearchUnit]:
    """The first declared unit that runs the search service: in this agent's own declaration,
    then in every declaration the deployment rendered (one search service serves a whole
    container, whichever account's daemon runs it). None when no declaration names one."""
    if own_home is None:
        try:
            from macf.utils.paths import find_agent_home
            own_home = Path(find_agent_home())
        except Exception:
            own_home = None
    for path in _declarations(own_home, rendered_root):
        try:
            body = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(body, dict):
            continue
        for unit in body.get("units") or []:
            if isinstance(unit, dict) and runs_search(unit.get("command")):
                return DeclaredSearchUnit(unit=str(unit.get("name", "?")), declaration=path,
                                          agent=str(body.get("agent", "")))
    return None
