# Instruction Language (IL) Policy

**Type**: Operations Infrastructure
**Scope**: All agents (PA and SA)
**Status**: ACTIVE (partial — foundational principles; see §1)
**Version**: 0.2.0
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

**1 Scope of This Version**
- What does this version define, and what is deferred?
- Why land the foundational principles before the full grammar?

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

=== CEP_NAV_BOUNDARY ===

## 1. Scope of This Version

IL is being canonicalized in stages, in order of evidential standing. This
version (0.2.0) lands the two principles that are supported by comparison across
independent pairs and by matched failures in more than one:

- **§2 — the two-layer architecture** (grammar vs vocabulary), and
- **§3 — one obligation per form.**

**Deferred to a later version, and intentionally not specified here:**

- **The concrete grammar** — the exact *shape* of a directive (its tokens,
  modifiers, and terminators) and its parse rules. A working draft exists and is
  in cross-pair review; it is not yet canonical.
- **The service model** — how an interrupting directive is absorbed and how prior
  work is resumed. This depends on runtime behaviour still being characterized and
  on a second pair's corpus, and is deferred rather than frozen on one pair's
  practice.

Landing the principles first is deliberate: §2 and §3 are the load-bearing design
decisions — they determine what *can* be expressed and how directives are
structured — and they are stable regardless of how the concrete shape settles. A
deployment can adopt them now without waiting for the grammar spec.

## 2. The Two Layers: Grammar and Vocabulary

IL is defined as two layers with different authorities and different evidential
bars.

### 2.1 Grammar (universal)

The **grammar** is the structure of a directive — its shape and parse rules. It is
**universal**: hand-curated, honoured by every agent, and changed only against a
**high bar** — evidence from more than one independent operator–agent pair. The
grammar is what lets an agent recognise a directive it has never seen as a
directive rather than read it as prose; that property depends on the structure
being pair-independent. (The concrete grammar spec is deferred to a later version
per §1; this policy fixes only its *status* as the universal, high-bar layer.)

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

Because the grammar is self-identifying (a directive is recognisable by its
structure even when its token is unknown — full spec deferred per §1), an agent
can meet a directive whose *form* it parses but whose *meaning* it does not know.
The prescribed response is a **clarify-then-codify** loop:

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

---

## Wiki-Links

<!-- NORMATIVE node. Links are what this policy governs: the two-layer IL
     architecture, per-pair namespacing, and the one-obligation design rule. -->

[[instruction_language]] [[single_source_of_truth]] [[silent_failure]] [[verification]]

---

*Foundational principles landed; concrete grammar and service model forthcoming (§1).*
