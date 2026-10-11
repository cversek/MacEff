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

**9 The Tray**
- What does the tray show, and for whom?
- How does one icon stand for several agents?
- What may the tray do, and what must it ask a primal daemon to do instead?
- How does the tray know an answer came from the agent's own daemon?

**10 The Declaration**
- Where does an agent's declaration live, and whose units may it declare?
- What must a unit state, and what takes a default?
- What refuses a declaration, and which account may a unit run as?
- How are schedules and quiet windows declared before anything runs them?
- Where does the daemon itself run, and what does each platform supply?

**11 The Events**
- Which events does the core write, and where do they go?
- What are a unit's states, and when is a unit running?
- What happens to the units when a daemon dies and the next one starts?
- Who writes a unit's liveness, and when is a unit overdue?
- How does a control act say who asked?

**12 The Daemon and Its Control Socket**
- How does an agent get exactly one daemon, and where does its identity come from?
- What does a daemon's start mark, and what happens when it stops?
- Where is the control socket, and what does a connection to it prove?
- What does the socket do, and what does it refuse?
- How is the daemon read from outside, and when is it believed?
- What happens to the units when a daemon dies?

**13 Not Yet Landed**
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
- **The daemon checks the channel the other way**: that the connecting process descends from the agent's live session, matched by pid and start time [MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)]. The user alone cannot tell the channel from any other command the agent runs, and a channel left running after its session ended fails because its session is no longer its ancestor. The check is built and tested now (`macf.notify.session.descends_from`). The daemon applies it once it serves the channel socket, which arrives with the notifier (13).

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

The transcript monitor makes these records today. Once the daemon supervises the session unit, its control record for a harness compaction names the harness in its `asked_by` (`Asker.kind == "harness"`), with no peer, because nobody requested it [MIS-0002-R127 (harness_compaction_MUST_be_recorded)]. That is still to come (13).

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

- **What it reads, per agent home:** the declaration; the daemon's record, probed by pid and start time through the interface's `verify_incarnation`; and each declared unit's last `pd_unit_alive`, aged against the cadence the unit itself published, by the rule the readout applies (11.2). It keeps no bound of its own [MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)].
- **Verdicts:** ALIVE, STALE (stamped, then stopped), GONE (the stamping process no longer exists), ABSENT (never stamped within the lookback), UNREADABLE (present but unparseable). Per home: UNREACHABLE when the home cannot be read, CHECK-FAILED when the watch cannot tell what to check. **Unknown is never healthy.**
- **It alerts independently** [MIS-0002-R75 (outside_watch_MUST_alert_independently)], through a command that holds its own credential, never an agent's channel, once per stretch.
- **Its one record is the alert log.** Each line carries its transitions and whether the push was delivered, and the open stretches are read back from the delivered lines. So a push that failed is sent again on the next pass, never lost, and there is no second file to disagree with the log.

---

## 8 What a Shared Container Shows You

In a container several agents share, you can see every agent's units and the container's budget, and change neither [MIS-0002-R62 (agent_MUST_see_shared_container)]. `python -m macf.pd.shared_view` lists them.

- **Your own units appear once your primal daemon publishes a summary of them** into your `agent/public/pd/units.json`: names, kinds, memory limits, restart rules, whether optional. Never your commands or environment. Only you write your public tree, and a reader refuses a summary owned by another account. **The daemon doesn't publish its summary yet, so every home, your own included, reads UNPUBLISHED;** the command only reads.
- **The summary is declaration facts only.** A unit's state written into a published file would be a second store of liveness, stale the moment its writer dies. When you need a peer's state, it comes from where it is live.
- **The budget** is the container's memory and processor limits, read from its cgroup: `memory.max`, `cpu.max`, and what the kernel cannot reclaim (anonymous and kernel memory, not the page cache). **Only the operator sets it**, in the deployment's compose files [MIS-0002-R103 (shared_budget_MUST_change_only_by_operator)], and no agent's declaration can carry it.
- **Unknown is never empty.** A home that published nothing is UNPUBLISHED, one whose summary does not parse is UNREADABLE, and a budget file that cannot be read is unknown.

