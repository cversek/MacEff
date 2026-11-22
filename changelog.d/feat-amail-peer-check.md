### Added

- **`macf_tools amail peer check <domain>`: a peer link checked station by station** (`peer_setup.check_peer`, amail policy 2.1.2): the declaration here, this side's agents map and registry keys for the peer, the peer's listener, the address the peer knows this host by, its build, and the cards and keys the peer declares for this broker's agents, which together predict whether mail reads attested; with `--send`, one signed test message the peer must acknowledge. The first failing station names its fix and the stations past it don't run. Each failure the first live link was set up through (a link declaring no agents, a key missing from a registry, a peer that could not store a message) is a named failing station.
- **A `ping` request on the rung-2 link** (`peer_link`): answered only to a declared peer (a stranger is still closed unread), with the receiver's domain, the domain it sees at the caller's address, its build and protocol, the cards it declares for the caller and whether its registry holds a key for each. Additive within protocol version 1; an older listener refuses it as unknown.

### Changed

- **A peer that closes the connection with no reply is told apart from one that is down** (`peer_link.ClosedUnread`, a `ConnectionError`, so a sender still keeps its copy): a failure to connect reads as unreachable, a connection reset or ended with no reply reads as closed unread, which is what a listener does to an address it doesn't declare.
