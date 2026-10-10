# MIS-0001: MacEff Improvement Specifications

**Number**: 0001
**Type**: Process
**Status**: Final
**Authors**: the operator; drafted by the Secretary of deliberation #493
**Secretary**: the Secretary of deliberation #493
**Deliberation**: none (designed with the operator in three rounds of questions; see section 14)
**Created**: 2026-10-02
**Updates**: none
**Supersedes**: none
**Lands-in**: framework/policies/base/meta/mis.md, framework/glossary.md, framework/mis/MIS-0000-template.md, macf_tools mis check
**Resolution**: Accepted by the operator's merge; Final on 2026-10-08, after cold-reader trial 3 on the landed policy (§11), by the operator's merge of the change that records it. The operator's decision comment names three maintainers by their calling cards on the pull request: the head maintainer, the container-management specialist, and the generalist for host-side needs and operator liaison. It decides, quoted with the one name replaced by its role: "Quorum has been reach and pending minor revisions by [the Secretary], I will merge." https://github.com/cversek/MacEff/pull/500#issuecomment-5971935869. No deliberation was convened (R22): the operator commissioned this process and settled its design directly (P01). O01 (fixed_72h_period_too_slow), the operator's own objection, is answered in the operator's words by the quorum ruling (P06), which R25 and R48 carry; the operator merged with the proposed slug in place. Neither of the other two maintainers raised a critical objection (P07, P08).

---

## 1 Summary

MacEff calls its policy the spec, but until now it had no way to propose a change, argue it in the open, decide it, and prove that it works. This MIS adds that process. An MIS is a numbered proposal and decision record in `framework/mis/`. Its normative text lands in policy, with its code and tests, so policy stays the single source of truth. Requirements are written in a controlled form that a tool checks: one requirement per sentence, one capitalized keyword, an ID, and a named check. A Secretary drafts the synthesis of a deliberation, a final comment period set by its initiator follows once every maintainer has commented, and the operator ratifies by merging. An MIS is Final only when its tests pass and an agent with no memory of the design can follow the landed policy.

## 2 Motivation

- **No process existed.** A survey of all 56 policy files found no proposal, decision-record or design-document convention, and no ratification mechanism in any policy. The closest precedents were the deliberation rule in `public_voice` and the "propose the type" step in `core_principles`. Evidence: a full read of the policy tree on 2026-10-02 (measurement).
- **The words of a live deliberation already drift.** On issue #493, at least six words name overlapping parts of one design ("hypervisor", "supervisor", "manager", "persistent layer", "daemon", "controller"), and "health" carries two meanings: "the due work ran" in four positions, and "the process answers" in the issue's own inventory. Agents on three harnesses will implement the outcome. An ambiguous requirement yields as many designs as readers. Evidence: a count over the issue body and its comments on 2026-10-02 (measurement).
- **Normative force is inconsistent.** Across the policies, uppercase MUST appears 93 times and lowercase "must" 353 times, and most binding statements are bold sentences in plain English. A reader cannot always tell a rule from advice. Evidence: a count over the policy tree (measurement).
- **Agents read specifications cold.** After a compaction an agent has only the text. A specification must therefore carry its own rationale and be checkable without its author. This is MacEff's founding constraint, stated in `core_principles`.

## 3 Goals and Non-Goals

**Goals**
- One process, from proposal to proof, for changes large enough to need it.
- Requirements that a tool can check where checking is possible, and that name their reviewer where it is not.
- A decision record that a cold reader can find from the policy it explains.
- One vocabulary, MacEff-wide.

**Non-goals**
- A second normative source. The policy stays canonical; an MIS records why.
- Ceremony for ordinary changes. Bug fixes and small features stay an issue and a pull request.
- Rewriting the existing policies into the new language. Policies adopt it as they are changed.
- Resolving the three header styles in use across the policies; that is a separate defect.

## 4 Guide-Level Explanation

Suppose the operator asks for one persistent layer to run every long-lived MacEff process.

1. **Draft.** The operator opens a deliberation issue and designates a Secretary. An author copies `MIS-0000-template.md` to the next free number and fills each section. `macf_tools mis check` tells the author at once if a requirement has two keywords, is too long, or has no test named.
2. **Deliberate.** Agents post positions on the issue. Container agents speak through a host agent, under a pseudonym.
3. **Synthesize.** When the window closes, the Secretary posts a synthesis that quotes and links every position and proposes a disposition: accept, revise, defer or reject. The MIS draft is revised to match, and its status becomes Final-Comment.
4. **Final comment.** Once every maintainer has commented, anyone may object, for as long as the initiator set.
5. **Ratify.** The operator merges the MIS with a Resolution that answers each objection by name. The status is now Accepted, and building may begin.
6. **Land.** A landing pull request carries the policy text and the code together. Each new policy section cites the MIS for its rationale.
7. **Prove.** When every decidable requirement passes and a fresh agent, given only the landed policy and the glossary, does the governed task correctly, the MIS becomes Final.

## 5 Terms

All terms this MIS uses are defined in `framework/glossary.md`, which this MIS creates.

- **architecture across components**: how MacEff's responsibilities are divided among its components and how the components talk to each other; a change moves a responsibility, or changes a file format, a protocol or a shared store between two components.
- **critical objection**: an objection that the maintainer raising it declares critical; it keeps an MIS's discussion open, and the operator answers it before the merge.
- **initiator**: whoever convenes a deliberation, usually the operator; the initiator sets its final comment period.
- **maintainer**: an agent that the operator has designated to maintain MacEff.

- **semantic slug**: a short name made of ASCII letters, digits, hyphens and underscores, given in parentheses at the end of a requirement line, that states the requirement's subject and strength, for example `req_MUST_have_30_words_max`.
- **subsystem**: a long-lived process, a store of agent state, a command group, or a channel to or from an agent.

## 6 Specification

### 6.1 When an MIS is required

- **R01** [MUST · judgment: the operator, at merge] A pull request that adds a subsystem, changes architecture across components, or changes what an agent is allowed to do MUST cite an accepted MIS. (PR_MUST_cite_accepted_MIS)
- **R02** [MAY · judgment: the author] An author MAY write an MIS for any other change. (author_MAY_write_MIS_for_any_change)
### 6.2 The document

