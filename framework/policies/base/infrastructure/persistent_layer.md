# Persistent Layer

**Type**: Infrastructure (long-lived processes and notices)
**Scope**: All agents (PA and SA), the deployments that run them, and the operator
**Status**: DRAFT — landing in steps
**Specified by**: MIS-0002 (`framework/mis/MIS-0002-persistent-layer.md`). Each rule below cites its requirement there; the reasons are in MIS-0002 §7.

---

## Purpose

MacEff's long-lived machinery grew one piece at a time, and most of it died without a word. MIS-0002 specifies one persistent layer instead: a **primal daemon** per agent, kept alive by the operating system's own service manager, starting, checking and scheduling that agent's managed units, and delivering its notices.

**This policy lands in steps, as MIS-0002 §12 plans.** A section exists here once the code that enforces it has landed with it, in the same pull request. Sections not yet written are listed at the end, so a reader knows what is coming and does not mistake an absent rule for permission.

**Core insight**: a notice delivered by typing into a session depends on reading a screen built for people, and every mail-clock failure on record was a failure to read one. A channel reads no screen.

---

## CEP Navigation Guide

**1 The MacEff Channel**
- How does a notice reach my live session, and why not by keystrokes?
- What may a channel event carry, and what must it never be taken as?
- How does the channel know it is talking to my primal daemon?
- How do I tell a MacEff notice from the operator's own channel?
- How is a notice's receipt recorded, given that Claude Code acknowledges nothing?
- Why does the channel offer no tools and relay no permission prompts?
- How is the channel installed and loaded?

**2 The Harness's Own Compactions**
- Who may compact my session, and what happens when the client compacts it on its own?
- How is the client's idle compaction turned off, and when is it kept?
- How do I tell, after the fact, who asked for a compaction?

**3 macOS**
- How does a primal daemon run on macOS, and under what name?
- Which privacy grants can a unit declare, and how is a denied grant told from a network fault?
- What happens to a session that Claude Code's own background daemon already runs?
- Why must a socket path be checked at install?

**4 Attach**
- How does attach find the session to attach to?
- What does the readout say when nothing can attach?

**5 Observation**
- Who may watch a session, and how does an onlooker get in?
- What does an onlooker see, and what is kept from it?
- How does the owner keep a stretch of work from an onlooker?
- How does an observation end, and who may end it?
- How does the agent know who is watching?

**6 Linux**
- How does a primal daemon run on Linux, and under what name?
- What happens to the units a daemon manages when the daemon exits?
- Who turns on linger, and what happens without it?

**7 The Outside Watch**
- What checks a primal daemon from outside the agents, and what does it read?
- What verdicts can it give, and how does it alert?
- Why does a failed alert get sent again?

**8 What a Shared Container Shows You**
- What can I see of the other agents in a shared container, and what can't I change?
- Where does the container's budget come from, and who sets it?

**9 Not Yet Landed**
- Which parts of the persistent layer are specified but not yet in this policy?

=== CEP_NAV_BOUNDARY ===

---

## 1 The MacEff Channel

### 1.1 What it is, and why it comes first

The **MacEff channel** is the Claude Code harness adapter for notices: a small MCP server that the session starts as a child process and that connects to the agent's primal daemon [MIS-0002-R112 (claude_code_adapter_MUST_be_maceff_channel)]. A notice it delivers arrives in the session as a channel event, which starts a turn when the session is idle.

The channel is the first path, not an alternative to the keystroke wake. Where it runs, notices go through it; keystrokes remain the marked fallback for a session whose channel is absent [MIS-0002-R104 (adapter_MUST_deliver_through_channel)] [MIS-0002-R105 (keystroke_wake_MUST_be_fallback_only)]. The fallback is wired by the notifier's step of the landing.

### 1.2 What a channel event carries

