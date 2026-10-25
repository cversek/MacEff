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
- What does the channel tell the daemon when it attaches, and what happens to a notice source it leaves out?
- How do I tell a MacEff notice from the operator's own channel?
- How is a notice's receipt recorded, given that Claude Code acknowledges nothing?
- Why does the channel offer no tools and relay no permission prompts?
- How is the channel installed and loaded?
- Where do notices wait while the session is down, and what happens to mail that arrived while no daemon ran?
- When does the daemon type a wake instead, and what may it type?

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
- How do I attach by a short name, and what happens when it names several agents?
- How do I list who I can attach to, and what does an unknown field mean?
- How do I attach from my laptop to an agent on another machine or in a container?
- How do I set up tab completion for agent names?

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
- How does my Claude Code session itself run as a unit of my primal daemon, and how do I attach to it?
- What reports a session's liveness, given that an idle session has no work loop?
- How is a session moved from the legacy harness onto its daemon, and what shows the plan before anything changes?

**7 The Outside Watch**
- What checks a primal daemon from outside the agents, and what does it read?
- What verdicts can it give, and how does it alert?
- Why does a failed alert get sent again?

**8 What a Shared Container Shows You**
- What can I see of the other agents in a shared container, and what can't I change?
- Where does the container's budget come from, and who sets it?
- What happens when a step of the container's start fails?

**9 The Tray**
- What does the tray show, and for whom?
- How does one icon stand for several agents?
- What may the tray do, and what must it ask a primal daemon to do instead?
- How does the tray know an answer came from the agent's own daemon?

**10 The Declaration**
- Where does an agent's declaration live, and whose units may it declare?
- What must a unit state, and what takes a default?
- What am I told when a unit fails, and what stops a crash loop?
- What refuses a declaration, and which account may a unit run as?
- How are schedules and quiet windows declared before anything runs them?
- Where does the daemon itself run, and what does each platform supply?
- How do I schedule a wake or a check for myself, and what may each do?
- How does the operator consent to an entry I make, and how can it be loosened?
- How does a reminder or the daily brief the operator asked for reach them?
- How does a duty that falls due wake me?

**11 The Events**
- Which events does the core write, and where do they go?
- What are a unit's states, and when is a unit running?
- What happens to the units when a daemon dies and the next one starts?
- Who writes a unit's liveness, and when is a unit overdue?
- How does a control act say who asked?
- How do I subscribe to the layer's events, and what does each record carry?
- What happens when a subscriber falls behind, or reconnects after records it never saw?
- Which records can a subscriber trust to say what the layer did?
- Who may subscribe, and how does the operator silence or reroute the stream?

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

The channel is the first path, not an alternative to the keystroke wake. Where it runs, notices go through it; keystrokes remain the marked fallback for a session whose channel is absent [MIS-0002-R104 (adapter_MUST_deliver_through_channel)] [MIS-0002-R105 (keystroke_wake_MUST_be_fallback_only)]. **Today the fallback covers mail only** (1.9). Every other notice, the daemon's own and an entry's wake included (10.6), waits in the log for a channel to connect (1.8).

### 1.2 What a channel event carries

A channel event carries **a notice and nothing else**: the source's own fixed wording, a pointer to the store, and at most a count, as `notification_delivery` requires of every notice. Its metadata carries the notice's identifier, source, read time and sent time [MIS-0002-R114 (channel_event_MUST_carry_notice_metadata)].

**No text crosses from the daemon to the channel.** The daemon sends a closed record (a known source, an arrival identifier, an optional count, two times), and the channel rebuilds the notice through that source's factory. A record with an unknown source or any extra field is refused and the next one is still delivered. The channel says so on its error stream, and nothing tells the daemon, which has already recorded the notice delivered (1.8). So nothing a sender chose can reach the session as an instruction, by construction rather than by care.

**The sources the channel knows**, each added in code, never by a record that names it:
- `amail`: mail arrived. It carries the count as a scheduling hint, and its pointer is the broker's store.
- The daemon's notices about your own units:
  - `pd_limit_exceeded`: a unit is past its declared memory limit [MIS-0002-R60 (pd_MUST_notice_limit_exceeded)].
  - `pd_unit_failed`: a unit failed: it exited with a failing code, missed its liveness, or the operating system refused to run its command. Its id names the unit and its failures in a row. A unit the daemon declines to start before running anything raises none. See 10.2.
  - `pd_grant_denied`: a declared grant was denied [MIS-0002-R65 (denied_grant_MUST_raise_notice)].
  - `pd_carried`: what a restart or a compaction carried, changed and lost [MIS-0002-R47 (pd_MUST_report_carried_changed_lost)].
  - `pd_run_failed`: a scheduled run of yours failed, was killed at its limit, or couldn't start [MIS-0002-R32 (run_MUST_fail_on_prompt)]. See 10.4.
  - `pd_run_missed`: runs of a schedule whose missed-run policy is `report_only` were missed while your daemon was down, and none was run [MIS-0002-R25 (missed-run_policy_MUST_be_listed)]. See 10.4.
  - `pd_schedule_changed`: a schedule of yours changed since the operator last ran `pd install`, so your daemon isn't running it [MIS-0002-R33 (run_MUST-NOT_change_schedules)]. See 10.4.
  - `pd_entry_due`: an entry you set is due. The notice's id is the entry's, and the entry is your own note, never the operator's word.
  - `pd_duty_due`: a duty of yours became due soon or overdue. The event log's `duty_tier_crossed` entry names it, and one that crossed while no daemon ran is announced once at its start.
- The daemon's notice about your mail:
  - `pd_unread_mail`: mail has waited in your pickup box past your declared threshold [MIS-0002-R55 (unread_mail_MUST_raise_notice)]. See 1.11.

The daemon sources arrive as `macf-daemon` notices. Under `notification_delivery`'s masking rule (6) they are news of yourself, which you may not decline, as you may decline news of the world. That agent-side mask isn't applied today: neither the notifier nor the channel reads one, so you can decline no source, mail included. What can keep a notice from you is the operator's stream rules, which the notifier applies before it writes (1.8, 11.4). The daemon sources carry no count, and a record that gives one a count is refused. Their pointer sends you to `macf_tools pd status` and the event log. **The facts, which unit and how far past its limit, are in the log, never in the notice.**

**What a notice licenses** is unchanged: one action, consulting the store it points at. It is never the operator's word and never consent.

### 1.3 Who the channel will talk to

- The channel reaches its primal daemon only through a local Unix socket, never a network port [MIS-0002-R113 (channel_MUST_connect_by_unix_socket)]. The socket lives in the per-user runtime directory named `maceff_pd`.
- **The channel checks that the listening peer is its own agent's primal daemon**: the same user, the pid the daemon published beside its socket, and that pid's process start time [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)]. Any process of the same user can bind a known path while the daemon is down, and a pid can be recycled. A peer that fails any of the three is refused, and the channel retries later.
- **The daemon checks the channel the other way**: that the connecting process descends from the agent's live session, matched by pid and start time [MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)]. The user alone cannot tell the channel from any other command the agent runs, and a channel left running after its session ended fails because its session is no longer its ancestor. The daemon serves the channel socket and applies the check to every channel that connects, against the session unit's live process; with no session unit running, a channel is refused and connects again later, and its notices wait (1.8).
- **The channel says what it takes.** Right after it connects and has checked its peer, the channel writes one line, its hello: `{"hello": {"takes": [...]}}`, listing the notice sources its record accepts (1.2), read from the record itself so the two can't disagree [MIS-0002-R149 (pd_MUST_hold_sources_channel_did_not_declare)]. The daemon records it as `pd_channel_declared`, naming the sources, and sends that channel only notices of those sources, and of those only what the operator's rules deliver to `@channel` (11.4). The hello exists because after every upgrade one side runs older code than the other: before it, a channel that didn't know a source dropped its record after the daemon had logged it delivered, and the use trial's first wake was lost that way. A channel that sends no hello within two seconds stays attached and declares nothing, so it is sent nothing. A malformed hello, one left unfinished, or anything a channel writes after its hello breaks the protocol, and the daemon drops that channel, as it always dropped a channel that wrote.

### 1.4 Telling a MacEff notice from the operator

A MacEff notice is the persistent layer speaking, never the operator. **It never counts as the operator's activity** [MIS-0002-R106 (wake_MUST-NOT_count_as_operator_activity)]. Counting it would end a remote mode and clear idle while the operator is away, and the woken turn would run as though someone were at the keyboard.

The hooks tell the MacEff channel from the operator's channels by the channel's name, which the transport sets and no sender can forge [MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)]. Its events arrive as `plugin:maceff-channel:maceff`.

**Read the source only from the tag that opens the prompt.** Content sent through any channel can contain an opening channel tag of its own, unescaped, naming a different source. A hook that searches the whole prompt for a source can be fooled by it [MIS-0002-R121 (hooks_MUST_read_source_from_origin_or_opening_tag)]. `macf.utils.input_origin` is the one reader of a source, for both producers of the operator's activity: the prompt hook and the transcript monitor. A delivered entry's origin record names the same source, and is read first where it exists. `macf.channels.channel_tag` reads a MacEff notice's other attributes.

Every producer of the operator's activity counts a channel only by a name the agent's declaration lists as the operator's, and never the MacEff channel [MIS-0002-R107 (hooks_MUST_tell_channels_apart_by_name)]. `mode_system` states the rule for an agent that hasn't declared its list yet.

### 1.5 Receipt

Claude Code acknowledges nothing to a channel, so the third time every notice carries, when it was received, comes from inside the session. When the session's prompt hook takes a MacEff channel event, it records an event (`notice_received`) naming the notice's identifier and the time the hook took it [MIS-0002-R120 (prompt_hook_MUST_record_notice_receipt)]. On a busy session that is when the client handed the event to the turn, which a long tool call can delay; that is the time recorded.

**Receipt doesn't decide delivery.** The daemon counts a notice delivered when it writes it (1.8), and never reads `notice_received`. The two events share the notice's id: `pd_notice_delivered` carries it as `arrival_id`, and `notice_received` as `notice_id`. A notice with a `pd_notice_delivered` and no `notice_received` for its id was sent and never taken by the hook, and it isn't sent again.

**Nothing recovers such a notice on its own.** No part of the layer reads a missing receipt, and the channel tells the daemon nothing of a record it refused (1.2). The notice is still in the log, and you read it there: `macf_tools events query --event store_arrival_detected --event pd_notice_delivered --event notice_received --after 1d -v` prints each with its id, as `arrival_id` on the detection and the delivery and as `notice_id` on the receipt. The detection's `source` and `store` say where to look.

### 1.6 No tools, no permission relay

The channel is one-way. It offers no tools, so a session has no reply path through it, and it does not declare permission relay [MIS-0002-R117 (channel_MUST-NOT_relay_permissions)]. Permission prompts stay with the operator's own channel. A later MIS may add a relay through the primal daemon, with verdicts accepted only from an authenticated operator surface.

### 1.7 Installing and loading it

The channel ships as a Claude Code plugin, `maceff-channel`, from the marketplace in the MacEff repository [MIS-0002-R125 (channel_MUST_ship_as_plugin)]. A plugin is required because Claude Code's organization allowlist admits plugins only. Its command, `maceff-channel`, is installed with `macf`.

A channel not on Claude Code's allowlist loads only under the development flag, which asks a person to confirm at every start. So a deployment loads it through an organization allowlist or an official listing where it can [MIS-0002-R119 (channel_SHOULD_load_without_development_flag)]. A restart the primal daemon performs never waits on that confirmation; such a restart comes up on the keystroke fallback until a person starts the session with the channel. Where a deployment sets an organization allowlist, the list replaces Claude Code's default list, so it must also name the operator's own channels, or they stop loading after the next unattended restart.

