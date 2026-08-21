# amail ingest — the inbound mail path (transport layer)

Internet mail for this deployment's agents arrives by:

    sender -> Cloudflare MX -> Email Routing rule -> Email Worker (courier,
    authenticates with a service token) -> Cloudflare Access (edge gate)
    -> Cloudflare Tunnel -> receiver (origin gate: validates the Access
    JWT, verifies payload hash) -> spool (broker's input)

Design authority: the amail Inbound System Specification (agent design
record; merging into the MacEff amail policy after peer review). This
directory holds the deployment-side transport components only — the broker
that consumes the spool and the agent-facing client are implemented in the
MacEff submodule (`macf.amail`).

## Components

| file | role |
|---|---|
| `amail_inbound_worker_tunnel.js` | Email Worker source (pasted in the dashboard). Courier, not a guard: no trust decisions, observations marked `trusted:false`, fail-closed on every error path. Size cap 5 MB — a deliberate operator routing choice (large material arrives as links), not a platform limit. |
| `worker_tunnel_test.js` | Worker test suite (`bun run worker_tunnel_test.js`), incl. a control on the harness itself. |
| `amail_ingest_receiver.py` | Origin gate + spooler, runs in-container. Validates `Cf-Access-Jwt-Assertion` against the team JWKS (RS256 + audience pinned, optional `INGEST_PIN_COMMON_NAME`), recomputes payload sha256, dedupes MTA retries, spools 0700/0600. Refuses to start unverifiable. Config: `receiver.env` (container-local, not committed). |
| `test_ingest_receiver.py` | Receiver suite: offline JWKS + local RSA keypair, known-answer case FIRST, single-variable refusals incl. alg-confusion. |
| `cloudflared-config.yml` | Tunnel ingress template (single-level hostname — Universal SSL stops one level deep; two-level names fail TLS at the edge). |
| `bring_up_tunnel.sh` | Step-gated bring-up runbook: check / login / create / route / run. The route step refuses until the Access gate covers the hostname (gate before door). |
| `ingest_gate_probe.py` | Scheduled negative control + token-age alarm. INTERIM FORM: runs from the operator host's cron with `MACF_ALERT_TASK_ID` injected; provisioned scheduling is owed (see debts). |
| `run_inbound.py` | Spool consumer entry point (unprivileged, broker uid). Verbs `check` / `process` / `reconcile`, deliberately separate so the operator fires each acceptance step himself. Config: `/etc/amail/inbound_config.json`. |
| `run_broker.py` | Broker daemon entry point (unprivileged, broker uid; REFUSES to run as root — the pickup-box model needs no privilege on the mail path, so a root broker is a regression this file makes structurally impossible). Config: `/etc/amail/broker_config.json`, validated by `macf.amail.deploy_config.BrokerDeployConfig` (Pydantic, unknown keys refuse to start). Replaced the hand-launched root testbed broker on 2026-08-18. NOTE: the broker's own custody checks require the contacts file AND its directory to be owned by the broker uid, so contacts live at `/var/lib/amail_broker/contacts.json`, not under `/etc/amail/`. |

## Standing security notes

- **Trust from ownership, never from string shape or transport reachability.**
  The receiver trusts only the JWT it verifies; the broker trusts only the
  spool that a single dedicated uid can write; wake authenticity (when built)
  comes from a broker-owned file, not from what a message looks like.
- **The gate probe is load-bearing, not optional**: the edge retains logs
  for only 24h, so the scheduled probe is the only continuing evidence the
  Access gate holds. Its alarm channel must never fail silently (undelivered
  alerts land in `UNDELIVERED_ALERTS.log` + the cron log).
- **Token lifetime is the only bound on an unnoticed credential leak.** The
  production token is 1-year with two independent expiry alarms; at rotation,
  while two tokens are briefly alive, run the cross-token check (old token
  must be refused once the policy names only the new one) — the named-token
  narrowing is otherwise verified only against constructible negatives.
- **The broker must never fetch links automatically.** Large material
  arrives as links by design, and a link from an unverified sender is
  SSRF-shaped input aimed at whatever the broker can reach. Fetching is a
  deliberate, allowlist-gated act, never an ingestion step.
- **The Worker has no fetch handler, deliberately.** A debug/simulation
  handler would be an injection vector for fabricated mail; the component's
  security rests on having exactly one trigger. The workers.dev route should
  be deleted rather than decorated (pending, dashboard-side).

## Recorded debts (before this system is declared 1.0)

1. ~~Receiver runs as a container sudoer uid~~ PAID 2026-08-17: dedicated
   `amail_ingest` system uid (nologin, no sudo, no extra groups) owns the
   state and runs the receiver. The `useradd` itself is a runtime act —
   its Dockerfile provisioning rides with debt 3.
2. Gate probe scheduling is manual host-cron — owed deployment-managed
   provisioning.
3. Runtime installs owed Dockerfile entries: PyJWT into the venv build,
   and the `amail_ingest` / `amail_broker` user creation (cloudflared is
   already in the Dockerfile).
4. workers.dev route deletion + Worker console logging (dashboard-side).
5. Daemon supervision is bare `setsid` + a log file, for the receiver and
   the broker both — owed a real supervisor (restart-on-exit, start at
   container boot). Until then a died daemon is only visible because
   `amail status` names an unreachable broker loudly.
6. The in-container `/opt/macf_tools` source tree is synced by hand
   (docker cp) from the MacEff branch — owed either an editable install
   against the submodule path or an image-build copy, so a code advance
   cannot silently diverge from the pinned submodule.

## Provisioning requirements (root, at deploy time)

Setup is not the mail path, so privilege here does not violate the
no-privileged-component property. What runs on the mail path — receiver,
broker, recipient — is unprivileged throughout.

- The `amail_ingest` and `amail_broker` uids exist; the broker owns its
  audit, quarantine, handoff and socket directories.
- The spool is mode **2770**, group `amail_broker`. Group *read* is not
  enough: consuming a spool means removing the entry at terminal
  disposition, which needs directory write.
- **Each pickup box `handoff/<agent>/` is broker-owned, group = the
  recipient's group, mode 2770.** This is required, not optional. The
  broker is unprivileged and cannot `chgrp` into a group it does not
  belong to, so a box it auto-creates carries the *broker's* group and the
  recipient cannot read its own mail. The first live agent-to-agent
  delivery failed exactly this way: submission reported success, the box
  held the message, and the recipient's pull found nothing.
- The contacts file is broker-**owned** and agent-**readable**. Readable is
  what lets a recipient verify signatures at ingest with no broker round
  trip (so custody survives the broker being down); owned-by-broker is what
  stops an agent rewriting its own allowlist.

## Prototyping rule

Experimental instruments do NOT live in this repo. Prototypes are developed
as Experiment CAs in the agent tree (protocol + data + analysis), and only
worked-out permanent components land here. The measurement stub that
validated this design lives on as an experiment record, not as code.
