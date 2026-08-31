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