If the container is near its limit and a peer's unit holds most of it, tell the operator. Don't touch the peer's unit [MIS-0002-R07 (pd_MUST-NOT_control_other_agents)].

---

## 9 The Tray

### 9.1 What it is

**The tray is optional** [MIS-0002-R67 (operator_MAY_run_tray)]. It is a menu-bar app the operator may run where the host has a desktop. The outer tier and every primal daemon run the same without it, and no part of the layer imports it [MIS-0002-R68 (layer_MUST-NOT_depend_on_tray)]. It is installed as the `tray` extra and run with `python -m macf.tray`. Where a host cannot show it, as on stock GNOME without an extension, the readout is to say so once it lands [MIS-0002-R73 (readout_MUST_say_tray_unavailable)]; until then nothing does.

### 9.2 One icon for every agent

**One icon stands for all the agents installed on the host**, with a menu entry per agent [MIS-0002-R69 (tray_MUST_show_icon_per_agent), as amended]. The agents are the ones the outer tier starts, found from their LaunchAgents (`maceff_pd.*`). Each is keyed by the calling card in its home's identity file, never by a label, a socket name or the environment.

**The icon shows the most urgent state among the agents**, and the menu names the agents that caused it [MIS-0002-R72 (tray_MUST_flag_waiting_on_person), as amended]. The order is:
1. failed;
2. unreachable (the agent's daemon did not answer, or its answer could not be trusted);
3. waiting on a person;
4. starting;
5. running and stopped.

The first three alert. A session that starts waiting on a person changes its own entry and, through the union, the icon.

**Glyphs.** There is one glyph per state, all drawn from one mark. They are monochrome template images at menu-bar size, black and transparency only, so the system tints them for light and dark bars. There are no letters or numbers, and the shape changes with the state, so color is never the only signal. Each agent's entry shows that agent's own logo beside its card.

### 9.3 What the tray may do

**The tray observes and asks; it never acts itself.**
- Each start, stop or restart goes to that agent's own primal daemon, as a control request that names the operator as the asker [MIS-0002-R70 (tray_MUST_act_through_pd)].
- It offers no compaction, which only the operator's own command or the declared wind-down may ask for.
- **It never types into a session** [MIS-0002-R71 (tray_MUST-NOT_type_into_session)].

**The operator asker is a claim.** On a shared login a socket's peer credentials cannot tell the operator's tray from another agent's process, so the control socket must establish the operator by its own means, never from the field alone. For step 1 the operator settled it on 2026-10-10, as 12.3 says: the asker is recorded beside the process the socket observed, as an attribution and never an authentication, and nothing over the socket gives a claimed operator more than any caller of the same login. Before compaction on request lands, the operator has to be established some other way (13).

**An answer counts only from the agent's own daemon.** The tray accepts an answer only from the socket peer that the daemon's record names, matched by pid and start time [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd), applied to the control socket]. A peer that cannot be checked makes the agent unreachable, never trusted.

---

## 10 The Declaration

### 10.1 Where it lives, and whose it is

An agent's declaration is one JSON file in its own home, `<agent home>/.maceff/pd/declaration.json`. Every managed unit and every schedule appears in it [MIS-0002-R08 (unit_MUST_be_declared)]. A process the declaration does not name is not supervised by the layer, however it was started.

**A declaration that names another agent is refused whole** [MIS-0002-R07 (pd_MUST-NOT_control_other_agents)]. The core is given its agent's calling card and compares it with the declaration's `agent`, so a declaration copied from another agent's home never starts that agent's units under this agent's name. Where the card comes from, the identity file in the agent's home and never an environment variable [MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)], is the daemon process's to read (12.1).

### 10.2 What a unit states

