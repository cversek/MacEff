# Voice Generation

**Type**: Infrastructure (Spoken Output and Voice Selection)
**Scope**: All agents (PA and SA), and any agent leading a voice selection with its operator
**Status**: ACTIVE

---

## Purpose

This policy governs the speaking side of the MacEff Voice Input Channel (MIS-0008): what an agent may say aloud and when, what silences it and how it gives way to the operator, how an agent's voice is chosen with its operator, what a voice must never be, how names are respelled so the engine says them right, and how the speech worker runs. The capture side (wake models, the recording indicator, what audio is kept, listening on and off) is in `voice_input.md`; the channel and how the daemon delivers utterances are in `persistent_layer.md`. This policy cites them and does not repeat them.

Text on a screen reaches whoever looks at it. Speech reaches whoever is in earshot: family, colleagues, a visitor, someone in the next room. An agent that talks is also a sound source for the microphone that listens to it. Both facts shape every rule below.

**Core Insight**: Speech is the short form. The full detail stays on screen, where the operator can read it when they choose; what goes aloud is brief, wanted, and safe for anyone to overhear. And the voice is the operator's to shape: the agent proposes, the operator decides, and no voice is made to sound like a real person.

---

## CEP Navigation Guide

**1 What an Agent Says Aloud**
- What may I say aloud, and what never?
- When do I stay silent?
- What do I do while the screen is locked?
- How is spoken text different from text on screen?

**1.1 What Belongs Aloud**
- Which things are right for speech?
- How long should a spoken message be?
- What happens to code and links in spoken text?

**1.2 What Never Goes Aloud**
- Which content is never spoken, whatever the operator asked?
- What do I do instead?

**1.3 While the Screen Is Locked**
- What does `while_locked` control, and what is its default?
- How do I know whether the screen is locked?
- What do I say aloud when the voice section allows speaking while locked?

**1.4 When to Stay Silent**
- When is speaking wrong even though it is allowed?

**2 What Silences Speech and How It Gives Way**
- How do I stop my own speech?
- What happens when the operator starts a recording while I talk?
- Why do two agents never talk over each other?
- Why does my own voice not wake the capture unit?

**2.1 Stopping**
- What does `voice speak --stop` do, and what doesn't it do?

**2.2 Giving Way to a Recording**
- When does speech wait, and when does it stop mid-sentence?
- What is dropped, and what can I do about it?
- I was cut off mid-sentence. How do I learn what the operator actually heard?

**2.3 One Worker, One Voice at a Time**
- What does one speech worker per system mean for my messages?

**2.4 The Speaking Mark**
- What is the speaking mark, and what does it protect?

**3 Choosing a Voice**
- Who leads a selection, and who decides?
- What order must a selection follow?
- What is the trait mapping, and how far can I rely on it?

**3.1 Inferring the Traits**
- Where do my traits come from?
- How many traits, and how do I phrase them?

**3.2 Putting the Traits to the Operator First**
- What must the dialog show before any sample is generated?
- Which questions does it ask, and when do I need the operator's agreement to play audio?

**3.3 Samples, Rounds and Steering**
- How do I generate candidates and what do they say?
- How many rounds, and what if the operator dislikes every candidate?
- How does the operator steer?

**3.4 Recording and Confirming the Choice**
- How is the choice recorded, and with which traits?
- What can refuse a choice, and what then?
- How do I confirm it took effect?

**3.5 What a Voice Must Never Be**
- May I make a voice sound like a real person?
- What do I do when the operator asks for one?

**4 Pronunciation**
- When do I add a respelling, and how?
- Which words does a respelling match?
- Whose table is it, and how do I remove an entry?

**5 Running It**
- What runs the speech worker, and what does it need?
- What does `voice speak` say when nothing is listening?
- How do I read the settings back?

**5.1 The Speech Worker Unit**
- How is the worker declared, and what are its exit codes?
- Where do the engine's model files go, and who installs them?

**5.2 The Commands**
- What does each `voice speak`, `voice show` and `voice select` command do?

**6 Integration with Other Policies**
**7 Anti-Patterns**
**8 Evolution & Feedback**

=== CEP_NAV_BOUNDARY ===

---

## 1 What an Agent Says Aloud

**Speak the short answer; keep the detail on screen.** A spoken message is for the operator who is listening now, and it passes once. Anything they may want to read, check, copy or come back to goes on screen in full. When an operator speaks to you and the label on their message says so (`persistent_layer.md`, the Voice Input Channel), a brief spoken reply fits, with the detail in your turn on screen.