**List every admitted channel in the declaration.** Where a deployment sets an organization allowlist (`allowedChannelPlugins` in Claude Code's managed settings), the agent's declaration lists every channel plugin the list admits, the operator's channels included, in `allowlisted_channels`, each as its plugin and marketplace [MIS-0002-R124 (allowlist_declaration_MUST_list_every_channel)]. The two are then compared:
- **`pd install` refuses** while they differ, and names each difference: a channel the list admits that the declaration leaves out, and a channel the declaration lists that the list leaves out, which won't load. Managed settings it can't read stop the install too, because a list that can't be read is not the same as no list.
- **The daemon compares again at start,** since managed settings can change after the install. Each difference goes to its stderr and into one `pd_allowlist_mismatch` event. It runs on: its units don't depend on the channels.
- **Where no managed settings set an allowlist,** there is nothing to compare, and `allowlisted_channels` may be left out. An allowlist that admits nothing stops every channel. A declaration says that's meant by listing `[]`, and otherwise it's named as a difference.
- **Only the managed settings files are read:** `/etc/claude-code/managed-settings.json`, and `/Library/Application Support/ClaudeCode/managed-settings.json` on macOS. Claude Code can also take managed settings from a macOS configuration profile, or from an organization's admin console. An allowlist set either way isn't seen here and reads as no allowlist, so a deployment that sets its list that way can't rely on this check.

**Test it the safe way.** A second Claude session under the same login inherits every plugin enabled for that login, and a second copy of the operator's messaging plugin takes the bot's connection from the first. Turn such plugins off in the test folder's project settings before starting a test session.

---

### 1.8 The notifier: where notices wait

The primal daemon hosts the notifier, because it runs while the session is down, and a notifier inside the session is down exactly when a notice has to wait [MIS-0002-R43 (wake_MUST_use_notifier)].

**Your declaration names only routes that reach someone** [MIS-0002-R42 (notice_source_MUST_be_routed)]. `agent` is served for every notice source, through the MacEff channel or the keystroke fallback. `operator`, and the operator's half of `both`, is served only for `pd_unread_mail`, by the outside watch. `held_until_present` is served nowhere yet. A declaration that routes a source to `held_until_present`, or to `operator` for anything but unread mail, is refused at load, with the reason and the route that works, so a notice is never accepted and silently dropped. `both` for another source keeps its agent half, and the daemon says at start that the operator's half is unserved, so a half-served route never stops a daemon. **A notice the daemon raises itself needs no route.** `pd_carried`, `pd_entry_due`, `pd_duty_due`, `pd_run_failed`, `pd_run_missed`, `pd_unit_failed`, `pd_limit_exceeded`, `pd_schedule_changed`, `pd_grant_denied` and `pd_unread_mail` go to you when the declaration doesn't route them, as `agent` would send them, so a declaration rendered without routes still tells you what was carried after a restart. Every route that would send one elsewhere is refused at load, but `operator` for `pd_unread_mail`, so that is the one route that keeps a daemon notice from you. The one route a declaration must name is `pd_unread_mail`'s, and only when it sets a threshold (1.11). The operator's stream rules still apply to every notice (below). The repo owner ruled this on 2026-10-21, and on 2026-10-24 scoped R42 to it: the operator's routes for the rest, and `held_until_present`, go to a successor MIS, to be built once an operator bridge subscribes to the event stream (13).

- **It polls each source itself.** For each source the declaration routes to the agent (`notice_routes`, `agent` or `both`), the daemon reads the store's names, never its contents, and makes one detection per burst of arrivals [MIS-0002-R42 (notice_source_MUST_be_routed)]. A source routed only to the operator is not polled for the session, and a declared source the daemon has no poller for is said on its error stream, not ignored.
- **Mail is watched where the broker delivers it.** The `amail` source reads the agent's pickup box, `<handoff>/<agent>`, by the rule `amail list` uses, one key at a time: `handoff` and `agent` each from the agent's `.maceff/amail.json` when the file has it, otherwise from the daemon's environment (`MACF_AMAIL_HANDOFF`, default `/var/lib/amail/handoff`; `MACEFF_AGENT_NAME`) (`macf.amail.pickup`). A host's settings often name only the handoff, with the agent from the shell, so the two keys are never taken as a pair. The daemon says on its error stream which box it watches and how it found it, and warns when nothing named the box or the box doesn't exist. Once it watched a guessed `<home>/amail/pickup`, which no deployment creates, and saw no mail anywhere without a word. **What a deployment must provide:** a container's outer tier gives the daemon only identity variables, not `MACEFF_AGENT_NAME`. So each seat that runs a daemon needs an `amail.json` in its home naming `handoff` and `agent`, written at provisioning. Otherwise its daemon warns at start and detects no mail.
- **The log is where a notice waits.** Every detection is appended to the agent's event log (`store_arrival_detected`, from the notifier `pd`) before anything is sent, and every notice written to a channel is recorded (`pd_notice_delivered`). A detection with no delivery after it, and no `pd_notice_silenced` (below), is owed. A daemon that restarts reads that back, so a notice waits through a restart of the session or the daemon with nothing kept outside the log [MIS-0002-R41 (pd_MUST_hold_notices_while_down)].
- **A notice is held whatever its age.** Each daemon start appends one `pd_notices_owed` event, from the notifier `pd`, listing every notice it still owes with its source, id, count and read time. The next start reads the log back only as far as the newest of these, then adds what was detected after it and neither delivered nor silenced, so a notice owed over a weekend down is still delivered on Monday and the read-back is bounded by the time since the last start, not by the log's length. A log with no checkpoint yet, as at the first start after this version, reads back one day, once: a notice owed longer than that is owed no more. An entry's wake is the one exception, owed again by the scheduler (10.6). The checkpoint is a fold of the log, not a second store: it lists only what the log already says is owed.
- **A notice the daemon raises itself is owed once per thing.** A newer one replaces an older one still owed from the same source: per schedule for `pd_run_failed`, `pd_run_missed` and `pd_schedule_changed`, per unit for `pd_unit_failed`, per entry for `pd_entry_due`, and per source for the rest. A notice only points to the log, which keeps every event, so nothing is lost, and a schedule that failed every five minutes through a weekend comes back as one notice, not hundreds; a unit that crashed all weekend comes back as one notice whose id carries its failures in a row. Notices from a store, such as mail, are each owed.
- **Delivered means written.** A notice stops being owed once its record is written to the channel's socket and `pd_notice_delivered` is recorded. Nothing comes back from the channel. So a record the channel refuses (1.2), or an event the prompt hook never records (1.5), still reads delivered and isn't sent again, and nothing recovers it on its own: you read it from the log (1.5). A write that fails, because the channel went away, keeps the notice owed.
- **A notice the operator's rules keep from you is settled, not owed** [MIS-0002-R152 (operator_MUST_silence_and_reroute)]. Before writing a notice, the notifier asks the event stream's rules in force whether its source is delivered to `@channel`, your session (11.4). Where it isn't, the notice is recorded as `pd_notice_silenced` and owed no more, whether a channel is attached or not; a restart reads it back as settled, and taking the rule away later never delivers it.
- **A notice its own record can't carry is never owed.** Before it owes a notice it raises itself, the daemon checks the notice against its own copy of the channel's record, the one in the macf it runs, never the attached channel's hello. An id the record's pattern refuses is one that fails. One that fails isn't owed: the daemon says so on its error stream, and the event log keeps the facts. Whether the attached channel takes the source is a separate question, asked at delivery from that channel's hello, and a source it didn't declare is held, not dropped (below).
- **What waited while no daemon ran is announced once.** At its start the daemon gives one notice, a count with no names, for whatever already waits in a store, unless that same set was announced before. A source that adopted what it found without a word would lose exactly the mail that arrived while nothing watched.
- **It is written to the newest channel that declared its source.** Each owed notice goes out as one closed record (1.2), naming its source and carrying when the store was read and when the notice was sent; the session's prompt hook records when it was received (1.5) [MIS-0002-R38 (notice_MUST_name_source)] [MIS-0002-R39 (notice_MUST_carry_three_times)]. A channel that has gone away keeps the notice owed for the next one.
- **A source no attached channel declared is held** for a channel that declares it [MIS-0002-R149 (pd_MUST_hold_sources_channel_did_not_declare)]. It stays owed in the log, never logged delivered, and goes out when a channel whose hello names it attaches, typically your session's next start on the upgraded channel. Mail is the exception that can't wait that long: the keystroke fallback counts it per source (1.9). **Nothing alerts anyone while a source is held this way.** The outside watch alerts on a dark channel (1.10) and on a typed wake held too long by something in the pane (1.9), and a channel that is attached but doesn't take a source is neither. If one of the daemon's own notices, such as `pd_entry_due`, seems never to arrive, read the channel's `pd_channel_declared` for the sources it took, and the newest `pd_notices_owed` for what still waits.
- **Nothing is sent to say nothing changed.** A poll that finds no arrival produces nothing [MIS-0002-R46 (layer_MUST-NOT_report_no_change)].

### 1.9 The keystroke fallback

When no channel has taken the mail notices owed for a minute, the daemon types a wake into the session unit's own pane instead, unless the operator's rules keep mail from your session: a wake is delivery to `@channel` too, so silencing `amail` or `@channel`, or routing `amail` elsewhere, settles the mail notices as silenced and types nothing (11.4) [MIS-0002-R105 (keystroke_wake_MUST_be_fallback_only)] [MIS-0002-R43 (wake_MUST_use_notifier)]. **"No channel" is counted per source:** a channel that is attached but whose hello left mail out, or that sent no hello, is no channel for mail, so the wake is typed all the same and mail is never held forever behind a channel that can't take it [MIS-0002-R149 (pd_MUST_hold_sources_channel_did_not_declare)]. Today the fallback types for mail only; the daemon's own notices wait for a channel that declares them (1.8). The rules are the ones the mail clocks learned typing wakes before the daemon did:

- **Only fixed words and message ids** [MIS-0002-R77 (wake_MUST_carry_fixed_words_only)]. The wake opens with the wake words, and names every message waiting, in the broker's id shape only, oldest first, eight at most, then a count. An agent consumes by position, so naming only the newest loses the rest.
- **Only into an empty box of an idle session** [MIS-0002-R45 (keystroke_wake_MUST_need_empty_idle_box)], read from the screen and failing closed. The input box must be on screen with nothing but a faint suggestion in it. No dialog, menu or question may be below it, because the wake carries digits and a digit or an Enter selects an option. No turn may be running, read from its phrase or from the spinner alone. Only the box's own text counts as a wake in the prompt, never the echo of one already sent.
- **Recorded before it is typed**, through the framework's keystroke record, so neither producer of the operator's activity counts it [MIS-0002-R106 (wake_MUST-NOT_count_as_operator_activity)].
- **Enter only while the wake is still in the box**, at most three times, since an Enter that lands on a dialog the new turn raised would approve it. A wake counts as sent when it is typed, so a misread status never sends it twice; the turn's start is then looked for, and the log says whether it came (`pd_wake_turn`).
- **A refractory window, ten minutes unless your declaration's `wake_refractory_s` says otherwise**, in which arrivals wait for the next wake, and a daily cap of 48 wakes. The cap is the fallback's constant (`macf.pd.wake`), not a declaration field, so no declaration or pace changes it. Mail that arrives inside the window is recorded as a hold, with the reason `refractory` and the seconds left (`left_s`), so a late wake always has its reason in the log. A held wake (`pd_wake_held`) and a reached cap (`pd_wake_cap_reached`) are each recorded once, not on every poll.

**You pace the window yourself.** The ten minutes are a default, not a rule about you. Mail that can wait longer while you work can rest longer, and mail you need sooner can rest less:
- `macf_tools pd wake --refractory 5m --reason "<why>"` sets how long the wake rests after each wake. The window is measured at the next poll, so a shorter one holds at once. `--declared` goes back to your declaration's window, and `pd wake` alone shows the window in force and where it came from.
- **No pace goes under the floor**, your declaration's `wake_refractory_floor_s` when it names one. Only the declaration sets the floor, never the socket, and in a container root renders the declaration from `agents.yaml`. So you can lengthen the window, or shorten it down to the floor, and never past it.
- **No pace goes over the ceiling**, your declaration's `wake_refractory_ceiling_s`, which is 30 minutes unless it says otherwise. That's the watch's allowance for a held wake, below. Past it you'd go unwoken longer than a stuck wake may before the operator is told, so a long enough pace would mute your wake with nobody told. Only the declaration sets the ceiling, as it sets the floor. A pace is a finite number of seconds: `inf` is refused at the command line, at the socket and in the declaration, and a saved pace over the ceiling is held to it at the next start.
- **Each pace is recorded like every act** (12.3): who asked, why, and the process that asked, with no unit. It goes in `pd_wake_paced` as well, with the window it replaced, before the daemon answers.
- **A pace outlives the daemon.** The next daemon reads the newest `pd_wake_paced` back at its start and keeps it, saying on its error stream which pace it came from. A floor declared above it since then wins, and the daemon says that too.

A typed wake delivers the mail notices it covers, so a channel that connects later doesn't deliver them again.

**A wake held too long reaches the operator.**
- While a dialog, a draft, a running turn or the refractory window holds a wake, the fallback records a `pd_wake_held`, naming the agent and the reason, once per stretch and again only if the reason changes.
- The stretch ends with a sent wake (`pd_wake_sent`), or with `pd_wake_released` when you read your mail on your own meanwhile, or when a channel attaches and takes over the notices.
- If the newest of those is a hold, and its stretch began more than 30 minutes ago, the outside watch alerts the operator once, through its own credential (verdict `HELD`, subject `wake`). A dialog waits on a person, and nothing in your session can say so. The refractory window is your own pace, not something in your pane, so it never counts toward the 30 minutes and never alerts: a dialog after the window is measured from the dialog.
- **A dialog or draft hold keeps the screen it read.** The fallback saves the captured pane, escape codes and all, to `~/.maceff/wake_screens/`, private to you (the directory mode 0700, each file 0600), keeping the newest 20, and the hold names the file in `screen`. A saved screen never leaves this host, because it can show anything your session showed. A pane that could not be read at all still holds the wake as a dialog, failing closed, and the hold says `captured: false` instead.
- If you find your mail was announced late, look for a `pd_wake_held`: its reason says what held the wake, and a dialog's or a draft's `screen` shows what the fallback saw. If that screen doesn't show a dialog or a draft, the fallback misread it. Keep the file and tell the operator.

Still to come with step 2: the operator's routes for sources other than unread mail, and the sources besides mail (13).

### 1.10 A dark channel

A channel is **dark** when your session is running and no MacEff channel is attached to your daemon [MIS-0002-R115 (dark_channel_MUST_raise_event)]. It happens one of two ways:
- the channel dropped while the session kept running;
- it never attached within `channel_connect_s` of the session's start. `channel_connect_s` is a declaration field: set it where a channel is expected, and leave it unset where none is, so nothing is watched.

**A restart is not a dark channel.** The old incarnation's channel goes with it, and the new incarnation gets its own window.

The daemon derives this each pass and writes it to the event log only:
- one `pd_channel_dark`, with the reason, opens a stretch;
- one `pd_channel_back` closes it, when a channel attaches or the session restarts.

**The operator hears of it through the outside watch**, which reads those events and alerts once per stretch through its own credential (R75). A dark channel can't carry the news of itself, and the daemon has no other way to reach a person.

**What it means for you:** while your channel is dark, notices from your daemon wait (1.8). The keystroke fallback types a wake when it can (1.9). If you find a `pd_channel_dark` with no `pd_channel_back` after it, your notices aren't reaching you by channel. Check that the MacEff channel plugin is loaded, and tell the operator if it isn't.

### 1.11 Mail left unread

Set `unread_mail_threshold_s` in your declaration to have your daemon notice mail you haven't read [MIS-0002-R55 (unread_mail_MUST_raise_notice)]. Mail is unread while it sits in your pickup box; reading it with `macf_tools amail list` takes it out. Leave the field unset and nothing is watched.

**Route it, or the declaration is refused.** A threshold needs `pd_unread_mail` in `notice_routes`:
- `agent` sends the notice to your session, held and delivered like any other (1.8);
- `operator` has the outside watch tell the operator;
- `both` does both.

**One notice per unread spell, not per message.** A spell opens when the oldest message in the box has waited past the threshold, and closes when the box is empty. More mail during a spell adds nothing; the next spell, after the box was emptied, gets its own notice. The daemon writes one `pd_unread_mail` when a spell opens and one `pd_unread_mail_cleared` when it closes, and nothing else is kept. A restarted daemon reads back whether a spell is open, so it never notices one twice.

**The wait counts only while your session runs.** A message's wait starts at its arrival or at the start of your current session, whichever is later, and no spell opens while your declared session is down. You can't read mail while you aren't running, and a notice about that would only teach its reader to ignore it. An agent with no session unit is counted on the wall clock.

**What to do with the notice:** read your mail. The event says how many messages waited, for how long, and which is the oldest.

**If reading your mail doesn't end the spell,** the oldest entry is one `amail list` couldn't take in: an unreadable pair, or one whose hash doesn't match its sidecar. Those are left in the box, so they hold the spell open. The event names the entry; tell the operator, who can inspect it and remove it.

**A spell is recorded before it's noticed.** The daemon raises the notice only once the opening event is in the log, and closes a spell only once the clearing event is. An event that fails to record is tried again next pass, so the log, the watch and a restarted daemon never disagree about whether a spell is open. One rare case remains: if the box was emptied and filled again while no daemon ran, a restarted daemon still holds the old spell, and the new one is noticed only after the box next empties.

## 2 The Harness's Own Compactions

### 2.1 Turning off the client's idle compaction

A compaction ends the agent's working memory. The persistent layer compacts a session only when the operator or the agent's declared wind-down asks [MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)]. The harness can also compact a session on its own: Claude Code compacts an idle session about 54 minutes after its last request, once the context has passed a threshold.

**The harness adapter turns that off unless the declaration keeps it** [MIS-0002-R126 (adapter_MUST_turn_off_harness_idle_compaction)]. From Claude Code 2.1.290 the settings key `idleCompaction: false` stops the idle compaction alone, and leaves compaction at the context limit on. The declaration's `keep_harness_idle_compaction`, false by default, is the one way to keep it. The session unit writes it into the project the session starts in, each time it starts the client, so a setting someone loosened by hand comes back off at the next start. A declaration it can't read keeps nothing, so the protection holds, and a client too old to have the key, or one it can't find, is said on the unit's error stream and the session starts anyway. Before 2026-10-21 nothing called it: the switch existed only as `claude-config idle-compaction`.

- `macf_tools claude-config idle-compaction status` reports the state, with the settings file it read and where that project came from. `off` sets the key and leaves every other key alone. `on` removes it, which returns the client to its default.
- **All three act on the project the session starts in, wherever they're run:** the session unit's `--project-dir`, then the harness's installed project. Only where neither names one do they fall back to the lookup by `CLAUDE_PROJECT_DIR`, git root and working directory, and they say so. Run from inside another checkout, that lookup would otherwise name the checkout's settings, which the session never reads.
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

The transcript monitor makes these records. **The primal daemon turns the monitor's `harness_compaction_detected` into a control act of its own,** `compact` on its session unit, naming the harness in its `asked_by` (`Asker.kind == "harness"`), with no peer, because nobody requested it [MIS-0002-R127 (harness_compaction_MUST_be_recorded)]. The monitor's event is the observation, and the daemon's record is the decision. It reads the event in the same tail of the agent's log that credits liveness, which starts at the log's end when the daemon starts. So a compaction made while no daemon runs is recorded by the monitor alone. A declaration with no session unit has no session of the daemon's to name, so nothing is recorded.

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
- **`pd install` tests each declared grant from the launchd context** [MIS-0002-R64 (adapter_MUST_test_grants_at_install)]. It loads a one-shot LaunchAgent that runs the daemon's own interpreter, because a grant attaches to the responsible process and a test from the terminal proves the terminal's grant. The job is loaded from the daemon's state directory, never `~/Library/LaunchAgents`, and booted out when it answers, so nothing of it starts at the next login. The probes read without asking: a TCP connect to the default gateway, with ping, for `local_network`; a read of the user's privacy database for `full_disk_access`; `AXIsProcessTrusted` for `accessibility`. `keychain` and `automation:` have no read that can't raise a permission dialog, so they are reported untested, and so is any probe that breaks; nothing is ever reported held that wasn't read as held. Each verdict is printed and recorded as a `pd_grant_probe` event. The probe runs only at install, where a person can answer a dialog, never at an unattended start.
- **A denied grant raises a notice** [MIS-0002-R65 (denied_grant_MUST_raise_notice)]. At each start the daemon reads the newest `pd_grant_probe` and owes the agent one `pd_grant_denied` notice for each declared grant it found denied; the notice's id names the grant. `pd install` records the probe before it starts the daemon, so the daemon it starts reads it. When the newest install couldn't test the grants, the daemon says so and raises no notice, rather than reading an older probe. It reaches you by default, or by `agent` in `notice_routes`. Granting it in System Settings and running `pd install` again records a new probe, which ends the notice.

### 3.3 Claude Code's own supervisor

Claude Code can run a session in the background under its own daemon (`claude --bg`, `/background`). **Where it already runs the agent's session, the primal daemon adopts that session** instead of starting a second supervisor over it [MIS-0002-R66 (pd_MUST_adopt_harness_supervisor)]. Before it starts the declared `session` unit, at boot or under the unit's restart policy, it asks what the client hosts. It adopts, starts or refuses by the decision in `macf/utils/client_daemon.py`, and records which in the unit's state event.

