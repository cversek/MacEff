---
name: maceff-report-from-experiment
description: "Use when a completed experiment (protocol and analysis with terminal states) needs to become a report for readers outside the working context: colleagues who did not follow the work, sponsors, external reviewers. Reads the reports, public voice, experiments and scholarship policies to discover the current folder layout, deliverable formats, provenance sidecar, voice rules and verification duties, then produces the deliverable, its sidecar, and the pointers in both directions."
allowed-tools: Bash, Read, Grep, Glob, Write, Edit
---

Derive a standalone report from a finished experiment, in the form the reports policy currently prescribes.

---

## Personal Policy Discovery

Check for an agent-specific writing policy at `agent/policies/personal/` (a public-voice or writing-discipline policy is the usual one). If present, read it and apply it alongside the framework's public voice policy. If absent, the framework policies alone govern.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate reports
macf_tools policy read reports
macf_tools policy navigate public_voice
macf_tools policy read public_voice
macf_tools policy navigate experiments
macf_tools policy navigate scholarship
```

Read `reports` and `public_voice` completely. From `experiments`, read the sections that answer what an experiment's completion documentation contains and which of its files are knowledge-web nodes. From `scholarship`, read the sections on node classes, provenance, and wiki-link normalization.

---

## Questions to Extract from Policy Reading

1. **Precondition** - What state must the experiment be in before a report may be derived from it, and which of its files is the technical record the report cites?
2. **Home** - Where does the policy say a report lives, how is the folder named, and which files must and may it contain?
3. **Deliverable** - What is the default deliverable format, what must it be self-contained against, and when are other formats produced?
4. **Sidecar** - What does the provenance sidecar record, which keys are required, and which file carries the wiki-links?
5. **Voice** - What voice rules apply to a reader outside the working context, which vocabulary must not appear, and what must be explained at first use?
6. **Verification** - What must be checked before a number from the analysis appears in the report, against what, and where is the check recorded?
7. **Figures and scope** - How are figures produced for the report's audience, and what must a report that includes restricted data state, and where?
8. **Structure** - What structure does the policy give an experiment-derived report, and how does it relate to the general report structure?
9. **Pointers** - What must point from the report to the experiment, and from the experiment to the report?
10. **Publication** - How are published copies recorded and kept at a stable address?
11. **Versions** - When is the result a new version of an existing report rather than a new report, how is a version labelled and where does the label appear, what happens to the earlier version's files, and what must the sidecar's ledger and the deliverable's opening say about the change?
12. **Domain** - Which domain specialization does the policy register for this content, what deliverable form and structure does it prescribe, and what does its build depend on?

---

## Execution

1. Confirm the precondition from question 1; if it is not met, stop and say what is missing.
2. Establish audience, format, and scope from the request and the experiment's own scope statements; state them before writing. Decide, from question 11, whether this is a new report or a new version of one that exists; from question 12, which domain row applies.
3. Build the folder and files the answers to questions 2 to 4 prescribe; for a new version, freeze the earlier version's files under their versioned names and extend the ledger before writing.
4. Write the deliverable under the answers to questions 5 and 8.
5. Perform the verification from question 6 on every number, correct the analysis where the check finds an error, and record the check in the sidecar.
6. Produce figures per question 7; place the classification statement where question 7 says.
7. Render and, if asked, publish; record the address per question 10.
8. Record the pointers from question 9 on the experiment side and in the task system.
9. Report to the operator with the unrestricted-scope numbers first, the folder path, and any published address.

---

## Critical Meta-Pattern

**Policy as API**: this skill points to policies without encoding their contents. The folder layout, sidecar keys, voice rules and verification duties live in the reports and public voice policies; when they change, this skill's questions extract the new answers without edits here.
