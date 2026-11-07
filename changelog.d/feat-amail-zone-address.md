### Added

- **A broker answers for the shared mail zone by each agent's calling card** (`amail/zone.py`, `BrokerConfig.zone`, the addressing file's `zone`, MIS-0004 R06): an agent's zone address is `name_shortid@<zone>`, lower-cased, read only from the identity file in its home, never from `MACEFF_AGENT_NAME`. `agent_for` resolves such an address to the local agent, so mail to a seat's zone address reaches the seat's pickup box. The zone name stays in each deployment's addressing file.
