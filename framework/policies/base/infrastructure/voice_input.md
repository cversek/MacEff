# Voice Input

**Type**: Infrastructure (Voice Capture, Wake Models and Measurement)
**Scope**: All agents (PA and SA), and any agent coaching an operator through wake training
**Status**: ACTIVE

---

## Purpose

This policy governs the capture side of the MacEff Voice Input Channel (MIS-0008): how a wake model is defined, recorded, trained and measured, what a wake or any other utterance may authorize, what the recording indicator must show, what happens to audio, and how listening is switched on and off. The channel itself, the label an utterance carries, and how the daemon delivers it are in `persistent_layer.md`; this policy cites them and does not repeat them.

A wake model is a small classifier that scores a stream of audio for one phrase. It is easy to make one that looks perfect on the files it was built from and fails in the room it was built for, and it is easy to forget that a phrase said aloud is open to anyone who can reach the microphone. Both mistakes cost the operator: the first with false wakes and missed calls, the second with trust.

**Core Insight**: A clean number on files says little. Recordings differ in more ways than voices do, and a model finds the easiest difference. What counts is the real microphone, the real room and real people, measured live. And whatever the model decides, a wake is only a doorbell: it authorizes nothing.

---

## CEP Navigation Guide

**1 Measuring a Wake Model**
- What does a number from held-out clips tell me, and what doesn't it?
- Why can a model look perfect and still fail?
- A score is perfect. What now?
- How do I measure in the real room?
- How do I report a result?

**1.1 What a Held-Out Number Shows**
- What is held out, and when is that decided?
- What does the held-out test never cover?
- Which threshold do the report's numbers describe?

**1.2 Reading a Perfect or Near-Perfect Score**
- How many clips make a zero count believable?
- What should I look for when nothing goes wrong?

**1.3 Measuring Live**
- What must I measure before saying a model works?
- How long must I listen before a false-alarm rate means anything?
- Why does a rejected fire still count?

**1.4 Reporting Results**
- What goes in a report of a result?
- How do file results and live results differ in the report?

**2 What a Wake or Utterance Authorizes**
- What may I do on a voice message?
- Does matching the wake phrase prove who spoke?
- What do I do instead of acting on spoken instructions?

**3 The Recording Indicator**
- What must the indicator show, and when?
- When does a recording start and end?
- What if the indicator can't be shown?

**4 Audio: What Never Leaves Memory and What Is Kept**
- Is raw audio ever written down?
- What clips are kept, where, and for whom?
- What consent do I need before recording?

**5 Listening On and Off**
- What does listening off do?
- Why does a declared hotkey still record while listening is off?
- What does the capture unit never wake on?

**6 Building a Wake Model**
- What order do I follow, from phrase to declared model?
- Which phrases are refused?
- Which kinds of clips do I record, how many, how long, under what conditions?
- What does training do with the clips?
- What do I do with a report that shows misses or false alarms?
- When do I retrain?
- When does a new model take effect?

**6.1 Choosing and Defining the Phrase**
- Which phrases are refused, and what do I choose instead?

**6.2 Recording Clips**
- Which kinds of clips do I record, how long is each, and how many?
- Under which varied conditions, and why in every sitting?

**6.3 Training**
- What does training do, and what does it refuse?
- How do `test` and `status` differ from `train`?

**6.4 Acting on the Report**
- What do I do with misses, false alarms, or another agent's phrase firing?

**6.5 Retraining and Declaring**
- When do I retrain, and when not?
- How and when does a model take effect?

**7 The Commands**
- What does each `voice` command do, and what does it print?
- Which commands open the microphone?

**8 Integration with Other Policies**
**9 Anti-Patterns**
**10 Evolution & Feedback**

=== CEP_NAV_BOUNDARY ===

---

## 1 Measuring a Wake Model

### 1.1 What a Held-Out Number Shows