A channel event carries **a notice and nothing else**: the source's own fixed wording, a pointer to the store, and at most a count, as `notification_delivery` requires of every notice. Its metadata carries the notice's identifier, source, read time and sent time [MIS-0002-R114 (channel_event_MUST_carry_notice_metadata)].

**No text crosses from the daemon to the channel.** The daemon sends a closed record (a known source, an arrival identifier, an optional count, two times), and the channel rebuilds the notice through that source's factory. A record with an unknown source or any extra field is refused and the next one is still delivered. So nothing a sender chose can reach the session as an instruction, by construction rather than by care.

**What a notice licenses** is unchanged: one action, consulting the store it points at. It is never the operator's word and never consent.

### 1.3 Who the channel will talk to

- The channel reaches its primal daemon only through a local Unix socket, never a network port [MIS-0002-R113 (channel_MUST_connect_by_unix_socket)]. The socket lives in the per-user runtime directory named `maceff_pd`.
- **The channel checks that the listening peer is its own agent's primal daemon**: the same user, the pid the daemon published beside its socket, and that pid's process start time [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)]. Any process of the same user can bind a known path while the daemon is down, and a pid can be recycled. A peer that fails any of the three is refused, and the channel retries later.
- **The daemon checks the channel the other way**: that the connecting process descends from the agent's live session, matched by pid and start time [MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)]. The user alone cannot tell the channel from any other command the agent runs, and a channel left running after its session ended fails because its session is no longer its ancestor. The check is built and tested now (`macf.notify.session.descends_from`). The daemon applies it when the daemon lands.

### 1.4 Telling a MacEff notice from the operator

A MacEff notice is the persistent layer speaking, never the operator. **It never counts as the operator's activity** [MIS-0002-R106 (wake_MUST-NOT_count_as_operator_activity)]. Counting it would end a remote mode and clear idle while the operator is away, and the woken turn would run as though someone were at the keyboard.

The hooks tell the MacEff channel from the operator's channels by the channel's name, which the transport sets and no sender can forge [MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)]. Its events arrive as `plugin:maceff-channel:maceff`.

**Read the source only from the tag that opens the prompt.** Content sent through any channel can contain an opening channel tag of its own, unescaped, naming a different source. A hook that searches the whole prompt for a source can be fooled by it [MIS-0002-R121 (hooks_MUST_read_source_from_origin_or_opening_tag)]. `macf.utils.input_origin` is the one reader of a source, for both producers of the operator's activity: the prompt hook and the transcript monitor. A delivered entry's origin record names the same source, and is read first where it exists. `macf.channels.channel_tag` reads a MacEff notice's other attributes.

The rule for every producer of the operator's activity, with names checked against the agent's declaration, lands with the hooks step of MIS-0002. What is here now is the part the channel needs in order to ship safely.

### 1.5 Receipt

Claude Code acknowledges nothing to a channel, so the third time every notice carries, when it was received, comes from inside the session. When the session's prompt hook takes a MacEff channel event, it records an event (`notice_received`) naming the notice's identifier and the time the hook took it [MIS-0002-R120 (prompt_hook_MUST_record_notice_receipt)]. On a busy session that is when the client handed the event to the turn, which a long tool call can delay; that is the time recorded.

### 1.6 No tools, no permission relay

The channel is one-way. It offers no tools, so a session has no reply path through it, and it does not declare permission relay [MIS-0002-R117 (channel_MUST-NOT_relay_permissions)]. Permission prompts stay with the operator's own channel. A later MIS may add a relay through the primal daemon, with verdicts accepted only from an authenticated operator surface.

### 1.7 Installing and loading it

The channel ships as a Claude Code plugin, `maceff-channel`, from the marketplace in the MacEff repository [MIS-0002-R125 (channel_MUST_ship_as_plugin)]. A plugin is required because Claude Code's organization allowlist admits plugins only. Its command, `maceff-channel`, is installed with `macf`.

