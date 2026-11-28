# MIS-0012: The Attention Stack and Interrupt Model

**Number**: 0012
**Type**: Standards
**Status**: Draft
**Authors**: the repo owner, who asked for it on 2026-10-14; drafted by the container-management maintainer
**Secretary**: none
**Deliberation**: pending
**Created**: 2026-11-28
**Updates**: none
**Supersedes**: none
**Lands-in**: framework/policies/base/development/task_management.md, framework/policies/base/operations/instruction_language.md, macf/src/macf/hooks/handle_user_prompt_submit.py, macf/src/macf/utils/input_origin.py, macf/src/macf/pd/daemon.py, macf_tools task trace
**Resolution**: none

---

## 1 Summary

MIS-0002 decides how a notice or a message reaches a session. Nothing decides what the agent does with it once it arrives: whether it outranks the work it interrupted, what waits while it is served, when the agent may go back, and what counts as finishing it. Today those rules live partly in policy (`task_management` section 16, `instruction_language` section 4) and partly in each agent's memory, and the framework records an operator's ask only as a prompt. This MIS proposes an attention stack: each operator message opens a frame, classified by where it came from; a remote message is acknowledged at once; the frame closes only on a recorded return; open frames survive a compaction and show on every hook line while they are open. It concerns every agent an operator directs by interruption, and the operator who relies on the agent to hold the work they set down. This is a first draft for the maintainers to argue, not a finished design.

## 2 Motivation

The repo owner opened this question on 2026-10-14, after an ask was lost: "Should this and maybe an increase in scope to a MacEff Attention Stack Frame Interrupt model been the subject of the next MIS after the amail system? ... Yes, I suspect that your direct experience with MIS-0002 will be helpful in constraining the draft." Earlier, in a cycle of September 2026, the repo owner had named the failure pattern: "You seem to default to a WORK QUEUE model which is wrong for IL interruptions."

The lived failures, each with its evidence tier (`empiricism` policy):