- **Recognise a hosted session by its sidecar's `kind: "bg"`, never by argv.** A respawned worker runs in a pre-started spare whose argv is generic, so the session's launch flags, its channels among them, are read from the client's job record (`respawnFlags`).
- **Adopt only when it is unambiguous.** Exactly one hosted session in the agent's home, or a directory below it, is adopted. Two or more are refused with their ids named, and the unit is recorded failed and not started, because picking by recency is a guess the operator makes. With none, the daemon starts the session itself.
- **An adopted session's liveness is its process.** The client's daemon supervises it, and it writes no liveness of its own, so the primal daemon judges it by pid and start time, as it does a unit carried from a previous daemon, and never fails it for silence.
- **Act only through the client's own verbs.** Start and restart are `claude respawn <job>`, which brings back the same session id, with its channels. Stop is `claude stop <job>`, which keeps the conversation. The verbs take the job's id, the session id's first eight characters as `claude --bg` prints them, and answer "No job matching" to the full session id. The daemon finds `claude` on the session unit's declared PATH, the environment the session runs in, because an installed daemon has its service manager's PATH, which on macOS is launchd's `/usr/bin:/bin:/usr/sbin:/sbin`. A session unit that relies on adoption should declare a PATH holding the client. When it isn't found, the unit is recorded failed with the PATH searched, and the hosted session is left alone. A missing client is not a refused stop, so nothing is signalled. **Never a signal:** a signalled worker ends as "done" and nothing brings it back. When the client can no longer respawn a session, because it pruned the finished job, the daemon decides again, and with nothing hosted starts the session itself. When the client refuses a stop, or accepts it and the worker outlives the unit's stop grace, the stop falls back to signals, because an outside stop must still stop [MIS-0002-R48 (outside_stop_MUST_override_gates)]. A respawn the client accepted is waited for, on each pass for up to 30 seconds, until the client lists the worker, so the session unit is never started beside it. A stop that lands during that wait holds: the worker is stopped through the client as soon as it is listed.
- **The client's daemon is transient.** It starts on demand and exits when its last client goes, so its absence says nothing about whether a hosted session lives. Workers it leaves behind keep their sidecars and are found the same way.
- **The readout shows the hosted sessions** under Claude Code's daemon, with their channels, or `unknown` where the job record cannot be read, never "none".
- A sidecar's `status` is turn state, stamped at transitions. It never says a person is awaited [MIS-0002-R21 (pd_MUST_report_waiting_on_person)]. For a session the daemon starts itself, the transcript monitor's beat says so (6.2). An adopted session writes no liveness, so the daemon reads what it waits on itself: every few seconds it asks the agent's event log, by the rule 6.2 gives, about the adopted session's own id, and moves the unit to waiting on a person and back.

---

## 4 Attach

### 4.1 Resolved from the primal daemon

**Attach by name resolves the session from the agent's primal daemon** [MIS-0002-R100 (attach_MUST_resolve_from_pd)], never from a tmux name. A name lookup cannot see a renamed session, cannot tell two similar names apart, and cannot see a session Claude Code's own daemon hosts.

1. Attach takes the session unit's pid from the daemon's status, and checks it against the recorded start time, so a recycled pid is refused.
2. A session hosted by Claude Code's daemon attaches with `claude attach <id>`.
3. A session under tmux attaches to its pane's session by exact name (`=name`).
4. A daemon that does not answer resolves nothing; there is no fallback to a name. The legacy harness's session is used only for an agent whose declaration has no session unit.
5. Attach names the attached window by the agent's calling card, with `automatic-rename` and `allow-rename` off, so a program in the session can't retitle it. A read-only attach (`--read-only`) changes nothing in the session it watches.

The session unit is the declaration's one unit of kind `session`, whatever its name. For an agent whose home isn't known here, such as a second agent on one login, the declaration can't be read, and the session is the live unit whose process parents a pane on the card's own tmux server, which is still the daemon's answer and not a name. The card's own server is asked first, then this account's other session-unit servers beside it, since a unit declared with a different `--agent` names its server after that; the pane is found by descent from the daemon's pid either way.

The operator may attach to any session without an invitation [MIS-0002-R81 (operator_MAY_attach_without_invitation)]. An onlooker is never given a keyboard.

**From another machine**, attach by name hands off to the remote's own attach over ssh (4.5). The remote resolves the session from its own daemon, so this section holds wherever the session runs.

### 4.2 When nothing can attach

**Where nothing attachable hosts the session, the readout says so, with the reason** [MIS-0002-R101 (readout_MUST_say_nothing_attachable)]: a stopped or undeclared unit, a pid that changed, or a session in a plain terminal that neither tmux nor Claude Code's daemon hosts.

### 4.3 Attach by name

**`macf_tools harness attach <name>` takes a short name and resolves it to one agent**, or says that the name means several, or none. With no name it attaches to the agent of the home it runs in. The name is matched against the roster (4.4) in three tiers, and the first tier with any hit decides:
1. an exact calling card, session identifier or uuid, with or without the `@` (`Lumen2MacEff@3f9a1c`, `Lumen2MacEff_3f9a1c`, `3f9a1c`, `@3f9a1c`). A shorter piece of a uuid is not exact;
2. an exact moniker or display name, ignoring case;
3. a prefix of a moniker or a display name, ignoring case (`lumen2`). Names match by their start, not anywhere inside.

A deployment's key for an agent, its account, and the account without `pa_` or `sa_` are aliases. **An alias counts only alongside the prefix hits**, so it resolves on its own only when nothing else starts with it: `lumen` lists every Lumen seat instead of quietly choosing the one whose key it is.

| what the name matches | on a terminal | not on a terminal |
|---|---|---|
| one agent | attaches | attaches |
| several | a numbered list (card, place, account, session kind, state), then a prompt, where a number, or a name that matches one of them, picks it | the list, then exit 2 |
| none | the nearest names, then exit 1 | the same |

Lists go to standard output, so a script can read the uuids, and each list shows them so the next call can be exact. `--card <card>` attaches to exactly that card on this endpoint, which is what a remote hand-off names (4.5). `--agent <slug>` still names a session identifier, and attaches to that session by its exact name when no roster row carries the card.

### 4.4 The roster: who you can attach to

**`macf_tools harness list` lists every agent you can attach to, here and on your declared remotes (4.5); `--json` prints the same as objects, and `--local` lists this endpoint alone.** Each entry carries the card, moniker, uuid, account, display name, session kind (`daemon` for a session unit, `legacy` for the old harness), state (`running`, `stopped` or `unknown`) and the place it is on. The table shows one line per agent; under a row whose card is unknown it says why, since that agent can't be named, and `--verbose` adds the reason for every unknown field and each row's detail. The command is read-only. It exits 0 when the listing is complete, and 1 when a source could not be read or a remote did not answer, naming which on the error stream.

- **On a host**, the agents come from the daemon records in your runtime directory, the installed legacy harness units, and the homes your own account owns. Other people's homes on the host are not listed at all, and neither is a home of yours with no agent config. One whose config is there but can't be read stays a row, with the reason.
- **In a container** (where `/etc/maceff/agents.yaml` declares the accounts), they come from each home's published units summary (8), or from the card in a home that has no summary. A seat's home is private to its account, so for a peer the card comes from the deployment instead: the account's `calling_card` in `agents.yaml` and the home's identity file, which the deployment writes root-owned and world-readable. An identity file that isn't root's, or whose uuid isn't six lowercase hex characters, gives that seat no card, with the reason, so one seat can't make a laptop refuse the whole remote (4.5). A seat's home that can't be read is listed, with the reason.
- **A card comes from the agent's home or its daemon, never from an environment variable** [MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)].
- **Unknown is never empty.** Every unknown field carries why it is unknown. A peer's state is `unknown`, because a peer's daemon answers only its own account.

### 4.5 Remotes: attaching from another machine

**You declare the places you attach to once, in your own config**: `$XDG_CONFIG_HOME/maceff/remotes.yaml`, else `~/.config/maceff/remotes.yaml`. It is never in an agent's home, because which machines a person reaches is that person's configuration.

```yaml
control: true               # iTerm2 control mode (tmux -CC) by default
remotes:
  - name: lab               # a host where you log in as yourself
    host: lab.example
    login: me
    macf_tools: /opt/macf/bin/macf_tools    # where a non-login shell's PATH lacks it
  - name: seats             # a container whose seats are reached as their own accounts
    host: lab.example
    port: 2224
    login: seat
    list_login: pa_first    # any one seat: it reads every home's public summary (8)
```

A file that can't be used is refused whole, naming what is wrong. `--control` and `--no-control` on `harness attach` override the declared `control`, which a remote's own entry may also set.

- **The roster of each remote** is one non-interactive `ssh -o BatchMode=yes` running the remote's `harness list --json --local`, all remotes at once, each bounded by a timeout (5 seconds for listing and attaching). `--local` keeps a remote with remotes of its own from asking them in turn. A remote that would prompt for a password, or whose host key you haven't accepted, answers "unreachable" rather than hanging.
- **A remote that doesn't answer is said, never dropped.** The listing names it with the reason and exits 1. A remote whose macf has no `harness list` is reported as too old, with the plain `ssh -t … harness attach` to type instead. A remote a version ahead still lists: fields this macf doesn't know are dropped.
- **The attach is handed off.** For an agent on a remote, `harness attach` runs `ssh -t` of the remote's own `harness attach --card <card>`, logging in as the seat's account where `login` is `seat`. Only the card crosses the wire. The remote resolves the session from its own daemon (4.1), so no socket path, pid or session name travels.
- **Nothing a remote says becomes an ssh option.** Each account and card in a remote's roster must be a legitimate name (an account matches `^[a-z_][a-z0-9_-]{0,31}$`), or the roster is refused whole. ssh is always given `-l <login>` and `--` before the host.
- **macf reads no credential.** ssh uses your own keys, agent and `~/.ssh/config`.
- **What a deployment must provide** for a seat to be reachable by name: a macf with `harness list`, and your key in each seat's `authorized_keys`.

For speed, let ssh reuse one connection per remote:

```
Host lab.example
    ControlMaster auto
    ControlPath ~/.ssh/cm-%r@%h:%p
    ControlPersist 10m
```

### 4.6 Completion

**`macf_tools completion zsh` or `macf_tools completion bash` prints a completion script.** In zsh, after `compinit`, add `source <(macf_tools completion zsh)` to `~/.zshrc`. macOS's own bash 3.2 can't source a process substitution, so there save the script to a file and source the file.

Commands and flags complete from a table taken from the parser when the script is printed. `harness attach <TAB>` offers cards, monikers and uuids from this endpoint and every remote, each remote bounded by a one-second timeout. A remote that doesn't answer in time adds nothing and costs no more than that second. zsh shows each name's place beside it.

---

## 5 Observation

### 5.1 Invitations, and the acts that change them

**An onlooker sees a session only after the observed agent invites it** [MIS-0002-R82 (onlooker_MUST_be_invited)]. The invitation names the onlooker by calling card, never by login user [MIS-0002-R94 (invitation_MUST_name_card)], and an agent never invites an onlooker that runs in another container [MIS-0002-R111 (invitation_MUST-NOT_cross_containers)]. Between containers, collaboration stays with agent mail.

**Each invitation carries a secret.** On a shared login a socket's peer credentials cannot say which agent is reading, so the stream admits whoever presents the secret, and the secret reaches the onlooker through its own channel. The log keeps only the secret's SHA-256, so the record can be read without handing out the key. An onlooker that already has a live observation is not invited again; end it first.

**Every invitation, pause, resume and ending is an event in the observed agent's own log** [MIS-0002-R90 (observation_acts_MUST_be_events)], and the state is whatever the log folds to. It is kept nowhere else.

**Ending.**
- The observed agent or the onlooker may end an observation at any time [MIS-0002-R86 (either_party_MAY_end_observation)], and the operator may end any [MIS-0002-R87 (operator_MAY_end_observation)].
- Who is ending is established from the transport the request arrived on, never from a field in it, or an onlooker could end an observation as the operator.
- An invitation may carry a lease [MIS-0002-R88 (invitation_MAY_carry_lease)]. When it runs out, the log records the same ending event a party's ending records, with `ended_by` set to `lease` [MIS-0002-R89 (lease_end_MUST_match_party_end)]. Your primal daemon writes that ending: about every 30 seconds it sweeps your log for leases that have run out, through the same record path every observation act takes [MIS-0002-R90 (observation_acts_MUST_be_events)]. With no daemon running, the ending is written the next time one does. A compaction writes it too: the carry ends a lease that ran out before the boundary, since the new cycle no longer holds that invitation and the daemon's sweep reads only the current cycle. A lapsed lease is refused at admission even before its end is logged, because the lease ends the invitation itself.

### 5.2 The stream

**The stream holds nothing from before its invitation** [MIS-0002-R84 (stream_MUST_start_at_invitation)]: it reads the transcript from the byte offset recorded with the invitation.

**It carries what a person watching the terminal would see, and less** where the more would be data the onlooker was not invited to see. It sends a typed prompt, a channel message's text with its source but never the chat's identifiers, the agent's own text, and each tool call by name with its stated purpose. A tool's result is a marker saying whether it failed, never its body. Thinking, hook output, skill text, peer messages and the client's housekeeping rows are not sent at all.

**An onlooker never types** [MIS-0002-R83 (onlooker_MUST-NOT_type)]. The socket is read for one handshake line and never again, so there is no input path to close. A connection that sends no handshake within five seconds is refused.

**An onlooker never receives an operator surface** [MIS-0002-R99 (onlooker_MUST-NOT_get_operator_surface)], a way to see and type into the session. Besides having no input path, the invitation names no attach target. A Remote Control session link opens the session's view and keyboard to anyone signed in to the account that owns it, so the stream puts a marker in its place, wherever it was written: a prompt, a channel message, the agent's text or a tool's stated purpose.
- **The limit is the login.** An onlooker that shares the operator's login, on the machine or on claude.ai, already holds the operator's surfaces through it, and nothing in the stream can withhold them. R99 holds between different logins; to such an onlooker, an invitation adds nothing the login hasn't given.

**The stream stops at once when the observation ends** [MIS-0002-R85 (stream_MUST_stop_at_end)]. The state is read before every frame, so an ending or a lapsed lease stops it before the next one. The stream is bound to the invitation it was admitted under. A new invitation for the same onlooker carries another secret, so an end and a re-invitation that both fall between two reads still end it.

**The pause.** Everything a session shows is in scope of an invitation, so the owner protects other people's records and credentials by pausing the stream before work that prints them [MIS-0002-R92 (owner_MAY_pause_stream)].
- **A pause records the transcript offset where it began, and the resume the offset where it ended.** The stream sends no row that starts inside that range, wherever its reads happen to fall. A pause and its resume can both come between two reads, and what was written between them is still withheld.
- **The onlooker sees the pause** [MIS-0002-R93 (onlooker_MUST_see_pause)]. When the stream reaches a pause it sends one frame saying the owner paused it, and one more when it passes the end. A stream opened after a pause sends what came before and after it, and marks the gap the same way.
- **A pause covers what is written from its offset on.** It cannot take back what was printed before it, which the onlooker may already have.
- **Offsets only grow.** A pause or a resume at an offset earlier than the last one recorded is refused, since a resume before its own pause would withhold nothing.
- **Resume only after the paused work is written.** The resume's offset is read when the resume is taken, so anything the paused work writes after that falls outside the range and goes out. A resume run beside the tool that prints, in the same turn, is too early. Resume once that tool's output is in the transcript.

### 5.3 Presence

**Presence is one record of each onlooker that watches and each operator surface that is present**, with a paused onlooker marked as paused, and a segment of the per-call line that shows it [MIS-0002-R91 (call_line_MUST_show_presence)]. **The per-call hook shows it for an agent that declares a primal daemon,** read from the cycle's own events. An agent with no declaration has no daemon to vouch for presence, so its line carries no segment rather than "unknown" on every call. The declaration is the test because it holds on every platform: a container under the start script has no unit file, and the daemon's record goes when the daemon stops. The daemon is alive when its record names a live process by pid and start time.

- **Open observations and present surfaces cross a compaction.** The carry re-asserts each open observation's invitation unchanged, then its pauses and resumes in order, and each surface's latest state since the newest daemon start, unless gone. A carried invitation keeps the cycle it was given in and is marked carried, because it is a consent and must never read as fresh. Its lease is an absolute time, so a compaction never extends it, and an ended or lapsed observation carries nothing.
- **A surface claims only what it can know.** A keyboard surface that can see its viewer says `attached` while someone is there. One that cannot detect its viewer says `enabled`, never `attached` [MIS-0002-R98 (presence_MUST_say_enabled_when_undetectable)]. A channel, which carries messages and no keyboard, says `reachable`, so an operator reachable by channel is told apart from one attached at a keyboard [MIS-0002-R102 (presence_SHOULD_show_reachable)]. Which keyboard surfaces set presence is judged per surface [MIS-0002-R97 (keyboard_surface_MUST_set_presence)].
- **Presence is derived, not stored.** It is folded from the agent's own event log: onlookers from the observation acts, surfaces from their recorded states. A copy kept elsewhere could drift from the acts or outlive its writer.
- **A row that won't parse costs only itself.** Other processes write these rows, so both folds skip one they can't read, with a line on stderr, and the carry keeps a row only once it folds, so it carries what the line showed. A failure nobody foresaw fails its own carry family, and the carry still writes its marker, so a compaction keeps its recovery output.
- **When the primal daemon is not alive, presence is unknown,** and the segment says so. It never shows a stale onlooker, and never "nobody".

---

## 6 Linux

### 6.1 The daemon as a systemd user unit

**On Linux each primal daemon runs as a systemd user unit** [MIS-0002-R03 (outer_tier_MUST_restart_pd)], named by the step 1 interface: `maceff_pd-<id>.service`, where `<id>` is the calling card with `@` written as `_` [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)].

- **The user's systemd is the outer tier.** `Restart=always` restarts the daemon on every exit, a clean one included. `StartLimitIntervalSec=0` sits in `[Unit]`, where current systemd reads it; in `[Service]` it is ignored, and the daemon would stay down after its fifth quick crash.
- **A daemon that can't start backs off, and is never given up on.** The delay between restarts stretches from 10 s to 60 s (`RestartSteps`, `RestartMaxDelaySec`), so a daemon that keeps exiting 75 or 78 tries once a minute, not every 10 s. Neither code stops the restarts. On 75 another daemon holds the agent, and this unit takes over when that one ends. 78 also covers start errors that clear by themselves. After fixing a declaration, `systemctl --user restart` starts it at once rather than at the next try.
  - systemd doesn't shorten the delay again after a healthy run: once a few restarts have happened, a crash waits the full minute (measured on systemd 259). That minute is the longest the units run unsupervised (12.6).
  - systemd before 254 ignores both keys and keeps the fixed 10 s.