A channel not on Claude Code's allowlist loads only under the development flag, which asks a person to confirm at every start. So a deployment loads it through an organization allowlist or an official listing where it can [MIS-0002-R119 (channel_SHOULD_load_without_development_flag)]. A restart the primal daemon performs never waits on that confirmation; such a restart comes up on the keystroke fallback until a person starts the session with the channel. Where a deployment sets an organization allowlist, the list replaces Claude Code's default list, so it must also name the operator's own channels, or they stop loading after the next unattended restart.

**Test it the safe way.** A second Claude session under the same login inherits every plugin enabled for that login, and a second copy of the operator's messaging plugin takes the bot's connection from the first. Turn such plugins off in the test folder's project settings before starting a test session.

---

## 2 The Harness's Own Compactions

### 2.1 Turning off the client's idle compaction

A compaction ends the agent's working memory. The persistent layer compacts a session only when the operator or the agent's declared wind-down asks [MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)]. The harness can also compact a session on its own: Claude Code compacts an idle session about 54 minutes after its last request, once the context has passed a threshold.

**The harness adapter turns that off unless the declaration keeps it** [MIS-0002-R126 (adapter_MUST_turn_off_harness_idle_compaction)]. From Claude Code 2.1.290 the settings key `idleCompaction: false` stops the idle compaction alone, and leaves compaction at the context limit on. The declaration's `keep_harness_idle_compaction`, false by default, is the one way to keep it.

- `macf_tools claude-config idle-compaction status` reports the state, with the settings file it read. `off` sets the key and leaves every other key alone. `on` removes it, which returns the client to its default.
- On a client older than 2.1.290 the command refuses and names the version. That client ignores the key, so writing it there would claim a protection that does not exist.
- Each change is an event, `harness_setting_changed`.

**Check the version the session runs, not the one installed.** The launcher can move to a new version while a running session still maps the old one. A key that needs 2.1.290 protects only a session that runs it.

### 2.2 Recording who asked

**When the harness compacts a session that nobody asked to compact, the compaction is recorded with the harness as the asker** [MIS-0002-R127 (harness_compaction_MUST_be_recorded)]. The PreCompact hook's `trigger` cannot say this alone: under 2.1.289 an idle compaction reports `manual`, and under 2.1.290 it reports `auto`. The reliable mark is the client's own row after the boundary, a system row that begins "Compacted while idle".

- **The asks are recorded where they happen.**
  - An operator's typed `/compact` appears in the transcript as a command row, and is recorded as `compaction_asked` with the asker `operator`.
  - A compaction asked through `macf_tools inject compact` is recorded with the asker `wind_down`.
- **The client's idle row** is recorded as `harness_compaction_detected` with the asker `harness`.
- **The hook records `trigger` as the client sent it**, and `unknown` when the field is absent, never a guess.
- No event carries the content of the work, only who asked, how and when.

Until the primal daemon lands, the transcript monitor makes these records. The daemon's control record for a harness compaction then names the harness in its `asked_by` (`Asker.kind == "harness"`), with no peer, because nobody requested it.

---

## 3 macOS

### 3.1 The daemon as a LaunchAgent

**On macOS each primal daemon runs as a per-user LaunchAgent** [MIS-0002-R05 (macos_MUST_render_LaunchAgent)], in the user's GUI session (`LimitLoadToSessionType: Aqua`), never as a LaunchDaemon that runs as root on someone's behalf.

- **Its label is `maceff_pd.<id>`** [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)], where `<id>` is the calling card with `@` written as `_`: `IraMacEff@ee9a78` becomes `maceff_pd.IraMacEff_ee9a78`. Several agents can share one login, so every name carries the agent.
- **launchd is the outer tier here.** `KeepAlive` and `RunAtLoad` restart the daemon whenever it exits.
- **The identity never travels in the environment.** The program is `python -m macf.pd <agent home>`, and the daemon reads its card from the identity file in that home.
- **Install, remove and restart go through `launchctl bootstrap`, `bootout` and `kickstart`** against `gui/<uid>`. The legacy `load` and `unload` are not offered.
- **Removal finishes even when nothing is loaded.** A boot-out of a service launchd does not have exits 3 ("No such process"), which happens after a failed bootstrap, after a reboot outside the GUI session, or on a second removal. The removal counts that as done and removes the plist.
- **The units outlive the daemon.** `AbandonProcessGroup` keeps launchd from killing the daemon's process group when the daemon exits, so the session keeps running for the restarted daemon to find. Linux renders the same with `KillMode=process`.

