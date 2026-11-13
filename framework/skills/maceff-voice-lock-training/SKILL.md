---
name: maceff-voice-lock-training
description: USE when an operator wants a voice lock on an agent, wants it re-measured, or asks why the agent said a voice couldn't be matched or that voice is locked out. Coaches enrollment, annotation, measurement and the choice of threshold, every rule taken from the voice_lock policy.
allowed-tools: Read, Bash, AskUserQuestion
---

Coach the operator through enrolling their voice and measuring the agent's voice lock.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate voice_lock
macf_tools policy read voice_lock --section <CEP_MATCH>
```

Read the sections on what the lock is and isn't, training and measuring it, and what a raised guard requires. `<CEP_MATCH>` is the section whose navigation questions match the step you are on.

---

## Questions to Extract from Policy Reading

1. **What it proves** - What does a match show, and what does it never show?
2. **Ready** - Is a speaker embedder chosen and measured yet, and what must be true before a lock is declared?
3. **Consent** - Whose voices are recorded as other speakers, and what must each be told?
4. **The clips** - Which annotations, how many of each, under which varied conditions?
5. **The report** - What must it hold before a threshold is stored, and what does each number mean?
6. **Coverage** - Does the lock cover the keys as well as the wake phrase here, and who decides?
7. **Lockout** - What are the declared attempts, window and duration, and how can a lockout be used against the operator?
8. **The guard** - What does the agent do when its guard is raised, and who may lower it?

---

## Execution

1. Answer question 2 first. If no embedder is measured yet, tell the operator what remains and stop.
2. Plan the sittings with the operator from the answers to questions 3 and 4, and get each recorded person's agreement before recording.
3. Train, read the report with the operator as question 5 says, and record more where it falls short.
4. Agree coverage and lockout settings with the operator, as questions 6 and 7 say; the declaration is theirs to change.
5. Tell the operator what happens on a lockout and how to lower the guard, as question 8 says. Leave a task note with the report's numbers.

---

## Critical Meta-Pattern

**Policy as API**: every rule used here comes from the `voice_lock` policy. This skill holds none of its own; when it seems to need one, that rule belongs in the policy.
