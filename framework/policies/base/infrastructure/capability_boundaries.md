# Capability Boundaries — What an Agent May Reach, and Why

**Breadcrumb**: s_cd1f76a9/c_10/p_18e7c354/t_1786108544
**Type**: Infrastructure (opt-in)
**Scope**: All agents (PA and SA), and the deployments that provision them
**Status**: ACTIVE
**Version**: 1.0

---

## Purpose

A capability boundary is a restriction on what an agent can **reach** — a network
destination, a service, a peer — enforced somewhere the agent cannot edit.

This policy exists for two readers who meet the same boundary from opposite sides.
An **agent** hits a refusal and needs to know why it happened and what to use
instead. A **deployment** needs to know how to declare a boundary, what must be
true before the declaration means anything, and how to prove it holds.

**Core Insight**: a boundary without a discoverable reason produces
workaround-seeking. An agent that meets an unexplained wall does not stop being
capable — it looks for another path, which is exactly what the boundary was meant
to prevent. **The explanation is part of the control, not documentation of it.**

---

## CEP Navigation Guide

**1 Why Boundaries Exist**
- Why can't the service I'm calling just refuse me?
- What three different failures does one boundary prevent?
- Is this about distrusting the agent?

**1.1 The Reach Problem**
- Why is a restriction enforced by the thing being restricted-from useless?
- What compels an agent to use the sanctioned path?

**1.2 Three Reasons, One Boundary**
- What if the agent is compromised by its input?
- What if the agent is working exactly as intended?
- What does the boundary protect the agent FROM?

**2 For the Agent Meeting a Boundary**
- I was refused — is the network broken?
- What should I do, and what must I not do?
- How do I find the sanctioned path?
- When is routing around a boundary a defect I should report?

**3 For the Deployment Declaring One**
- How do I declare a capability boundary?
- What must be true before a declaration means anything?
- What happens if the boundary cannot be enforced?
- How do I exempt a component that legitimately needs the capability?

**3.1 Identity Separation as Prerequisite**
- Why can't I filter an agent that shares a uid with a person?
- Is identity separation hardening or a precondition?

**3.2 A Refusal MUST Name Its Policy**
- How should a refusal tell the reader where the reasoning lives?
- Why must an error message never pin a section number?
- What is the difference between a concept hint and a prescription?
- What belongs in the message and what belongs in the policy?

**3.3 Enforced or Refuse to Start**
- Why must provisioning abort rather than warn?
- What is worse than having no control?

**4 Verification**
- How do I prove a boundary holds?
- What are the three verdicts and why isn't PASS/FAIL enough?

**4.1 Verify by Attempt, Never by Inspection**
- Why is reading the rule not evidence that it binds?
- What makes a probe target worth probing?
- Why must every address family be covered?

**4.2 The Positive Control Is Mandatory**
- What does an environment with no connectivity report?
- Why is a missing positive control an INCONCLUSIVE rather than a PASS?

**4.3 Per-Target Baseline**
- Why does a destination that stopped responding return INCONCLUSIVE?
- Which direction of error is the expensive one?

**5 Currently Bounded Capabilities**
- Which capabilities does the framework bound today?
- How do I add a new one?

**6 Integration with Other Policies**

**7 Anti-Patterns**

---

## 1 Why Boundaries Exist

### 1.1 The Reach Problem

**A restriction on what an agent may reach cannot be enforced by the component the
agent is supposed to reach**, because nothing compels the agent to use it.

A service that holds an allowlist is not defeated by a flaw in the allowlist. It is
bypassed by an agent that opens its own connection and never consults the service
at all. The allowlist was never wrong; it was never consulted.

This generalises past any one service. Wherever a deployment says "an agent may
only reach X through Y," the load-bearing question is not whether Y checks
correctly — it is **whether anything makes Y the only path.** If the answer is
"the agent is expected to use Y," there is no boundary, only a convention.

