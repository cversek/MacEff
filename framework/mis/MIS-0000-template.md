# MIS-0000: Template for a MacEff Improvement Specification

**Number**: 0000
**Type**: Process
**Status**: Draft
**Authors**: the policy authors
**Secretary**: none
**Deliberation**: pending
**Created**: 2026-10-02
**Updates**: none
**Supersedes**: none
**Lands-in**: framework/policies/base/meta/mis.md
**Resolution**: none

<!--
How to use this template:
- Copy this file to framework/mis/MIS-NNNN-short-slug.md. Take the next number not used
  on main; it is provisional until the Secretary (or, before one is designated, the
  operator) confirms it. Numbers are never reused, also after a rejection or a withdrawal.
- Header: set Created to today. Deliberation stays `pending` until the operator decides;
  then the issue link, or `none` with the operator's reason. Lands-in is a comma-separated
  list of policies, files and commands, or `none (Informational)`.
- Keep every numbered section and its order. Write "None." in a section that has
  nothing to say, so that a reader can tell empty from forgotten.
- Run `macf_tools mis check framework/mis/MIS-NNNN-short-slug.md` before each push.
- The policy that governs this format is `mis` (macf_tools policy read mis).
This template is itself a valid MIS in Draft, so the checker runs on it.
-->

---

## 1 Summary

*One paragraph in plain words: what changes, for whom, and why now. A reader who reads only this section must know whether the MIS concerns them.*

This template shows the format of an MIS. It holds one example requirement in each of the three forms.

## 2 Motivation

*The problem, from lived failures. For each claim, give its evidence and the evidence tier (`empiricism` policy): a measurement, a reproduction, an incident in a log, or reasoning only. Link the source.*

None.

## 3 Goals and Non-Goals

*Goals: what success looks like, as outcomes a reader can check. Non-goals: what this MIS deliberately does not do. Non-goals stop a deliberation from widening the scope without a decision.*

**Goals**
- A copy of this file is a complete skeleton for a new MIS.

**Non-goals**
- This template does not define the process. The `mis` policy does.

## 4 Guide-Level Explanation

*Teach the change by example, as the agent or the operator will meet it. No requirement language here. A cold reader reads this section first.*

An author copies the template, fills each section, runs the checker, and opens a pull request.

## 5 Terms

*Every term that the Specification uses and that `framework/glossary.md` does not define yet. One line each, one meaning each. By the time the MIS is Accepted, these lines must also be in the glossary (R21 of MIS-0001).*

- **example term**: a word this template defines only to show the form of a Terms entry.

## 6 Specification

*The normative part. One requirement per line, in this exact form:*
*`- **Rnn** [KEYWORD · decidable: <test or hook>] <sentence> (semantic_slug)` or `- **Rnn** [KEYWORD · judgment: <who reviews>] <sentence> (semantic_slug)`.*
*The semantic slug names the requirement in words: ASCII letters, digits, hyphens and underscores, no spaces, unique in the MIS. The usual pattern is the subject, the keyword in capitals (MUST-NOT hyphenated), then the action. Cite a requirement by its ID and slug together the first time you name it, and from outside this MIS as `MIS-NNNN-Rnn (slug)`.*
*KEYWORD is MUST, MUST NOT, SHOULD, SHOULD NOT or MAY, in capitals (BCP 14 as clarified by RFC 8174: these words are normative only in capitals). Each sentence holds one requirement, uses that keyword once, has 30 words or fewer, and is in the active voice. Prefer the EARS patterns: "When <trigger>, the <system> MUST ...", "While <state>, ...", "If <unwanted event>, then ...", "Where <feature is present>, ...". Use only glossary terms and the terms in section 5. Sub-headings (### 6.1) may group requirements.*

- **R01** [MUST · decidable: macf/tests/test_mis_check.py::test_repo_mis_files_pass] Each MIS file MUST pass `macf_tools mis check` before its pull request merges. (MIS_MUST_pass_check)
- **R02** [SHOULD · judgment: the Secretary] When an author adds a requirement, the author SHOULD use an EARS pattern. (req_add_SHOULD_use_EARS)
- **R03** [MAY · judgment: the author] An MIS MAY group its requirements under sub-headings. (MIS_MAY_use_sub_reqs)
- **R04** [MUST NOT · judgment: the Secretary, at review] A requirement sentence MUST NOT hide its keyword inside a double negative. (req_MUST-NOT_use_double-neg)

## 7 Rationale and Rejected Alternatives

*Plain English, short sentences. Explain each requirement by its ID. Then list the alternatives that were considered and why each was rejected, so that a later reader does not propose them again without new evidence. The rationale is part of the control: an agent that cannot find why a rule exists tends to route around it.*

- **R01**: a format that a tool checks stays the same across authors.
- **R02**: EARS sentences state the trigger and the response, which makes each requirement testable.
- **R03**: grouping helps a long specification; it is optional because a short one does not need it.
- **R04**: "no hook must not block" passes the checker and means the opposite of what was intended. A negative requirement names the forbidden act once, positively.

**Rejected**
- None.

## 8 Prior Art

*Related work inside MacEff (policies, earlier MIS, experiments) and outside it, with links. Say what this MIS copies and what it refuses.*

None.

## 9 Compatibility and Deployment

*What changes for existing agents, deployments and data. What a deployment must do, step by step. "Nothing" is a valid answer and must be stated.*

Nothing.

## 10 Security and Safety

*How the change could be abused or could fail unsafely: prompt injection, permission escalation, leaks of private context (OPSEC), changes to capability boundaries, and loss of an agent's memory or work. "No new exposure" is valid only with its reason.*

No new exposure: a template changes nothing at run time.

## 11 Conformance

*One row for every requirement. A decidable requirement names its test or hook and its state (planned, passing, failing). A judgment requirement names who reviews it and when, and its state (pending, or recorded with who and when). Add the cold-reader trial: who read the landed policy cold, what task they did, and the result; until then, "not yet held". An Informational MIS has no trial.*

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | decidable | macf/tests/test_mis_check.py::test_repo_mis_files_pass | passing |
| R02 | judgment | the Secretary, at review | n/a |
| R03 | judgment | the author | n/a |
| R04 | judgment | the Secretary, at review | n/a |

**Cold-reader trial**: not applicable to a template.

## 12 Landing Plan

*Where the normative text lands (which policies and sections), which code and tests ship with it, and in which pull requests. Policy ships with its capability, in one change (`core_principles`).*

The format lands in the `mis` policy.

## 13 Open Questions

*Questions not yet decided, one per line: `- **Q01** <question> <who decides, and by when>. (semantic_slug)`. An MIS cannot be accepted with an open question that blocks a requirement.*

None.

## 14 Deliberation Record

*Links to the deliberation issue, the Secretary's synthesis and the operator's Resolution. Each position and each objection on its own line, numbered and slugged: `- **P01** <who>: <the position in a sentence>, <link>. (semantic_slug)` and `- **O01** <who>: <the objection in a sentence>, <link>. (semantic_slug)`. The Resolution answers each objection by its ID and slug.*

None.

## 15 Revision History

*One line per change after the first draft: date, what changed, why. After acceptance, only editorial changes are allowed here; a substantive change needs a new MIS.*

- 2026-10-02: first draft.

## Wiki-Links

[[methodology]] [[policy_as_api]]
