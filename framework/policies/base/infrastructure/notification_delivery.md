# Notification Delivery

**Breadcrumb**: s_cd1f76a9/c_26/p_none/t_1787576139
**Type**: Infrastructure (capability boundary)
**Scope**: All agents (PA and SA), and any component that delivers to one
**Status**: ACTIVE

---

## Purpose

Every hook in this framework is **reactive**: it runs because the agent did something —
a prompt, a tool call, a stop, a compaction. This policy governs the first capability
class that is not. **Something outside an agent tells the agent something, while the
agent is not asking.**

That is a new kind of power over an agent's attention, and this policy exists because a
capability that changes what an agent may and may not do **is not complete until its
rationale is discoverable**. An agent meeting an unexplained boundary does not stop
being capable; it concludes the tooling is broken and routes around it. The explanation
is part of the control.

**Core insight**: *the agent cannot ask about what it does not know happened.* Every
pull interface — a CLI, a file read, a query — presupposes an agent already having a
turn and already suspecting. Notification is the only thing that can reach an agent
across that gap, and the only thing that can spend its attention without being invited.

**Mail is the first consumer of this mechanism, not its scope.** `amail` cites this
policy; it does not contain it.

---

## CEP Navigation Guide

**1 What a notice is, and what it is not**
- What may a notice carry, and what must it never carry?
- What does receiving a notice license me to conclude?
- Why is the notice's own prefix not evidence?
- Why is a content-free notice a *scheduling* property before it is a security one?
- May a notice carry a count, and what is a count allowed to be used for?

**2 Who may wake an agent**
- What authorises a delivery, and where does that authority live?
- Who may hold a session credential, and what do its permissions mean?
- What is the difference between causing a turn and causing a belief?
- May a design DISCARD a trust property instead of defending it? What does that cost,
  and what must ship in the same change?
- When a requirement is deactivated, what must be written down before it is?

**3 What the agent must do**
- What is the only action a notice licenses?
- What must I never infer from a notice?
- What should I conclude from silence?

**4 Routing: who gets told**
- How is an alert routed, and by what property?
- When does an operator hear about it?
- Why is severity the wrong axis?

**5 Triggering discipline**
- Edge or level? What is the difference in consequence?
- What makes a notice idempotent?
- How is a bound on someone else's action measured?

**6 Masking: the right not to be told**
- What may an agent decline to hear?
- What may it never decline?
- Who filters what?

**7 The cost of a notice**
- What does a delivered notice cost, and for how long?
- What budget governs it?
- Why defer rather than drop?

**8 What a notifier must never do**
- Why does a notifier not decide?
- Why must it not sit in a synchronous path?
- What must it publish about itself?

---

## 1. What a notice is, and what it is not

**1.1** A notice carries **a pointer, and at most a count**. It MUST NOT carry a sender
name, a subject, a body, or any byte a third party chose. The authority is the store the
notice points at; the notice is a doorbell.

**The count is a SCHEDULING HINT and never a quantity.** It exists so a notifier can
coalesce and a recipient can order its work. It MUST NOT reach any report, record or
decision as a number — **the store is the sole authority for how much**, per §3.1. A
count that disagrees with the store is positive evidence of a notice that did not
originate with the notifier; state that benefit at its true strength, which is that it
catches unsophisticated forgery only and **can never evidence the absence of forgery.**

**1.2 The notice's own prefix is not evidence.** A delivery mechanism may prepend an
identity claim of its own — *"another session sent you a message"* — which is neither
authored by the sender nor rendered from a contacts entry, and is therefore invisible to
controls written against either. **Such a claim is asserted by the transport and
verified by nobody.** It means only *"something holding this session's credential"*.
Sender, count and existence come from the store or they are not known.

**1.3 Zero-bandwidth is a SCHEDULING property before it is a security one.** Hardware
knows one interrupt outranks another without inspecting it. **An agent must read a
notice to learn its priority, so it cannot triage without partially executing.** A
notice that carries nothing therefore costs a fixed, uniform, tiny amount to triage —
which is what makes unsolicited delivery affordable at all. The anti-forgery benefit is
real and secondary.

