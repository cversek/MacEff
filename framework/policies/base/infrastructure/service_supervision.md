# Service Supervision — Who Watches Whom, and Where the Chain Ends

**Breadcrumb**: s_cd1f76a9/c_25/p_62a56ea5/t_1787434910
**Type**: Infrastructure
**Scope**: Any MacEff component that runs as a long-lived process, and the deployments that provision them
**Status**: ACTIVE
**Version**: 1.0

---

## Purpose

MacEff runs several long-lived processes — mail brokers and spool consumers, the
search service, the transcript monitor, the API proxy, agent harnesses. This
policy says who is allowed to report whose death, and where the reporting has to
end up.

It exists because a deployment assembled every piece of a supervision chain and
still went dark for over a day. It had a correct orphan sweep. It had an
age-bound alarm written into the spec as an invariant that HOLDS. It published a
heartbeat every fifteen seconds. It even carried a written instruction to
*"schedule this even when a watcher runs — it is what notices the watcher died."*

The sweep ran in exactly one place: **inside the watcher's own loop**. Nothing
read the heartbeat. And the provisioning function whose docstring named the
missing schedule as the entire defect did not create one — the declaration and
the omission were four lines apart.

**Core Insight**: a supervisor that shares a fate with its subject is not a
supervisor. It is a second symptom, and it makes the outage quieter than having
no supervisor at all — because the design above it is now built on cover that
does not exist.

---

## CEP Navigation Guide

**1 The Fate-Sharing Rule**
- My daemon already checks for stuck work on a timer. Is that supervision?
- Why is a co-located checker worse than none?
- What does "higher scope" mean when everything is in one container?

**2 Publishing and Reading Liveness**
- What must a long-running component publish?
- Who decides the staleness bound, and why not the observer?
- My component has never started. Is that the same as dead?
- The heartbeat is corrupt. Is the component healthy?

**3 Accepting Work Nobody Processes**
- Why is an accumulating failure worse than an outage?
- What must an acceptor do when its processor is gone?

**4 Where the Chain Terminates**
- I added a supervisor for the supervisor. Am I done?
- The service manager records failures. Isn't that the terminus?
- What must an external check distinguish, and why three states rather than two?
- The alarm goes over a channel I already have. What does that couple together?
- When is a shortcut here a decision rather than a gap?

**5 Provisioning**
- The start log says the service started. Does it?
- What must provisioning report, and how many outcomes?

**6 Proving Any of It**
- Can I verify a supervision chain by reading it?
- What is the control for "the alarm reaches someone"?

---

## 1. The Fate-Sharing Rule

**A component that reports another component's death MUST run in a separate
process from it.**

This is the whole policy in one line, and it is violated by the most natural
implementation available. Putting the health check inside the loop it checks is
convenient, needs no new process, no new unit, no new provisioning — and it
produces a checker that stops checking at the exact instant checking becomes
necessary.

**"Higher scope" is relative, not a fixed layer.** The test is not *which
container* or *which host*; it is: **does the observer survive the observed's
failure?** A thread in the same process fails that test. A second process in the
same container passes it for a crashed daemon and fails it for a stopped
container. Ask what failure you are trying to report, then put the observer
somewhere that failure does not reach.

A corollary that is easy to miss: **adding a supervisor moves the problem up one
level rather than solving it**, unless the new supervisor's own death is visible
somewhere further out. Otherwise you have built a taller stack of unwatched
processes, and the tallest one is still unwatched.

---

## 2. Publishing and Reading Liveness

**A long-running component MUST publish a heartbeat carrying at least a timestamp
and its own cadence.**

The cadence is the part that gets left out, and leaving it out is a
derive-versus-restate failure. If the observer hard-codes a staleness bound, two
places now configure one interval. They drift, and the drift is invisible in the
direction that matters: a bound that is too generous reports a dead component as
healthy, and nothing about that looks wrong from outside. **Publish the cadence
and let the observer compute from it**, so a component that changes its interval
changes its own bound.

