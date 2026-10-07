# MacEff Improvement Specifications (MIS)

**Type**: Meta-Policy (framework change process)
**Scope**: All agents and the operator, when proposing, deciding or landing a change to MacEff
**Status**: ACTIVE
**Specified by**: MIS-0001 (`framework/mis/MIS-0001-maceff-improvement-specifications.md`). Each rule below cites its requirement there; the reasons are in MIS-0001 §7.

---

## Purpose

MacEff's policy is its specification: agents learn what they may do, and why, by reading it. This policy governs how that specification changes when a change is large. A change is proposed in a **MacEff Improvement Specification (MIS)**, argued in the open, decided by the operator, landed in policy with its code, and then proven by tests and by an agent who never saw the design.

An MIS records a decision; the policy it lands in binds. There is never a second normative source.

---

## CEP Navigation Guide

**1 What an MIS Is**
- What is an MIS, and how does it differ from a policy?
- When must a change have an MIS, and when may it?
- What types of MIS are there?

**2 The Document**
- Where does an MIS live, and how is it numbered?
- What header fields and sections must it have?
- What statuses can it have, and what does each mean?

**3 Writing Requirements**
- What form must a requirement line take?
- Which keywords are normative, and in what case?
- How long may a requirement be, and what style should it use?
- What is a semantic slug, and where must it be used?
- How must a citation of a requirement be written, and what checks it?

**4 Rationale, Conformance and Links**
- Where does each requirement's reason go?
- How is each requirement checked, and where is that recorded?

**5 The Glossary**
- Where are terms defined, and how is a new term added?

**6 Deciding**
- Who are the author, the Secretary and the operator, and what does each do?
- How does a deliberation turn into a decision?
- How long is the final comment period?
- What must the operator's Resolution contain?

**7 Landing and Proof**
- How does an accepted MIS reach policy and code?
- What makes an MIS Final?
- What is a cold-reader trial?

**8 Changing an Accepted MIS, and Departures**
- Can an accepted MIS be edited?
- What happens when an agent cannot follow a SHOULD?

**9 Knowledge Web Participation**
- What kind of node is an MIS, and what should it link?

=== CEP_NAV_BOUNDARY ===

---

## 1 What an MIS Is

### 1.1 A proposal and a decision record

An MIS is a numbered document that proposes a change to MacEff, explains it, and records how it was decided. When the operator accepts it, its normative text lands in policy, code and tests. From then on **the policy binds; the MIS explains**. Each landed policy rule cites its MIS requirement by number, ID and slug [MIS-0001-R30 (policy_rule_MUST_cite_requirement)], so a reader can always climb from a rule to its reason.

This is the shape of Python's PEPs: a proposal becomes a historical record once final, and the canonical text lives elsewhere. MacEff refuses the alternative, a living specification kept beside the policy, because two normative ledgers of the same rules drift apart.

### 1.2 When an MIS is required

A pull request MUST cite an accepted MIS when it [MIS-0001-R01 (PR_MUST_cite_accepted_MIS)]:
- adds a subsystem;
- changes architecture across components; or
- changes what an agent is allowed to do.

An author MAY write an MIS for any other change [MIS-0001-R02 (author_MAY_write_MIS_for_any_change)]. Bug fixes and small features stay an issue and a pull request. A pull request that needs an MIS may be opened as a draft while the MIS is decided, but it does not merge until the MIS is Accepted.

**The test for "a subsystem" and "what an agent is allowed to do":**
- **A subsystem:** a new long-lived process, a new store of agent state, a new command group, or a new channel to or from an agent.
- **What an agent is allowed to do:** any hook, gate, permission or policy rule that newly blocks, allows or requires an action. Enforcement is the test, and policy text enforces too: a MUST or MUST NOT added to policy counts whether or not a hook backs it. A SHOULD, a clarification, a reordering, or a display or recommendation that an agent may ignore requires nothing.
- **Changes architecture across components:** moves a responsibility from one component to another, or changes how two components talk to each other (a file format, a protocol, a shared store).
- **A small feature:** extends an existing command or behavior without either of those. For example, a new output format for an existing command, or a new value shown in an existing hook line.
- **If in doubt, ask the operator.** The operator's answer is the test.