`macf_tools voice wake train` and `voice wake test` report how a model does on clips it was not trained on. That is a real measurement of one thing: how the model does on those clips. It is not a measurement of how it will do tomorrow in the room.

**What is held out.** One clip in four of each kind is held out, and which ones is fixed at the moment each clip is recorded, by its place among the clips of its kind: the fourth, eighth, twelfth and so on. A clip's set never changes afterward. Training reads only the training clips, and the test reads only the held-out ones, so no clip a model trained on is in the numbers that justify it (MIS-0008 R25). The reason it is fixed at recording: a split decided at training time can be re-rolled until the number looks good, and then the held-out clips have shaped the model.

**What it never covers.**
- Held-out clips come from the same sittings as the training clips, so they share the same mic, room, mood and day. The test shows that the model learned the clips, not that it works in a different room or on a different day. Only live use shows that.
- Repeated cycles of train, look at the report, record more, train again slowly teach the model about the held-out clips through your choices, even though no clip moves. Treat a number as weaker each time you tuned against it.
- The conditions listed in a report are those recorded on the held-out clips only. A condition that appears only on training clips was never tested.

**Which threshold the report describes.** Training picks the model's threshold from training scores only, never from the held-out clips, so the report is a measurement and not a fit. The report's misses and false alarms are counted at that threshold, and the live detector fires at the same one, stored in the model file. The voice section's `detector_bar` can override it. Where an override is declared, the report doesn't describe live behavior at that bar, so measure live (1.3) or leave the override out.

The stored report carries the fields MIS-0008 R24 requires: held-out counts, misses, the score of each held-out phrase, how many near misses and other agents' phrases fired, false alarms and the seconds of held-out background they were counted over, false alarms per hour, the conditions, and a caveat that only live use measures the real room.

### 1.2 Reading a Perfect or Near-Perfect Score

**A perfect score is a bug to explain.** Zero errors in n trials supports only "the true rate is under about 3 in n" at 95% confidence. Zero misses on 3 held-out phrases allows a miss rate of nearly one in one; zero in 25 still allows about 11%.

When nothing goes wrong, ask what the model could be using other than the words:
- Did every kind go through the same microphone, the same room, the same gain and the same sittings? Clips recorded under different conditions per kind let a model tell the kinds apart by the conditions. Record each kind in each sitting, interleaved, and never mix in audio that did not come from the live microphone (synthetic speech, files recorded elsewhere). `voice wake record` takes only the live microphone for this reason.
- Do the held-out counts in the report make the claim? A kind with fewer than four clips has none held out for it, and `false_alarms_per_hour` is empty when no speech or room clip is held out.
- Do the listed conditions include the one the model will meet?

If you cannot explain a perfect score, treat the model as unmeasured.

### 1.3 Measuring Live

**Before saying a model works, measure it live**, with the declared bar, the real microphone, the real room and the real people:
- the operator saying the phrase from the places and at the distances they will use it, counting calls missed;
- other people in the room talking, and media playing, counting wakes nobody intended;
- other agents' phrases on this machine, said by the operator, counting wakes of this agent;
- ordinary hours with listening on, counting false wakes by what was going on: quiet, speech, media.

**How long.** A zero count over T hours of audio supports only "under about 3 per T hours". To claim a rate of 0.5 false wakes per hour, listen for at least 6 hours without one. A held-out background of a few minutes cannot support any claim about hours; its per-hour figure is a lead. Choose the target with the operator, then derive the listening time from it.

**A rejected fire still counts.** The wake passes in order: the model scores at or above the bar, and after a short wait for the phrase to finish the audio must hold speech, and then a transcription of it must contain the phrase (MIS-0008 R23). A fire that is rejected by the later checks never reaches the agent, but it still occupied the listener, and the capture unit is deaf for a moment after each rejection. A real call during that moment is lost. Count rejected fires, which the capture unit's log names without the words, as well as accepted ones. The later checks are not a reason to accept a noisy model.