**A heartbeat nobody ages out is not a liveness signal.** It is a write with no
reader — the mirror image of a reader with no writer, and just as silent. If you
add a heartbeat, add the thing that reads it in the same change, or you have
added a file.

### 2.1 The verdict has more than two states

At minimum, distinguish:

| verdict | means | why it is not the others |
|---|---|---|
| ALIVE | stamped within the bound | — |
| STALE | stamped, then stopped | it ran; something killed it |
| ABSENT | never stamped at all | the deployment may not run this component |
| UNREADABLE | present, unparseable | liveness is **unknown** |

Collapsing ABSENT into STALE reports every deployment that does not run the
component as an outage. Treating UNREADABLE as ALIVE is how a supervisor comes to
report green over a corpse — and it is the tempting default, because "I could not
read it" feels like "no news."

**Unknown is not healthy.** Any verdict that cannot be established must fail
toward the alarm.

---

## 3. Accepting Work Nobody Processes

**A component that accepts work MUST be coupled to the liveness of the component
that processes it.** When the processor is known dead, the acceptor refuses or
alarms; it does not go on accepting.

An acceptor decoupled from its processor turns a stopped subsystem into an
**accumulating** one, and that is strictly worse than an outage:

- an outage has a floor — nothing more is lost after it starts
- an accumulation has none — the queue grows for as long as nobody looks
- and the deployment **presents as healthy**, because every surface a caller
  touches is still answering

In the measured case the receiver kept accepting mail and writing it to a spool
that nothing drained, while the broker kept authorizing sends. Two live services,
one dead one, and from outside the system looked fine.

---

## 4. Where the Chain Terminates

**There MUST be a check that runs outside the deployment, on a schedule, whose
failure reaches a person.**

Supervision inside a deployment cannot report that the deployment is gone. A
stopped container, a wedged runtime, a vanished volume — in each of those, the
thing that would report it does not exist.

### 4.1 A record is not a terminus

The seductive stopping point is a durable record: a failed unit in the service
manager, a line in a log, a row in a table. **A record is only a terminus if
someone reads it**, and that is an empirical question about your deployment, not
a property of the mechanism.

Measure it before relying on it. On the host where this policy was written, two
service-manager units had been sitting in `failed` state for weeks. They were
benign, but they settle the question: on that host, unit failure state is where
an alarm goes to be quiet. A chain terminating there terminates nowhere.

**So the last hop is a push, to a channel the operator actually receives.**

### 4.2 The external check distinguishes three failures

| state | meaning | what the reader does |
|---|---|---|
| UNHEALTHY | it answered, and the answer is bad | fix the subsystem |
| UNREACHABLE | it is not running; **nothing was measured** | start the deployment |
| CHECK-FAILED | the instrument broke; state is **unknown** | fix the monitor |

Collapsing UNREACHABLE into UNHEALTHY reports a deliberately stopped deployment
as a subsystem fault. Collapsing either into healthy is how a monitor certifies a
deployment it never reached — the worst available outcome, because it is
indistinguishable from good news.

### 4.3 The notifier names no subject it did not measure

A notifier that restates the subject from its own configuration will eventually
name the wrong one. When this policy's reference implementation was first
exercised, the gate ran against one container and the alarm named another —
fluently, specifically, and wrongly, sending a reader to inspect something
healthy.

**Carry the checker's own words.** The component that made the measurement is the
only one that knows what it measured.

### 4.4 Credentials on the notification path

The notifier holds a credential for the channel it pushes to. Read it from disk
at send time, use it, and never echo, cache, or write it into the alert record.
Report transport failures by status code, never by echoing a URL that carries the
token.

**A notifier that cannot notify must not also fall silent.** If the push cannot
happen, the alarm is still recorded durably and still loud on the process's error
stream. Degrading to a quieter channel is acceptable; degrading to no channel is
the failure being guarded against.