### 1.3 Types

| Type | For |
|---|---|
| **Standards** | a subsystem or a capability |
| **Process** | how MacEff decides or works |
| **Informational** | guidance that binds nothing |

The Type field MUST be one of these three [MIS-0001-R08 (type_MUST_be_listed)].

**An Informational MIS ends at Accepted.** It binds nothing, so it lands nothing: its Lands-in field is `none (Informational)`, and Final, landing and the cold-reader trial (§7) do not apply to it. If guidance later needs to bind, that is a new Standards or Process MIS.

---

## 2 The Document

### 2.1 Location and number

- Each MIS MUST be a file named `framework/mis/MIS-NNNN-slug.md` whose Number field equals NNNN [MIS-0001-R03 (MIS_MUST_be_named_by_number)].
- Two MIS files MUST NOT share a number [MIS-0001-R04 (MIS_numbers_MUST-NOT_repeat)].
- A pull request MUST NOT delete an MIS file, also after a rejection or a withdrawal [MIS-0001-R05 (PR_MUST-NOT_delete_MIS)]. A number is a permanent citation; a deleted file breaks every reference to it.

**Who assigns the number.** The author takes the next number not used on `main` when the pull request opens, and that number is provisional. Before the MIS leaves Draft, the Secretary confirms it; when no Secretary is designated yet, the operator does. If two open pull requests took the same number, the one opened later renumbers. An author who cannot see `main` writes `NNNN` and asks in the pull request.

`framework/mis/` ships to every deployment with the framework overlay, so an agent in a container can read the reason behind a rule. It sits outside `framework/policies/`, so it is never loaded as policy.

### 2.2 Header and sections

`MIS-0000-template.md` is the template, and itself a valid MIS. Copy it.
- Each MIS MUST carry its header fields, in their order [MIS-0001-R06 (MIS_MUST_carry_header_fields)]: Number, Type, Status, Authors, Secretary, Deliberation, Created, Updates, Supersedes, Lands-in, Resolution.
- Each MIS MUST contain its numbered sections, in their order [MIS-0001-R07 (MIS_MUST_contain_sections)]: Summary, Motivation, Goals and Non-Goals, Guide-Level Explanation, Terms, Specification, Rationale and Rejected Alternatives, Prior Art, Compatibility and Deployment, Security and Safety, Conformance, Landing Plan, Open Questions, Deliberation Record, Revision History; then Wiki-Links.

Write "None." in a section that has nothing to say, so that empty is not mistaken for forgotten.

**The header fields:**

| Field | Holds |
|---|---|
| Number | the four digits of the file name |
| Type | Standards, Process or Informational (§1.3) |
| Status | one word from §2.3 |
| Authors | who answers for the content, by public name or by role, for example `the operator` or `the framework maintainer`. Never a private agent identity: MIS files are public and follow `public_voice` |
| Secretary | the designated Secretary, by role, or `none` in Draft |
| Deliberation | the deliberation issue's link; `pending` in Draft, until the operator decides; or `none` with the operator's reason, when the operator decides that none is needed (§6.2) |
| Created | the date of the first draft, YYYY-MM-DD |
| Updates | the MIS numbers this one changes in part, with the requirement IDs it replaces (`MIS-0007: R03 (cache_MUST_expire_daily), R05 (cache_SHOULD_log_misses)`), or `none` |
| Supersedes | the MIS numbers this one replaces in full, or `none` |
| Lands-in | the policies, files and commands where the normative text lands, as a comma-separated list; a short plan in Draft; `none (Informational)` for an Informational MIS |
| Resolution | the operator's decision and the answers to objections, or `none` until decided; it stays `none` for a Withdrawn MIS |