- **The unit holds nothing of the agent's** [MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)]: no environment, no declaration, no credential. Its program is `python -m macf.pd <agent home>`, and the daemon reads everything from that home.
- **The units outlive the daemon.** The daemon is the parent of every unit it manages, so they share its cgroup. With `KillMode=process` only the daemon is signalled when it exits; under systemd's default, a daemon crash would stop the session and every other unit with no drain and no regard for a quiet window. macOS renders the same with `AbandonProcessGroup` (3.1).
- **Linger is the operator's switch.** Without it the user's systemd, and the daemon with it, stops at the user's last logout. `linger_enabled` reports it, and says why when it cannot tell. Turning it on (`loginctl enable-linger`) is the operator's decision on the host, never the tool's.

### 6.2 The session as a unit

**An agent's Claude Code session runs as its daemon's `session` unit through `macf_tools harness unit`**, which keeps the daemon the session's parent [MIS-0002-R12 (pd_MUST_start_units_itself)]. The legacy harness can't be that child: `tmux new-session` asks a tmux server to run the session, and the server detaches from whoever started it. The process the daemon started would end at once, while the session went on out of its reach.

- **The chain is primal daemon → wrapper → tmux server → `claude`.** The wrapper runs the agent's own tmux server in the foreground (`tmux -D`) as its child. It creates the agent's session there, running the harness child script, which runs `claude -c` with the declared channels. Only then does it turn the server's `exit-empty` on. From that point the session's end is the server's end, and the server's end is the unit's exit.

- **The session's window is named after the agent's calling card,** or after the session's name where that isn't the card's, and so is the title of a terminal attached to it. The server holds only that session, so it doesn't let the client set its own title, which is its version and names nobody. It also turns `allow-rename` off after the agent's own tmux config (`~/.tmux-<id>.conf`) is read, so a program's rename escape can't retitle the window either. A tmux too old to have `allow-set-title` says so at the unit's start; there the client can still set the pane's own title, and the window and terminal title still name the agent. Harness commands run in an agent's home name that agent from its calling card, even where a shell exports `MACEFF_AGENT_NAME` for the host's resident agent; the variable names the session only where no card resolves, or for an agent with no identity file of its own.

- **An outside stop reaches the session too** [MIS-0002-R48 (outside_stop_MUST_override_gates)]. tmux runs each pane in a process group of its own, so the daemon's stop of the unit's group reaches `claude` only through the server's hangup. The wrapper records the pane's process group when it creates the session, and once the server has gone it sends that group SIGTERM, then SIGKILL after 10 seconds. It records the group's leader's start time too, and before each signal confirms the group is still the session's: a group number is free again once its members have gone, and a leader under that number with another start is someone else's group, which is left alone. It returns only when the group is gone, so a restart never starts a second session beside one that outlived its unit. So **a session unit's `stop_grace_s` must exceed those 10 seconds**: otherwise the daemon's SIGKILL reaches the wrapper first, and nothing is left to stop the session. A wrapper killed outright can't do this, so each wrapper names its pane groups, with their leaders' start times, in a file in its private tmux directory (`pane_groups.json`). The next wrapper, finding no server on the socket, ends any group still running from that file before it starts a session, under the same start check. One window is left: the wrapper names a group once the pane has started its own session, which it waits up to 2 seconds for, so a wrapper killed outright within those seconds leaves that session unnamed, and an operator ends it by hand.
- **Restarts belong to the daemon alone.** There is no auto-restart loop inside the pane. When `claude` exits, the unit exits, and the daemon restarts it under the unit's declared policy and backoff. Every restart is then an event naming who acted. **A session unit's restart is `always`, and a declaration that says otherwise is refused by name**: the wrapper exits 0 however `claude` ends, so under `on-failure` or `never` an ended session would stay down.
- **The server has a socket of its own.** It lives in a private directory in the daemon's runtime directory, `<runtime>/<id>.tmux`, mode 0700, with tmux's default socket name inside. No other login's sessions can share the server, or keep it alive after the agent's session ends. The wrapper refuses a directory that is open to others, and a socket path the kernel would refuse [MIS-0002-R129 (adapter_MUST_check_socket_path_length)]. It also refuses to start while a server already answers on the socket, because a second one would double the session. **A refusal no restart can fix exits 78**: a missing project directory, a socket path too long, a directory open to others. 78 is in a unit's default `no_restart`, so the daemon records why and stops, instead of retrying with backoff forever. A server still answering exits 1, because that one can clear. When the server has gone, the wrapper removes the socket tmux leaves behind and its private directory.
- **Clients reach it through `TMUX_TMPDIR`.** `macf_tools harness attach` and `harness status` find the session unit's server first and the legacy harness's session second. When the session is the daemon's, `harness status` says the systemd harness isn't used, in place of its unit and init-system lines. `macf_tools env` names the daemon as the session's supervisor, once the daemon itself confirms it runs the unit on the pid the session was handed. The session's own variables are only its claim, and a claim the daemon doesn't confirm is shown as unconfirmed, with why. **A session that isn't its daemon's unit says so at its start, without being asked:** where the agent has a primal daemon declaration and the daemon doesn't confirm this session as its session unit, SessionStart adds one line saying the daemon won't restart it, or naming why its claim is unconfirmed. A confirmed session, and an agent with no daemon, hear nothing. That line is also the check for moving sessions onto their daemons: once every session has moved, no session says it. The mail clock reaches the pane through `TMUX_TMPDIR` in its declared environment, unchanged otherwise. Attach resolved from the daemon (4.1) finds the session's pane by its descent from the unit's process [MIS-0002-R100 (attach_MUST_resolve_from_pd)].
- **`macf_tools inject` still reaches the session.** It used to find its pane through the auto-restart supervisor's registry, and a session unit has no supervisor. So it falls back to its own pane: when it runs inside a session unit (the session variables are set) under tmux (`TMUX` and `TMUX_PANE`), it types into `TMUX_PANE` on the server `TMUX` names, and so does the follow-up prompt after a compaction. That follow-up counts as sent only once a turn has started: it presses Enter only while its own text is still in the input box, up to three times, and otherwise records that the text was typed but no turn started. An Enter that lands with the text can be taken into it, and an unsent prompt left in the box holds every wake behind it, since a wake types only into an empty box.
- **Clear `TMUX` when you name `TMUX_TMPDIR`.** tmux follows `TMUX` over `TMUX_TMPDIR`, so a client run from inside another tmux session asks that session's server instead. The wrapper and the attach helpers drop it.
- **End the legacy session before the unit starts.** A transcript monitor stands down when an older one already serves the transcript. The legacy session's monitor carries no session variables, so it writes no liveness for the unit, and the unit reads failed after three intervals. Only an interpreter running the monitor counts as one: a wrapper such as `timeout` that carries a monitor's arguments in its own isn't taken for it.
- **The declaration states the session's whole environment** (R12, R13). The wrapper adds only the context window, the terminal type, and the proxy attachment, which it probes as the legacy start script does. A declared project directory that is missing starts nothing, because `claude -c` would resume a different conversation anywhere else.

**A session's liveness comes from its transcript monitor** [MIS-0002-R14 (unit_MUST_emit_liveness_events)], as the operator decided on 2026-10-12. An idle session has no work loop. The monitor's loop reads the transcript and confirms the client process on every pass, so its beat means both are running. The wrapper hands the session `MACF_PD_SESSION_UNIT`, `MACF_PD_SESSION_LIVENESS_S` and `MACF_PD_SESSION_PID`, the last naming the wrapper, the process the daemon started. The monitor beats once per pass for that pid (11.2), and stops beating when its client ends. **Each beat also says when the session waits on a permission dialog** [MIS-0002-R21 (pd_MUST_report_waiting_on_person)]: the monitor reads the agent's event log for its own session, by the rule `macf_tools permissions pending` uses, where the newest deciding event is either a `permission_requested` or progress (a tool starting or finishing, a prompt, a session start or end, a compaction). The client can't say it waits while it waits, and the monitor runs outside it. The beat's `waiting_on` names the tool and the time the dialog opened, never the command, because it reaches `pd status`. The beat doesn't wait out its interval to say so: between beats it asks every few seconds whether what the session waits on has changed, and beats at once when it has, so a dialog that opens, and one that's answered, reach the daemon within seconds. The core moves the unit to waiting on a person and back, and never restarts it for the wait [MIS-0002-R22 (layer_MUST-NOT_restart_waiting_unit)]. A log that can't be read keeps the last answer, since reporting "not waiting" then would end a wait nobody answered. A defect in reading it does the same and is warned of by name, because an exception that escaped would end the beat, and the core would fail the live session for stale liveness and restart it. A denial writes no event of its own, so the session reads as waiting until its next prompt, tool call or end; a denial with a reply arrives as a prompt and ends the wait at once. Only a person answers the dialog; nothing in the layer does. The wrapper removes its own `MACF_PD_UNIT` and `MACF_PD_LIVENESS_S` from the session's environment: under names of their own, the variables can't be taken by any other process the session starts as its own unit's.

**Each beat also says when the session can't authenticate** [MIS-0002-R19 (auth_failure_MUST_read_failed)]. Claude Code writes a failed login into the transcript as an assistant entry marked as an API error, with the error `authentication_failed` ("Login expired", or the API's 401). The monitor reads it as the line arrives, and the beat's `auth_failed` carries what the client said until a later reply shows that a request went through. While it does, the core reads the session failed, with that text as the reason. It doesn't stop or restart the session:
- **A restart can't log in.** A person has to run `/login`.
- **A restarted session that nobody prompts makes no request,** so it would read healthy again while it still can't authenticate. On 2026-10-04 an expired login read as quiet for seven hours.

The session reads running again, as the same process, once a reply comes through. A daemon that starts while the session reads failed for its login adopts it like a live session, because it is still running. If its beat stops as well, the session has died, and it fails and restarts like any other.

### 6.3 Moving a session onto its daemon

**`macf_tools harness cutover` prints the plan for moving your session from the legacy harness onto your daemon's session unit, and changes nothing.** It reads this host and names only what is installed here:
- **the checks the move depends on:** a staged declaration (`<your declaration>.cutover`, or `--staged`) that validates, names you, declares a session unit, and gives it a `stop_grace_s` longer than the wrapper's 10 s pane grace (6.2); your daemon answering; your legacy harness unit and session; and any mail clock running beside the daemon's own;
- **the steps, in order:** stop the duplicate clocks, stop the legacy session, keep the current declaration as `<declaration>.pre-cutover`, install the staged one, restart the daemon, and watch the session unit come up;
- **each step's undo, and the rule for using them:** a failed move undoes only the steps it reached, last first. The install's undo puts the saved declaration back, restarts the daemon, ends the unit's tmux server, and removes the saved copy. Only then are the legacy harness and clocks started again, since the legacy start refuses a session name already held. A step that was never reached is never undone: its undo could restore what it never saved.
- **a saved declaration from an earlier attempt stops the plan.** `<declaration>.pre-cutover` may hold what the live one has since lost, or the reverse, so the move won't start until a person has compared the two and removed it.
- **this agent's transcript monitors whose session has ended are ended** with the legacy session. A monitor the old session's hooks started isn't a unit, so stopping the session doesn't always end it. Left running, it holds the transcript, the new session's monitor stands down, and the unit never beats.
- **notes for the person watching:** a new session that asks how to resume gets "continue", never "summarize"; scheduled jobs the old session made for itself lived in its process and need recreating once the move holds.

It exits 0 when every check holds and 1 otherwise. A session already running as its unit has nothing to move, and a host without systemd is told so rather than given systemd steps: a macOS move goes through launchd.

**Run the steps from a terminal outside the session they stop.** Stopping the legacy session ends the session you may be typing in, and the host's first move was finished only because a second copy of the remote session survived. Nothing else is stopped: the API proxy and the host's watches stay as they are, so the move changes one thing at a time.

**`--run` carries the plan out, from outside the session.** It refuses unless every check holds. Then it starts the move as a transient user unit, `maceff-cutover-<agent>`, which is no part of the session it stops, and prints the `tail -f` line for its log under `~/.maceff/logs/`, to follow from any terminal or a phone. The unit runs the printed steps exactly, in order, then waits up to 300 s for the daemon to report the session unit running. **The first failing command, or a session unit that isn't running in time, rolls the move back:** the undo of every step it reached runs, last step first, each command tried whatever came before. Ending a session that was already gone isn't a failure. What `--run` changes is your session, so on a seat it runs in an operator's window, with the operator's word for that move.

---

## 7 The Outside Watch

### 7.1 A watch that does not share the daemon's fate

**Every primal daemon is checked from outside the agents** [MIS-0002-R74 (pd_MUST_have_outside_watch)], by its own process on its own timer, reading only what the agents wrote. A supervisor that shares a fate with its subject is not a supervisor.

- **What it reads, per agent home:** the declaration; the daemon's record, probed by pid and start time through the interface's `verify_incarnation`; and each declared unit's last `pd_unit_alive`, aged against the cadence the unit itself published, by the rule the readout applies (11.2). It keeps no bound of its own [MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)].
- **Verdicts:** ALIVE, STALE (stamped, then stopped), GONE (the stamping process no longer exists), ABSENT (never stamped within the lookback), UNREADABLE (present but unparseable). Per home: UNREACHABLE when the home cannot be read, CHECK-FAILED when the watch cannot tell what to check. **Unknown is never healthy.**
- **It alerts independently** [MIS-0002-R75 (outside_watch_MUST_alert_independently)], through a command that holds its own credential, never an agent's channel, once per stretch.
- **Its one record is the alert log.** Each line carries its transitions and whether the push was delivered, and the open stretches are read back from the delivered lines. So a push that failed is sent again on the next pass, never lost, and there is no second file to disagree with the log.
- **It compares each named container's limits after every recreate** [MIS-0002-R61 (layer_MUST_check_limits_after_recreate)]. A recreate is where limits drift: a compose file edited but not applied, an override file left out of the command that recreated the container, or a `docker update` the files never learned of. List the compose-created containers in the watch config's `containers`.
  - **When it runs:** every pass. The watch reads the limits in force each time, so a `docker update` shows at once. It reads the declared limits from the container's own compose files (`macf.platform.container_limits`), and the `.env` compose reads beside the first, again whenever the container was recreated (a new id) or one of those files changed, and keeps them in `limits.json` in its state directory in between. That file is a cache of a comparison, not a record of liveness.
  - **Verdicts:** ALIVE when the limits match. DRIFTED when they differ, with each limit named and both values given. A check that can't be made (the container can't be inspected, or its files can't be read) is CHECK-FAILED under its own subject, `limits check`. Both subjects are reported on every pass, since a subject left out reads as no longer checked: `limits check` is ALIVE whenever the comparison was made, and while it fails, `limits` keeps its last verdict. So a failed check opens and recovers a stretch of its own, and a drift stretch stays open across it rather than closing and alerting twice.
  - **What to do with a DRIFTED alert:** recreate the container from all of its compose files, or bring the files into line with the limits you meant. Either closes the stretch at the next pass.

---

## 8 What a Shared Container Shows You

In a container several agents share, you can see every agent's units and the container's budget, and change neither [MIS-0002-R62 (agent_MUST_see_shared_container)]. `python -m macf.pd.shared_view` lists them. It takes its list of daemons from the deployment's own word, the declarations root renders under `/etc/maceff/pd/`, so a service account's daemon is counted wherever its home is, the mail broker's among them. A declared daemon that hasn't published reads "declared, no summary published" rather than vanishing. A declared account the reader can't look into is listed as UNREADABLE with its reason, and the others are still listed. Each summary is still read from where its own daemon writes it, after the owner check. Seats with no declaration yet are found by the scan of `/home`. A daemon the deployment declares publishes its summary even when its home has no `agent/public` tree.

- **Your primal daemon publishes a summary of your units** into your `agent/public/pd/units.json` each time it starts: names, kinds, memory limits, restart rules, whether optional. Never your commands or environment. Only you write your public tree, and a reader refuses a summary owned by another account. The command only reads.
- **A changed declaration is published by the restart that loads it.** The daemon reads its declaration only when it starts, so the summary it publishes is always the declaration it runs. A home with no `agent/public` gets none made, unless the deployment declares its daemon (the exception above). A summary that can't be written never stops the daemon: it says so on its error stream, and peers see no summary or the old one.
- **The view prints each summary's age.** The file outlives the daemon that wrote it, so a summary left by a stopped daemon would otherwise read as current. A running daemon's summary is as old as its last start, so an age of days means a daemon that has run that long or one that stopped. The summary can't tell which, since it holds declaration facts only.
- **The summary is declaration facts only.** A unit's state written into a published file would be a second store of liveness, stale the moment its writer dies. A peer's state lives with the peer's daemon and log, and there is no sanctioned way for you to read it there. `pd status` reads only the agent home it runs in. Each daemon's sockets sit in its own account's private runtime directory, and its control socket answers only that account's uid, and the operator's for the stream's rules (12.3). Its event stream needs a grant in the peer's declaration for any other uid [MIS-0002-R156 (subscriber_MUST_be_granted_agents)], and even then the socket's mode and the private directory keep a non-root uid from reaching it today (11.4). When you need a peer's state, ask the operator.
- **The budget** is the container's memory and processor limits, read from its cgroup: `memory.max`, `cpu.max`, and what the kernel cannot reclaim (anonymous and kernel memory, not the page cache). **Only the operator sets it**, in the deployment's compose files [MIS-0002-R103 (shared_budget_MUST_change_only_by_operator)], and no agent's declaration can carry it.
- **Unknown is never empty.** A home that published nothing is UNPUBLISHED, one whose summary does not parse is UNREADABLE, and a budget file that cannot be read is unknown.

