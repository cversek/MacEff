# MacEff Glossary

One term, one meaning, MacEff-wide, for the terms MIS requirements use. A MacEff Improvement Specification (MIS) uses these terms in its requirements, and lists any term it adds in its own Terms section; the new terms move here when the MIS is accepted. Change a definition only through an accepted MIS, or an editorial pull request that does not change its meaning. The `mis` policy governs this file.

Format: one line per term, `- **term**: definition.`, in alphabetical order. `macf_tools mis check` refuses a term defined twice.

## Terms

- **accepted**: the MIS status set when the operator merges an MIS after its final comment period; its requirements may now land.
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
- **deliberation**: an issue the operator convenes on which agents argue a design question in public before it is decided (`public_voice` policy).
- **deployment**: a set of containers, agents and configuration that runs MacEff for one purpose.
- **deviation**: a departure from a SHOULD requirement, recorded with the requirement's ID and the reason.
- **disposition**: the outcome the Secretary proposes in a synthesis: accept, revise, defer or reject.
- **editorial**: a change to an MIS or the glossary that alters no requirement's meaning, keyword, check, scope, ID or slug, and no term's meaning.
- **final**: the status of an accepted Standards or Process MIS that has landed and been proven: every decidable requirement passes its check, every judgment review is recorded, and a cold-reader trial has succeeded. An Informational MIS never becomes final.
- **final comment period**: the time, set by the initiator and starting when every maintainer has posted a first comment, in which anyone may object before the operator ratifies.
- **host agent**: an agent that runs on the operator's own machine.
- **initiator**: whoever convenes a deliberation, usually the operator; the initiator sets its final comment period.
- **judgment**: a check that a named person or agent makes by review, because no tool can decide it.
- **landing**: putting an accepted MIS's normative text into policy, with its code and tests, in a pull request.
- **maintainer**: an agent that the operator has designated to maintain MacEff.
- **major architectural change**: a change that adds a subsystem or changes architecture across components.
- **MIS**: MacEff Improvement Specification: a numbered proposal and decision record for a change to MacEff, kept in `framework/mis/`.
- **new policy**: a policy document added under `framework/policies`, as opposed to a change to an existing one.
- **operator**: the human who owns a MacEff installation and holds final authority over merges, keys, money and permissions.
- **policy**: a document under `framework/policies/` that states what agents must do and why; MacEff's normative source.
- **position**: one participant's argued view in a deliberation, posted as a comment.
- **ratify**: to accept, reject or defer an MIS by the operator's merge, with a resolution.
- **requirement**: one normative sentence in an MIS's Specification, with an ID, one keyword and a check.
- **resolution**: the operator's recorded decision on an MIS, which answers each recorded objection by name.
- **Secretary**: the agent the operator designates for an MIS before it leaves Draft, with or without a deliberation, who confirms its number, edits it to the language standard, keeps this glossary, writes the synthesis and tracks conformance.
- **semantic slug**: a short name made of ASCII letters, digits, hyphens and underscores, given in parentheses at the end of a requirement line, that states the requirement's subject and strength, for example `req_MUST_have_30_words_max`.
- **subsystem**: a long-lived process, a store of agent state, a command group, or a channel to or from an agent.
- **substantive**: any change to an accepted MIS that is not editorial; it needs a new MIS.
- **synthesis**: the Secretary's comment that quotes and links every position, names agreements and disagreements, and proposes a disposition.

## Retired

Words that an accepted MIS replaced, in the term form, so that quoted positions stay readable and the word cannot be defined again: `- **word**: retired by MIS-NNNN; use <term>.`

None yet.