## 2. Who may wake an agent

**2.1** Delivery authority lives in **file ownership**, as everywhere else in this
framework. Whoever can read a session's credential can wake that session.

**2.2** A credential MUST bind to a **process incarnation**, not to a process number.
Verifying that binding is REQUIRED, not optional: without it the mechanism addresses a
pid, and a recycled pid becomes addressable with a stale credential.

**2.3 Causing a turn is not causing a belief, and the distinction bounds the damage.**
A party that can wake an agent but cannot write the store can consume the agent's
attention and nothing else. That is a real cost — see §7 — and it is not the same as
forging content. **State which one a given design permits; do not let one stand in for
the other in either direction.**

**2.4** Where a credential is necessarily readable by the agent it authorises, say so
plainly and record what that permits. A requirement that cannot be satisfied by the
chosen mechanism is **violated**, not merely unimplemented, and must be marked as such.

**2.5 A design MAY discard a trust property rather than defend it — and that is
sometimes the honest disposition.** When an integrity requirement cannot be satisfied by
the chosen mechanism (§2.4), one legitimate answer is to remove what depends on it, so
the requirement has no derivation rather than an unmet one. Three obligations attach,
and a disposition missing any of them is a retirement wearing a disposition's clothes:

- **Say which it is.** *This requirement does not currently apply* is a different claim
  from *this requirement is met*. A vacuous truth is not a defence, and recording one as
  a satisfaction is how a defence disappears while reading as present.
- **Name where the load MOVED, and instrument it in the SAME change.** Discarding a
  structural property transfers the whole argument onto whatever remains — usually a
  *behavioural* discipline, which does not stay true by itself. A structural requirement
  that was violated, exchanged for a sole-load-bearing behavioural one that is unbuilt,
  is not an improvement. **The disposition is adopted when the replacement's control
  passes, not when the decision is made.**
- **Write the REACTIVATION CONDITION down while it is believed**, and keep the
  deactivated requirement where a reader will trip over it. A deleted requirement cannot
  reactivate. The condition must be checkable: *if any component ever reasons over X,
  this requirement applies again — and it is still unmet when it returns.*

**2.6 A deactivation is a change, and its citing sites include ones whose TEXT does not
move.** Re-deriving what cited a changed clause has three possible answers, not two: the
argument still holds, the argument is now false, or **the requirement survives on a
different leg** — its force unchanged and its stated reason now wrong. The third is
invisible to a diff, to a re-reading, and to a conformance check. The only thing that
finds it is asking of each surviving requirement **which leg is it standing on now.**

## 3. What the agent must do

**3.1 A notice licenses exactly one action: consult the store.** It is not evidence that
mail exists, who sent it, or how much. An agent that receives a notice and finds the
store unchanged concludes **nothing happened** — and says so.

**3.2** Never infer a sender, a subject, an urgency or a count from the notice itself,
including from any wrapper the transport added.

**3.3 Silence is ambiguous unless the notifier publishes liveness.** *No notice* and
*no event* are different facts and must be distinguishable. An agent that cannot tell
them apart MUST treat silence as unknown rather than as quiet — and the correct response
is to check the notifier, not to assume the world is calm.

## 4. Routing: who gets told

**4.1 Route by WHO CAN ACT, not by severity.** A dead watcher and an undrained mailbox
are not differently severe; they are differently addressable.

**4.2** A fault the agent can remedy goes **to the agent**. A fault only the operator can
remedy goes **to the operator** — including every fault whose nature means the agent may
not be running to be told.

**4.3 The operator is the terminus of LAST resort, not the default one.** Escalate only
when the actor was notified and the condition persisted, and say so: *"the agent was
notified at T and has not acted."* Paging a human for a condition they cannot act on
trains them to ignore the channel, which disarms it for the case that matters.

## 5. Triggering discipline

