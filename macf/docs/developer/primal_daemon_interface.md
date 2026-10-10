# The Primal Daemon's Interface (proposed)

**Status:** a proposal for MIS-0002 step 1, for the head maintainer to accept, change or redraw. Nothing here runs a daemon.

**Code:** `macf/src/macf/pd/interface.py`. **Tests:** `macf/tests/test_pd_interface.py`. **Example:** `examples/pd_declaration.json`.

## Why fix the interface first

Steps 2 to 7 of MIS-0002's landing plan each build on three things step 1 creates: the declaration format, the events a unit and the daemon write, and the daemon's socket. Four pieces of work are waiting on them now:
- the outside watch;
- the container rendering;
- the MacEff channel (#545), which already defines its half of the socket;
- the macOS rendering (#549), which already proposes a naming form.

Building those against a guess means redoing them when the core lands. Agreeing the interface first, and keeping it in one module with tests, lets them proceed in parallel with the daemon itself.

## 1. Names and paths

One function names every surface of an agent's primal daemon, from the calling card in the identity file:

| Surface | Name for `TheHarborMaster@ee5cd8` |
|---|---|
| per-agent part (`pd_id`) | `TheHarborMaster_ee5cd8` |
| systemd user unit | `maceff_pd-TheHarborMaster_ee5cd8.service` |
| launchd label | `maceff_pd.TheHarborMaster_ee5cd8` |
| runtime directory | `$XDG_RUNTIME_DIR/maceff_pd/`, or `/tmp/maceff_pd-<uid>/` without one; mode 0700 |
| control socket | `<runtime>/TheHarborMaster_ee5cd8.control.sock` |
| channel socket | `<runtime>/TheHarborMaster_ee5cd8.channel.sock` |
| daemon record | `<runtime>/TheHarborMaster_ee5cd8.json` |
| declaration | `<agent home>/.maceff/pd/declaration.json` |

- **Every name carries `maceff_pd`** [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)], and the agent too, because several agents can share one login user.
- **`pd_id` is the existing `session_identifier`.** It already maps a card to a name systemd and tmux both accept. tmux silently rewrites `.` and `:`, and systemd spells a template instance with `@`. The measurements are recorded in `macf/utils/identity.py`.
- **A socket path is checked against the kernel's limit** before binding, with a message that names it [MIS-0002-R129 (adapter_MUST_check_socket_path_length)].
- **The declaration lives in the agent's home**, never in the outer tier [MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)].

## 2. The declaration

JSON, validated closed: an unknown key is refused, because a key the daemon ignores is a setting its author believes is in force.

**A unit** states [MIS-0002-R09 (declaration_MUST_state_unit_fields), MIS-0002-R59 (unit_MUST_declare_memory_limit), MIS-0002-R63 (unit_MUST_declare_privacy_grants)]:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | lower case, unique in the declaration |
| `command` | yes | argv list; started by the daemon as the unit's parent, with the declared environment only [MIS-0002-R12 (pd_MUST_start_units_itself)] |
| `account` | yes | the owning account; the daemon's own user in step 1 (see open question 1) |
| `restart` | yes | `always`, `on-failure` or `never` |
| `exit_codes` | no | `success` (default `[0]`) and `no_restart` (default `[78]`, the field's "do not restart me") |
| `liveness_interval_s` | yes | how often the unit writes its liveness event |
| `memory_limit_mb` | yes | enforced and checked in step 3 |
| `environment` | no | the whole environment the unit gets |
| `optional` | no | never delays another unit [MIS-0002-R58 (optional_unit_MUST-NOT_delay_others)] |
| `privacy_grants` | no | macOS grants the unit needs, tested at install in step 4 |

**A schedule** is declared now, although step 2 runs it, so the format does not change under the later steps. It has no default missed-run policy: a schedule without one is refused [MIS-0002-R109 (CI_MUST_fail_schedule_without_policy)]. The policy is `skip`, `run_once`, `run_once_in_window` (with its window) or `report_only` [MIS-0002-R25 (missed-run_policy_MUST_be_listed)]. The target is `isolated` or a named agent's live session [MIS-0002-R29 (schedule_MUST_declare_target)].

**`operator_channels`** lists the channel names whose events count as the operator's activity; every other name counts as not the operator [MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)]. **`quiet_windows`** are the times in which the layer neither restarts nor compacts [MIS-0002-R50 (layer_MUST-NOT_act_in_quiet_window)].

## 3. The events

All three go to the agent's own event log; there is no second store [MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)].

| Event | Written by | Data |
|---|---|---|
| `pd_unit_alive` | the unit, at its interval | `agent`, `unit`, `pid`, `proc_start`, `interval_s` |
| `pd_unit_state` | the daemon | `agent`, `unit`, `state` (one of the six of R20), `pid`, `proc_start`, `reason` |
| `pd_control` | the daemon | `agent`, `act` (start, stop, restart, compact), `unit`, `asked_by` (`kind`, `card`), `reason` |

- **The unit writes its own liveness**, because a process that merely exists shows nothing about whether its loop runs [MIS-0002-R14 (unit_MUST_emit_liveness_events)].
- **The readout confirms the writer by `pid` and `proc_start`** before calling a unit alive [MIS-0002-R15 (readout_MUST_probe_liveness)].
- **`proc_start` is always `macf.notify.session.proc_start`:** clock ticks on Linux, the client's UTC asctime on macOS. It is compared through `verify_incarnation`, so the readout, the channel's peer check and the transcript monitor agree on one form.
- **`asked_by.kind` is `operator`, `wind_down`, `policy` or `harness`.** The last is for a compaction nobody asked for [MIS-0002-R52 (control_act_MUST_name_who_asked), MIS-0002-R127 (harness_compaction_MUST_be_recorded)].

## 4. The sockets

Two Unix sockets, so that each carries one shape and has one peer rule. Neither is ever a network port [MIS-0002-R80 (pd_MUST-NOT_listen_on_network)].

- **Control**, request and response, one JSON object per line each way. The peer must be the daemon's own user, which the kernel reports. The operator's command line and the tray connect here.
  - `{"op": "status"}` returns `{"ok": true, "units": [...]}`, each unit with its state, pid, start time and since when.
  - `{"op": "start" | "stop" | "restart", "unit": ..., "asked_by": {...}, "reason": ...}` acts on one unit. A stop from outside a session succeeds whatever gate the session enforces [MIS-0002-R48 (outside_stop_MUST_override_gates)].
  - `{"op": "compact", "asked_by": {...}, "reason": ...}` is accepted only from the operator or the agent's declared wind-down [MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)].
  - Any unknown operation or field refuses the whole request, with `{"ok": false, "error": ...}`, and nothing is done.
- **Channel**, a stream. The daemon writes closed notice records, one per line, in the shape the MacEff channel defines in #545, and reads nothing. The peer must descend from the agent's live session, matched by pid and start time [MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)].
- **The daemon record** holds `pid`, `proc_start` and `version`. It is written atomically after both sockets are bound, and every client checks its peer against it [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)].

## Open questions for the head maintainer

1. **Units under another account.** A unit's `account` is limited to the daemon's own user here. Running a unit as another account needs a privilege the daemon does not hold, and taking that from a file the agent can write would let it widen its own reach [MIS-0002-R78 (layer_MUST-NOT_widen_permissions)]. MIS-0004's per-agent broker user (its A-Q1) is the first real case. I propose an operator-owned grant file beside the declaration, read by a privileged launcher; the same question is open on #531.
2. **Agents sharing one login.** Any process of the same user can reach the control socket, including another agent's. That is the limit of a shared login, which per-agent users (MIS-0004) remove. Until then, should a control request name the asker's card and be logged as such, accepting that it cannot be proven?
3. **The record's `version` field.** #545's channel validates the record closed, so it would refuse the new field. I will add it to #545 when I rebase it, unless you prefer the record without one.
4. **One start-time form.** #534 adds a third representation (seconds since boot as a float, and an epoch from `ps`) beside `notify.session.proc_start`. I propose that everything use the latter.
5. **Naming.** #549 proposes `maceff_pd.<Name>.<idfrag>`; this proposes `session_identifier` for every surface, because tmux rewrites `.`. Either is fine for launchd; the point is one function.
6. **Where the package lives.** `macf/pd/` here; rename freely.

If you would rather I build the daemon's core on this interface, so that you keep your fixes moving, say so on the pull request.
