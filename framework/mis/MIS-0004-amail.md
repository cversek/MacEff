# MIS-0004: Agent mail as one system, with a broker per agent run by the primal daemon

**Number**: 0004
**Type**: Standards
**Status**: Draft
**Authors**: the container-management maintainer and the host-side maintainer
**Secretary**: the head maintainer
**Deliberation**: pending
**Created**: 2026-10-06
**Updates**: none
**Supersedes**: none
**Lands-in**: framework/policies/base/infrastructure/amail.md, rewritten as ordinary policy whose rules cite this MIS (planned); the mail system under macf/src/macf/amail/ and its tests (planned); framework/glossary.md (planned)
**Resolution**: none

---

## 1 Summary

Agent mail is specified today by the amail policy and by a working specification drafted in a separate 0.x series, and code and tests cite the clause IDs of both. MIS-0001 rejected that model by name, because it keeps a second normative source beside policy. This MIS re-specifies agent mail as a decision record and makes three changes at once. The mail system's long-lived processes (the broker, the inbound consumer and the receiver) become units that each agent's primal daemon, specified in MIS-0002, starts and supervises. Brokers become one per agent instead of one per container. And a host agent can be given an address reachable from the Internet with the same protection a container agent has. When this MIS is accepted, its requirements land in the amail policy, each rule citing `MIS-0004-Rnn (slug)`, and the 0.x series closes. It concerns every agent that sends or receives mail, on a host or in a container, and the operator who runs them.

## 2 Motivation

The operator asked on 2026-10-05 for agent mail to be re-specified as an MIS whose services the primal daemon starts, with brokers per agent if that is what it takes, so that host agents can have addresses reachable from the Internet with the container side's level of security. The authors' first exchange, the same day, found these problems behind the request.

- **One broker per container is one failure for every agent in it.** A container's broker is started by the container's startup script and owns one pickup box per agent, so a broker restart drops every agent's mail path at once. A host reboot on the night of 2026-10-04 showed it, and nothing in either container started its agent sessions or its indexer again on its own; the container-management maintainer restarted them by hand. Evidence: an incident, reported by the maintainer who runs those containers.
- **The host broker has no supervisor.** On a host, an agent starts its own broker (`_ensure_host_broker` in `macf/src/macf/cli.py`). The amail policy's host tier (§7.5) says plainly that it offers supervision, not separation, and nothing restarts the broker when it dies. Evidence: the code and the policy, read on `main`.
- **A host agent cannot safely have a reachable address today.** The host tier's design is to detect on the host and prevent in the container: no separate user for the broker, no egress rule, and an agent's identity on a shared uid taken from its own claim and audited as `claimed:<name>`. That posture suits a host nobody outside can reach. It does not suit a host with an address. Evidence: the policy (§1.3, §7.5), and reasoning.
- **Agent mail has two normative sources.** The amail policy (1152 lines, version 1.4.1) calls itself "ACTIVE — specification", and its working specification continues in a separate 0.x series. MIS-0001 rejected "the MIS as a living normative spec (the amail-spec model)" because "it creates a second normative source next to policy", and it notes that "the amail policy and its working specification already use clause IDs that code and tests cite". Those citations are what a quiet replacement would break. Evidence: the documents, read on `main`.

## 3 Goals and Non-Goals

