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

An MIS is a numbered document that proposes a change to MacEff, explains it, and records how it was decided. When the operator accepts it, its normative text lands in policy, code and tests. From then on **the policy binds; the MIS explains**. Each landed policy section cites its MIS by number (MIS-0001-R30), so a reader can always climb from a rule to its reason.

This is the shape of Python's PEPs: a proposal becomes a historical record once final, and the canonical text lives elsewhere. MacEff refuses the alternative, a living specification kept beside the policy, because two normative ledgers of the same rules drift apart.

### 1.2 When an MIS is required

A pull request MUST cite an accepted MIS when it (MIS-0001 R01):
- adds a subsystem;
- changes architecture across components; or
- changes what an agent is allowed to do.

An author MAY write an MIS for any other change (R02). Bug fixes and small features stay an issue and a pull request.

**The test for "a subsystem" and "what an agent is allowed to do":**
- **A subsystem:** a new long-lived process, a new store of agent state, a new command group, or a new channel to or from an agent.
- **What an agent is allowed to do:** any hook, gate, permission or policy rule that newly blocks, allows or requires an action.
- **A small feature:** extends an existing command or behavior without either of those. For example, a new output format for an existing command.
- **If in doubt, ask the operator.** The operator's answer is the test.

### 1.3 Types

| Type | For |
|---|---|
| **Standards** | a subsystem or a capability |
| **Process** | how MacEff decides or works |
| **Informational** | guidance that binds nothing |

The Type field MUST be one of these three (R08).

---

## 2 The Document

### 2.1 Location and number

- Each MIS MUST be a file named `framework/mis/MIS-NNNN-slug.md` whose Number field equals NNNN (R03).
- Two MIS files MUST NOT share a number (R04).
- A pull request MUST NOT delete an MIS file, also after a rejection or a withdrawal (R05). A number is a permanent citation; a deleted file breaks every reference to it.

**Who assigns the number.** The author takes the next number not used on `main` when the pull request opens. Until a Secretary is designated, that number is provisional: before the MIS enters Deliberation, the Secretary confirms it, or renumbers it if another pull request took it first.

`framework/mis/` ships to every deployment with the framework overlay, so an agent in a container can read the reason behind a rule. It sits outside `framework/policies/`, so it is never loaded as policy.

### 2.2 Header and sections

`MIS-0000-template.md` is the template, and itself a valid MIS. Copy it.
- Each MIS MUST carry its header fields, in their order (R06): Number, Type, Status, Authors, Secretary, Deliberation, Created, Updates, Supersedes, Lands-in, Resolution.
- Each MIS MUST contain its numbered sections, in their order (R07): Summary, Motivation, Goals and Non-Goals, Guide-Level Explanation, Terms, Specification, Rationale and Rejected Alternatives, Prior Art, Compatibility and Deployment, Security and Safety, Conformance, Landing Plan, Open Questions, Deliberation Record, Revision History; then Wiki-Links.

Write "None." in a section that has nothing to say, so that empty is not mistaken for forgotten.

**The header fields:**

| Field | Holds |
|---|---|
| Number | the four digits of the file name |
| Type | Standards, Process or Informational (§1.3) |
| Status | one word from §2.3 |
| Authors | who answers for the content, by public name or by role. Never a private agent identity: MIS files are public and follow `public_voice` |
| Secretary | the designated Secretary, by role, or `none` in Draft |
| Deliberation | the deliberation issue's link, or `none` with the reason |
| Created | the date of the first draft, YYYY-MM-DD |
| Updates | the MIS numbers this one changes in part, or `none` |
| Supersedes | the MIS numbers this one replaces in full, or `none` |
| Lands-in | the policies, files and commands where the normative text lands, or the plan for them while in Draft |
| Resolution | the operator's decision and the answers to objections, or `none` until decided |

### 2.3 Status

The Status field MUST be one of these words (R09):

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

A cold reader can tell from this one word whether the MIS binds anything yet: only an Accepted or Final MIS has landed, or may land.

**Transitions:**

| From | To | Who | Condition |
|---|---|---|---|
| Draft | Deliberation | Secretary | the operator convened a deliberation on it |
| Draft | Final-Comment | Secretary | Informational, or the operator decided no deliberation was needed |
| Deliberation | Final-Comment | Secretary | the window closed and the synthesis is posted |
| Final-Comment | Accepted, Rejected or Deferred | operator | at least 72 hours passed; the operator merges with a Resolution |
| Final-Comment | Deliberation or Draft | Secretary | the comments call for revision |
| Draft, Deliberation or Final-Comment | Withdrawn | author | the authors abandon it |
| Deferred | Draft | author | the operator reopens it |
| Accepted | Final | Secretary | landed and proven (§7.2) |
| Accepted or Final | Superseded | Secretary | a later MIS replaces it in full |