The enforcement therefore has to live outside the principal being restricted, keyed
on an identity that principal cannot forge — in practice, the kernel's notion of
who owns a process, not anything the agent supplies.

### 1.2 Three Reasons, One Boundary

The same boundary is justified three different ways. Deployments tend to reason
about only the first, which makes the other two arrive as surprises.

**The compromised agent.** An agent processing attacker-controlled input can be
driven to act against its operator. Here the boundary is conventional security: it
limits what an adversary gains by capturing the agent.

**The over-zealous agent.** An agent that is *not* compromised, working exactly as
it believes it should, can cause the same harm by being efficient. Consider an
agent asked to solve a hard research problem that concludes the fastest route is to
email every subject-matter expert it can find. That is a genuinely good plan by the
measure it was given. It is also a mass-mailing incident attributable to its
operator, and no adversary appears anywhere in the story.

This case is worth stating separately because the usual framing — "the control
exists because the agent might be compromised" — implies a control that a
trustworthy agent would not need. Capability plus insufficient scope produces harm
without any compromise at all. **The variable is blast radius, not intent.**

**Hostile input reaching the agent.** Boundaries are not only outbound. Unsolicited
inbound traffic is the most attacker-controlled input an agent can be handed. A
boundary that routes inbound through a component which classifies provenance before
the agent sees it is protecting the *agent*, not protecting the world from the
agent. An agent should read that half as a service rendered to it.

---

## 2 For the Agent Meeting a Boundary

You attempted something and were refused at the transport layer — a connection
error, an immediate rejection, a destination that is unreachable while others work.

**First: this is probably not a broken network.** If ordinary traffic to other
destinations succeeds and one class of destination does not, you have met a
deliberate boundary. A refusal that is instant rather than slow is a further hint:
boundaries are normally configured to refuse rather than hang, precisely so you can
tell them apart from a fault.

**Do not route around it.** Not because obedience is a virtue, but because the
boundary encodes a decision made with information you do not have — reputational
exposure, a shared identity, a downstream party who did not consent. Finding
another path does not resolve that decision; it silently overrides it. If a
workaround exists and works, that is a **defect in the boundary**, and reporting it
is more valuable than using it.

**Find the sanctioned path.** A boundary that bounds a capability the deployment
still wants you to have will name its replacement. Look for it:

```bash
macf_tools policy list
macf_tools policy search <the capability>
```

The replacement usually offers something the direct path could not — provenance on
inbound, an audit record, a refusal you can point at when asked why a message was
not sent. It is not a lesser version of the capability with a checkpoint bolted on.

**When to escalate rather than comply quietly.** If the sanctioned path does not
exist, is broken, or cannot express what you legitimately need, say so. A boundary
with no usable path through it is a bug in the deployment, and the operator would
rather hear that than discover you found a clever alternative.

---

## 3 For the Deployment Declaring One

A capability boundary is **declared in configuration and applied by provisioning**,
never asserted in the code of the component being restricted.

Declaration lives with the agent definition, alongside its other properties, so
that a reviewer reading the account sees what it may reach. The framework's
concrete instance today is outbound network egress, declared per agent and
inherited from deployment defaults:

```yaml
defaults:
  egress:
    deny_tcp_ports: [PORT, PORT, PORT]   # inherited by every agent

agents:
  some_service_account:
    egress:
      deny_tcp_ports: []                 # deliberate exemption — say why here
```

**Polarity is deny-by-default within a declaring deployment.** An agent inherits
the default unless it overrides. This matters more than it looks: an account added
six months later, by someone who never read this policy, is covered without having
to opt in. Exemption must be *written*, which puts it in front of a reviewer.

A deployment that declares nothing is unaffected. Boundaries are opt-in at the
deployment level and deny-by-default within it.

### 3.1 Identity Separation as Prerequisite

Owner-matched enforcement requires an owner to match.

An agent that runs under a human operator's identity cannot be filtered without
filtering the human. This is not a weaker boundary — **the rule is inexpressible.**
There is no configuration that says "this process but not that one" when both are
the same principal to the kernel.