A unit names its command, the account it runs as, its restart policy, its liveness interval [MIS-0002-R09 (declaration_MUST_state_unit_fields)] and its memory limit [MIS-0002-R59 (unit_MUST_declare_memory_limit)]. Its exit-code contract, its privacy grants, its stop grace and its environment take defaults when it names none: exit 0 is success, exit 78 asks not to be restarted, and the grants are none. The fields, their values and their defaults are defined once, in `macf.pd.interface`, and described in `macf/docs/developer/primal_daemon_interface.md`. This policy does not restate them, so the two cannot disagree.

A declaration with one unit:

```json
{
  "version": 1,
  "agent": "ExampleAgent@abc123",
  "units": [
    {
      "name": "transcript-monitor",
      "command": ["/usr/local/bin/macf_tools", "transcript-monitor", "start"],
      "account": "example",
      "environment": {"MACEFF_AGENT_HOME_DIR": "{agent_home}"},
      "restart": "always",
      "liveness_interval_s": 30,
      "memory_limit_mb": 256
    }
  ]
}
```

- `agent` is the card in the home's identity file.
- `account` is the login the daemon itself runs as (10.3).
- `liveness_interval_s` is a promise the unit makes: it writes its liveness at least this often, and the core judges it by that promise (11.2).

**The core starts each unit itself, as the unit's parent, with the declared environment and nothing inherited** [MIS-0002-R12 (pd_MUST_start_units_itself)]. It renders that environment at each start, rather than reading files a persistent volume carried forward [MIS-0002-R13 (pd_MUST_render_env_at_start)]. Nothing inherited includes `PATH`, so a unit names its command by its absolute path, as the example does, or declares the `PATH` it needs. A unit that reads or writes the agent's event log declares `MACEFF_AGENT_HOME_DIR` as `{agent_home}`, which the core fills in at the start. Each unit leads a process group of its own, so a stop reaches every process the unit started.

### 10.3 Validation, and the account a unit runs as

**The declaration is validated closed.** An unknown key is refused, because a key the core ignores is a setting its author believes is in force. Loading has no side effects. A declaration that fails is refused whole and no unit starts from it, rather than the units that could be read: a partial start supervises a set nobody declared. A schedule that can never fire, by its cron or its window, is refused at load too, rather than found out when it falls due.

**Step 1 runs units only as the daemon's own account.** A unit naming another account refuses the whole declaration. Acting as another account takes a privilege, and a file the agent can write must not be where that privilege comes from [MIS-0002-R78 (layer_MUST-NOT_widen_permissions)]. Granting it is the operator's decision, made in a file the agent cannot write.

### 10.4 Schedules and quiet windows

Schedules are declared in the same file, although step 2 of MIS-0002's landing runs them, so that the format holds still while the later steps land. A schedule names its missed-run policy from a closed list, `skip`, `run_once`, `run_once_in_window` or `report_only` [MIS-0002-R25 (missed-run_policy_MUST_be_listed)], and there is no default: a schedule without one is refused when the declaration is read, and CI holds the model to that [MIS-0002-R109 (CI_MUST_fail_schedule_without_policy)]. A default would decide, for every schedule nobody thought about, what happens to the runs a downtime missed. A schedule also names its target, an isolated session or the live session of a named agent [MIS-0002-R29 (schedule_MUST_declare_target)].

`quiet_windows` lists the times in which the layer neither restarts nor compacts a session [MIS-0002-R50 (layer_MUST-NOT_act_in_quiet_window)]. A session unit's restart waits for the window's end, whether its own restart policy or a request asked for it. An asked restart is recorded when it arrives and carried out when the window ends. Until then the unit's status names the window's end, so whoever asked reads that the restart waits, not that it happened. A stop never waits [MIS-0002-R48 (outside_stop_MUST_override_gates)]. The window holds an operator's restart as well as the restart policy's, because it is the layer's own rule, declared by the agent, and not a gate the session enforces; a stop and then a start still get through, since a start does not consult the window. Windows are read in the declaration's timezone, which a declaration with windows must name, and one whose end comes before its start runs past midnight. A window that isn't a time of day is refused at load.