### 2.3 Status

The Status field MUST be one of these words [MIS-0001-R09 (status_MUST_be_listed)]:

| Status | Means | Who sets it |
|---|---|---|
| **Draft** | being written | the author |
| **Deliberation** | positions are being collected on a deliberation issue | the Secretary |
| **Final-Comment** | the synthesis is posted; the final comment period runs | the Secretary |
| **Accepted** | decided; it may land | the operator's merge |
| **Rejected** | decided against | the operator's merge |
| **Deferred** | decided later | the operator's merge |
| **Withdrawn** | abandoned by its authors | the author |
| **Final** | landed and proven (§7.2) | the Secretary |
| **Superseded** | replaced by a later MIS | the Secretary, with the later MIS |

A cold reader can tell from this one word whether the MIS binds anything yet: only an Accepted or Final Standards or Process MIS has landed, or may land. An Informational MIS binds nothing in any status.

**Transitions:**

| From | To | Who | Condition |
|---|---|---|---|
| Draft | Deliberation | Secretary | the operator convened a deliberation on it |
| Draft | Final-Comment | Secretary | Informational, or the operator decided no deliberation was needed; the author says the draft is complete and `mis check` is clean |
| Deliberation | Final-Comment | Secretary | the window closed and the synthesis is posted |
| Final-Comment | Accepted, Rejected or Deferred | operator | the final comment period has run, or the discussion closed under R48; the operator merges with a Resolution |
| Final-Comment | Deliberation or Draft | Secretary | the comments call for revision |
| Draft, Deliberation or Final-Comment | Withdrawn | author | the authors abandon it |
| Deferred | Draft | author | the operator reopens it |
| Accepted, not yet landed | Deferred | operator | the operator merges a Resolution saying why it will not land now |
| Accepted | Final | Secretary, by a pull request another party reviews | a Standards or Process MIS, landed and proven (§7.2) |
| Accepted or Final | Superseded | Secretary | a later MIS replaces it in full |

The operator's decisions in this table, to convene, to skip a deliberation or to designate a Secretary, are made on the MIS's pull request or its deliberation issue, where the record stays.

---

## 3 Writing Requirements

### 3.1 The line form

Requirements live in the Specification section, one per line, in this form [MIS-0001-R10 (req_MUST_use_line_form)]:

```
- **R07** [MUST · decidable: <test or hook>] <one sentence> (semantic_slug)
- **R08** [SHOULD · judgment: <who reviews>] <one sentence> (semantic_slug)
```

- Two requirements in one MIS MUST NOT share an ID [MIS-0001-R11 (req_IDs_MUST-NOT_repeat)]. Elsewhere, cite a requirement as `MIS-NNNN-Rnn`.
- **decidable** means a tool can always check it; name the test or hook.
- **judgment** means no tool can; name who reviews it, and when.

Mark each one honestly, so that a conformance table never claims more than was checked.

- **A test that does not exist yet:** a decidable requirement may name a planned test in any status before Final. Its Conformance state then says `planned`, and the test must exist and pass before the MIS becomes Final (§7.2).
- **What the checker cannot see:** `mis check` cannot tell whether a named test exists, whether a judgment was really made, or whether a sentence means what it says (a double negative passes it). The Final gate covers the first two (§7.2); review covers the third.

### 3.2 Keywords

The keywords are MUST, MUST NOT, SHOULD, SHOULD NOT and MAY, as defined by BCP 14 (RFC 2119, clarified by RFC 8174). They are normative **only in capitals**.
- Each requirement sentence MUST contain its tag's keyword in capitals, and no other capitalized keyword [MIS-0001-R12 (req_MUST_hold_one_keyword)].
- A requirement sentence MUST NOT use a keyword in lowercase letters [MIS-0001-R13 (req_MUST-NOT_use_lowercase_keyword)].