If the container is near its limit and a peer's unit holds most of it, tell the operator. Don't touch the peer's unit [MIS-0002-R07 (pd_MUST-NOT_control_other_agents)].

**A failed start step never takes sshd down.** The container starts sshd before anything slow [MIS-0002-R57 (container_MUST_start_access_first)]. Each step after it runs on its own: a step that fails is logged as STEP FAILED, the steps that need it are logged as SKIPPED, and every other step still runs. The optional units, the policy index and the search service, come last, and neither waits on the other [MIS-0002-R58 (optional_unit_MUST-NOT_delay_others)]. The index builds in a thread of its own, under a 120 s timeout. The search service starts at once and opens the index on each query, so until the index is built a search comes back as an error rather than a result. The start log ends "Startup complete with N step(s) failed or skipped", naming them, and the container stays up so the operator can log in and repair it. If you find a tool missing or your mail not running after a recreate, look for that line in the container's log and tell the operator. Don't take it to mean the deployment is broken in some way nobody knows about.

---

## 9 The Tray

### 9.1 What it is

**The tray is optional** [MIS-0002-R67 (operator_MAY_run_tray)]. It is a menu-bar app the operator may run where the host has a desktop. The outer tier and every primal daemon run the same without it, and no part of the layer imports it [MIS-0002-R68 (layer_MUST-NOT_depend_on_tray)]. It is installed as the `tray` extra and run with `python -m macf.tray`.

**The tray has a LaunchAgent of its own, outside every agent** (`macf_tools pd tray install`, the repo owner's decision of 2026-10-20). A tray started from an agent's session dies with that session, and a unit of one agent's daemon would put the operator's view of every agent in that one daemon's failure domain, when the tray is how the operator sees a daemon in trouble. So there is one job per GUI user, `maceff_tray`, in the GUI session as an interactive app. launchd relaunches it after a crash or a kill, and leaves it down after Quit until the next login. Install refuses, saying why, where this host can't show the tray, and where the installing interpreter, run as launchd runs it, can't import the tray or imports another macf. `--plan` prints the steps and the plist and changes nothing; `pd tray uninstall` boots it out and removes the plist. Quit a tray started by hand before installing, or there are two icons.

**Whether a host can show it is checked, with the reason when it can't** (`macf.platform.tray_host`). The tray runs only on macOS so far. There it needs its extra, which is looked up and never imported, and a GUI session that belongs to the user: a Mac at the login window, reached over SSH, has nowhere to show it. The check sits outside the tray package so that asking never imports the tray. `pd status` prints its answer as its last line, and carries it in its JSON as `tray`, whatever the units' source, including for an agent with no daemon declared [MIS-0002-R73 (readout_MUST_say_tray_unavailable)].

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

An agent's declaration is one JSON file. On a host it is in the agent's own home, `<agent home>/.maceff/pd/declaration.json`. In a container it is written by the deployment, not the agent (below). Every managed unit and every schedule appears in it [MIS-0002-R08 (unit_MUST_be_declared)]. A process the declaration does not name is not supervised by the layer, however it was started.

**In a container, the deployment writes the declaration, and the agent can't.** A run executes as the agent, so a declaration the agent can write is one a run could rewrite before the daemon next starts, and with it the schedules [MIS-0002-R33 (run_MUST-NOT_change_schedules)].
- **Where you declare it:** as `primal_daemon` under the agent in `agents.yaml`. This is the declaration's body without `agent` or `version`, which the container fills in. A body the daemon would refuse is refused when `agents.yaml` loads.
- **Declare the agent's calling card beside it.** `calling_card` under the agent gives the name the daemon goes by (a letter, then up to 47 letters or digits). The id half is the first six characters of the agent's identity file. `agents.yaml` refuses `primal_daemon` without `calling_card` when it loads, naming the agent. A card without a daemon is allowed. A vanilla account can't declare one. **What a deployment must do:** add `calling_card` to every agent that declares `primal_daemon` before it takes this version, or `agents.yaml` won't load.
- **Start-up writes the card into the agent's home at every start,** as `agent_identity.calling_card` in `<agent home>/.maceff/config.json`, before any declaration renders. The daemon reads its identity from the home and never from the environment [MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)], so this is how the card reaches it. Every other key in the file stays, and so do its owner and mode. A missing file is created as the agent's, mode 0600, holding just the card. A home that already holds the same card is left untouched. An agent without `calling_card` gets nothing written.
- **A different card already in the home is refused, not overwritten.** The daemon's sockets and unit names are keyed by the agent's card, so a silent rename would strand them. When the home's `calling_card` or `moniker` differs from `agents.yaml`, or `config.json` can't be read, start-up logs the conflict by the agent's name with both values, and that agent gets no rendering, so no daemon. Every other agent still renders and starts. To resolve it, make `agents.yaml` and the home agree, then restart the container.
- **What start-up does:** at every start, it writes the declaration to `/etc/maceff/pd/<account>/declaration.json`, owned by root, mode 0644, in directories only root can write. An agent whose `primal_daemon` is removed has its old rendering removed too.
- **What the daemon reads:** when a rendering exists, every reader uses it, the daemon, `pd status` and the outside watch alike. The home copy isn't read. The daemon refuses a rendering that anyone but root could change (a symlink, another owner, or group or world write on the file or its directories), and exits 78.
- **A vanilla account can't declare one.** It gets no MacEff footprint, so nothing would start a daemon for it, and its schedules would have none to run them. `agents.yaml` refuses the pair when it loads, which container start does [MIS-0002-R11 (CI_MUST_fail_unhosted_schedule)]. No CI job loads a deployment's `agents.yaml`, since those files live outside this repository, so the check runs at start and in the model's tests.
- **A declaration only in an agent's home starts nothing in a container, and fails the start step.** Start-up logs, for each such agent, that its daemon was not started and why. After the agents declared in `agents.yaml` have started, the step fails, naming every agent declared only in its home, because no daemon runs their units or schedules. To give an agent a daemon, declare it in `agents.yaml`.
- **Inside a daemon, a schedule is hosted by construction:** the daemon builds a scheduler for exactly the schedules its declaration holds. A prompt run into the agent's own live session is hosted but not yet run, and it's recorded as not run (10.4). On a host, a declaration with no `pd install` behind it shows in `pd status`, not in CI.
- **On a host the agent runs as the operator's own login,** so file permissions can't keep a run from the declaration. Detection of a changed declaration is the host's half of R33.

**A service account can have a daemon of its own, declared the same way.** A service under `services` in `agents.yaml` declares `primal_daemon`, and a `calling_card` to go with it, which `agents.yaml` requires together.
- **Start-up treats it as it treats an agent's:** it renders the declaration to `/etc/maceff/pd/<account>/`, owned by root, and starts the daemon as the account, with the account's persisted directory (`/var/lib/<account>`) as its home.
- **It writes the account's identity there first:** the card's name from `calling_card`, and an id derived from the account and the deployment's id block, so the card holds across recreates and differs between deployments on one host. The identity files are root's. `.maceff` is the account's, since the daemon writes its event log there.
- **Each unit runs as the service account** (10.3), which `agents.yaml` checks when it loads.

**The mail broker's account is such a service, and in a container it must be** [MIS-0002-R53 (mail_broker_MUST_be_managed)].
- **Its daemon runs the broker and the inbound watcher as units, and the aged sweep as a schedule** [MIS-0002-R54 (periodic_mail_clock_MUST_be_schedule)]. The schedule runs `inbound sweep --quiet`, with `wake_when: stdout` and `missed_run: skip`. A clean sweep then has nothing to say, and a missed sweep is covered by the next one.
- **A stuck message is a failed run, recorded and shown, and nobody is alerted yet.** The run is in the event log, `pd status` shows the schedule's `FAILED` verdict with how the run ended, and `inbound health`, which runs the sweep itself, exits unhealthy. A failed run doesn't make the daemon unhealthy, though, and the outside watch has no verdict for one, so no alert reaches a person (13).
- **The watcher beats its liveness from its loop, and doesn't sweep.** Its 15 s drain is that unit's own loop, whose health is the unit's liveness, and a skipped drain owes nothing, since the next one reads the same spool. So it isn't a schedule.
- **A unit that runs `inbound watchdog` or `inbound sweep` is refused when `agents.yaml` loads.** A periodic check belongs in `schedules`, where its runs are recorded, and the daemon now notices the watcher's death, which was the watchdog's reason to exist.
- **What a deployment must do:** declare `services.amail_broker.primal_daemon` with those two units and that schedule before it takes this version of MacEff. `docs/arch_v0.3_named_agents/APPENDIX_A_YAML_SCHEMAS.md` shows the block.
  - The amail step no longer starts the broker, the watcher or a watchdog.
  - A deployment that configures the broker without the daemon fails that step by name, after the receiver has started, since otherwise mail would have no broker at all.
  - The receiver and any inbound tunnel are started by the amail step as before, since neither is a broker or a watcher.

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
- **`memory_limit_mb` is watched, not enforced** [MIS-0002-R60 (pd_MUST_notice_limit_exceeded)].
  - Every 30 s, starting 30 s after each start, the core reads the resident memory of the unit's whole process tree. It counts the tree, not just the process group, so a session unit's `claude` under its tmux server counts.
  - The first reading above the limit records `pd_unit_over_limit` with the unit, its use and its limit. A notice is owed to you and held like mail's (1.8).
  - The first reading back below records `pd_unit_back_under_limit`. Readings that don't cross record nothing.
  - **The unit keeps running.** If you get the notice, read `macf_tools pd status` and the event log, find what is growing, and tell the operator if you can't fix it. Don't restart the unit only to make the notice go away.

**A unit that fails is noticed, and restarted only by its policy.** A unit fails when it exits with a code its exit-code contract doesn't call success or no-restart, when it misses its liveness (11.2), or when the operating system refuses to run its command, as for a program that is missing or not executable. Each such failure is recorded as `pd_unit_state` with the reason, counts toward the restart backoff, and owes you the `pd_unit_failed` notice:
- **Its id is `<unit>:<failures in a row>:<epoch>`.** The count is the one the backoff grows with, cleared once the unit has run ten of its intervals. The notice carries nothing else; how each failure ended is in the log, `macf_tools events query --event pd_unit_state -v`.
- **Only the newest per unit is owed** (1.8). While a channel is attached each failure is delivered as it happens; while none is, a unit that crashed all weekend comes back as one notice, and its count says how many times in a row.
- **The session unit's own failure is noticed too,** when its liveness stops: the notice waits for the restarted session's channel and tells it that its predecessor failed, and how many times, beside the `pd_carried` report of what the restart lost (11.1). The session's wrapper exits 0 however `claude` ends (6.2), so a session that merely ended reads stopped and raises none.
- **The operator hears of it outside the session.** When the session is the unit that keeps failing, it is the one thing the notice can't reach in time. Each failure is also a `pd_unit_state` event the daemon writes itself, so a subscriber to the event stream (11.4), such as the tray or an operator bridge, takes it with `origin: daemon` and tells the operator. Neither subscriber is built yet. Until one is, nothing reliably tells a person: the outside watch (7.1) ages each unit's last liveness, and a unit that keeps restarting stamps afresh, so between failures it can read ALIVE.
- **Not noticed:** a stop someone asked for, an exit with a success or no-restart code, and a session failed for its login, which is still running and can't take a turn (6.2).
- **A start the daemon declines raises no notice yet.** The daemon declines a unit before running anything when a placeholder in it has no value, when the client hosts two or more sessions it could adopt (3.3), or when the client hosts the session and the daemon can't find `claude` on PATH to act on it. The unit is recorded `failed`, with a reason that begins `could not start:`, `not started:` or `not adopted:`, isn't counted toward the backoff, and stays down until someone starts it.
- **Where these show.** A declined unit reads `failed` and a unit that exited with a `no_restart` code reads `stopped` in `macf_tools pd status`, which prints the state and not the reason. The reason is in the unit's `pd_unit_state` event: `macf_tools events query --event pd_unit_state -v`.
- **Nothing ends a crash loop on its own.** A unit whose policy restarts it after a failure (`always` or `on-failure`) is restarted at a backoff that doubles to five minutes, for as long as it fails; there is no give-up state. What keeps a unit down is its declaration (an exit code in `no_restart`, or `restart: never`), a start the daemon declines, or a stop someone asks for. None of these ends a loop of ordinary failures. If the notice shows a loop, read why it fails, and tell the operator if you can't fix it.

**The core starts each unit itself, as the unit's parent, with the declared environment and nothing inherited** [MIS-0002-R12 (pd_MUST_start_units_itself)]. It renders that environment at each start, rather than reading files a persistent volume carried forward [MIS-0002-R13 (pd_MUST_render_env_at_start)]. Nothing inherited includes `PATH`, so a unit names its command by its absolute path, as the example does, or declares the `PATH` it needs. A unit that reads or writes the agent's event log declares `MACEFF_AGENT_HOME_DIR` as `{agent_home}`, which the core fills in at the start. Each unit leads a process group of its own, so a stop reaches every process the unit started. A member of the group that outlives its leader's exit, by ignoring SIGTERM, is killed with the group when the stop's grace ends, provided a member the core recorded by pid and start time still holds the group's id, so the signal can't reach a stranger who took a recycled id. A restart starts the new incarnation only once the old group is empty, so two copies never run side by side. A leader that exits on its own, crashed or done, takes its group with it the same way: what it left running is sent SIGTERM at once and SIGKILL at the unit's grace, as systemd ends a unit's cgroup and launchd a job's process group, and the unit reads stopped, or restarts, only once the group is empty. A session the client's own daemon hosts is left to that daemon (3.3). The reach ends at the process group: a child that leaves it, by `setsid()` or `setpgid()`, is beyond a stop, so a unit that daemonizes a worker must end that worker itself.

**A unit that crashes is restarted by its restart policy** [MIS-0002-R09 (declaration_MUST_state_unit_fields)]:
- **What counts as a failure.** An exit code outside the unit's `success` and `no_restart` lists, a unit that sends no liveness within three intervals of its start, a liveness that goes stale (11.2), and a command the operating system refuses to run. Each one records the unit failed and adds one to its failure count.
- **Who is restarted.** `always` and `on-failure` restart a failed unit. `always` also restarts a unit that exited with success, one second later. `never` restarts nothing. An exit code in `no_restart` stops the unit, and it stays down until someone starts it.
- **The backoff.** The first restart after a failure waits one second. Each further failure in a row doubles the wait, up to five minutes. These are the core's constants (`macf.pd.core`), not declaration fields.
- **The count clears** once the unit has run for ten of its liveness intervals since its last start, so a crash today doesn't inherit last week's backoff.
- **Failures have no cap.** Nothing limits how many times a failed unit is restarted: one that keeps failing is tried again every five minutes for as long as the daemon runs. A unit stays down only for an exit code in `no_restart`, `restart: never`, a start the daemon declines (above), or a stop someone asks for; none of them is a failure the backoff counts.
- **A waiting unit is never restarted for waiting** [MIS-0002-R22 (layer_MUST-NOT_restart_waiting_unit)], and a session's restart waits out a quiet window (10.4).

11.1 says where a crashing unit shows.

### 10.3 Validation, and the account a unit runs as

**The declaration is validated closed.** An unknown key is refused, because a key the core ignores is a setting its author believes is in force. Loading has no side effects. A declaration that fails is refused whole and no unit starts from it, rather than the units that could be read: a partial start supervises a set nobody declared. A schedule that can never fire, by its cron or its window, is refused at load too, rather than found out when it falls due.

**Step 1 runs units only as the daemon's own account.** For a service's daemon, that's the service account (10.1). A unit naming another account refuses the whole declaration. Acting as another account takes a privilege, and a file the agent can write must not be where that privilege comes from [MIS-0002-R78 (layer_MUST-NOT_widen_permissions)]. Granting it is the operator's decision, made in a file the agent cannot write.

### 10.4 Schedules and quiet windows

Schedules are declared in the same file, although step 2 of MIS-0002's landing runs them, so that the format holds still while the later steps land. A schedule names its missed-run policy from a closed list, `skip`, `run_once`, `run_once_in_window` or `report_only` [MIS-0002-R25 (missed-run_policy_MUST_be_listed)], and there is no default: a schedule without one is refused when the declaration is read, and CI holds the model to that [MIS-0002-R109 (CI_MUST_fail_schedule_without_policy)]. A default would decide, for every schedule nobody thought about, what happens to the runs a downtime missed. Every policy records the missed firings once (`pd_run_missed`, below), and a missed run that restarts a unit is never replayed under any of them:
- `skip` runs none of them.
- `report_only` runs none of them either, and tells you: one `pd_run_missed` notice for each missed spell (below).
- `run_once` runs the newest one as soon as the daemon is back.
- `run_once_in_window` runs the newest one at the next opening of the policy's own `window`, or at once when the daemon is back inside it, and not at all when the next regular firing comes first.

A schedule also names its target, an isolated session or its own agent's live session [MIS-0002-R29 (schedule_MUST_declare_target)]: `target` is `isolated` or the declaration's own `agent` card. Any other card is refused at load, with the target and the two values allowed, since one agent's schedule may never act in another's session (R07). A prompt run into the agent's own live session is accepted and recorded as not run yet.

**The daemon runs the command schedules** (`pd.scheduler`), and keeps nothing but the event log:
- **The next run moves on before the run starts.** `pd_run_started` names the firing the run is for and is written before the command starts, so a run that crashes the daemon is not run again for the same firing [MIS-0002-R26 (scheduler_MUST_advance_before_run)]. A started record that fails to write is warned about and the run still starts: failing closed would let a full disk stop every schedule, and the cost of failing open is that a daemon restarted during that run may run the same firing again. A run that starts late says how late [MIS-0002-R34 (late_run_MUST_state_lateness)].
- **A run is its process group.** It ends when the group is empty, not when its leader exits: members a leader leaves are sent SIGTERM, then SIGKILL after the grace, and the run is recorded ended once they have gone. Each run ends with `pd_run_done`, naming how.
- **Each run has a wall-clock limit,** its `timeout_s`, and a run past it has its process group sent SIGTERM, then SIGKILL after the grace, whether or not its leader is still alive [MIS-0002-R36 (run_MUST_have_wall-clock_limit)]. A daemon that stops does the same to every run in flight.
- **A run's environment is `PATH=/usr/bin:/bin` and `HOME`, plus what its `CommandRun` declares** in `environment`, rendered with the same placeholders as a unit's [MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)]. A declared `PATH` or `HOME` overrides the default. Nothing else of the daemon's environment reaches a run, so a command that needs a variable declares it, and the declaration is where an auditor finds it.
- **A downtime's missed firings are recorded once** (`pd_run_missed`), with the count and the policy that decided them. A daemon reads the newest record back when it starts, so a restart before the next run doesn't record them again. A missed run whose act restarts a unit is never replayed [MIS-0002-R27 (scheduler_MUST-NOT_replay_restart_runs)].
- **What the policy does with them.** `run_once` runs the newest missed firing when the daemon starts, and `run_once_in_window` runs it when the declared window next opens, unless the next regular run comes first. `skip` runs none and raises nothing: the next regular run covers it, as with the mail clock's sweep (10.1). **`report_only` runs none and tells you**, with the `pd_run_missed` notice, raised with the `pd_run_missed` record and so once per spell of missed firings, not once per pass or per restart [MIS-0002-R25 (missed-run_policy_MUST_be_listed)]. Its id is the schedule's name and the last firing missed, and only the newest per schedule is owed (1.8). Its pointer sends you to `macf_tools events query --event pd_run_missed`, which names the schedule, the count and the first and last firing, and to `macf_tools pd status`. Choose it for work you would rather decide about than have replayed blind. Until 2026-10-21 `report_only` behaved exactly as `skip`, since neither raised a notice; the maintainers ruled on #552 that it be served.
- **A run left in flight by a daemon that stopped is ended by the next one.** Its process group is stopped, SIGTERM then SIGKILL, if the group is still the run's: its leader is alive with the recorded start, or no process leads that number and members remain, since a number can't be reused while any member of its group lives. A leader there with another start means the number now names someone else's group, which is left alone. The run is recorded as abandoned, so nothing it held outlives the daemon that started it [MIS-0002-R28 (scheduler_MUST_release_leases_on_restart)].
- **A command decides whether the agent is woken.** Under `exit_code`, as `grep` reports, 0 means its condition holds, 1 means there is nothing to say, and anything else is a failed run. Under `stdout`, output means its condition holds, and a non-zero exit is a failed run. No model turn is spent on a run that has nothing to say [MIS-0002-R37 (no-judgment_work_SHOULD_skip_model_turn)]. Whether a wake is due is recorded with the run; delivering it waits on a notice source for it.
- **Every failed run raises the `pd_run_failed` notice:** a failing exit, a run killed at its limit, and a run that couldn't start. It's raised after the run's `pd_run_done` record, which says how the run ended. A run stopped on purpose raises none. It reaches you whether or not the declaration routes `pd_run_failed`, as every notice the daemon raises does (1.8). Without it, a check that keeps failing would look like one with nothing to say.
- **A schedule whose pass raises costs only itself.** The daemon skips it for that pass, and records `pd_schedule_pass_failed` with the error and says it on its error stream. It says so once while the same failure repeats, and again if the failure returns after a pass that went through. The other schedules and the daemon's units go on.
- **A prompt run into an isolated session runs Claude Code in print mode,** with the prompt file on its standard input, in a fresh working directory of its own, so nothing an earlier run left there loads.
  - **Its permissions are its schedule's `allowed_tools`, settled when the daemon took the declaration** [MIS-0002-R31 (schedule_MUST_settle_permission_at_creation)]. They're written from the declaration to the run's settings file before every run, so nothing a run grants itself outlives it. Only project settings are loaded besides it, from a directory that's empty, so none; no user or local settings load, and no MCP server.
  - **Anything else that would prompt is denied at once.** The default mode is `dontAsk`, and nobody answers prompts. Acts the client itself counts as read-only, such as `date`, run without any allow; anything that writes or reaches out needs one.
  - **A run that was denied anything fails, and raises the `pd_run_failed` notice** [MIS-0002-R32 (run_MUST_fail_on_prompt)]. Its record names the tools it was denied, never what the run said. A declaration with an isolated prompt run may leave `pd_run_failed` unrouted, which sends it to you (1.8). A route that would send it anywhere but your session is refused at load, as every such route for a daemon notice is, because a notice nobody hears is no notice.
  - **The client is found on the session unit's declared PATH,** as the core finds the session's own client, else on the daemon's, and the run gets that PATH. A daemon under launchd, or one systemd's linger starts before any login, gets a PATH that rarely holds `claude`, so a host that runs prompt schedules declares the session unit's PATH.
  - **A run's HOME is the agent's home,** so it uses the agent's own credentials and client state, and its user-level CLAUDE.md, which no settings flag controls. A CLAUDE.md that sends the agent to tools the schedule doesn't settle shows up as denied runs.
  - **A prompt run into the agent's own live session isn't run yet,** and nor is any prompt run whose client can't be found. The daemon says once which, and why, naming the PATH it searched.