- **R03** [MUST · decidable: macf_tools mis check, path] Each MIS MUST be a file named framework/mis/MIS-NNNN-slug.md whose Number field equals NNNN. (MIS_MUST_be_named_by_number)
- **R04** [MUST NOT · decidable: macf_tools mis check, numbers] Two MIS files MUST NOT share a number. (MIS_numbers_MUST-NOT_repeat)
- **R05** [MUST NOT · judgment: the reviewers of each pull request] A pull request MUST NOT delete an MIS file, also after a rejection or a withdrawal. (PR_MUST-NOT_delete_MIS)
- **R06** [MUST · decidable: macf_tools mis check, header] Each MIS MUST carry the header fields of MIS-0000, in their order. (MIS_MUST_carry_header_fields)
- **R07** [MUST · decidable: macf_tools mis check, sections] Each MIS MUST contain the numbered sections of MIS-0000, in their order. (MIS_MUST_contain_sections)
- **R08** [MUST · decidable: macf_tools mis check, type] The Type field MUST be Standards, Process or Informational. (type_MUST_be_listed)
- **R09** [MUST · decidable: macf_tools mis check, status] The Status field MUST be Draft, Deliberation, Final-Comment, Accepted, Rejected, Withdrawn, Deferred, Final or Superseded. (status_MUST_be_listed)
### 6.3 Requirements

- **R10** [MUST · decidable: macf_tools mis check, requirement form] Each requirement MUST use the line form that MIS-0000 section 6 shows, with an ID, one keyword and a check. (req_MUST_use_line_form)
- **R11** [MUST NOT · decidable: macf_tools mis check, IDs] Two requirements in one MIS MUST NOT share an ID. (req_IDs_MUST-NOT_repeat)
- **R12** [MUST · decidable: macf_tools mis check, keyword] Each requirement sentence MUST contain its tag's keyword in capitals, and no other capitalized keyword. (req_MUST_hold_one_keyword)
- **R13** [MUST NOT · decidable: macf_tools mis check, lowercase] A requirement sentence MUST NOT use a keyword in lowercase letters. (req_MUST-NOT_use_lowercase_keyword)
- **R14** [MUST · decidable: macf_tools mis check, length] Each requirement sentence MUST have 30 words or fewer. (req_MUST_have_30_words_max)
- **R15** [SHOULD · judgment: the Secretary] Each requirement SHOULD use the active voice and an EARS pattern. (req_SHOULD_use_active_EARS)
- **R16** [MUST · judgment: the Secretary] Each requirement MUST use only glossary terms, terms from its MIS's Terms section, and plain words with one meaning. (req_MUST_use_defined_words)
### 6.4 Rationale, conformance and links

- **R17** [MUST · decidable: macf_tools mis check, rationale] The Rationale section MUST name every requirement ID. (rationale_MUST_name_every_req)
- **R18** [MUST · decidable: macf_tools mis check, conformance] The Conformance section MUST list every requirement ID with its check. (conformance_MUST_list_every_req)
- **R19** [MUST · decidable: macf_tools mis check, wiki-links] Each MIS MUST end with a Wiki-Links section that names at least two concepts. (MIS_MUST_end_with_wiki-links)
### 6.5 Terms and the glossary

- **R20** [MUST NOT · decidable: macf_tools mis check, glossary] The glossary MUST NOT define one term twice. (glossary_MUST-NOT_repeat_terms)
- **R21** [MUST · decidable: macf_tools mis check, terms] When an MIS is Accepted or Final, each term in its Terms section MUST appear in the glossary. (terms_MUST_reach_glossary)
### 6.6 Deciding

- **R22** [MUST · judgment: the operator] Before a Standards or Process MIS becomes Accepted, the operator MUST convene a deliberation on it, or record in the Resolution why none was needed. (operator_MUST_convene_or_explain)
- **R23** [MUST · decidable: macf_tools mis check, secretary] When an MIS leaves Draft, its Secretary field MUST name the Secretary that the operator designated. (secretary_MUST_be_named)
- **R24** [MUST · judgment: the operator] When a deliberation was held, the Secretary MUST post a synthesis that quotes and links every position and proposes one disposition. (secretary_MUST_post_synthesis)
- **R25** [MUST · judgment: the operator] The final comment period MUST last as long as its initiator set it, and start when every maintainer has posted a first comment. (final-comment_MUST_follow_maintainers)
- **R26** [MUST · judgment: the operator] An MIS MUST become Accepted, Rejected or Deferred only through a pull request that the operator merges. (decision_MUST_be_operator_merge)
- **R27** [MUST NOT · decidable: macf_tools mis check, resolution] When an MIS is Accepted, Rejected, Deferred, Final or Superseded, its Resolution field MUST NOT be empty or none. (resolution_MUST-NOT_be_empty)
- **R28** [MUST · judgment: the operator] The Resolution MUST answer each recorded objection by its ID and semantic slug. (resolution_MUST_answer_objections)
### 6.7 Landing and proof

- **R29** [MUST · judgment: the reviewers of the landing pull request] A landing pull request MUST carry the normative text and the capability that it governs together. (landing_MUST_ship_text_with_capability)
- **R30** [MUST · judgment: the reviewers of the landing pull request] Each landed policy rule MUST cite its MIS requirement by MIS number, requirement ID and semantic slug. (policy_rule_MUST_cite_requirement)
- **R31** [MUST NOT · decidable: macf_tools mis check, lands-in] When an MIS is Final, its Lands-in field MUST NOT be empty or none. (final_lands-in_MUST-NOT_be_empty)
- **R32** [MUST · judgment: the Secretary, from the test results] Before an MIS becomes Final, every decidable requirement MUST pass its check. (final_MUST_pass_decidable_checks)
- **R33** [MUST · judgment: the Secretary] Before an MIS becomes Final, a cold-reader trial of its landed policy MUST succeed and be recorded in its Conformance section. (final_MUST_pass_cold-reader_trial)
- **R37** [MUST · judgment: the Secretary] Before an MIS becomes Final, its Conformance section MUST record each one-time judgment review and name the reviewer of each standing one. (final_MUST_record_judgments)
### 6.8 Change after acceptance, and departures

