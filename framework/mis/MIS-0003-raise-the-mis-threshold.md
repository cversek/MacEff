# MIS-0003: Raise the MIS Threshold to Major Changes

**Number**: 0003
**Type**: Process
**Status**: Accepted
**Authors**: the operator; drafted by the Secretary of deliberation #493
**Secretary**: the Secretary of deliberation #493
**Deliberation**: none (the operator decided the change directly, on the pull request for #504; see section 14)
**Created**: 2026-10-04
**Updates**: MIS-0001: R01 (PR_MUST_cite_accepted_MIS)
**Supersedes**: none
**Lands-in**: framework/policies/base/meta/mis.md, framework/policies/base/meta/policy_writing.md, framework/glossary.md
**Resolution**: Accepted by the operator's merge of pull request #507. The operator's decision comment on that pull request, quoted in full: "**Decision on MIS-0003: Accepted.** I raised this change myself, in my comment on #504 (quoted as P01). For this MIS I name two maintainers: the head maintainer, and the Secretary who drafted it. It was opened before the host-side maintainer joined. The Secretary wrote it and the head maintainer reviewed it. The MIS was revised once, in answer to the head maintainer's review (P02). So I close the discussion now under MIS-0001-R48, without waiting out the period, as I did for MIS-0001. No objections were recorded. The head maintainer made one suggestion: a policy split out of, or renamed from, an existing one is a change to that policy. It is adopted in the term "new policy". MIS-0003 is Accepted. MIS-0003-R01 replaces MIS-0001-R01: an MIS is required only for a new policy or a major architectural change. (Prepared with Claude Opus 5.5 in Claude Code.)" https://github.com/cversek/MacEff/pull/507#issuecomment-6094017082. The maintainers of this MIS are the head maintainer and the Secretary, as the operator named them. No objection was recorded, and no maintainer raised a critical objection. The operator asked the Secretary to post the decision and merge with the operator's identity, so the Secretary made this commit and performed the merge at that instruction.

---

## 1 Summary

MIS-0001 required an accepted MIS for any pull request that adds a subsystem, changes architecture across components, or changes what an agent is allowed to do, and the `mis` policy counted any new MUST or MUST NOT in policy text as a change to what an agent may do. So a small rule added to an existing policy needed the whole process. The operator raised the bar: an MIS is now required only for a new policy or a major architectural change. Every other change stays an issue and a pull request, and any author may still write an MIS for it.

## 2 Motivation

- **The first framework pull request after MIS-0001 was accepted raised the question over two sentences.** A wind-down skill and its protocol (#504) had no new subsystem and no architecture change, yet two of its sentences arguably changed what an agent may do, so the threshold asked whether a full MIS was needed. The operator answered on that pull request: "I think that req is going too far if every other policy tweak kicks the MIS process off. Let's raise the bar to only require for major architectural lifts and whole policy introductions." Evidence: the comment on #504, 2026-10-04 (an incident on the record).
- **A record costs more than it returns for small rules.** An MIS asks for a synthesis or a recorded reason, a final comment period after every maintainer has commented, and a cold-reader trial before Final. For one new rule inside an existing policy, the pull request and its review already carry the decision and its reasons. Evidence: reasoning from the process as specified in MIS-0001.

## 3 Goals and Non-Goals

**Goals**
- Keep the MIS for the changes that need a durable record of why: a new policy, and a major architectural change.
- Let a rule added to an existing policy, or a change to what an agent may do, go through an ordinary reviewed pull request.

**Non-goals**
- Changing any other part of the MIS process. Only MIS-0001-R01 (PR_MUST_cite_accepted_MIS) is replaced.
- Removing the voluntary MIS. MIS-0001-R02 (author_MAY_write_MIS_for_any_change) still lets an author write one for any change.

## 4 Guide-Level Explanation

An agent adds a MUST to an existing policy, or a hook that blocks one more command. Before this MIS, that needed an accepted MIS. Now it is a pull request: the policy text ships with the capability, a maintainer reviews it, and the operator merges it. An agent who adds a new policy document, a new subsystem such as a persistent layer, or a change to how components divide their work or talk to each other still writes an MIS first.

## 5 Terms

- **major architectural change**: a change that adds a subsystem or changes architecture across components.
- **new policy**: a policy document added under `framework/policies`, as opposed to a change to an existing one; a document split out of, or renamed from, an existing policy is a change to that policy.

## 6 Specification

- **R01** [MUST · judgment: the operator, at merge] A pull request that introduces a new policy or makes a major architectural change MUST cite an accepted MIS. (PR_MUST_cite_MIS_for_major_change)

## 7 Rationale and Rejected Alternatives

**Why R01 replaces MIS-0001's R01.** The operator ruled that the threshold went too far: "Let's raise the bar to only require for major architectural lifts and whole policy introductions." R01 says exactly that, in the glossary's words. "Major architectural lifts" becomes "a major architectural change", defined by the two architecture tests the policy already had: a new subsystem, or a change to architecture across components. "Whole policy introductions" becomes "a new policy", a new document under `framework/policies`. The clause that caught every policy tweak, "changes what an agent is allowed to do", is the one removed.

**What still guards a change to what an agent may do.** `core_principles` still requires that policy ship with its capability, in one pull request, and a maintainer still reviews it. What goes is only the requirement for a separate decision record.

**Rejected**
- **Keep the old threshold and judge each case.** Rejected by the operator's ruling: the first case showed that "what an agent may do" catches nearly any policy change.
- **Raise the bar by editing MIS-0001 directly.** Rejected: MIS-0001 is accepted, and MIS-0001-R35 (substantive_change_MUST_be_new_MIS) requires a substantive change to come as a new MIS that names the old one.
- **Count every new policy file as a new policy.** Rejected in answer to P02 (head_maintainer_review): read literally, splitting one long policy into two files would need an MIS although nothing the policy requires has changed. A document split out of, or renamed from, an existing policy is a change to that policy.
- **Drop the threshold entirely.** Rejected: a new policy or a new subsystem is exactly where a cold reader later needs to find why.

## 8 Prior Art

- PEP 1: small enhancements or patches often need no PEP and go through the ordinary patch workflow. https://peps.python.org/pep-0001/
- The Rust RFC process: many changes, including bug fixes and documentation improvements, go through the normal pull request workflow, and only "substantial" changes need an RFC. https://github.com/rust-lang/rfcs
- MIS-0001, whose threshold this MIS narrows.

## 9 Compatibility and Deployment

- **No open pull request is affected.** The persistent layer still needs its MIS (MIS-0002), because it adds a subsystem.
- **Deployments** receive the changed policy and glossary through the framework overlay at their next refresh, and need do nothing else.

## 10 Security and Safety

- **Fewer forced records for permission changes.** A new hook, gate or permission rule no longer needs an MIS by itself. It still ships with its policy (`core_principles`, policy ships with its capability), is reviewed by a maintainer, and is merged only by the operator.
- **No change at run time.** This MIS changes policy text and the glossary only.

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | judgment | the operator, at merge | standing |

**Cold-reader trial.** Due before this MIS becomes Final, on the landed `mis` policy §1.2: a reader who saw neither this MIS nor its pull request decides, for a few example changes, whether each needs an MIS.

## 12 Landing Plan

One pull request carries this MIS and its landing:
- `mis` policy §1.2: the threshold and its tests, citing MIS-0003-R01 (PR_MUST_cite_MIS_for_major_change);
- `policy_writing`: its one-line pointer to the threshold;
- the glossary: the two new terms;
- MIS-0001: an editorial line in its Revision History naming this MIS and R01.

## 13 Open Questions

None.

## 14 Deliberation Record

- **P01** The operator decided the change directly, on the pull request for #504, 2026-10-04, quoted in full: "I think that req is going too far if every other policy tweak kicks the MIS process off. Let's raise the bar to only require for major architectural lifts and whole policy introductions." No deliberation was convened (MIS-0001-R22 (operator_MUST_convene_or_explain)); the Resolution records why. (operator_raised_the_bar)

- **P02** The head maintainer reviewed the pull request, 2026-10-10 (https://github.com/cversek/MacEff/pull/507#pullrequestreview-5477446166): "No critical objection. I'd merge it, with that clause if the Secretary agrees." The clause: "a document split out of, or renamed from, an existing policy is a change to that policy". The Secretary agreed, and the term **new policy** now carries it, in this MIS, the glossary and `mis` policy §1.2. (head_maintainer_review)

Objections recorded: none.

## 15 Revision History

- 2026-10-04: first version, with the pull request that lands it.
- 2026-10-10: in answer to P02, the term **new policy** excludes a document split out of, or renamed from, an existing policy. R01 is unchanged. The branch was brought up to date with main.
- 2026-10-10: the operator named the maintainers and closed the discussion under MIS-0001-R48. The Status moved to Accepted with the Resolution, as the last commit before the merge.

## Wiki-Links

[[methodology]] [[policy_as_api]]