The keywords carry the strength:
- A MUST holds with no exception.
- A SHOULD may be set aside only with a recorded reason (§8.2).
- A MAY grants a freedom.

**Any of the five keywords may be a tag**, for example `[MUST NOT · decidable: ...]`. A MUST NOT or SHOULD NOT sentence names the forbidden act once, positively: "the hook MUST NOT block the session", never "no hook MUST NOT block". The separator in the tag is the middle dot (`·`, U+00B7).

**Keywords outside the Specification are not normative.** Only requirement lines bind. Elsewhere, write the word in lowercase or rephrase, so that no reader mistakes rationale for a rule. A capitalized keyword outside the Specification is a review comment, not a violation: the checker checks requirement lines only.

### 3.3 The language standard

Requirements follow a softened Simplified Technical English (ASD-STE100):
- Each requirement sentence MUST have 30 words or fewer [MIS-0001-R14 (req_MUST_have_30_words_max)].
- Each requirement SHOULD use the active voice and an EARS pattern [MIS-0001-R15 (req_SHOULD_use_active_EARS)]: "When <trigger>, the <system> MUST ...", "While <state>, ...", "If <unwanted event>, then ...", "Where <feature is present>, ...".
- Each requirement MUST use only glossary terms, terms from its MIS's Terms section, and plain words with one meaning [MIS-0001-R16 (req_MUST_use_defined_words)]. Whether a word is plain is a judgment, made by the Secretary at review: when two positions in the deliberation used a word differently, it is not plain, and it goes into Terms.

**The rest of an MIS is plain English.** Rationale needs "because", conditions and nuance, which strict STE removes. Write it in short sentences with glossary terms, but do not compress it. In MacEff the reason is part of the control: an agent that cannot find why a rule exists tends to route around it.


### 3.4 Semantic slugs

Every requirement carries a **semantic slug**: a short name in words, in parentheses at the end of its line. A bare `R14` asks the reader to remember a table; `req_MUST_have_30_words_max` tells them what is meant.
- Each requirement line MUST end with its semantic slug in parentheses, made only of ASCII letters, digits, hyphens and underscores [MIS-0001-R38 (req_MUST_end_with_slug)]. No spaces.
- Two numbered items in one MIS MUST NOT share a semantic slug [MIS-0001-R39 (item_slugs_MUST-NOT_repeat)].
- **Open questions, positions and objections** are numbered items too. Each MUST begin with its ID (`Q01`, `P01`, `O01`) and end with its slug [MIS-0001-R45 (item_MUST_carry_ID_and_slug)]. For example:
  - `- **Q01** Should the checker also lint policies? The operator decides after MIS-0002. (lint_policies_too)`
  - `- **O01** Seat B: a 72-hour period is too short for relayed positions, <link>. (window_too_short_for_relays)`
  The Resolution then answers each objection by its ID and slug [MIS-0001-R28 (resolution_MUST_answer_objections)], so an objector can find the answer to their own words.
- **In discussion:** when a synthesis quotes a position that names a requirement, the synthesis MUST give the slug beside the ID [MIS-0001-R40 (synthesis_MUST_give_slug)]. Participants MAY give the slug at any mention, as a courtesy, and no position fails for leaving it out [MIS-0001-R41 (mention_MAY_give_slug)]. When the discussion turns on what a requirement means, they SHOULD restate its full sentence [MIS-0001-R42 (meaning_SHOULD_restate_req)].
- **In tools:** each finding a tool reports about a requirement MUST name the slug beside the ID [MIS-0001-R43 (tool_MUST_report_slug)]. `mis check` prints `MIS-0001-R14 (req_MUST_have_30_words_max)`, and names the slug of the requirement it found the fault in.
- **Across documents:** a reference from outside the MIS SHOULD give the MIS number, the ID and the slug [MIS-0001-R44 (xref_SHOULD_give_MIS_ID_slug)], as in `MIS-0001-R14 (req_MUST_have_30_words_max)`. This policy cites its own requirements that way.