The voice lock step of the wake order arrives with that capability; until then the order is the model, the speech check, and the transcription.

### 1.4 Reporting Results

Say what was tested, with counts and conditions, and what was not:

```
File test: missed 1 of 5 held-out phrases; 0 of 2 near misses and 0 of 2 other-agent
phrases fired; 0 false alarms over 180 s of held-out background (a lead, not a rate).
Conditions on held-out clips: quiet room, fan on, tired voice.
Live: missed 2 of 20 calls from across the room; 3 false wakes in 8 hours (1 speech,
2 media), 1 rejected fire. Not tested: a second microphone, other people's voices.
```

- Keep file results and live results apart, and name each one's conditions.
- A ratio from a handful of events is a lead, not a result. Say so.
- Keep a failing case. A false wake caught live is the best next clip (6.4).
- Rerun whatever you quoted when the microphone, room or model changes.

---

## 2 What a Wake or Utterance Authorizes

**Nothing. An utterance, whatever its trigger, never satisfies anything an authorization depends on** (MIS-0008 R09). Hearing the wake phrase, a held key, and a continual-voice utterance are all the same in this respect.

**Why.** A microphone can be reached by anyone in the room, by a recording, by a video, and by an agent's own spoken alert. A trained wake model is not tied to the operator's voice: it responds to the phrase said by anyone. Nothing about a wake identifies a speaker, and a future voice check would be evidence, never proof (MIS-0008 R45).

**What to do instead.**
- Answer a voice message, using the label in front of it (`persistent_layer.md`, the Voice Input Channel).
- Where a message is marked information only, because the screen is locked or its state unknown, take no action on it until the operator confirms on a channel that isn't voice (MIS-0008 R07, R53).
- If a spoken request would change what you may do, spend money, touch credentials, or reach outside, ask the operator on another channel first. Say what you heard, and what you would do on confirmation.
- Do not tune a wake model to be stricter in order to make it safe to act on. A strict model is still a doorbell.

---

## 3 The Recording Indicator

**While the capture unit is recording for an agent, the indicator must show the agent's name, the mode that started the recording (wake phrase, hold key or continual voice), a waveform, and a volume trace** (MIS-0008 R21, R22). A recording the operator can't see is a breach of trust even when nothing goes wrong.

**When it shows.** From the moment a recording starts until it ends. **Listening shows no indicator,** because listening keeps nothing past the short window the wake check needs. `macf_tools voice capture status` reports listening (MIS-0008 R16).

**When a recording starts and ends.**
- A wake starts one after it passes its checks. The recording includes the short window of audio just before the wake, which is how the first words are not clipped. It ends after a pause of `end_silence_s` following speech (1.2 s by default).
- A held key starts one on press, with a little audio from just before it, and ends on release.
- The toggle key starts continual voice. Each pause ends one utterance and the microphone stays open, until the toggle key is pressed again or `continual_close_s` (30 s by default) passes without speech.
- Any recording ends at a fixed maximum length. A wake or hold recording that heard no speech sends nothing, and a wake recording that hears none is cancelled after a few seconds.
- A recording is delivered as text with closed metadata; empty text is dropped and said in the unit's log.

**If the indicator can't be shown.** The capture unit refuses to start without a display for it, rather than record unseen (`persistent_layer.md`, the capture unit). Do not work around that by recording some other way. Ask the operator to fix the unit's display environment.

---

## 4 Audio: What Never Leaves Memory and What Is Kept

**Raw audio of a recording stays in the capture unit's memory** (MIS-0008 R13). It is transcribed from memory and dropped, never written to disk and never sent anywhere. The unit's log, like the daemon's event log, names an utterance by id and outcome, never by its words (MIS-0008 R10). While listening, the unit holds only the short window the wake check needs.

