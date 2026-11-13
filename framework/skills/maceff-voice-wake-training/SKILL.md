---
name: maceff-voice-wake-training
description: USE when an operator wants to give an agent a wake phrase, record or improve its wake model, or asks why the wake misses or fires falsely. Coaches the operator from choosing a phrase to a measured, declared wake model, with every rule taken from the voice_input policy.
allowed-tools: Read, Bash, AskUserQuestion
---

Coach the operator through defining, recording, training, measuring and declaring the agent's wake phrase.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate voice_input
macf_tools policy read voice_input --section <CEP_MATCH>
```

Read the sections on building a wake model, measuring it, and what a wake authorizes. `<CEP_MATCH>` is the section whose navigation questions match the step you are on.

---

## Questions to Extract from Policy Reading

1. **Consent** - Before any recording, who must be told what, and who must agree?
2. **The phrase** - Which phrases are refused, and what should the operator choose instead?
3. **The clips** - Which kinds, how long, how many to start with, and under which varied conditions in every sitting?
4. **The microphone** - Which commands open it, and when may they be run?
5. **The report** - What does a held-out number show and not show, and which threshold does it describe?
6. **Findings** - What does each finding in a report call for: misses, false alarms, another agent's phrase firing, a perfect score, an empty rate?
7. **Live** - What must be measured live before the model is declared, and for how long?
8. **Declaring** - How is the model declared, and when does it take effect?
9. **Authority** - What may a wake authorize, and what does the agent do instead when a spoken request would change something?

---

## Execution

1. Ask the operator, in a dialog, for the phrase they want and who else may be heard while recording; apply the answers to questions 1 and 2. Run `macf_tools voice wake define "<phrase>"` and show its result.
2. Plan the sittings with the operator from the answers to question 3: which kinds, which conditions each sitting varies. Run `macf_tools voice wake record <kind> ...` only while the operator is present and has agreed, one kind at a time, interleaved.
3. Run `macf_tools voice wake train`, read the report aloud and on screen, and act on it by the answers to questions 5 and 6. Record more and retrain only for a reason the policy names.
4. Agree a live test with the operator from the answer to question 7, and record what it showed, file results and live results kept apart.
5. Declare the model as the answer to question 8 says, and tell the operator when it takes effect. Leave a task note with the report's numbers and the live result.

---

## Critical Meta-Pattern

**Policy as API**: every number and rule used here comes from the `voice_input` policy. This skill holds none of its own; when it seems to need one, that rule belongs in the policy.
