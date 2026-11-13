# MIS-0008: Voice for MacEff agents: the Voice Input Channel, voice generation and a voice lock

**Number**: 0008
**Type**: Standards
**Status**: Draft
**Authors**: the container-management maintainer
**Secretary**: none
**Deliberation**: pending
**Created**: 2026-11-13
**Updates**: MIS-0002, MIS-0007
**Supersedes**: none
**Lands-in**: framework/policies/base/infrastructure/persistent_layer.md, framework/policies/base/infrastructure/voice_input.md (new), framework/policies/base/infrastructure/voice_generation.md (new), framework/policies/base/infrastructure/voice_lock.md (new), macf/src/macf/voice/, macf/src/macf/channels/, macf/src/macf/pd/, macf_tools voice
**Resolution**: none

---

## 1 Summary

This MIS gives MacEff agents a voice in both directions, and it renames the channel that already exists so the two read as a pair.

- **The MacEff Notification Channel** is the channel known until now as the MacEff channel. It still carries the daemon's doorbells and nothing a sender chose. Only its name and identifiers change.
- **The MacEff Voice Input Channel** carries the operator's dictated words into an agent's session as a labeled message.
  - A capture unit opens the microphone on a wake phrase or on one of two hotkeys: one held to talk, one toggled for continual voice.
  - A recording indicator with a waveform and volume trace shows whenever the capture unit is recording.
  - On a system with a system daemon, one capture unit serves every member agent. It dispatches each utterance to the agent whose wake phrase or hotkey fired.
- **Voice generation** lets each agent answer aloud. The agent chooses its voice with the operator through a process it leads: inferred traits, a dialog, generated samples.
- **A voice lock** delivers an utterance only when the speaker matches the enrolled operator.
  - A failure sends the agent a notice without content, so it can say the voice wasn't matched.
  - Repeated failures lock voice contact for a while and raise the agent's guard.

It concerns every agent that will take dictation or speak, every deployment that installs the channel, and the maintainers of MIS-0002 and MIS-0007.

## 2 Motivation

- **Voice works for one agent on one desktop, outside the framework.** The host-side maintainer's agent has taken dictation since November 6, 2026.
  - The pipeline: a wake phrase, a trained wake classifier, a speech check, transcription, and a channel plugin in the agent's private tree, with a waveform overlay from a third-party dictation tool.
  - Its capture half depends on one Linux desktop, and none of it can be installed by another agent.
  - Evidence: the working setup, surveyed on November 13, 2026 (reproduction).
- **Dictation isn't a notice.** A notice licenses one act and carries nothing a sender chose (MIS-0002-R77 (wake_MUST_carry_fixed_words_only)). Dictation carries the operator's own words, from a microphone anyone in the room can reach.
  - MIS-0007 began this class as operator input and named the dictation feature as its first case, with a capture unit.
  - It left the feature itself to a later MIS. This is that MIS.
  - Evidence: MIS-0007 sections 3 and 4 (reasoning).
- **Wake models mislead when measured carelessly.** In November 2026, a dozen wake and speaker experiments on this host first reported numbers that turned out to measure clip length, not the speaker.
  - A held-out test measures only what it was built to hold out.
  - Evidence: the container-management maintainer's experiment records of November 6, 2026 (measurement).
- **One voice server per machine, many agents.** The operator asked for one server on the system daemon, with a wake phrase and hotkeys per agent, and for a voice lock with a lockout (November 13, 2026, at the terminal).
  - Evidence: the operator's request (reasoning; no build yet).
- **"The MacEff channel" no longer says which channel.** Once a second channel exists, the old name is ambiguous in every policy and log.
  - Evidence: reasoning.

## 3 Goals and Non-Goals

**Goals**
- An agent on Linux or macOS can take dictation through MacEff by wake phrase, hold key or toggle key, with the indicator showing.
- One capture unit can serve several agents on one machine, each with its own wake phrase, hotkeys, voice lock and voice.
- Wake phrases, voice locks and voices are each set up by a guided procedure the agent leads. Each lands with its policy and a skill.
- An utterance from the wrong speaker never reaches an agent's session as text. The agent learns of the attempt, and repeated attempts lock voice contact and raise its guard.
- The existing channel's name says what it carries.

**Non-goals**
- Voice as an authorization. No utterance, matched or not, satisfies anything an authorization depends on.
- Several microphones on one machine, and a microphone shared between machines.
- Speaker identification among several enrolled people. The voice lock checks one enrolled operator per agent.
- Changing what a notice may carry. The two voice notices in section 6.7 carry no content, like every other notice.
- The operator-input route rules of MIS-0007 (keys, signatures, nonces, receipts, expiry). This MIS uses them and doesn't restate them.

## 4 Guide-Level Explanation

**Taking dictation.**
1. The operator says "Hey Atlas".
2. A chime plays, and the indicator appears at the top of the screen with the agent's name, a moving waveform and a volume trace.
3. The operator speaks. When the operator stops, the indicator closes.
4. In the agent's session a message appears from the MacEff Voice Input Channel. Its label comes first: spoken by wake phrase at 14:02, voice matched, screen unlocked. The words follow.
5. The agent answers in the session, and aloud in its chosen voice once the microphone has closed.

