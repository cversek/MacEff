### Fixed

- **A broker's own domain is compared without case, and an empty one never matches** (`amail/attest.py` `acceptance_time`, #749): a sidecar written under `Example.org` was not recognized as the broker's own when the broker's domain was configured `example.org`, so its acceptance time was dropped; an empty configured domain matched a sidecar with no origin. Both sides are stripped and lowercased, and an empty one yields no time.