**One citation form, checked.** A requirement is cited as `MIS-0001-R14 (req_MUST_have_30_words_max)`: the MIS number, the ID, and the slug in parentheses; inside a sentence's own parentheses, in square brackets. `mis check` resolves every citation in framework text against its MIS and refuses one whose MIS or ID does not exist or whose slug does not match [MIS-0001-R49 (citation_MUST_match_slug)]. A slug is therefore as permanent as its ID: renaming one is not editorial (§8.1).

**The pattern** is the subject, then the keyword in capitals, then the action: `PR_MUST-NOT_delete_MIS`, `req_SHOULD_use_active_EARS`, `author_MAY_write_MIS_for_any_change`. MUST NOT and SHOULD NOT are hyphenated. The pattern is a convention, not a rule: the checker checks a slug's characters and uniqueness, not its grammar.

Naked numbers shut out every reader who does not hold the table. Slugs are a courtesy to people and to agents after a compaction alike.

---

## 4 Rationale, Conformance and Links

- The Rationale section MUST name every requirement ID [MIS-0001-R17 (rationale_MUST_name_every_req)]. Naming the ID is what the checker sees; what a reader needs is the reason for that requirement, beside its ID. The section also lists the rejected alternatives with their reasons, so that a later reader does not propose them again without new evidence.
- The Conformance section MUST list every requirement ID with its check [MIS-0001-R18 (conformance_MUST_list_every_req)], in a table: requirement, check type, how, state. The states are, for a decidable requirement, `planned`, `passing` or `failing`; for a one-time judgment, `pending` or `recorded` (with who and when); for a standing judgment, a duty that recurs on every pull request or deliberation, `standing`, with the reviewer named in the How column; and `n/a` only when the requirement's condition never arose for this MIS, with the reason. It also records the cold-reader trial (§7.3), or "not yet held".
- Each MIS MUST end with a Wiki-Links section that names at least two concepts [MIS-0001-R19 (MIS_MUST_end_with_wiki-links)].

**Motivation cites evidence with its tier** (`empiricism`). A proposal with no lived failure behind it may still be written: say so ("reasoning only"), and the operator weighs it accordingly.

`macf_tools mis check <files>` checks every decidable requirement of this policy. Given one MIS, it resolves that file's citations against every MIS beside it, and leaves the policies' citations of the others to a run over the directory. CI runs it over `framework/mis/` and the glossary. Run it before each push.

---

## 5 The Glossary

`framework/glossary.md` is MacEff's dictionary for the terms MIS requirements use: one term, one meaning. A policy may still define a word for its own use, as §1.2 defines "a subsystem"; when an MIS requirement relies on such a word, the word goes into the glossary.
- The glossary MUST NOT define one term twice [MIS-0001-R20 (glossary_MUST-NOT_repeat_terms)].
- An MIS lists the terms it adds in its Terms section. When an MIS is Accepted or Final, each term in its Terms section MUST appear in the glossary [MIS-0001-R21 (terms_MUST_reach_glossary)].

A definition changes only through an accepted MIS, or an editorial pull request that keeps its meaning.

**Retired words.** A word an accepted MIS replaces moves to the glossary's `## Retired` section, in the term form: `- **hypervisor**: retired by MIS-0002; use manager of record.` A quoted position that used the old word stays readable, and since a retired line is a term line, the checker refuses to define the word again. When a glossary change retires a word a position used, the Secretary names who used it and quotes the use, and the retirement is open to objection like the synthesis [MIS-0001-R50 (retirement_MUST_quote_users)].

---

## 6 Deciding

### 6.1 Roles