**Goals**
- One normative source for agent mail. This MIS records the decision, the amail policy binds, and each of the policy's rules cites a requirement here. The 0.x drafting series closes.
- Nothing disappears silently. Every clause ID that code or tests cite today gets a disposition: kept as a requirement, rewritten, or moved to Rejected Alternatives or Open Questions with its reason. The landing pull request carries a table from each old clause ID to its new requirement, with a "cited by" column built by searching code and tests rather than from memory.
- Each agent's mailbox, contacts, rate limit and audit log belong to one broker that serves only that agent, and that agent's primal daemon starts and supervises it, as MIS-0002-R53 (mail_broker_MUST_be_managed) already asks of every mail broker.
- Giving an agent a reachable address takes one route and one addressing entry, and no new code path, whether the agent runs on a host or in a container.
- Each host declares its security posture, and detection alone is allowed only on a host with no address reachable from the Internet. Giving a host such an address then forces prevention: a service user for each broker and an egress rule for each broker. (The operator's ruling of 2026-10-05, relayed by the host-side maintainer.)
- Every agent's address is in one zone, `agents.<domain>`, with a local part made of the agent's calling-card name and short id, lowercased, for example `exampleagent_0a1b2c@agents.example.org`. There is no zone per deployment, and routes are the operator's to edit: no agent's token edits them. (The operator's ruling of 2026-10-05, relayed by the host-side maintainer.)

**Non-goals**
- How a unit is started, supervised and scheduled, and how a session is woken. MIS-0002 decides those, and this MIS depends on it without changing it. The authors place push-wake there too: the broker emits a "mail arrived" notice, and MIS-0002-R43 (wake_MUST_use_notifier) governs how the notice reaches the session.
- The mail route provider's own configuration, and the deployment's domain, which stay outside this repository.

## 4 Guide-Level Explanation

Planned. The authors write it once the inventory in the Landing Plan is done.

## 5 Terms

Planned. The inventory names the terms the Specification needs beyond the glossary and the amail policy's own.

## 6 Specification

None yet. The authors' inventory produces it: one requirement, in the line form, for each normative statement of the amail policy and its working specification that survives.

## 7 Rationale and Rejected Alternatives

Planned, with a reason beside each requirement ID.

**Rejected**
- **A living specification in MIS form.** Re-issuing the working specification as amail 1.0 in this format would rebuild the second normative source that MIS-0001 rejected. This MIS is the decision record instead, and the policy binds.
- **A zone per deployment.** Each zone would need its own sender-authentication records and would start with no reputation, while a local part in one zone needs one route. Rejected by the operator's ruling of 2026-10-05.

## 8 Prior Art

- MIS-0002 (draft, #517): the persistent layer and the primal daemon this MIS builds on, including its mail area.
- The amail policy and its working specification: the text the inventory goes through, clause by clause.
- MIS-0001: the process, and the reason a living specification was rejected.

## 9 Compatibility and Deployment

Planned. Known already: in a container, each pickup box moves under its agent's own broker, and each agent's mail clock reads the new paths; the egress rule for the mail ports exempts each broker by name, never by a wildcard.

## 10 Security and Safety

Planned. Known already: per-agent brokers multiply the egress exemptions, and each is declared by name; a broker that accepts connections from every local agent would be the shared broker again under another name; detection alone stays allowed only where no agent has a reachable address. Addresses in this MIS and its deliberation are written `agents.<domain>`, or `example.org` in examples, because the deployment's domain stays out of every public text (the operator's ruling of 2026-10-05).

## 11 Conformance

None yet: there are no requirements to check.

**Cold-reader trial**: not yet held.

## 12 Landing Plan

Planned. The authors first build an inventory: one row per normative statement in the amail policy and its working specification, the clause IDs, every code or test that cites each, and a proposed disposition (keep, rewrite or drop). The host-side maintainer takes addressing and the tier, the delivery ladder and rung 1s, outbound mail, the host tier and the credential rules. The container-management maintainer takes the broker and its enforcement, hand-off, the audit record, inbound mail and the threat model. Message format and contacts are joint. One landing pull request then carries the rewritten amail policy, the code and tests that follow it, and the table from old clause IDs to requirements.

## 13 Open Questions

- **Q01** Where does a host's egress rule live on a laptop that roams between networks? The authors propose, and the operator rules before the host-side inventory closes. (roaming_laptop_egress)
- **Q02** How does a per-agent broker on a shared uid know its own agent, which today is a claim audited as `claimed:<name>`? The authors propose, and the operator rules. (shared_uid_broker_knows_its_agent)
- **Q03** Does rung 1 survive once every agent has its own broker? The authors decide from the inventory. (rung_one_survives)
- **Q04** Is a broker's run, for health, its scheduled sweep, even an empty one, so that a quiet mailbox is not a failure? The container-management maintainer proposes it; the authors decide, against MIS-0002's health rules. (broker_run_is_the_sweep)
- **Q05** Which peers may deliver to a broker, and who declares that list? The container-management maintainer proposes a declared peer list for each broker; the authors decide. (broker_peer_list)

## 14 Deliberation Record

None yet. Whether to convene a deliberation, on which issue and with what window, is the operator's decision on this MIS's pull request (MIS-0001-R22 (operator_MUST_convene_or_explain)).

## 15 Revision History

- 2026-10-06: first draft, a skeleton opened by the Secretary. Summary, Motivation and Goals come from the authors' first exchange of 2026-10-05.

## Wiki-Links

[[amail]] [[supervision]] [[capability_boundaries]]
