# Instruction Language (IL) Policy

**Type**: Operations Infrastructure
**Scope**: All agents (PA and SA)
**Status**: ACTIVE
**Version**: 0.3.0
**Methodology**: Policy as Spec — this policy IS the specification. Implementation must match.

---

## Purpose

**IL (Instruction Language)** is a one-directional **operator→agent** instruction
language for dense, low-interruption course correction. Its value is highest
exactly when the operator is watching autonomous work — or firing corrections
between turns — and a full-prose interruption would be expensive while a single
token would not. Value scales with agent autonomy.

An agent is **not** required to speak IL back to the operator, except when
explaining its own understanding of IL's syntax and semantics. IL is a control
channel, not a dialect of conversation.

This policy is grounded in an empirical finding that shapes everything below:
compared across **two independent operator–agent pairs** sharing this framework,
the instruction *vocabularies* were nearly disjoint, while the underlying
*structure* was shared. That single result is why IL is defined in two layers
(§2) and why the vocabulary is never hand-curated as universal.

---

## CEP Navigation Guide

**1 The Shape**
- What is the canonical form of an IL directive?
- What do the two terminators mean, and what parser work do they do?
- What are `.subtype`, `(target)`, and the `# rider`?
- How is IL recognised for a token the agent has never seen?

**2 The Two Layers: Grammar and Vocabulary**
- What is universal (grammar) versus per-pair (vocabulary)?
- Why is namespacing required, not merely convenient?
- Is there a universal core vocabulary?
- How is the vocabulary registry maintained without drifting?
- How does vocabulary evolve (clarify-then-codify)?

**3 One Obligation Per Form**
- Why does a directive bundling two obligations lose one?
- What does "a grammar that cannot express half-compliance cannot suffer it" mean?
- What is the one-obligation design rule?

**4 The Service Model**
- How does an interrupting directive bind to the work stack?
- What is the service-discipline axis, and how does observability set it?
- What overrides does a correction need (abandon vs defer)?
- How does an autonomous sprint change the interrupt?

**5 Scope and Forthcoming Work**
- What is fully canonical, and what is still per-pair or unbuilt?

=== CEP_NAV_BOUNDARY ===

## 1. The Shape

The canonical form of an IL directive:

```
TOKEN[.subtype][(target)][ : | ! ] payload   [# rider]
```

- **TOKEN** — an UPPERCASE directive class (`RULE`, `RESUME`, `IDEA`, `GO`, …).
  Uppercase is part of the recognition trigger; lowercase directive-shaped forms
  are treated as ordinary prose (empirically they are typos).
- **`.subtype`** — SPECIALIZATION: `X.y` = *y is a kind of X* (`TASK.bug`,
  `TASK.detour`).
- **`(target)`** — PARAMETERIZATION: `X(t)` = *X acts on / is written into t*
  (`RULE(TM)` — the target is what the rule is written into, not a kind of rule).
  A different relation from `.subtype`, and a distinct structural slot because dot
  notation cannot express it. **Provenance:** this slot is retained on the
  evidence of a single pair; unlike the rest of the shape it is not yet
  corroborated by a second corpus, and a reader should weight it accordingly.

### 1.1 The terminators carry the parse

Both terminators may be followed by text. The distinction is not *presence* of a
payload but its **grammatical role**:

- **`:`** — the payload is the directive's **argument**, the thing it operates on.
  Dropping it destroys the instruction. → An unknown `TOKEN:` **traps and
  queries**; it is never silently read as prose.
- **`!`** — the payload is a **rider or colored-prose instruction**: the token
  *tones or qualifies* what follows rather than consuming it (`UGH! get rid of the
  old injection…` is an affect marker on an ordinary request, not a directive
  taking "get rid of…" as an argument). → An unknown `TOKEN!` **acknowledges and
  continues**; register the tone, keep reading, do not interrogate it.

The terminator, not the token, carries the parse: a single token may appear with
**both** terminators. A vocabulary registry (§2.5) therefore records a
terminator as a property of the **occurrence**, never as a fixed attribute of the
token.

### 1.2 The `# rider`

A modifier attaches to a directive with `#`:

```
GO!  # pause around the wind-down boundary
```

The rider can itself contain a full IL form, which is the mechanism by which one
directive composes with another — composition is a rider phenomenon, not a
separate stacking syntax.

### 1.3 Self-identifying, with a false-positive guard

The grammar parses **independently of the vocabulary**: an uppercase TOKEN,
optional slots, and a terminator are recognised as IL even when the TOKEN is
unknown — so a novel coinage costs one clarifying question (§2.6), not a silently
dropped instruction. Recognition requires the token at a **directive position**
(start of a message or line, or after a clause boundary), not anywhere in prose,
so an exclamation embedded in a fixed phrase is not mistaken for a directive. The
terminator **and** the position together identify IL; the terminator alone
over-fires.

## 2. The Two Layers: Grammar and Vocabulary

IL is defined as two layers with different authorities and different evidential
bars.

