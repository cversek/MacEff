# Consuming amail from the base image

**Who this is for**: someone bringing agent mail up on a *new* deployment.

The base image carries the whole amail runtime. A deployment gets it by
**declaring configuration and supplying secrets** — not by copying files. If you
find yourself copying a Python file out of another deployment, something in this
document is wrong and it is worth saying so rather than working around it.

> **Why this document exists in the base repo.** The first deployment worked for
> weeks with its runtime sitting next to it, which demonstrated nothing about
> whether a *second* one could consume the same base. It also accumulated seven
> load-bearing things that nothing declared — each placed by hand in a moment
> when placing it by hand was the obviously right thing to do, and each of which
> an ordinary teardown would have destroyed. The checklist below is that list,
> made declarative. It is exhaustive because it was assembled by destroying a
> working deployment and recording what failed to come back, not by remembering.

---

## The split

| | provides |
|---|---|
| **base image** | every runtime component, as importable package modules; the accounts; the store directories and their modes; the startup sequence |
| **deployment** | two config files, the secrets, the transport identity, and the accounts' *declarations* |

The runtime is `macf.amail.daemons.*` — package modules, not scripts in a
directory. That is deliberate: they are reached by `python -m`, so a fix to one
of them is a **restart**, not an image rebuild. Do not vendor them.

---

## What the base provides

**Daemons**, all invoked as `python -m macf.amail.daemons.<name>`:

| module | role |
|---|---|
| `broker` | authorizes and serves the agent-facing socket. **Refuses to run as root** — the pickup-box model needs no privilege on the mail path, so a root broker is a regression the entry point makes structurally impossible |
| `inbound` | the spool consumer and its supervisors; see the verb table below |
| `receiver` | the origin gate: validates the inbound assertion, verifies the payload hash, writes the spool |

**`inbound` verbs**, deliberately separated so an operator can drive an
acceptance battery step by step rather than firing one at a side effect:

| verb | does |
|---|---|
| `check` | validate config and push-grant eligibility; confirm the spool is *consumable* (writable — a check that validates everything except the mutating permission reports green on a consumer that cannot consume) |
| `validate` | check the configuration the deployment obeys, touching nothing. **`--contacts <path>` validates a CANDIDATE** that is not installed yet, so the sequence is validate-then-replace |
| `process` | drain the spool once |
| `watch` | unattended mode: `process` on an interval, publishing a heartbeat |
| `watchdog` | **a separate process** that ages the watcher's heartbeat and sweeps orphans |
| `health` | one-shot verdict over both heartbeats and the sweep; **non-zero when unhealthy** |
| `sweep` | the orphan sweep alone; non-zero on any alert |
| `reconcile` | conservation: spooled == terminals + in-flight |

**Provisioning** (`start.py`, runs at container start): creates the socket
directory, the ingest ledger directory, and the store directories with their
modes; starts broker, watcher, watchdog, receiver and the tunnel; and **verifies
each is still running a moment after launching it**, reporting "started and
STILL RUNNING (pid N)" or "started and EXITED IMMEDIATELY (rc N)". A launch is
not a life, and this log line used to claim one while the process was already
dead.

---

## What a deployment must supply

### 1. Two config files

Both are YAML, both validated by Pydantic with `extra="forbid"` — an unknown key
**refuses to start** rather than being ignored, because an ignored key in a
security config silently changes what the broker enforces.

- **broker config** → `/etc/amail/broker_config.yaml` (root-owned; it is
  configuration the broker *obeys*, so the broker must not be able to rewrite
  its own authority)
- **inbound config** → `/etc/amail/inbound_config.yaml`

Declare `requires_macf` in both. It is compared *before* the fields are, so a
container running a package older than its configuration says exactly that —
instead of rejecting every newer key as unknown, which reads like a config bug
and sends you to edit a file that is correct.

### 2. The addressing file

Who exists, who they may correspond with, and **which direction**
(`inbound` / `outbound` / `both` / `neither`). `neither` is a revocation
*record*, not an absence — it says this correspondent was permitted and no
longer is, which makes an attempt against it a near-zero-false-positive signal.

Broker-owned, **agent-readable (0644)**: an agent must be able to see which
destinations it may write to without a socket call, because a boundary an agent
cannot see is discoverable only by tripping it.

**Never committed.** It is a map of who this system corresponds with.

### 3. Accounts

Two, declared so provisioning creates them:

