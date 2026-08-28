# MacEff Maintainer Conventions

**Version**: 1.0.0
**Tier**: RECOMMENDED
**Category**: Meta
**Status**: ACTIVE
**Scope**: Anyone changing MacEff framework code, policies or provisioning

---

## Policy Statement

Conventions that are genuinely about **this framework** — its constructs, its
tools, its principals. Everything a maintainer needs that would also hold in any
other codebase lives in the general policies, and this document **cites** those
rather than restating them.

That split is the whole design, and it is worth stating why. A general control
parked in a framework-specific policy is invisible to everyone not reading about
this framework — so the rule never reaches the next person writing Python
elsewhere, and the next instance of the same problem has nowhere to live.
Restating instead of citing has the mirror failure: two copies that drift, after
which a reader cannot tell which is current.

**This document is short on purpose.** If it grows, the likely cause is a general
principle being discovered here and written down where it was found rather than
where it belongs — **discovery order is not ownership.**

---

## CEP Navigation Guide

**1 Declarative Configuration**
- Where does framework configuration live, and in what form?
- How do base-image defaults relate to deployment overrides?

**2 Speaking as the Framework**
- How does a refusal name its authority?
- What prefix identifies framework output, and where does it go?

**3 Registers Beyond the Usual Three**
- Where does exploratory reasoning belong, dead ends included?
- What must a durable artifact carry so it can be located later?

**4 Agents as a Principal Class**
- Why can a rule about agents not be stated in a general policy?
- Which principal may perform privileged placement?

**5 Shipping a Capability**
- What must accompany a new capability?

=== CEP_NAV_BOUNDARY ===

---

## 1 Declarative Configuration

**Framework configuration is YAML at the standard layout** — `agents.yaml`,
`projects.yaml`, and their siblings in the documented locations.

The general requirement, that configuration be annotatable and schema-checked, is
not ours: see `base/development/coding_standards` on config versus generated
state and on closed schemas at trust boundaries, and `lang/python/coding_standards`
for the Pydantic expression. **The choice of YAML at these paths is the framework
convention**; that is all this section adds.

**The base image provides defaults; a deployment carries overrides, with the
defaults shown commented alongside.** A deployment file that shows only what was
changed hides what was available to change, and the next maintainer cannot tell a
deliberate override from an unexamined inheritance.

---

## 2 Speaking as the Framework

### 2.1 A refusal names its policy via `macf_tools policy navigate`

The general rule — a refusal cites its authority — is not framework-specific. The
**form** is:

```
Refused: <what and why>. See: macf_tools policy navigate <policy_name>
```

**Never a section number.** Sections renumber on reorganisation and the citation
then points somewhere plausible and wrong, which is worse than pointing nowhere.
Naming the policy and letting the reader navigate survives every reorganisation
the policy will have.

### 2.2 The `⚠️ MACF:` stderr prefix

Framework warnings go to stderr carrying `⚠️ MACF:` so their origin is
identifiable in interleaved output. The stderr-warning *pattern* is Python's and
lives in `lang/python/coding_standards`; the **prefix** identifies this framework.

Settled convention rather than a new rule — recorded here because it was observed
at over two hundred sites and had never been written down.

---

## 3 Registers Beyond the Usual Three

`base/development/coding_standards` names three registers — docstring, inline
comment, commit message — chosen by what the reader intends to do next.

**This framework has a fourth: task notes and consciousness artifacts.** It holds
*exploratory* reasoning, dead ends included: what was tried, what it looked like,
why it was abandoned. That does not belong in a commit message, which describes
what a change does and is read by people who do not care how it was found.

The fourth register exists because the framework has a reader the other three do
not serve — **a successor with no memory of the work**, for whom the abandoned
path is often the most valuable thing written.

**Durable artifacts carry breadcrumbs** so a later reader can locate the moment
they were written. See the scholarship policy for the format.

---

## 4 Agents as a Principal Class

An agent is a **principal with its own trust boundary**, and this is the only
layer where that can be said — a general policy has no word for *agent*.

The general rule is in `base/development/coding_standards`: provisioning and
runtime are different trust contexts, and a runtime principal that performs its
own privileged setup collapses the boundary it sits inside.

**Here it becomes concrete: provisioning may perform privileged placement; an
agent may not.** See `base/infrastructure/capability_boundaries` for what an
agent may and may not reach.

---

## 5 Shipping a Capability

**Policy ships with the capability.** Already normative — see
`base/core_principles` — and cited here rather than restated, because a second
copy of a rule this load-bearing is exactly the drift this document is shaped to
avoid.

---

## Integration With Other Policies

| this document says | the general rule lives in |
|---|---|
| YAML at the standard layout | `coding_standards` (config vs state, closed schemas) |
| refusals cite `policy navigate` | general: a refusal names its authority |
| `⚠️ MACF:` prefix | `lang/python/coding_standards` (stderr warning pattern) |
| the fourth register | `coding_standards` (three registers) |
| agents may not self-provision | `coding_standards` (provisioning vs runtime), `capability_boundaries` |
| policy ships with the capability | `core_principles` |

---

## Wiki-Links

[[policy]] [[coding_standards]] [[capability_boundaries]] [[agent_architecture]]