**The daemon runs only while its user is logged in to the GUI.** That is the price of the grants: a unit outside the GUI session holds none of the user's. A Mac reached only over SSH, or sitting at the login window after a reboot, runs no daemon and none of the agent's units. On Linux the user unit starts at boot and outlives a logout, so an operator moving between the two should expect the difference.

**launchd does not rotate `StandardOutPath` or `StandardErrorPath`.** They are for what the daemon cannot log itself, such as a crash. A daemon that wrote a line per poll there would grow them without bound.

**Check the socket path at install** [MIS-0002-R129 (adapter_MUST_check_socket_path_length)]. A Unix socket path longer than the platform allows fails at bind with a bare error. On macOS the limit is 103 bytes (Linux: 107), and a long home path or runtime directory reaches it. The install refuses with the path and the limit.

### 3.2 Privacy grants

macOS attaches a privacy grant to the **responsible process**. A unit started by launchd does not hold what the terminal held, and its denial looks like an ordinary error. For example, the Local Network grant refuses a LAN connection with `EHOSTUNREACH` at once, while ping, which the grant does not cover, still answers.

- **Each unit declares the grants it needs** [MIS-0002-R63 (unit_MUST_declare_privacy_grants)], from a closed list: `local_network`, `accessibility`, `full_disk_access`, `keychain`, and `automation:<bundle id>` per target app. A misspelt grant fails at declaration, not as a silent missing grant at run time.
- **A denial is read as the grant it is.** An instant `EHOSTUNREACH` while ping answers is read as `local_network` denied. A timeout, a refusal or a slow unreachable host stays the network failure it is, never reported as a grant.
- **Still to come.** The install-time probe [MIS-0002-R64 (adapter_MUST_test_grants_at_install)] arrives with the installer. It will run from the launchd context, because a test from the terminal proves the terminal's grant, and since its runs can raise permission dialogs, only when a person is at the machine. The notice that names a denied grant [MIS-0002-R65 (denied_grant_MUST_raise_notice)] arrives with the notifier. Until then a denial is read, not announced.

### 3.3 Claude Code's own supervisor

Claude Code can run a session in the background under its own daemon (`claude --bg`, `/background`). **Where it already runs the agent's session, the primal daemon adopts that session** instead of starting a second supervisor over it [MIS-0002-R66 (pd_MUST_adopt_harness_supervisor)].

- **Recognise a hosted session by its sidecar's `kind: "bg"`, never by argv.** A respawned worker runs in a pre-started spare whose argv is generic, so the session's launch flags, its channels among them, are read from the client's job record (`respawnFlags`).
- **Adopt only when it is unambiguous.** Exactly one hosted session in the agent's home is adopted. Two or more are refused with their ids named, because picking by recency is a guess. With none, the daemon starts the session itself.
- **Act only through the client's own verbs.** Start and restart are `claude respawn <id>`, which brings back the same session id, with its channels. Stop is `claude stop <id>`, which keeps the conversation. **Never a signal:** a signalled worker ends as "done" and nothing brings it back.
- **The client's daemon is transient.** It starts on demand and exits when its last client goes, so its absence says nothing about whether a hosted session lives. Workers it leaves behind keep their sidecars and are found the same way.
- **The readout shows the hosted sessions** under Claude Code's daemon, with their channels, or `unknown` where the job record cannot be read, never "none".
- A sidecar's `status` is turn state, stamped at transitions. It never says a person is awaited; that inference is the readout's [MIS-0002-R21 (pd_MUST_report_waiting_on_person)].