- a **broker** uid — owns the stores and the authorization files
- a **receiver** uid — accepts inbound mail and is the sole *writer* of the
  spool. Deliberately not the broker: the receiver is the process an attacker
  reaches first, so it holds no credential the broker holds and cannot read the
  broker's stores

Declare each agent by **`account`**, not by `uid`. The uid is resolved from the
account database, and a declared uid that disagrees **refuses startup** — the
uid table *is* the authentication table, so a transcribed number that drifts
authenticates the wrong principal with correct-looking audit entries.

### 4. Secrets, declared rather than placed

Every one of these was once placed by hand and would have been destroyed by a
teardown. Declaring them means a **declared-but-absent secret refuses to
start**, which is the property that makes the list checkable.

| secret | owner | mode | note |
|---|---|---|---|
| submission credential | broker | 0600 | compromise sends mail as the whole domain; the property reduces entirely to custody, since the broker legitimately reaches the network |
| addressing file | broker | 0644 | see above |
| receiver environment | receiver | 0600 | the transport identity: with it an attacker knows what to forge against |
| tunnel credential | root | 0600 | **the least replaceable thing in a deployment.** If it was created locally it has never transited, which is a good property that also means nothing on this side can reissue it |
| tunnel config | root | 0644 | policy the tunnel obeys; nothing in it is secret |

### 5. Transport

The edge components — the mail router, the Worker, the tunnel hostname — are
deployment identity and stay with the deployment. The base makes no assumption
about them beyond the receiver's contract.

---

## Order of operations

1. Declare the accounts and secrets; bring the container up
2. `inbound validate` — the configs parse, and every agent named in the
   addressing file is one the deployment defines
3. `inbound check` — push-grant eligibility, and the spool is *consumable*
4. `inbound health` — both heartbeats and the sweep
5. Send one message in and watch it reach a mailbox

Steps 2–4 are cheap and each fails differently. Run them in order; a failure at
2 makes 3 and 4 meaningless.

---

## Verifying it, which means breaking it

Every claim here is about what happens when something fails, and **reading only
ever shows you the system that has not failed.** Each of these has been
demonstrated; run them again on a new deployment rather than assuming they
carried over.

| break | expect |
|---|---|
| declare an agent whose account does not exist | broker refuses to start, naming the account |
| declare `requires_macf` above the installed version | refuses, naming the pin — **not** an unknown-key error |
| corrupt the addressing file | broker keeps serving and **refuses every send** (fail-closed), audited with the sender, and recovers with no restart when repaired. The watcher survives it and reports itself FAILING |
| kill the watcher | the watchdog alarms within its interval, naming the dead pid |
| leave an entry in the spool past the bound | the receiver alarms that its spool is not draining, and **keeps accepting** |
| stop the container | the host-side gate reports UNREACHABLE — distinct from unhealthy, because nothing was measured |

Pair every one with its acceptance. A refusal with no matching acceptance proves
only that the code path can raise, not that it discriminates.

---

## Two deployments on one machine (a host and a container): rung 1s

A host broker and a container broker on the same machine share a filesystem
through a bind mount, and the spec's rung 1s (`amail.md` §2.1.1) delivers
between them broker-to-broker over that mount. Nothing about addressing or
contacts changes; a deployment adopts the rung with **one declaration and one
mount**, in each direction it wants.

**The declaration**, in `broker_config.yaml`, keyed by the peer's mail domain:

```yaml
shared_handoffs:
  box.local:                       # the container deployment's domain
    handoff: /srv/box/amail/handoff  # its inbound_handoff, as mounted HERE
    uid: 100999                      # owner of its intake, as this kernel sees it
    gid: 101005                      # group of its intake, as this kernel sees it
    note: "container 'box', compose service amail, mounted at /srv/box/amail"
shared_sweep_seconds: 5            # how often this broker reads its OWN intake
```

**The mount.** Each side's `inbound_handoff` root is visible to the other:
`-v /srv/box/amail/handoff:/var/lib/amail/handoff` gives the host the
container's root at `/srv/box/amail/handoff`, and a second mount gives the
container the host's root. One mount per direction; a single shared root that
holds both deployments' trees also works.