### 1.1 What Belongs Aloud

- A short answer to something the operator said aloud: a sentence or two.
- An alert the operator asked for, such as a long job finished or a wake-up they set. Say what it is and that detail is on screen.
- A status the operator chose to hear. Ask once what they want spoken, and then speak only that.

**Length.** A few sentences at most. A long reading is tiring to hear and cannot be skimmed or interrupted without losing the thread. If the content is longer, say the headline aloud and point to the screen.

**What the engine does with your text.** The text is made fit to hear before it is spoken: a fenced code block is replaced by "code block omitted", a link is read as "a link" (or by its words, if it has some), and markdown marks are dropped. So a path, a command, a URL or a number table gets lost in speech. Do not rely on speaking them; put them on screen.

### 1.2 What Never Goes Aloud

Never speak:
- **Credentials of any kind**: passwords, tokens, keys, codes, recovery phrases, and the contents of any file that holds them.
- **The private content of other people**: messages, mail, personal details, anything a person told you or wrote in confidence.
- **Anything the operator has not chosen to hear in a room others may share.** The operator's own private matters, finances, health, and the content of their private files belong on screen, not in the air.
- **Content you are not sure is safe to overhear.** When in doubt, put it on screen and say aloud only that there is something to read.

**Why.** Speech cannot be taken back or confined to the person it was meant for. A text on screen can be closed; a sentence in a room has already been heard.

**What to do instead.** Say a neutral pointer: "There is something for you on screen." The operator then reads the detail where only they can see it.

### 1.3 While the Screen Is Locked

A locked screen often means the operator is away and others may be near (MIS-0008 R33). The voice section's `while_locked` setting says what happens then:
- `speak` (the default): the agent speaks as usual.
- `silent`: a message queued while the screen is locked is dropped unspoken. Its text is still on screen when the operator returns.

**How the screen state is known.** The worker reads it itself, and treats an unknown state as locked. You do not get a command to read it. A voice message you receive carries the screen state in its label; use that.

**What you say when speaking while locked is allowed.** Only what the voice section allows, and the most conservative reading of that: the short alert the operator asked for, with no private content (1.2). While locked, speak nothing the operator did not ask to hear. Do not change `while_locked` yourself: it is part of the operator's declaration, and what a room may overhear is the operator's choice. When an agent has a voice and no declared `while_locked`, suggest to the operator that they choose between `speak` and `silent`, and say what each does.

### 1.4 When to Stay Silent

Speaking is allowed but still wrong when:
- the operator has told you to be quiet, or has turned listening off to be left alone;
- the operator is not at the machine and has not asked for alerts;
- the message is routine progress: the operator did not ask to hear it, and a stream of it trains them to ignore it;
- the operator is mid-conversation with someone else. Hold until they are done.

When unsure, write; do not speak.

---

## 2 What Silences Speech and How It Gives Way

The operator's voice outranks the agent's. Speech yields to a recording, to the operator's stop, and to other agents' speech in turn.

### 2.1 Stopping

`macf_tools voice speak --stop` drops every queued message and stops the sentence playing within a twentieth of a second; the rest of that message is dropped. Use it when you queued something that is no longer wanted.

### 2.2 Giving Way to a Recording

The speech worker never plays while the capture unit is recording (MIS-0008 R29):
- **Before a sentence**, the worker waits while a recording is open. It keeps the speaking mark fresh while it waits (2.4). If the recording stays open for about five and a half minutes, it says so in its log and drops the rest of that message.
- **During a sentence**, a recording that opens stops that sentence at once, and the rest of that message is dropped. Nothing plays until the recording ends.

**What this means for you.** A message may be cut short, and the dropped part is not queued again. If the content matters, it is on screen (1); speak it again only if the operator asks. An operator who presses a key while you talk is heard, not talked over.