- **R34** [MUST · judgment: the reviewers of each pull request] After an MIS is Accepted, each change to it MUST be editorial and recorded in its Revision History. (accepted_MIS_MUST_change_editorially)
- **R35** [MUST · judgment: the Secretary] A substantive change to an accepted MIS MUST be a new MIS that names the old one in Updates or Supersedes. (substantive_change_MUST_be_new_MIS)
- **R36** [MUST · judgment: the reviewers of the change] When an agent departs from a requirement that permits departure, the agent MUST record the requirement ID, its semantic slug and the reason where the departure is made. (departure_MUST_be_recorded)
### 6.9 Semantic slugs

- **R38** [MUST · decidable: macf_tools mis check, slug] Each requirement line MUST end with its semantic slug in parentheses, made only of ASCII letters, digits, hyphens and underscores. (req_MUST_end_with_slug)
- **R39** [MUST NOT · decidable: macf_tools mis check, slug uniqueness] Two numbered items in one MIS MUST NOT share a semantic slug. (item_slugs_MUST-NOT_repeat)
- **R40** [MUST · judgment: the operator] When a synthesis quotes a position that names a requirement, the synthesis MUST give the requirement's semantic slug beside its ID. (synthesis_MUST_give_slug)
- **R41** [MAY · judgment: the participant] A participant MAY give a requirement's semantic slug at any mention. (mention_MAY_give_slug)
- **R42** [SHOULD · judgment: the Secretary] When a discussion turns on a requirement's meaning, the participant SHOULD restate the requirement's full sentence. (meaning_SHOULD_restate_req)
- **R43** [MUST · decidable: macf/tests/test_mis_check.py::test_findings_name_their_slugs] Each finding that a tool reports about a requirement MUST name the requirement's semantic slug beside its ID. (tool_MUST_report_slug)
- **R44** [SHOULD · judgment: the reviewers of each pull request] A reference to a requirement from outside its MIS SHOULD give the MIS number, the requirement ID and the semantic slug. (xref_SHOULD_give_MIS_ID_slug)
- **R45** [MUST · decidable: macf_tools mis check, numbered items] Each open question, position and objection MUST begin with its ID (Qnn, Pnn or Onn) and end with its semantic slug. (item_MUST_carry_ID_and_slug)

### 6.10 Review of the procedure, 2026-10-03

- **R46** [MUST · judgment: the operator] When the Secretary records an objection, the Secretary MUST use the slug that its objector gave or confirmed. (objection_slug_MUST_come_from_objector)
- **R47** [MUST NOT · judgment: the operator] An MIS MUST NOT become Accepted while an open question blocks one of its requirements. (open_question_MUST-NOT_block_acceptance)
- **R48** [MUST · judgment: the operator] When every maintainer has commented and the MIS has been revised once in answer, the discussion MUST close unless a maintainer raises a critical objection. (discussion_MUST_close_after_one_revision)
- **R49** [MUST · decidable: macf_tools mis check, citations] A citation of an MIS requirement in framework text MUST name the slug that the MIS gives it. (citation_MUST_match_slug)
- **R50** [MUST · judgment: the operator] When a glossary change retires a word that a position used, the Secretary MUST name who used it and quote the use. (retirement_MUST_quote_users)
- **R51** [MUST · judgment: the operator] Each option that a synthesis puts to the operator MUST quote the text that it rests on. (option_MUST_quote_its_source)

## 7 Rationale and Rejected Alternatives

**Why an MIS records and policy binds (R01, R02, R29, R30).** MacEff's policy is the spec. A second normative document would be a second ledger of the same rules, and two ledgers drift. So an MIS proposes and justifies; when accepted, its normative text lands in policy, and the MIS stays as the permanent answer to "why". This is the PEP model: a Python Enhancement Proposal becomes a historical document once final, and the canonical text lives in the documentation. R29 restates `core_principles`: policy ships with its capability, in one change. R30 makes the link run both ways, so a cold reader can climb from a rule to its reason. R01 sets the threshold where a change alters architecture or what an agent may do; R02 leaves the format open to anything else, without making it a duty.

**Why a numbered file, changed by pull request (R03 to R09).** A file in the repository has a review history, ships to every deployment with the framework overlay, and can be checked by a tool. Numbers that are never reused (R04, R05) let tests, tasks and later MIS cite a decision forever; a deleted file would break every citation to it. A fixed header and section order (R06, R07) let a reader, and the checker, find the same thing in the same place in every MIS. A closed vocabulary for Type and Status (R08, R09) lets an agent after a compaction tell from one word whether a document binds anything yet.

**Why the language rules (R10 to R16).** The operator proposed writing the outcome of a deliberation in "80% ASD-STE100", the Simplified Technical English developed for aircraft maintenance, and recommended for language models by Andrej Karpathy at roughly that strength.
- **From STE:** one instruction per sentence and a cap on length. STE caps procedural sentences at 20 words and descriptive ones at 25; a softened, 80% adoption allows up to about 25. R14 sets 30, because a requirement carries a condition, an actor and a response, and the checker counts every word.
- **From BCP 14 (RFC 2119, clarified by RFC 8174):** the keywords are normative only in capitals. R12 and R13 make that mechanical: one capitalized keyword per requirement, and none in lowercase, so that no reader can mistake a requirement's force.
- **From requirements engineering:** the ID and the named check (R10, R11) follow DO-178C traceability and the INCOSE rule that every requirement be verifiable. The EARS patterns (R15) state a trigger and a response, which makes a requirement testable.
- **Why R15 is a SHOULD:** some requirements, like R03, are better as plain statements.
- **Why R16 is a judgment:** no tool can decide which words are terms.

**Why rationale and conformance by ID (R17 to R19).** MacEff's rule is that the explanation is part of the control: an agent that cannot find why a rule exists tends to route around it. R17 guarantees that no requirement arrives without its reason. R18 makes conformance a table that can be audited row by row, like MISRA's compliance summary. R19 keeps every MIS reachable in the knowledge web.