**What is kept on purpose.** The clips `voice wake record` makes are the one exception, because the operator records them to train and measure a model. They are 16 kHz mono WAV files kept in the agent's home under `.maceff/voice/wake/<phrase slug>/clips/<kind>/`, with a manifest line for each (kind, set, time and the conditions you gave). They stay until deleted. A trained model beside them holds weights and a report, never audio, and is stored as plain arrays without pickle so a long-lived unit can load it without running anything it contains.

**What to do about them.**
- Before recording, tell everyone whose voice will be captured what is recorded, where it lives and that it can be deleted. This includes family members and colleagues whose speech serves as negatives, and any speech in the background. Ask each for agreement.
- Keep the clips out of version control and shared folders unless the operator says otherwise. They are people's voices.
- Describe conditions, not people. The conditions text is stored in the manifest and in the model's report; write "tired, fan on", not names.
- No command deletes clips yet. The operator removes the phrase's folder, which removes its clips, manifest and model together; the model then has to be trained again. A retention period for kept clips is an open question in MIS-0008 (Q06); until it is decided, the operator decides what to keep.

---

## 5 Listening On and Off

**`macf_tools voice listen off` closes the microphone between recordings, and nothing is read while it is off** (MIS-0008 R15). `on` opens it again. The switch is a file in the agent's home, read on every pass, so it takes effect within a frame and survives restarts of the unit and the machine. Listening also stays closed while no wake phrase and model are declared, since there is nothing to listen for.

**A declared hotkey still opens one recording while listening is off.** That is a deliberate press on a declared device (MIS-0008 R17), and the indicator shows it (R21). Listening off is about the always-open ear, not about the operator's own keys. When that recording ends, the microphone closes again. If you want no recording at all, the operator removes the key from the declaration; no command or socket can open the microphone (R18), and none will be added.

**What it never wakes on.** The capture unit takes no wake while the agent's own speech is playing, and for three seconds after, so an alert containing the phrase cannot call itself (MIS-0008 R27). A held or toggle key is a deliberate press and is not blocked by this. Instead, the agent's speech gives way: the sentence playing stops the moment the recording opens, the rest of that message is dropped, and nothing more plays until the recording ends (R29). An operator who presses a key while the agent talks is heard, not talked over.

**The command waits for the unit to agree.** After switching, `voice listen` waits a few seconds for the capture unit's status to match and says so if it doesn't. A mismatch means the unit may not have read the switch yet, or isn't running. Read the printed status; do not assume the switch took.

---

## 6 Building a Wake Model

The order is: define the phrase, record clips of each kind, train, read the report, record more where it falls short, train again, measure live, then declare the model. A skill coaches an operator through this by pointing at this policy and holds no rule of its own.

### 6.1 Choosing and Defining the Phrase

`macf_tools voice wake define "<phrase>"` refuses a phrase that cannot work, and says why:
- one word, which ordinary talk sets off;
- fewer than five letters in all, too short to tell apart from other speech;
- a phrase too common in ordinary talk, such as a greeting or a bare command.

**What to choose instead.** Two or more words, distinctive, unlike any other agent's phrase on the machine and unlike common speech. A phrase must be unique per capture unit, and so must a hotkey (MIS-0008 R26). The phrase is stored in a folder named from it, so a changed phrase is a new model and starts again from no clips.

### 6.2 Recording Clips

`macf_tools voice wake record <kind> --count N --conditions "<what differs>"` counts down, then records each clip from the live microphone and keeps it. This opens the microphone, so run it only when the operator has agreed and is present.

| Kind | Length | What to say or do |
|---|---|---|
| `phrase` | 2.5 s | Say the wake phrase as you would to call the agent. |
| `near_miss` | 2.5 s | Say something close that isn't it: a near rhyme, half of it, another name. |
| `other_phrase` | 2.5 s | Say another agent's wake phrase on this machine. |
| `speech` | 30 s | Talk or read aloud normally, with pauses. |
| `room` | 60 s | Stay quiet, so the room is recorded as it usually sounds. |