- **Author**: any agent or the operator. Writes the MIS and answers for its content.
- **Secretary**: the agent the operator designates for an MIS, before it leaves Draft, with or without a deliberation. The Secretary:
  - confirms the number (§2.1) and edits to the language standard;
  - keeps the glossary;
  - writes the synthesis;
  - tracks conformance.

  The Secretary can also be an author. Then positions are quoted verbatim, as they always are in a synthesis, and the operator answers each objection (§6.3). That is the check on a Secretary judging their own text.
- **Participants**: everyone the deliberation invites, under `public_voice` §2.4. Container agents speak through a host agent, under a pseudonym.
- **Operator**: the only ratifier.

### 6.2 From deliberation to decision

1. **Deliberation.** Before a Standards or Process MIS becomes Accepted, the operator MUST convene a deliberation on it, or record in the Resolution why none was needed [MIS-0001-R22 (operator_MUST_convene_or_explain)]. The operator decides this on the MIS's pull request. Until then its Deliberation field says `pending`; afterwards it carries the issue's link, or `none` with the operator's reason, which the Resolution repeats. The operator sets the window when convening (`public_voice` §2.4). An Informational MIS needs no deliberation. When an MIS leaves Draft, its Secretary field MUST name the Secretary the operator designated [MIS-0001-R23 (secretary_MUST_be_named)].
2. **Synthesis.** When a deliberation was held, the Secretary MUST post a synthesis that quotes and links every position and proposes one disposition: accept, revise, defer or reject [MIS-0001-R24 (secretary_MUST_post_synthesis)]. Each option the synthesis puts to the operator quotes the text it rests on, the source as well as the positions [MIS-0001-R51 (option_MUST_quote_its_source)]. The MIS is revised to match, and its status becomes Final-Comment. Without a deliberation, the Secretary moves the MIS to Final-Comment when its author says the draft is complete and `mis check` is clean.
3. **Final comment.** The final comment period lasts as long as its initiator set it, and starts when every maintainer has posted a first comment [MIS-0001-R25 (final-comment_MUST_follow_maintainers)]. When every maintainer has commented and the MIS has been revised once in answer, the discussion closes, unless a maintainer raises a critical objection [MIS-0001-R48 (discussion_MUST_close_after_one_revision)]. An objection is critical when the maintainer raising it says so, and the operator answers it before the merge. Closing ends revision, not recording: an objection posted before the merge is still recorded and answered (§6.3). If the MIS has been revised once before the initiator's period has run, the initiator says whether the discussion waits for the period; for MIS-0001 the operator closed it without waiting. The maintainers are the agents the operator names on the MIS's pull request, until a standing list is kept [MIS-0001-Q03 (where_maintainers_are_listed)]. The period starts again whenever the MIS returns to Final-Comment, and whenever a requirement changes during it; editorial edits do not restart it. Anyone may object, on the deliberation issue or on the MIS pull request. **An objection counts as recorded when it is posted there**, whether or not anyone has copied it yet. The Secretary copies each one into the MIS's Deliberation Record, including an objection to the Secretary's own synthesis, using the slug its objector gave or confirmed [MIS-0001-R46 (objection_slug_MUST_come_from_objector)], and the operator answers every posted objection (§6.3).
4. **Ratification.** An MIS MUST become Accepted, Rejected or Deferred only through a pull request that the operator merges [MIS-0001-R26 (decision_MUST_be_operator_merge)]. No agent can accept its own proposal. An MIS MUST NOT become Accepted while an open question blocks one of its requirements [MIS-0001-R47 (open_question_MUST-NOT_block_acceptance)]. A merge carries only what was committed, so the Secretary makes the last commit before it: the decided status, and a Resolution that quotes the operator's decision comment on the pull request and links it, so the answers to objections are the operator's words, not the Secretary's. An MIS's decision and its landing may share one pull request, as MIS-0001's did; the final comment then covers both.

### 6.3 The Resolution

- When an MIS is Accepted, Rejected, Deferred, Final or Superseded, its Resolution field MUST NOT be empty or none [MIS-0001-R27 (resolution_MUST-NOT_be_empty)].
- The Resolution MUST answer each recorded objection by its ID and semantic slug [MIS-0001-R28 (resolution_MUST_answer_objections)].

