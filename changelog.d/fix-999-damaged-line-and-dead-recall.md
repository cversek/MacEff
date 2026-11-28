### Fixed

- **The prompt hook's transcript scan says so when a line before the newest one doesn't parse.** Only the newest line of a live transcript can be cut mid-write and is still skipped quietly; a damaged line anywhere else used to be skipped silently on every scan.

### Removed

- **The disabled memory-recall experiment in the prompt hook.** Its call had been commented out, its script path pointed at a folder that no tree here has, and its 200 ms timeout was the subject of a follow-up that can no longer apply.
