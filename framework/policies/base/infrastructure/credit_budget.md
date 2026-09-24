# Credit Budget: The Subscription's Rate Limits as a Budget the Agent Can See

**Type**: Infrastructure (operations)
**Scope**: All agents (PA and SA) running under a Claude subscription
**Status**: ACTIVE

---

## Purpose

An agent already sees one budget, its context window. There is a second one it cannot see, and the operator manages it
by hand: the subscription's rate limits. A five-hour session window, a seven-day cap across models, and weekly caps
scoped to particular models each fill as work is done and each expire, unused, at their reset. An operator who wants
the week's allowance spent on real work before it resets, or who wants an agent never to hit the five-hour wall in the
middle of a task, has had only the interactive `/usage` screen and their own arithmetic.

`macf_tools budget` gives the agent the same numbers, a record of how they move, and a record of what the operator
intends for them. This policy says where the numbers come from, what may be kept, and what each intent promises.

---

## CEP Navigation Guide

**1 Where the Numbers Come From**
- What does `budget sample` read, and which part of the reply is trusted?
- Why is only the limits list read?
- What happens when the endpoint changes or disappears?

**2 Credential Custody**
- Which credential does a sample use, and where does it live on a host and in a container?
- What may never happen to the token?
- What may a sample keep, and what must it drop?
- What if no credential is reachable, or a command that reads it is refused?

**3 Reading the Budget**
- What does `budget status` report, and how is a burn rate computed?
- What is a window, and why are rates never computed across a reset?
- How often may the endpoint be asked?

**3.1 Unasked Reminders**
- When does the budget show up without being asked, and why so rarely?
- What is the warning before the five-hour wall, and what does it ask for?
- When do the hooks sample on their own, and when do they never touch a credential?

**4 Intent: conserve, normal, burn**
- What does each mode promise?
- What does `budget plan` offer an agent told to spend the allowance?

**4.1 The Burn Gate**
- When does burn mode hold a session open at Stop, and when does it never?
- How does the operator end it, and what bounds it if nobody does?
- What does burn need to be meaningful, and what are its defaults?
- How long does a mode last?

**5 Anti-Patterns**
- What are the known ways to misuse a budget reading?

=== CEP_NAV_BOUNDARY ===

---

## 1 Where the Numbers Come From

`budget sample` asks the same endpoint Claude Code's `/usage` screen asks, once, and keeps the reply's **limits list**:
entries of `kind` (`session`, `weekly_all`, `weekly_scoped`), `percent`, `severity`, `resets_at`, and for a scoped entry
the model's display name. That list is the general form of the answer. The rest of the reply is a set of named fields
that have churned between releases and will churn again; reading them would tie the framework to a shape nobody
promised, so none of them is read.

The endpoint is not a published API. If it changes, `sample` refuses with the reason and points at `--manual`; nothing
else in the framework depends on a successful fetch.

## 2 Credential Custody

The request carries the Claude Code CLI's own OAuth token: on macOS the Keychain item `Claude Code-credentials`, on
other hosts and in containers the CLI's credential file. The token is read for one request and lives only in that
request's frame. **It is never printed, logged, written to a file, or placed in an event**, and a sample keeps the
declared limit fields and nothing else from the reply, because the reply's other fields can carry account details.

Where no credential is reachable, or where a permission layer refuses the command that reads it (an auto-mode
classifier may reasonably treat a credential read as sensitive), the operator pastes what `/usage` shows:
`budget sample --manual "session 24 @18:50 week 3 Fable 4"`. A manual sample is marked as such and is as good as a
fetched one for every purpose here. Do not work around a refused credential read; ask the operator, who can approve
the one command or paste the numbers.

## 3 Reading the Budget

`budget status` shows the latest sample and, for each limit, the burn rate over the last hour and since the window
opened, and where the limit lands at its reset if that pace holds. A **window** is one limit between two resets; a
limit's history is read only within its current window, because a percentage that fell to zero at a reset says
nothing about how fast the new window fills. `budget log` shows the week's samples.