### 4.5 The alert path should not share a fate with the agent's

§1 applies to the notification path too, and it is easy to miss because the
notifier is not a daemon and the channel does not look like a component.

The reference implementation pushes through the **agent's own bot credential**,
into the operator's ordinary conversation. That was the right thing to reach for
first — an existing, proven channel beats an unbuilt one, and a working alarm
today is worth more than a well-separated alarm next month. But it couples four
things that have no reason to be coupled:

- **Rate limit.** Agent and alarm are two producers on one bounded channel with
  no coordination. A long agent report and an alarm arriving together contend,
  and the notifier's degraded path on a throttle is a recorded-but-quiet
  failure — so a chatty session can silence the channel that reports the
  session's own deployment is dead.
- **Credential.** Rotating or revoking the agent's token — a thing you do when a
  secret is suspected — takes the infrastructure alarms down with it, silently.
- **Attribution.** The alarm presents as agent output when it is host
  infrastructure that runs whether or not any agent exists. The reader cannot
  tell *my agent is telling me something* from *a timer fired while nobody was
  home*.
- **Privilege.** A credential that can send **as the agent** now lives in a shell
  script whose only job is to post an alarm. That is a wider grant than the task
  needs (see `capability_boundaries.md`).

**The separated form**: a credential scoped to an alerts destination and nothing
else, held by the host, absent from every agent environment — readable by the
agent, writable only by the gate.

Record the coupling where the alarm is configured rather than treating a channel
as a channel, and name the **measurable trigger** for separating: the first
throttled push, or the first alarm missed during an active session. An
acknowledged shortcut with a stated trigger is a decision; the same shortcut
undocumented is a control that quietly does not hold.

---

---

## 5. Provisioning

**After starting a component, provisioning MUST confirm it is still running, and
report the two outcomes differently.**

A successful launch means the fork succeeded. It says nothing about whether the
process is still there a second later. The measured case logged `broker started`
while the broker had already refused on a missing directory and exited — a
statement that was **true about the act and silent about the outcome**.

A success line is worse than silence here. Silence invites a check; a success
line closes the question.

Report per component, and let one failure not stop the others starting — a
provisioning run that aborts on the first dead service leaves the rest
unprovisioned as well.

---

## 6. Proving Any of It

**You cannot verify a supervision chain by reading it.** Every property in this
policy is a claim about what happens when something fails, and reading only ever
shows you the system that has not failed. The reference implementation's
co-located sweep read correctly, tested green, and was documented accurately.

So the control for every rule here is a **demonstration**:

- **§1** — stop the subject; observe the supervisor, still running, alarm within
  one pass. Restart it; observe recovery. Both polarities.
- **§2** — corrupt the heartbeat, remove it, and backdate it; three different
  verdicts, none of them ALIVE.
- **§4** — induce each of the external check's states and confirm each maps to
  its own exit code. Then fail the gate for real and **confirm the alarm
  arrived**. Verifying that the unit failed is not the control; the failure was
  never in doubt. **The delivery is the part under test.**
- **§5** — recreate the deployment and read the **process table**, not the log
  that claims to describe it.

Use a self-labelling subject when drilling a live alarm (`SELFTEST-…`), so
whoever receives the page can see immediately that it is a drill.

---

## Relationship to other policies

- `capability_boundaries.md` — a boundary is enforced where the agent cannot
  reach; a supervisor is placed where the failure cannot reach. Same shape,
  different adversary: there the adversary is a capable agent, here it is a
  shared fate.
- `debugging_and_validation.md` — the demonstrate-don't-inspect discipline in §6
  is that policy's rule applied to liveness.
- `amail.md` — the mail subsystem is the first consumer and cites this policy
  rather than restating it.

---

## Wiki-Links

[[silent_failure]] [[verification]] [[deployment]] [[capability_boundary]]