**How many.** The trainer refuses with fewer than 12 phrase clips to train on or fewer than 3 held out, which 15 clips of the phrase give. That is a floor to train at all, not evidence. A starting set, with its basis:
- About 20 phrase clips. With one in four held out that is 5 held out, so zero misses would support only "under 60%". More clips tighten the claim; keep recording until the held-out count supports the miss rate you need (1.2).
- At least 8 clips of each other kind. Fewer than 4 of a kind leaves none held out for it, and the report has nothing to say about that kind. With 8, two are held out.
- `other_phrase` clips only where another agent's phrase exists on this machine, and then one set per phrase, said as naturally as the real one.
- Held-out `speech` and `room` clips are the only background the report counts false alarms over, so a few minutes of them supports no per-hour rate (1.3).

**Under varied conditions, in every sitting.** Record every kind in each sitting and interleave them, with the real microphone, in the real room, at the real gain. Then vary what will vary in use, naming each in `--conditions`:
- distance and direction from the microphone, and posture;
- voice: rested, tired, hurried, quiet, loud, a cold;
- room noise: quiet, fan or air conditioning on, music, a television, the street;
- anything that failed live: chewing, a held nose, speaking while typing.

For `speech` and `room`, include what actually happens at the machine: family talk, media, typing, the fan. White noise or a silent room is not a negative: a detector trained on it fires every few seconds on a real one. Real false wakes caught live belong here too, recorded as the kind they were.

**Do not pad or process clips** and do not substitute synthetic speech. Differences in how the kinds were made are shortcuts for the model, as in 1.2.

### 6.3 Training

`macf_tools voice wake train` fits the model on the training clips, re-weights the negatives it still scores high, chooses the threshold from training scores alone, measures on the held-out clips, and stores the model with its report. It refuses, naming what is missing, when there are too few phrase clips or the phrase is refused.
`macf_tools voice wake test` measures the stored model again on the held-out clips, including any recorded since training, and replaces the model's report. It never changes the model. `macf_tools voice wake status` shows the clips kept per kind, how many to train on and how many held out, and the model's age, threshold and last numbers.

### 6.4 Acting on the Report

Read the report with 1.1 and 1.2 first. Then:

- **Near misses fired, or false alarms above zero.** Record more of the kind that fired (`near_miss`, `speech` or `room`), under the conditions where it fired, then train again. These cost more than misses: a false wake takes the listener, and the later checks cannot give the time back.
- **Another agent's phrase fired.** Do not declare the model for use. This is the error that matters most, because one agent's phrase must never wake another (MIS-0008 R24). Record more `other_phrase` clips of that phrase, or choose a more distinct phrase and start again (6.1).
- **Misses.** Record more `phrase` clips under the conditions the misses came from, then train again. A missed call can be repeated; a false wake can't be taken back.
- **A perfect report.** See 1.2, then measure live (1.3). Do not stop at the file result.
- **Empty `false_alarms_per_hour`.** No speech or room clip was held out. Record more of those kinds.

### 6.5 Retraining and Declaring

**Retrain** when:
- the report or live use shows misses or false alarms, and you have recorded clips that address them;
- the microphone, its gain, the room, or the operator's voice has changed;
- another agent has taken a phrase on this machine (record `other_phrase` clips for it);
- the report is from clips that no longer reflect how the agent is used.

Do not retrain only to move a number. Each cycle weakens the held-out set (1.1).

**Declare** the model only after the report and live measurement are acceptable to the operator. The voice section names the phrase and the model together (`wake_phrase` and `wake_model`), the model's path being relative to the agent's home; `voice wake define` prints both. The capture unit loads the model when it starts, so a new or retrained model takes effect at its next start, and the operator decides when that is. After a restart, measure live again.

---

## 7 The Commands

All run from an agent's home, and the `voice` extra must be installed where they run.