---

## 3 Writing Requirements

### 3.1 The line form

Requirements live in the Specification section, one per line, in this form (R10):

```
- **R07** [MUST · decidable: <test or hook>] <one sentence>
- **R08** [SHOULD · judgment: <who reviews>] <one sentence>
```

- Two requirements in one MIS MUST NOT share an ID (R11). Elsewhere, cite a requirement as `MIS-NNNN-Rnn`.
- **decidable** means a tool can always check it; name the test or hook.
- **judgment** means no tool can; name who reviews it, and when.

Mark each one honestly, so that a conformance table never claims more than was checked.

- **A test that does not exist yet:** a decidable requirement may name a planned test. Its Conformance state then says `planned`, and the test must exist and pass before the MIS becomes Final (§7.2).
- **What the checker cannot see:** `mis check` cannot tell whether a named test exists, or whether a judgment was really made. The Final gate covers both.

### 3.2 Keywords

The keywords are MUST, MUST NOT, SHOULD, SHOULD NOT and MAY, as defined by BCP 14 (RFC 2119, clarified by RFC 8174). They are normative **only in capitals**.
- Each requirement sentence MUST contain its tag's keyword in capitals, and no other capitalized keyword (R12).
- A requirement sentence MUST NOT use a keyword in lowercase letters (R13).

The keywords carry the strength:
- A MUST holds with no exception.
- A SHOULD may be set aside only with a recorded reason (§8.2).
- A MAY grants a freedom.

**Keywords outside the Specification are not normative.** Only requirement lines bind. Elsewhere, write the word in lowercase or rephrase, so that no reader mistakes rationale for a rule. The checker checks requirement lines only.

### 3.3 The language standard

Requirements follow a softened Simplified Technical English (ASD-STE100):
- Each requirement sentence MUST have 30 words or fewer (R14).
- Each requirement SHOULD use the active voice and an EARS pattern (R15): "When <trigger>, the <system> MUST ...", "While <state>, ...", "If <unwanted event>, then ...", "Where <feature is present>, ...".
- Each requirement MUST use only glossary terms, terms from its MIS's Terms section, and plain words with one meaning (R16).

**The rest of an MIS is plain English.** Rationale needs "because", conditions and nuance, which strict STE removes. Write it in short sentences with glossary terms, but do not compress it. In MacEff the reason is part of the control: an agent that cannot find why a rule exists tends to route around it.

---

## 4 Rationale, Conformance and Links

- The Rationale section MUST name every requirement ID (R17), and lists the rejected alternatives with their reasons, so that a later reader does not propose them again without new evidence.
- The Conformance section MUST list every requirement ID with its check (R18), in a table: requirement, check type, how, state. It also records the cold-reader trial (§7.3).
- Each MIS MUST end with a Wiki-Links section that names at least two concepts (R19).

`macf_tools mis check <files>` checks every decidable requirement of this policy. CI runs it over `framework/mis/` and the glossary. Run it before each push.

---

## 5 The Glossary

`framework/glossary.md` is MacEff's one dictionary: one term, one meaning.
- The glossary MUST NOT define one term twice (R20).
- An MIS lists the terms it adds in its Terms section. When an MIS is Accepted or Final, each term in its Terms section MUST appear in the glossary (R21).

A definition changes only through an accepted MIS, or an editorial pull request that keeps its meaning.

---

## 6 Deciding

### 6.1 Roles

- **Author**: any agent or the operator. Writes the MIS and answers for its content.
- **Secretary**: the agent the operator designates for a deliberation. The Secretary:
  - assigns the number and edits to the language standard;
  - keeps the glossary;
  - writes the synthesis;
  - tracks conformance.

  The Secretary can also be an author. Then positions are quoted verbatim, as they always are in a synthesis, and the operator answers each objection (§6.3). That is the check on a Secretary judging their own text.
- **Participants**: everyone the deliberation invites, under `public_voice` §2.4. Container agents speak through a host agent, under a pseudonym.
- **Operator**: the only ratifier.

### 6.2 From deliberation to decision

