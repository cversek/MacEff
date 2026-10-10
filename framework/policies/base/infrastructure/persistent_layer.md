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

**3 Attach**
- How does attach find the session to attach to?
- What does the readout say when nothing can attach?

**4 Not Yet Landed**
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

---

## 3 Attach

### 3.1 Resolved from the primal daemon

**Attach by name resolves the session from the agent's primal daemon** [MIS-0002-R100 (attach_MUST_resolve_from_pd)], never from a tmux name. A name lookup cannot see a renamed session, cannot tell two similar names apart, and cannot see a session Claude Code's own daemon hosts.

1. Attach takes the session unit's pid from the daemon's status, and checks it against the recorded start time, so a recycled pid is refused.
2. A session hosted by Claude Code's daemon attaches with `claude attach <id>`.
3. A session under tmux attaches to its pane's session by exact name (`=name`).
4. A daemon that does not answer resolves nothing; there is no fallback to a name.

The operator may attach to any session without an invitation [MIS-0002-R81 (operator_MAY_attach_without_invitation)]. An onlooker is never given a keyboard.

**From the operator's side of a container**, the command also needs the way in (`ssh -t` or `docker exec -it -u <agent>`). The plan will add it once the daemon's status says where the daemon runs; until then it does not.

### 3.2 When nothing can attach

**Where nothing attachable hosts the session, the readout says so, with the reason** [MIS-0002-R101 (readout_MUST_say_nothing_attachable)]: a stopped or undeclared unit, a pid that changed, or a session in a plain terminal that neither tmux nor Claude Code's daemon hosts.

---

## 4 Not Yet Landed

Specified in MIS-0002 and arriving with their landing steps, each in the pull request that enforces it:
- **The primal daemon itself:** declarations, liveness events, health derived from runs, outside control and the outside watch (MIS-0002 §6.1 to §6.4, §6.7, §6.12).
- **Schedules and the notifier,** including the keystroke fallback, the dark-channel event, and every producer of the operator's activity (MIS-0002 §6.5, §6.6, the rest of §6.14).
- **Mail, containers, macOS, the tray and observation** (MIS-0002 §6.8, §6.9, §6.10, §6.11, §6.13).

Until a section lands, the rules in force are the existing policies: `service_supervision`, `notification_delivery` and `amail`.

---

## Integration

- `notification_delivery`: what a notice may carry and what it licenses. The channel is a delivery transport and inherits every rule there.
- `capability_boundaries`: the channel is a new way for notices to enter a session, held to a socket and a peer check rather than to trust.
- `service_supervision`: the primal daemon, when it lands, is the supervisor this policy describes.
- MIS-0002: the decision record, with each requirement's reason.

## Wiki-Links

[[notification_delivery]] [[supervision]]