**You are told where you were cut off** (MIS-0008 R55). When a recording cuts your speech, you learn once which of your words the operator heard and which they didn't:
- **Where it appears:** on the voice message that recording produced, after its label ("This recording cut off your speech"). If the operator pressed the key and said nothing, it appears on your next prompt instead (✂️).
- **How it was known:** sentences played to the end are exact. For the sentence cut, the words heard come from the engine's word timings where it gives them ("measured"), and otherwise are estimated from how long the sentence had played ("estimated"). A word still playing at the cut counts as not heard. The Kokoro engine gives no word timings, so its cuts are estimated.
- **What to do with it:** answer the interruption knowing what the operator actually heard. Don't assume the cut-off part landed. If something they didn't hear still matters to the answer, say it on screen, or aloud if they ask. Treat an estimate as approximate: the boundary may be off by a word.
- **What it holds:** your own words, read by your daemon from your home, never the operator's or a sender's. A stop (2.1) is not a cut, and tells you nothing. A cut more than ten minutes old is not told.

### 2.3 One Worker, One Voice at a Time

Spoken output passes through one speech worker per system (MIS-0008 R28). Every agent's messages wait in order and are spoken one at a time, so two agents never talk over each other. A second worker refuses to start while one holds the lock. Your message may wait behind another agent's; do not queue the same thing again because it was not heard yet.

### 2.4 The Speaking Mark

While a message is queued, being made, or playing, and for a moment after, the worker keeps a mark in the agent's voice directory. The capture unit takes no wake while the mark is fresh, and for three seconds after the speech ends, so an alert that contains the wake phrase cannot call itself (MIS-0008 R27). Details of how the capture unit uses it are in `voice_input.md`. The mark protects only the wake: a deliberate key press still opens a recording, and then speech gives way (2.2).

---

## 3 Choosing a Voice

**The agent leads; the operator decides.** The agent infers a few traits from who it is and what it does, puts them to the operator in a dialog, and takes the operator's answer before anything is generated. It then generates candidates from the agreed traits, the operator picks or steers, and the choice is recorded with its traits.

**The order is fixed**: infer traits, ask the operator, take the answer, generate samples, let the operator choose, record, confirm. A sample generated before the operator has answered is a breach (MIS-0008 R31), even if you expect the traits to be accepted.

**The trait mapping is deliberately simple.** `macf_tools voice select samples` reads accent words (such as british, american), male or female words, timbre and pace words (such as calm, brisk, deep), and ranks the engine's voices against them. It always offers a blend of its two best matches as the last candidate. A word it does not know has no effect on the ranking. It is the working prototype's to improve, so treat its candidates as a starting point and let the operator's ear overrule the mapping.

### 3.1 Inferring the Traits

Infer traits from your identity and role: your charter, your name, how you write, how you work. A quiet librarian of an archive and a fast build agent should not sound alike.

- **A few traits: about three to five.** Fewer leave the mapping nothing to rank on; many contradict each other. The voice section holds at most twelve, each at most sixty characters.
- **A few words each**, plain descriptors of how it sounds: "calm", "measured pace", "low and warm", "british accent". Use words from the mapping's vocabulary where they fit (accent, male or female, timbre, pace), and add any other trait the operator should weigh.
- **Describe a sound, not a person.** Never write a trait that names a real person or says to sound like one (3.5).
- **Write them down before the dialog**, so the dialog shows exactly what will be recorded if accepted.

### 3.2 Putting the Traits to the Operator First

At the terminal, put the traits to the operator in a dialog (`AskUserQuestion`), with the context first: say in a line why you are asking and what will happen next. A question asked in prose goes unanswered. When the operator is remote or the session is unattended, `mode_system.md` governs how to ask: do not open a dialog nobody can answer.

**What the dialog must show before any sample is generated:**
- the full list of traits as you would record them, each in the words you would record;
- a short reason each trait follows from your identity or role;
- that samples play aloud through the speech worker, and so to anyone in the room.

**What it asks:**
- whether to accept the traits, change some, drop some, or add others, one answer per question;
- whether now is a good time to play samples aloud. If not, do not generate them.

**Take the answer, and use it.** The traits you generate from are the ones the operator accepted, not the ones you proposed. If the operator changes them, state the changed list back, and ask again if the change is more than a word.

### 3.3 Samples, Rounds and Steering

`macf_tools voice select samples --traits "<trait>" "<trait>"` makes candidates from the agreed traits and queues each through the speech worker, numbered, saying the same line. The default is four candidates (the best matches, then a blend); `--count` changes it, and `--line` changes what each says. Keep the line short and neutral, and say it identically for every candidate so the voices are compared, not the words. The candidates and their traits are kept so a choice can be recorded.

**Rounds.** One round is one run of `voice select samples`. Allow up to three rounds. After each, ask the operator in a dialog: pick a number, hear again with different traits, or none of these.