### 10.5 Where the daemon runs

**The daemon is the one thing a platform renders.** A declared unit needs no rendering of its own, because the core starts it as its child (10.2). Each supported platform supplies an adapter behind one interface, `macf.pd.adapter`, that renders and installs the daemon's outer tier: the LaunchAgent on macOS (3.1) and the systemd user unit on Linux (6.1). The core imports no platform code. CI fails when a supported platform has no adapter [MIS-0002-R10 (CI_MUST_fail_unrendered_unit)]. That is how this policy reads R10 while every unit is the daemon's child.

---

## 11 The Events

### 11.1 The core's events, one log

| Event | Written by | What it says |
|---|---|---|
| `pd_unit_alive` | the unit, at its declared interval | this pid, started at this time, is running its loop |
| `pd_unit_state` | the core | the unit entered one of the six states, and why |
| `pd_control` | the core | a start, stop or restart of a unit, who asked for it, and why |
| `pd_daemon_start` | the daemon | its life began, with its pid and start time, before it adopts or starts any unit |

All of them go to the agent's own event log, which is the only store the layer keeps: no status file and no ledger of runs beside it [MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)]. A second store is a second answer to the same question, and the two drift apart. The fields are in `macf.pd.interface`.

The six states are declared, starting, running, waiting on a person, failed and stopped [MIS-0002-R20 (unit_MUST_have_listed_state)]. A unit stays starting until its own first liveness event names the pid the core started. A fork that succeeded is not a running unit.

An event carries states, times and identities. It never carries file content from the agent's home [MIS-0002-R79 (layer_MUST-NOT_copy_home_content)].

**A unit outlives a daemon that dies, and the next daemon adopts it.** At boot the core reads each unit's last recorded state, back past any compaction or rotation as far as the previous daemon's start, since every unit that daemon left running was recorded after it. A unit recorded live, whose process is still that process by pid and start time, is adopted rather than started a second time, and the state event says it was carried. A unit whose pid now names another process is started fresh. An adopted unit is stopped through its process group, as one the core started is, and its first liveness is judged from its adoption, as a started unit's is from its start, so a unit that went silent while no daemon ran becomes overdue.

### 11.2 Liveness is the unit's own

**The unit writes its own liveness**, because a process that exists shows nothing about whether its loop runs [MIS-0002-R14 (unit_MUST_emit_liveness_events)]. The core only reads it.

**The unit publishes its interval, and the observer computes the bound from it**, as `service_supervision` requires, so a unit that changes its interval changes its own bound. A unit is overdue when its last liveness is older than three of the intervals it published, and an overdue unit is failed, not running. Three tolerates two missed writes. It is the core's constant, chosen in 2026-10 without a measurement of real write jitter, and is re-derived once units have run under load.

**The health verdict says alive only after a probe.** `macf.pd.health` confirms by pid and process start time that the process named in a unit's last liveness event is still that process before it calls the unit alive [MIS-0002-R15 (readout_MUST_probe_liveness)], because a pid can be reused. The start time has one stored form, `macf.notify.session.proc_start`, compared through `verify_incarnation`. It derives everything when asked and stores nothing. Its five verdicts are alive, stale, gone, absent and unreadable, and a liveness it cannot read is unreadable, never alive. It is the verdict the readout will print, and the outside watch (7.1) applies the same rule now, through `read_liveness`, so the two cannot disagree about a unit.

### 11.3 Who asked

Every start, stop and restart the core performs is a `pd_control` event naming who asked and why [MIS-0002-R52 (control_act_MUST_name_who_asked)]: the operator, the agent's declared wind-down, or the unit's own restart policy. An operator's act needs the process that asked, its user, pid and start time, and the core records it beside the asker, because the asker is a claim and the process is observed. The process is observed from the kernel's report on the control socket's connection (12.3).

