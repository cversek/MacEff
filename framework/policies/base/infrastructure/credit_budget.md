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
- When do two samples belong to the same window, given that reset times jitter?
- What is the smoothed burn rate, and what does `wk 38% (2.4%/hr)` on a hook line mean?
- How often may the endpoint be asked?

**3.1 Unasked Reminders**
- When does the budget show up without being asked, and why so rarely?
- What is the warning before the five-hour wall, and what does it ask for?
- When do the hooks sample on their own, and when do they never touch a credential?
- What happens when a refresh fails, and how long do the hooks wait before asking again?
- What does the weekly field show when its refresh is failing, or its week has reset since the sample?
- What does `me 0.9%/1h` after the weekly field mean, and why does what other agents do not move it?
- How is the rate behind it calibrated, and what does a `!` before it ask for?

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
opened, a smoothed rate, and where the limit lands at its reset if that pace holds. A **window** is one limit between two resets; a
limit's history is read only within its current window, because a percentage that fell to zero at a reset says
nothing about how fast the new window fills. `budget log` shows the week's samples.

Two samples belong to one window when their reset times agree to within a few minutes. The endpoint's reset time
jitters by about a second between replies, and an exact match once split every window into single samples, so no
rate was ever computed and a band reminder repeated with each jitter. Real windows are five hours or a week apart,
so the tolerance cannot join two of them.

The **smoothed rate** is an exponentially weighted mean of the burn rate over the window, with a time constant of
two hours (`MACEFF_BUDGET_RATE_TAU_MIN`). It exists because percentages are whole numbers sampled every few
minutes, so the rate between two neighbouring samples jumps between zero and several percent an hour. Each interval
between samples counts by how much of it lies in the recent past, so an overnight gap does not outvote the last
two hours. It is shown only once a window's samples span half an hour, for the reason in §5: one sample is a position, not a
speed.

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

**The weekly field** rides on every hook line, beside the context level: `wk 38% (2.4%/hr)`, the all-models weekly
cap and its smoothed burn rate. It is not a reminder and carries no remedy; it is an instrument the agent paces
against. The rate is shown to two significant figures (`0.35`, `2.4`, `12`). For scale, a cap spent evenly over a week
burns about 0.6 percent an hour, so pacing is read in the range where one figure collapsed "on pace" and "half again
over" into the same `1`. The samples are whole percents, so the second figure is the smoothing's trend over hours of
those steps, not a measurement to that precision: read a change in it as a direction, and its value against the even
pace. A sample over an hour old says so: `wk 38% (2.4%/hr, 3h old)`. When the refresh has failed since that sample,
the field says why and what to run: `wk 38% (57h old: endpoint 429; budget sample --manual)`. Once the sample's week
has reset, its percentage and rate describe a window that is over, so the field shows neither:
`wk reset since the last sample (3h old)`.