1. **An operator ask with no frame** (incident in a session transcript, 2026-10-14). An ask to examine all in-progress work was noted on the interrupted task instead of opening a frame of its own. The agent closed fifteen tasks, returned to its own pull request without reporting, then opened a self-chosen review on top. The report arrived late, at the end of a long message. The task command's "return to" hint named an unrelated frame.
2. **An ask queued behind a refactor** (incident, the repo owner's words above). An operator ask waited through four exchanges behind work the agent had chosen before the ask arrived.
3. **An obligation written on a closed frame** (incident, 2026-10-14). A root test run was recorded on a task after that task completed. No open frame held it, and a weekly audit later found the run had never happened.
4. **A pause with no wake** (incident, 2026-10-12). A seat told to pause for some minutes ran on until the next mail, because only mail woke it. A timer interrupt was missing.
5. **An interrupt consumed by the wrong reader** (incident, 2026-10-02). Reading a seat's mail as that seat took in its pickup box, so the seat's own wake never fired.
6. **Delivery into an open dialog** (observation, pane captures, 2026-10-14). Two seats sat on confirmation dialogs while mail waited for them, and mail had to be held by hand, because a keystroke wake would have typed into the dialog.
7. **An ask carried across a compaction only by the summary** (incident, 2026-10-14). A demonstration request from the evening before reached the next cycle only because a compaction summary happened to mention it.
8. **Idle while merges were owed** (incident, 2026-10-10). An agent paused while a pull request became mergeable, and nothing woke it when it did.

The repo owner's direction of 2026-10-17 sets the shape of the remote case: "When the operator is at the terminal watching the expectation of a quicker servicing is higher than when it is remote - this is because the operator can see what you are working on directly in the terminal", and Telegram is operator class "with sub-priority as 'remote'". "Different channels have different expectations of response latency."

On the acknowledgment: "at least with the hook-trace feature off, the Telegram channel is not privy to every tool call. It is thus important on Telegram to quickly notify the operator that you see his request - ... use the moving eyes emoji as a reaction to the Telegram message - we should make that part of proper protocol."

On the routine: "Often the agent is in the middle of a sprint when the remote interruption occurs - the best course of action is to react immediately, then prepare to push the current attention frame, and start servicing the operator's perhaps detailed query in full before returning to the previous frame." And: "In the terminal the operator expects the FULL synchronous attention to their prompt - optionally the previous frame may be delegated - but a return is owed."

On strategy: "The agent may strategize here such as delegating parts of either service to parallel subagents or handling synchronously with full attention - or a mixture - policy should provide guidance."

## 3 Goals and Non-Goals

**Goals**
- Every operator message opens a frame the framework records, classified by origin, with the handle a reply needs.
- A remote operator message is acknowledged on its own channel before the agent does anything else.
- An operator frame closes only on a recorded return, and the frame below is named as owed next.
- Open frames survive a compaction and a restart, and the operator can see them while they are open.
- The latency from arrival to acknowledgment, first reply and return is measured per subclass, from the event log.
- The stack and interrupt rules live in framework policy every agent reads, not in each agent's memory.

**Non-goals**
- This MIS does not change how notices and wakes are delivered. MIS-0002 decides delivery.
- It does not choose an agent's work. The task system stays the work store, and a frame points at a task without copying it.
- It does not block a session's Stop. The enforcement is visibility and the recorded return, not a gate.
- It does not decide the voice presence modes, which belong to MIS-0008.

## 4 Guide-Level Explanation

An agent is three phases into a sprint when the operator writes on Telegram: "what happened to the indexer last night?". The prompt hook sees the message's origin, a declared operator channel of the remote subclass, and opens an operator frame holding the channel, the arrival time and the message's id, since Telegram keeps no history. The agent's first act is the eyes reaction on that message, and the framework records the acknowledgment. The agent notes the sprint's next step on the sprint task, which is the push, and serves the question in full. It replies on Telegram with the answer, and records the return with the reply's id. The frame closes, and the hook names the sprint as the frame owed next.

Had the operator typed the same question at the terminal, the frame would be of the terminal subclass. No reaction is owed, since the operator watches the turn begin, and the agent gives the question its whole attention until it answers. If a mail notice arrives while an operator frame is open, the agent finishes the operator's ask first; the notice waits, listed, and is not lost.

If the session compacts while the frame is open, the notice that reports what a compaction carried lists the open frame with its channel, its reply handle and its age, so the next cycle replies to the right message. While any operator frame is open, each hook line shows how many and the oldest one's age. When none is open, the line says nothing about frames.

## 5 Terms

- **frame**: one unit of attention the agent owes a return to, opened by an input and closed by its return or by a recorded disposal.
- **operator frame**: a frame opened by a message from the operator, as the operator's activity is told apart under MIS-0002-R107 and R121.
- **frame class**: the rank of a frame, taken from its input's origin: operator, a person's dialog the agent raised, agent mail, schedule, notification, or self-opened.
- **operator subclass**: terminal, for a prompt typed in the session; remote, for a message on a declared operator channel the operator cannot watch the session through.
- **acknowledgment**: a signal on a remote operator message's own channel that the agent has seen it, such as a reaction.
- **return**: the act that closes a frame: for an operator frame, a reply on the ask's channel or the terminal's final message naming it.
- **frame below**: the frame attention left when the current frame opened, owed a return once the current one closes.
- **masking**: holding lower-class inputs, listed and not lost, while a higher-class frame waits for its return.

## 6 Specification

### 6.1 Frames and their classes

- **R01** [MUST · decidable: macf/tests/test_attention_frames.py::test_an_operator_message_opens_a_frame] When the prompt hook takes an operator message, the framework MUST record an open operator frame naming its channel, arrival time and reply handle. (operator_message_MUST_open_frame)
- **R02** [MUST · decidable: macf/tests/test_attention_frames.py::test_the_class_comes_from_the_origin] The framework MUST take each frame's class from its input's origin, as MIS-0002-R121 reads the source, and never from the input's text. (frame_class_MUST_come_from_origin)
- **R03** [MUST NOT · decidable: macf/tests/test_attention_frames.py::test_notices_wakes_and_peers_never_open_an_operator_frame] A notice, a wake, a peer session's message or a task notification MUST NOT open an operator frame. (non_operator_input_MUST-NOT_open_operator_frame)
- **R04** [MUST · decidable: macf/tests/test_attention_frames.py::test_each_operator_channel_declares_its_subclass] The declaration MUST name each operator channel's subclass, terminal or remote. (operator_channel_MUST_declare_subclass)
- **R05** [MUST · decidable: macf/tests/test_attention_frames.py::test_a_new_message_opens_a_new_frame] When a new operator message arrives, the framework MUST open a new frame for it, while asks within one message share one frame. (each_operator_message_MUST_open_own_frame)
- **R06** [MUST NOT · decidable: macf/tests/test_attention_frames.py::test_a_frame_names_its_task_and_copies_nothing] A frame MUST NOT copy a task's contents, and it refers to the task it serves by the task's id. (frame_MUST-NOT_copy_task)
- **R07** [MUST · decidable: macf/tests/test_attention_frames.py::test_frames_come_from_the_event_log] The framework MUST derive open frames from events in the agent's event log, keeping no second ledger. (frames_MUST_derive_from_event_log)

### 6.2 Acknowledgment

- **R08** [MUST · decidable: macf/tests/test_attention_frames.py::test_a_remote_message_is_acknowledged_first] When an operator message arrives on a remote channel, the agent MUST acknowledge it on that channel before its first other act in the turn. (remote_message_MUST_be_acknowledged_first)
- **R09** [MUST · decidable: macf/tests/test_attention_frames.py::test_an_acknowledgment_is_recorded] When an operator message is acknowledged, the framework MUST record an event naming the frame and the acknowledgment's time. (acknowledgment_MUST_be_recorded)

### 6.3 Service and masking

- **R10** [MUST NOT · judgment: the Secretary, at review of the landed policy] While an operator frame waits for its return, the agent MUST NOT open a frame of its own choosing above it. (agent_MUST-NOT_self_open_above_operator_frame)
- **R11** [SHOULD · decidable: macf/tests/test_attention_frames.py::test_lower_notices_wait_listed_while_an_operator_frame_is_open] While an operator frame waits for its return, the persistent layer SHOULD hold lower-class notices and list them, losing none. (lower_notices_SHOULD_wait_while_operator_frame_open)
- **R12** [MUST · judgment: the head maintainer, at review of the landed policy] When the agent serves a terminal operator frame, it MUST give that frame synchronous attention until the frame's return. (terminal_frame_MUST_get_synchronous_attention)
- **R13** [MUST NOT · judgment: the head maintainer, at review of the landed policy] The agent MUST NOT count a delegated result as a frame's return until the agent has reviewed it. (delegation_MUST-NOT_discharge_return)

### 6.4 Return

- **R14** [MUST · decidable: macf/tests/test_attention_frames.py::test_an_operator_frame_closes_only_on_a_recorded_return] The framework MUST close an operator frame only on a recorded return or a recorded disposal. (operator_frame_MUST_close_on_return)
- **R15** [MUST · decidable: macf/tests/test_attention_frames.py::test_a_return_records_its_reply_and_time] When the agent records a return, the framework MUST record the reply's handle and the return's time. (return_MUST_record_reply_and_time)
- **R16** [MUST · decidable: macf/tests/test_attention_frames.py::test_a_return_names_the_frame_below] When a frame closes, the framework MUST name the frame below as the next frame owed. (return_MUST_name_frame_below)
- **R17** [MUST · decidable: macf/tests/test_attention_frames.py::test_a_return_says_resume_or_discard] Each return MUST say whether the frame below resumes or is discarded, and resume is the default. (return_MUST_say_resume_or_discard)
- **R18** [MAY · decidable: macf/tests/test_attention_frames.py::test_a_disposal_carries_its_reason] The agent MAY dispose of a frame by converting it to a task, absorbing it as a steer, deferring it or dropping it, recording a reason. (frame_MAY_be_disposed_with_reason)

### 6.5 Visibility and survival

- **R19** [MUST · decidable: macf/tests/test_attention_frames.py::test_the_hook_line_shows_open_operator_frames] While any operator frame is open, each hook line MUST show how many are open and the oldest one's age. (hook_line_MUST_show_open_operator_frames)
- **R20** [MUST NOT · decidable: macf/tests/test_attention_frames.py::test_the_hook_line_is_silent_with_no_frame] While no operator frame is open, the hook line MUST NOT spend any text on frames. (hook_line_MUST-NOT_report_empty_stack)
- **R21** [MUST · decidable: macf/tests/test_attention_frames.py::test_the_carried_notice_lists_open_frames] After a compaction or restart, the carried notice MUST list each open operator frame with its channel, reply handle and age. (carried_notice_MUST_list_open_frames)
- **R22** [SHOULD · judgment: the host-side maintainer, at review of the landed policy] While the agent serves a remote frame whose channel shows no tool trace, it SHOULD send interim progress during a long service. (remote_service_SHOULD_report_progress)

### 6.6 Measurement and policy

- **R23** [MUST · decidable: macf/tests/test_attention_frames.py::test_latencies_are_reported_per_subclass] The framework MUST report, per operator subclass, the time from arrival to acknowledgment, to first reply and to return, derived from the event log. (latency_MUST_be_reported_per_subclass)
- **R24** [MUST · judgment: the Secretary, at the cold-reader trial] The framework's policies MUST state the stack and interrupt rules for every agent, so that no agent learns them only from its own operator. (interrupt_rules_MUST_live_in_policy)

## 7 Rationale and Rejected Alternatives

- **R01**: an ask held only in the agent's head dies with the next interruption or compaction (incidents 1 and 7). The reply handle is recorded at arrival because Telegram's bot interface keeps no history: without the id, nothing later can reply to the message.
- **R02**: MIS-0002 already tells the operator apart by origin (R107, R121), which settles the hardest part of a local design: telling the operator from the mail clock, a schedule or CI. Text is never the classifier, because any input can say anything.
- **R03**: MIS-0002-R40 (layer_MUST-NOT_present_notice_as_instruction), R96 (agent_MUST-NOT_take_onlooker_text_as_operator) and R106 (wake_MUST-NOT_count_as_operator_activity) already keep these inputs from passing as the operator. A frame class is one more place that must hold the same line.
- **R04**: the repo owner set two expectations for one class (section 2). Visibility differs by channel and its configuration, so the declaration, which already lists operator channels (MIS-0002-R107), names the subclass beside each.
- **R05**: the boundary is the message, in the repo owner's refinement: asks within one message are queued and worked in order, because they were issued together; a new message supersedes, because the operator has spoken again. The test is mechanical and needs no judgment.
- **R06** and **R07**: tasks are the work store (`task_management` section 16), and a second store of the same facts drifts. MIS-0002-R16 (layer_MUST-NOT_keep_second_ledger) set the same rule for liveness. Frames as events make R23's measurements free.
- **R08** and **R09**: on a remote channel the operator sees only what the agent sends. A message can wait for a tool boundary before the session takes it, so a long foreground step delays the acknowledgment however careful the agent is (measured on the MIS-0002 deliberation: queued, then taken into the running turn). Recording the acknowledgment makes a missing one measurable, as MIS-0002-R120 (prompt_hook_MUST_record_notice_receipt) does for notices.
- **R10**: incident 1 nested a self-chosen review above an unreturned ask. Opening a new frame of the agent's choosing is exactly the work-queue model the repo owner named.
- **R11**: masking at delivery already exists for keystrokes (MIS-0002-R45). This states it at the level of attention. It is a SHOULD in this draft because holding mail behind an operator frame could delay a maintainer's urgent message; Q06 asks the bound.
- **R12**: the repo owner's words: "FULL synchronous attention". The interrupted frame may go to a subagent, but the terminal ask may not be split from the operator's view.
- **R13**: delegation moves work, not responsibility. A subagent's report is a claim until the agent has read it.
- **R14**, **R15** and **R16**: the return plays the part of end-of-interrupt. MIS-0002-R120 already records the first acknowledgment of a notice, its receipt. This adds the second, the return, and the pointer back to the frame below, which `task trace` today infers from touches.
- **R17**: `instruction_language` section 4.4 already names the override. Without it, a faithful agent resumes work the operator has just killed.
- **R18**: not every frame ends in a reply. A steer absorbed into current work, an ask turned into a task, or one the operator withdrew each closes the frame honestly, if its reason is recorded.
- **R19** and **R20**: visibility is the enforcement instead of a Stop-hook gate. MIS-0002-R46 (layer_MUST-NOT_report_no_change) keeps the line silent when there is nothing to show.
- **R21**: MIS-0002-R47 (pd_MUST_report_carried_changed_lost) already reports what a compaction carried. Open frames are part of what is carried, and today the notice lists only units (incident 7).
- **R22**: the less the operator can see, the more progress the agent owes. A terminal owes none, a remote channel with the tool trace on owes milestones, and one with it off owes interim edits. An edit does not notify; a new message does.
- **R23**: a promise nobody measures is a hope. The event log already holds arrival and reply events; deriving the latencies needs no new store.
- **R24**: the operator taught the interrupt rule to one agent at a time, and each agent wrote it into its own memory. Framework policy is where every agent finds it, and where the operator can audit it.

**Rejected**
- **A Stop-hook block while an operator frame is open.** It turns a visibility problem into a lock the agent will route around, and it would block a legitimate stop while the operator is away. Visibility on every line and the recorded return do the same work without the lock.
- **Classifying frames from the message text.** Any channel can carry any words; MIS-0002 already rejected text as the classifier for the operator's activity.
- **A separate frame store beside the tasks.** It would duplicate the task system and drift from it (R06, R07).
- **One operator class with one latency contract.** The repo owner set two expectations, by what the operator can see.

## 8 Prior Art

- `task_management` section 16, the work stack: push as a durable note, pop as completion, the reconciled pop, and `macf_tools task trace`, which classifies open frames as active, enclosing, parked, ready or deferred and names the top owed frame after a completion. This MIS keeps all of it and adds operator frames with a class, an acknowledgment and a recorded return.
- `instruction_language` section 4: an interrupting directive binds to the work stack; service discipline follows what the interrupting party can observe; discard-below versus resume-below. R04, R12 and R17 build on it.
- The prompt hook (`hooks/handle_user_prompt_submit.py`) records `notice_received` for MacEff notices (MIS-0002-R120), and `utils/input_origin.py` tells the operator's channels from the rest by exact name (MIS-0002-R107, R121). R01 to R03 and R09 extend the same producers.
- MIS-0002 decides delivery and its labels, including the carried notice (R47) and the keystroke masks (R45, R104, R105). MIS-0004 decides mail and its notices (R25 to R29, R39). This MIS changes neither; it decides attention after delivery.
- Outside MacEff: interrupt controllers in hardware keep a priority, a mask and an end-of-interrupt acknowledgment. This MIS copies that shape: frame classes for priority, masking, and the return as end of interrupt. It refuses nested preemption of an operator frame by the agent's own choices (R10), which hardware has no analogue for.

## 9 Compatibility and Deployment

- The declaration's operator channels gain a subclass each (R04). A declaration written before this MIS lists names only; the framework reads a bare name as remote, which owes the most, and says so once.
- Hook lines gain a frame count while an operator frame is open (R19), and nothing otherwise (R20).
- The carried notice gains a list of open frames (R21). Agents that read it learn more; nothing they read today goes away.
- No store is added: frames are events in the existing event log (R07).
- A deployment does nothing until the landing ships, then updates its framework as usual.

## 10 Security and Safety

- **Forged operator frames.** An input that could open an operator frame would gain the operator's priority. R02 and R03 take the class from the origin record only, as MIS-0002-R121 does, and never from text, so a mail or notice that claims to be the operator opens no operator frame.
- **Acknowledgment by the hook.** If the prompt hook reacted on the agent's behalf (Q03), the hook would need the channel bot's credential. That widens where the credential lives, and the deliberation should weigh it against an acknowledgment that depends on the agent's discipline.
- **Masking as denial of service.** Holding lower-class notices while an operator frame is open could hold a maintainer's urgent mail indefinitely if a frame never closes. R11 is a SHOULD with Q06 asking its bound; held notices are listed, never dropped.
- **Private context in frames.** A frame carries a one-line summary of the ask and a reply handle, in the agent's own event log, which is private to the agent's account. Nothing in a frame leaves the machine.

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | decidable | macf/tests/test_attention_frames.py::test_an_operator_message_opens_a_frame | planned |
| R02 | decidable | macf/tests/test_attention_frames.py::test_the_class_comes_from_the_origin | planned |
| R03 | decidable | macf/tests/test_attention_frames.py::test_notices_wakes_and_peers_never_open_an_operator_frame | planned |
| R04 | decidable | macf/tests/test_attention_frames.py::test_each_operator_channel_declares_its_subclass | planned |
| R05 | decidable | macf/tests/test_attention_frames.py::test_a_new_message_opens_a_new_frame | planned |
| R06 | decidable | macf/tests/test_attention_frames.py::test_a_frame_names_its_task_and_copies_nothing | planned |
| R07 | decidable | macf/tests/test_attention_frames.py::test_frames_come_from_the_event_log | planned |
| R08 | decidable | macf/tests/test_attention_frames.py::test_a_remote_message_is_acknowledged_first | planned |
| R09 | decidable | macf/tests/test_attention_frames.py::test_an_acknowledgment_is_recorded | planned |
| R10 | judgment | the Secretary, at review of the landed policy | pending |
| R11 | decidable | macf/tests/test_attention_frames.py::test_lower_notices_wait_listed_while_an_operator_frame_is_open | planned |
| R12 | judgment | the head maintainer, at review of the landed policy | pending |
| R13 | judgment | the head maintainer, at review of the landed policy | pending |
| R14 | decidable | macf/tests/test_attention_frames.py::test_an_operator_frame_closes_only_on_a_recorded_return | planned |
| R15 | decidable | macf/tests/test_attention_frames.py::test_a_return_records_its_reply_and_time | planned |
| R16 | decidable | macf/tests/test_attention_frames.py::test_a_return_names_the_frame_below | planned |
| R17 | decidable | macf/tests/test_attention_frames.py::test_a_return_says_resume_or_discard | planned |
| R18 | decidable | macf/tests/test_attention_frames.py::test_a_disposal_carries_its_reason | planned |
| R19 | decidable | macf/tests/test_attention_frames.py::test_the_hook_line_shows_open_operator_frames | planned |
| R20 | decidable | macf/tests/test_attention_frames.py::test_the_hook_line_is_silent_with_no_frame | planned |
| R21 | decidable | macf/tests/test_attention_frames.py::test_the_carried_notice_lists_open_frames | planned |
| R22 | judgment | the host-side maintainer, at review of the landed policy | pending |
| R23 | decidable | macf/tests/test_attention_frames.py::test_latencies_are_reported_per_subclass | planned |
| R24 | judgment | the Secretary, at the cold-reader trial | pending |

**Cold-reader trial**: not yet held.

**Use trial**: not yet held.

## 12 Landing Plan

- **Policy:** `task_management` section 16 gains operator frames, their classes, the acknowledgment and the recorded return, beside the existing push and pop; `instruction_language` section 4 cites it rather than restating it. The routine for each subclass, and the guidance on delegating (Q04), land with the policy, in the same pull request as the code (`core_principles`: policy ships with the capability).
- **Code:** the prompt hook records `frame_opened` for an operator message and its acknowledgment (R01, R09); `input_origin` supplies the class and subclass (R02 to R04); `task trace` and the hook line read frames from events (R07, R16, R19, R20); the primal daemon's carried notice lists open frames (R21); a report derives the latencies (R23).
- **Seed evidence first:** on one host deployment, a lab version records frames and measures time to acknowledgment and return for two weeks before the landing, so the deliberation argues from measurements, as the seed proposed.
- **Pull requests:** one for the policy and the frame events, one for the carried notice and the hook line, after the deliberation settles the open questions.

## 13 Open Questions

- **Q01** In what order do the classes below the operator rank: a person's dialog the agent raised, agent mail, schedules, notifications, self-opened frames? The maintainers, in deliberation. (frame_class_order)
- **Q02** Does the subclass follow the channel alone, or also the operator's presence, such as a Telegram message sent while the operator watches the terminal, or voice hands-free under MIS-0008? The maintainers, with the repo owner. (operator_subclass_by_channel_or_presence)
- **Q03** Who acknowledges a remote message: the agent, which keeps the channel credential inside its plugin but depends on discipline, or the prompt hook, which guarantees it but needs the credential? The repo owner. (acknowledgment_by_agent_or_hook)
- **Q04** What guidance does the policy give for delegating the ask, the interrupted frame, both or neither, and does any of it belong in a requirement? The maintainers. (interrupt_delegation_guidance)
- **Q05** When the operator moves between channels, does the return go to the ask's channel, to where the operator is now, or both, with the full answer where they are and a pointer on the ask's thread? The repo owner. (return_channel_when_operator_moves)
- **Q06** How long may the persistent layer hold a lower-class notice behind an open operator frame before it delivers the notice anyway, and does a maintainer's message ever outrank the hold? The maintainers. (masking_hold_bound)
- **Q07** Is R21 an amendment of MIS-0002-R47 (pd_MUST_report_carried_changed_lost), signed off under MIS-0001-R57, or this MIS's own requirement on the same notice? The Secretary. (carried_notice_amends_mis_0002)
- **Q08** Do frames get explicit verbs, a task push and a task pop that carry the channel and reply handle, or does the hook open frames and a return close them without a verb? The maintainers. (frame_verbs_or_hook_only)
- **Q09** Does an operator frame left open across several cycles expire, ask again, or stay open until a return or a disposal? The repo owner. (old_frame_fate)

## 14 Deliberation Record

None.

## 15 Revision History

- 2026-11-28: first draft, from the seed of 2026-10-14 and the repo owner's direction of 2026-10-17.

## Wiki-Links

[[stack_duty]] [[attention]] [[interrupt]] [[mis]]