---

## 4 Attach

### 4.1 Resolved from the primal daemon

**Attach by name resolves the session from the agent's primal daemon** [MIS-0002-R100 (attach_MUST_resolve_from_pd)], never from a tmux name. A name lookup cannot see a renamed session, cannot tell two similar names apart, and cannot see a session Claude Code's own daemon hosts.

1. Attach takes the session unit's pid from the daemon's status, and checks it against the recorded start time, so a recycled pid is refused.
2. A session hosted by Claude Code's daemon attaches with `claude attach <id>`.
3. A session under tmux attaches to its pane's session by exact name (`=name`).
4. A daemon that does not answer resolves nothing; there is no fallback to a name.

The operator may attach to any session without an invitation [MIS-0002-R81 (operator_MAY_attach_without_invitation)]. An onlooker is never given a keyboard.

**From the operator's side of a container**, the command also needs the way in (`ssh -t` or `docker exec -it -u <agent>`). The plan will add it once the daemon's status says where the daemon runs; until then it does not.

### 4.2 When nothing can attach

**Where nothing attachable hosts the session, the readout says so, with the reason** [MIS-0002-R101 (readout_MUST_say_nothing_attachable)]: a stopped or undeclared unit, a pid that changed, or a session in a plain terminal that neither tmux nor Claude Code's daemon hosts.

---

## 5 Observation

### 5.1 Invitations, and the acts that change them

**An onlooker sees a session only after the observed agent invites it** [MIS-0002-R82 (onlooker_MUST_be_invited)]. The invitation names the onlooker by calling card, never by login user [MIS-0002-R94 (invitation_MUST_name_card)], and an agent never invites an onlooker that runs in another container [MIS-0002-R111 (invitation_MUST-NOT_cross_containers)]. Between containers, collaboration stays with agent mail.

**Each invitation carries a secret.** On a shared login a socket's peer credentials cannot say which agent is reading, so the stream admits whoever presents the secret, and the secret reaches the onlooker through its own channel. The log keeps only the secret's SHA-256, so the record can be read without handing out the key. An onlooker that already has a live observation is not invited again; end it first.

**Every invitation, pause, resume and ending is an event in the observed agent's own log** [MIS-0002-R90 (observation_acts_MUST_be_events)], and the state is whatever the log folds to. It is kept nowhere else.

**Ending.**
- The observed agent or the onlooker may end an observation at any time [MIS-0002-R86 (either_party_MAY_end_observation)], and the operator may end any [MIS-0002-R87 (operator_MAY_end_observation)].
- Who is ending is established from the transport the request arrived on, never from a field in it, or an onlooker could end an observation as the operator.
- An invitation may carry a lease [MIS-0002-R88 (invitation_MAY_carry_lease)]. When it runs out, the log records the same ending event a party's ending records [MIS-0002-R89 (lease_end_MUST_match_party_end)]. A lapsed lease is refused at admission even before its end is logged, because the lease ends the invitation itself.

### 5.2 The stream

**The stream holds nothing from before its invitation** [MIS-0002-R84 (stream_MUST_start_at_invitation)]: it reads the transcript from the byte offset recorded with the invitation.

**It carries what a person watching the terminal would see, and less** where the more would be data the onlooker was not invited to see. It sends a typed prompt, a channel message's text with its source but never the chat's identifiers, the agent's own text, and each tool call by name with its stated purpose. A tool's result is a marker saying whether it failed, never its body. Thinking, hook output, skill text, peer messages and the client's housekeeping rows are not sent at all.

**An onlooker never types** [MIS-0002-R83 (onlooker_MUST-NOT_type)]. The socket is read for one handshake line and never again, so there is no input path to close. A connection that sends no handshake within five seconds is refused.

