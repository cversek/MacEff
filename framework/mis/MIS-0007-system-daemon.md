# MIS-0007: A system daemon, one root-run supervisor per system

**Number**: 0007
**Type**: Standards
**Status**: Draft
**Authors**: the operator; drafted by the head maintainer as Secretary
**Secretary**: the head maintainer
**Deliberation**: pending
**Created**: 2026-10-28
**Updates**: none
**Supersedes**: none
**Lands-in**: a system daemon in the macf package, with its tests (planned); framework/policies/base/infrastructure/persistent_layer.md, a section on the system daemon (planned); framework/glossary.md (planned)
**Resolution**: none

---

## 1 Summary

A system daemon is one process per system, run by root. It starts each of its units as the account its system declaration names, supervises them, and runs no feature code itself. It is a second locus beside each agent's primal daemon (MIS-0002). Units that hold what belongs to the system, or that serve every agent on it, run under the system daemon. Units that belong to one agent stay with that agent's primal daemon.

MIS-0004 depends on it directly, because its mail broker is a system-daemon unit. The operator proposed the system daemon on #850, MIS-0004's deliberation, and on 2026-10-28 moved that its requirements be documented in a separate draft. That way mail and the system daemon can be developed in parallel without breaking the basis for reconciling them (#850, comment 6477160351). The same motion named the head maintainer Secretary of this draft. The requirements below are gathered from the positions on #850. This MIS concerns the operator, who installs and declares the system daemon, and every agent on a system that has one.

**This draft is a working specification for two prototypes.** The container-management maintainer prototypes it in a Linux multi-seat container, where it can parent the seats' primal daemons. The host-side maintainer prototypes on macOS the one relationship a container can't test: watching a unit that the system daemon can't parent. Section 12 assigns each requirement to one of them.

## 2 Motivation