### 2.1 Grammar (universal)

The **grammar** is the structure of a directive (§1) — its shape and parse rules.
It is **universal**: hand-curated, honoured by every agent, and changed only
against a **high bar** — evidence from more than one independent operator–agent
pair. The grammar is what lets an agent recognise a directive it has never seen as
a directive rather than read it as prose; that property depends on the structure
being pair-independent.

### 2.2 Vocabulary (per-pair)

The **vocabulary** is which specific directive tokens a given operator–agent pair
actually uses, and what each means. It is **per-pair, namespaced, and allowed to
move at the speed of the work.** It carries no universality bar at all — a pair
may coin, retire, and redefine forms freely, because doing so cannot fragment a
core that does not depend on it.

### 2.3 Namespacing is required, not convenient

Two findings make per-pair namespacing a requirement rather than a nicety:

- **Near-zero overlap.** Across two independent pairs sharing this framework, a
  tool, and even an operator, the frequently-used directive vocabularies were
  effectively disjoint — one pair's single most frequent directive did not appear
  in the other's corpus at all. A vocabulary curated from one pair's habits would
  freeze those habits onto everyone.
- **A live collision.** The same short token meant *token-management* to one pair
  and *task-management* to another, both current. Without a namespace, an agent
  servicing the wrong contract for a colliding token is inevitable.

Therefore: a token's meaning is always resolved **within a pair's namespace**,
never globally.

### 2.4 The core universal vocabulary is empty

On the evidence above, the correct size of the shared, every-agent-honours-it
vocabulary is **zero**, and it ships empty. Two independent pairs sharing
everything external still produced disjoint vocabularies; shipping a "small core"
would mean imposing one pair's idioms as everyone's defaults on the strength of a
single example. If a genuinely universal directive ever emerges, it will do so by
appearing — independently — in *more than one* pair's corpus, which is the same
high bar the grammar carries. Until then, the core is empty by principle.

### 2.5 The registry is generated, not shared-writable

The per-pair vocabulary is recorded in a **registry**, and the registry is
**generated, never hand-maintained** — the durable form of the same
single-source-of-truth discipline the framework applies elsewhere. Two properties
follow:

- **No shared write access.** Each agent *generates* its own vocabulary record,
  read-only, from its own instruction history; the operator *queries the union*
  rather than recalling which form was coined with which agent. No agent writes
  into another's namespace because no agent writes a shared object at all — it is
  a set of per-agent files and a reader, not a coordinated mutable store.
- **Two columns from two sources.** *Usage* — which forms are live, how often,
  last seen — is **derived** from the instruction history and cannot lie about
  frequency. *Meaning* — what a form does — is **curated** via the loop in §2.6.
  Deriving usage and curating meaning is what keeps the registry from drifting the
  way a hand-written glossary does.

### 2.6 Vocabulary evolves by clarify-then-codify

Because the grammar is self-identifying (§1.3), an agent can meet a directive
whose *form* it parses but whose *meaning* it does not know. The prescribed
response is a **clarify-then-codify** loop:

1. State the inference and ask a cheap, confirmable question — *"I take this to
   mean X; record it?"* — then continue.
2. **Default to the inference.** The question must be answerable with a grunt. If
   the agent must stop and be taught at length, the interruption stops being cheap
   and the operator stops using the language — which is how a correction language
   dies.
3. **Codify durably, or it re-asks.** An inference confirmed only in conversation
   is re-litigated next cycle; the write into the registry is the point.

This is the engine that lets IL **evolve with the workflows** rather than harden
into a historically accurate script — and it is why the vocabulary layer carries
no universality bar: it is *meant* to move.

## 3. One Obligation Per Form

The strongest principle in this policy, and the one that generalizes past IL to
any instruction system.

### 3.1 The failure

A directive that bundles a **durable write** (record this) and a **behaviour
change** (now do this) will reliably have **one half dropped under load** — and
the half dropped is the one that does not *feel* like compliance. This was
observed as **mirror-image failures** across two independent pairs: one agent
performed the durable half and skipped the behavioural stop; another performed the
behavioural half and skipped the durable write. In both, the agent experienced
full compliance from the inside, and nothing in its output revealed the gap.

The asymmetry is why "be more careful" does not fix it: the behavioural half
produces immediate visible motion and *feels* like the obligation discharged, so
nothing prompts a check of the durable half, which produces an artifact nobody is
waiting for.

### 3.2 The rule

> **A grammar that cannot express half-compliance cannot suffer it.**

Therefore, **each IL form carries exactly one obligation**, not two.

The cleanest realization makes the durable write primary and lets behaviour
follow from it. A rule written into policy **governs subsequent work by existing**
— there is no separate behavioural obligation to drop, because being governed is
not a second action. One obligation, and it is checkable: the artifact either
exists or it does not.

### 3.3 In practice

- **When designing a form:** if it implies both a durable write and a behaviour,
  either split it into two forms, or make the behaviour follow structurally from
  the write (the preferred shape).