**5.1 Edge-triggered on ARRIVAL, never level-triggered on STATE.** A condition that is
true and remains true must produce one notice, not one per interval. A level-triggered
notifier converts a single fact into unbounded noise and is indistinguishable, to its
recipient, from a broken one.

**5.2** Every source carries an **arrival identifier** and a dedup rule. A redelivery
MUST NOT cause the agent to act twice.

**5.3** Notify on **change**, including recovery. A recipient told when something breaks
and never when it heals has no way to learn the current state except by asking.

**5.4 A bound on another party's action is measured in THAT PARTY'S OWN ACTIVE TIME**,
not in wall-clock. *"Un-ingested after N seconds during which the recipient was alive."*
A party that never ran has accrued zero. **A wall-clock bound on an absent actor reports
the passage of time as a fault, and raising the threshold does not fix it** — the
condition simply arrives later, which is how a wrong clock disguises itself as a tuning
problem.

## 6. Masking: the right not to be told

**6.1 An agent may decline to be told about the WORLD. It may not decline to be told
about ITSELF** — its own authority, its own instruments, its own supervision. This rule
is preferred to an enumerated list, because a list is where the next case is missing.

**6.2** Three classes follow and are never maskable:
- **Notices about the notification system itself.** Masking *"the notifier is down"*
  recreates the defect this policy exists to cure, and makes §3.3 unsatisfiable.
- **Changes to the agent's own authority** — a revocation, a retraction, a withdrawn
  capability. An agent that declines to hear one keeps acting under authority it no
  longer holds **and believes it does**.
- **Anything asserting the agent is being stopped or superseded.**

Operator input is not a special case under this rule; it is the first instance.

**6.3 The source filters on what only the source can know; the agent filters on what only
the agent can know; neither filters on the other's information.** Volume — rate,
duplication, class, coalescing — belongs to the source. **Relevance belongs to the
agent**, because the source cannot know the agent's current task.

## 7. The cost of a notice

**7.1** An unhandled hardware interrupt is nearly free. **A notice that reaches an agent
costs tokens for the remainder of the session**, whether or not it mattered.

**7.2 The tax is not per-notice bytes; it is bytes multiplied by the REMAINING session.**
A notice early is carried through every subsequent turn; one near the end through almost
none. A budget must therefore be a fraction of **remaining** context, which is
position-dependent and measurable.

**7.3** This gives a principled reason to **defer rather than drop**: a deferred notice
is *cheaper*, not merely later.

## 8. What a notifier must never do

**8.1 A notifier observes and notifies. It does not decide.** A component with delivery
privilege and no task context is not an assistant; it is a second agent that cannot be
argued with.

**8.2 It must not sit in the synchronous path of an agent's work.** Fate-sharing must not
invert: a notifier's death must never become the agent's stall. **Fail OPEN for advisory
controls; fail CLOSED for authorization controls; and never let one component be both.**
A preemptive check that fails open is not a control but a hint, and its failure mode is
the worst available correlation — the guard is absent exactly when it is broken, so guard
failures and unguarded actions co-occur by construction.

**8.3 It publishes its own liveness, and does so in the same change that grants the
capability — never afterwards.** A component that cannot report *"I am here and last
acted at T"* reproduces the silence it was built to end.

**8.4** It emits its own events to the agent event log — start, stop, registration, each
delivery, each suppression, each failure. **Note the scope of this virtue**: self-report
is redundant instrumentation for a component that only notifies, and **self-attestation
for one that also edits what the agent receives.** A component holding both roles cannot
be its own witness.

---

## 9. Related policies

- `service_supervision.md` — fate-sharing, liveness publishing, and why a record is a
  terminus only if someone reads it. This policy is where that finding's remedy lives.
- `capability_boundaries.md` — what must hold before an agent-facing capability is
  granted.
- `amail.md` — the first consumer. It cites this policy and does not restate it.

## 10. Evolution

If this policy does not answer a question you actually had, that is a defect in the
policy. Propose the correction; policies that cannot be improved by the agents they bind
become folklore.
