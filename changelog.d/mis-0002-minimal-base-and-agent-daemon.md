### Changed

- **MIS-0002 specifies the minimal base and the Agent Daemon built on it** (`framework/mis/MIS-0002-persistent-layer.md`, a revision at the repo owner's request): section 6 is now the base every primal daemon is (6.1), the Agent Daemon's components, each opening with what adds it (6.2), and placement in containers and on macOS (6.3). Every requirement kept its ID and slug. R183 to R185, R193 and R194 are new, R186 to R192 and R195 to R198 move here from MIS-0007's draft, R01, R60, R65 and R80 are reworded so the base stands alone, and R76 is withdrawn. The glossary gains Agent Daemon, base, component and principal.
- **persistent_layer follows the same seam** (`framework/policies/base/infrastructure/persistent_layer.md`): sections 1 to 4 are the base, 5 to 11 the Agent Daemon, 12 to 14 placement. Every citation of its section numbers in code, tests and documents moved with it. Section 1.7 says what a daemon builds, and 13.4 what agents that share one login can prove.
- **A system or fleet daemon builds no Agent Daemon component** (`macf/src/macf/pd/daemon.py`, MIS-0002 R183 and R184, MIS-0007 R74): only a declaration of `kind: agent` builds the notice path and its wake, the MacEff channel's socket, duties, the login check and mail. A system or fleet daemon runs the base alone and records what its core would have noticed.

### Removed

- **The old `hypervisor` supervision value** (`macf/src/macf/amail/deploy_config.py`, MIS-0002 R76 withdrawn): the reader that mapped it to `primal-daemon` is gone. No deployment checked still writes it.
