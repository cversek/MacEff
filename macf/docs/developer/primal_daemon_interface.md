# The Primal Daemon's Interface

**Status:** accepted by both maintainers as MIS-0002 step 1's interface (#555), revised with their changes. Nothing here runs a daemon. The head maintainer builds the core on it; the outer tiers, the channel and the macOS parts build against it in parallel.

**Code:** `macf/src/macf/pd/interface.py`. **Tests:** `macf/tests/test_pd_interface.py`. **Example:** `examples/pd_declaration.json`.

## 1. Identity, names and paths

**The card comes from the agent home, and only from it.**
- Every caller (the daemon, the channel, the command line, an outer tier) names the agent's home explicitly and gets the card from `agent_card(agent_home)`.
- The name is `agent_identity.calling_card` (or `moniker`) in `<home>/.maceff/config.json`. The suffix is the first six characters of `<home>/.maceff_primary_agent.id`.
- No environment variable and no working directory are read [MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)].
- **Why it matters:** for a host-global agent, `get_agent_identity()` reads `MACEFF_AGENT_NAME` first. A session that has the variable and a daemon started by the outer tier, which does not, would name different sockets for the same agent.
- A home that names no agent raises `IdentityError`, and the daemon refuses to start. The rendered outer-tier unit passes the home, `python -m macf.pd <agent home>`, because a daemon started there has no working directory in the agent's tree.

**One function names every surface:**

| Surface | Name for `TheHarborMaster@ee5cd8` |
|---|---|
| per-agent part (`pd_id`, which is `session_identifier`) | `TheHarborMaster_ee5cd8` |
| systemd user unit | `maceff_pd-TheHarborMaster_ee5cd8.service` |
| launchd label | `maceff_pd.TheHarborMaster_ee5cd8` |
| runtime directory | `$XDG_RUNTIME_DIR/maceff_pd/`, or `/tmp/maceff_pd-<uid>/` without one |
| control socket | `<runtime>/TheHarborMaster_ee5cd8.control.sock` |
| channel socket | `<runtime>/TheHarborMaster_ee5cd8.channel.sock` |
| daemon record | `<runtime>/TheHarborMaster_ee5cd8.json` |
| declaration | `<agent home>/.maceff/pd/declaration.json` |

- Every name carries `maceff_pd` [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)], and the agent too, because agents can share a login user.
- tmux silently rewrites `.` and `:`, and systemd reads `@` as a template instance. `session_identifier` replaces both; the measurements are in `macf/utils/identity.py`.
- **The runtime directory is private.** `ensure_runtime_dir` creates it with mode 0700. It refuses an existing one that is owned by another user or open to its group or others: in `/tmp`, anyone could have made it first.
- A socket path is checked against the kernel's limit before binding [MIS-0002-R129 (adapter_MUST_check_socket_path_length)].
- The declaration lives in the agent's home, never in the outer tier [MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)].

## 2. The declaration

JSON, validated closed: an unknown key is refused, because a key the daemon ignores is a setting its author believes is in force.

**A unit** [MIS-0002-R09 (declaration_MUST_state_unit_fields), MIS-0002-R59 (unit_MUST_declare_memory_limit), MIS-0002-R63 (unit_MUST_declare_privacy_grants)]:

| Field | Required | Meaning |
|---|---|---|
| `name` | yes | lower case, unique in the declaration |
| `kind` | no | `session` or `service` (default). At most one session: the unit a quiet window, a compaction and the waiting-on-a-person inference apply to |
| `command` | yes | argv list, started by the daemon as the unit's parent [MIS-0002-R12 (pd_MUST_start_units_itself)] |
| `account` | yes | the daemon's own user in step 1; another account is the operator's decision [MIS-0002-R78 (layer_MUST-NOT_widen_permissions)] |
| `restart` | yes | `always`, `on-failure` or `never` |
| `exit_codes` | no | `success` (default `[0]`) and `no_restart` (default `[78]`) |
| `liveness_interval_s` | yes | how often the unit writes its liveness event |
| `memory_limit_mb` | yes | enforced and checked in step 3 |
| `stop_grace_s` | no | seconds between SIGTERM and SIGKILL on a stop; default 10. A broker flushing its spool may need more |
| `environment` | no | the whole environment the unit gets |
| `optional` | no | never delays another unit [MIS-0002-R58 (optional_unit_MUST-NOT_delay_others)] |
| `privacy_grants` | no | macOS grants from a closed list: `local_network`, `accessibility`, `full_disk_access`, `keychain`, `automation:<bundle id>` |

**Placeholders.** A command or environment value may use `{agent_home}`, `{card}` and `{runtime_dir}`. The daemon fills them in when it renders the unit at start [MIS-0002-R13 (pd_MUST_render_env_at_start)], because the same agent's home differs between a host and a container. Any other placeholder is refused, so the environment stays the declared one [MIS-0002-R12 (pd_MUST_start_units_itself)].