**Why one glossary (R20, R21).** STE's central idea is one word, one meaning, with project-specific technical names and verbs added to its dictionary. The drift measured on issue #493 shows what happens without it. One file, checked for duplicates (R20), is the dictionary; R21 makes an accepted MIS's new terms land there, so no definition lives only in an MIS.

**Why this decision procedure (R22 to R28).** R23 makes the Secretary a named role from the moment an MIS leaves Draft, so participants know who will carry their words. R27 makes a decided MIS carry its decision in its own header, where a cold reader looks first. The procedure combines several traditions:
- the Rust RFC process's final comment period with a stated disposition;
- the IETF's rough consensus, where an objection must be answered, not outvoted;
- Python's steering council, where one authority decides.

MacEff has one ratifier, the operator, as it has one owner. The IETF's real safeguard is kept: the operator answers each recorded objection by name (R28). A disposition (R24) tells participants what they are commenting on. An Informational MIS, or one the operator decides without a deliberation, has no synthesis, so the final comment period is the one point every path passes through. Its length was first a fixed 72 hours; the operator's ruling of 2026-10-03 replaced it (R25, R48, below). R22 lets the operator skip a deliberation, but only with a recorded reason; this MIS uses that exception. R26 holds acceptance to the operator's merge, so no agent can accept its own proposal.

**Why proof before Final (R31 to R33, R37).** R32 holds Final to passing tests, so a decidable requirement is never only declared. R37 does the same for judgment requirements: a review that nobody recorded did not happen, as far as the record shows. The first cold-reader trial found that without R37, Final checked only half of the requirements. R31 ensures a Final MIS says where its text landed. TC39 requires two implementations that pass its test suite, and W3C asks for implementations "created by people other than the authors". In MacEff, the reader that matters is an agent with no memory of the design. That is exactly what compaction produces. So a cold-reader trial is the independent implementation, and passing tests are the conformance suite. `policy_writing` already asks for this as model-user validation; R33 makes it a gate.

**Why change only by a new MIS (R34, R35), and why departures are recorded (R36).** An accepted MIS is a record of a decision. Rewriting it would falsify the record. So a substantive change is a new decision, linked by Updates or Supersedes, as RFCs do with "Updates" and "Obsoletes". R36 is MISRA's deviation record in its simplest form: a SHOULD may be set aside, but never silently.

**Why semantic slugs (R38 to R44).** The operator asked for them on this MIS's pull request on 2026-10-03, quoted in the Deliberation Record. A bare number asks every reader to hold a table in their head. "R14" means nothing to someone who did not write the MIS, and it costs a person's memory and attention even when they did. A slug such as `req_MUST_have_30_words_max` carries the rule's subject and its strength into every place the number goes: a discussion, a refusal from a tool, a citation from another document. So a reader can follow the conversation without opening the file, and an outsider can tell what is being argued.
- **R38 and R39** make the slug part of the line form, and unique, so that a tool can find it, check it and print it. The character set is the operator's: ASCII letters, digits, hyphens and underscores, with no whitespace, so that a slug survives any medium.
- **R40, R41 and R42** are the conversational rules: the slug on first mention (a MUST), at any later mention (a MAY), and the full sentence restated when the meaning is in dispute (a SHOULD). The first mention is where a reader without the table is lost; later mentions can rely on it.
- **R45** extends IDs and slugs to the other items a deliberation cites: open questions (`Q01`), positions (`P01`) and objections (`O01`). The operator chose them on 2026-10-03. R28 then has the Resolution answer each objection by its ID and slug, so an objector can find the answer to their own words, and an outsider can follow which objection was answered how.
- **R43** holds tools to the same courtesy. A refusal that names only "R14" sends the reader to look it up.
- **R44** extends the rule across documents. A policy citing this MIS writes `MIS-0001-R14 (req_MUST_have_30_words_max)`, so the citation still reads when it is quoted out of context.
- **The pattern** in the operator's examples is the subject, then the keyword in capitals (MUST-NOT hyphenated), then the action. It is a convention, not a rule: a slug is checked for its characters and its uniqueness, not for its grammar.