**What each side provisions, for the other to write into.** Under its own
root, `_peers/<peer domain>/`: owner its own broker, group the **writer's
primary gid** as this kernel sees it, mode 2770. The primary, not "a group the
writer belongs to": `start.py` launches brokers with `setpriv --clear-groups`,
so a broker holds only its primary gid and nothing can be arranged through
supplementary membership on either side. The writer creates pairs **0644**
inside it (the directory is 2770, so the wider file mode exposes nothing to
anyone who cannot already enter it), which is what lets the owner read files
it does not own with its groups cleared. A default ACL granting the owner
read (`setfacl -d -m u:<owner>:r-- <intake>`) is the equivalent when a
deployment prefers 0640 files. The writing broker never creates the
directory (§2.3: a box created from the wrong side is unreadable by its
owner, silently); an absent intake refuses the send and names the path. The
`uid`/`gid` in the declaration are what the writer **verifies** before every
write — the mount's id mapping, which is why they are numbers as seen from the
writer's side, not the peer's. Found on the second deployment: with 0640
pairs the sweep reported `unreadable pair: [Errno 13]` on every pass.

**What happens on a send.** The sender's broker checks the sender's contacts
(unchanged), then writes sidecar + `.amsg` into the peer's intake with
`rung: shared` and `origin_domain`. The peer's broker sweeps its intake on
`shared_sweep_seconds`, verifies the pair (hash, sender under the intake's
domain, recipient one of its own agents), and accepts it through the same
inbound path internet mail takes: its contacts, its keys, its quarantine, its
audit, its hand-off into the recipient's pickup box as rung 1. The recipient's
next `amail list` ingests as before. Rejected pairs go to `<intake>/rejected/`
with the reason; refused senders go to the quarantine, as they always have.

**A host-side broker.** The host needs a broker for its agents to reach the
socket. The same daemon runs on the host from a host config (`AMAIL_BROKER_CONFIG`
pointing at it, a socket path under the agent's home rather than `/run/amail`).
When a host deployment sets `autostart: true` and `broker_config` in the
agent's `~/.maceff/amail.json`, the client starts the daemon on first use if
nothing answers on the socket. **Say what that is:** a broker the agent's own
client launched, as the agent's uid, unsupervised. It is not the boundary the
spec's broker is against that agent — it is the same code path (gate, rate
limit, audit, ledger, ladder) so host mail is handled by the same rules, and
the container's own broker still enforces its own contacts on what arrives.
`amail status` labels it `agent-launched`, and the daemon's banner says so. A
host deployment whose agents share one uid needs a claimed-identity rule this
document does not yet carry; until it does, one host agent per uid.

**Verifying it, which means breaking it** — pair each with its acceptance:

| break | expect |
|---|---|
| remove the peer's `_peers/<your domain>/` | your send refuses, naming the path; nothing is created across the mount |
| declare a `gid` one off from the mount's | refused with both numbers side by side; nothing written |
| launch the receiving broker with its groups cleared and write 0640 pairs | every sweep reports `unreadable pair`; the 0644 pair mode is what makes the happy path work |
| declare an agent key in mixed case | its address still resolves; the local part is case-insensitive and the lookup folds |
| a pair in `_peers/x.local/` whose sender is under `y.local` | rejected into `rejected/` by the receiving broker, audited; nothing reaches a box |
| a `_peers/<undeclared domain>/` directory | left unread and named on stderr; never consumed |
| recipient's book lacks the sender | delivered into the peer's intake, then quarantined on the peer's side; the sender's ledger says delivered (custody passed to the peer broker), the peer's audit says quarantined |

## Supervision, and where it ends

Read `service_supervision.md` (`macf_tools policy read service_supervision`) —
it is the general rule and this subsystem is only its first consumer.

The short version: the watcher is supervised by the watchdog, which runs **in a
separate process** because a supervisor sharing a fate with its subject is not a
supervisor. The watchdog publishes its own heartbeat, and `inbound health`
covers both. **The chain does not terminate inside the container** — supervision
inside a deployment cannot report that the deployment is gone, so a deployment
owes an external check on a schedule whose failure reaches a person. A record
that merely persists is not a terminus unless someone reads it, and that is an
empirical question about your host, not a property of the mechanism.

---

## Known debts

- **The second deployment is the test of all of this**, and until one exists,
  "a deployment consumes the base by declaring config" is a claim rather than a
  measurement. If you are that second deployment: what you had to do that is not
  written above is the finding, and it belongs back in this file.
- The external health gate is currently deployment-supplied rather than provided
  by the base.
- Push-wake is specified and not built; it ships disabled, and enabling it is a
  deliberate deployment act rather than a side effect of granting a contact.
