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

**2 The Tray**
- What does the tray show, and for whom?
- How does one icon stand for several agents?
- What may the tray do, and what must it ask a primal daemon to do instead?
- How does the tray know an answer came from the agent's own daemon?

**3 Not Yet Landed**
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

## 2 The Tray

### 2.1 What it is

**The tray is optional** [MIS-0002-R67 (operator_MAY_run_tray)]. It is a menu-bar app the operator may run where the host has a desktop. The outer tier and every primal daemon run the same without it, and no part of the layer imports it [MIS-0002-R68 (layer_MUST-NOT_depend_on_tray)]. It is installed as the `tray` extra and run with `python -m macf.tray`. Where a host cannot show it, as on stock GNOME without an extension, the readout says so [MIS-0002-R73 (readout_MUST_say_tray_unavailable)].

### 2.2 One icon for every agent

**One icon stands for all the agents installed on the host**, with a menu entry per agent [MIS-0002-R69 (tray_MUST_show_icon_per_agent), as amended]. The agents are the ones the outer tier starts, found from their LaunchAgents (`maceff_pd.*`). Each is keyed by the calling card in its home's identity file, never by a label, a socket name or the environment.

**The icon shows the most urgent state among the agents**, and the menu names the agents that caused it [MIS-0002-R72 (tray_MUST_flag_waiting_on_person), as amended]. The order is:
1. failed;
2. unreachable (the agent's daemon did not answer, or its answer could not be trusted);
3. waiting on a person;
4. starting;
5. running and stopped.

The first three alert. A session that starts waiting on a person changes its own entry and, through the union, the icon.

**Glyphs.** There is one glyph per state, all drawn from one mark. They are monochrome template images at menu-bar size, black and transparency only, so the system tints them for light and dark bars. There are no letters or numbers, and the shape changes with the state, so color is never the only signal. Each agent's entry shows that agent's own logo beside its card.

### 2.3 What the tray may do

**The tray observes and asks; it never acts itself.**
- Each start, stop or restart goes to that agent's own primal daemon, as a control request that names the operator as the asker [MIS-0002-R70 (tray_MUST_act_through_pd)].
- It offers no compaction, which only the operator's own command or the declared wind-down may ask for.
- **It never types into a session** [MIS-0002-R71 (tray_MUST-NOT_type_into_session)].

**The operator asker is a claim.** On a shared login a socket's peer credentials cannot tell the operator's tray from another agent's process, so the control socket establishes the operator by its own means and never takes the field alone.

**An answer counts only from the agent's own daemon.** The tray accepts an answer only from the socket peer that the daemon's record names, matched by pid and start time [MIS-0002-R123 (channel_MUST_check_its_peer_is_its_pd), applied to the control socket]. A peer that cannot be checked makes the agent unreachable, never trusted.

---

## 3 Not Yet Landed

Specified in MIS-0002 and arriving with their landing steps, each in the pull request that enforces it:
- **The primal daemon itself:** declarations, liveness events, health derived from runs, outside control and the outside watch (MIS-0002 §6.1 to §6.4, §6.7, §6.12).
- **Schedules and the notifier,** including the keystroke fallback, the dark-channel event, and every producer of the operator's activity (MIS-0002 §6.5, §6.6, the rest of §6.14).
- **Mail, containers, macOS, observation and attach** (MIS-0002 §6.8, §6.9, §6.10, §6.13).

Until a section lands, the rules in force are the existing policies: `service_supervision`, `notification_delivery` and `amail`.

---

## Integration

- `notification_delivery`: what a notice may carry and what it licenses. The channel is a delivery transport and inherits every rule there.
- `capability_boundaries`: the channel is a new way for notices to enter a session, held to a socket and a peer check rather than to trust.
- `service_supervision`: the primal daemon, when it lands, is the supervisor this policy describes.
- MIS-0002: the decision record, with each requirement's reason.

## Wiki-Links

[[notification_delivery]] [[supervision]]