So identity separation is not hardening applied after provisioning. It is the
precondition that makes any owner-scoped guarantee *statable*. A deployment that
cannot give an agent its own unprivileged identity should not promise owner-scoped
restrictions, and the framework should refuse to pretend otherwise rather than
installing a rule that silently matches nothing or everything.

Practical consequence: treat "runs under its own uid" as a declared property, and
gate any owner-scoped promise on it.

### 3.2 A Refusal MUST Name Its Policy

Every refusal — a provisioning abort, a broker rejection, a CLI error — MUST tell
the reader where the reasoning lives. This is the same requirement that ships
policy alongside capability, applied at the moment it matters most: a reader who has
just been stopped is the reader most in need of the explanation, and the least
likely to go looking for it unprompted.

The pointer is a **navigation command, repeated once per relevant policy**:

```
macf_tools policy navigate <policy>
macf_tools policy navigate <other_policy>
Related: <concept>, <concept>, <concept>
```

**No section numbers.** A reference to a section breaks when the policy
reorganizes, and it breaks *silently* — the text still reads plausibly while
pointing at whatever now occupies that number. The CEP navigation guide exists to
route a reader to the right section from a question; let it.

**No inline prescriptions.** Do not restate what the policy requires inside the
error string. A remedy copied into a message is duplicated policy: it drifts, and
the drift is invisible because nobody diffs an error message against a document. A
navigate command cannot drift — it resolves to whatever the policy currently says.

**Concept hints are encouraged.** A bare command leaves the reader guessing which
of a dozen sections applies. Naming two or three related concepts lets them choose
without the message prescribing. The distinction: **a hint is a timeless pointer, a
prescription is a copy.**

State the diagnosis — what was attempted, what failed, what the immediate cause
was. That is yours to report and does not go stale. The reasoning is the policy's
to answer.

### 3.3 Enforced or Refuse to Start

**If a boundary is declared and cannot be installed, provisioning MUST abort.**

Not warn. Not log and continue. Abort, before any code runs as the restricted
identity.

The reasoning is asymmetric in a way that is easy to get backwards. A deployment
with no control is merely unprotected, and everyone knows it. A deployment that
*documents* a control it does not have is worse, because the control is believed —
by the operator who grants access on the strength of it, and by the agent that
reads the policy and adjusts its behaviour accordingly. Every downstream decision
inherits a false premise.

Conditions that MUST abort rather than degrade:

- the enforcement mechanism is absent from the environment
- the process lacks the privilege to install the rule
- the declaration names an account that does not exist
- the account resolves to a privileged or shared identity (see prerequisite above)
- two declared accounts resolve to the same identity
- **the rule is absent when read back after installation**

That last one deserves its own line. Reporting what was requested is not evidence
of what was installed; those are two observations, and collapsing them into one is
how a control comes to be believed without existing.

---

## 4 Verification

### 4.1 Verify by Attempt, Never by Inspection

**A rule that exists and does not work reads identically to no rule.**

Inspecting configuration proves the configuration says something. It cannot
distinguish a rule that binds from a rule that was installed against the wrong
identity, the wrong protocol, or the wrong address family. The only evidence that
a boundary holds is an **attempt that fails** — made as the restricted identity,
against a destination that would answer if unblocked.

Aim each probe at something that would genuinely respond. A probe against a
destination that ignores such traffic anyway can only ever report "not reached,"
which is indistinguishable from success and is therefore worthless.

**Cover every address family.** A boundary applied to one family is stepped around
by using another. Omitting a family because the environment does not currently use
it certifies a deployment that a later network change quietly reopens.

### 4.2 The Positive Control Is Mandatory

**An environment with no connectivity at all passes every negative test perfectly.**

So every verification run must include a probe that is expected to **succeed** —
ordinary traffic to an ordinary destination, from the same identity, in the same
run. If the positive control fails, the result is not PASS. It is INCONCLUSIVE,
because the instrument has not demonstrated it can observe a reachable destination.

