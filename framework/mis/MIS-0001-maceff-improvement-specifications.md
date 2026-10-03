# MIS-0001: MacEff Improvement Specifications

**Number**: 0001
**Type**: Process
**Status**: Accepted
**Authors**: the operator; drafted by the Secretary of deliberation #493
**Secretary**: the Secretary of deliberation #493
**Deliberation**: none (designed with the operator in three rounds of questions; see section 14)
**Created**: 2026-10-02
**Updates**: none
**Supersedes**: none
**Lands-in**: framework/policies/base/meta/mis.md, framework/glossary.md, framework/mis/MIS-0000-template.md, macf_tools mis check
**Resolution**: Ratified by the operator's merge of the pull request that adds this file. No deliberation was convened: this MIS defines the process that deliberations will use, and its design was settled with the operator directly, in three recorded rounds of questions (section 14). No objection was recorded.

---

## 1 Summary

MacEff calls its policy the spec, but until now it had no way to propose a change, argue it in the open, decide it, and prove that it works. This MIS adds that process. An MIS is a numbered proposal and decision record in `framework/mis/`. Its normative text lands in policy, with its code and tests, so policy stays the single source of truth. Requirements are written in a controlled form that a tool checks: one requirement per sentence, one capitalized keyword, an ID, and a named check. A Secretary drafts the synthesis of a deliberation, a 72-hour final comment period follows, and the operator ratifies by merging. An MIS is Final only when its tests pass and an agent with no memory of the design can follow the landed policy.

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
4. **Final comment.** For at least 72 hours, anyone may object.
5. **Ratify.** The operator merges the MIS with a Resolution that answers each objection by name. The status is now Accepted, and building may begin.
6. **Land.** A landing pull request carries the policy text and the code together. Each new policy section cites the MIS for its rationale.
7. **Prove.** When every decidable requirement passes and a fresh agent, given only the landed policy and the glossary, does the governed task correctly, the MIS becomes Final.

## 5 Terms

All terms this MIS uses are defined in `framework/glossary.md`, which this MIS creates.

## 6 Specification

### 6.1 When an MIS is required

- **R01** [MUST · judgment: the operator, at merge] A pull request that adds a subsystem, changes architecture across components, or changes what an agent is allowed to do MUST cite an accepted MIS.
- **R02** [MAY · judgment: the author] An author MAY write an MIS for any other change.

### 6.2 The document

- **R03** [MUST · decidable: macf_tools mis check, path] Each MIS MUST be a file named framework/mis/MIS-NNNN-slug.md whose Number field equals NNNN.
- **R04** [MUST NOT · decidable: macf_tools mis check, numbers] Two MIS files MUST NOT share a number.
- **R05** [MUST NOT · judgment: the reviewers of each pull request] A pull request MUST NOT delete an MIS file, also after a rejection or a withdrawal.
- **R06** [MUST · decidable: macf_tools mis check, header] Each MIS MUST carry the header fields of MIS-0000, in their order.
- **R07** [MUST · decidable: macf_tools mis check, sections] Each MIS MUST contain the numbered sections of MIS-0000, in their order.
- **R08** [MUST · decidable: macf_tools mis check, type] The Type field MUST be Standards, Process or Informational.
- **R09** [MUST · decidable: macf_tools mis check, status] The Status field MUST be Draft, Deliberation, Final-Comment, Accepted, Rejected, Withdrawn, Deferred, Final or Superseded.

### 6.3 Requirements

- **R10** [MUST · decidable: macf_tools mis check, requirement form] Each requirement MUST use the line form that MIS-0000 section 6 shows, with an ID, one keyword and a check.
- **R11** [MUST NOT · decidable: macf_tools mis check, IDs] Two requirements in one MIS MUST NOT share an ID.
- **R12** [MUST · decidable: macf_tools mis check, keyword] Each requirement sentence MUST contain its tag's keyword in capitals, and no other capitalized keyword.
- **R13** [MUST NOT · decidable: macf_tools mis check, lowercase] A requirement sentence MUST NOT use a keyword in lowercase letters.
- **R14** [MUST · decidable: macf_tools mis check, length] Each requirement sentence MUST have 30 words or fewer.
- **R15** [SHOULD · judgment: the Secretary] Each requirement SHOULD use the active voice and an EARS pattern.
- **R16** [MUST · judgment: the Secretary] Each requirement MUST use only glossary terms, terms from its MIS's Terms section, and plain words with one meaning.

### 6.4 Rationale, conformance and links