---

## 12 The Daemon and Its Control Socket

### 12.1 One daemon per agent, and whose it is

`python -m macf.pd <agent home>` runs the agent's primal daemon. It takes its agent's calling card from the identity file in that home, never from an environment variable [MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)]. A variable is inherited by everything started below the shell that set it, and a client started from such a shell has taken another agent's name as its own. The daemon then loads the declaration (10.1), and wherever a unit's environment names the agent home, the card or the daemon's runtime directory, it fills in the values only it knows.

**One daemon per agent** [MIS-0002-R01 (agent_MUST_have_one_primal_daemon)]. Once its control socket is bound, the daemon writes a record beside it holding its pid, its process start time and a version. A second daemon for the same agent refuses to start while that record names a live process by pid and start time, or while something answers on the socket, whatever the record says: a record can go missing, as after a sweep of the runtime directory. A daemon that stops removes the socket and the record only while they are still its own, so one stopping late never removes a successor's. A record whose process is gone, or whose pid now belongs to another process, is stale and is replaced. The MacEff channel checks its peer against the same record [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)].

**A daemon's start bounds what it observed.** After writing its record, and before it adopts or starts any unit, the daemon writes `pd_daemon_start` with the record's fields and the agent, so a second daemon that is refused never writes one. What a daemon observes outside its units, such as a surface's state, holds only for its own life, so a reader folding those observations starts from the newest start. Unit state carries across a start, because the next daemon reads it to adopt the units still running (11.1).

On SIGTERM, SIGINT or SIGHUP the daemon removes its socket and its record and ends, and its units keep running for the next daemon to adopt (12.6). A restart through the outer tier, `launchctl kickstart -k` or `systemctl --user restart`, therefore restarts the daemon alone, as the operator ruled on 2026-10-10. Stopping every unit is its own act, which the daemon takes only when asked for it; no command line offers it yet (13). It exits with 75 when a daemon for the agent is already running and with 78 when the agent home can't be used, so an outer tier's log tells the two apart.

### 12.2 Where the socket is

The daemon listens on Unix sockets only, never on a network port [MIS-0002-R80 (pd_MUST-NOT_listen_on_network)]: the control socket here and, once the notifier lands, the channel socket of 1.3. Both live in the runtime directory, `$XDG_RUNTIME_DIR/maceff_pd/`, or `/tmp/maceff_pd-<uid>/` where that variable is unset, each named for the agent's card, so every path carries `maceff_pd` and the card [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)]. The daemon checks the socket path against the platform's length limit before binding, as the adapter does at install (3.1), with a message naming the path and the limit. Without the check, a path that's too long fails at bind with an error that names neither.

**The runtime directory must be private.** The daemon creates it with mode 0700, and refuses to start when an existing one belongs to another user or is open to group or others. Under `/tmp`, another local user could have made the directory first, and every socket in it would then be theirs to replace.

### 12.3 Who may connect, and what that proves

The control socket accepts a connection only from the daemon's own user, as the kernel reports it for the connection. **That is all the check proves.** On a login that several agents share, or an agent and its operator, the kernel can't tell them apart. So a request names its asker, and the daemon records that claim beside the user, pid and start time it observed [MIS-0002-R52 (control_act_MUST_name_who_asked)]. The claim is an attribution, not an authentication, until each agent runs under its own account, and nothing over the socket gives a claimed operator more than any caller of the same login.

A request may claim only the operator or the agent's wind-down. Which of the two it claims isn't checked against the declaration in step 1, and is recorded as any claim is. The restart policy and the harness ask from inside the daemon, so a request that claims either is refused with the reason, and nothing is done.

### 12.4 What it does, and what it refuses