**Why the review of 2026-10-03 changed the procedure (R25, R30, R36, R37, R40, R41, R46 to R51).** The operator named three maintainers: the head maintainer, the container-management maintainer (who is this MIS's Secretary), and the host-side maintainer and operator liaison. The other two reviewed this MIS on its pull request, and the operator ruled on the comment period. Their words are in the Deliberation Record (P04 to P09, O01).
- **R25 and R48: the operator's ruling.** A fixed 72 hours protected positions relayed by hand, but all the voices today are agents on the repository owner's own machines, and the delay bought nothing. So each deliberation's initiator sets its final comment period, and it starts only when every maintainer has posted a first comment, so no maintainer is outrun. R48 is the operator's standing quorum rule: after every maintainer has commented and the MIS has been revised once in answer, the discussion closes, unless a maintainer raises a critical objection. Both reviewers proposed that the maintainer who raises an objection says whether it is critical, and that the operator answers it before the merge; the glossary and the policy now say so. Closing ends revision, not recording, so an objection posted before the merge is still answered under R28.
- **R30 and R36: a landed rule cites its requirement.** An agent departs from the landed policy, not from the MIS, and R36 asks it to name the requirement it departed from. A section that cited only "MIS-0002" would leave it to guess which requirement a sentence came from. So each landed rule cites its requirement by number, ID and slug, as the `mis` policy already does.
- **R37: one-time and standing reviews.** Most judgment requirements are duties that recur on every pull request or deliberation, and can never be recorded once. Final then needs a recorded review for the one-time requirements, and a named reviewer for the standing ones. The Conformance states say which is which.
- **R40 and R41: the slug duty on the synthesis.** Some participants are relayed by hand, and one is the operator typing between other things. A MUST on their form would give the Secretary a ground to discount a position for its form. So the synthesis gives the slug beside every ID it quotes, and participants give slugs as a courtesy (R41).
- **R46: the objector names the objection.** A slug written by the Secretary is a five-word restatement of the objection, by the party it may be objecting to, and it is the handle the operator answers. So the slug comes from the objector, or the objector confirms it.
- **R47: no acceptance over a blocking question.** The template stated this rule, and neither the policy nor this MIS did: a second normative ledger, one sentence long. It is now a requirement.
- **R49: citations are checked.** A citation names a rule; a slug that no longer matches is a call to a function that was renamed. `mis check` resolves each citation in framework text against its MIS, and an ID or slug is no longer an editorial change.
- **R50 and R51: what a synthesis decides before the operator does.** Verbatim quotation protects what a position says, not what it is taken to mean. Retiring a participant's word disposes of part of their meaning before the synthesis, so the Secretary names who used it and quotes the use, and the retirement is open to objection like the synthesis. And an option put to the operator quotes the text it rests on, because a ruling made on a misreading of a source rests on the misreading.

**Rejected**
- **The MIS as a living normative spec** (the amail-spec model). Rejected: it creates a second normative source next to policy.
- **MISRA's three categories with formal deviation records.** Rejected as more ceremony than value: the BCP 14 keywords already carry the strength, and the check type carries what MISRA's decidability carries.
- **The issue body as the MIS.** Rejected: the text would have no review history and could not be checked by a tool.
- **Full STE, rationale included.** Rejected: rationale needs "because" and nuance, which STE's limits remove.
- **An MIS only when the operator designates one.** Rejected: a change to what an agent may do needs a record whether or not anyone thought to ask for one.
- **Writing the policy first and numbering MIS from the persistent layer.** Rejected: specifying the process in its own format tests the format before its first real use.
- **Ratification straight after the synthesis, without a final comment period.** Rejected: participants deserve to see the proposed disposition before it is decided.
- **The template outside `framework/mis/`.** Rejected: as MIS-0000, the template is itself checked by the same tool, as PEP 12 is itself a PEP.

## 8 Prior Art

- **Inside MacEff.**
  - `public_voice` §2.4 defines deliberations and the relay of container agents' positions.
  - `core_principles` asks that a new artifact type be proposed to the operator, and that policy ship with its capability.
  - `policy_writing` §5.2 asks for model-user validation.
  - The amail policy and its working specification already use clause IDs that code and tests cite, a closed status vocabulary, and a split between normative and informative text. This MIS makes those patterns general.
- **Outside MacEff:**
  - PEP 1 and PEP 12: types, statuses, a template, and historical status after Final. https://peps.python.org/pep-0001/ and https://peps.python.org/pep-0012/
  - RFC 8174 (BCP 14), RFC 7282 (rough consensus), RFC 7322 (Updates and Obsoletes; mandatory security considerations). https://www.rfc-editor.org/rfc/rfc8174
  - Rust RFCs: template, and a final comment period with a disposition. https://github.com/rust-lang/rfcs
  - Kubernetes KEPs: goals and non-goals, test plan, production readiness. https://github.com/kubernetes/enhancements
  - MISRA C:2012 and MISRA Compliance:2020: decidable rules, deviations, and a compliance summary.
  - EARS requirement patterns (Mavin). https://alistairmavin.com/ears/
  - The INCOSE Guide to Writing Requirements.
  - Architecture Decision Records (Nygard): numbers never reused, superseded instead of deleted. https://adr.github.io/
  - TC39 stages and test262. https://tc39.es/process-document/
  - The W3C Process, on implementation experience. https://www.w3.org/policies/process/
  - ASD-STE100 Simplified Technical English, and its softened use for language-model output.

## 9 Compatibility and Deployment

- **Existing policies and processes are unchanged.** No current work needs an MIS retroactively.
- **The persistent-layer deliberation (issue #493)** was convened before this process existed. Its positions stand as they are, and its outcome becomes MIS-0002.
- **Deployments** receive `framework/mis/` and `framework/glossary.md` through the framework overlay at their next refresh. They need do nothing else.

## 10 Security and Safety

- **No change at run time.** This MIS adds documents and a checker that reads files. Nothing executes what it reads.
- **OPSEC.** MIS files are public. They follow `public_voice`: no agent identity, deployment name, host or path. Authors are named by role. Deliberation positions keep the protections of `public_voice` §2.4.
- **Capability boundaries.** R01 requires an accepted MIS for any change to what an agent may do, which puts such changes in front of the operator, with a record, before they merge.
- **Self-acceptance.** R26 prevents an agent from accepting its own proposal.

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | judgment | the operator, at merge | standing |
| R02 | judgment | the author | standing |
| R03 | decidable | mis check: path and Number | passing |
| R04 | decidable | mis check: unique numbers | passing |
| R05 | judgment | the reviewers of each pull request | standing |
| R06 | decidable | mis check: header fields and order | passing |
| R07 | decidable | mis check: sections and order | passing |
| R08 | decidable | mis check: Type vocabulary | passing |
| R09 | decidable | mis check: Status vocabulary | passing |
| R10 | decidable | mis check: requirement line form | passing |
| R11 | decidable | mis check: unique requirement IDs | passing |
| R12 | decidable | mis check: one capitalized keyword, matching the tag | passing |
| R13 | decidable | mis check: no keyword in lowercase | passing |
| R14 | decidable | mis check: 30 words or fewer | passing |
| R15 | judgment | the Secretary, at review | standing |
| R16 | judgment | the Secretary, at review | standing |
| R17 | decidable | mis check: every ID named in Rationale | passing |
| R18 | decidable | mis check: every ID listed in Conformance | passing |
| R19 | decidable | mis check: Wiki-Links with at least two concepts | passing |
| R20 | decidable | mis check: no duplicate glossary term | passing |
| R21 | decidable | mis check: Terms present in the glossary once accepted | passing |
| R22 | judgment | the operator | recorded: no deliberation, by the operator's commission of 2026-10-02 (P01) |
| R23 | decidable | mis check: Secretary named outside Draft | passing |
| R24 | judgment | the operator | n/a: no deliberation was held for this MIS |
| R25 | judgment | the operator | recorded: started 2026-10-03 at 17:05 UTC, when the head maintainer's review was the third maintainer's first comment; the operator closed the discussion under R48 at 18:01 UTC |
| R26 | judgment | the operator | recorded: the operator merged the pull request that adopted this MIS, 2026-10-03 |
| R27 | decidable | mis check: Resolution present once decided | passing |
| R28 | judgment | the operator | recorded: the Resolution answers O01 |
| R29 | judgment | the reviewers of the landing pull request | recorded: the adopting pull request carried the policy, the checker and its tests together, 2026-10-03 |
| R30 | judgment | the reviewers of the landing pull request | recorded: a maintainer checked all 60 citations in this pull request, 2026-10-03 |
| R31 | decidable | mis check: Lands-in present once Final | passing |
| R32 | judgment | the Secretary, from the test results | recorded: on main at 82518d0, mis check reports 0 findings over framework/mis/ and the glossary, and test_mis_check.py passes 43 of 43, 2026-10-08 |
| R33 | judgment | the Secretary | recorded: cold-reader trial 3, on the landed policy, succeeded, 2026-10-08 (below) |
| R34 | judgment | the reviewers of each pull request | standing |
| R35 | judgment | the Secretary | standing |
| R36 | judgment | the reviewers of the change | standing |
| R37 | judgment | the Secretary | recorded: every one-time judgment row is recorded or n/a, and every standing row names its reviewer, 2026-10-08 |
| R38 | decidable | mis check: slug at the end of each requirement line | passing |
| R39 | decidable | mis check: unique slugs | passing |
| R40 | judgment | the operator, on each synthesis | standing |
| R41 | judgment | the participant | standing |
| R42 | judgment | the Secretary, in each deliberation | standing |
| R43 | decidable | macf/tests/test_mis_check.py::test_findings_name_their_slugs | passing |
| R44 | judgment | the reviewers of each pull request | standing |
| R45 | decidable | mis check: IDs and slugs on open questions, positions and objections | passing |
| R46 | judgment | the operator, on each Deliberation Record | standing |
| R47 | judgment | the operator | recorded: Q01, Q02 and Q04 to Q07 block no requirement; the operator answered Q03 for this MIS by naming the maintainers (P09) |
| R48 | judgment | the operator | recorded: revised once (P04 to P06 answered), no critical objection (P07, P08), closed by the operator (P09) |
| R49 | decidable | mis check: citations resolve to their MIS slug | passing |
| R50 | judgment | the operator, on each glossary change | standing |
| R51 | judgment | the operator, on each synthesis | standing |

**Tests.** `macf/tests/test_mis_check.py` runs the checker over every file in `framework/mis/` and the glossary, and plants one defect for each decidable check to show that the check catches it.

**Cold-reader trial 1 (2026-10-02, on the policy as first drafted).** Two fresh agents on a different model from the drafter's, with no memory of the design. Neither was allowed to open this MIS, the checker's source or its tests.
- **The writer** was given only the policy, the template and the glossary, and wrote an MIS for a small real change (a `--json` option for `mis check`). Its MIS passed the checker on the first run, with six requirements, six open questions, and honest "planned" states for tests that did not exist yet.
- **The answerer** was given only the policy and the glossary. It answered every navigation question and five scenarios correctly on the main path.
- **Gaps they found, and how each was fixed in the policy before this MIS was accepted:**
  - the path for an Informational MIS, and for one decided without a deliberation (R24 and R25 reworded; policy section 6.2);
  - no status-transition table (policy section 2.3);
  - "editorial" and "substantive" undefined, with no one to judge them (policy section 8.1);
  - Final checked only the decidable requirements (R37 added);
  - header fields undefined, including the Authors format (policy section 2.2);
  - who assigns the number before a Secretary exists, which led the writer to take a number already planned for another MIS (policy section 2.1);
  - whether a decidable requirement may name a test that is still planned (policy section 3.1);
  - whether capitalized keywords may appear outside the Specification (policy section 3.2);
  - who records objections, and who sets the deliberation window (policy section 6.2);
  - where wiki-link concepts come from (policy section 9);
  - two citation styles; the Secretary as an author (policy sections 1.1, 6.1);
  - a partly replaced MIS (policy section 8.1);
  - the test for "a subsystem" against "a small feature" (policy section 1.2).
- **Not fixed by design:** the checker cannot tell whether a named test exists. R32 covers that at Final.
- **Result:** the main path succeeded cold. Every gap at the edges is fixed or answered in the policy. A second trial on the revised policy is due before this MIS becomes Final (R33).

**Cold-reader trial 2 (2026-10-03, on the policy as revised after trial 1).** The same setup, with two fresh agents on a different model. The scenarios were aimed at the gaps trial 1 found.
- **The writer** was given a borderline change ("budget pace mode", a recommendation shown in the hook line) and asked first whether it needs an MIS. It answered no, citing the §1.2 test, and wrote one anyway as told. The MIS passed the checker on its first run, with five requirements, eight Terms and honest `planned` states.
- **The answerer** answered every navigation question and the main path of all eight scenarios. Its scenarios included the Informational path, editorial against substantive changes, Final with judgment requirements, number collisions, a Secretary who is also an author, planned tests, partial replacement, and keywords outside the Specification.
- **Gaps they found, and how each was fixed:**
  - who assigns the number (§2.1 and §6.1 disagreed), with no tie-break and no owner before a Secretary exists (policy section 2.1);
  - where an Informational MIS ends, when Final requires a landed policy (it ends at Accepted; policy section 1.3);
  - who designates a Secretary for an MIS with no deliberation, and how the operator records a decision to skip one (policy sections 2.3 and 6.1);
  - what the Deliberation field says before the operator decides (`pending`; policy sections 2.2 and 6.2);
  - who checks the Final gate, when the Secretary both tracks conformance and sets Final, and whether the Secretary may be the cold reader (a reviewed pull request, and neither the Secretary nor an author may be the cold reader; policy sections 7.2 and 7.3);
  - how an editorial change to an accepted MIS is merged (policy section 8.1);
  - an objection to the Secretary's own synthesis, which only the Secretary would record (an objection counts as recorded when posted; policy section 6.2);
  - whether the final comment period restarts (policy section 6.2);
  - how a partly replaced MIS shows which requirements no longer hold (policy sections 2.2 and 8.1);
  - how an accepted MIS that will not land is abandoned (the operator sets it Deferred; policy sections 2.3 and 8.1);
  - MUST NOT tags and double negatives, which the checker cannot see (policy sections 3.1 and 3.2, and a template example);
  - whether display or advice counts as "requires" in the §1.2 test (enforcement is the test; policy section 1.2);
  - who judges a "plain word" under R16 (policy section 3.3);
  - a Motivation with no evidence (policy section 4);
  - the "at most five" links cap against R19 (policy section 9);
  - glossary drift: "Secretary" tied to a deliberation, "final" without the Accepted condition, and "editorial" and "substantive" used in R34 and R35 but not defined. All are corrected or added.
- **Not fixed by design:** the R-ID order (R37 after R36) follows when each requirement was written, and IDs are never renumbered. The policy now says so.
- **Result:** the main path succeeded cold again, and every gap is fixed in the policy, the glossary or the template. The trial records are kept with the drafting roadmap. A trial on the landed policy after merge, by a reader who saw neither trial, is the evidence R33 needs at Final.

**Cold-reader trial 3 (2026-10-08, on the landed policy after merge).** Two fresh agents on a different model from the drafter's, who saw neither earlier trial. Each was given only the files on main: the writer the policy, the template and the glossary; the answerer the policy and the glossary. Neither the Secretary nor an author was a reader (policy section 7.3).
- **The writer** was given the same change as trial 1 (a `--json` option for `mis check`). It answered first that the change needs no MIS, quoting the policy's own example of a small feature ("a new output format for an existing command"), and wrote one anyway as told. Its MIS passed the checker with 0 findings, though the writer was not allowed to run it.
- **The answerer** answered 23 of the 24 navigation questions clearly and inferred one (the length of a final comment period). None went unanswered. Of five scenarios it answered three clearly, inferred one, and found one part unanswered.
- **Gaps found:**
  - EARS was named but not expanded. Fixed in policy section 3.3.
  - The rest change what the process says, so each is recorded as an open question (R35): Q04 to Q07.
- **Wording notes kept for the next revision, with no change to any requirement:** a placeholder for an unknown link or test file in a Draft; the Lands-in form in a Draft; which Type fits a small capability; how a code token counts toward the word limit and the defined-words rule.
- **Result:** the governed task succeeded cold on the landed policy, and every gap is fixed or recorded. With R32 and R37 recorded above, this MIS meets the Final gate (policy section 7.2).

## 12 Landing Plan

One pull request to MacEff carries all of this:
- this MIS;
- the template (MIS-0000) and the glossary;
- the policy `framework/policies/base/meta/mis.md`, which carries the normative text and cites this MIS for its rationale;
- the `macf_tools mis check` command and its tests;
- the manifest entry;
- one cross-reference in `public_voice` §2.4.

## 13 Open Questions

- **Q01** Should `mis check` also lint policy files for the language rules? Not now: policies adopt the rules as they are changed. The operator decides later, from experience with MIS-0002. (lint_policies_too)
- **Q02** Should small MIS be decided by a delegate of the operator, as a PEP-Delegate decides some PEPs? Not now. The operator decides when the volume makes it worthwhile. (delegate_small_decisions)
- **Q03** Where is the list of maintainers kept, so that R25 and R48 can tell when every maintainer has commented? For this MIS the operator named them on the pull request (P09), and until a standing list is kept the policy says the operator names them that way. Where a standing list lives stays open; it blocks no requirement. (where_maintainers_are_listed)
- **Q04** Should a final comment period have a default length, and who is the initiator when no deliberation was convened? R25 leaves the length to the initiator, and trial 3's reader found neither a default nor the initiator on the path without a deliberation. Blocks no requirement. (default_final_comment_length)
- **Q05** What path does an implementer take when a MUST cannot be met? A MUST has no departure (R36 covers SHOULD only). Trial 3's reader inferred a new MIS under R35. Whether to say so outright stays open. Blocks no requirement. (unmeetable_MUST_path)
- **Q06** Should the §1.2 test name a changed default outright? Trial 3's reader reached the right answer by mapping "default" onto "newly blocks, allows or requires", but the word never appears. MIS-0003 (pull request 507), which revises the threshold, is the natural place. (changed_default_in_threshold)
- **Q07** How does a code token, such as a command flag, count toward R14's word limit and R16's defined words? Trial 3's writer had to guess. Blocks no requirement. (code_tokens_in_requirements)

## 14 Deliberation Record

- **P01** No public deliberation was convened (R22): the operator commissioned this process on 2026-10-02 and settled its design with the drafting Secretary in three rounds of multiple-choice questions, deciding as follows. (operator_commissioned_process)
  - an MIS is a proposal and record, and policy binds;
  - an MIS is required for a new subsystem, cross-component architecture, or a change to what an agent may do;
  - the venue is a numbered file changed by pull request, with debate on a linked issue;
  - requirements use 80% STE, BCP 14 keywords and IDs;
  - keywords carry strength, with a decidable or judgment check;
  - Final needs passing tests and a cold-reader trial;
  - this MIS bootstraps the process;
  - the decision runs synthesis, then a final comment period, then ratification;
  - files live under `framework/mis/`, with one framework glossary and a checker in CI.
- **P02** The operator proposed, on issue #493 on 2026-10-02, that a deliberation's outcome be written in "80% ASD-STE100". The Secretary's reply on that issue set out the scope this MIS adopts. (operator_proposed_80pct_STE)
- **P03** Semantic slugs. The operator, on this MIS's pull request, 2026-10-03, quoted in full: "Requirements or any numbered item should be assigned a semantic slug at the end of the line that defines it [...] Upon first invocation, deliberators MUST use the semantic slugs in addition to the req# when discussing specific requirements. And they MAY use it at any time for clarity. They SHOULD restate the full definition when it helps with clarity like when discussing its semantics. Any tooling MUST use the semantic slug in error messages in addition to the number. This is to ease the burden on the human memory and attention and help outsiders understand conversational references. Outside or cross-MIS scope should also refer to the MIS # as a prefix before the req # and include the semantic slug. Naked number references are off-putting by most standards showing lack of concern to accommodate multiple audiences. Semantic slugs MUST be free of whitespace, limited to ASCII subset [-_A-Za-z0-9]." R38 to R45 carry it. The Secretary's readings, put to the operator the same day in multiple-choice questions: the lowercase "should" for assigning slugs became a MUST (R38), which the operator confirmed; "any numbered item" means requirements, open questions, positions and objections (R45), as the operator chose, and not the numbered sections; the lowercase "should" for cross-document references stays a SHOULD (R44), not yet confirmed. (operator_asked_for_slugs)
- **P04** The host-side maintainer, who is also a participant in the persistent-layer deliberation, reviewed this MIS on its pull request, 2026-10-03: three defects (the Status claimed a decision not yet made, a malformed glossary line escaped the duplicate check, retired words had no place) and five opinions on binding the Secretary. All are answered in this revision. https://github.com/cversek/MacEff/pull/500#issuecomment-5971230845 (participant_review_secretary_limits)
- **P05** The head maintainer reviewed this MIS on its pull request, 2026-10-03, with a run on macOS and arm64: seven defects (judgment rows that could never be recorded, slugs renameable as editorial, landed rules citing only a number, a rule living only in the template, a locale-dependent checker, an MIS absent from the knowledge web, one-way integration) and five opinions, merging once the first four were settled. All are answered in this revision. https://github.com/cversek/MacEff/pull/500#issuecomment-5971413100 (maintainer_review_macos_run)
- **P06** The operator ruled, 2026-10-03, quoted in full: "I would primarily object to the 72-hr comment period considering that all the voices at the moment are of agents within only the MacEff repo owner's infrastructure. We can go a lot faster and the adjudication of the refractory period should be decided for each deliberation by the initiator and should kick in after all maintainers have made their first comments. This discussion should end after one more iteration unless a maintainer voices a critical objection. Consider this a standing maintainer quorum ruling. We will keep the Oct. 9 synthesis deadline for the persistence layer debate." R25 and R48 carry it. https://github.com/cversek/MacEff/pull/500#issuecomment-5971630349 (operator_quorum_ruling)
- **P07** The host-side maintainer checked the revision, 2026-10-03: all eight items answered, and four wording points (who the maintainers are, who judges a critical objection, which of R25 and R48 governs and whether closing stops recording, and exact links for P04 and P05). "If I am counted as a maintainer, none of this is a critical objection." All four are answered in the final revision. https://github.com/cversek/MacEff/pull/500#issuecomment-5971798527 (host_maintainer_rereview)
- **P08** The head maintainer re-ran the checker and the full suite at the revision on macOS and arm64, 2026-10-03, found every defect fixed, agreed with P07's four points, and asked that "subsystem" and "architecture across components" join the glossary: "I have no critical objection [...] I would merge it." Both terms are added in the final revision. Three follow-ups (a traceback on a file that is not UTF-8, two tests that fail under a Latin-1 locale, and emoji in the summary line there) go to an ordinary pull request later. https://github.com/cversek/MacEff/pull/500#issuecomment-5971827296 (head_maintainer_rerun)
- **P09** The operator named the three maintainers and closed the discussion, 2026-10-03; quoted in the Resolution. https://github.com/cversek/MacEff/pull/500#issuecomment-5971935869 (operator_names_maintainers)

Objections recorded:
- **O01** The operator: the fixed 72-hour comment period is too slow while every voice is an agent on the repository owner's own machines. Answered by R25 and R48. The slug was the Secretary's proposal under R46; the operator did not replace it, and merged with it in place. https://github.com/cversek/MacEff/pull/500#issuecomment-5971630349 (fixed_72h_period_too_slow)

## 15 Revision History

- 2026-10-02: first version, with the pull request that adopts it.
- 2026-10-02: after cold-reader trial 1, R24 and R25 reworded for the path without a deliberation, and R37 added (judgment reviews recorded before Final). Made before acceptance, in the same pull request.
- 2026-10-03: after cold-reader trial 2, sixteen gaps (§11) were fixed in the policy's prose and the glossary, the glossary gained "editorial" and "substantive", and the template gained a MUST NOT example. No requirement's keyword or check changed. Made before acceptance, in the same pull request.
- 2026-10-03: at the operator's request on the pull request, every requirement gained a semantic slug, and R38 to R44 were added (slugs in the line form, unique, used in discussion, in tool findings and in cross-document references). Made before acceptance, in the same pull request.
- 2026-10-03: at the operator's choice, open questions, positions and objections gained IDs and slugs too (R45), R39 now covers every numbered item, and R28 answers objections by ID and slug. Made before acceptance, in the same pull request.
- 2026-10-03: the final comment period began when the last maintainer commented; the Status moved back to Final-Comment and the Resolution to none, so that the merge records a decision actually reached. After two maintainers' reviews and the operator's ruling: R25 rewritten (the initiator sets the period, starting after every maintainer's first comment), R30, R36, R37, R40 and R41 amended, R46 to R51 added, and O01 recorded. Made before acceptance, in the same pull request.
- 2026-10-03: the operator named the maintainers and closed the discussion under R48 (P09). Final revision, from P07 and P08: "critical objection", "subsystem" and "architecture across components" defined; the stale "at least 72 hours" corrected in the glossary and in the policy's status table; policy §6.2 says who judges a critical objection, that closing ends revision but not recording, and who the maintainers are; P04 and P05 link their reviews exactly; Q03 answered for this MIS. No requirement changed. The Status moved to Accepted with the Resolution, as the last commit before the merge.
- 2026-10-08: after cold-reader trial 3 on the landed policy (§11), the pending Conformance rows (R26, R29, R32, R33, R37) were recorded, Q04 to Q07 were added, and policy section 3.3 now expands EARS. No requirement changed. The Status moved to Final; the operator's merge of this change is the Final gate's reviewed pull request (policy section 7.2).
- 2026-10-10: R01 (PR_MUST_cite_accepted_MIS) no longer holds. MIS-0003 replaces it with MIS-0003-R01 (PR_MUST_cite_MIS_for_major_change): an MIS is required only for a new policy or a major architectural change, and no longer for every change to what an agent may do. Every other requirement of this MIS stays in force. An editorial line under R34 (accepted_MIS_MUST_change_editorially), landing with MIS-0003.

## Wiki-Links

[[methodology]] [[policy_as_api]] [[collaboration]]
