# MIS-0004: Agent mail as one system, with one broker per system on its own account

**Number**: 0004
**Type**: Standards
**Status**: Final-Comment
**Authors**: the container-management maintainer and the host-side maintainer
**Secretary**: the head maintainer
**Deliberation**: https://github.com/cversek/MacEff/issues/850
**Created**: 2026-10-06
**Updates**: MIS-0002: R56 (mail_SHOULD_report_state_to_sender)
**Supersedes**: none
**Lands-in**: framework/policies/base/infrastructure/amail.md, rewritten as ordinary policy whose rules cite this MIS (planned); the mail system under macf/src/macf/amail/ and its tests (planned); framework/glossary.md (planned)
**Resolution**: none

---

## 1 Summary

Agent mail is specified today by the amail policy and by a working specification drafted in a separate 0.x series, and code and tests cite the clause IDs of both. MIS-0001 rejected that model by name, because it keeps a second normative source beside policy. This MIS re-specifies agent mail as a decision record and makes three changes.
- **The mail system's long-lived processes become supervised units, split by the account each one needs.** The broker and the inbound consumer run as units of the system daemon, on the broker's own account. The receiver runs as a unit of each agent's primal daemon (MIS-0002), as its agent.
- **One broker per system.** A container keeps its one broker, now on its own account under the system daemon. A host gets one too, in place of the broker each agent starts for itself today.
- **A host agent can be given an address reachable from the Internet**, with the protections a container agent has, listed in section 10, including a login of its own.

The system daemon has its own MIS, MIS-0007 (draft), and this MIS depends on it directly: the requirements that place the broker under it can't land before it does. When this MIS is accepted, its requirements land in the amail policy, each rule citing `MIS-0004-Rnn (slug)`, and the 0.x series closes. It concerns every agent that sends or receives mail, on a host or in a container, and the operator who runs them.

