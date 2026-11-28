---
name: maceff-voice-select
description: USE when an agent has no chosen voice, when the operator wants to change how the agent sounds, or says the voice doesn't fit. The agent leads the selection with its operator, inferring traits from its own identity, asking first, then playing samples and recording the choice, every rule taken from the voice_generation policy.
allowed-tools: Read, Bash, AskUserQuestion
---

Lead the choice of this agent's voice with its operator: traits first, samples next, the choice recorded with its traits.

---

## Policy Engagement Protocol

```bash
macf_tools policy navigate voice_generation
macf_tools policy read voice_generation --section <CEP_MATCH>
```

Read the sections on choosing a voice, what a voice must never be, and what may be said aloud. `<CEP_MATCH>` is the section whose navigation questions match the step you are on.

---

## Questions to Extract from Policy Reading

1. **Traits** - Where does the agent look to infer its traits, how many, and how is each phrased?
2. **Asking first** - What must the dialog show the operator before any sample is made, and what answers can it take?
3. **Never** - What voice must the agent refuse to build, and what does it offer instead?
4. **Samples** - What do the candidates say, how are they played, and how many rounds before stepping back?
5. **Steering** - What does the agent do when the operator dislikes every candidate, or wants a trait changed?
6. **Recording** - How is the choice recorded, what goes with it, and how does the agent confirm it took?
7. **Aloud** - While samples play, what may be heard in the room, and what silences them?

---

## Execution

1. Read the agent's own identity and role as the answer to question 1 says, and draft its traits.
2. Put the traits to the operator in a dialog, as the answer to question 2 says, and wait for the answer. Generate nothing before it.
3. Run `macf_tools voice select samples --traits ...` with the agreed traits, and let the operator listen.
4. Steer or repeat as the answers to questions 4 and 5 say; refuse as question 3 says.
5. Run `macf_tools voice select choose <number>`, then `macf_tools voice show`, and read back what was recorded. Leave a task note with the traits and the choice.

---

## Critical Meta-Pattern

**Policy as API**: every rule used here comes from the `voice_generation` policy. This skill holds none of its own; when it seems to need one, that rule belongs in the policy.
