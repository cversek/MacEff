### Fixed

- **The shared container view counts every declared daemon, the mail broker's included** (`macf/src/macf/pd/shared_view.py`, `daemon.py`; MIS-0002 R62). The view scanned `/home` only, and a daemon published only when its home had an `agent/public` tree. A service account, whose home is elsewhere and has no such tree, was invisible to every agent beside it, so R62's "every unit in that container" wasn't met (the head maintainer's judgment on #552).
  - The view now lists daemons first from the declarations root renders under `/etc/maceff/pd/`, the deployment's own word on which daemons exist. One that hasn't published reads "declared, no summary published".
  - A declared daemon publishes even without a public tree.
  - The `/home` scan stays for seats with no declaration yet, and no home is listed twice.
  - Planting each defect fails its test.