**A schedule** is declared now, although step 2 runs it, so the format does not change under the later steps.
- **Missed-run policy:** no default; a schedule without one is refused [MIS-0002-R109 (CI_MUST_fail_schedule_without_policy)]. The policy is `skip`, `run_once`, `run_once_in_window` with its window, or `report_only` [MIS-0002-R25 (missed-run_policy_MUST_be_listed)].
- **Target:** `isolated` or a named agent's live session [MIS-0002-R29 (schedule_MUST_declare_target)].
- **Time limit:** `timeout_s` is required [MIS-0002-R36 (run_MUST_have_wall-clock_limit)].
- **The run** is one of two shapes:
  - `{"prompt_file", "allowed_tools"}`, a model turn whose permissions are settled when the schedule is created, so a run that meets a prompt fails instead of waiting [MIS-0002-R31 (schedule_MUST_settle_permission_at_creation), MIS-0002-R32 (run_MUST_fail_on_prompt)];
  - `{"command", "wake_when": "exit_code" | "stdout"}`, work that needs no judgment, which wakes the agent only when its condition holds [MIS-0002-R37 (no-judgment_work_SHOULD_skip_model_turn)].

**The agent-level fields:**
- `operator_channels`: the channel names whose events count as the operator's activity; every other name counts as not the operator [MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)].
- `notice_routes`: per notice source, `agent`, `operator`, `both` or `held_until_present` [MIS-0002-R42 (notice_source_MUST_be_routed)].
- `quiet_windows`: when the layer neither restarts nor compacts [MIS-0002-R50 (layer_MUST-NOT_act_in_quiet_window)].
- `keep_harness_idle_compaction`: `false` by default, so the harness's own idle compaction is turned off [MIS-0002-R126 (adapter_MUST_turn_off_harness_idle_compaction)].
- `wind_down`: the skill that winds the agent down and asks for its compaction through the control socket. Absent means only the operator may ask [MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)].

## 3. The events

All go to the agent's own event log; there is no second store [MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)].

| Event | Written by | Data |
|---|---|---|
| `pd_unit_alive` | the unit, at its interval | `agent`, `unit`, `pid`, `proc_start`, `interval_s`, `in_flight`, `waiting_on` |
| `pd_unit_state` | the daemon | `agent`, `unit`, `state` (one of the six of R20), `pid`, `proc_start`, `reason` |
| `pd_control` | the daemon | `agent`, `act`, `unit`, `asked_by` (`kind`, `card`), `peer` (`uid`, `pid`, `proc_start`), `reason` |

- **The unit writes its own liveness,** because a process that merely exists shows nothing about whether its loop runs [MIS-0002-R14 (unit_MUST_emit_liveness_events)]. The readout confirms the writer by `pid` and `proc_start` [MIS-0002-R15 (readout_MUST_probe_liveness)].
- **`in_flight`** counts work the unit has started and not finished, checked before any restart [MIS-0002-R49 (pd_MUST_check_work_in_flight)]. A unit that reports none is taken as idle, and the daemon records that it assumed so.
- **`waiting_on`** says what the unit waits on a person for [MIS-0002-R21 (pd_MUST_report_waiting_on_person)]. The daemon never restarts a unit for it [MIS-0002-R22 (layer_MUST-NOT_restart_waiting_unit)].
- **`asked_by` and `peer`.** `asked_by` is what the asker claimed. `peer` is what the kernel proved about the asking process [MIS-0002-R52 (control_act_MUST_name_who_asked)].
  - An act asked over the control socket (operator or wind-down) records both.
  - The daemon's own `policy`, and a `harness` compaction, record no peer.
- **For a harness compaction,** the harness detector's events (`harness_setting_changed`, `harness_compaction_detected`, `compaction_asked`, from #547 and #548) are the observation. The daemon's `pd_control` with `asked_by.kind` `harness` is the decision [MIS-0002-R127 (harness_compaction_MUST_be_recorded)].
- **`proc_start` is always `macf.notify.session.proc_start`:** ticks on Linux, the client's UTC asctime on macOS, compared through `verify_incarnation`.

## 4. The sockets

Two Unix sockets, so that each carries one shape and has one peer rule; never a network port [MIS-0002-R80 (pd_MUST-NOT_listen_on_network)].

- **Control**, request and response, one JSON object per line each way. The peer must be the daemon's own user. The request names its asker, recorded as claimed beside the peer the kernel proves.
  - `{"op": "status"}` returns each unit's state, pid, start time and since when.
  - `{"op": "start" | "stop" | "restart", "unit", "asked_by", "reason"}` acts on one unit. A stop from outside a session succeeds whatever gate the session enforces [MIS-0002-R48 (outside_stop_MUST_override_gates)].
  - `{"op": "compact", "asked_by", "reason"}` is accepted only from the operator or the declared wind-down [MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)].
  - Any unknown operation or field refuses the whole request, with `{"ok": false, "error": ...}`.
- **Channel**, a stream. The daemon writes closed notice records in the shape the MacEff channel defines (#545), and reads nothing. The peer must descend from the agent's live session [MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)].
- **The daemon record** holds `pid`, `proc_start` and `version`. It is written atomically after both sockets are bound, and every client checks its peer against it [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)].

## Decided on #555

1. **A unit under another account:** refused in step 1. An operator-owned grant file read by a privileged launcher goes to the operator as a proposal, with MIS-0004's per-agent broker user as the case.
2. **Agents sharing one login:** a control request names its asker, recorded as claimed beside the kernel-proven peer.
3. **The record keeps `version`;** #545 adds it to its closed record when it rebases.
4. **One start-time form,** `notify.session.proc_start`, everywhere; #564 moves the transcript monitor onto it.
5. **`session_identifier` names every surface;** #549 follows it.
6. **The package is `macf/pd`,** and the daemon runs as `python -m macf.pd <agent home>`.