1. **Deliberation.** Before a Standards or Process MIS becomes Accepted, the operator MUST convene a deliberation on it, or record in the Resolution why none was needed (R22). The operator sets the window when convening (`public_voice` §2.4). An Informational MIS needs no deliberation. When an MIS leaves Draft, its Secretary field MUST name the Secretary the operator designated (R23).
2. **Synthesis.** When a deliberation was held, the Secretary MUST post a synthesis that quotes and links every position and proposes one disposition: accept, revise, defer or reject (R24). The MIS is revised to match, and its status becomes Final-Comment. Without a deliberation, the MIS goes straight to Final-Comment when its pull request is ready for decision.
3. **Final comment.** A final comment period of at least 72 hours MUST pass between the start of status Final-Comment and the ratification (R25). Anyone may object, on the deliberation issue or on the MIS pull request. The Secretary records each objection in the MIS's Deliberation Record. It is long enough for positions relayed by hand, and short enough not to stall the work.
4. **Ratification.** An MIS MUST become Accepted, Rejected or Deferred only through a pull request that the operator merges (R26). No agent can accept its own proposal.

### 6.3 The Resolution

- When an MIS is Accepted, Rejected, Deferred, Final or Superseded, its Resolution field MUST NOT be empty or none (R27).
- The Resolution MUST answer each recorded objection by name (R28).

MacEff has one decider, but it keeps the safeguard of the IETF's rough consensus: an objection is answered, never just outvoted.

---

## 7 Landing and Proof

### 7.1 Landing

- A landing pull request MUST carry the normative text and the capability that it governs together (R29). This is `core_principles`: policy ships with its capability, in one change.
- Each landed policy section MUST cite its MIS by number for its rationale (R30).
- When an MIS is Final, its Lands-in field MUST NOT be empty or none (R31).

### 7.2 Final

An Accepted MIS becomes Final only when it is proven:
- Before an MIS becomes Final, every decidable requirement MUST pass its check (R32).
- Before an MIS becomes Final, a cold-reader trial of its landed policy MUST succeed and be recorded in its Conformance section (R33).
- Before an MIS becomes Final, each judgment requirement MUST have its named review recorded in the Conformance section (R37).

### 7.3 The cold-reader trial

A **cold reader** is an agent with no memory of the MIS's design or deliberation, given only the landed policy and the glossary. It is the reader a compaction produces, and it plays the part of W3C's "implementations created by people other than the authors". In the trial, the cold reader does a task the landed policy governs, and the result is compared with the policy's intent. The trial **succeeds** when the cold reader completes the main path correctly, and every gap it finds is fixed in the policy or recorded as an open question with an owner. Any agent may serve as a cold reader if it took no part in the design or the deliberation; a different model is better still. Record who read, what task, the result, and every gap found, with how it was fixed. This is `policy_writing`'s model-user validation, made a gate.

---

## 8 Changing an Accepted MIS, and Departures

### 8.1 An accepted MIS is a record

- After an MIS is Accepted, each change to it MUST be editorial and recorded in its Revision History (R34).
- A substantive change to an accepted MIS MUST be a new MIS that names the old one in Updates or Supersedes (R35). The old MIS then becomes Superseded, if it is fully replaced.

Rewriting an accepted MIS would falsify the record of what was decided.

- **Editorial:** a change that alters no requirement's meaning, keyword, check or scope. For example, typos, broken links, clearer wording with the same meaning, or a Conformance state moving from `planned` to `passing`.
- **Substantive:** anything else.
- **Who judges:** the Secretary judges which a change is; when anyone disputes it, the operator decides.
- **A partly replaced MIS:** an MIS that a later MIS only updates stays in force, except where the later one changes it. Only full replacement makes it Superseded. This applies equally to an MIS accepted but not yet landed.

### 8.2 Departing from a SHOULD

When an agent departs from a requirement that permits departure (a SHOULD), the agent MUST record the requirement ID and the reason where the departure is made (R36): in the pull request, the commit, or the task note. A SHOULD may be set aside; never silently.

---

## 9 Knowledge Web Participation

An MIS participates in the knowledge web as a whole document.
- **Class (`scholarship` §3.5):** an MIS is **conceptual authority**. Its rationale explains a decision, and stays worth reading long after the decision, to someone who was not there.
- **Not normative:** an MIS is never normative, because the binding text lives in policy. Classing it normative would make it the second ledger this policy forbids.
- **Provenance:** lived. Its authors and the positions it records are first-hand.
- **Links:** an MIS links the domain it decides: at least two concepts (the checker's floor) and at most five, not every concept it mentions. Use concepts the knowledge web already carries (`macf_tools knowledge query <concept>`) before coining a new one.

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
