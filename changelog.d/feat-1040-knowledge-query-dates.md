### Added

- **`knowledge query` shows each result's date, filters with `--since`, and orders newest first with `--recent`** (#1040). After a few days away, the newest record of the work was the hardest to find: results are ranked by how well they match, and nothing said how recent each was. The date is the one in the artifact's name or its folder's name (an idea's is its creation stamp); a result whose name carries none is shown blank, left out by `--since` with a count, and last under `--recent`. The default ranking is unchanged.
