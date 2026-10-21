### Fixed

- **`ids renumber --apply` is no longer stopped by a zombie on a moved number** (`macf/ids/renumber.py`, policy `container_operations`). A zombie with one thread runs nothing and holds no files; a process whose main thread exited while another runs still counts.