- **The schedules are read when the daemon starts,** never from a run, so a run cannot create, change or delete one while its daemon runs [MIS-0002-R33 (run_MUST-NOT_change_schedules)]. Across a restart, it holds in a container because the deployment writes the declaration (10.1).
- **On a host, a schedule changed since `pd install` isn't run until it's installed again** [MIS-0002-R33 (run_MUST-NOT_change_schedules)]. A host's declaration sits in the agent's own home, where a run can write it. So `pd install`, which the operator runs, records each schedule's digest (`pd_declaration_installed`), taken over its declared form, the timezone its cron is read in, and a prompt run's prompt file, which sits in the home where a run could rewrite its own future instructions. The daemon reads that prompt once, when it starts and checks the digest, and feeds every run in its life from those bytes, so a rewrite takes effect only at the next start, where the check refuses it. It records before the service manager starts the daemon, since launchd starts one at load.
  - A daemon over a home declaration doesn't run a schedule that was added or changed since that record, nor any schedule when there's no record. It says so once (`pd_schedule_not_run`, so `pd status` shows it), says it on its error stream for the operator, who alone can accept it, and raises the `pd_schedule_changed` notice.
  - **Running `pd install` again accepts the change,** and the daemon reads it when it next starts.
  - **A command's script isn't digested,** only its path. A script kept in the agent's home can be rewritten by a run as the prompt file could, so a host keeps a schedule's script outside the home, or accepts that limit.
  - **The notice reaches you whether or not the declaration routes `pd_schedule_changed`,** as every notice the daemon raises does (1.8), unless the operator's stream rules keep it from `@channel` (11.4).
  - **This is detection, not prevention.** The event log is written as the same user, so a run could forge the install record. Prevention on a host would need the declaration kept from the agent's account, which is the operator's decision.

`quiet_windows` lists the times in which the layer neither restarts nor compacts a session [MIS-0002-R50 (layer_MUST-NOT_act_in_quiet_window)]. A session unit's restart waits for the window's end, whether its own restart policy or a request asked for it. An asked restart is recorded when it arrives and carried out when the window ends. Until then the unit's status names the window's end, so whoever asked reads that the restart waits, not that it happened. A stop never waits [MIS-0002-R48 (outside_stop_MUST_override_gates)]. The window holds an operator's restart as well as the restart policy's, because it is the layer's own rule, declared by the agent, and not a gate the session enforces; a stop and then a start still get through, since a start does not consult the window. Windows are read in the declaration's timezone, which a declaration with windows or schedules must name, and one whose end comes before its start runs past midnight. A window that isn't a time of day is refused at load.

### 10.5 Where the daemon runs

**The daemon is the one thing a platform renders.** A declared unit needs no rendering of its own, because the core starts it as its child (10.2). Each supported platform supplies an adapter behind one interface, `macf.pd.adapter`, that renders and installs the daemon's outer tier: the LaunchAgent on macOS (3.1) and the systemd user unit on Linux (6.1). The core imports no platform code. CI fails when a supported platform has no adapter [MIS-0002-R10 (CI_MUST_fail_unrendered_unit)]. That is how this policy reads R10 while every unit is the daemon's child.

**`macf_tools pd install` puts the daemon under the platform's service manager, and `pd uninstall` takes it out.** Install reads the agent's card from its home and the declaration from that home first, and installs nothing from a declaration that fails (10.3). `--plan` prints the unit it would install and changes nothing, and a unit already installed that differs is replaced only with `--force`, so a hand edit is never lost silently. The unit runs the interpreter that ran the install, from `/` and without the shell's Python settings, so install first asks that interpreter, run that way, which macf it imports, and plans and installs nothing when it isn't the macf the command itself runs: otherwise the daemon would run other code than the plan named, or fail to start and be restarted every few seconds. On Linux it says when linger is off, since without it the daemon stops at the user's last logout, and turning it on is the host operator's decision (6.1). Uninstall stops the daemon and removes its unit, and on Linux it stops at any failure other than a unit that isn't loaded. The units the daemon supervised keep running, as after any daemon's exit (12.6), for a later daemon to adopt.

