# Agent Harness — The Supervised Session, and the Name It Answers To

**Breadcrumb**: s_1afd4d78/c_12/p_04343b94/t_1786152911
**Type**: Infrastructure (opt-in)
**Scope**: All agents that run supervised, and the deployments that provision them
**Status**: ACTIVE
**Version**: 1.0

---

## Purpose

The **harness** is what makes an agent session outlive the terminal that started
it: a systemd user unit creates a tmux session, tmux runs `macf.supervisor`, and
the supervisor runs the client through a child wrapper that restarts it in place.
Detach, reboot, client crash, and deliberate restart all survive it. Unattended
autonomous operation is not possible without one.

This policy exists because the harness fails in a particular way. **It does not
crash. It reports success and does nothing** — or it comes up degraded in a
configuration no surface displays. Every rule below was written after a failure
that produced no error message, and the rules are stated with what they cost so
the next deployment does not pay again.

**Core Insight**: the harness is *identity infrastructure*, not just process
supervision. What names the session determines who can find it, whether a status
check can resolve its own subject, and whether "is it running" has an answer.

---

## CEP Navigation Guide

**1 What the Harness Is**
- What are the four layers and which one supervises which?
- Why is the systemd unit `oneshot` when it manages a long-lived session?
- What does `stop` have to stop, and why is the obvious answer wrong?

**2 Identity and Naming**
- What names the tmux session and the systemd unit?
- How do I get from a Calling Card to a session name, and back?
- Which characters are substituted, and which of those are actual constraints?
- What happens when two agents map to the same identifier?
- Why is what I *type* a different identifier from what the machine *names*?

**3 Establishing That the Harness Is Up**
- Why isn't `tmux has-session` an answer?
- Why isn't `pgrep` for the supervisor an answer either?
- What is the authoritative signal?
- Why must every tmux target be written `=name`?

**4 Invariants That Cost Incidents**
- Why must the base URL and the first-party flag never be separated?
- Why does the launch decision live in exactly one script?
- What must a command started under tmux state explicitly?

**5 For a Deployment**
- What must I install, and in what order?
- What must I not hand-edit?
- How do I verify the harness rather than assume it?

**6 Scope**
- One session per identity — why, and what is deferred?

---

## 1 What the Harness Is

Four layers, each supervising the next:

| layer | responsibility |
|---|---|
| systemd user unit | create the session at boot, once |
| tmux | own the session so a detached client survives |
| `macf.supervisor` | own the client process and restart it in place |
| child wrapper | resume with `-c`, restore channels, answer the trust prompt |

The unit is `Type=oneshot` with `RemainAfterExit=yes` because **its job is to
create the session, not to be the session.** A `Restart=` here would fight the
supervisor, which is the component that actually owns the client.

For the same reason, **stopping the harness means stopping the SUPERVISOR.**
Killing the child is not a stop — the supervisor simply restarts it. A stop that
targets the child is a restart with extra steps.

---

## 2 Identity and Naming

### 2.1 The session identifier derives from the Calling Card

The tmux session, the systemd unit and the supervisor instance are all named by
one **session identifier**, and it is a pure function of the agent's Calling
Card:

```
TheHarborMaster@ee5cd8   ->   TheHarborMaster_ee5cd8
```

`macf.utils.identity.session_identifier()` computes it;
`calling_card_from_identifier()` reverses it.

Before this, the harness used a nickname that appeared nowhere else in the
framework. That made session management **a second, unregistered namespace**: an
operator holding the Calling Card could not derive the session name, a tool
holding the session name could not recover the agent, and `harness status` had no
default it could resolve — so it guessed, printed `ABSENT`, and read as *there is
no harness here* while a healthy harness ran under another name.

**A default reported as a resolution is a lie the reader cannot detect.** Any
surface that falls back to a default must say that it did.

### 2.2 Which characters are substituted, and why each

Measured, not assumed (tmux 3.6 / systemd 257, 2026-08-07):

| char | tmux | systemd | verdict |
|---|---|---|---|
| `.` | **silently rewritten to `_`** at session creation | fine | **constraint** |
| `:` | **silently rewritten to `_`** | rejected: "Couldn't process aliases" | **constraint** |
| `/`, space, tab | unsafe | unsafe | **constraint** |
| `@` | kept verbatim, addresses correctly | enables, symlinks, starts, reports active | **convention** |
| `-`, `_` | fine | fine | kept |

The `.` and `:` cases are the reason substitution exists at all, and they show the
harness's signature failure shape: `tmux new-session` **succeeds**, reports no
error, and stores a different name — so every later `-t` lookup silently misses.

`@` is different and the difference is recorded deliberately. It is **not** a
constraint: a concrete unit named `cc-harness-Name@abc123.service` enables,
symlinks into `default.target.wants`, starts and reports `is-active`. It is
substituted by **convention**, because `@` is how systemd spells a template
instance and a concrete unit wearing that shape misleads both people and tooling.

> An earlier write-up of this work asserted that `@` had to be substituted *for
> systemd's sake*. Measurement refuted it. The distinction is kept in the policy
> because a convention can be revisited and a constraint cannot, and a reader who
> cannot tell them apart will treat both as immovable.

