### Fixed

- **The compaction recovery message puts what recovery needs where it arrives** (`hooks/recovery.py`, #802). Claude Code keeps a long hook context in a file and shows the model a short preview. The recovery message runs to about 35 KB, and its artifact list and authorization sat past the preview, so a successor never saw them. A short block right after the banner's first lines now gives the mode and what it authorizes, the artifacts to open with the Read tool, in order, and that an artifact re-attached after compaction has not been read.