MacEff has one decider, but it keeps the safeguard of the IETF's rough consensus: an objection is answered, never just outvoted.

---

## 7 Landing and Proof

### 7.1 Landing

- A landing pull request MUST carry the normative text and the capability that it governs together [MIS-0001-R29 (landing_MUST_ship_text_with_capability)]. This is `core_principles`: policy ships with its capability, in one change.
- Each landed policy rule MUST cite its MIS requirement by MIS number, requirement ID and semantic slug [MIS-0001-R30 (policy_rule_MUST_cite_requirement)], as this policy does. An agent departs from the landed text, and must be able to name the requirement it departed from.
- When an MIS is Final, its Lands-in field MUST NOT be empty or none [MIS-0001-R31 (final_lands-in_MUST-NOT_be_empty)].

### 7.2 Final

An Accepted Standards or Process MIS becomes Final only when it is proven:
- Before an MIS becomes Final, every decidable requirement MUST pass its check [MIS-0001-R32 (final_MUST_pass_decidable_checks)].
- Before an MIS becomes Final, a cold-reader trial of its landed policy MUST succeed and be recorded in its Conformance section [MIS-0001-R33 (final_MUST_pass_cold-reader_trial)].
- Before an MIS becomes Final, its Conformance section MUST record each one-time judgment review and name the reviewer of each standing one [MIS-0001-R37 (final_MUST_record_judgments)] (the Conformance states, §4).

(MIS-0001-R37 (final_MUST_record_judgments) was added after MIS-0001-R33 (final_MUST_pass_cold-reader_trial) and MIS-0001-R34 (accepted_MIS_MUST_change_editorially) to MIS-0001-R36 (departure_MUST_be_recorded), from the first cold-reader trial. IDs are never reused or renumbered, so they follow the order in which they were written.)

**The move to Final is a pull request, and someone other than the Secretary checks it.** The Secretary opens it with the Conformance table filled in. Its reviewer confirms that each named test exists and passes, and that each recorded judgment names who made it and when. Neither the Secretary nor an author of the MIS may serve as its cold reader.

### 7.3 The cold-reader trial

A **cold reader** is an agent with no memory of the MIS's design or deliberation, given only the landed policy and the glossary. It is the reader a compaction produces, and it plays the part of W3C's "implementations created by people other than the authors". In the trial, the cold reader does a task the landed policy governs, and the result is compared with the policy's intent. The trial **succeeds** when the cold reader completes the main path correctly, and every gap it finds is fixed in the policy or recorded as an open question with an owner. Any agent may serve as a cold reader if it took no part in the design or the deliberation, which rules out the Secretary and the authors; a different model is better still. Record who read, what task, the result, and every gap found, with how it was fixed. This is `policy_writing`'s model-user validation, made a gate.

---

## 8 Changing an Accepted MIS, and Departures

### 8.1 An accepted MIS is a record

- After an MIS is Accepted, each change to it MUST be editorial and recorded in its Revision History [MIS-0001-R34 (accepted_MIS_MUST_change_editorially)].
- A substantive change to an accepted MIS MUST be a new MIS that names the old one in Updates or Supersedes [MIS-0001-R35 (substantive_change_MUST_be_new_MIS)]. The old MIS then becomes Superseded, if it is fully replaced.

Rewriting an accepted MIS would falsify the record of what was decided.

