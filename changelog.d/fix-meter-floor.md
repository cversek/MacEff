### Fixed

- **The usage meter counts a live transcript instead of re-baselining it on every Stop.** A transcript can open with a record that has no timestamp, and the floor for its lookup then fell back to the file's mtime, which for a file being written is now: the lookup found none of its events, and every tick recorded a fresh baseline, so the main session's calls were never counted. The start is now the first timestamp among the opening lines, else the birth time, else unknown (one unbounded walk).
