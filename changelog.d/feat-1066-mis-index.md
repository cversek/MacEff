### Added

- **`macf_tools mis index` prints the registry of MIS files** (`macf/mis.py`, `cli.py`, first slice of #1066): each file's number, title, status, secretary, deliberation, creation date, what it updates, where it lands and how it was resolved, read from the header the file already carries, so nothing is typed twice and the index can't drift from the files. `--json` gives the rows. The template is not a row. It lists the MIS files under `framework/mis`; the open ones that have no file there yet (their pull requests) are for a later slice.