- **A unit that needs another account has no supervisor.** A primal daemon starts units only as its own account (persistent_layer 10.3, under MIS-0002-R78 (layer_MUST-NOT_widen_permissions)). So a mail broker on its own account needs something that can start a unit as a declared account. Without one shared supervisor, each such service gets a service daemon of its own, which is the sprawl MIS-0002 set out to end (the operator, #850 comment 6471946844). Evidence: the policy, and the positions on #850.
- **Shared resources are duplicated per agent.** A warm embedding model holds 1,273 MB resident, once per agent under MIS-0006's draft, although only each agent's index is private. The subscription's usage reading runs in every agent's hooks, each with its own copy of the credential. Once a fetch failed, every hook on the host retried it on every tool call (#852). Evidence: a measurement (the search service) and an incident.
- **Only a parent can read an exit status.** A primal daemon restarted beside its running session adopts that session. At every planned restart it then reports the session failed, because only a parent reads an exit status (Seat N, #850 comment 6476229730). Evidence: an incident, reported by the seat.
- **A container's start step already does this job, once.** It renders declarations that only root can write, and starts each daemon as its account (persistent_layer 10.1). Nothing keeps doing that after the start (#850 comment 6475537319). Evidence: the deployment.

## 3 Goals and Non-Goals

**Goals**
- One supervisor per system for the units that need an account other than an agent's, or that serve every agent on the system.
- A privileged part as small as it can be: root only starts, stops and accounts for units.
- A placement rule that says where any new unit goes, so the system daemon doesn't become the next sprawl.
- One system declaration format for a Linux container, a Linux host and macOS, with each platform's limits stated.

**Non-goals**
- The units' own behavior. Mail is MIS-0004's, and the shared embedding model is MIS-0006's.
- Replacing the primal daemon. Each agent's primal daemon keeps supervising that agent's session and its own units. The system daemon supervises accounts and shared resources, not sessions.
- A fleet layer across systems. If one comes, it reads the system daemons' reports, and instructions never flow down through it (Q04).

## 4 Guide-Level Explanation

The operator installs the system daemon once per system, as root, with a system declaration that only root can write. The declaration lists units, each with the account it runs as, how it starts, its environment and its restart policy. The daemon forks, changes to the unit's account, executes the declared command and reaps it. It does nothing else as root.

In a container, it also parents each seat's primal daemon, so it reads each one's exit status. On macOS, a primal daemon has to stay a LaunchAgent in the operator's GUI session, so the system daemon watches it instead: it reads its liveness and reports when it is down, but doesn't start it. Agents read the system daemon's state through a socket that answers status only. Each system daemon is checked by an outside watch that doesn't run under it.

To place a new unit, ask three questions:
- **Whose secret does it hold?** That decides its account.
- **How many agents does it serve?** That decides its supervisor.
- **Does it need a login's session, for a privacy grant or the login keychain?** Then it runs in that session, and the system daemon watches it.

The usage reading is an example. It holds a person's credential and serves every agent on that person's login. So it runs once per login, as that login. On macOS it is a LaunchAgent the system daemon watches. Each agent given a login of its own needs its own client credential, which multiplies those readers, so one reader serving other logins through the system daemon's feed keeps the account-wide reading to one (#850, 6481387490).

**The system declaration's format** is #856 (draft), which both prototypes import and which freezes once each has run a unit against it. A declaration has `version`, `system`, one `time_zone`, `stop_timeout_s` and its `units`. Each unit has:
- `name`, `account` and `relationship` (parent or watch);
- `command`, required for a parented unit;
- `environment` in full, and an `identity_probe` for R12;
- `restart` and `exit_codes`;
- `stop_grace_s`, `liveness_interval_s` and `memory_limit_mb`;
- up to 16 `groups`, and `after` for the start order;
- a `platform`: `linux`, with `stop` set to `cgroup` or `subreaper`, or `launchd`, with a `domain` and a `label`.

The system daemon sets `TZ` and the unit's marker itself, and a unit can't declare them. A parented unit's exit code is read through the exit table:

| A parented unit exits with | `restart: always` | `on-failure` | `never` |
|---|---|---|---|
| a code in `success` | restarted | stays stopped | stays stopped |
| a code in `no_restart` | stays stopped | stays stopped | stays stopped |
| any other code | a failure, restarted with backoff | a failure, restarted with backoff | a failure, stays down |

Under `on-failure`, a unit that wants a restart has to fail. A watched unit's `restart` is `never` until the host prototype settles Q01.

## 5 Terms

These are the terms the Specification uses beyond the glossary.
- **system**: one host, or one container.
- **system daemon**: the one root-run process per system that starts, stops and accounts for the units its system declaration names, each as its declared account.
- **system declaration**: the file, writable only by root, that lists a system daemon's units, with each unit's account, command, environment and restart policy.
- **unit**: a managed unit (glossary), here one of the system daemon's.
- **root process**: the system daemon's own process, the one that runs as root.
- **feature code**: code that does a unit's work, as opposed to starting, stopping and accounting for units.
- **parent**: the relationship in which the system daemon starts a unit and reads its exit status.
- **watch**: the relationship in which the system daemon observes a unit it did not start, and reports when it is down.
- **session-bound unit**: a unit that needs a login's GUI session, for a privacy grant or the login keychain.
- **restart report**: the notice, after a restart, of which units were carried, which changed, and what was lost.
- **feed**: data the system daemon publishes for primal daemons and hooks to read and weigh.
- **outer manager**: the service manager that starts the system daemon: launchd, systemd, or a container's runtime.
- **stop timeout**: the outer manager's limit on stopping the whole system daemon, such as a container's `docker stop -t` or launchd's `ExitTimeOut`.
- **marker**: the environment value `MACEFF_SD_UNIT`, which the system daemon sets in each unit so that it can find the unit's detached workers where no control group is delegated.
- **exit table**: how a unit's exit code is read: a code meaning success, a code meaning do not restart, or any other code, a failure.

## 6 Specification

The Secretary gathered these preliminary requirements from the positions on #850, at the operator's motion of 2026-10-28. Section 7 gives each one's reason and source. Section 12 assigns each one to a prototype.

### 6.1 The root process

- **R01** [MUST · decidable: macf/tests/test_sd_root.py::test_one_per_system] Each system MUST run at most one system daemon, started as root by the system's own service manager. (system_daemon_MUST_be_one_per_system)
- **R02** [MUST · decidable: macf/tests/test_sd_root.py::test_root_only_supervises] The root process MUST only start declared units as their accounts, stop them, and reap or read their exits, and run no feature code. (root_MUST_only_supervise)
- **R03** [MUST · decidable: macf/tests/test_sd_root.py::test_declaration_parsed_unprivileged] The system daemon MUST parse its system declaration in a process without root, and import nothing from any unit's tree. (declaration_MUST_be_parsed_unprivileged)
- **R04** [MUST · decidable: macf/tests/test_sd_root.py::test_unit_files_by_descriptor] When root touches a unit's file, it MUST open it by descriptor without following links, check the owner on that descriptor, and act relative to it. (root_MUST_act_by_descriptor)
- **R05** [MUST · decidable: macf/tests/test_sd_root.py::test_stop_reaches_whole_unit] When the system daemon stops a unit, it MUST end the unit's control group where delegated, its launchd job on macOS, and otherwise each process carrying the unit's marker. (stop_MUST_reach_the_whole_unit)
- **R06** [MUST · decidable: macf/tests/test_sd_root.py::test_declaration_root_written] The system daemon MUST refuse a system declaration that any account other than root can write. (declaration_MUST_be_root_written)
- **R07** [MUST · decidable: macf/tests/test_sd_socket.py::test_status_only] The system daemon's socket MUST answer status only, and accept no instruction from any agent. (socket_MUST_answer_status_only)

### 6.2 Units and their placement

- **R08** [MUST · decidable: macf/tests/test_sd_units.py::test_feature_code_not_root] Each unit that runs feature code MUST run as a process under a non-root account, never as a thread of the root process. (feature_code_MUST_run_unprivileged)
- **R09** [MUST · judgment: the head maintainer, at review of each new unit] A unit MUST run as the account whose secret it holds, under the supervisor whose scope matches the agents it serves. (unit_MUST_be_placed_by_secret_and_scope)
- **R10** [MUST · judgment: the head maintainer, at review of each new unit] Where a unit needs a login's session, it MUST run in that session, and the system daemon watches it instead of parenting it. (session_bound_unit_MUST_be_watched)
- **R11** [MUST · decidable: macf/tests/test_sd_units.py::test_parent_in_container] Where the system is a container, the system daemon MUST parent each agent's primal daemon and read its exit status. (system_daemon_MUST_parent_where_it_can)
- **R12** [MUST · decidable: macf/tests/test_sd_units.py::test_declared_environment_and_identity] Each unit MUST start with only its declared environment, checked under `env -i`, together with the identity it presents to outside services. (unit_environment_MUST_be_declared_in_full)
- **R13** [MUST · decidable: macf/tests/test_sd_units.py::test_one_time_zone] The system daemon MUST declare one time zone for all its units, and state it in every restart report. (system_daemon_MUST_declare_one_time_zone)
- **R14** [MUST · decidable: macf/tests/test_sd_units.py::test_code_version_recorded] When a unit starts, the system daemon MUST record the code version it started from, and report a unit that runs older code. (unit_code_version_MUST_be_recorded)
- **R15** [MUST · decidable: macf/tests/test_sd_units.py::test_restart_report_in_agent_store] After a restart, the report of what was carried, changed and lost MUST be written into the agent's own store, by the agent's account. (restart_report_MUST_reach_agent_store)
- **R16** [MUST · decidable: macf/tests/test_sd_units.py::test_agent_controls_own_units] An agent MUST be able to start, stop, read the status of, and read the logs of the units under its primal daemon, without root. (agent_MUST_control_its_own_units)
- **R21** [MUST · decidable: macf/tests/test_sd_units.py::test_parented_pd_speaks_by_exit_status] A parented primal daemon MUST tell its parent what it wants only by its exit status, read through the declared exit table. (parented_pd_MUST_speak_by_exit_status)
- **R17** [MUST · judgment: the head maintainer, at review of each feed] Data MUST flow from the system daemon down to primal daemons and hooks as feeds the reader weighs, never as instructions. (feeds_MUST_flow_down_never_instructions)

### 6.3 Status and the outside watch

- **R18** [MUST · decidable: macf/tests/test_sd_watch.py::test_watch_outside_system_daemon] Each system daemon MUST be checked by an outside watch that the service manager runs, never by a unit of that system daemon. (system_daemon_MUST_have_outside_watch)
- **R22** [MUST · decidable: macf/tests/test_sd_socket.py::test_status_reports_egress_rule] The system daemon's status MUST report whether the system's egress rule is loaded; loading it stays the operator's install step. (egress_rule_MUST_be_reported_by_status)

### 6.4 Platforms and the outer manager

- **R19** [MUST · decidable: macf/tests/test_sd_platform.py::test_reload_waits_for_bootout] On macOS, a reload MUST wait until launchd reports the booted-out job gone before it bootstraps the job again. (reload_MUST_wait_for_bootout)
- **R20** [MUST · decidable: macf/tests/test_sd_declaration.py::test_the_longest_stop_chain_must_fit_inside_the_stop_timeout] The longest chain of unit stop graces, in reverse start order, MUST fit inside the stop timeout the system declaration states. (container_stop_timeout_MUST_exceed_unit_grace)

## 7 Rationale and Rejected Alternatives

Each requirement's reason, with its source on #850.
- **R01**: one supervisor per system ends the service daemon per service (the operator, 6471946844). The service manager starts it, so the operating system restarts it.
- **R02**: a thread of a root process runs with root's privilege, so feature code can't live there (the container-management maintainer, 6475537319). On Linux the root process forks, changes account, executes and reaps. On macOS launchd is every job's parent, so its verbs there are rendering a unit's plist by descriptor (R04), `bootstrap`, `bootout`, `kickstart`, and reading a job's state (6481387490). Seat M asked that root's job be a closed list, and the container-management maintainer asked that the list go into this MIS verbatim (6476229281, 6476259000). Units that share one account and one trust context can still share a process as threads, as long as that process isn't root's (6472809029, 6475537319). That keeps the operator's performance option.
- **R03**: a root-run step once imported from an environment that a service account could rewrite, which made that account's code run as root (Seat M, 6476229281).
- **R04**: a root delete once checked ownership by name, then acted by name, and a symlink swapped in between the two redirected it. The rule ("check the ancestors") was followed both times; what was missing was binding the check to the act (Seat M, 6476229281).
- **R05**: a process-group kill misses whatever detached (Seat M). In both multi-seat containers the cgroup2 hierarchy is mounted read-only and the container is unprivileged, so there the system daemon makes itself a child subreaper, collects a unit's detached workers, and finds them by the marker in their environment (6479561476). macOS has no control groups, and each unit is its own launchd job (6476909402). On either, a unit that scrubs the marker or detaches outside its job must end its own workers, the limit persistent_layer already states for primal-daemon units.
- **R06**: the declaration is what keeps a unit's account and command out of an agent's reach (persistent_layer 10.1). On macOS that is a system-domain plist only root can write (6468749316).
- **R07**: this is the system-level form of MIS-0002-R78 (layer_MUST-NOT_widen_permissions). An agent reads the system daemon's state but never steers it (6472809029).
- **R08**: same reason as R02 (6475537319).
- **R09**: whose secret a unit holds decides its account, and how many agents it serves decides its supervisor (6475537319). Asked as one question, the usage reading had no home (6476909402).
- **R10**: on macOS, privacy grants attach to the responsible process and the login session (persistent_layer 3.1, 3.2), so a primal daemon stays a LaunchAgent (6472809029, 6475350267). launchd holds a job's exit status for any watcher, so on macOS watching versus parenting comes down to who may start and stop the unit, not who can read its status (6481387490). The host-side maintainer found that a GUI-domain LaunchAgent and its descendants can read the login keychain (6476909402). Whether a system-domain job with `UserName` can read it is untested (Q02).
- **R11**: an adopter can't read a unit's exit status, so every planned restart reported the session failed (Seat N, 6476229730). In a container no GUI session binds a primal daemon, so the system daemon can parent it there (6475537319). On a Linux host the user's service manager binds it: its runtime directory and user bus hold the session's tmux (persistent_layer 6.3). So R11 is scoped to containers until the Linux host form is decided (6479561476).
- **R12**: units that moved onto declarations lost a timezone and an agent name, and read healthy (#836). After one move, a PATH order made a tool act under a person's login (Seat N). A client running without `USER` filed its credential under a second keychain item (#853). Every variable looked fine except the identity the unit presented, so the check compares that identity too (6476909402).
- **R13**: one restart moved a seat's time zone, and its scheduled wakes fired at the same clock numbers in the new zone (Seat L, 6476228404). A container's clock and its configured zone can disagree (Seat M).
- **R14**: a worker without reload served stale code after an update until someone restarted it by hand. A supervisor can't know when a unit needs restarting for new code, so it records and reports, and doesn't guess (Seat L, 6476228404).
- **R15**: the restart report is the most useful notice a seat gets, and it stays the seat's, written by the seat's account (Seat L, 6476228404).
- **R16**: long-lived services survive restarts under a supervisor, but only if the seat keeps control of its own (Seat K, 6476228830). It covers the units under the agent's primal daemon. A primal daemon controlling itself through the system daemon would be instructing it, which R07 forbids (6479561476).
- **R17**: a fleet server, if it comes, aggregates the system daemons' reports, and each hop carries data the reader weighs (the host-side maintainer, 6475350267). Mode changes still come from the operator directly, as `public_voice` 2.5 says of relayed words.
- **R18**: a watch that runs inside the thing it watches dies with it. Once the system daemon hosts the broker and the model, its failure takes them all down at once (6475537319). This extends MIS-0002-R74 (pd_MUST_have_outside_watch) to the new locus.
- **R19**: `launchctl bootout` returns before the job has exited, so a bootstrap straight after it fails with error 5 (#841, 6468749316).
- **R20**: docker's default stop timeout is 10 s, shorter than a session unit's 30 s stop grace (persistent_layer 6.2), so `docker stop` kills units mid-grace, and does so today (6479561476). Units stop in reverse start order, so the graces add along each chain. #856 checks this at load.
- **R21**: a parented primal daemon that asked through the socket would be instructing the system daemon, which R07 forbids, so its exit status is its one channel up (6479561476). The exit table is the primal daemon's own, read the way its core reads it (#856).
- **R22**: loading a pf or iptables rule needs root, which R02 keeps from the root process. So the operator's install step loads it and makes it survive a reboot, as a container's start step does today, and the status says whether it is in force (6481387490, 6481618179).

**Rejected**
- **Units as threads of the root process.** A thread there runs as root (6475537319).
- **The outside watch as a unit of the system daemon.** It would die with what it watches. The head maintainer and the host-side maintainer withdrew it on #850 (6476069492, 6476909402).
- **Primal daemons parented by the system daemon on macOS.** Privacy grants attach to the login session, which a system-domain job can't host (6472809029, 6475350267).
- **A service daemon per service needing its own account.** That is the sprawl the operator ruled out (6471946844). The container-management maintainer withdrew it for the broker (6475537319).
- **Feature code in the root process.** Seat M's two incidents show what root running another account's code costs (6476229281).

## 8 Prior Art

- MIS-0002 (Final): the primal daemon, and persistent_layer 10.1's service daemon for a container's service account.
- A container's start step: it does this MIS's job once, at start.
- launchd system-domain jobs with `UserName`, and systemd system units with `User=`: each platform's way to start a process as a declared account.
- MIS-0004 (deliberation): agent mail, which depends on this MIS.
- MIS-0006 (draft, #751): the shared embedding model, which would run under this MIS.
- #856 (draft): the system declaration schema both prototypes import.

## 9 Compatibility and Deployment

- **No flag day.** A system without a system daemon keeps working as it does today. Each unit moves under it one system at a time.
- **Order.** The container first, where the start step becomes the system daemon kept running. A macOS spike of the watch relationship runs in parallel, before the interfaces freeze (6476909402). The Linux host follows the container.
- **Installing it is the operator's act.** It runs as root, so its installation is never the layer's own act (MIS-0002-R78 (layer_MUST-NOT_widen_permissions)). In a container, the start step is the install step: it runs once as root, creates the accounts and the boxes, loads the egress rule, and then hands over to the system daemon (6481618179).

## 10 Security and Safety

The root process is the one privileged piece of the system daemon, and R02 to R07 keep it to starting, stopping and accounting for units. Seat M's two incidents (R03, R04) show the two ways root ends up running an unprivileged account's code: importing from a tree that account can write, and checking a file by name before acting on it by name. A failed system daemon takes all its units down at once, which is why its outside watch runs under the service manager and not under it (R18). Agents can't write its system declaration (R06), and its socket answers status only (R07).

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | decidable | `macf/tests/test_sd_root.py::test_one_per_system` | planned |
| R02 | decidable | `macf/tests/test_sd_root.py::test_root_only_supervises` | planned |
| R03 | decidable | `macf/tests/test_sd_root.py::test_declaration_parsed_unprivileged` | planned |
| R04 | decidable | `macf/tests/test_sd_root.py::test_unit_files_by_descriptor` | planned |
| R05 | decidable | `macf/tests/test_sd_root.py::test_stop_reaches_whole_unit` | planned |
| R06 | decidable | `macf/tests/test_sd_root.py::test_declaration_root_written` | planned |
| R07 | decidable | `macf/tests/test_sd_socket.py::test_status_only` | planned |
| R08 | decidable | `macf/tests/test_sd_units.py::test_feature_code_not_root` | planned |
| R09 | judgment | the head maintainer, at review of each new unit | standing |
| R10 | judgment | the head maintainer, at review of each new unit | standing |
| R11 | decidable | `macf/tests/test_sd_units.py::test_parent_in_container` | planned |
| R12 | decidable | `macf/tests/test_sd_units.py::test_declared_environment_and_identity` | planned |
| R13 | decidable | `macf/tests/test_sd_units.py::test_one_time_zone` | planned |
| R14 | decidable | `macf/tests/test_sd_units.py::test_code_version_recorded` | planned |
| R15 | decidable | `macf/tests/test_sd_units.py::test_restart_report_in_agent_store` | planned |
| R16 | decidable | `macf/tests/test_sd_units.py::test_agent_controls_own_units` | planned |
| R17 | judgment | the head maintainer, at review of each feed | standing |
| R18 | decidable | `macf/tests/test_sd_watch.py::test_watch_outside_system_daemon` | planned |
| R19 | decidable | `macf/tests/test_sd_platform.py::test_reload_waits_for_bootout` | planned |
| R20 | decidable | `macf/tests/test_sd_declaration.py::test_the_longest_stop_chain_must_fit_inside_the_stop_timeout`, in #856 | planned |
| R21 | decidable | `macf/tests/test_sd_units.py::test_parented_pd_speaks_by_exit_status` | planned |
| R22 | decidable | `macf/tests/test_sd_socket.py::test_status_reports_egress_rule` | planned |

**Cold-reader trial**: not yet held.

**Use trial**: not yet held.

## 12 Landing Plan

### 12.1 The prototypes

The operator's motion on #850 (comment 6477160351) treats this draft as the working specification for two prototypes.

| Prototype | Who | Requirements | What it should show |
|---|---|---|---|
| Linux container | the container-management maintainer | R01 to R09, R11 to R18, R20 to R22 | The start step kept running as the system daemon. Each seat's primal daemon parented, with its exit status read. The root process held to R02's list, stopping by control group. |
| macOS host | the host-side maintainer | R01, R02 (launchd's verbs), R05 (a launchd job per unit), R06, R07, R10, R12, R19, R20 (launchd's `ExitTimeOut`), R22 | A system-domain job with `UserName` starting a unit as a service account. Watching a LaunchAgent the daemon can't parent, with the per-login usage reading as its first unit (#853's reader). An answer to Q02. |
| Withheld | after the prototypes | the Linux host form of each requirement; a fleet layer (Q04) | The order puts the Linux host after the container, and the fleet layer is deferred. |

### 12.2 After the prototypes

The prototypes' results make this draft's next revision. MIS-0004's requirements that place the broker under the system daemon wait on this MIS. This MIS lands by area, as MIS-0002 did. Each pull request carries its requirements' Conformance rows.

## 13 Open Questions

- **Q01** On macOS, can the system daemon restart a primal daemon it watches, through the user's own service manager, or only report that it is down? Probably yes while the login is present, since root can target the login's `gui/<uid>` domain. With nobody logged in there is no domain to restart in, and the report should say the login is absent, not that the unit failed (6481387490). Until the host prototype tests it, a watched unit's restart is `never` (#856). (watched_unit_restart_on_macos)
- **Q02** Can a system-domain job with `UserName` read the login keychain? Untested. A GUI-domain LaunchAgent and its descendants can. The host prototype tests it with the usage reading. (system_job_reads_login_keychain)
- **Q03** Who installs and updates the system daemon, and how does an update avoid restarting every unit? (system_daemon_update_path)
- **Q04** Does a fleet layer that reads several systems' reports belong in this MIS or a later one? Deferred. (fleet_layer_placement)

## 14 Deliberation Record

None yet. The operator opened this draft by motion on #850 (comment 6477160351) and named the head maintainer its Secretary. Whether it gets a deliberation of its own is the operator's decision on its pull request (MIS-0001-R22 (operator_MUST_convene_or_explain)). Its requirements come from MIS-0004's deliberation, #850, and section 7 names the comment behind each one.

## 15 Revision History

- 2026-10-28: first draft, written by the Secretary at the operator's motion and addendum on #850 (comment 6477160351), from the positions there. Its number, 0007, is provisional until the Secretary confirms it before the draft leaves Draft.
- 2026-10-29: the corrections the authors of MIS-0004 agreed on #850 for the system daemon (6479561476, 6481387490, 6481618179), folded in by the Secretary. R02 states root's verbs per platform. R05 gains the container's subreaper and marker. R11 is scoped to containers, and R16 to the units under an agent's primal daemon. R20 to R22 are new: the stop budget #856 checks, a parented primal daemon speaking only by its exit status, and the status reporting the egress rule. The Guide gains the schema (#856) and its exit table, and Q01 a likely answer.

## Wiki-Links

[[supervision]] [[service_supervision]] [[capability_boundaries]] [[mis]]