- **`status`** returns each declared unit's state, pid, start time and when it entered that state.
- **`start`, `stop` and `restart`** act on one declared unit. A stop sends SIGTERM to the unit's process group and SIGKILL after its grace period, and it succeeds whatever gate the session enforces [MIS-0002-R48 (outside_stop_MUST_override_gates)]. It is how the operator takes back a session that a loop holds. An asked restart first lets the unit's work in flight drain, up to a timeout it names when it gives up [MIS-0002-R49 (pd_MUST_check_work_in_flight)].
- **A unit the declaration doesn't name is refused.** The daemon never starts, stops or signals another agent's units [MIS-0002-R07 (pd_MUST-NOT_control_other_agents)].
- **A malformed request, an unknown operation or an unknown field refuses the whole request**, and nothing is done.
- **A compaction is refused** in step 1. The layer never compacts a session on its own initiative [MIS-0002-R51 (layer_MUST-NOT_compact_on_own)], and compaction on request arrives with the session unit, accepted only from the operator or the agent's declared wind-down [MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)], and only once the operator is established some other way than a claim (9.3).

Each connection carries one request. A refusal says what was refused and why, and names this policy, `macf_tools policy navigate persistent_layer`, as `capability_boundaries` requires of every refusal.

### 12.5 Reading it from outside

**`macf_tools pd status`** shows each declared unit's state. It believes the daemon only after the check the MacEff channel makes of its peer [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)]: the record must name a live process by pid and start time, and the process answering the socket must be that one. Otherwise it reads each declared unit's last state and liveness from the event log, through the shared health verdict (11.2). Either way it says which source it used, and why. A session whose restart a quiet window holds shows the window's end (10.4).

### 12.6 A unit outlives a daemon that dies

The daemon starts its units as its children, but they don't die with it: the outer tier renders the daemon so that its exit leaves them running, as the LaunchAgent does with `AbandonProcessGroup` (3.1) and the systemd unit with `KillMode=process` (6.1). Taking every unit down with a daemon that crashed would drop their work in flight unasked, and leave the restart nothing to carry. The next daemon adopts the units that are still the processes it recorded (11.1). A daemon that ends on a signal leaves them running too, so its restart drops nothing; stopping every unit is its own act (12.1).

**Between a daemon's death and its restart, the units run unsupervised.** The window is the outer tier's restart delay. A unit whose process dies inside it isn't adopted, and the new daemon starts it as at any boot.

---

## 13 Not Yet Landed

Specified in MIS-0002 and arriving with their landing steps, each in the pull request that enforces it:
- **The rest of the primal daemon:** health derived from runs owed and done; compaction on request, once the operator is established some other way than a claim on the socket (9.3, 12.3); the harness's compactions in the daemon's own control records [MIS-0002-R127 (harness_compaction_MUST_be_recorded)] (2.2); and a command-line act that stops every unit, with the question of which asker a command line claims (12.1) (MIS-0002 §6.1 to §6.4, §6.7).
- **Schedules and the notifier,** including the keystroke fallback, the dark-channel event, and every producer of the operator's activity (MIS-0002 §6.5, §6.6, the rest of §6.14).
- **Mail and the rest of containers** (MIS-0002 §6.8, §6.9).
- **Adopting a session Claude Code's own daemon already hosts** [MIS-0002-R66 (pd_MUST_adopt_harness_supervisor)] (3.3). Until it lands, the core starts a declared session unit itself.

Until a section lands, the rules in force are the existing policies: `service_supervision`, `notification_delivery` and `amail`.

---

## Integration

- `notification_delivery`: what a notice may carry and what it licenses. The channel is a delivery transport and inherits every rule there.
- `capability_boundaries`: the channel is a new way for notices to enter a session, held to a socket and a peer check rather than to trust.
- `service_supervision`: the primal daemon is the supervisor this policy describes, for the units its agent declares.
- MIS-0002: the decision record, with each requirement's reason.

## Wiki-Links

[[notification_delivery]] [[supervision]]