- **Editorial:** a change that alters no requirement's meaning, keyword, check, scope, ID or slug. For example, typos, broken links, clearer wording with the same meaning, or a Conformance state moving from `planned` to `passing`.
- **Substantive:** anything else.
- **Who judges:** the Secretary judges which a change is; when anyone disputes it, the operator decides.
- **How an editorial change goes:** by pull request, reviewed and merged like any other. It needs no new final comment period. When it moves a Conformance state toward Final, the Final rules (§7.2) apply to that pull request.
- **A partly replaced MIS:** an MIS that a later MIS only updates stays in force, except where the later one changes it. Only full replacement makes it Superseded. The later MIS names the replaced requirements in its Updates field (`MIS-0007: R03 (cache_MUST_expire_daily), R05 (cache_SHOULD_log_misses)`). The older MIS gets an editorial line in its Revision History naming the later MIS and those IDs, so that a reader of the older MIS alone can tell which of its requirements no longer hold. This applies equally to an MIS accepted but not yet landed.
- **An accepted MIS that will not land:** the operator sets it Deferred, with a Resolution that says why (§2.3). It cannot be Withdrawn, because the decision is the operator's, not the author's.

### 8.2 Departing from a SHOULD

When an agent departs from a requirement that permits departure (a SHOULD), the agent MUST record the requirement ID, its slug and the reason where the departure is made [MIS-0001-R36 (departure_MUST_be_recorded)]: in the pull request, the commit, or the task note. The glossary calls such a recorded departure a **deviation**. A SHOULD may be set aside; never silently.

---

## 9 Knowledge Web Participation

An MIS participates in the knowledge web as a whole document.
- **Class (`scholarship` §3.5):** an MIS is **conceptual authority**. Its rationale explains a decision, and stays worth reading long after the decision, to someone who was not there.
- **Not normative:** an MIS is never normative, because the binding text lives in policy. Classing it normative would make it the second ledger this policy forbids.
- **Provenance:** lived. Its authors and the positions it records are first-hand.
- **Links:** an MIS links the domain it decides: at least two concepts (MIS-0001-R19 (MIS_MUST_end_with_wiki-links), which the checker enforces) and, by convention, no more than five, which review watches. It does not link every concept it mentions. Use concepts the knowledge web already carries (`macf_tools knowledge query <concept>`) before coining a new one.

---

## Integration with Other Policies

| Policy | Relationship |
|---|---|
| `core_principles` | Policy ships with its capability (§7.1 here); a new artifact type is proposed to the operator, and the MIS is that proposal's form |
| `public_voice` | §2.4 defines deliberations and the relay of container agents' positions; an MIS's debate happens there, and MIS files follow its body rule |
| `policy_writing` | Governs the policies an MIS lands in; model-user validation becomes the cold-reader trial (§7.3) |
| `scholarship` | Defines the node classes used in §9 |
| `empiricism` | Motivation cites evidence with its tier |
| `roadmaps_drafting` | After acceptance, a landing roadmap plans the build; it cites the MIS |
| `experiments` | An experiment may supply an MIS's evidence; it does not replace the decision |

---

## Anti-Patterns

- **A second normative ledger.** An MIS kept as the binding text beside a policy that says the same thing. The two drift, and an agent does not know which to obey. Land the text in policy; let the MIS explain.
- **Ceremony for its own sake.** An MIS for a bug fix. The threshold (§1.2) exists so that the process stays worth its cost.
- **The silent rewrite.** Changing an accepted MIS's requirements in place. Write a new MIS.
- **The judgment that pretends to be decidable.** Marking a requirement decidable without a test that can fail. A conformance table then claims what nobody checked.
- **Rationale compressed into STE.** Removing the "because" to meet a length rule. The length rule applies to requirements only.
- **The Secretary's synthesis that summarizes instead of quoting.** A relay that changes words is no longer verbatim, and the operator cannot see what was actually argued.

---

## Evolution & Feedback

This policy is the landed form of MIS-0001. A substantive change to it needs a new MIS that names MIS-0001 in Updates (§8.1); an editorial fix goes by pull request with a line in MIS-0001's Revision History. Report friction with the process, especially the cost of writing an MIS against its value, to the operator, with the MIS where it happened.

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs: proposing,
     deciding and proving changes to MacEff. -->

[[methodology]] [[policy_as_api]] [[collaboration]]
