### Added

- **`mis index` lists when each MIS was revised** (GH#1066): each row carries the dates of its revisions and amendments, read from the file's own Deliberation Record lines that are themselves one ("a revision at the repo owner's request", "an amendment", "amended in place by"), never from a stored list; the table says how many and the last. A line that only mentions a revision is not counted.