**In a container, the container's init is the outer tier.** A container has no systemd or launchd to restart a daemon, so the container's start script does it. It first writes each agent's declaration from `agents.yaml` (10.1). Then, for every agent with a declaration written that way, it starts the daemon as that agent (`runuser`, then `python -m macf.pd <home>`) and restarts it whenever it exits. The backoff is the systemd unit's, 10 s, doubling, at most one try a minute, with one difference: a run of a minute or more starts it over at 10 s, which systemd doesn't do (6.1) [MIS-0002-R03 (outer_tier_MUST_restart_pd)].
- Each agent's loop runs in its own thread, after the access path and before every optional unit, so a daemon that keeps failing never holds up sshd or another step [MIS-0002-R57 (container_MUST_start_access_first), MIS-0002-R58 (optional_unit_MUST-NOT_delay_others)].
- It gives the daemon only who and where it is (`HOME`, `USER`, `LOGNAME`, a fixed `PATH`, `LANG`). The daemon renders each unit's environment from the declaration [MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config)].
- A daemon that exits 78 (its home can't be used) isn't restarted, and the log says to fix the home and restart the container. One that exits 75 (another daemon already serves the agent) is checked again once a minute, so the container takes over if that one ends.
- **An agent with no declaration is started exactly as before.** A deployment opts in agent by agent, by writing the declaration.

### 10.6 Your own entries

**You can schedule for yourself.** Declared schedules (10.4) are the operator's. An *entry* is yours: a timed obligation your primal daemon holds, because it outlives your session and is the only clock running while the session is down.
- `macf_tools pd entry add <when> "<purpose>" --missed once|skip|report` makes one. `--missed` is required: there is no default, as a schedule has none (10.4). Write the purpose so a later you, after a compaction, can act on it cold.
- `pd entry list`, `pd entry show <id>` and `pd agenda` read them, and `pd entry remove <id>` takes one out. Reading and removing need only your uid, so the operator can read and revoke any entry. On a login you share with other agents, any of them can read and remove your entries the same way.
- `pd entry edit <id> --when … --purpose … --missed …` changes an entry and keeps its id. A new `--when` starts its clock again, now, as making it would. `pd entry pause <id>` stops it firing without forgetting it, and `pd entry resume <id>` lets it fire again from the moment you resume. A pause means "stop waking me". A paused entry wakes no one, not even with a wake owed from before the pause, and the firings it covered aren't made up late, whatever the entry's `--missed` policy, since a pause is a choice, not a miss. The resume says how many firings fell in the pause instead, so an entry whose policy is `report` still hears of them. A pause, and a resume, both survive a later edit. A pause only stops work, so, like a removal, the operator may pause any entry. An edit or a resume makes an entry fire as no one consented to before, so, like making one, it's taken only from your live session, and both start in the client's `ask` list beside `pd entry add`. An edit made after untrusted input marks the entry, as making it then would have.
- **The operator's consent is the ask prompt on `pd entry add`.** Setting the mode installs it in the client's `ask` list, so the prompt shows the operator the whole command, the time, the purpose and the flags, before the entry exists. The operator who loosens it to `allow` lets you plan unprompted; that choice is kept at every later install. **The rule matches the command as written:** one built to dodge it, wrapped in `sh -c` for instance, gets past it. That takes a compromised agent, not a confused one, and on a login you share with the operator nothing here is more than advisory (`capability_boundaries` 3.1).
- **Only your live session can make one.** The daemon checks that the request comes from a process below the session unit, as it checks the MacEff channel [MIS-0002-R122 (pd_MUST_check_channel_peer_lineage)]. A run, a cron job or another shell is refused. That's what keeps "a run can't create schedules" [MIS-0002-R33 (run_MUST-NOT_change_schedules)] true for entries.
- **An entry's id is opaque,** `e-` and 12 hex digits, and the event log is its only store: what you hold is what `pd_entry_added`, `pd_entry_changed`, `pd_entry_paused`, `pd_entry_resumed` and `pd_entry_removed` fold to.

**When.** An instant (`2026-10-20T06:30`), a time from now (`in 20m`, `in 2h`, `in 3d`), `tomorrow 06:30`, a cron (`cron:*/5 * * * *`) or a recurrence (`rrule:FREQ=WEEKLY;BYDAY=MO`), read in the declaration's timezone. A daily, weekly or monthly recurrence fires at the time of day the entry was made, and a part it doesn't read, `BYHOUR` among them, is refused by name. So a wake at a set time of day is a cron: a daily brief at 08:00 is `macf_tools pd entry add 'cron:0 8 * * *' "<purpose>" --missed once`. A declaration must name a timezone only when it has schedules or quiet windows (10.4). Where it names none, an entry's time is read in UTC, and the entry records the zone it was read in. A recurrence can also step in hours or minutes (`rrule:FREQ=MINUTELY;INTERVAL=50`), by elapsed time from its start: a wake every fifty minutes lands inside the hour a prompt cache lasts, so the session reads its context from cache instead of writing it again. A relative time is fixed when the entry is made, so "in 20m" means the same moment after a restart. A firing missed while the daemon was down fires once, for the newest instant, unless its policy is `skip`. A wake still owed is held across any number of starts by the notifier's checkpoint (1.8), so a weekend's wake survives a Monday reboot. A log with no checkpoint, whose read-back stops at a day, can't lose one either: at every start the scheduler owes again the wake of each entry you still hold whose newest firing is more than a day old and was never delivered or silenced. The notifier owes one notice per entry, so a wake the checkpoint already holds isn't owed twice.

**What a shared login means for all three** [MIS-0002-R136 (shared_login_limits_MUST_be_stated)]. The three are these:
- **the ask rule:** the operator's ask prompt on `pd entry add` (above);
- **revocation:** the operator can read, pause and remove any entry by its id, needing only your uid [MIS-0002-R135 (entry_MUST_be_revocable_by_operator)]. It is a remedy after the fact, not a check: nothing stops an entry being made, and one that already fired has done what it did;
- **the check-template rule:** an entry's check runs only a template the operator declared, as argv with no shell, each argument one whole element that matches its declared kind, the program named by an absolute path the agent's account can't write [MIS-0002-R143 (check_MUST_run_operator_template)]. The check bullet below has the details.

Where you run under the operator's own login, each of the three stops a confused agent, not a compromised one. A compromised agent can dodge a rule that matches the command as written, read the alert credential, and write programs outside its home, because the operator's account can. None of the three is a boundary there; each is advisory (`capability_boundaries` 3.1). Where you have your own account, the declaration and its check templates are held where you can't write; the entries themselves are folded from your own event log, so the ask rule still stops a confused agent, not a compromised one.

**A late firing, and `--missed`.** A firing more than a minute past its time is late, as when the daemon was down at that moment. Firings missed in a row count as one, for the newest instant. The entry's `--missed` says what a late firing does, and every one is recorded as `pd_entry_fired` with how late it was [MIS-0002-R34 (late_run_MUST_state_lateness)]:
- `once`: it fires as if on time. A wake notifies you, and a check runs its template.
- `skip`: it is recorded and does nothing else. No notice, no run.
- `report`: you are told, and nothing runs [MIS-0002-R25 (missed-run_policy_MUST_be_listed)]. A wake notifies you as `once` does, and a check sends the `pd_entry_due` notice instead of running its template, so a check meant for 06:30 doesn't act at noon on a condition that was true at 06:30.

No other value is taken: the daemon refuses an `entry_add` whose `--missed` is anything but these three, a schedule's `run_once` included, and records nothing.

**`pd entry show <id>` says how late the wake is.** The `pd_entry_due` notice points there, so that record states it: a `last fired:` line names the instant the entry last fired for, and how late it fired (`fired 3h 0m late`, or `on time` within the minute's grace), with the earlier firings it stood for and, under `skip`, that no wake was sent. An entry not yet fired reads `not yet`. The daemon reads it from the entry's newest `pd_entry_fired` in the event log, still the only store, and `pd entry list --json` carries it as `last_fired` [MIS-0002-R34 (late_run_MUST_state_lateness)].

**What an entry does when it falls due:**
- **wake** (the default): the `pd_entry_due` notice, whose id is the entry's. It's a doorbell; its pointer sends you to `pd entry show <id>`.
- **check** (`--check TEMPLATE --arg NAME=VALUE`): runs one of the operator's *check templates* (`check_templates` in the declaration). It wakes you only when the template's condition holds, as a command schedule does (10.4), and the first 4 KB of what it said is kept for you. A template is inline argv with no shell. Each argument fills one whole argv element and must be an integer or match its pattern whole, so a value can never become a second command. A template names its program by absolute path, and one whose program your account can write, the file or the folder holding it, never runs: on a shared login that reaches past your home, to a package manager's `bin`. On a host, a template added or changed in the declaration since `pd install` runs nothing until it's installed again; the program's own bytes aren't digested, only the template. A check refused by any of these runs nothing: its run is recorded `not started` with the reason, and you get the `pd_run_failed` notice.

**A fired entry is your own note, never the operator's word.** In AUTO_MODE you act on it under your normal rules. In MANUAL_MODE you read it and report. A *marked* entry, made while your context held untrusted input, is acted on too, but with the care a notice gets: its text came from a context an outsider could have shaped, so if it asks for anything you wouldn't do unprompted, report it instead of acting.

**Taint marks an entry.** When you make an entry, the daemon reads your session's tool events since its start or last compaction. If your log holds more than one session, a fork or a resume, it reads each back to its own start or compaction, since it can't tell which one asked without taking your word for it, and what any of them read marks the entry. A web fetch, a tool that reads GitHub or mail, a Bash call that names a host or a URL, or a message by a channel other than the MacEff channel marks the context. **This is a heuristic, and you should read it as one.** A Bash call can fetch without naming a host. Nothing in the tool events can prove it didn't, and a log with nothing to bound the context reads as marked.
- An entry made from a marked context records why it's marked, and `pd entry list`, `pd entry show` and `pd agenda` show it.
  - `pd entry add` says so when it makes the entry, with the reasons.
  - `pd entry list` and `pd agenda` put `[marked]` before the entry's purpose.
  - `pd entry show <id>` prints a `marked:` line with each reason, and `pd entry list --json` carries them in `marked`.
- **The mark is part of the entry's record** (`pd_entry_added`), so it stays for as long as you hold the entry.
- **Firing doesn't end an entry.** A fired one-shot entry stays held, and `pd entry list` shows its next firing as `none`, until you or the operator run `pd entry remove <id>`. The event log is its only store [MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger)], and only a removal takes an entry out of it.

**Reaching the operator is a wake, not a separate path.** A reminder or a daily brief the operator asked for is a wake entry of yours: it wakes your session at its time, and you report through whatever channel the deployment gives your session to reach the operator, such as the operator's messaging plugin (1.7). The MacEff channel is not that channel: it is one-way, into your session (1.6). There is no agent-curated feed to the operator. The automatic notification stream the operator can silence or reroute is the layer's event stream (11.4), which publishes every event to the subscribers that chose its source. Its rules reach your session too, as `@channel`: a rule that keeps `pd_entry_due` from `@channel` keeps your own entries' wakes from you, settled as silenced.

**Duties wake you.** The daemon polls your roles once a minute, and a duty's crossing into DUE_SOON or OVERDUE raises `pd_duty_due`, recorded first as `duty_tier_crossed`. A duty that crossed while no daemon ran is announced once at its start, and none twice.

**Planning your own wakes.** An entry is a note to a later you, who will have lost this context:
- **Prefer an entry to session cron** for anything that must outlive the session, survive a compaction or a restart, or run past the client's seven-day expiry. Session cron is still right for a timer that should die with the session: a poll while one build finishes, or a reminder inside one sitting.
- **At a wind-down, plan the next cycle's wakes as entries.** Use a one-shot for a follow-up you owe ("in 2h", re-check a pull request's CI), and a recurrence for a rhythm the operator asked for. Read `pd agenda` first, so you don't add a second clock for a rhythm one entry already keeps.
- **Clean up.** When the work an entry served is done, remove it. When it's only on hold, pause it. A spent recurring entry keeps waking a session that no longer needs it, and costs a turn each time.

**Not yet built:** arbitrary commands as checks, the keystroke fallback for entries (they need the MacEff channel), a duty's `at HH:MM` as its own wake, the two-way calendar, and the planner.

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

**How a crashing unit shows** (10.2):
- Each failure is a `pd_unit_state` event with the state `failed` and a reason: the exit code or signal, or the liveness that was missing or stale.
- Each restart is a `pd_control` event asked by the restart policy, whose reason reads `restart policy <policy> after failure <n>`. The `n` is the failure count, so a rising number is a crash loop [MIS-0002-R52 (control_act_MUST_name_who_asked)].
- `macf_tools pd status` prints each unit's state, its pid while it runs, and since when. It doesn't print the failure count or the reason. Read those from the log: `macf_tools events query --event pd_unit_state --event pd_control --after 1h`.

An event carries states, times and identities. It never carries file content from the agent's home [MIS-0002-R79 (layer_MUST-NOT_copy_home_content)].

**Reading them.** `macf_tools events query` reads the log one line per event: the time, the event and a short summary, with every field under `-v` and one JSON line per event under `--json` for scripts. `--event` repeats and takes globs (`pd_*`). `--after` and `--before` take `30m`, `2h`, `09:00`, an ISO time or an epoch. `--follow` keeps printing new events until Ctrl+C. So `macf_tools events query --event 'pd_wake_*' --event pd_unit_state --after 30m --follow` shows the layer's wakes and state changes as they happen. A query bounded by time reads newest first and stops at its cutoff, and one with no bound reads the current cycle. `events history` prints the newest events the same way.

**A unit outlives a daemon that dies, and the next daemon adopts it.** At boot the core reads each unit's last recorded state, back past any compaction or rotation as far as the previous daemon's start, since every unit that daemon left running was recorded after it. A unit recorded live, whose process is still that process by pid and start time, is adopted rather than started a second time, and the state event says it was carried. A unit whose pid now names another process is started fresh. So is one whose last record names another boot of the host: on Linux a start time counts clock ticks since boot, so after a reboot a new process can carry the very pid and ticks an old record names. Each state event carries the kernel's id for the boot it was recorded in (`boot_id`), and only a record of the current boot is adopted. Boots are compared by id, not by the boot time, because the boot time moves when the clock is stepped, as on a host without a battery-backed clock once NTP answers, and would make this boot's records look older than the boot. A record without the id, written before it existed or on macOS, whose start times are UTC, rests on the pid and start time alone. An adopted unit is stopped through its process group, as one the core started is, and its first liveness is judged from its adoption, as a started unit's is from its start, so a unit that went silent while no daemon ran becomes overdue.

**Each restart and compaction is reported once: what it carried, what changed and what was lost** [MIS-0002-R47 (pd_MUST_report_carried_changed_lost)]. The core writes one `pd_carried` event, with `occasion` (`daemon`, `session` or `compaction`), `after` saying it in words, and three lists, and owes you the `pd_carried` notice, which points to it:
- **after the daemon restarts** (and so after a container is recreated): units adopted are carried; units that were live and came back as new processes changed; units that were live and didn't come back, such as an optional unit nobody started again, were lost. A first start isn't a restart and isn't reported.
- **after the session unit restarts:** the session changed, its working context was lost, and the units still running were carried.
- **after a compaction,** read from the hooks' `compaction_detected` a minute after it lands, so the recovery follower's own prompt comes first: the units running were carried, and the session's working context was lost. A compaction the running daemon couldn't see, made while no daemon ran or inside that minute before a restart, is taken up at the next start, unless a compaction report already covers it.

A notice delivered to an idle session opens a turn, so an agent in AUTO_MODE resumes after any compaction; in MANUAL_MODE it reads the report and stops. The notice reaches you by default, or by `agent` or `both` in `notice_routes`; `both` keeps only its agent half, as for every source but unread mail (1.8). `operator` and `held_until_present` are refused at load.

### 11.2 Liveness is the unit's own

**The unit writes its own liveness**, because a process that exists shows nothing about whether its loop runs [MIS-0002-R14 (unit_MUST_emit_liveness_events)]. The core only reads it.

**How a unit writes it.** A unit gets only its declared environment (R12, R13), and the daemon adds three variables to it: `MACF_PD_UNIT` (the unit's name), `MACF_PD_LIVENESS_S` (its `liveness_interval_s`) and `MACEFF_AGENT_HOME_DIR` (the agent home). They used to be typed into every declaration, where a missing or mistyped value silently stopped the unit's liveness. A declaration may still state them, but a value that disagrees with the unit's own name or interval, or a home that isn't the agent's, is refused at load.
- **A Python unit** calls `macf.pd.liveness.heartbeat_from_env()` and has its work loop call `tick()` on the result once per pass. A beat follows a pass, not the clock: the first `pd_unit_alive` event goes out on the first tick, then at most one per interval, and only when the loop has ticked since the last one. Each names the unit's own pid and start time. A heartbeat thread on its own timer would keep writing while a wedged loop does nothing, which is the failure liveness exists to catch [R18]. So a loop that can block longer than its interval, waiting on a quiet socket say, takes a timeout that makes it pass at least once per interval. The mail broker ticks from its accept loop, which passes at least every half second, idle or not.
- **A unit in any other language,** a shell loop for example, runs `macf_tools pd alive` once per pass, with `--in-flight N` when it has work under way. It writes one event from the same variables, naming its parent process (the loop that runs it, which is the unit the daemon started; `--pid` overrides), and exits 1 when it can't.
- **A unit whose loop runs in another process** names the unit's pid in its beat. The session unit's transcript monitor does this (6.2): `session_heartbeat_from_env()` reads the session variables, and its beats name the wrapper's pid, so the daemon credits them to the process it started.
- **Outside a daemon** the variables are absent, and the call does nothing, so the same program runs with or without a daemon.
- **A partial or malformed setting** writes nothing and says why on stderr, because liveness credited to the wrong unit or agent is worse than none.
- **Silence:** a unit that writes no liveness reads `starting` only until three of its intervals have passed since its start. Then it is recorded failed and restarted by its policy (10.2). The mail broker and its inbound watcher both write liveness.

**The unit publishes its interval, and the observer computes the bound from it**, as `service_supervision` requires, so a unit that changes its interval changes its own bound. A unit is overdue when its last liveness is older than three of the intervals it published, and an overdue unit is failed, not running. Three tolerates two missed writes. It is the core's constant, chosen in 2026-10 without a measurement of real write jitter, and is re-derived once units have run under load.

**The health verdict says alive only after a probe.** `macf.pd.health` confirms by pid and process start time that the process named in a unit's last liveness event is still that process before it calls the unit alive [MIS-0002-R15 (readout_MUST_probe_liveness)], because a pid can be reused. The start time has one stored form, `macf.notify.session.proc_start`, compared through `verify_incarnation`. It derives everything when asked and stores nothing. Its five verdicts are alive, stale, gone, absent and unreadable, and a liveness it cannot read is unreadable, never alive. It is the verdict the readout will print, and the outside watch (7.1) applies the same rule now, through `read_liveness`, so the two cannot disagree about a unit.

**A schedule's health is its runs, owed against done, when the readout is asked** [MIS-0002-R17 (readout_MUST_derive_health_from_runs)]. `macf.pd.health.schedule_health` reads the cron for the newest firing owed by now and the scheduler's events (`pd_schedule_seen`, `pd_run_started`, `pd_run_done`, `pd_run_missed`, `pd_schedule_not_run`) for what became of it, with the daemon's newest `pd_daemon_start`. A firing the declared missed-run policy accounted for is not owed, and nor is one whose run ended without starting, which reads failed. The verdicts:
- **ok** or **failed:** how the last run ended;
- **due:** a run owed and not started, inside a minute's grace for a slow pass, or a missed run its policy put off to a window that hasn't opened yet (`pd_run_deferred`);
- **overdue:** a run owed and not started past that grace, measured from the oldest firing owed, or one started and past its limit with no end recorded;
- **running:** a run in flight, which holds its schedule, as the scheduler starts no other until it ends;
- **not run:** a schedule the daemon declined at its newest start, such as a prompt run it can't run yet or a schedule changed since the last `pd install` (10.4). A refusal at an earlier start counts for nothing once a later start took the schedule;
- **none owed:** nothing owed since the schedule was first seen.

Nothing is stored, so the same events read later give the later verdict. **The daemon owes every run it starts, so while it answers `pd status`, which is how it is known alive, one overdue schedule makes it read unhealthy** [MIS-0002-R18 (overdue_run_MUST_read_unhealthy)]. A failed run is its schedule's outcome, and a schedule the daemon declined is said once; both show per schedule, and neither judges the daemon. `pd status` prints each schedule's verdict and a `runs:` line, and its JSON carries `schedules` and `runs`. With no daemon answering, the schedules are still listed, and no daemon is called healthy or unhealthy.

### 11.3 Who asked

Every start, stop and restart the core performs is a `pd_control` event naming who asked and why [MIS-0002-R52 (control_act_MUST_name_who_asked)]: the operator, the agent's declared wind-down, or the unit's own restart policy. An operator's act needs the process that asked, its user, pid and start time, and the core records it beside the asker, because the asker is a claim and the process is observed. The process is observed from the kernel's report on the control socket's connection (12.3).

### 11.4 The event stream

**What it is.** Every event your persistent layer records is published, as it is recorded, on one event stream [MIS-0002-R150 (layer_MUST_publish_event_stream)]. The stream is a way of reading your event log, not a second copy of it: the log stays the only store. Anything that tells a person, an agent or an app about your layer is a subscriber to the stream. The MacEff channel, the tray, and a bridge to the operator are meant to be subscribers, and nothing keeps a parallel feed. Today the MacEff channel still takes notices on its own socket (1.3), and no bridge to the operator is built: moving them onto the stream is a later step. The channel is already under the stream's rules, though, as the subscriber `@channel` (below).

**Where it is.** Your primal daemon serves the stream on `<id>.events.sock` in its runtime directory, beside its control and channel sockets, mode 0600 (12.2). `<id>` is the calling card with `@` written as `_`, so `IraMacEff@ee9a78` serves `IraMacEff_ee9a78.events.sock`. It follows its own event log, as the core already does, and sends each new record to the subscribers that asked for its source. "As it records it" means within the daemon's tail interval, about one second: it reads the log on every pass of its loop, a quarter of a second apart, and that is the bound a subscriber may rely on. The daemon polls; it doesn't wait on kqueue or inotify, and nothing signals it from `append_event`.

**Subscribing.** A subscriber connects and, within three seconds, sends one line. The line names the sources it takes (event names, with `*` globs), and optionally the position of the last record it saw and a name it goes by. A connection that sends nothing in time is closed. `macf_tools pd stream subscribe --source 'pd_unit_*' --name watch` does this and prints every line it gets; `--position LOG:OFFSET`, the `log` and `offset` of a record's position, resumes just after that record. The command doesn't reconnect on its own. When the stream ends, as when the daemon restarts, it exits 0, and a subscriber that must not miss records runs it again with the last position it printed. The daemon answers with a `welcome` line naming where the stream starts for it. Each record then arrives as one JSON line with:
- its **position**: the log's identity (its inode and a digest of its first line, since rotation rewrites the file in place) and the byte offset just past the record, which is a line boundary;
- its **source**, **agent** and **time**, as the layer set them;
- its **origin**;
- the record itself.

**On the wire**, one JSON object per line each way:
- hello: `{"sources": ["pd_unit_*"], "position": {"log": "<identity>", "offset": 1234}, "name": "watch"}`, with `position` and `name` optional. A position is copied whole from the last record received.
- welcome: `{"type": "welcome", "agent", "position", "sources", "granted"}`.
- record: `{"type": "record", "position", "source", "agent", "time", "origin", "record"}`.
- gap: `{"type": "gap", "agent", "time", "from", "to", "reason"}`, where `reason` is `rotated`, `not_a_line_boundary`, `backlog` or `overflow`.
- refused: `{"type": "refused", "error"}`.

A subscriber receives only the sources it chose [MIS-0002-R151 (subscriber_MUST_receive_chosen_sources)]. A subscriber refused for any reason gets one `refused` line saying why, and the connection closes.

**Nothing is skipped in silence** [MIS-0002-R154 (subscriber_MUST_resume_from_last_record)]. On reconnect with a position, the stream resumes just after it, from the log. If the position names another log, or isn't on a line boundary of this one, the stream sends one `gap` record saying from where to where records may be missing, then continues. A subscriber is never handed the next record as if nothing were missed. A resume reads at most 8 MB of the log at once, and one from further back gets a `gap` (`backlog`) to where that read starts.

**Rotation changes the log's identity.** Rotation rewrites the log in place from a later line, keeping its inode and its current cycle, so its first line, and with it the identity in every position, changes. What a subscriber gets depends on whether it was connected:
- **Connected through the rotation:** the daemon finds the last line it had read in the rewritten log and goes on without a gap, when rotation kept it. When it didn't, each subscriber gets a `gap` (`rotated`).
- **Reconnecting with a position from before the rotation:** that position names a log that no longer exists, even when the record it points to was kept. The subscriber gets a `gap` (`rotated`), then the rotated log from its start, within the 8 MB bound. Records it already saw can come again, under new positions.

**A slow subscriber never slows the layer** [MIS-0002-R153 (subscriber_MUST-NOT_block_layer)]. Each subscriber has a bounded queue of a thousand records, and sends never block. A subscriber that falls behind loses its own backlog, not the daemon's time. Its next record is a `gap` (`overflow`) from the last record it still held. Each uid may hold eight connections, a hello not yet sent included.

**What a record can claim** [MIS-0002-R155 (stream_record_MUST_name_source)]. `agent` and `time` come from the layer, never from a field a publisher put in the event's data: `agent` is the daemon's own agent, and `time` the record's timestamp in the log, which `append_event` writes.
- Anything running as your uid can append a line to your log: a shell redirect, or a tool steered by injected text. So a record read back from the log carries `origin: log`, whatever its event name claims.
- A record the daemon writes itself carries `origin: daemon`. The daemon learns the line in-process as it writes it, and checks that the log holds exactly those bytes at that offset; a copy appended by anything else, even byte for byte, is `origin: log`. Only these can vouch that the layer did what they say. The daemon remembers the last ten thousand lines it wrote, in memory, so a record from before this daemon started, or replayed on a resume from further back, is `origin: log` even if the layer wrote it. `origin: daemon` marks live records, not history.
- A subscriber that alerts a person, such as an operator bridge, alerts on `origin: daemon` records.
- This is the same threat model as your own entries (10.6): it stops a confused agent, not a compromised one. The operator's rules below are folded from the log too, so a forged rule line is read like any other.

**Who may subscribe** [MIS-0002-R156 (subscriber_MUST_be_granted_agents)]. The daemon checks the connecting process's uid, as the kernel reports it (`SO_PEERCRED` on Linux, `LOCAL_PEERCRED` on macOS):
- **Your own uid** may subscribe to your sources.
- **Any other uid** needs a grant in the operator's declaration, naming that uid and the sources it may take: `stream_grants: [{"uid": 0, "sources": ["pd_unit_state", "pd_daemon_start"]}]`. A host-wide watch might be granted unit states and notices, but never your tool events. A grant narrows what the subscriber asked for; the `welcome` names what was granted. The socket's mode and the private runtime directory keep every other non-root uid from reaching it at all, so today a grant is how a root watch, or a later deployment that opens the socket, gets in.
- A subscriber of one daemon sees only that agent's records. Watching several agents means connecting to several daemons, each granting it separately.
- **A grant separates uids, not agents.** On a host where several agents share one login, every one of them is "your own uid" to every other's daemon, and each may subscribe to the others' streams. Separating agents needs an account per agent, as containers have. The stream can't be more private than the event log it reads, which is mode 0600 to the login. The cap of eight connections per uid is likewise one budget per daemon for the whole login on a shared login, so another agent's subscribers, or a reconnect loop, can fill it and leave the tray or an operator bridge refused.

**The operator can silence or reroute any source or subscriber without a restart** [MIS-0002-R152 (operator_MUST_silence_and_reroute)]. The commands are `macf_tools pd stream silence <source|@subscriber>`, `unsilence <source|@subscriber>`, and `route <source> <subscriber>`, which sends a source only to that subscriber, among those that chose it; `route <source> --clear` takes the route away. A subscriber is named with `@`, by the name its hello gave.
- **A source in a rule is an event name or a glob,** matched with `*` and `?` as a subscriber's sources are. A subscriber's name is matched exactly. Each source is its own name: `amail` (mail arrived) and `pd_unread_mail` (mail left unread) are two, and silencing `amail` leaves `pd_unread_mail` delivered. Keeping both from your session takes a rule for each.
- Each one is recorded as a `pd_stream_rule` event before it takes effect, and the daemon's rules are what those events fold to, so a rule survives a restart. A rule that can't be recorded isn't set.
- A silenced source still lands in the log. Only its delivery stops.
- **Your session is under the same rules, as `@channel`.** Before the notifier writes a notice to the MacEff channel (1.8), it asks the daemon's rules in force whether the notice's source is delivered to the subscriber `channel`. The rules are read live, so a rule set now is in force from the daemon's next pass. So `pd stream silence amail` stops mail notices to your session as well as mail records to the stream's subscribers, `pd stream silence @channel` stops every notice to your session, and `pd stream route pd_entry_due tray` keeps that source from your session while the tray still gets it. A source's name in a rule is matched against an event name on the stream and against a notice's source (1.8) at the channel; the two namespaces overlap, as with `pd_carried`, and a rule matches both. No stream subscriber may name itself `channel`; a hello that does is refused.
- **A silenced notice is not owed.** The notifier records it as `pd_notice_silenced`, with its source and arrival id, and drops it from what is owed (1.8). A restart reads that event back as settled, as it reads `pd_notice_delivered`, so the notice is never owed again. Unsilencing delivers only what arrives after it, never what was silenced. The detection stays in the log, and the mail stays in the box: a later notice sends you to the box, and you find there whatever it holds.
- **The keystroke wake honors the rules too** (1.9). A typed wake is delivery to your session by another path, so where the rules keep mail from `@channel`, whether by silencing `amail`, silencing `@channel` or routing `amail` elsewhere, no wake is typed for it, and the notice is settled as silenced the same way. A wake already typed before the rule was set is still followed through to its Enter, so no half-typed text is left in your prompt.
- What reaches your session doesn't change: a closed record the notifier builds from what it owes, never a line from the log. A line appended to your log, a forged `pd_carried` with free text in its data among them, reaches the channel as no text.
- Setting the mode puts these commands in the client's ask list, as `pd entry add` is, so on a login you share with the operator, approving the prompt is the operator's act. An operator who loosens one to `allow` keeps that choice.
- Where the operator has an account of its own, as in a container, the declaration names it as `operator_uid`, and the control socket takes the stream's rules only from that uid, refusing your own. That uid is let through the control socket for these rules alone. On a shared login the uid check separates nothing: every agent on that login has the operator's uid, so there the ask prompt is what makes a rule the operator's act.
- **That check holds at the socket, not across a restart.** At its start the daemon folds every `pd_stream_rule` line in your event log, and your own uid writes that log. So even with `operator_uid` set, a rule line you append yourself is honored from the next start, a `silence` of the very source that reports on you included. The operator's rules are kept apart only when they live where your uid can't write, which isn't built. As with your entries (10.6), the rules stop a confused agent, not a compromised one.

**What the stream is not for.** Quiet hours, a daily bound, and delivering something exactly once belong to whichever subscriber delivers to a person, not to the layer. The operator route beyond unread mail, and "hold until present", are that subscriber's job, left by MIS-0002 R42 to a successor MIS.

---

## 12 The Daemon and Its Control Socket

### 12.1 One daemon per agent, and whose it is

`python -m macf.pd <agent home>` runs the agent's primal daemon. It takes its agent's calling card from the identity file in that home, never from an environment variable [MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)]. A variable is inherited by everything started below the shell that set it, and a client started from such a shell has taken another agent's name as its own. The daemon then loads the declaration (10.1), and wherever a unit's environment names the agent home, the card or the daemon's runtime directory, it fills in the values only it knows.

**One daemon per agent** [MIS-0002-R01 (agent_MUST_have_one_primal_daemon)]. Once its control socket is bound, the daemon writes a record beside it holding its pid, its process start time and a version. A second daemon for the same agent refuses to start while that record names a live process by pid and start time, or while something answers on the socket, whatever the record says: a record can go missing, as after a sweep of the runtime directory. A daemon that stops removes the socket and the record only while they are still its own, so one stopping late never removes a successor's. A record whose process is gone, or whose pid now belongs to another process, is stale and is replaced. The MacEff channel checks its peer against the same record [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)].

**A daemon's start bounds what it observed.** After writing its record, and before it adopts or starts any unit, the daemon writes `pd_daemon_start` with the record's fields and the agent, so a second daemon that is refused never writes one. What a daemon observes outside its units, such as a surface's state, holds only for its own life, so a reader folding those observations starts from the newest start. Unit state carries across a start, because the next daemon reads it to adopt the units still running (11.1).

On SIGTERM, SIGINT or SIGHUP the daemon removes its socket and its record and ends, and its units keep running for the next daemon to adopt (12.6). A restart through the outer tier, `launchctl kickstart -k` or `systemctl --user restart`, therefore restarts the daemon alone, as the operator ruled on 2026-10-10. Stopping every unit is its own act, which the daemon takes only when asked for it; no command line offers it yet (13). It exits with 75 when a daemon for the agent is already running and with 78 when the agent home can't be used, so an outer tier's log tells the two apart.

On Linux the daemon names its own process `maceff_pd` as it starts, so `ps`, `top` and `pgrep maceff_pd` show it by that name rather than as the Python interpreter [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)]; its command line is unchanged, so `pgrep -f macf.pd` still finds it. macOS offers no call that renames a running process, so there the LaunchAgent names the daemon at exec: launchd runs the interpreter as `Program` with `maceff_pd` as its `argv[0]`, and `ps` and `pgrep maceff_pd` show it by that name [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)]. `top`, and anything else that reads the kernel's own name for a process, still shows the interpreter. An interpreter that is a framework build, as Homebrew's and python.org's are, would re-exec itself through its Python.app and lose the name, so the LaunchAgent starts that Python.app directly and tells it which venv it came from in `__PYVENV_LAUNCHER__`, as the build's own launcher does. That variable is an internal of CPython's macOS build, and a test pins it.

