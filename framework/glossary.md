# MacEff Glossary

One term, one meaning, MacEff-wide, for the terms MIS requirements use. A MacEff Improvement Specification (MIS) uses these terms in its requirements, and lists any term it adds in its own Terms section; the new terms move here when the MIS is accepted. Change a definition only through an accepted MIS, or an editorial pull request that does not change its meaning. The `mis` policy governs this file.

Format: one line per term, `- **term**: definition.`, in alphabetical order. `macf_tools mis check` refuses a term defined twice.

## Terms

- **accepted**: the MIS status set when the operator merges an MIS after its final comment period; its requirements may now land.
- **access path**: the means by which the operator reaches a container, such as its SSH service.
- **agent**: an AI process that runs on MacEff under one identity, with its own memory, tasks and event log.
- **architecture across components**: how MacEff's responsibilities are divided among its components and how the components talk to each other; a change moves a responsibility, or changes a file format, a protocol or a shared store between two components.
- **author**: an agent or the operator who writes an MIS and answers for its content.
- **capability**: something an agent can do because the framework or its deployment allows it.
- **check**: the means by which a requirement is verified: a named test or hook (decidable), or a named reviewer (judgment).
- **cold reader**: an agent with no memory of an MIS's design or deliberation, who is given only the landed policy and this glossary.
- **cold-reader trial**: a test in which a cold reader does a task that the landed policy governs, and the result is compared with the policy's intent.
- **compaction**: the loss of most of an agent's working context when its context window fills, or when the operator or the agent asks for it earlier; the agent continues from a summary and its own artifacts.
- **conformance**: the record, for each requirement, of its check and whether the check passes.
- **container agent**: an agent that runs inside a deployment's container rather than on the operator's own machine.
- **critical objection**: an objection that the maintainer raising it declares critical; it keeps an MIS's discussion open, and the operator answers it before the merge.
- **decidable**: a check that a tool can always run without human judgment, such as a test or a hook.
- **declaration**: the file that lists one agent's managed units and schedules, with how each starts, its restart policy and its limits.
- **deliberation**: an issue the operator convenes on which agents argue a design question in public before it is decided (`public_voice` policy).
- **deployment**: a set of containers, agents and configuration that runs MacEff for one purpose.
- **development flag**: a harness's option that loads a channel its allowlist does not name; in Claude Code it asks a person to confirm at every start.
- **deviation**: a departure from a SHOULD requirement, recorded with the requirement's ID and the reason.
- **disposition**: the outcome the Secretary proposes in a synthesis: accept, revise, defer or reject.
- **editorial**: a change to an MIS or the glossary that alters no requirement's meaning, keyword, check, scope, ID or slug, and no term's meaning.
- **final**: the status of an accepted Standards or Process MIS that has landed and been proven: every decidable requirement passes its check, every judgment review is recorded, and a cold-reader trial has succeeded. An Informational MIS never becomes final.
- **final comment period**: the time, set by the initiator and starting when every maintainer has posted a first comment, in which anyone may object before the operator ratifies.
- **harness adapter**: the part of the persistent layer that launches, wakes and reads one harness, such as Claude Code, Codex CLI or Hermes Agent.
- **harness channel**: a transport the harness provides that delivers events into a live session and sets each event's source from the transport, never from the text, such as a Claude Code channel.
- **health**: proof that the work that fell due actually ran: runs owed against runs done, derived from events when read; never only that a process answers.
- **host agent**: an agent that runs on the operator's own machine.
- **initiator**: whoever convenes a deliberation, usually the operator; the initiator sets its final comment period.
- **invitation**: the observed agent's grant that lets one onlooker receive an observation stream until either side, the operator or a lease ends it.
- **isolated session**: a fresh session that a schedule starts for one run, with no access to the agent's live conversation.
- **judgment**: a check that a named person or agent makes by review, because no tool can decide it.
- **landing**: putting an accepted MIS's normative text into policy, with its code and tests, in a pull request.
- **lease**: a claim that one run holds on a schedule while it runs, so that the run cannot start twice.
- **live session**: the agent's current conversation in its supervised session.
- **liveness event**: an event in an agent's event log by which a managed unit shows that it is alive, keyed by the agent's identity and naming its process.
- **MacEff channel**: the harness channel through which a primal daemon delivers notices and wakes into its agent's live session.
- **maintainer**: an agent that the operator has designated to maintain MacEff.
- **managed unit**: one process or one schedule that a primal daemon runs for its agent, such as the session, the transcript monitor, the notifier or a mail clock.
- **MIS**: MacEff Improvement Specification: a numbered proposal and decision record for a change to MacEff, kept in `framework/mis/`.
- **missed-run policy**: what a schedule does about runs owed while it was down: skip them, run once, run once inside a window, or report them only.
- **notice**: a message the persistent layer delivers to an agent, the operator, or both, naming its source and stamped with when its content was read, sent and received.
- **notifier**: the managed unit that delivers notices into a live session, with masking, de-duplication and a budget.
- **observation stream**: what an onlooker receives: the observed session's events or output from the invitation onward, never its history and never a keyboard.
- **official listing**: a channel plugin's entry in the harness vendor's official marketplace, which puts it on the harness's default allowlist.
- **onlooker**: an agent, or later a person, that watches another agent's session by its invitation and never types into it.
- **operational mode**: a state the hooks detect and act on, such as USER_IDLE or USER_REMOTE, as `mode_system` defines them.
- **operator**: the human who owns a MacEff installation and holds final authority over merges, keys, money and permissions.
- **operator surface**: a way for the operator to see and type into a session, such as a terminal attach or a Remote Control view.
- **organization allowlist**: the list of channel plugins that an organization's administrator permits, which replaces a harness's default allowlist for that organization's sessions.
- **outer tier**: the operating system's own service manager that keeps each primal daemon running: a systemd user unit on Linux, a per-user LaunchAgent on macOS, or a container's init.
- **outside watch**: a check of the primal daemons that runs outside their outer tier and alerts a person through a credential independent of every agent's channel.
- **persistent layer**: the subsystem this MIS specifies: the outer tier, every primal daemon, their declarations, schedules, notices and the outside watch.
- **platform adapter**: the part of the persistent layer that renders declarations for one outer tier.
- **policy**: a document under `framework/policies/` that states what agents must do and why; MacEff's normative source.
- **position**: one participant's argued view in a deliberation, posted as a comment.
- **presence state**: the derived state that says who watches a session and which operator surface is present, read from the agent's event log.
- **primal daemon**: the one process per agent that starts, stops, restarts, checks and schedules that agent's managed units; it manages their lifecycles only, and never reads, writes or decides the agent's work.
- **quiet window**: a time an agent declares in which the layer does not restart or compact its session.
- **ratify**: to accept, reject or defer an MIS by the operator's merge, with a resolution.
- **readout**: what a command or a display reports about the persistent layer's state.
- **requirement**: one normative sentence in an MIS's Specification, with an ID, one keyword and a check.
- **resolution**: the operator's recorded decision on an MIS, which answers each recorded objection by name.
- **run done**: an event recording that a run owed ran, with its result.
- **run owed**: a time at which a schedule must run.
- **schedule**: a recurring or one-time obligation declared outside any session, so that it survives restarts.
- **scheduler**: the part of a primal daemon that runs its agent's schedules.
- **Secretary**: the agent the operator designates for an MIS before it leaves Draft, with or without a deliberation, who confirms its number, edits it to the language standard, keeps this glossary, writes the synthesis and tracks conformance.
- **semantic slug**: a short name made of ASCII letters, digits, hyphens and underscores, given in parentheses at the end of a requirement line, that states the requirement's subject and strength, for example `req_MUST_have_30_words_max`.
- **shared budget**: the limits in force for a whole container that several agents share, such as its memory and processor limits.
- **substantive**: any change to an accepted MIS that is not editorial; it needs a new MIS.
- **subsystem**: a long-lived process, a store of agent state, a command group, or a channel to or from an agent.
- **synthesis**: the Secretary's comment that quotes and links every position, names agreements and disagreements, and proposes a disposition.
- **tray**: an optional desktop display of the persistent layer, one icon per agent, that asks primal daemons to act and acts on nothing itself.
- **waiting on a person**: the state of a managed unit, the session included, blocked on a prompt that only a person can answer.
- **wake**: the delivery of a notice into a live session.
- **wind-down**: the steps an agent declares to preserve its state before a compaction, ending in its request for that compaction.
- **work in flight**: a job a managed unit runs that has not finished, such as a long command or a training run, whether or not a session is open.

## Retired

Words that an accepted MIS replaced, in the term form, so that quoted positions stay readable and the word cannot be defined again: `- **word**: retired by MIS-NNNN; use <term>.`

- **controller**: retired by MIS-0002; use managed unit, or primal daemon for the one per agent.
- **daemon**: retired by MIS-0002; use managed unit, or primal daemon for the one per agent.
- **hypervisor**: retired by MIS-0002; use primal daemon.
- **manager of record**: retired by MIS-0002; use primal daemon.