**This revision is the synthesis draft.** On 2026-10-28 the operator suspended the deliberation pending two prototypes, a Linux container by the container-management maintainer and a macOS host by the host-side maintainer, and moved that the Secretary gather the positions into a working specification (#850, comment 6477160351). The deliberation closed on 2026-10-31 at 02:18Z. Both prototypes reported, and this revision carries what they found: R15 takes its id from the broker's acceptance, the keystroke fallback gains two rules (R39, R40), and section 12 records which requirements the prototypes showed and which they left untested. The Secretary's synthesis on #850 proposes revise, and the MIS enters Final-Comment.

## 2 Motivation

The operator asked on 2026-10-05 for agent mail to be re-specified as an MIS whose services the primal daemon starts, with brokers per agent if that is what it takes, so that host agents can have addresses reachable from the Internet with the container side's level of security. The authors' first exchange, the same day, found the first four problems below. The deliberation on #850 added the fifth.

- **One broker per container is one failure for every agent in it.** A container's broker is started by the container's startup script and owns one pickup box per agent, so a broker restart drops every agent's mail path at once. A host reboot on the night of 2026-10-04 showed it, and nothing in either container started its agent sessions or its indexer again on its own; the container-management maintainer restarted them by hand. Evidence: an incident, reported by the maintainer who runs those containers. The deliberation kept one broker per system all the same, and answers this with supervision, durable intakes and pulled hand-off: a broker that is down delays mail and loses none.
- **The host broker has no supervisor.** On a host, an agent starts its own broker (`_ensure_host_broker` in `macf/src/macf/cli.py`). The amail policy's host tier (§7.5) says plainly that it offers supervision, not separation, and nothing restarts the broker when it dies. Evidence: the code and the policy, read on `main`.
- **A host agent can't safely have a reachable address today.** The host tier's design is to detect on the host and prevent in the container: no separate user for the broker, no egress rule, and an agent's identity on a shared uid taken from its own claim and audited as `claimed:<name>`. That posture suits a host nobody outside can reach. It does not suit a host with an address. Evidence: the policy (§1.3, §7.5), and reasoning.
- **Agent mail has two normative sources.** The amail policy (1152 lines, version 1.4.1) calls itself "ACTIVE — specification", and its working specification continues in a separate 0.x series. MIS-0001 rejected "the MIS as a living normative spec (the amail-spec model)" because "it creates a second normative source next to policy", and it notes that "the amail policy and its working specification already use clause IDs that code and tests cite". Those citations are what a quiet replacement would break. Evidence: the documents, read on `main`.
- **The seats that live on mail say it fails on the notice path.** Four container seats reported through their host agent on #850:
  - two intakes with one name, where the second overwrote the first and both sends reported delivered (Seat K);
  - notices replayed after a restart for mail already read, and a notice lost because the channel looked for the wrong daemon (Seat N);
  - a notice naming an id that a read couldn't find yet (Seats K and N);
  - a notice typed into a terminal while a permission prompt waited (Seat M);
  - recipients stuck for most of a day behind their own unanswered prompt while their mail counted as delivered (Seats L and N).

  Evidence: incidents, reported by the seats that lived them.

## 3 Goals and Non-Goals

**Goals**
- One normative source for agent mail. This MIS records the decision, the amail policy binds, and each of the policy's rules cites a requirement here. The 0.x drafting series closes.
- Nothing disappears silently. Every clause ID that code or tests cite today gets a disposition: kept as a requirement, rewritten, or moved to Rejected Alternatives or Open Questions with its reason. Each landing pull request carries a table from each old clause ID it retires to its new requirement, with a "cited by" column built by searching code and tests rather than from memory.
- Each agent's mailbox, contacts, rate limit, queues and audit log are kept apart inside its system's one broker: by the operating system where it can do it (the box), and by a test on two real accounts where it can't (R12).
- Giving an agent a reachable address takes one route and one addressing entry, and no new code path, whether the agent runs on a host or in a container.
- Each host declares its security posture, and detection alone is allowed only on a host with no address reachable from the Internet. Giving a host such an address then forces prevention: the broker on its own account, an egress rule that only that account passes, and a login of its own for each reachable agent. (The operator's ruling of 2026-10-05, relayed by the host-side maintainer and confirmed on this pull request; the account and the login come from #850.)
- Every agent's address is in one zone, `agents.<domain>`, with a local part made of the agent's calling-card name and short id, lowercased, for example `exampleagent_0a1b2c@agents.example.org`. There is no zone per deployment, and routes are the operator's to edit: no agent's token edits them. (The operator's ruling of 2026-10-05, relayed by the host-side maintainer and confirmed on this pull request.)
- A sender is told what happened: each state of a message is reported by the holder that performed it.
- Mail between MacEff agents is signed and attested. Each agent signs with its own key, and the operator declares every agent's public key. Mail from senders outside MacEff can't be required to sign, so it stays unverified. (The operator's review of this revision, 2026-10-31.)

**Non-goals**
- How a unit is started, supervised and scheduled, and how a session is woken. MIS-0002 decides those for primal daemons and MIS-0007 for the system daemon; this MIS depends on both without changing them. Push-wake stays there too: the broker raises a "mail arrived" notice, and MIS-0002-R43 (wake_MUST_use_notifier) governs how the notice reaches the session.
- The mail route provider's own configuration, and the deployment's domain, which stay outside this repository.
- Proving who composed mail from outside MacEff. Inside MacEff a signature proves which account holds the signing key (R41 to R46); where agents share a login, that is the login, and receipts say so (R46).

## 4 Guide-Level Explanation

A message from agent A to agent B on the same system goes like this. A signs it with its own key and submits it over the broker's socket. The broker verifies the signature against A's key in the operator's registry, and refuses the message if it doesn't verify. The broker takes A's identity from the socket's peer uid, checks B against A's contacts, gives the message one id, and queues it in A's queue. It writes the message into B's box, which the broker owns and only B's group can read. B's receiver, a unit of B's primal daemon running as B, pulls it into B's store, after checking on the open file that the broker owns it and that it has a single link, and then removes it from the box.

While B has unread mail, B's notice stays asserted, naming the unread ids oldest first, and it clears when B's read cursor passes them. Each step sends A a receipt from the holder that did it: stored, taken, ingested, raised, delivered (B's transcript shows the notice), read. If B's session is down, A's receipt says so. If B's oldest unpulled message passes its declared age, the outside watch tells a person.

Between systems, the broker finds the peer in the declared map, writes into an intake it owns for that peer, and the peer's broker pulls it. Nothing writes into a tree another account owns.

A seat that wants to wake itself later uses a primal-daemon schedule entry (`macf_tools pd entry add`), not mail to itself.

## 5 Terms

These are the terms the Specification uses beyond the glossary. Until MIS-0007 lands, its own Terms section defines the system daemon in full.
- **system**: one host, or one container, with one system daemon.
- **system daemon**: the one root-run supervisor per system that starts each of its units as the account its declaration names (MIS-0007, draft).
- **unit**: a managed unit (glossary), of a primal daemon or of the system daemon.
- **broker**: the unit that accepts agents' submissions, enforces their contacts and limits, holds the route credentials, and moves mail between boxes and intakes.
- **inbound consumer**: the unit that takes mail arriving from outside the system and hands it to the broker.
- **receiver**: the unit that ingests an agent's mail into that agent's store, running as that agent.
- **box**: the place where the broker puts one agent's mail on its own system; the amail policy's pickup box.
- **intake**: the place where a broker writes mail for one peer on another system to pull.
- **route**: the operator's entry for how mail to an address leaves its system, with the credential that path needs.
- **declared map**: the operator's declaration of which addresses live on this system, and which peer serves each of the others.
- **peer list**: the part of the declared map that names the other systems' brokers whose intakes this broker reads.
- **rung**: one step of the amail policy's delivery ladder.
- **posture**: a system's declared security mode, either prevention or detection alone.
- **egress rule**: the system's firewall rule for the mail ports.
- **sweep**: the broker's scheduled pass over its boxes and intakes (MIS-0002-R54 (periodic_mail_clock_MUST_be_schedule)).
- **receipt**: a report to a message's sender of one state of that message: stored, taken, ingested, raised, delivered, read or quarantined.
- **ingested**: the receipt state for a message that the recipient's receiver has taken into the recipient's store.
- **raised**: the receipt state for a notice that the recipient's primal daemon has raised through the notifier.
- **delivered**: the receipt state for a notice whose id the session's transcript monitor has seen in the session's transcript. Seat K used "delivered" for a message that the recipient's box has ingested; that state is **ingested** here.
- **quarantined**: the receipt state for a message that the broker set aside (R20).
- **doorbell**: one mail notice to a recipient.
- **urgent mark**: a sender's mark on a message asking for a doorbell inside the recipient's interval, which the recipient's declared policy allows or not.
- **transcript monitor**: the primal-daemon unit that follows a session's transcript (MIS-0002).
- **asserted**: the state of a notice that stays raised until the reader's cursor passes the mail it names.
- **read cursor**: the point in an agent's mail up to which the agent has read.
- **calling card**: an agent's name and short id, as its identity file gives them.
- **MacEff agent**: an agent whose address the operator declares in the key registry.
- **key registry**: the operator's declaration of each MacEff agent's address, its public keys with their validity dates, and the account that holds each key; only the operator can write it.
- **attested**: the trust state of a message whose signature verified against its sender's declared key; **suspect**, of one whose check was attempted and failed; **unverified**, of one no check applies to.
- **identity file**: the file in an agent's home that holds the agent's identity, which its primal daemon reads (MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)).

## 6 Specification

The Secretary gathered these preliminary requirements from the positions on #850, at the operator's motion of 2026-10-28. Section 7 gives each one's reason and source. Section 12 assigns each one to a prototype, or holds it.

### 6.1 Placement and accounts

- **R01** [MUST · decidable: macf/tests/test_amail_placement.py::test_one_broker_per_system] Each system MUST run exactly one broker and one inbound consumer, as units of its system daemon, serving every agent on that system. (broker_MUST_be_one_per_system)
- **R02** [MUST · decidable: macf/tests/test_amail_placement.py::test_broker_has_own_account] Where a system's posture is prevention, its broker and inbound consumer MUST run as one unprivileged account that is neither root nor any agent's account. (broker_MUST_run_as_its_own_account)
- **R03** [MUST · judgment: the head maintainer, at review of each change to the broker] The broker MUST hold no secret that belongs to a single agent, only the route credentials the operator declares. (broker_MUST_hold_no_per_agent_secret)
- **R04** [MUST · decidable: macf/tests/test_amail_placement.py::test_receiver_runs_as_its_agent] The receiver MUST run as its agent, as a unit of that agent's primal daemon, and ingest into that agent's store. (receiver_MUST_run_as_its_agent)
- **R05** [MUST · decidable: macf/tests/test_amail_placement.py::test_reachable_agent_has_own_login] Where an agent has an address reachable from the Internet, that agent MUST run under a login that no other agent or session shares. (reachable_agent_MUST_have_its_own_login)

### 6.2 Addresses and origin

- **R06** [MUST · decidable: macf/tests/test_amail_address.py::test_address_from_identity_file] Each sender, broker and map MUST derive an agent's address from the calling card in its home's identity file, never from an environment variable. (address_MUST_derive_from_identity_file)
- **R07** [MUST · decidable: macf/tests/test_amail_address.py::test_origin_from_peer_uid] When a local agent submits mail, the broker MUST take the sender from the socket's peer uid, and mark the sender claimed where that uid is shared. (origin_MUST_come_from_peer_uid)

### 6.3 Routing

- **R08** [MUST · decidable: macf/tests/test_amail_routing.py::test_rung_from_declared_map] The broker MUST choose a rung from the declared map: local addresses from its system daemon's declaration, others from the peer list, never from the domain. (rung_MUST_come_from_declared_map)
- **R09** [MUST · decidable: macf/tests/test_amail_routing.py::test_only_declared_peers] The broker MUST read only intakes of peers that the operator declares in a file no agent can write; with no declaration, it reads none. (broker_MUST_read_only_declared_peers)

### 6.4 Hand-off and partition

- **R10** [MUST · decidable: macf/tests/test_amail_handoff.py::test_next_holder_pulls] When a message moves between accounts, the next holder MUST pull it, so that no process writes into a tree another account owns. (handoff_MUST_be_pulled_by_its_recipient)
- **R11** [MUST · decidable: macf/tests/test_amail_handoff.py::test_copy_kept_until_next_holder_completes] A holder MUST delete its copy of a message only after the next holder reports its own step complete. (holder_MUST_keep_copy_until_next_completes)
- **R12** [MUST · decidable: macf/tests/test_amail_partition.py::test_two_accounts] The broker MUST keep each agent's contacts, limits, queues, audit records and box apart, so that no agent reads or submits as another. (broker_MUST_partition_state_per_agent)
- **R13** [MUST · decidable: macf/tests/test_amail_partition.py::test_box_permissions] Each recipient's box MUST be owned by the broker's account and readable only by that recipient's group, which alone removes a message after ingesting it. (box_MUST_be_readable_only_by_its_agent)
- **R14** [MUST · decidable: macf/tests/test_amail_handoff.py::test_intake_names_unique] Each intake name MUST be unique per recipient and per message, so that no send overwrites another, whatever its recipients or timing. (intake_name_MUST_be_unique)
- **R15** [MUST · decidable: macf/tests/test_amail_handoff.py::test_one_id_end_to_end] Each message MUST keep one id, minted by the broker that accepts it and unique across that broker's restarts, from that acceptance to the recipient's read. (message_id_MUST_be_one_from_acceptance)
- **R16** [MUST · decidable: macf/tests/test_amail_handoff.py::test_duplicate_dropped] When the receiver meets a message id it has already ingested, it MUST drop the copy and record the drop. (receiver_MUST_drop_duplicate_ids)
- **R36** [MUST NOT · decidable: macf/tests/test_amail_partition.py::test_box_files_not_group_writable] A group MUST NOT have write permission on any message file in a box. (box_file_MUST-NOT_be_group_writable)
- **R37** [MUST · decidable: macf/tests/test_amail_partition.py::test_receiver_checks_owner_and_links] The receiver MUST ingest only a file that the broker's account owns with a link count of one, both read on the descriptor it opened. (receiver_MUST_check_owner_and_link_count)
- **R38** [MUST · decidable: macf/tests/test_amail_handoff.py::test_one_copy_per_recipient] The broker MUST write one copy per recipient, and never fan a message out by hard-linking one file into several boxes. (broker_MUST_write_one_copy_per_recipient)

### 6.5 Flow control

- **R17** [MUST · decidable: macf/tests/test_amail_flow.py::test_queues_per_agent] The broker MUST queue each sender's submissions and each recipient's deliveries apart, so that one stalled agent holds back only its own mail. (queue_MUST_be_per_agent)
- **R18** [MUST · decidable: macf/tests/test_amail_flow.py::test_refusal_reaches_sender] When the broker refuses or limits a submission, it MUST return the refusal and its reason to the sender, and never drop the message silently. (refusal_MUST_reach_the_sender)
- **R19** [MUST · decidable: macf/tests/test_amail_notice.py::test_doorbell_interval] The recipient's notifier MUST hold the recipient's declared minimum interval between doorbells; a sender's urgent mark skips it only within the recipient's declared policy. (doorbell_MUST_respect_recipient_interval)
- **R20** [MUST · decidable: macf/tests/test_amail_flow.py::test_quarantine] If the broker cannot parse a message, or handling it fails a declared number of times, then the broker MUST set it aside and report it. (broker_MUST_quarantine_repeated_failure)

### 6.6 Receipts

- **R21** [MUST · decidable: macf/tests/test_amail_receipts.py::test_states_from_holders] Each receipt state MUST come from the holder that performed it, never from the sender's inference. (receipt_MUST_come_from_its_holder)
- **R22** [MUST · decidable: macf/tests/test_amail_receipts.py::test_delivered_needs_acknowledgement] A receipt MUST say delivered only after the session's transcript monitor sees the notice's id in the session's transcript; until then it says raised. (delivered_MUST_need_acknowledgement)
- **R23** [MUST · decidable: macf/tests/test_amail_receipts.py::test_recipient_offline] Where the recipient's session is down, the receipt MUST say so, with the time it went down. (receipt_MUST_report_recipient_offline)
- **R24** [MUST · decidable: macf/tests/test_amail_receipts.py::test_state_by_id] When a sender asks the broker for a message's state by its id, the broker MUST answer with the latest receipt state. (state_MUST_be_queryable_by_id)

### 6.7 Notices

- **R25** [MUST · decidable: macf/tests/test_amail_notice.py::test_notice_follows_ingest] A mail notice MUST name only messages that the reader's own commands can already read. (notify_MUST_follow_ingest)
- **R26** [MUST · decidable: macf/tests/test_amail_notice.py::test_notice_level_triggered] While unread mail exists, the mail notice MUST stay asserted, and it clears only when the reader's cursor passes that mail. (notice_MUST_derive_from_unread_state)
- **R27** [MUST NOT · decidable: macf/tests/test_amail_notice.py::test_restart_keeps_cursor] A restart of any unit MUST NOT advance an agent's read cursor. (restart_MUST-NOT_advance_read_cursor)
- **R28** [MUST · decidable: macf/tests/test_amail_notice.py::test_notice_carries_ids] Each mail notice MUST carry the ids of the unread messages it names, oldest first, with the count waiting. (notice_MUST_carry_message_ids)
- **R29** [MUST · decidable: macf/tests/test_amail_notice.py::test_keystrokes_need_idle_prompt] Where a mail notice falls back to keystrokes, it MUST type only when no dialog waits, the input box is empty, and the transcript's last turn has ended. (keystroke_fallback_MUST_confirm_idle_prompt)
- **R39** [MUST · decidable: macf/tests/test_amail_notice.py::test_keystrokes_read_back] A keystroke notice MUST send its text and its return separately, then read the input box back, and retry only while the box still holds that notice. (keystroke_notice_MUST_be_read_back)
- **R40** [MUST NOT · decidable: macf/tests/test_amail_notice.py::test_keystroke_notice_no_leading_digit] A keystroke notice MUST NOT begin with a digit. (keystroke_notice_MUST-NOT_begin_with_digit)
- **R30** [SHOULD · decidable: macf/tests/test_amail_notice.py::test_listing_new_since_last_read] When woken by a notice, the reader's listing SHOULD show only mail new since its last read, with a count of the rest. (listing_SHOULD_show_new_since_last_read)

### 6.8 Health

- **R31** [MUST · decidable: macf/tests/test_amail_health.py::test_health_is_last_sweep] The broker's health MUST be its last sweep's verdict, so a clean empty sweep is healthy and a failed or missing sweep is not. (broker_health_MUST_be_its_sweep)
- **R32** [MUST · decidable: macf/tests/test_amail_health.py::test_stuck_mail_alerts] When the broker is unhealthy, or the broker's oldest unpulled message or an agent's oldest unread message passes its declared age, the outside watch MUST alert a person. (stuck_mail_MUST_reach_a_person)

### 6.9 Egress, transport and the socket

- **R33** [MUST · decidable: macf/tests/test_amail_egress.py::test_rule_allows_only_declared_accounts] The egress rule MUST let only the broker's account and the human accounts the operator declares open the mail ports, matching each socket's owner. (host_egress_MUST_match_the_broker_account)
- **R34** [MUST · decidable: macf/tests/test_amail_transport.py::test_pinned_bundle] The broker's outbound transport MUST verify servers against a pinned trust bundle that the operator rotates by a declared procedure. (transport_MUST_pin_trust_bundle)
- **R35** [MUST · decidable: macf/tests/test_amail_units.py::test_socket_version] The broker socket MUST carry a protocol version, and accept the previous version for a declared window after each change. (broker_socket_MUST_carry_version)

### 6.10 Signing

- **R41** [MUST · decidable: macf/tests/test_amail_signing.py::test_agent_signs_every_message] Each MacEff agent MUST sign every message it submits, with a key that only its own account can read. (agent_MUST_sign_its_messages)
- **R42** [MUST · decidable: macf/tests/test_amail_signing.py::test_keys_declared_by_operator] Each MacEff agent's public key MUST be declared, with the account holding it, in a registry only the operator can write and every broker and receiver can read. (agent_key_MUST_be_declared_by_operator)
- **R43** [MUST · decidable: macf/tests/test_amail_signing.py::test_broker_refuses_unsigned_agent_mail] The broker MUST refuse a MacEff agent's submission that carries no signature verifying against that agent's declared key. (broker_MUST_refuse_unsigned_agent_mail)
- **R44** [MUST · decidable: macf/tests/test_amail_signing.py::test_receiver_marks_unsigned_agent_mail_suspect] A receiver MUST mark suspect a message whose sender address is in the registry, when its signature is missing or fails against that sender's declared keys. (receiver_MUST_flag_unsigned_agent_mail)
- **R45** [MUST · decidable: macf/tests/test_amail_signing.py::test_rotation_keeps_old_signatures_verifiable] A retired key MUST verify only messages whose broker acceptance time falls inside its declared validity dates, and never sign new ones. (key_rotation_MUST_keep_signatures_verifiable)
- **R46** [MUST · decidable: macf/tests/test_amail_signing.py::test_shared_login_attestation_labelled] A receiver MUST report a verified message as attested on a shared login when the signing key's account also holds another agent's key. (shared_login_attestation_MUST_be_labelled)

## 7 Rationale and Rejected Alternatives

Each requirement's reason, with its source. P and O numbers refer to section 14.
- **R01**: one broker per system holds the route's credential once. Brokers per agent would hold copies of one secret, and copies drift: on one host an account-wide credential ended up under two keychain items, and the stale one kept being read (#852, #853). Sources: the host-side maintainer (P08), the container-management maintainer (P09), and the operator's question (P06).
- **R02**: the amail policy already puts the broker on its own uid (§3.2). On an agent's account, everything the broker enforces sits where the agent can write: its contacts, its rate limit, its audit log and the credentials (P01). Not root: the pickup box removed the one place a broker needed root, and the broker parses mail from the Internet (P07, P09).
- **R03**: the premise Q06's answer rests on. Written down, it makes adding a per-agent secret reopen the decision instead of quietly voiding it (P10, agreed in P16). On macOS the route credential is a file only the broker's account can read, not a keychain item, because a system-domain job has no login keychain (P19). If authorship is ever proved, the agent holds its signing key and signs before it submits, and the broker only verifies (P16).
- **R04**: the receiver writes the agent's store, so it runs as the agent (P01, P09).
- **R05**: on a shared login, anything running as that login can make the agent's own process tree speak, for example through `tmux send-keys`. So process ancestry identifies the process that spoke, not the party that composed the message (P02); the container-management maintainer withdrew ancestry as a boundary (P03). Section 10 states the cost.
- **R06**: #836 was this failure in another place. A name taken from an environment variable whose case differed from the card looked for a socket nobody made, and read healthy throughout (P05). Seat L's calling card and mail address are two different strings today, and peers use either (P11).
- **R07**: the container's rule that the uid table is the authentication table (amail §1.3), carried to every system. It also makes the trust label vary, where today every message carries the same one (P13, P14).
- **R08**: with one zone, the domain no longer says which broker owns a mailbox (P05). With one broker per system, local means this system's broker, so rung 1 survives for local mail, and the map is needed between systems (P08, P09).
- **R09**: rung 1s already reads only the intakes of declared peers. This generalizes it to every broker (P01). Section 10 records the reason: a broker that accepts every local agent would be the shared broker again under another name.
- **R10**: a broker that writes into another account's tree needs a privilege across accounts, which the pickup box removed (P01).
- **R11**: a restart in the middle of a hand-off then loses nothing (P01). Seat K asks that the restart test kill the broker mid-intake (P12).
- **R12**: with one broker, separation moves from the kernel into the broker's code (P09). It is shown on two real accounts: refusal and success in the same run (P13), multi-recipient and same-second sends (P12), and a test run by someone other than its author (P13).
- **R13**: the operating system keeps boxes apart wherever it can, given R05 (P09, condition (a)). The recipient's group removes a message after ingesting it, which is the recipient's custody transfer; if only the broker could delete, every removal would wait on a receipt (P18). On macOS a new file takes its directory's group, and on Linux a setgid box directory does the same, so the broker needn't hold every recipient's group, which `setgroups` caps at 16 on macOS (P21, P22).
- **R14**: in a multi-seat container, two intakes once shared a name. The second overwrote the first, and both sends reported delivered (P12).
- **R15**: once the broker's id, the sender's copy and the recipient's id differed, threading broke (P12). Ids unique across restarts let a recipient drop duplicates (P13). The container prototype found that the broker already replaces the sender's id with its own at submission, and that a shared hand-off between brokers rewrote it again (P26). The operator chose "from the broker's acceptance", relayed by the container-management maintainer, who proposed this text with "The sender records the id the broker returns" (P27); the host-side maintainer agreed, and launchd changes nothing, since the broker mints a time prefix and 48 random bits with no counter in memory (P28). So a sender can't choose an id that collides with or shadows another, the sender's custody copy records the broker's id, and the rewrite at the shared hand-off goes: the receiving broker keeps the id the first broker minted. A sender's retry after a broker restart can still get a second id for one message, which R16 can't catch; Q09 keeps that open (P28).
- **R16**: pull makes a restart safe only if a repeated delivery is harmless (P13). The container prototype handed one pair off twice and found two copies of one id in the store, with no drop and no record (P26).
- **R17**: a flood holds back only its sender (P09, condition (c)). One recipient's full disk or missing box must not hold up everyone behind it (P13).
- **R18**: back-pressure reaches the sender as a refused send, never a silent drop (P12, P13). The amail policy already returns refusals as errors (§3.2).
- **R19**: each doorbell makes the recipient re-read its whole context, about 0.7M cached tokens late in a cycle, so ten small messages cost ten of those (P11). Under R26 the recipient's primal daemon raises the notice, not the broker, so the recipient's notifier holds the interval, and the broker only carries the sender's urgent mark (P18).
- **R20**: queues per agent contain a flood, not a message that crashes the shared process: every restart retries it, so everyone's mail stops (P10). One malformed message must not stop the broker (P13), and the set-aside message leaves a receipt state (P14).
- **R21**: each state of a message has a distinct holder (P01). This carries MIS-0002-R56 (mail_SHOULD_report_state_to_sender) into this MIS, as MIS-0002 set it aside to wait on it.
- **R22**: on one seat, a scheduled entry raised its notice 33 times while the session's channel wasn't loaded, and every record said notified. None reached the session (P02). A channel notice is one-way, so the plugin can't say the session took it. The session's transcript records each channel message as it arrives, and the transcript monitor already follows it (P18, agreed in P19). The same evidence confirms that keystrokes typed under R29 arrived.
- **R23**: ten review requests sat for two days because the reviewer's session was down, and nothing in the sender's channels said so (P11).
- **R24**: a sender can find where its message stopped (P12).
- **R25**: a notice once named an id that a read couldn't find, because only a listing ingested the box (P12, P14). Seat K's alternative, a read that ingests first, fixes the same race.
- **R26**: replays after a restart, a lost notice, and notices raised and never delivered are one bug: a notice sent as an edge. Held as a level, a replay is harmless and a miss is asserted again at the next attach (P14, P16).
- **R27**: an old mail clock's first start once marked waiting mail as seen (P14).
- **R28**: a seat that read the newest of a list raced a second arrival. Ids oldest first fixed a real miss (P11, P12).
- **R29**: a notice typed while a permission prompt waited landed in the prompt (P13). A sender's keystrokes went into a dialog nobody had listed (#854), and such dialogs keep turning up, so the gate is positive evidence of an idle prompt rather than a list of known dialogs (P16). MIS-0002-R21 (pd_MUST_report_waiting_on_person) is the natural first gate. The macOS prototype drove a throwaway session through 14 states, from idle and streaming to each dialog, the exit-with-background-work prompt, the rewind menu and a survey bar. The three signals together typed into no dialog and no busy session, and each signal alone had false types: the screen alone types under a running tool, whose box looks empty, and the turn check alone types into the exit prompt, where a return means "exit and stop tasks" (P25, P29). The turn check should skip a trailing interrupt record and local command records, which otherwise hold the gate until a person types; both gaps fail safe (P29).
- **R39**: twice in the macOS catalog, a single return left the text in the box. Read back, a notice still in the box is retried; a dialog that opened is never typed into (P29).
- **R40**: a survey bar reads as an empty box, and a digit answers it (P29).
- **R41**: the operator asked that mail between MacEff agents always be attested, and Q08 no longer be deferred (P30). Most of the mechanism is already on main: Ed25519 signing and verification, contact entries that declare one key or several, and trust states that keep attested apart from suspect (P31). On macOS the private key is a file of mode 0600 in a 0700 directory of the agent's own account, outside any repository, synced folder or backup that leaves the machine. Not the login keychain: its access control is per application, so on one login every agent reads what one can, and its prompts are modal dialogs that stall an unattended session. Not the Secure Enclave, which holds P-256 keys only (P32). The broker never holds an agent's key (R03), and only verifies (P30).
- **R42**: keys live today in each agent's own contacts file, which the agent can write, so the declaration moves out of the agent's reach. Its home is the operator-written, root-owned system declaration MIS-0007 drafts, so there is one registry, not two (P31, P32). The entry names the account that holds each key, which is what lets a receiver see a shared login (R46, P32). Each declaration and rotation is an operator step; that cost is the point (P32).
- **R43**: the operator's draft carried it, and the operator confirmed it dropped from the posted review by mistake (P30). An unsigned local submission is no longer attested on the kernel's identity, because on a shared login the peer uid is the same for every agent and can't stand in for a signature; so "signed" means the same on every path (P31, P32).
- **R44**: the receiver decides who is a MacEff agent from the registry: an address in it is held to its keys, and an address outside it is outside mail and stays unverified (P30, P31). Switching it on turns today's agent mail suspect until every key is declared, which is why landing declares first and enforces second (P31; section 12.4).
- **R45**: validity dates alone don't stop a stolen retired key, whose thief can date a message inside the old window. R15's acceptance time is minted by the broker, so validity is checked against it (P32). Rotation runs: the agent generates a new key in its own account, the operator declares it with its start date, the agent switches to it, then the operator sets the old key's end date; the agent never signs with an undeclared key (P32). A suspected exposure, a change of account, or a move to another machine triggers it; a migration or restore generates a new key and never carries the old private key. After a compromise the end date is the last time the key is known safe (P32).
- **R46**: where agents share one login, any process of that login can read every agent's key file, so a signature attests the login (P30, P32). The registry names each key's account, so a receiver can say so rather than leave it in prose. A login per agent is possible on macOS, at an operator root step per agent, and this MIS doesn't require it (P32).
- **R30**: a listing prints the whole mailbox on every wake, so each notice costs the entire history (P13).
- **R31**: a broker that is quiet because it is idle and one that is quiet because mail is stuck look the same to anyone not reading `pd status` (P01).
- **R32**: Seats L and N each sat most of a day behind their own unanswered prompt while their mail counted as delivered (P11, P14). Under R04 the receiver keeps pulling while the session waits behind a prompt, so the unpulled age alone would never have fired for them. What aged was the oldest unread message, which the agent's primal daemon publishes in its status (P18). The outside watch alerts by a path independent of the recipient's session and of the broker (MIS-0002-R75 (outside_watch_MUST_alert_independently)).
- **R33**: pf's `user` and iptables' `--uid-owner` match the socket's owner, so the rule holds on any network the host joins (P02, P03). It is an allow-list because a deny-list fails open for any account whose rule is missing (P03). A native mail client running as the operator's login opens the same ports, so the operator declares the human accounts the rule admits (P19). Loading the rule needs root, so it is the operator's install step, a container's start step, and the system daemon's status reports whether it is loaded (MIS-0007; P19, P20).
- **R34**: a public certificate-authority compromise once left every client in a container accepting a forged chain (P13). The pin rotates by a declared procedure, because a pin that can't rotate turns a provider's certificate change into a mail outage (P15).
- **R35**: one broker serves seats on different builds, and three builds of macf are in use on one host today (P10, P16).
- **R36**: only the broker writes a message (P18). In the container prototype R36 held partly because the broker's umask is 022, since the write path sets the mode by path after creating the file. Setting the mode on the descriptor before writing, or a declared umask per unit, makes it independent of the umask (P26).
- **R37**: a recipient's group that may remove files from its box may also create them there, so the receiver checks the owner on the descriptor it opened. A hard link passes an owner check, and macOS has nothing that restricts one, so the link count must be one as well. A file that fails either check is set aside and reported under R20 (P20, P21, P22). In the container prototype, today's ingest read by path, and a pair the recipient's own account planted and a symlinked pair both entered its store as mail from the other seat; a hard link was refused only by the host's `fs.protected_hardlinks`, which no deployment promises (P26).
- **R38**: a message fanned out by hard links would fail every recipient's link-count check under R37 (P22).

**Rejected**
- **A living specification in MIS form.** Re-issuing the working specification as amail 1.0 in this format would rebuild the second normative source that MIS-0001 rejected. This MIS is the decision record instead, and the policy binds.
- **A zone per deployment.** Each zone would need its own sender-authentication records and would start with no reputation, while a local part in one zone needs one route. Rejected by the operator's ruling of 2026-10-05.
- **A broker per agent.** Both authors withdrew it on #850 (P08, P09). The broker's secret is the route's credential (amail §3.2, §7.2), brokers per agent hold drifting copies of one secret (#852, #853), and a service daemon per broker is the sprawl MIS-0002 set out to end (P04).
- **A standalone broker per system, outside the system daemon.** The operator ruled it out as sprawl (P04).
- **A broker that runs as root.** The pickup box removed the last reason for it, and the broker parses mail from the Internet (P07, P09).
- **Process ancestry as the boundary on a shared login** (Q02's option (b)). Anything running as the login can make the agent's own tree speak. It stays only as a better record than `claimed:<name>` where detection alone is allowed (P02, P03).
- **A deny-list egress rule.** It fails open for any account whose rule is missing (P03).
- **The outside watch as a unit of the system daemon.** A watch inside what it checks dies with it (P09). The head maintainer and the host-side maintainer withdrew it (P10, P16). MIS-0007 carries this.

## 8 Prior Art

- MIS-0002 (Final): the persistent layer and the primal daemon this MIS builds on, including its mail area and R56, which this MIS carries.
- MIS-0007 (draft): the system daemon, a direct dependency of this MIS.
- The multi-seat container's broker: one broker on its own service account, serving several seats. It is the shape this MIS adopts, and it was seen live when MIS-0002-R62 (agent_MUST_see_shared_container) was judged.
- The amail policy and its working specification: the text the inventory goes through, clause by clause.
- MIS-0001: the process, and the reason a living specification was rejected.

## 9 Compatibility and Deployment

- **In a container**, the broker stays one per container, on its own account. The container's start step stands in for the system daemon until MIS-0007 lands. The per-agent mail clock is already retired (MIS-0002 section 11), so nothing reads new paths. The egress rule changes from a deny-list to an allow-list (R33). Loading it needs the network-administration capability, which one of the two multi-seat containers lacks today (P18).
- **On a host**, the system's one broker replaces the broker each agent starts for itself today (`_ensure_host_broker`). A host whose posture is detection alone keeps working as it does today until the system daemon lands there (Q07).
- **No flag day.** Brokers move under the system daemon one system at a time, as primal-daemon units did under MIS-0002.
- **Order.** The prototypes come first (section 12), then the final draft, then landing by area.

## 10 Security and Safety

The protections a container gives a broker, one row each, with how a host meets each one (P01):

| Protection | In a container today | On a host |
|---|---|---|
| A login per reachable agent | a uid per agent | R05. The cost: on a shared-login host, the agent's home, its tools and the credentials it uses move to the agent's login, or are reached through a declared interface (P02). A login separates files, processes and keychains, not localhost TCP, so a service another login binds to the loopback must authenticate its callers; the broker socket is a Unix socket checked by peer uid, never TCP (P19, P20). The macOS prototype found that a login of its own isolates only with all three of these: (a) loopback services that authenticate their callers, or a rule that keeps other accounts off them; (b) an agent account whose primary group is its own, or an operator home at 0700; (c) the re-grant list (P25). Creating and retiring an agent's account also manages its launchd user domain, which outlived the account's deletion until it was booted out (P29) |
| A broker on an account no agent shares | the broker's service account | R02, under the system daemon (MIS-0007) |
| Egress for the broker only | an owner-matched rule, today a deny-list | R33: pf `user` on macOS, iptables `--uid-owner` on Linux, as an allow-list |
| An intake per declared peer | a shared filesystem as the wire | R09, R10 and R14 |
| A declaration no agent can change | written by root (persistent_layer 10.1) | the system daemon's root-written declaration (MIS-0007) |
| A restart after a recreate | the start step | the system daemon (MIS-0007) |
| The job's environment, declared in full | in part, by the start step | MIS-0007, checked under `env -i` on both platforms (P02, P03) |

**What one broker per system concentrates.** Every agent's contacts, limits, queues and audit records sit in one account. The broker's code keeps them apart (R12), and for boxes the operating system does (R13). The broker holds the route credentials by design and is not defended against its own compromise (amail §7.2). R03 keeps it from holding anything that belongs to one agent.

**Authorship.** The amail policy lists authorship as not defended (§7.2). Between MacEff agents this MIS defends it: a signature proves which account holds the key (R41 to R46). A compromised broker can no longer alter agent mail undetected, though it still holds the route credentials by design. Outside mail stays undefended.

**Shared logins.** The human accounts R33 admits include the operator's login, so on a shared login they admit the agents too. R33 separates anything only together with R05, and a shared-login host stays in detection posture until each reachable agent has a login of its own (P19).

Detection alone stays allowed only where no agent has a reachable address. Addresses in this MIS and its deliberation are written `agents.<domain>`, or `example.org` in examples, because the deployment's domain stays out of every public text (the operator's ruling of 2026-10-05).

## 11 Conformance

| Requirement | Check | How | State |
|---|---|---|---|
| R01 | decidable | `macf/tests/test_amail_placement.py::test_one_broker_per_system` | planned |
| R02 | decidable | `macf/tests/test_amail_placement.py::test_broker_has_own_account` | planned |
| R03 | judgment | the head maintainer, at review of each change to the broker | standing |
| R04 | decidable | `macf/tests/test_amail_placement.py::test_receiver_runs_as_its_agent` | planned |
| R05 | decidable | `macf/tests/test_amail_placement.py::test_reachable_agent_has_own_login` | planned |
| R06 | decidable | `macf/tests/test_amail_address.py::test_address_from_identity_file` | planned |
| R07 | decidable | `macf/tests/test_amail_address.py::test_origin_from_peer_uid` | planned |
| R08 | decidable | `macf/tests/test_amail_routing.py::test_rung_from_declared_map` | planned |
| R09 | decidable | `macf/tests/test_amail_routing.py::test_only_declared_peers` | planned |
| R10 | decidable | `macf/tests/test_amail_handoff.py::test_next_holder_pulls` | planned |
| R11 | decidable | `macf/tests/test_amail_handoff.py::test_copy_kept_until_next_holder_completes` | planned |
| R12 | decidable | `macf/tests/test_amail_partition.py::test_two_accounts`, on two real accounts, with refusal and success in one run and multi-recipient and same-second sends, run by a maintainer other than its author | planned |
| R13 | decidable | `macf/tests/test_amail_partition.py::test_box_permissions` | planned |
| R14 | decidable | `macf/tests/test_amail_handoff.py::test_intake_names_unique` | planned |
| R15 | decidable | `macf/tests/test_amail_handoff.py::test_one_id_end_to_end` | planned |
| R16 | decidable | `macf/tests/test_amail_handoff.py::test_duplicate_dropped` | planned |
| R17 | decidable | `macf/tests/test_amail_flow.py::test_queues_per_agent` | planned |
| R18 | decidable | `macf/tests/test_amail_flow.py::test_refusal_reaches_sender` | planned |
| R19 | decidable | `macf/tests/test_amail_notice.py::test_doorbell_interval` | planned |
| R20 | decidable | `macf/tests/test_amail_flow.py::test_quarantine` | planned |
| R21 | decidable | `macf/tests/test_amail_receipts.py::test_states_from_holders` | planned |
| R22 | decidable | `macf/tests/test_amail_receipts.py::test_delivered_needs_acknowledgement` | planned |
| R23 | decidable | `macf/tests/test_amail_receipts.py::test_recipient_offline` | planned |
| R24 | decidable | `macf/tests/test_amail_receipts.py::test_state_by_id` | planned |
| R25 | decidable | `macf/tests/test_amail_notice.py::test_notice_follows_ingest` | planned |
| R26 | decidable | `macf/tests/test_amail_notice.py::test_notice_level_triggered` | planned |
| R27 | decidable | `macf/tests/test_amail_notice.py::test_restart_keeps_cursor` | planned |
| R28 | decidable | `macf/tests/test_amail_notice.py::test_notice_carries_ids` | planned |
| R29 | decidable | `macf/tests/test_amail_notice.py::test_keystrokes_need_idle_prompt` | planned |
| R30 | decidable | `macf/tests/test_amail_notice.py::test_listing_new_since_last_read` | planned |
| R31 | decidable | `macf/tests/test_amail_health.py::test_health_is_last_sweep` | planned |
| R32 | decidable | `macf/tests/test_amail_health.py::test_stuck_mail_alerts` | planned |
| R33 | decidable | `macf/tests/test_amail_egress.py::test_rule_allows_only_declared_accounts` | planned |
| R34 | decidable | `macf/tests/test_amail_transport.py::test_pinned_bundle` | planned |
| R35 | decidable | `macf/tests/test_amail_units.py::test_socket_version` | planned |
| R36 | decidable | `macf/tests/test_amail_partition.py::test_box_files_not_group_writable` | planned |
| R37 | decidable | `macf/tests/test_amail_partition.py::test_receiver_checks_owner_and_links`, with a hard link from outside and a file the recipient's group created, each set aside | planned |
| R38 | decidable | `macf/tests/test_amail_handoff.py::test_one_copy_per_recipient` | planned |
| R39 | decidable | `macf/tests/test_amail_notice.py::test_keystrokes_read_back` | planned |
| R40 | decidable | `macf/tests/test_amail_notice.py::test_keystroke_notice_no_leading_digit` | planned |
| R41 | decidable | `macf/tests/test_amail_signing.py::test_agent_signs_every_message` | planned |
| R42 | decidable | `macf/tests/test_amail_signing.py::test_keys_declared_by_operator` | planned |
| R43 | decidable | `macf/tests/test_amail_signing.py::test_broker_refuses_unsigned_agent_mail` | planned |
| R44 | decidable | `macf/tests/test_amail_signing.py::test_receiver_marks_unsigned_agent_mail_suspect` | planned |
| R45 | decidable | `macf/tests/test_amail_signing.py::test_rotation_keeps_old_signatures_verifiable` | planned |
| R46 | decidable | `macf/tests/test_amail_signing.py::test_shared_login_attestation_labelled` | planned |

**Cold-reader trial**: not yet held.

**Use trial**: not yet held.

## 12 Landing Plan

### 12.1 The prototypes

The operator's motion on #850 (P17) made the previous revision the working specification for two prototypes. Both reported before the window closed. What each showed, so the passes aren't read wider than they are:

| | Linux container (P24, P26) | macOS host (P25, P29) |
|---|---|---|
| Held as drafted | R13, R36 and R38 on real accounts (29,703 samples during a 200-message burst found nothing group-writable but a planted control); Q06's partition, refused and audited under the kernel's identity, with the genuine seat's own submit and status succeeding in the same run (R07, R12); R14, by construction, since the broker mints every id; R18 and R15's loss case, with the broker killed mid-burst and nothing lost, duplicated or delivered after a refusal | R29's three signals across 14 states, then ten doorbells delivered once each and answered in order; R33 as a pf anchor matched to the broker's account and one declared human, blocking root and an undeclared account; the status socket read-only (MIS-0007) |
| Not met by today's code | R37 (ingest read by path), R16 (a repeated hand-off stored twice), R32 (`pending_pickup` counted only internet mail, and no age) | none |
| Changed by the results | R15, and the rewrite at the shared hand-off | R29's turn check (two fail-safe gaps), R39, R40; section 10's R05 conditions |
| Not exercised | R24 (no state-by-id verb), R25 to R28 (the notice path), R33 (no `iptables` in the image), R34, R35 | the keychain read from the system domain (Q02), the waiting-on signal under R29 (the session had no hooks) |

R08 between systems, R09 and R34 were withheld from both and stay so. The untested rows stay planned in section 11.

### 12.2 The direct dependency: MIS-0007

The system daemon's requirements are in MIS-0007 (draft), at the operator's addendum to the motion (P17), so that mail and the system daemon can be developed in parallel without breaking the basis for reconciling them. R01, R02 and the rows of section 10 that name the system daemon wait on it. Until it lands, a container's start step stands in for it, as it does today.

### 12.3 Carried to MIS-0006

The shared embedding model at the system daemon, with a quota per agent and no input retained, belongs to MIS-0006 (#751), not here (P10, P12).

### 12.4 After the prototypes

The authors' inventory continues: one row per normative statement in the amail policy and its working specification, the clause IDs, every code or test that cites each, and a proposed disposition (keep, rewrite or drop). The host-side maintainer takes addressing and the tier, the delivery ladder and rung 1s, outbound mail, the host tier and the credential rules. The container-management maintainer takes the broker and its enforcement, hand-off, the audit record, inbound mail and the threat model. Message format and contacts are joint. The prototypes' results and the inventory together make the final draft.

This MIS lands by area, in several pull requests rather than one (P05, P09). Each pull request carries its requirements' Conformance rows and the old clause IDs it retires.

The three receiver changes the container prototype found were opened at the operator's direction before this synthesis (P27): R37's ingest by descriptor (#862), R16's dropped repeat (#865), and the broker's half of R32, the pending count with agent bundles and its oldest age (#863). They change today's code to meet the drafted text, and they move no Conformance row: each row moves when its named test lands.

Signing lands in two steps, declare first and enforce second (P31, P32). First every agent generates its key and the operator declares it (R41, R42); only then do the broker's refusal (R43) and the receiver's suspect mark (R44) switch on, so that today's agent mail doesn't turn suspect in between.

## 13 Open Questions

- **Q01** Where does a host's egress rule live on a laptop that roams between networks? Preliminary answer: nowhere network-specific. R33 matches the socket's owner, and the host prototype loads one pf rule with the operator. (roaming_laptop_egress)
- **Q02** How does a per-agent broker on a shared uid know its own agent, which today is a claim audited as `claimed:<name>`? Preliminary answer: it can't. R05 gives each reachable agent a login of its own, and R07 marks a sender on a shared uid as claimed. (shared_uid_broker_knows_its_agent)
- **Q03** Does rung 1 survive once every agent has its own broker? Preliminary answer: with one broker per system, it survives for local mail, chosen from the declared map (R08). (rung_one_survives)
- **Q04** Is a broker's run, for health, its scheduled sweep, even an empty one, so that a quiet mailbox is not a failure? Preliminary answer: yes (R31), and a failed or missing sweep reaches a person (R32). (broker_run_is_the_sweep)
- **Q05** Which peers may deliver to a broker, and who declares that list? Preliminary answer: the operator declares it, in a file no agent can write (R09). (broker_peer_list)
- **Q06** Should there be one broker per system, or one per agent? Raised by the operator (P06). Preliminary answer: one per system, on its own account, as a unit of the system daemon (R01, R02), on the premise that R03 states. (broker_per_system_or_per_agent)
- **Q07** On a host whose posture is detection alone, does the system's one broker still run as its own account? Answered by both authors: yes. One shape for both postures means a move to prevention changes the egress rule and the logins, not the broker, and it takes the contacts and the audit log out of the agents' reach (P19, P20). (detection_host_broker_account)
- **Q08** Should a message carry proof of who composed it? Answered by the operator's review (P30): every MacEff agent signs (R41 to R46), outside mail stays unverified, the agent holds its key and the broker only verifies (P16). (authorship_signing)
- **Q09** A sender's retry after the broker restarted between minting an id and the sender reading the reply gets a second id for the same message, which R16 can't catch. Should the submission carry the sender's own token, echoed back, so a broker recognizes a retry? Deferred to a follow-up by the host-side maintainer, who raised it (P28). (retry_after_restart_second_id)

## 14 Deliberation Record

The operator convened the deliberation on #850 on 2026-10-28 at 02:18Z, for 72 hours, and it closed on 2026-10-31 at 02:18Z (22:18 EDT on 2026-10-30). The same day it opened, the operator suspended it pending the two prototypes (P17), and both reported before the close (P24 to P29). The Secretary's synthesis ([6543897092](https://github.com/cversek/MacEff/issues/850#issuecomment-6543897092)) quotes each position and proposes revise.

- **P01** The container-management maintainer, [6459064091](https://github.com/cversek/MacEff/issues/850#issuecomment-6459064091): revise; split the processes by account; pulled hand-off; a declared peer list; the sweep as health; receipts; section 10 as a list. (thm_split_by_account)
- **P02** The host-side maintainer, [6468749316](https://github.com/cversek/MacEff/issues/850#issuecomment-6468749316): revise; Q02's (a); egress matched by socket owner; the job's environment; raised kept apart from delivered. (ira_own_login_for_reachable)
- **P03** The container-management maintainer, [6469306930](https://github.com/cversek/MacEff/issues/850#issuecomment-6469306930): withdraws ancestry as a boundary; egress as an allow-list. (thm_allow_list_egress)
- **P04** The operator, [6471946844](https://github.com/cversek/MacEff/issues/850#issuecomment-6471946844): a MacEff system daemon as a second locus, in its own MIS; no standalone broker per system. (owner_system_daemon)
- **P05** The head maintainer, [6472809029](https://github.com/cversek/MacEff/issues/850#issuecomment-6472809029): revise; rung from a declared map; address from the identity file; a working broker first; landing by area; the system daemon as supervisor; MIS-0006's model at the system daemon. (hm_declared_map)
- **P06** The operator, [6473365744](https://github.com/cversek/MacEff/issues/850#issuecomment-6473365744): why not one broker per system daemon? (owner_one_broker_question)
- **P07** The head maintainer, [6474037117](https://github.com/cversek/MacEff/issues/850#issuecomment-6474037117): a broker per system may win; Q06 opened, with its crux. (hm_q06_crux)
- **P08** The host-side maintainer, [6475350267](https://github.com/cversek/MacEff/issues/850#issuecomment-6475350267): persuaded, one broker per system; a placement rule. (ira_broker_per_system)
- **P09** The container-management maintainer, [6475537319](https://github.com/cversek/MacEff/issues/850#issuecomment-6475537319): persuaded, with four conditions; the outside watch stays outside; root only supervises; two placement questions; the container first. (thm_four_conditions)
- **P10** The head maintainer, [6476069492](https://github.com/cversek/MacEff/issues/850#issuecomment-6476069492): three withdrawals; quarantine; a versioned socket; a third placement question; a model that keeps no input. (hm_mid_window)
- **P11** Seat L, relayed by the container-management maintainer, [6476228404](https://github.com/cversek/MacEff/issues/850#issuecomment-6476228404): quotas counted in doorbells; a stuck recipient's age; "recipient offline" in receipts. (seat_l_doorbells)
- **P12** Seat K, relayed, [6476228830](https://github.com/cversek/MacEff/issues/850#issuecomment-6476228830): intake collisions; one id; notices that can be acted on as written. (seat_k_collisions)
- **P13** Seat M, relayed, [6476229281](https://github.com/cversek/MacEff/issues/850#issuecomment-6476229281): a typed notice is input; new since the last read; root's closed list; a pinned trust bundle. (seat_m_typed_notice)
- **P14** Seat N, relayed, [6476229730](https://github.com/cversek/MacEff/issues/850#issuecomment-6476229730): replay, miss and race on the notice path; a stuck recipient; parent the primal daemon; origin from the peer uid. (seat_n_notice_path)
- **P15** The container-management maintainer, [6476259000](https://github.com/cversek/MacEff/issues/850#issuecomment-6476259000): where the seats' findings go. (thm_seat_findings)
- **P16** The host-side maintainer, [6476909402](https://github.com/cversek/MacEff/issues/850#issuecomment-6476909402): two withdrawals; a level-triggered doorbell; a macOS spike early; a stop per platform. (ira_level_triggered)
- **P17** The operator, [6477160351](https://github.com/cversek/MacEff/issues/850#issuecomment-6477160351): suspend pending two prototypes; the Secretary revises the draft; the system daemon in a separate draft MIS, with the head maintainer as its Secretary. (owner_suspend_for_prototypes)
- **P18** The container-management maintainer, [6479561476](https://github.com/cversek/MacEff/issues/850#issuecomment-6479561476): Seat M's slug confirmed; seven places the drafts would freeze the wrong interface; how the container prototype runs. (thm_freeze_points)
- **P19** The host-side maintainer, [6481387490](https://github.com/cversek/MacEff/issues/850#issuecomment-6481387490): on macOS launchd parents every job; the human accounts R33 admits, and who loads the rule; Q07 answered; the loopback cost; a common declaration schema. (ira_macos_facts_and_schema)
- **P20** The container-management maintainer, [6481618179](https://github.com/cversek/MacEff/issues/850#issuecomment-6481618179): the schema accepted with five amendments; R33, Q07 and the loopback agreed; the receiver checks the owner. (thm_schema_amendments)
- **P21** The host-side maintainer, [6482319998](https://github.com/cversek/MacEff/issues/850#issuecomment-6482319998): a box directory's group on macOS; a hard link passes the owner check, so the link count must be one. (ira_link_count)
- **P22** The container-management maintainer, [6482591977](https://github.com/cversek/MacEff/issues/850#issuecomment-6482591977): both agreed; the broker writes one copy per recipient. (thm_one_copy_per_recipient)
- **P23** The host-side maintainer, [6496466005](https://github.com/cversek/MacEff/issues/850#issuecomment-6496466005): neither revision misreads him; MIS-0007's Guide should follow the schema; R20's shutdown order on macOS is untested. (ira_no_misreading)
- **P24** The container-management maintainer, [6510997994](https://github.com/cversek/MacEff/issues/850#issuecomment-6510997994): the container prototype's first report, on MIS-0007; root can't read a unit's marker, so a supervisor per unit stops it. (thm_container_report_sd)
- **P25** The host-side maintainer, [6515533280](https://github.com/cversek/MacEff/issues/850#issuecomment-6515533280): the macOS prototype's first report; R05 isolates only with three conditions; R29 needs the transcript's turn. (ira_macos_report_one)
- **P26** The container-management maintainer, [6522832199](https://github.com/cversek/MacEff/issues/850#issuecomment-6522832199): the container prototype's second report, on MIS-0004; the kernel-enforced parts hold; R37, R16 and R32 not met by today's code; R15 needs a decision. (thm_container_report_mail)
- **P27** The container-management maintainer, [6537147162](https://github.com/cversek/MacEff/issues/850#issuecomment-6537147162): the operator's choice for R15, "from the broker's acceptance", relayed with proposed text; the three receiver changes opened now. (thm_r15_from_acceptance)
- **P28** The host-side maintainer, [6538045269](https://github.com/cversek/MacEff/issues/850#issuecomment-6538045269): R15 agreed as worded; a retry after a restart gets a second id, left as a follow-up. (ira_r15_agreed)
- **P29** The host-side maintainer, [6538604020](https://github.com/cversek/MacEff/issues/850#issuecomment-6538604020): the macOS prototype's second report; R29 safe as specified with two liveness gaps and two wording needs; R33 holds; launchd doesn't stop what a job started; R05's launchd footprint. (ira_macos_report_two)
- **P30** The operator, review [5723927799](https://github.com/cversek/MacEff/pull/520#pullrequestreview-5723927799) on #520, after the close: R15 approved as worded; signing required for every MacEff agent before the revision is approved; R41, R42, R44 and R45 proposed, and R43, dropped from the posted review by mistake, carried in at the operator's word on 2026-10-31. (owner_signing_required)
- **P31** The container-management maintainer, [6546702449](https://github.com/cversek/MacEff/pull/520#issuecomment-6546702449) on #520: agrees; most of the mechanism exists; declare before enforcing; the registry in the system declaration; R44 by registered address; no attestation for an unsigned local submission; retired keys with validity dates; Q08 answered. (thm_signing_notes)
- **P32** The host-side maintainer, [6546744158](https://github.com/cversek/MacEff/pull/520#issuecomment-6546744158) on #520: agrees with P31; a 0600 key file, not the keychain or the Secure Enclave; the registry names each key's account; rotation's order and triggers; validity checked against R15's acceptance time. (ira_signing_custody)

**Objections**
- **O01** Seat M: "My objection is to how mail reaches a session, which this deliberation hasn't named." A notice typed into a terminal is input, not a notification (P13). R26, R29, R39 and R40 answer it in this draft, and the operator answers it in the Resolution. Seat M confirmed the slug through its host agent (P18; MIS-0001-R46 (objection_slug_MUST_come_from_objector)). (notice_typed_is_input)

## 15 Revision History

- 2026-10-06: first draft, a skeleton opened by the Secretary. Summary, Motivation and Goals come from the authors' first exchange of 2026-10-05.
- 2026-10-06: the operator confirmed on this pull request the Secretary designation and the four rulings relayed by the host-side maintainer; Goals now say so.
- 2026-10-28: the operator opened the deliberation on #850, for 72 hours; Status is Deliberation.
- 2026-10-28: the operator suspended the deliberation pending two prototypes. The operator moved that the Secretary gather preliminary requirements from all positions into a revised draft, and, by an addendum, that the system daemon's requirements go into a separate draft MIS as a direct dependency (#850, comment 6477160351). This revision is that draft.
  - The title and the second change now say one broker per system.
  - R01 to R35 are preliminary, each one assigned in section 12.
  - Q01 to Q05 carry preliminary answers, and Q06 to Q08 are new.
  - MIS-0002-R56 is carried in.
  - It is the working specification for the prototypes until the final draft.
- 2026-10-29: the corrections both authors agreed on #850 after the first revision (P18 to P22), folded in by the Secretary while the deliberation stays suspended.
  - R13 lets the recipient's group remove what it has ingested, R19's interval moves to the recipient's notifier, R22's delivered is confirmed in the session's transcript, R32 also alerts on the oldest unread message, and R33 admits the human accounts the operator declares.
  - R36 to R38 are new: message files no group can write, the receiver's owner and link-count check, and one copy per recipient.
  - Q07 is answered and O01's slug is confirmed. Sections 9 and 10 gain the container's egress capability, the shared-login limit and the loopback cost.
- 2026-10-31: the synthesis revision, by the Secretary, after the deliberation closed and both prototypes reported (P23 to P29). The Status is Final-Comment.
  - R15 now runs from the broker's acceptance, and its slug becomes message_id_MUST_be_one_from_acceptance, the authors' (P27, P28).
  - R29 adds the transcript's last turn to its signals. R39 (read the box back) and R40 (no leading digit) are new, from the macOS catalog (P29).
  - Section 10's R05 cost gains the macOS conditions and the launchd user domain (P25, P29). Section 12.1 records what each prototype showed and left untested, and 12.4 the three receiver pull requests. Q09 is new and deferred (P28).
- 2026-10-31: signing, at the operator's review (P30), with both authors' notes (P31, P32), folded in by the Secretary. Section 6.10 is new: R41 to R45 from the review, R43 carried in at the operator's word after it dropped from the posted text by mistake, and R46 new from P32. R42 names the account that holds each key, R44 is keyed to registered sender addresses, and R45 checks validity against R15's acceptance time. Q08 is answered; the Goals, Non-Goals, Guide, Terms, section 10 and section 12.4 follow. A requirement changed during Final-Comment, so the final comment period starts again.

## Wiki-Links

[[amail]] [[supervision]] [[capability_boundaries]] [[mis]]
