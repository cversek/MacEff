### Added

- **The primal daemon's event stream** (`pd/stream.py`, MIS-0002 R150 to R156, policy `persistent_layer` 11.4). Each daemon serves `<agent>.events.sock`, follows its own event log and sends each new record to the subscribers that chose its source, within the loop's tail interval. The log stays the only store.
  - A record carries its position (the log's identity and a byte offset on a line boundary), its source, the daemon's own agent, the log's time, and its origin: `daemon` only for a line the daemon wrote itself, `log` for anything else appended to the log.
  - A subscriber that reconnects with its position resumes just after it, or gets one `gap` record where rotation, a bad position or a long backlog means records may be missing.
  - Each subscriber has a bounded queue and non-blocking sends, so one that never reads loses its own backlog and gets a `gap`, never the daemon's time. A connection that sends no hello within three seconds is closed, and a uid may hold eight connections.
  - Another uid subscribes only with a `stream_grants` entry in the declaration, limited to the sources it names.
- **`macf_tools pd stream subscribe|silence|unsilence|route`.** The operator's rules are `pd_stream_rule` events, in force at once and folded back at the next start. Setting the mode puts the three rule commands in the client's ask list, as `pd entry add` is. A declaration's `operator_uid` makes the rules the operator's uid alone.
