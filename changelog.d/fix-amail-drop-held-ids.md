### Fixed

- **A message is held once** (`amail/client.py`, MIS-0004 R16): a repeated hand-off of one message (a broker restarted between writing the box and clearing its intake) left two copies of one id in the recipient's store, as a container experiment showed. Ingest now drops a copy whose id the store already holds, removes it from the box, and records the drop in the held message's sidecar under `duplicates_dropped`. Policy `amail` 1.7.0, §2.3.