**The stream stops at once when the observation ends** [MIS-0002-R85 (stream_MUST_stop_at_end)]. The state is read before every frame, so an ending or a lapsed lease stops it before the next one. The stream is bound to the invitation it was admitted under. A new invitation for the same onlooker carries another secret, so an end and a re-invitation that both fall between two reads still end it.

**The pause.** Everything a session shows is in scope of an invitation, so the owner protects other people's records and credentials by pausing the stream before work that prints them [MIS-0002-R92 (owner_MAY_pause_stream)].
- **A pause records the transcript offset where it began, and the resume the offset where it ended.** The stream sends no row that starts inside that range, wherever its reads happen to fall. A pause and its resume can both come between two reads, and what was written between them is still withheld.
- **The onlooker sees the pause** [MIS-0002-R93 (onlooker_MUST_see_pause)]. When the stream reaches a pause it sends one frame saying the owner paused it, and one more when it passes the end. A stream opened after a pause sends what came before and after it, and marks the gap the same way.
- **A pause covers what is written from its offset on.** It cannot take back what was printed before it, which the onlooker may already have.
- **Offsets only grow.** A pause or a resume at an offset earlier than the last one recorded is refused, since a resume before its own pause would withhold nothing.
- **Resume only after the paused work is written.** The resume's offset is read when the resume is taken, so anything the paused work writes after that falls outside the range and goes out. A resume run beside the tool that prints, in the same turn, is too early. Resume once that tool's output is in the transcript.

### 5.3 Presence

**Presence is one record of each onlooker that watches and each operator surface that is present**, with a paused onlooker marked as paused, and a segment of the per-call line that shows it [MIS-0002-R91 (call_line_MUST_show_presence)]. **The per-call line carries it once the per-call hook calls `call_line`,** which comes with the primal daemon or in a small pull request of its own. Until then the line shows no presence.

- **A surface claims only what it can know.** A keyboard surface that can see its viewer says `attached` while someone is there. One that cannot detect its viewer says `enabled`, never `attached` [MIS-0002-R98 (presence_MUST_say_enabled_when_undetectable)]. A channel, which carries messages and no keyboard, says `reachable`, so an operator reachable by channel is told apart from one attached at a keyboard [MIS-0002-R102 (presence_SHOULD_show_reachable)]. Which keyboard surfaces set presence is judged per surface [MIS-0002-R97 (keyboard_surface_MUST_set_presence)].
- **Presence is derived, not stored.** It is folded from the agent's own event log: onlookers from the observation acts, surfaces from their recorded states. A copy kept elsewhere could drift from the acts or outlive its writer.
- **When the primal daemon is not alive, presence is unknown,** and the segment says so. It never shows a stale onlooker, and never "nobody".

---

## 6 Linux

### 6.1 The daemon as a systemd user unit

**On Linux each primal daemon runs as a systemd user unit** [MIS-0002-R03 (outer_tier_MUST_restart_pd)], named by the step 1 interface: `maceff_pd-<id>.service`, where `<id>` is the calling card with `@` written as `_` [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)].

- **The user's systemd is the outer tier.** `Restart=always` restarts the daemon on every exit, a clean one included. `StartLimitIntervalSec=0` sits in `[Unit]`, where current systemd reads it; in `[Service]` it is ignored, and the daemon would stay down after its fifth quick crash.
- **The unit holds nothing of the agent's** [MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)]: no environment, no declaration, no credential. Its program is `python -m macf.pd <agent home>`, and the daemon reads everything from that home.
- **The units outlive the daemon.** The daemon is the parent of every unit it manages, so they share its cgroup. With `KillMode=process` only the daemon is signalled when it exits; under systemd's default, a daemon crash would stop the session and every other unit with no drain and no regard for a quiet window. macOS renders the same with `AbandonProcessGroup` (3.1).
- **Linger is the operator's switch.** Without it the user's systemd, and the daemon with it, stops at the user's last logout. `linger_enabled` reports it, and says why when it cannot tell. Turning it on (`loginctl enable-linger`) is the operator's decision on the host, never the tool's.