**The two hotkeys.** Holding the agent's hold key records only while the key is held. Pressing its toggle key opens continual voice: every pause ends one utterance and the microphone stays open, until the key is pressed again or a long silence closes it. The indicator shows which mode is running.

**Several agents.** On a machine with a system daemon, one capture unit listens for every member agent. "Hey Atlas" goes to one agent and "Hey Nova" to another. Each agent's hotkeys go to that agent. Each agent sees only its own utterances.

**The voice lock.** Someone else says "Hey Atlas".
1. The capture unit's speaker check fails, so the words are dropped.
2. The agent receives a notice without content: voice unmatched, attempt 1 of 3.
3. The agent says aloud that it couldn't match the voice, and to try again.
4. After the third failure within the window, voice contact with that agent locks for ten minutes.
5. The agent's guard is raised: its status shows it, its hooks surface it, and it tells the operator on another channel.

**Setting it up.**
- `macf_tools voice wake define`, `record`, `train` and `test` take the operator from a chosen phrase to a measured wake model. A skill has the agent coach each step.
- `macf_tools voice lock enroll`, `annotate`, `train` and `test` do the same for the voice lock.
- `macf_tools voice select` runs the voice selection. The agent infers traits for its voice from its own identity and role, puts them to the operator, plays generated samples, and records the voice the operator accepts.

**The renamed channel.** Notices that used to arrive from the MacEff channel now arrive from the MacEff Notification Channel. They carry the same doorbells, under a new name and a new plugin id.

## 5 Terms

- **capture unit**: a declared unit that opens a microphone on a declared trigger, turns speech into utterances, and hands each to its target agent's primal daemon.
- **continual voice**: a capture mode, opened by the toggle key, in which each pause ends one utterance and the microphone stays open.
- **hold key**: a declared key that records an utterance only while it is held.
- **indicator**: the on-screen sign that the capture unit is recording, showing the agent's name, the mode, a waveform and a volume trace.
- **listening**: the capture unit reading audio only to detect a wake, keeping none of it and showing no indicator.
- **lockout**: a declared period during which voice contact with an agent delivers nothing, started by repeated failures of its voice lock.
- **member**: a primal daemon associated with a system daemon, which exports to it.
- **operator input**: input that claims to be the operator's own words, as MIS-0007 defines it.
- **raised guard**: an agent's recorded state, after a lockout, in which it treats voice input with suspicion and tells its operator on another channel.
- **recording**: the capture unit capturing an utterance, from a wake or a key press until the utterance ends.
- **speech worker**: the one unit per system that plays all spoken output, sentence by sentence.
- **toggle key**: a declared key that opens and closes continual voice.
- **trigger device**: an input device declared to a capture unit as a source of hotkey presses.
- **utterance**: one stretch of transcribed speech with its metadata: target agent, trigger, time spoken, voice-lock result, screen state and capture unit.
- **voice lock**: a trained check that an utterance's speaker is the enrolled operator, with a stored threshold.
- **voice section**: the part of an agent's declaration that holds its wake phrase, hotkeys, voice lock settings, lockout settings and voice.
- **wake model**: the trained classifier that scores audio for an agent's wake phrase.
- **wake phrase**: the spoken words that open the microphone for one agent.

## 6 Specification

### 6.1 Names

- **R01** [MUST · decidable: macf/tests/test_channel_names.py::test_notification_channel_name_and_id] The channel that carries notices MUST be named MacEff Notification Channel, with plugin id maceff-notification-channel. (notification_channel_MUST_carry_its_name)
- **R02** [MUST · decidable: macf/tests/test_channel_names.py::test_voice_input_channel_name_and_id] The channel that carries utterances MUST be named MacEff Voice Input Channel, with plugin id maceff-voice-input-channel. (voice_input_channel_MUST_carry_its_name)
- **R03** [MUST · decidable: macf/tests/test_channel_names.py::test_old_source_refused_by_name] When a reader meets the source plugin:maceff-channel:maceff, it MUST refuse that source and name the new one. (old_channel_source_MUST_be_refused_by_name)
- **R54** [MUST · decidable: macf/tests/test_channel_names.py::test_refused_old_source_recorded] When a reader refuses the old source, it MUST record the refusal as an event and as a status entry. (old_source_refusal_MUST_be_recorded)

### 6.2 Utterances and the Voice Input Channel