**Steering.** The operator steers in words: "lower", "slower", "more formal", "less British". Turn that into changed traits, show the new list, and generate again. Do not guess at changes the operator did not say.

**If the operator dislikes every candidate.** Steer once, then once more. If the third round is no better, stop: do not record a choice, leave the voice section as it is (the defaults apply), and tell the operator what the mapping could not do. They may try other traits later or ask a maintainer for other voices. Do not loop for another round to be agreeable, and do not pick for them.

**Playing audio is not free.** Each round is speech in the room. Do not run samples when the operator has said not now, and do not run them again to confirm a choice already made.

### 3.4 Recording and Confirming the Choice

`macf_tools voice select choose N` writes candidate N into the agent's own declaration's voice section, with the traits the candidates were made from (MIS-0008 R30). It keeps the section's other speech settings (language, filter, `while_locked`, engine). It records the traits of the last run of `samples`, so the last run must be the one from the traits the operator accepted. A choice records the traits for a later selection to start from.

**It can refuse, and says why**, in these cases:
- no candidates have been made, so run `samples` first;
- the number is not one of the candidates;
- the declaration is rendered by the operator's tooling: give the operator the speech settings to add; do not edit a rendered file;
- the declaration has no voice section: the operator adds one, naming the capture unit, first;
- the result would not load: it refuses whole rather than write a declaration that cannot load.

A refusal ends the attempt; report it to the operator rather than working around it by editing files.

**Confirm.** Run `macf_tools voice show` and read back the voice, the speed and the traits. Tell the operator what was recorded. New speech settings are read for each message, so the next spoken message uses the choice without a restart.

### 3.5 What a Voice Must Never Be

**A voice is never built to imitate a real person's voice** (MIS-0008 R32), whether the operator named the person or the traits happen to point at one. That includes mixing voices to approach a particular person, and a trait such as "sounds like" a named actor, public figure or acquaintance. Imitating a real voice is impersonation, whatever the intent.

**What to do when asked.** Refuse, plainly, and say why: a voice made to sound like a real person is an impersonation. Offer what you can do instead: ask which qualities the operator likes in that voice, such as pace, warmth, depth and accent, and use those as traits (3.1). Do not record the name as a trait.

**Judgment, not detection.** Nothing in the tool can tell whether a voice resembles someone. The rule rests on the agent leading the selection, and on the operator at each selection. If candidates seem to be approaching a named person, stop and say so.

---

## 4 Pronunciation

The speech engine says some names and terms wrong. When it does, add a respelling: `macf_tools voice speak --say-as WORD=SPELLING`, for example `--say-as Acme=Ack-mee`. Spell it as the engine says it correctly; test it by speaking a short line with the word in it.

**What it matches.**
- Whole words only. A word counts when it stands alone: after whitespace or a line start, and before whitespace, common punctuation (period, comma, question or exclamation mark, semicolon, colon, quote, apostrophe, closing bracket) or a line end. So "Acme." and "Acme's" are respelled, and "Acme-Corp" and "Acmeville" are not.
- Case exactly as listed, and the longest entries first. A word listed as `Acme` does not match `ACME`; list both if both occur.

**Whose table it is.** The table is the agent's own, stored in its voice directory, and applies to everything it says, sample candidates included. Add an entry when the engine mispronounces something you say often. Remove one with `voice speak --unsay WORD`. Do not use the table to change meaning; it only respells for the ear.

**Nothing in it is spoken.** `--say-as` and `--unsay` alone only edit the table, and print how many entries there are. Given text as well, the command also speaks the text.

---

## 5 Running It

### 5.1 The Speech Worker Unit

The speech worker is a declared unit of the agent's primal daemon: `python -m macf.voice.speech <agent home>`, in an interpreter with macf's `voice` extra installed. It takes the one-worker lock or exits 75 (another worker holds it, 2.3), and exits 78 when it cannot start: no agent home, or a missing model file, which it names.

**The engine's model files** live in the agent's voice directory under `models/`: the Kokoro model and voices files. **The operator installs them.** The worker does not fetch them. The engine runs locally, so nothing spoken leaves the machine. Which other engines exist, and whether a voice may blend several, is an open question in MIS-0008 (Q05); this policy does not decide it.

**The worker's log** names what it did without the words: a message dropped while locked, a sentence cut by a recording, a recording that outlasted the wait.