Samples are events (`budget_sampled`), so the history is the events log and nothing is stored beside it. Reads stop
at eight days, one day past the longest window, because nothing older can bear on a current answer.

The endpoint is asked at most once every few minutes; a `sample` inside that interval returns the last one unless
`--fresh`. Anything that samples automatically relies on this and must not pass `--fresh`.

### 3.1 Unasked Reminders

The budget reaches the agent unasked in two places, both governed by `mode_system`'s nag design: computed from
observed state, naming the remedy, and rare, because every line injected into context spends the agent's willingness
to read the next one.

- **The prompt line** appears when a limit this model is filling (the session window, the weekly cap, and a per-model
  cap only if it is this model's) enters a new band, 50, 75 and 90 percent by default (`MACEFF_BUDGET_BANDS`), and in
  burn when the pace still needed moves by more than a point. It records what it showed as a `budget_notice` event and
  stays silent until something changes.
- **The wall warning** fires once per five-hour window, before a tool call, when the window reaches 90 percent
  (`MACEFF_BUDGET_WALL`). Running out of the window stops work with no hook afterwards, unlike a compaction, so the
  remedy it names is a task note or checkpoint for the work in hand.

The hooks refresh the sample themselves at most every ten minutes (`MACEFF_BUDGET_AUTOSAMPLE_MIN`) with a short
timeout, and **only for an agent that has sampled in the last week**: an installation that never asked for its budget
never has a credential read on its behalf. Anything failing inside the budget code yields no line; it never fails a
hook.

## 4 Intent: conserve, normal, burn

`budget mode set` records what the operator wants from the allowance, as a `budget_mode_set` event.

- **normal**: no intent beyond the work at hand. The default, and what every mode lapses to after a week.
- **conserve**: the allowance is scarce; prefer smaller steps and checkpoints before the five-hour wall.
- **burn**: the allowance is expiring and the operator wants it spent on real work. Burn names a **target** percent
  (default 100), a **scope** (`session`, `week`, or a model's name as `/usage` shows it; default `week`) and a
  **deadline** (default the scope's reset). `status` then reports the pace still needed.

`budget plan` shows the status arithmetic beside the open work it could buy: tasks in the active scope first, then open
missions, phases, experiments and detours. It lists what exists; it proposes nothing new.

A mode is intent, not permission: burn never authorizes work the agent would not otherwise be authorized to do, and
it is spent on work that already exists (open mission phases, scoped tasks), not on work invented to consume credit.

### 4.1 The Burn Gate

In AUTO_MODE, burn is more than a report: the Stop hook holds the session while **all** of these hold: the mode is
burn; the burn's limit is below its target; the deadline (and the limit's reset) is still ahead; and open work
exists to spend it on (the same list `budget plan` shows). The reason it gives names the limit, the target, the time
left, the pace needed and the open work.

It never holds in MANUAL_MODE, where the operator is present and decides. It composes after the scope and focus
gates, which already hold a session with scoped work or due duties, and it shares their idle-stop failsafe: an agent
that keeps stopping without working is let through when the counter reaches zero, as with every gate.
`budget mode set normal` always ends it. A gate that could trap a session with no escape would be worse than none.

## 5 Anti-Patterns

- **Reading the reply's named fields.** They churn; a tool built on them fails silently when they move.
- **Echoing the credential to debug a fetch.** Debug with the HTTP status and the exception type; that is all the
  message needs.
- **Treating a percentage as a rate.** One sample is a position, not a speed; say so until there are two in a window.
- **Burning on invented work.** The point of spending an expiring allowance is the work it buys.

---

## Integration with Other Policies

`capability_boundaries` governs the credential read as a reach the agent must not route around when refused.
`mode_system` governs any reminder that surfaces the budget unasked: thresholds, never a line on every prompt.
`context_management` governs the other budget, the context window, which `macf_tools budget` with no subcommand still
reports.

## Evolution & Feedback

The endpoint's shape is the part most likely to change; when it does, the parser and section 1 change together.

## Wiki-Links

[[credential_custody]] [[consciousness_infrastructure]] [[modes]]
