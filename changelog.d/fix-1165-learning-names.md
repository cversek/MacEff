### Fixed

- **knowledge eval labels learnings named the way the learnings CLI names them** (`knowledge_eval.py`, #1165): the filename pattern matched only names ending in `_learning.md`. So a corpus of `<date>_<time>_<slug>.md` learnings had no cross-reference or same-subject labels at all, and a mixed corpus silently lost part of its labels. It now matches any dated `.md` name. Both callers keep only names that resolve to a learning, and a name counts as unresolved only when it names no node at all. One test; two planted defects each turn it red.
