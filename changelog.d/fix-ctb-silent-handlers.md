### Fixed

- **109 except handlers that dropped an error silently now say something, or say why not** (47 files under `macf/src/macf` and `docker/scripts/start.py`): 56 warn on stderr with what failed and what happens instead; 53 keep the drop with a `noqa: S110`/`S112` and the reason. No caught type or control flow changes (#988).