| Command | What it does | Opens the microphone |
|---|---|---|
| `macf_tools voice wake define "<phrase>"` | Refuses a phrase that can't work; otherwise creates the phrase's folder and prints the declaration lines. | No |
| `macf_tools voice wake record <kind> [--count N] [--conditions "..."] [--phrase "..."]` | Records clips of a kind from the live microphone and keeps each, saying which set it fell in. Default count is 5. | Yes |
| `macf_tools voice wake train [--phrase "..."]` | Trains, measures on held-out clips, stores model and report, prints the summary. | No |
| `macf_tools voice wake test [--phrase "..."]` | Measures the stored model again on held-out clips and replaces its report. | No |
| `macf_tools voice wake status [--phrase "..."]` | Prints clips per kind and the model's age, threshold and numbers. | No |
| `macf_tools voice listen [on\|off]` | Switches listening, or says whether it is on, then the capture unit's state. Exit 1 if the unit's status does not agree in time. | Controls it |
| `macf_tools voice capture status` | Says what the capture unit's microphone is doing: recording for which agent and mode and for how long, listening, closed, or no unit running (exit 1). | No |

Without `--phrase`, the commands use the voice section's phrase. `macf_tools voice listen` and `capture status` read the unit's state from the agent's own daemon.

---

## 8 Integration with Other Policies

- `persistent_layer.md` - The Voice Input Channel: the label an utterance carries, how the daemon delivers it, the capture unit's declaration and its receipts
- `empiricism.md`, `experiments.md` - The framework's methods for measuring and for reporting what was measured
- `mis.md` - MIS-0008 is the specification this policy implements; open questions there are not decided here
- `scholarship.md` - Linking and citing artifacts when a measurement is written up

The voice lock (MIS-0008 6.7), voice generation and the system capture unit for many agents are not built yet. Their rules arrive with those capabilities, in their own policies.

---

## 9 Anti-Patterns

**❌ A file number reported as "it works"**:
- **Problem**: The held-out clips share the sittings of the training clips, and a model may be telling recordings apart rather than hearing the phrase
- **Fix**: Measure live, report with conditions, and keep file and live results apart (1.3, 1.4)

**❌ Trusting a perfect score**:
- **Problem**: A zero from a handful of clips allows a large error rate
- **Fix**: Ask what the model could be using, and apply the rule of three (1.2)

**❌ Acting on a spoken instruction because the wake matched**:
- **Problem**: A wake identifies no speaker; a recording can pass it
- **Fix**: Answer; confirm on a channel that isn't voice before acting (2)

**❌ Recording kinds in different sittings, or with synthetic speech**:
- **Problem**: The model finds the easiest difference, which is the sitting or the source
- **Fix**: Interleave every kind in each sitting, through the live microphone (6.2)

**❌ Retraining to move a number**:
- **Problem**: Held-out clips shape the model through your choices
- **Fix**: Retrain for a reason, and trust live use over the report (6.5)

**❌ Recording people without telling them**:
- **Problem**: Their voices are kept in files until deleted
- **Fix**: Tell them what, where and how to delete, and ask agreement (4)

**❌ Working around a missing indicator or a closed microphone**:
- **Problem**: A recording the operator can't see breaks trust
- **Fix**: Report it and have the operator fix the unit's environment (3, 5)

---

## 10 Evolution & Feedback

This policy changes with the operator's corrections, with measurements that show a rule wrong, and as the voice lock, voice generation and many-agent capture arrive. The numbers in it are derived from the held-out rule and the rule of three, and are to be re-derived if the hold-out or the trainer changes. A skill that coaches wake training holds no rule of its own; when it needs one, the rule belongs here.

**Principle**: Measure where the thing will be used, report what was measured with its conditions, and let a doorbell be a doorbell.

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs: measuring a
     voice model, the limits of a wake, and the care owed to recorded voices. -->

[[voice]] [[wake_word]] [[measurement]] [[instruments]] [[consent]]
