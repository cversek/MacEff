"""Parent-to-children lookups over tasks already read from the store.

Build the index once per read. Finding a node's children by scanning every task
made each render that walks the hierarchy quadratic in the size of the store:
at 1,350 tasks, 7.3 million parent reads and about 1.5 s of a 2.2 s tree.
"""
from typing import Dict, Iterable, List, Optional

from .models import MacfTask


def children_index(tasks: Iterable[MacfTask]) -> Dict[Optional[str], List[MacfTask]]:
    """Each parent id's children, in numeric id order; top-level tasks under None."""
    index: Dict[Optional[str], List[MacfTask]] = {}
    for t in tasks:
        # str() on both sides also covers int-coerced legacy entries (GH #112).
        key = str(t.parent_id) if t.parent_id is not None else None
        index.setdefault(key, []).append(t)
    for kids in index.values():
        # Zero-pad ids so "2" sorts before "10".
        kids.sort(key=lambda t: str(t.id).zfill(10))
    return index