**The own share** follows the weekly field once the agent's usage meter has counted calls: `· me 0.9%/1h`, the
points this agent spent over the last hour. The window is written out because it is not the weekly field's: that
rate is smoothed over two hours, this is a plain one-hour sum, so the two disagree during a burst and neither is
wrong. Points are this agent's own metered tokens times a **frozen calibration**: a rate in points per weighted
token, recorded once as a `usage_rate_calibrated` event and read from there by the hook line, `budget me` and the
digest. Nothing on the hook or Stop path recomputes it from the current hours, so other agents on the same account
working in the same hours cannot move this agent's figure. A rate refitted each hour against the account's counter
could not tell this agent's use from theirs, and read their activity as this agent's cost (#1176).

`budget calibrate` computes the rate as a lower envelope. The counter's change over a window is this agent's points
plus everyone else's, and everyone else's is never negative, so each window gives an upper bound on the rate: the
counter's change plus one (its whole-percent step) over this agent's weighted tokens in it. The calibration is the
smallest of those bounds over every window of one to twelve whole hours in the last fourteen days that has a
counter reading at both ends, no weekly reset inside and this agent active in it. Other agents' use can only raise a
window's bound, never lower it, so a busy hour of theirs loosens that window and is simply not the one chosen.
Alongside the whole hours it also tries **step windows**, which run at the samples' own times from a step-up (the
first reading of a new value) to the sample just before a later step-up, one to twelve hours apart. Every reading `v`
means the true counter is at least `v` and below `v + 1`, so the bound has the same form; but at these ends the
counter has only just passed its start reading and is just short of its end reading plus one, so the added one is
nearly all real movement rather than rounding. No allowance for movement inside a sample gap is assumed, because none
is needed: the bound holds however the account moved between two samples. The calibration is the smallest bound over
both sets, so the step windows can only tighten it. Any fall of the counter between a window's two ends breaks it,
whether or not the samples name a reset time, so a stale low reading or an unmarked weekly reset never ends a window
below its start. As a second line of defence a bound at or below zero is refused and named in the output, never
chosen: it is never a measurement, and with no positive bound there is no calibration and the command says why.
The command prints the rate, the kind of window that set it (`hour` or `step`, also recorded in the event), its span
and how many windows were considered, and beside it the tightest window that does not overlap the chosen one, with
its rate and how many times the chosen rate it is (recorded as `runner_up`). The minimum goes to whichever window had
this agent's tokens most over-counted, so a runner-up far above the chosen rate says the chosen window may be one
window's measurement error. **A rate more than four times the provisional constant, or less than a quarter of it,
is refused and not recorded**, and the command exits 1 saying why: so far from the price list it is more likely a
meter fault than a measurement. Look at the window it names and the runner-up before anything else; there is no
override, and the provisional rate or the previous calibration stays in force. `--dry-run` prints without
recording, and says when a real run would be refused.
Cache reads weigh a tenth of fresh input, a constant chosen by an earlier fit that agreed with the price list.
**Each model's tokens are weighed by its price relative to the main model** before they count anywhere: in the
calibration's windows, the hook line, `budget me`, the digest and the sprint records. The account's points follow
the price list, and the models differ there several-fold, so one rate for every model would let the minimum pick
the window whose tokens were cheapest, the one leaning most on a less expensive model, and then price main-model
hours at that rate: `me` would read low in the hours that cost most, by an amount the band of four does not catch.
The factors are the list-price ratios to `claude-opus-5-5`, **one per model and per token kind** (input, the two
cache writes, cache reads, output), each against the main model's price for the same kind, kept in a small table in
the usage meter keyed by model id prefix. One factor per model would not do: the list prices cache reads at a
different fraction of input per model, so Fable 5.2 costs twice the main model for input and output but the same
for a cache read, and reads are most of the tokens (Sonnet 5.5 is a half in every kind; Haiku 5.5 a fortieth, and a
twentieth for reads, its read price derived from the list's tenth-of-input rule since the list gives none). The Haiku 5.5 factors assume
prompts under its long-prompt price tier, beyond which the list charges five times as much. The calibrated rate is
therefore points per `claude-opus-5-5` token, and the calibration event records the factors it used. A model missing from the table
weighs as the main model and is never passed over silently: it is named once on stderr and in `budget me`, and the
remedy is to add its ratio to the table when the price list changes or a model arrives.
The rate is an upper bound, and it tightens as the agent works through hours in which the account barely moves. **So
`me` is an upper bound on this agent's points, not an estimate**: it errs high by construction, and the figures of
several seats on one account added together come to more than the account moved. `budget me` says so on its own
line; the hook line keeps the bare figure. Until
the first calibration the provisional constant stands in, marked `~`. `part` marks an hour not fully metered.

The account's movement is kept only as a sanity check. When this agent's points over a window come to more than the
account moved plus one, the figure is shown as it is, not capped, and marked `!`, as in `me !3.6%/1h`. What
`budget me` says depends on the calibration's age. Within six hours of calibrating the rate cannot have gone stale:
it says the calibrated bound is loose for this hour, an upper bound that recalibrating after heavy hours tightens.
After six hours it says the calibration looks stale and names `budget calibrate`. `budget me` shows the share over any
window and puts the rest of the account's movement down to other agents and unmetered use. Calls are placed at their
own times: an event that gathered calls across a window's edge counts only the part inside, and a call copied into a
forked subagent's transcript is counted once.

The hooks refresh the sample themselves at most every ten minutes (`MACEFF_BUDGET_AUTOSAMPLE_MIN`) with a short
timeout, and **only for an agent that has sampled in the last week**: an installation that never asked for its budget
never has a credential read on its behalf. Anything failing inside the budget code yields no line; it never fails a
hook.

**A failed refresh is recorded and waited out.** Each failed fetch, from a hook or from `budget sample`, leaves a
`budget_sample_failed` event with a short reason, the HTTP status and any `Retry-After`, never anything from the reply
or the credential. The hooks' interval runs from the last attempt, not the last success: each failure in a row since
the newest sample doubles the wait, up to two hours (`MACEFF_BUDGET_BACKOFF_CAP_MIN`), and a reply that says how long
to wait is waited out even past that. A success restores the ten-minute interval. Measured from the last success, the
interval never closed after a failure, so every hook call asked again; on a busy session that was enough to keep the
endpoint answering 429 for days while the field showed an ever older number (#852). The backoff is per agent: agents
that share one credential each keep their own, so their combined asking grows with their number but stays bounded.
A failed refresh never takes the reminders with it either. They are computed from the newest sample, and say how old
it is when it is over an hour old. `budget status` names the last failure and when the hooks will ask again.

## 4 Intent: conserve, normal, burn

`budget mode set` records what the operator wants from the allowance, as a `budget_mode_set` event.

- **normal**: no intent beyond the work at hand. The default, and what every mode lapses to after a week. A lapse is
  announced once in the budget notice, naming the mode and when it was set, since the intent may still hold.
- **conserve**: the allowance is scarce; prefer smaller steps and checkpoints before the five-hour wall. The Stop
  hook's idle-stop failsafe yields on the first blocked Stop that made no new tool call and got no new result, so a
  gate never forces a second turn of re-checking under conserve (amended 2026-11-22, BUG #1120).
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