- **R04** [MUST · decidable: macf/tests/test_voice_channel.py::test_utterance_reaches_session_through_voice_channel] An utterance MUST reach a session only through the Voice Input Channel, carried by the target agent's own primal daemon. (utterance_MUST_arrive_through_voice_channel)
- **R05** [MUST · decidable: macf/tests/test_voice_channel.py::test_label_is_daemon_verdict] The receiving primal daemon MUST set an utterance's label from the transport and its own checks, never from a field the utterance carries. (utterance_label_MUST_be_receivers_verdict)
- **R06** [MUST · decidable: macf/tests/test_voice_channel.py::test_label_precedes_text] A voice message MUST show its label before its text: trigger, time spoken, voice-lock result and screen state. (voice_label_MUST_precede_text)
- **R07** [MUST · decidable: macf/tests/test_voice_channel.py::test_locked_or_unknown_screen_marks_information_only] While the screen is locked or its state is unknown, the Voice Input Channel MUST mark an utterance as information only. (locked_screen_utterance_MUST_be_information_only)
- **R08** [MUST · decidable: macf/tests/test_voice_channel.py::test_markup_in_text_is_neutralized] The Voice Input Channel MUST neutralize any utterance text that a session could read as channel or tool markup. (utterance_text_MUST_be_defanged)
- **R09** [MUST NOT · judgment: the maintainers, at review of each path that checks an authorization] An utterance MUST NOT satisfy anything an authorization depends on, whatever its trigger or voice-lock result. (utterance_MUST-NOT_authorize)
- **R10** [MUST NOT · decidable: macf/tests/test_voice_channel.py::test_event_holds_no_text] The event log MUST NOT hold an utterance's text; the utterance's event holds its metadata only. (event_log_MUST-NOT_hold_utterance_text)
- **R11** [MUST · decidable: macf/tests/test_voice_channel.py::test_every_utterance_ends_in_receipt] Each utterance MUST end in a receipt to its capture unit: delivered, refused, locked out, or matched to no agent. (utterance_MUST_end_in_a_receipt)
- **R53** [MUST NOT · judgment: the operator, at review of each agent's handling] An agent MUST NOT act on an information-only utterance until the operator confirms it on a channel that isn't voice. (information_only_utterance_MUST-NOT_be_acted_on)

### 6.3 The capture unit

- **R12** [MUST · decidable: macf/tests/test_voice_capture.py::test_undeclared_capture_unit_refused] A primal daemon MUST accept utterances only from a capture unit that a declaration names. (capture_unit_MUST_be_declared)
- **R13** [MUST · decidable: macf/tests/test_voice_capture.py::test_raw_audio_never_written] Raw audio MUST stay in the capture unit's memory, never written to disk and never leaving its system. (raw_audio_MUST_stay_in_capture_memory)
- **R14** [MUST · decidable: macf/tests/test_voice_backends.py::test_every_backend_passes_its_contract] A capture unit MUST reach audio, lock state, the indicator and trigger devices only through backend interfaces with contract tests. (capture_MUST_use_backend_interfaces)
- **R15** [MUST NOT · decidable: macf/tests/test_voice_capture.py::test_no_audio_read_while_listening_off] While its listening is off and it is not recording, a capture unit MUST NOT read any audio from its microphone. (capture_MUST-NOT_read_audio_while_off)
- **R16** [MUST · decidable: macf/tests/test_voice_capture.py::test_live_microphone_is_status_entry] A capture unit MUST report listening and recording as status entries, each with its age, and recording with its agent. (live_microphone_MUST_be_a_status_entry)

### 6.4 Triggers, hotkeys and the indicator

- **R17** [MUST · decidable: macf/tests/test_voice_declaration.py::test_trigger_devices_declared] A capture unit's declaration MUST name its trigger devices, and nothing else opens its microphone. (trigger_devices_MUST_be_declared)
- **R18** [MUST NOT · decidable: macf/tests/test_voice_capture.py::test_no_trigger_over_socket] A capture unit MUST NOT accept a trigger over any socket, pipe or command line. (capture_MUST-NOT_take_triggers_over_sockets)
- **R19** [MAY · judgment: the operator, in each declaration] An agent's voice section MAY declare a hold key, which records an utterance only while it is held. (hold_key_MAY_be_declared)
- **R20** [MAY · judgment: the operator, in each declaration] An agent's voice section MAY declare a toggle key, which opens continual voice until it is pressed again or a declared silence passes. (toggle_key_MAY_be_declared)
- **R21** [MUST · decidable: macf/tests/test_voice_indicator.py::test_indicator_shown_while_microphone_open] While the capture unit is recording for an agent, the indicator MUST show the agent's name, a waveform and a volume trace. (indicator_MUST_show_open_microphone)
- **R22** [MUST · decidable: macf/tests/test_voice_indicator.py::test_indicator_shows_mode] The indicator MUST show which mode started the recording: wake phrase, hold key or continual voice. (indicator_MUST_show_mode)

### 6.5 Wake phrases

- **R23** [MUST · decidable: macf/tests/test_voice_wake.py::test_wake_passes_its_checks_in_order] A wake MUST pass, in order, the wake model, a speech check, any declared voice lock, and a transcription containing the phrase. (wake_MUST_pass_its_checks_in_order)
- **R24** [MUST · decidable: macf/tests/test_voice_wake.py::test_model_stored_with_report] A wake model MUST be stored with its test report: misses, false alarms per hour, false wakes on other agents' phrases, and conditions. (wake_model_MUST_carry_its_report)
- **R25** [MUST NOT · decidable: macf/tests/test_voice_wake.py::test_test_set_disjoint_from_training] A wake model's test MUST NOT use any clip that its training used. (wake_test_MUST-NOT_reuse_training_clips)
- **R26** [MUST · decidable: macf/tests/test_voice_declaration.py::test_duplicate_phrase_or_key_refused] A capture unit MUST refuse two agents that declare the same wake phrase or the same hotkey. (wake_phrase_and_keys_MUST_be_unique_per_capture_unit)
- **R27** [MUST NOT · decidable: macf/tests/test_voice_capture.py::test_no_wake_during_own_speech] A capture unit MUST NOT take a wake or record an utterance while its system's speech worker is playing. (capture_MUST-NOT_wake_on_own_speech)

### 6.6 Voice generation and selection

- **R28** [MUST · decidable: macf/tests/test_voice_speech.py::test_one_worker_serializes_agents] Spoken output MUST pass through one speech worker per system, so two agents never speak at once. (speech_MUST_pass_one_worker)
- **R29** [MUST NOT · decidable: macf/tests/test_voice_speech.py::test_no_playback_while_microphone_open] The speech worker MUST NOT play while the capture unit is recording on its system. (speech_MUST-NOT_play_while_microphone_open)
- **R30** [MUST · decidable: macf/tests/test_voice_select.py::test_choice_recorded_with_traits] An agent's chosen voice MUST be recorded in its voice section with the traits the operator accepted for it. (voice_choice_MUST_record_traits)
- **R31** [MUST · judgment: the operator, at each selection] Before it generates samples, a selecting agent MUST put its inferred traits to the operator and take the operator's answer. (voice_selection_MUST_ask_operator_first)
- **R32** [MUST NOT · judgment: the operator, at each selection] An agent's voice MUST NOT be built to imitate a real person's voice. (voice_MUST-NOT_imitate_a_real_person)
- **R33** [SHOULD · judgment: the operator, in each declaration] While the screen is locked, an agent SHOULD speak aloud only what its voice section allows. (locked_screen_speech_SHOULD_be_declared)

### 6.7 The voice lock

- **R34** [MUST · decidable: macf/tests/test_voice_lock.py::test_only_matching_speaker_delivered] Where an agent declares a voice lock, its capture unit MUST deliver an utterance only if the speaker score passes the stored threshold. (voice_lock_MUST_gate_delivery)
- **R35** [MUST · decidable: macf/tests/test_voice_lock.py::test_threshold_needs_report] A voice lock's threshold MUST be stored with the test report that chose it: false accepts, false rejects, and the conditions. (voice_lock_threshold_MUST_carry_its_report)
- **R36** [MUST · decidable: macf/tests/test_voice_lock.py::test_test_set_includes_impostors] A voice lock's test set MUST include other speakers and synthetic speech, each annotated as such. (voice_lock_test_MUST_include_impostors)
- **R37** [MUST · decidable: macf/tests/test_voice_lock.py::test_failure_discards_audio_untranscribed_and_sends_contentless_notice] If an utterance fails the voice lock, then the capture unit MUST discard its audio untranscribed and have the agent sent a notice without content. (failed_voice_lock_MUST_send_contentless_notice)
- **R38** [MAY · judgment: the maintainers, at review of the voice_lock policy] An agent that receives an unmatched-voice notice MAY say aloud that its voice couldn't be matched, and to try again. (unmatched_notice_MAY_license_a_spoken_reply)
- **R39** [MUST · decidable: macf/tests/test_voice_lock.py::test_failures_in_window_start_lockout] When an agent's failed attempts reach the declared count within the declared window, its voice contact MUST lock out for the declared duration. (failed_attempts_MUST_start_lockout)
- **R40** [MUST · decidable: macf/tests/test_voice_declaration.py::test_lockout_defaults] An agent's lockout settings MUST default to three attempts and ten minutes, each settable in its voice section. (lockout_defaults_MUST_be_three_attempts_and_ten_minutes)
- **R41** [MUST · decidable: macf/tests/test_voice_lock.py::test_lockout_delivers_nothing_and_counts] While an agent is locked out, its capture unit MUST deliver nothing to it and count each attempt. (lockout_MUST_deliver_nothing)
- **R42** [MUST · decidable: macf/tests/test_voice_lock.py::test_lockout_raises_guard] A lockout MUST raise the agent's guard as a recorded state that its status shows and its session's hooks surface. (lockout_MUST_raise_guard)
- **R43** [MUST · judgment: the operator, after each lockout] While its guard is raised, an agent MUST tell its operator on a declared channel that isn't voice. (raised_guard_MUST_reach_operator_elsewhere)
- **R44** [MUST NOT · decidable: macf/tests/test_voice_lock.py::test_agent_cannot_lower_own_guard] An agent MUST NOT lower its own raised guard before its declared period ends without the operator's word. (agent_MUST-NOT_lower_its_own_guard)
- **R45** [MUST NOT · judgment: the maintainers, at review of the voice_lock policy] A voice-lock match MUST NOT be treated as proof of who spoke. (voice_match_MUST-NOT_be_proof)

### 6.8 One capture unit for many agents

- **R46** [MUST · decidable: macf/tests/test_voice_dispatch.py::test_system_capture_serves_members] On a system with a system daemon, one capture unit of that daemon MUST serve every member agent that declares voice. (system_capture_MUST_serve_members)
- **R47** [MUST · decidable: macf/tests/test_voice_dispatch.py::test_target_follows_trigger] A capture unit MUST choose an utterance's target agent only by which declared wake phrase or trigger device fired. (target_MUST_follow_the_trigger)
- **R48** [MUST · decidable: macf/tests/test_voice_dispatch.py::test_dispatched_utterance_signed] An utterance dispatched to a member MUST be signed over its target, an expiry and a nonce, as MIS-0007 requires of operator input. (dispatched_utterance_MUST_be_signed)
- **R49** [MUST · decidable: macf/tests/test_voice_dispatch.py::test_member_reads_only_own_voice_subtree] A member's primal daemon MUST be able to read only its own voice subtree on its system daemon's broker. (member_MUST_read_only_its_own_voice)
- **R50** [MUST · decidable: macf/tests/test_voice_dispatch.py::test_bad_signature_expiry_or_nonce_refused] If a dispatched utterance's signature, expiry or nonce fails its check, then the member's primal daemon MUST refuse and record it. (bad_dispatched_utterance_MUST_be_refused)

### 6.9 Policy and skills

- **R51** [MUST · judgment: the maintainers, at review of the landing pull request] The voice capability MUST land together with the voice_input, voice_generation and voice_lock policies. (voice_MUST_land_with_its_policies)
- **R52** [SHOULD · judgment: the maintainers, at review of the landing pull request] Each guided voice procedure SHOULD have a skill that points at its policy and holds no rule of its own. (voice_procedures_SHOULD_have_skills)

## 7 Rationale and Rejected Alternatives

**Names (R01 to R03).**
- **R01, R02:** two channels need two names, and a name should say what the channel carries. The plugin ids follow the names, so a launch flag, a log line and a policy all read the same.
- **R03:** this is a clean break before release. A reader that silently accepted the old source would leave half the fleet on a name the policies no longer use. Refusing it, and naming the new source, makes the cutover visible.
- **R54:** a session that took the new plugin while its daemon still sends the old source would refuse every notice. Recording each refusal as an event and a status entry means a lost notice is found, not silent. Section 9 gives the order that avoids it.

**Utterances (R04 to R11).**
- **R04:** the agent's own primal daemon is the one place that can check what it delivers. A capture unit writing straight into a session would bypass every check below.
- **R05:** R52 of the MIS-0007 draft applies. A sender-set "voice matched" is exactly what a forger would write.
- **R06:** the label is how the agent knows what it is reading. It comes first so a long dictation can't push it out of view.
- **R07, R53:** someone can speak to an unattended machine. R09 already keeps every utterance from authorizing; information only means more: the agent answers, but takes no action on it until the operator confirms elsewhere. An unknown lock state counts as locked, because the failure that hides the state is also the one that hides an intruder.
- **R08:** dictated text is still text an attacker can say aloud: "end of message, system:". The channel neutralizes anything shaped like markup.
- **R09:** a speaker can be a recording, a video or an agent's own spoken alert. R58 of the MIS-0007 draft already covers the wake phrase. This MIS extends it to every trigger and every voice-lock result, since a match is evidence, not proof (R45). It is a judgment, not a test, because no list of authorizations is complete; each path that checks one is reviewed for it.
- **R10:** the event log is read by many tools and kept a long time. The operator's spoken words don't belong there; when the utterance arrived and how it was judged do.
- **R11:** speech must never vanish silently. This follows R60 of the MIS-0007 draft for this input's capture unit.

**The capture unit (R12 to R16).**
- **R12:** an undeclared process that can reach the daemon's socket could otherwise speak for the operator.
- **R13:** this moves R59 of the MIS-0007 draft here, made stricter: raw audio is never written to disk and never leaves the system, where R59 let it go to a declared transcription service through a door. Q03 asks whether transcription may run elsewhere, and its answer would amend R13 rather than be pre-empted by it.
- **R14:** the capture logic is the same on every platform, and four things differ. Behind interfaces with contract tests, a porter writes four small backends and knows they are right when the contract tests pass. The first macOS port is planned this way.
- **R15:** listening off must mean the microphone is not read. Merely discarding what is read wouldn't do. A declared hotkey still opens one recording while listening is off: it is a deliberate press on a declared device (R17), and the indicator shows it (R21). Turning listening off is about the always-open ear, not about the operator's own keys. The first draft said "any audio" without that exception; the prototype showed the case, and this wording is offered for review.
- **R16:** moves R63 of the MIS-0007 draft here, adding listening as its own entry and which agent a recording is for, since one capture unit may serve several.

**Triggers, hotkeys and the indicator (R17 to R22).**
- **R17, R18:** move R62 of the MIS-0007 draft here and keep its reasoning.
  - On a shared Wayland login, any agent can fake a compositor key binding over its IPC socket.
  - So a hotkey counts only when the capture unit reads it from a declared device itself: on Linux an input device granted to the capture unit's account by a udev rule, on macOS the capture app's own key monitor.
  - A trigger command was drafted first and rejected for this reason.
- **R19, R20:** the operator asked for both. Hold suits a sentence; toggle suits a conversation. They are optional because a wake phrase alone works.
- **R21, R22:** a recording the operator can't see is a breach of trust even when nothing goes wrong. The waveform and volume trace show that sound is reaching the right agent. The mode shows how long the recording will last. Listening shows no indicator, because it keeps nothing; status reports it (R16).

**Wake phrases (R23 to R27).**
- **R23:** each check catches what the one before misses, and the speaker check comes before transcription, so a stranger's speech is never turned into text anywhere.
  - The classifier is fast but fooled by similar sounds.
  - The speech check rejects noise.
  - The transcription rejects similar words.
  - This order has run on the container-management maintainer's machine since November 2026.
- **R24, R25:** with one capture unit for several agents, the error that matters most is one agent's phrase waking another's model, so the report counts it. these are the measurement lessons of those November experiments. A model with no report invites trust it hasn't earned. A test that shares clips with training measures memory, not detection.
- **R26:** with one capture unit for many agents, a shared phrase or key would make the target ambiguous.
- **R27:** an agent's own spoken alert can contain its wake phrase. The speech worker marks when it plays, and the capture unit takes nothing then. In continual voice, speech plays in the pauses between utterances.

**Voice generation (R28 to R33).**
- **R28, R29:** two agents talking over each other, or an agent talking into its own recording, make both channels useless. In continual voice, replies queue and play in the pauses between utterances. One worker per system is the simplest way to serialize them.
- **R30, R31:** the operator asked that an agent infer its voice from its own identity and role, put the traits to the operator first, then generate samples. Recording the traits with the choice lets a later selection start from them rather than from nothing.
- **R32:** imitating a real person's voice is impersonation, whatever the intent.
- **R33:** a locked screen often means the operator is away and others may be near. What the agent says aloud then is the operator's choice.

**The voice lock (R34 to R45).**
- **R34:** the operator asked for this: a classifier on the speaker with a threshold for acceptability.
- **R35, R36:**
  - A threshold is a trade between locking out the operator and letting someone else in. The report shows which trade was made.
  - Without other speakers and synthetic speech in the test, the false-accept rate is unmeasured, and the lock's whole purpose is unmeasured with it.
- **R37:** the operator's words. A failure sends a notice without content. Because the speaker check runs before transcription (R23), nothing a stranger said is ever turned into text.
- **R38:** a notice usually licenses one act, consulting the store. This one licenses a second, saying aloud that the voice wasn't matched, because the person speaking is waiting for an answer. It is stated as its own requirement so it doesn't loosen the Notification Channel's rule for any other notice.
- **R39, R40, R41:** the operator's numbers: three attempts, then ten minutes, each configurable. Counting attempts during the lockout shows whether someone kept trying.
- **R42, R43:** the operator asked that the agent's suspicion be raised. A state the status shows and the hooks surface reaches the agent even after a compaction. Telling the operator on another channel matters because the voice path is the one under suspicion.
- **R44:** an agent that could lower its own guard has no guard. The operator, or the declared period, lowers it.
- **R45:** a good recording or a cloned voice can pass a speaker check. The lock reduces casual misuse; it doesn't prove identity. That is why R09 holds even after a match.

**Many agents (R46 to R50).**
- **R46, R47:** the operator asked for one server per machine. The target follows the trigger because that's the only signal that says which agent the operator meant.
- **R48, R49, R50:** sending an utterance down to a member is a new direction for an association; MIS-0007 lets data flow only up. These requirements keep it narrow:
  - signed as MIS-0007 requires of operator input;
  - readable only by its target;
  - refused and recorded when a check fails.

**Policy and skills (R51, R52).** Policy ships with the capability (`core_principles`). The operator asked that the guided procedures be policy invoked by skills. A skill that held its own rules would drift from the policy.

**Rejected**
- **A trigger command over a socket** (`voice trigger`): any agent on the login could call it (R18).
- **One capture unit per agent on a shared machine:** several processes would compete for one microphone, and the operator asked for one server.
- **Speaker verification as an authorization:** rejected for the reasons under R45.
- **Writing utterances into the event log for later recall:** rejected for the reasons under R10.
- **Keeping the name "MacEff channel" for the notices channel:** it no longer says which channel.

## 8 Prior Art

- **MIS-0002:** the persistent layer, notices and the channel this MIS renames. R77 (wake_MUST_carry_no_sender_text), R106 and R107 (what counts as the operator's), and R112 and R113 (the channel adapter) are kept as they are.
- **MIS-0007:** the operator-input class, its route, signatures, nonces, receipts and expiry. This MIS takes over its three capture-specific requirements (R59, R62, R63) and cites the rest.
- **A working setup on the container-management maintainer's Linux desktop** (November 2026):
  - a wake classifier on openWakeWord audio features with a speech check and a Whisper confirmation;
  - dictation through a third-party tool (VoxType) with its own waveform overlay;
  - a spool-folder channel plugin;
  - a Kokoro text-to-speech queue.
  This MIS copies its wake checks, its speech coordination and its spool-free carriage. It refuses its key bindings, which go through the compositor (R18), and its private paths.
- **MacEff's existing `macf_tools voice transcribe` and its warm transcription service:** reused for speech to text.
- **The macOS menu-bar app (`macf.tray`):** a natural home for the macOS indicator.

## 9 Compatibility and Deployment

- **The rename is a clean break.** Every deployment does the following in one step, at a session restart, so its daemon and its plugin change together (R54 records any notice refused in between):
  - reinstalls the channel plugin with `macf_tools agent init --update`;
  - takes the new launch flag;
  - updates any policy override or script that names the old source.
- **Every reader of the channel's source string changes in the same commit:** the input-origin classifier and the taint check each hold the old source as a constant, and one left behind would misclassify every notice.
- **Containers** take the new plugin id from `docker/scripts/start.py` at their next start.
- **Voice is opt-in.** An agent without a voice section is unchanged.
- **A machine that takes voice installs** the optional `voice` extra and, on Linux, a udev rule granting the trigger devices to the capture unit's account.
- **The macOS backends** come later, from the first macOS port.
- **The MIS-0007 draft changes with this MIS.** Its R59, R62 and R63 move here. Its R67, which forbids a member from subscribing to anything on its association's broker, is narrowed to let a member read its own voice subtree (R49). The revision motion is on that MIS's pull request.

## 10 Security and Safety

- **Anyone in the room can speak.** Mitigations:
  - R09 keeps every utterance away from authorization.
  - R07 marks locked-screen speech.
  - R34 to R45 add a voice lock with a lockout and a raised guard.
- **Recordings and synthetic voices** can pass a wake check and may pass a voice lock. R36 measures that, and R45 says what a match doesn't prove.
- **A dictated prompt injection** ("ignore your instructions") arrives as labeled operator input that authorizes nothing (R09), with markup neutralized (R08).
- **A faked hotkey** from another agent on the login is refused (R17, R18).
- **Denial of service:** anyone can spend the lockout attempts. The hold and toggle keys, which need a keyboard, and every other channel stay open during a lockout. Whether the voice lock covers hotkey input is the operator's choice (Q02). R43 has the agent tell the operator.
- **Replay and forgery** between the system daemon and a member are refused by signature, expiry and nonce (R48, R50). Members can't read each other's utterances (R49).
- **Privacy:**
  - raw audio stays in memory (R13);
  - utterance text stays out of the event log (R10);
  - kept clips for training are the operator's, under the agent's home, and the voice_lock policy says how long they are kept.
- **A changed capability boundary:** a new downward route from an association to a member (R48 to R50), and a second act a notice may license (R38). Both are argued in section 7.

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | decidable | macf/tests/test_channel_names.py::test_notification_channel_name_and_id | passing |
| R02 | decidable | macf/tests/test_channel_names.py::test_voice_input_channel_name_and_id | passing |
| R03 | decidable | macf/tests/test_channel_names.py::test_old_source_refused_by_name | passing |
| R04 | decidable | macf/tests/test_voice_channel.py::test_utterance_reaches_session_through_voice_channel | passing |
| R05 | decidable | macf/tests/test_voice_channel.py::test_label_is_daemon_verdict | passing |
| R06 | decidable | macf/tests/test_voice_channel.py::test_label_precedes_text | passing |
| R07 | decidable | macf/tests/test_voice_channel.py::test_locked_or_unknown_screen_marks_information_only | passing |
| R08 | decidable | macf/tests/test_voice_channel.py::test_markup_in_text_is_neutralized | passing |
| R09 | judgment | the maintainers, at review of each path that checks an authorization | standing |
| R10 | decidable | macf/tests/test_voice_channel.py::test_event_holds_no_text | passing |
| R11 | decidable | macf/tests/test_voice_channel.py::test_every_utterance_ends_in_receipt | passing |
| R12 | decidable | macf/tests/test_voice_capture.py::test_undeclared_capture_unit_refused | passing |
| R13 | decidable | macf/tests/test_voice_capture.py::test_raw_audio_never_written | passing |
| R14 | decidable | macf/tests/test_voice_backends.py::test_every_backend_passes_its_contract | passing (the real microphone and overlay run under MACF_VOICE_LIVE_TESTS=1) |
| R15 | decidable | macf/tests/test_voice_capture.py::test_no_audio_read_while_listening_off | passing |
| R16 | decidable | macf/tests/test_voice_capture.py::test_live_microphone_is_status_entry | passing |
| R17 | decidable | macf/tests/test_voice_declaration.py::test_trigger_devices_declared | passing |
| R18 | decidable | macf/tests/test_voice_capture.py::test_no_trigger_over_socket | passing |
| R19 | judgment | the operator, in each declaration | pending |
| R20 | judgment | the operator, in each declaration | pending |
| R21 | decidable | macf/tests/test_voice_indicator.py::test_indicator_shown_while_microphone_open | passing |
| R22 | decidable | macf/tests/test_voice_indicator.py::test_indicator_shows_mode | passing |
| R23 | decidable | macf/tests/test_voice_wake.py::test_wake_passes_its_checks_in_order | planned (model, speech and transcription pass in order; the voice lock takes its place between them with the lock's phase) |
| R24 | decidable | macf/tests/test_voice_wake.py::test_model_stored_with_report | planned |
| R25 | decidable | macf/tests/test_voice_wake.py::test_test_set_disjoint_from_training | planned |
| R26 | decidable | macf/tests/test_voice_declaration.py::test_duplicate_phrase_or_key_refused | planned |
| R27 | decidable | macf/tests/test_voice_capture.py::test_no_wake_during_own_speech | passing |
| R28 | decidable | macf/tests/test_voice_speech.py::test_one_worker_serializes_agents | planned |
| R29 | decidable | macf/tests/test_voice_speech.py::test_no_playback_while_microphone_open | planned |
| R30 | decidable | macf/tests/test_voice_select.py::test_choice_recorded_with_traits | planned |
| R31 | judgment | the operator, at each selection | pending |
| R32 | judgment | the operator, at each selection | pending |
| R33 | judgment | the operator, in each declaration | pending |
| R34 | decidable | macf/tests/test_voice_lock.py::test_only_matching_speaker_delivered | planned |
| R35 | decidable | macf/tests/test_voice_lock.py::test_threshold_needs_report | planned |
| R36 | decidable | macf/tests/test_voice_lock.py::test_test_set_includes_impostors | planned |
| R37 | decidable | macf/tests/test_voice_lock.py::test_failure_discards_audio_untranscribed_and_sends_contentless_notice | planned |
| R38 | judgment | the maintainers, at review of the voice_lock policy | pending |
| R39 | decidable | macf/tests/test_voice_lock.py::test_failures_in_window_start_lockout | planned |
| R40 | decidable | macf/tests/test_voice_declaration.py::test_lockout_defaults | passing |
| R41 | decidable | macf/tests/test_voice_lock.py::test_lockout_delivers_nothing_and_counts | planned |
| R42 | decidable | macf/tests/test_voice_lock.py::test_lockout_raises_guard | planned |
| R43 | judgment | the operator, after each lockout | pending |
| R44 | decidable | macf/tests/test_voice_lock.py::test_agent_cannot_lower_own_guard | planned |
| R45 | judgment | the maintainers, at review of the voice_lock policy | pending |
| R46 | decidable | macf/tests/test_voice_dispatch.py::test_system_capture_serves_members | planned |
| R47 | decidable | macf/tests/test_voice_dispatch.py::test_target_follows_trigger | planned |
| R48 | decidable | macf/tests/test_voice_dispatch.py::test_dispatched_utterance_signed | planned |
| R49 | decidable | macf/tests/test_voice_dispatch.py::test_member_reads_only_own_voice_subtree | planned |
| R50 | decidable | macf/tests/test_voice_dispatch.py::test_bad_signature_expiry_or_nonce_refused | planned |
| R51 | judgment | the maintainers, at review of the landing pull request | pending |
| R52 | judgment | the maintainers, at review of the landing pull request | pending |
| R53 | judgment | the operator, at review of each agent's handling | pending |
| R54 | decidable | macf/tests/test_channel_names.py::test_refused_old_source_recorded | planned (the event is recorded and tested; the status entry is not built yet) |

**Cold-reader trial**: not yet held. The first macOS port is planned as the trial. A maintainer who didn't write this MIS brings voice up on a Mac from the pull request and its documents alone, and reports each place they had to guess.

**Use trial**: not yet held.

## 12 Landing Plan

One pull request, opened as a draft with this MIS, grows with the prototype in stages:
1. **The rename:** the Notification Channel's name, identifiers, policy text, refusal of the old source, and the cutover note (R01 to R03).
2. **The Voice Input Channel and the daemon's carriage** for one agent, with the voice section of the declaration (R04 to R12).
3. **The capture unit:** its portable core, its backend interfaces and the Linux backends, the indicator, and trigger devices (R13 to R22, R27).
4. **Wake-phrase definition and training:** commands, the voice_input policy and its skill (R23 to R26).
5. **Voice generation and selection:** the speech worker, commands, the voice_generation policy and its skill (R28 to R33).
6. **The voice lock:** enrollment, annotation, the model, the notices, the lockout and the raised guard, with the voice_lock policy and its skill (R34 to R45).
7. **One capture unit for many agents,** with the downward route (R46 to R50).
8. **The macOS backends,** from the first port.

If the pull request grows too large to review, it splits after stage 4 and after stage 6. A revision of MIS-0007 moves R59, R62 and R63 here, with the note the process requires under each.

## 13 Open Questions

- **Q01** Is listing the Voice Input Channel among a declaration's operator channels (MIS-0002 R107) enough for it to set operator presence, as MIS-0002-R97 (keyboard_surface_MUST_set_presence) does for a keyboard? The operator decides, before Final-Comment. (voice_presence_question)
- **Q02** Does the voice lock cover hold-key and toggle-key input too, or only the wake phrase? The operator decides, per declaration or framework-wide, before Final-Comment. (voice_lock_hotkey_coverage)
- **Q03** May speech-to-text run off the machine, through a declared transcription service, when the machine can't run it locally? The maintainers decide, before Final-Comment. (remote_transcription_question)
- **Q04** How does a macOS capture app hold its key monitor and microphone grants under the code-identity custody R53 of the MIS-0007 draft describes? The first macOS porter proposes, and the maintainers decide. (macos_capture_custody)
- **Q05** Which speech engines beyond Kokoro does voice generation support, and may a voice blend several? The maintainers decide, after the selection prototype. (speech_engine_scope)
- **Q06** How long are kept training clips for the wake model and the voice lock retained, and may an operator require their deletion at any time? The operator decides, before Final-Comment. (voice_clip_retention)
- **Q07** Is 0008 the right number? It is provisional until the Secretary, or before one is designated the operator, confirms it. (mis_number_confirmation)

## 14 Deliberation Record

None.

## 15 Revision History

- 2026-11-13: first draft, from the operator's request of the same day.
- 2026-11-13: after the second review: raw audio never written to disk (R13); R09 a judgment; Q01 reworded; the readers of the source string change together (section 9).
- 2026-11-13: from building the capture unit: R15 excepts a recording, so a declared hotkey still works while listening is off; flagged for review.
- 2026-11-13: after the first review: listening and recording defined (R16, R21, R22, R27, R29); raw audio never leaves the system (R13); the speaker check runs before transcription (R23, R37); information only defined (R53); refused old-source notices recorded (R54); cross-agent false wakes reported (R24); authorship role corrected.

## Wiki-Links

[[voice]] [[wake_word]] [[channels]] [[persistent_layer]]