### 2.3 Collisions

Two Calling Cards differing only in a substituted character map to one
identifier. This is **not resolved by the substitution** — it is made harmless
downstream: a resolver that finds several candidate harnesses **lists them and
refuses to choose**. The six-hex suffix comes from a UUID, so a real collision
needs two monikers differing only by punctuation *and* a shared UUID prefix.

### 2.4 Two identifiers, on purpose

What the machine **names** and what an operator **types** are separate:

- `agent` — the session identifier. Traceable to an identity. Long.
- `shell_prefix` — the handle in the generated shell functions
  (`maceff_<prefix>_harness_launch`). Short. Defaults to the moniker.

Forcing one identifier to serve both is what produced the untraceable nickname in
the first place. **Traceability is a property the tools need; brevity is a
property the hand needs.** Do not collapse them.

---

## 3 Establishing That the Harness Is Up

Three checks, two of which are wrong, and both wrong ones look right.

**`tmux has-session -t <name>` — wrong.** It proves a session *by that name*
exists, not that it is yours. An unrelated ssh login once owned the name; the
guard matched, launch attached to a shell, and the harness stayed down for nine
days with nothing logged, because a session really did exist.

**`pgrep -f 'macf.supervisor ... --name <agent>'` — also wrong**, and worse
because it looks like a real check. When tmux starts a server it keeps the
command it was asked to run **in its own argv**. So this matches the tmux server
and reports a live supervisor for as long as the server lives — nine days after
the supervisor exited, when measured.

**Authoritative**: the supervisor's own registry, which is keyed by the
supervisor's pid, then confirmed against the process table:

1. a registry entry for this agent with `status: running`, and
2. `kill -0 <pid>` — entries outlive their processes, and
3. `ps -o args= -p <pid>` still shows a supervisor — pids get recycled.

### 3.1 Every tmux target must be written `=name`

**tmux resolves `-t` targets by PREFIX.** `-t thm` matches a session called
`thm-stale-ssh`. This is not academic: renaming the imposter out of the way is
exactly the remedy an operator reaches for, and it **does not free the name** —
the harness kept reporting its session "up" for nine days after the only session
by that prefix had been renamed and handed to an ssh login.

Write `-t =name` everywhere: `has-session`, `attach`, `send-keys`, and in any
advice printed for a human to type. Loose advice teaches the loose form.

Short identifiers make this worse — a three-character slug is a prefix of almost
anything — which is a second, independent reason to derive names from the Calling
Card.

---

## 4 Invariants That Cost Incidents

**The base URL and the first-party flag are one assignment.** Whenever
`ANTHROPIC_BASE_URL` points at a host that is not `api.anthropic.com`, the client
stops extending the long-context window and falls back to 200K — silently, while
every UI surface keeps displaying the full window. `_CLAUDE_CODE_ASSUME_FIRST_
PARTY_BASE_URL=1` is what prevents it. Emitting them in separate places is how a
months-long "compacts early" mystery survived, and later how a terminal-launched
harness ran at a fifth of its reported capacity for a week.

**The launch decision lives in exactly one script.** systemd and the operator's
shell both call it. When they each carried a copy, the copies drifted, and the
drift was the missing flag above. One implementation cannot disagree with itself.

**A command started under tmux inherits nothing you can rely on.** It runs under
the tmux *server*, which may have been created days earlier by an unrelated
login. Interpreter path, `PATH`, and context window must be stated in the command
string. Verified: an exported variable in the launching shell did not arrive.

**Channels are part of continuity.** Losing `--channels` costs no error and no
log line — the session comes up, the terminal looks right, and the agent is
unreachable from outside. Never defaulted, never inferred: declared.

---

## 5 For a Deployment

```bash
macf_tools harness generate              # review first; writes nothing
macf_tools harness install --check       # report drift against the generator
macf_tools harness install --channel <plugin> [--shell-prefix <short>]
systemctl --user daemon-reload && systemctl --user enable --now cc-harness-<id>.service
macf_tools harness status                # resolves the agent, or says it defaulted
```

**Do not hand-edit the rendered artifacts.** Every one carries a
`generated, do not hand-edit` banner and a regeneration command. The generator
exists because a hand-edited unit and its stored copy drifted, and the stored copy
was missing the flag that makes the harness work — so anyone installing from the
artifact got a silently degraded session.

**Verify, do not assume.** `install --check` reports drift. `harness status`
reports whether the session is *owned* by this harness, not merely present.
A harness that has never been observed through a second path has not been
verified.

---

## 6 Scope

**In scope: one active session per Calling Card.** This is Agentic Continuity —
one agent identity persisting across restarts, which is what the harness exists
to provide.

**Out of scope: multiple parallel sessions sharing one Calling Card.** That needs
fork → join semantics to reconcile divergent sessions into a single identity, and
it is a substantially harder problem: two sessions writing one task store is a
solved class of problem, but **which fork's experience is the agent's experience**
is not. It is named here so the naming scheme does not foreclose it — an
identifier with room for an optional discriminator costs nothing today.

---

## Wiki-Links

[[tooling]] [[silent_failure]] [[verification]] [[autonomy]] [[capability_boundary]]