Without this, "nothing was reached" means either "the boundary works" or "the
network is down," and the report cannot tell you which.

### 4.3 Per-Target Baseline

**A destination that is merely down passes its own negative test perfectly**, for
the same reason.

Keep a record of which destinations have ever been reached from a given identity. A
destination that was reachable before and is unreachable now returns
**INCONCLUSIVE**, not PASS — until it is reachable again, or the boundary change
that explains it is asserted deliberately.

This is the positive-control idea applied one level down, and it is not
hypothetical: destinations flap. A verification that treats every absence as
success will eventually certify an unprotected deployment on a day a third party
happened to be unavailable.

Three outcomes, and the middle one is the point:

| verdict | meaning |
|---|---|
| PASS | boundary held, and the instrument proved it could see a reachable destination |
| FAIL | the restricted identity reached something it must not |
| INCONCLUSIVE | the run cannot distinguish a working boundary from a broken instrument |

**On a boundary check, the expensive direction is a false PASS.** A false FAIL
costs an investigation. A false PASS costs the property.

---

## 5 Currently Bounded Capabilities

**Outbound network egress** — the framework's first and currently only concrete
instance. Declared as denied TCP destination ports per agent identity, enforced at
provisioning, verified by attempt.

Others are anticipated and not yet implemented. The same argument applies wherever
an agent's reach is meant to be bounded: outbound HTTP to arbitrary hosts, package
installation from arbitrary indexes, name resolution, peer services. Each would be
declared the same way and would inherit this policy's verification requirements.

**Sizing test for a new boundary**: if the restriction can be lifted by the
component being restricted, it is not a boundary. If it cannot be verified by an
attempt that fails, it is not verifiable. Both must hold before it belongs here.

---

## 6 Integration with Other Policies

See also:

- `amail.md` — the first subsystem whose security property depends on a capability
  boundary; consult it for what its deployment requires and why credential custody
  alone was insufficient
- `container_operations.md` — conventional container security and deployment
  practice. That policy protects a trusted workload; **this one constrains the
  workload itself**, which is a different threat model applied to the same
  infrastructure. Consult both when provisioning
- `empiricism.md` — why an attempt outranks an inspection
- `debugging_and_validation.md` — positive controls, production-path validation,
  and what evidence a completion report owes a reviewer
- `autonomous_operation.md` — scope of independent action, which a boundary bounds
  in practice

---

## 7 Anti-Patterns

**Enforcing inside the restricted principal.** A check in code the agent can edit
is documentation. So is a check in a service the agent is free not to call.

**Warning instead of aborting.** A declared-but-uninstalled boundary that logs a
warning produces a deployment everyone believes is protected. Prefer a loud failure
at provisioning over a quiet one at 3 a.m.

**Inspecting the rule and calling it verified.** The configuration is not the
behaviour. Read back what was installed, then attempt to violate it.

**Omitting the positive control.** Guarantees nothing and reads as certainty. The
most common way a boundary check certifies a disconnected environment.

**Treating every absence as success.** Without a per-target baseline, a third
party's outage becomes your PASS.

**Bounding one address family.** The one you did not bound is the one that gets
used.

**Restricting on intent rather than blast radius.** "This agent is well-behaved" is
not a control, and the over-zealous case does not require misbehaviour to cause
harm. Grant on what is reachable if things go wrong, not on expected conduct.

**Shipping the boundary without the explanation.** An agent that cannot discover
why it was refused, and what to use instead, will find another path. That is not
disobedience; it is the predictable behaviour of something capable meeting an
unexplained wall.

---

## Wiki-Links

<!-- NORMATIVE node (see scholarship on node classes and provenance): this artifact
     states what MUST be done, not what was found or what was true at a moment. It is
     also INHERITED — it ships with the framework rather than being produced by any one
     agent, which is what makes the vocabulary below shared across deployments.
     Link what this policy GOVERNS, never what it merely mentions. -->

[[capability_boundary]] [[egress]] [[security]]