- **R17** [MUST · decidable: macf_tools mis check, rationale] The Rationale section MUST name every requirement ID.
- **R18** [MUST · decidable: macf_tools mis check, conformance] The Conformance section MUST list every requirement ID with its check.
- **R19** [MUST · decidable: macf_tools mis check, wiki-links] Each MIS MUST end with a Wiki-Links section that names at least two concepts.

### 6.5 Terms and the glossary

- **R20** [MUST NOT · decidable: macf_tools mis check, glossary] The glossary MUST NOT define one term twice.
- **R21** [MUST · decidable: macf_tools mis check, terms] When an MIS is Accepted or Final, each term in its Terms section MUST appear in the glossary.

### 6.6 Deciding

- **R22** [MUST · judgment: the operator] Before a Standards or Process MIS becomes Accepted, the operator MUST convene a deliberation on it, or record in the Resolution why none was needed.
- **R23** [MUST · decidable: macf_tools mis check, secretary] When an MIS leaves Draft, its Secretary field MUST name the Secretary that the operator designated.
- **R24** [MUST · judgment: the operator] When a deliberation was held, the Secretary MUST post a synthesis that quotes and links every position and proposes one disposition.
- **R25** [MUST · judgment: the operator] A final comment period of at least 72 hours MUST pass between the start of status Final-Comment and the ratification.
- **R26** [MUST · judgment: the operator] An MIS MUST become Accepted, Rejected or Deferred only through a pull request that the operator merges.
- **R27** [MUST NOT · decidable: macf_tools mis check, resolution] When an MIS is Accepted, Rejected, Deferred, Final or Superseded, its Resolution field MUST NOT be empty or none.
- **R28** [MUST · judgment: the operator] The Resolution MUST answer each recorded objection by name.

### 6.7 Landing and proof

- **R29** [MUST · judgment: the reviewers of the landing pull request] A landing pull request MUST carry the normative text and the capability that it governs together.
- **R30** [MUST · judgment: the reviewers of the landing pull request] Each landed policy section MUST cite its MIS by number for its rationale.
- **R31** [MUST NOT · decidable: macf_tools mis check, lands-in] When an MIS is Final, its Lands-in field MUST NOT be empty or none.
- **R32** [MUST · judgment: the Secretary, from the test results] Before an MIS becomes Final, every decidable requirement MUST pass its check.
- **R33** [MUST · judgment: the Secretary] Before an MIS becomes Final, a cold-reader trial of its landed policy MUST succeed and be recorded in its Conformance section.
- **R37** [MUST · judgment: the Secretary] Before an MIS becomes Final, each judgment requirement MUST have its named review recorded in the Conformance section.

### 6.8 Change after acceptance, and departures

- **R34** [MUST · judgment: the reviewers of each pull request] After an MIS is Accepted, each change to it MUST be editorial and recorded in its Revision History.
- **R35** [MUST · judgment: the Secretary] A substantive change to an accepted MIS MUST be a new MIS that names the old one in Updates or Supersedes.
- **R36** [MUST · judgment: the reviewers of the change] When an agent departs from a requirement that permits departure, the agent MUST record the requirement ID and the reason where the departure is made.

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

MacEff has one ratifier, the operator, as it has one owner. The IETF's real safeguard is kept: the operator answers each recorded objection by name (R28). A disposition (R24) tells participants what they are commenting on. An Informational MIS, or one the operator decides without a deliberation, has no synthesis, so R25 counts the final comment period from the start of status Final-Comment, which every path passes through. The 72-hour period is long enough for container agents, whose positions are relayed by hand, and short enough not to stall the build. R22 lets the operator skip a deliberation, but only with a recorded reason; this MIS uses that exception. R26 holds acceptance to the operator's merge, so no agent can accept its own proposal.

**Why proof before Final (R31 to R33, R37).** R32 holds Final to passing tests, so a decidable requirement is never only declared. R37 does the same for judgment requirements: a review that nobody recorded did not happen, as far as the record shows. The first cold-reader trial found that without R37, Final checked only half of the requirements. R31 ensures a Final MIS says where its text landed. TC39 requires two implementations that pass its test suite, and W3C asks for implementations "created by people other than the authors". In MacEff, the reader that matters is an agent with no memory of the design. That is exactly what compaction produces. So a cold-reader trial is the independent implementation, and passing tests are the conformance suite. `policy_writing` already asks for this as model-user validation; R33 makes it a gate.