### 5.2 The Commands

All run from an agent's home, and the `voice` extra must be installed where they run.

| Command | What it does |
|---|---|
| `macf_tools voice speak "<text>"` (or text on stdin) | Queues the text for the speech worker and returns at once. With no worker running it queues nothing, says so and exits 1, since text spoken whenever a worker next starts would be out of its time. `--voice` and `--speed` apply to this message only. |
| `macf_tools voice speak --stop` | Drops every queued message and stops the sentence playing (2.1). |
| `macf_tools voice speak --say-as WORD=SPELLING ...` | Adds respellings to the agent's table (4). |
| `macf_tools voice speak --unsay WORD ...` | Removes respellings. |
| `macf_tools voice show` | Prints the speech settings as the worker reads them (voice, speed, language, filter, traits, `while_locked`), and says when no voice has been chosen, so these are the defaults. |
| `macf_tools voice select samples --traits ...` | Makes candidates from the agreed traits and queues each to be spoken (3.3). Only after the operator has accepted the traits (3.2). |
| `macf_tools voice select choose N` | Records candidate N with its traits (3.4). |

**When no worker runs.** `voice speak` and `voice select samples` queue nothing, say so, and exit 1. Do not retry in a loop: tell the operator the speech unit is not running, and keep the answer on screen.

---

## 6 Integration with Other Policies

- `voice_input.md` - The capture side: the recording indicator, wake models, what is kept, listening on and off, and what a wake authorizes. Speech gives way to recordings there; spoken text never authorizes anything either.
- `persistent_layer.md` - The Voice Input Channel, the capture unit and the declared units the worker runs as.
- `mode_system.md` - How to ask the operator when they are remote or the session is unattended, and why a dialog is not opened then.
- `mis.md` - MIS-0008 is the specification this policy implements; its open questions (engines, blends) are not decided here.
- `scholarship.md` - Linking and citing artifacts.

The voice lock (MIS-0008 6.7) and the system capture unit for many agents are not built yet. Their rules arrive with those capabilities, in their own policies.

---

## 7 Anti-Patterns

**❌ Speaking a long answer, a code block or a path**:
- **Problem**: Speech passes once, and code and links are lost to the engine
- **Fix**: Say the headline, keep the detail on screen (1)

**❌ Speaking a credential, a person's private message, or the operator's private matters**:
- **Problem**: Anyone in earshot hears it, and it cannot be taken back
- **Fix**: Say there is something on screen (1.2)

**❌ Generating samples before the operator has answered**:
- **Problem**: Breaks the order the operator asked for; the samples play in the room, unasked
- **Fix**: Put the traits in a dialog first, and take the answer (3.2)

**❌ Looping rounds until the operator relents**:
- **Problem**: Each round is audio in the room, and a pick made to end the loop is not a choice
- **Fix**: Steer within three rounds, then stop with the defaults (3.3)

**❌ A voice, or a trait, built to sound like a real person**:
- **Problem**: Impersonation, whatever the intent
- **Fix**: Refuse, say why, offer traits from the qualities the operator likes (3.5)

**❌ Changing `while_locked` or editing a rendered declaration**:
- **Problem**: What a room may overhear is the operator's choice
- **Fix**: Suggest, and give the operator the settings to add (1.3, 3.4)

**❌ Queueing again because a message was not heard**:
- **Problem**: It may be waiting behind another agent, or was cut by a recording, and will play twice
- **Fix**: Wait; speak again only if the operator asks (2.2, 2.3)

**❌ Retrying `voice speak` when no worker runs**:
- **Problem**: Nothing is spoken, and the loop only hides that the speech unit is down
- **Fix**: Tell the operator the speech unit isn't running, and keep the answer on screen (5.2)

---

## 8 Evolution & Feedback

This policy changes with the operator's corrections, with what hearing it shows, and as the trait mapping, other engines (MIS-0008 Q05) and the voice lock arrive. The number of traits and rounds in section 3 are working rules, set for the prototype and to be revised from use. A skill that coaches a selection holds no rule of its own; when it needs one, the rule belongs here.

**Principle**: Short in the air, full on the screen; the agent proposes a voice and the operator decides it; and no voice borrows a real person's.

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs: what an agent
     says aloud, how its voice is chosen, and the limits on both. -->

[[voice]] [[speech]] [[voice_selection]] [[consent]] [[privacy]]