### 12.2 Where the socket is

The daemon listens on Unix sockets only, never on a network port [MIS-0002-R80 (pd_MUST-NOT_listen_on_network)]: the control socket here, the channel socket of 1.3, and the event stream's socket (11.4). All three live in the runtime directory, `$XDG_RUNTIME_DIR/maceff_pd/`, or `/tmp/maceff_pd-<uid>/` where that variable is unset, each named for the agent's card, so every path carries `maceff_pd` and the card [MIS-0002-R06 (pd_identifiers_MUST_use_maceff_pd)]. The daemon checks the socket path against the platform's length limit before binding, as the adapter does at install (3.1), with a message naming the path and the limit. Without the check, a path that's too long fails at bind with an error that names neither.

**The runtime directory must be private.** The daemon creates it with mode 0700, and refuses to start when an existing one belongs to another user or is open to group or others. Under `/tmp`, another local user could have made the directory first, and every socket in it would then be theirs to replace.

**A long-running daemon keeps its record from being swept.** On macOS, without `XDG_RUNTIME_DIR`, the runtime directory is under `/tmp`, and the system's `tmp_cleaner` deletes a regular file there once it has gone three days unread, unwritten and unchanged. The sockets are not regular files and their directory is never empty, so only the record is at risk, and `pd status` believes the daemon only through it. The daemon refreshes the record's times every hour, and writes it again if a cleaner has already taken it.

### 12.3 Who may connect, and what that proves

The control socket accepts a connection only from the daemon's own user, as the kernel reports it for the connection, and from the declaration's `operator_uid` for the event stream's rules alone (11.4). **That is all the check proves.** On a login that several agents share, or an agent and its operator, the kernel can't tell them apart. So a request names its asker, and the daemon records that claim beside the user, pid and start time it observed [MIS-0002-R52 (control_act_MUST_name_who_asked)]. The claim is an attribution, not an authentication, until each agent runs under its own account, and nothing over the socket gives a claimed operator more than any caller of the same login.

An act may claim only the operator or the agent's wind-down. A pace of the keystroke wake (1.9) acts on no unit, and may claim the agent, from its own command line, or the operator. Which asker a request claims isn't checked against the declaration in step 1, and is recorded as any claim is. The restart policy and the harness ask from inside the daemon, so a request that claims either is refused with the reason, and nothing is done.

### 12.4 What it does, and what it refuses

- **`status`** returns each declared unit's state, pid, start time and when it entered that state.
- **`start`, `stop` and `restart`** act on one declared unit. A stop sends SIGTERM to the unit's process group and SIGKILL after its grace period, and it succeeds whatever gate the session enforces [MIS-0002-R48 (outside_stop_MUST_override_gates)]. It is how the operator takes back a session that a loop holds. An asked restart first lets the unit's work in flight drain, up to a timeout it names when it gives up [MIS-0002-R49 (pd_MUST_check_work_in_flight)].
- **`stream_rule`** silences, unsilences or reroutes a source or a subscriber of the event stream, asked by the operator, recorded first and in force at once (11.4).
- **A unit the declaration doesn't name is refused.** The daemon never starts, stops or signals another agent's units [MIS-0002-R07 (pd_MUST-NOT_control_other_agents)].
- **A malformed request, an unknown operation or an unknown field refuses the whole request**, and nothing is done.
- **A compaction is refused.** The layer never compacts a session on its own initiative [MIS-0002-R51 (layer_MUST-NOT_compact_on_own)]. Compaction on request is still to come (13): it will be accepted only from the operator or the agent's declared wind-down [MIS-0002-R108 (compaction_MUST_be_asked_by_operator_or_wind-down)], and only once the operator is established some other way than a claim (9.3).

Each connection carries one request. A refusal says what was refused and why, and names this policy, `macf_tools policy navigate persistent_layer`, as `capability_boundaries` requires of every refusal.

### 12.5 Reading it from outside

**`macf_tools pd status`** shows each declared unit's state. It believes the daemon only after the check the MacEff channel makes of its peer [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd)]: the record must name a live process by pid and start time, and the process answering the socket must be that one. Otherwise it reads each declared unit's last state and liveness from the event log, through the shared health verdict (11.2). Either way it says which source it used, and why. A session whose restart a quiet window holds shows the window's end (10.4).

### 12.6 A unit outlives a daemon that dies

The daemon starts its units as its children, but they don't die with it: the outer tier renders the daemon so that its exit leaves them running, as the LaunchAgent does with `AbandonProcessGroup` (3.1) and the systemd unit with `KillMode=process` (6.1). Taking every unit down with a daemon that crashed would drop their work in flight unasked, and leave the restart nothing to carry. The next daemon adopts the units that are still the processes it recorded (11.1). A daemon that ends on a signal leaves them running too, so its restart drops nothing; stopping every unit is its own act (12.1).

**Between a daemon's death and its restart, the units run unsupervised.** The window is the outer tier's restart delay. A unit whose process dies inside it isn't adopted, and the new daemon starts it as at any boot.

---

## 13 Not Yet Landed

Specified in MIS-0002 and arriving with their landing steps, each in the pull request that enforces it:
- **The rest of the primal daemon:** compaction on request, once the operator is established some other way than a claim on the socket (9.3, 12.3); and a command-line act that stops every unit, with the question of which asker a command line claims (12.1) (MIS-0002 §6.1 to §6.4, §6.7).
- **The rest of the notifier** (1.8):
  - the refusal at load of a declaration that doesn't route `pd_carried` to the agent, once the deployed declarations route it, so that the notice of what a restart, recreate or compaction carried, changed and lost always reaches the agent (11.1) [MIS-0002-R47 (pd_MUST_report_carried_changed_lost)];
  - the operator's routes for sources other than unread mail, and `held_until_present`, which a declaration may not name until the event stream serves them (1.8);
  - sources besides mail (MIS-0002 §6.6).
- **Observation** (5): messages from an onlooker into the observed session, an optional feature that nobody has built. Wherever one is built, its source comes from the transport and the onlooker's card from the invitation [MIS-0002-R95 (onlooker_message_MUST_carry_transport_source)] [MIS-0002-R116 (onlooker_card_MUST_come_from_invitation)].

Not specified as a requirement, and listed so that nobody assumes it:
- **An alert on a failed run** (7.1, 10.1). The outside watch reads liveness and runs owed against runs done, and a failed run is neither. The agent is owed the `pd_run_failed` notice (10.4). But nothing reaches a person while the agent is down, and a service's daemon has no session to tell. So the broker's sweep finding stuck mail is recorded and shown, and tells no one.

Until a section lands, the rules in force are the existing policies: `service_supervision`, `notification_delivery` and `amail`.

---

## Integration

- `notification_delivery`: what a notice may carry and what it licenses. The channel is a delivery transport and inherits every rule there.
- `capability_boundaries`: the channel is a new way for notices to enter a session, held to a socket and a peer check rather than to trust.
- `service_supervision`: the primal daemon is the supervisor this policy describes, for the units its agent declares.
- MIS-0002: the decision record, with each requirement's reason.

## Wiki-Links

[[notification_delivery]] [[supervision]]