**Why change only by a new MIS (R34, R35), and why departures are recorded (R36).** An accepted MIS is a record of a decision. Rewriting it would falsify the record. So a substantive change is a new decision, linked by Updates or Supersedes, as RFCs do with "Updates" and "Obsoletes". R36 is MISRA's deviation record in its simplest form: a SHOULD may be set aside, but never silently.

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
| R01 | judgment | the operator, at merge | n/a |
| R02 | judgment | the author | n/a |
| R03 | decidable | mis check: path and Number | passing |
| R04 | decidable | mis check: unique numbers | passing |
| R05 | judgment | the reviewers of each pull request | n/a |
| R06 | decidable | mis check: header fields and order | passing |
| R07 | decidable | mis check: sections and order | passing |
| R08 | decidable | mis check: Type vocabulary | passing |
| R09 | decidable | mis check: Status vocabulary | passing |
| R10 | decidable | mis check: requirement line form | passing |
| R11 | decidable | mis check: unique requirement IDs | passing |
| R12 | decidable | mis check: one capitalized keyword, matching the tag | passing |
| R13 | decidable | mis check: no keyword in lowercase | passing |
| R14 | decidable | mis check: 30 words or fewer | passing |
| R15 | judgment | the Secretary, at review | n/a |
| R16 | judgment | the Secretary, at review | n/a |
| R17 | decidable | mis check: every ID named in Rationale | passing |
| R18 | decidable | mis check: every ID listed in Conformance | passing |
| R19 | decidable | mis check: Wiki-Links with at least two concepts | passing |
| R20 | decidable | mis check: no duplicate glossary term | passing |
| R21 | decidable | mis check: Terms present in the glossary once accepted | passing |
| R22 | judgment | the operator | n/a |
| R23 | decidable | mis check: Secretary named outside Draft | passing |
| R24 | judgment | the operator | n/a |
| R25 | judgment | the operator | n/a |
| R26 | judgment | the operator | n/a |
| R27 | decidable | mis check: Resolution present once decided | passing |
| R28 | judgment | the operator | n/a |
| R29 | judgment | the reviewers of the landing pull request | n/a |
| R30 | judgment | the reviewers of the landing pull request | n/a |
| R31 | decidable | mis check: Lands-in present once Final | passing |
| R32 | judgment | the Secretary, from the test results | n/a |
| R33 | judgment | the Secretary | pending |
| R34 | judgment | the reviewers of each pull request | n/a |
| R35 | judgment | the Secretary | n/a |
| R36 | judgment | the reviewers of the change | n/a |
| R37 | judgment | the Secretary | pending |

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

## 12 Landing Plan

One pull request to MacEff carries all of this:
- this MIS;
- the template (MIS-0000) and the glossary;
- the policy `framework/policies/base/meta/mis.md`, which carries the normative text and cites this MIS for its rationale;
- the `macf_tools mis check` command and its tests;
- the manifest entry;
- one cross-reference in `public_voice` §2.4.

## 13 Open Questions

- **Should `mis check` also lint policy files for the language rules?** Not now. Policies adopt the rules as they are changed. Decided later by the operator, from experience with MIS-0002.
- **Should small MIS be decided by a delegate of the operator, as a PEP-Delegate decides some PEPs?** Not now. The operator decides when the volume makes it worthwhile.

## 14 Deliberation Record

- **No public deliberation was convened** (R22). The operator commissioned this process on 2026-10-02 and settled its design with the drafting Secretary in three rounds of multiple-choice questions. The decisions were:
  - an MIS is a proposal and record, and policy binds;
  - an MIS is required for a new subsystem, cross-component architecture, or a change to what an agent may do;
  - the venue is a numbered file changed by pull request, with debate on a linked issue;
  - requirements use 80% STE, BCP 14 keywords and IDs;
  - keywords carry strength, with a decidable or judgment check;
  - Final needs passing tests and a cold-reader trial;
  - this MIS bootstraps the process;
  - the decision runs synthesis, then a final comment period, then ratification;
  - files live under `framework/mis/`, with one framework glossary and a checker in CI.
- **The operator's proposal** that a deliberation's outcome be written in "80% ASD-STE100" was made on issue #493 on 2026-10-02, and the Secretary's reply on that issue set out the scope this MIS adopts.
- **Objections recorded**: none.

## 15 Revision History

- 2026-10-02: first version, with the pull request that adopts it.
- 2026-10-02: after cold-reader trial 1, R24 and R25 reworded for the path without a deliberation, and R37 added (judgment reviews recorded before Final). Made before acceptance, in the same pull request.

## Wiki-Links

[[methodology]] [[policy_as_api]] [[collaboration]]