- **When receiving a form you cannot split:** name both halves explicitly before
  acting, and **verify the durable one produced an artifact.** The behavioural
  half needs no verification — you will notice if you did not do it.
- **The tell of a silent half-failure:** you have complied, it felt complete, and
  nothing changed on disk.

## 4. The Service Model

An IL directive is an **interrupt**: it arrives mid-work, must be serviced, and the
work it interrupted must be resumed. IL does not invent a mechanism for this. It
**binds to the work stack** already defined in `task_management` §16, and adds only
the parts specific to directives.

### 4.1 Binding to the work stack

An inbound IL directive mid-work becomes a **push** — a task, or a note on one —
exactly as `task_management` §16 defines: servicing the directive is the work,
and resuming prior work is a **reconciled pop** (the resume protocol, which reports
a frame's age and requires reconciliation before continuing). All of the
mechanics — that a frame must be durable *before* the interrupt (§16.3), the
active / parked / abandoned distinction and the structural completed-parent check
(§16.4), and how to see the stack via `macf_tools task trace` (§16.5) — live in
that policy and are not restated here. **IL directives are simply a source of stack
frames**, and the operator's entitlement to interrupt-and-forget while the agent
holds the interrupted work is the obligation stated in §16.6.

This binding is the recommended pattern; a deployment that adopts it inherits §16's
guarantees. The additions below are the IL-specific layer on top of it.

### 4.2 Service discipline follows observability (universal)

Each directive is serviced under one of two disciplines:

- **preempt-now** — unwind and service immediately;
- **service-at-next-boundary** — queue to the next clean stopping point.

Which one applies is **not a fixed property of the form**. It follows from a
property of the channel:

> **The party who can observe what they are interrupting may interrupt harder.**
> An operator watching the session may issue **preempt-now** directives. Inbound
> correspondence from a party who cannot see the agent's current state — a
> different host, hours offset (e.g. asynchronous inter-agent mail) — defaults to
> **service-at-next-boundary**.

This is the one genuinely universal element of the service model, because it
derives from observability rather than from any pair's taste.

### 4.3 Autonomous operation inverts the interrupt

IL was shaped for the attended case: the operator watches, the agent executes, the
operator corrects. In an autonomous sprint the assumption inverts — the agent has
its own scope and plan, so an inbound directive **interrupts the agent's plan, not
the operator's.** Binding IL to the work stack (§4.1) is what keeps this coherent:
the directive becomes a frame the sprint can see and the scope gate accounts for,
so "resume the sprint" and "pop the frame" are the same operation rather than two
competing stacks.

A consequence worth stating, because it changes autonomy and not just syntax: in
an unattended sprint the operator's observability drops to nearly nothing (§4.2),
so an interrupt is **more** costly, not less — the agent may be mid-phase on work
no one has seen. The same directive that is service-at-boundary while the operator
watches may warrant preempt-now unattended, precisely because no one else will
catch an error for hours.

### 4.4 Override: abandon versus defer

The default pop resumes the frame below. But some corrections **invalidate** it —
*"stop, that whole approach is wrong"* means the frame beneath should be
**discarded**, not resumed. A directive therefore needs one marker with two
outcomes: **resume-below** (the default) or **discard-below**. Without it, a
faithful agent dutifully returns to work the operator has already killed, which is
worse than dropping it.

Frame staleness and depth-reporting are **not** IL-specific overrides — they are
the reconciled-pop and trace mechanics of §16 (a resumed frame is validated for
age before restoration; the stack is surfaced via `task trace`). IL relies on them
rather than restating them.

## 5. Scope and Forthcoming Work

**Canonical now:** the shape (§1), the two-layer architecture and namespacing
(§2), one-obligation-per-form (§3), and the observability rule (§4.2). These are
supported by comparison across independent pairs or by matched failures in more
than one.

**Per-pair pattern, not universal law:** the service-model binding (§4.1, §4.3,
§4.4). It is expressible in the grammar and recommended, but rests on one pair's
practice for its finer contracts; it is expected to evolve at the vocabulary
layer's speed (§2.6) rather than be frozen here.

**Forthcoming tooling (not policy):** the vocabulary-registry generator described
in §2.5 — the per-agent read-only usage record and the union reader — is build
work, not yet shipped. The stack/detector tooling the service model binds to
already exists (`task_management` §16 / `macf_tools task trace`).

---

## Wiki-Links

<!-- NORMATIVE node. Links are what this policy governs: the IL shape, the
     two-layer grammar/vocabulary architecture, per-pair namespacing, the
     one-obligation rule, and the binding of directives to the work stack. -->

[[instruction_language]] [[single_source_of_truth]] [[silent_failure]] [[verification]] [[task_lifecycle]] [[autonomous_operation]]

---

*Grammar and the two-layer architecture canonical; the service-model binding is a per-pair pattern over the work stack (task_management §16); the vocabulary-registry generator is forthcoming.*