---

## 7 The Outside Watch

### 7.1 A watch that does not share the daemon's fate

**Every primal daemon is checked from outside the agents** [MIS-0002-R74 (pd_MUST_have_outside_watch)], by its own process on its own timer, reading only what the agents wrote. A supervisor that shares a fate with its subject is not a supervisor.

- **What it reads, per agent home:** the declaration; the daemon's record, probed by pid and start time through the interface's `verify_incarnation`; and each declared unit's last `pd_unit_alive`, aged against the cadence the unit itself published. It keeps no bound of its own [MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)].
- **Verdicts:** ALIVE, STALE (stamped, then stopped), GONE (the stamping process no longer exists), ABSENT (never stamped within the lookback), UNREADABLE (present but unparseable). Per home: UNREACHABLE when the home cannot be read, CHECK-FAILED when the watch cannot tell what to check. **Unknown is never healthy.**
- **It alerts independently** [MIS-0002-R75 (outside_watch_MUST_alert_independently)], through a command that holds its own credential, never an agent's channel, once per stretch.
- **Its one record is the alert log.** Each line carries its transitions and whether the push was delivered, and the open stretches are read back from the delivered lines. So a push that failed is sent again on the next pass, never lost, and there is no second file to disagree with the log.

---

## 8 What a Shared Container Shows You

In a container several agents share, you can see every agent's units and the container's budget, and change neither [MIS-0002-R62 (agent_MUST_see_shared_container)]. `python -m macf.pd.shared_view` lists them.

- **Your own units appear once your primal daemon publishes a summary of them** into your `agent/public/pd/units.json`: names, kinds, memory limits, restart rules, whether optional. Never your commands or environment. Only you write your public tree, and a reader refuses a summary owned by another account. **Until the daemon lands, nothing publishes, so every home, your own included, reads UNPUBLISHED;** the command only reads.
- **The summary is declaration facts only.** A unit's state written into a published file would be a second store of liveness, stale the moment its writer dies. When you need a peer's state, it comes from where it is live.
- **The budget** is the container's memory and processor limits, read from its cgroup: `memory.max`, `cpu.max`, and what the kernel cannot reclaim (anonymous and kernel memory, not the page cache). **Only the operator sets it**, in the deployment's compose files [MIS-0002-R103 (shared_budget_MUST_change_only_by_operator)], and no agent's declaration can carry it.
- **Unknown is never empty.** A home that published nothing is UNPUBLISHED, one whose summary does not parse is UNREADABLE, and a budget file that cannot be read is unknown.

If the container is near its limit and a peer's unit holds most of it, tell the operator. Don't touch the peer's unit [MIS-0002-R07 (pd_MUST-NOT_control_other_agents)].

---

## 9 Not Yet Landed

Specified in MIS-0002 and arriving with their landing steps, each in the pull request that enforces it:
- **The primal daemon itself:** declarations, liveness events, health derived from runs, and outside control (MIS-0002 §6.1 to §6.4, §6.7).
- **Schedules and the notifier,** including the keystroke fallback, the dark-channel event, and every producer of the operator's activity (MIS-0002 §6.5, §6.6, the rest of §6.14).
- **Mail, the rest of containers, and the tray** (MIS-0002 §6.8, §6.9, §6.11).

Until a section lands, the rules in force are the existing policies: `service_supervision`, `notification_delivery` and `amail`.

---

## Integration

- `notification_delivery`: what a notice may carry and what it licenses. The channel is a delivery transport and inherits every rule there.
- `capability_boundaries`: the channel is a new way for notices to enter a session, held to a socket and a peer check rather than to trust.
- `service_supervision`: the primal daemon, when it lands, is the supervisor this policy describes.
- MIS-0002: the decision record, with each requirement's reason.

## Wiki-Links

[[notification_delivery]] [[supervision]]
