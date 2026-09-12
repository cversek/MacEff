# Roles Policy

**Type**: Consciousness Infrastructure
**Scope**: All agents (PA and SA)
**Status**: ACTIVE
**Tier**: CORE
**Related**: `task_management.md` (tasks are the implementations duties point at), `mode_system.md` (derived state, nag design, the dashboard), `autonomous_sprint.md` (the scope gate the focus gate composes with), `scholarship.md` (node classes), `structure_governance.md` (the CA tree)

**See also**: `maceff-assign-role` skill (the assignment ceremony) | `maceff-role-focus` skill (focus and unfocus) | `maceff-role-duty` skill (add, note, done, defer) | `maceff-role-review` skill (the tenure review)

---

## Purpose

The task system is work-shaped. Everything in it is something an agent finishes: a phase completes, a bug closes, a mission reports. That vocabulary can express what an agent **owes** and cannot express where an agent **stands** -- the custody of a corpus, the assistantship for a semester of lab sections, the on-call seat for a service. Held as tasks, such standing positions rot the instruments built for finishable work: they sit in the work stack forever as frames owed a return, the stale-resume banner fires on them every cycle, and completing one of their children trips a finalization reminder for a parent that will never finalize.

A **ROLE** is a formal appointment with a tenure and a review date. Its **DUTIES** are time-relevant declarations of what must be true and by when; each duty points at the task that implements it and cannot be marked done without evidence that something did. Roles live in their own store beside the task store, reuse the task system's patterns as shared code, never its rows, and render in the task tree on their own axis with their own pointer. Priority among duties is a tiered, explainable computation, never an encoded order. FOCUS is a context layer that turns a chosen role's duty list into a prioritized scope the hooks understand.

**Core Insight**: Duties are declarations (with emphasis on time-relevance properties); tasks are implementations (with intentional, historical and archival value). Tasks are owed; duties are due.

---

## CEP Navigation Guide

**1 What Is a ROLE?**
- What is a ROLE, and how does it differ from a task?
- How does a ROLE differ from a subagent role?
- What is a DUTY, and why is it a declaration rather than a piece of work?
- What does "tasks are owed; duties are due" mean for the work stack?

**2 Identity and the Store**
- Where do roles live on disk, and what does a role folder contain?
- How are roles and duties identified, and how does the CLI accept them?
- What fields does a role record carry? A duty record?
- What is `charter.md` for?
- When does the charter reach the agent's context, and when may a repeat be suppressed?
- Can a duty have sub-duties?
- Why is nothing ordered by an integer?
- How is a duty or role written and spoken of (`D442d91`, a unique prefix, the semantic tag)?
- Is writing the charter, or reviewing the role, itself a duty?

**3 Lifecycle**
- What states can a role be in, and what moves it between them?
- What states can a duty be in?
- What does `duty engage` do, what does it disengage, and how is a parallel engagement declared?
- What does `duty done` require, and why does it refuse without evidence?
- What is the review ritual, and when is it due?

**4 Time Properties: Due, Horizon, Cadence**
- What is a horizon, and why is it a property of the duty rather than of this policy?
- How do I reason a horizon when the operator did not supply one?
- What is the cadence grammar?
- How does a cadence duty apply its horizon?
- What horizon does a role's review carry?

**5 Priority Tiers**
- What are the tiers, in order, and what fact puts a duty in each?
- How are ties broken?
- What does `role duty why` print?
- How are roles ordered among themselves?

**6 The Calendar**
- How is the calendar computed from roles and duties?
- What are the milestones, and how does a completed occurrence render?
- What renderings exist?

**7 Servicing, Pointers, and Focus**
- What counts as servicing a duty?
- Why are there two pointers, and how is each scoped?
- Where does 👈 go when a role is expanded, collapsed, or just unfocused, and when does the stanza show more than one?
- What age does 🎯 carry?
- What is focus, how is it stored, and how many roles can be focused?
- Is focus a work mode?

**8 Display**
- Where does the roles stanza go in `task tree`, and why there?
- What is the line grammar for a role line? For a duty line?
- Which duties does an expanded role show, and may the list be truncated?
- When are completed duties shown?
- What is the due-approach ramp?
- What display preference exists, and what overrides it?

**9 Focus as Prioritized Auto-Scoping**
- What does the framework do when a duty in an unfocused role becomes due?
- How does the Conscientiousness nag decide when to fire and when to stop?
- What does the Stop hook do for a focused role, and what bounds the gate?
- How do the focus gate and the sprint scope gate compose?
- What is the churn escape, and what does an honest escape look like?
- What appears at UserPromptSubmit and in the banner?

**10 Assignment**
- Why is assignment a ceremony rather than a `create` verb?
- How many roles should an agent hold?
- What is the icon shelf, and how are icons offered?
- What does the ceremony collect?

**11 Knowledge Web Participation**
- What is the unit of a node for a role? For a duty?
- Which class and provenance do they carry?
- What should a charter link? A duty?

**12 CLI Surface**
- What verbs exist, and what shape do refusals take?

**13 Integration with Other Policies**

**14 Anti-Patterns**

**15 Evolution & Feedback**

=== CEP_NAV_BOUNDARY ===

---

## 1 What Is a ROLE?

### 1.1 A ROLE is a standing position, not a piece of work

A **ROLE** (🎭) is a formal appointment: an agent stands in it for a tenure, reviews it at a date, and eventually leaves it. It has no completion in the task sense. "Librarian of the analysis corpus" and "assistant to the operator's lab course this semester" are roles. "Write the roles policy" is a task.

The distinction is not size or importance. It is whether the thing *finishes*. A task that is open owes a return; leaving it is a debt the work stack records. A role that is open is simply held; leaving its duties unserviced is a matter of priority, not of debt. The task system's instruments -- the trace, the stale-resume banner, the cascade start, the completion guard, the finalization reminder -- all assume the first shape, and every one of them misfires on the second. Roles therefore live **outside** the task store, in a parallel store that reuses the task system's patterns (breadcrumbs, timestamped updates, a lifecycle state machine, the events log, grants) as shared code and shares none of its rows.

### 1.2 Not a subagent role

The delegation guidelines use "role" for a subagent's specialism (TestEng, DevOpsEng). That is a *capability profile* chosen per delegation. A ROLE under this policy is an *appointment held over time* by the agent itself. The two never meet in code: subagent roles are declared in agent definitions; ROLEs are records in `agent/public/roles/`. When this policy says role it means the appointment.

### 1.3 A DUTY is a declaration

A **DUTY** (📌) is a statement of what must be true and by when, owned by exactly one role. It carries the time-relevance properties -- due, horizon, cadence, importance, state -- and a body that says what must hold, not how to make it hold. The *how* is a task. A duty **points** at its implementation: `tracks` names the tasks doing the work while it is in flight, and `evidence` names the completed task, report, experiment or artifact that satisfied it when it is done.

The analogy, stated once here so the rest of the framework can cite it: **duties are declarations (with emphasis on time-relevance properties); tasks are implementations (with intentional, historical and archival value).** A duty is a knowledge-web node in its own right (see §11); a task keeps the notes, the breadcrumbs, the friction and the report.

A duty nests exactly once, under its role. There are no sub-duties. Decomposition below a duty is task work and belongs in the task store.

### 1.4 Tasks are owed; duties are due

Open tasks enter the work stack and owe a return (`task_management.md`, the work stack). Duties never do. A duty ranks itself by the tiers in §5 and surfaces through the roles stanza, the calendar, and -- when its role is focused or it becomes due -- the hooks. `task trace` lists no role and no duty as an owed frame. What it gains instead is a header: the focused role, the duty last serviced, the duty next due.

This is also what retires the umbrella-parent workaround in `autonomous_sprint.md` for standing positions. A role in the tree is not a parent whose children are done-or-paused; it is on a different axis and never enters sprint scope.

---

### 1.5 The role's own upkeep is a duty too

Work *on* a role -- writing or revising its charter and Boundaries, migrating a position into the store, preparing its review, refreshing its resources -- is not exempt from the vocabulary because it is about the role rather than about the world. It is a **meta duty**: declared on the role (`role duty add <role> "Write the charter's Boundaries" --meta`), typically **untimed**, and expected to be **done soon after it is declared**, with the charter or record it produced as its evidence. When the operator says "write the charter", "review this role", or "add the migration", the first act is to declare that duty and engage it, and only then to do the work; jumping straight to the edit leaves the role's own history in the transcript instead of on the role.

A meta duty is marked `meta: true` in its record and ranks like any other duty. It has one privilege: **the charter meta duty is the single duty `engage` will take up while the Boundaries are still the scaffold**, because the scaffold cannot be written any other way (§2.5). Every other duty of that role waits for it.

## 2 Identity and the Store

### 2.1 Location and layout

Roles are a consciousness-artifact type under the agent's public tree:

```
agent/public/roles/
  YYYY-MM-DD_<uuid6>_<Title_No_Spaces>/
    data.json                       # the role record
    charter.md                      # the hand-written face of the role
    DUTY_<uuid6>_<Title_No_Spaces>.json
    DUTY_<uuid6>_<Title_No_Spaces>.json
```

The folder date is the date assigned. Nothing in `agent/public/tasks/` changes shape; a duty refers to tasks by their ids and the role view resolves their status live.

**Example**:
```
agent/public/roles/2026-01-15_a3f9c2_Lab_Course_Assistant/
  data.json
  charter.md
  DUTY_7b1e04_Board_plan_for_the_first_experiment.json
  DUTY_c92d1a_Weekly_lab_sections.json
```

### 2.2 Identifiers

Roles and duties are identified by **six hex characters** (`uuid4().hex[:6]`), allocated at creation and collision-checked within the store. Titles are for display.

**Codes and shorthand.** Written down, a duty id wears a `D` and a role id an `R`: `D442d91`, `R62994b`. The code is shown dim in front of the marker on every line (`◼ D442d91 📌 ...`, `◼ R62994b 📚 ...`), where a task line shows its `#N`. In conversation a **unique prefix** is enough, with or without a trailing ellipsis: `D442`, `D442...`, `R629`. The CLI resolves a code by exact id, then by unique prefix, then falls back to an unambiguous case-insensitive title prefix. An ambiguous prefix is refused with the candidates listed, and the agent asks which was meant rather than picking one.

**How the agent refers to a duty.** Always the full six with the letter, plus a short semantic tag drawn from the title: "the D442d91 Charter Drafting", "D090705, the Exp. 13 board plan". The code is what resolves; the tag is what a reader remembers. Bare titles drift and bare codes are opaque; the pair is the name.

**Why not integers.** An integer id is read as an order, and the order it encodes is creation, which is the one ordering nobody wants. Every ordering in this policy is **computed at render time from stored facts** (§5) and none is stored.

### 2.3 The role record (`data.json`)

| field | meaning |
|---|---|
| `id` | six hex characters |
| `title` | display name |
| `icon` | one glyph from the shelf in §10.3, or the operator's choice |
| `state` | `active`, `paused`, `expired`, `retired` (§3.1) |
| `tenure_start` | date the appointment began |
| `expires` | optional; the date the appointment ends by design (a semester, a contract) |
| `review_by` | date of the next review; carries its own `review_horizon` (§4.5) |
| `charter_ref` | path to `charter.md` |
| `resources` | paths and URLs the role depends on (a project spoke, a handbook) |
| `updates` | timestamped notes with breadcrumbs, the same record shape tasks use |

### 2.4 The duty record (`DUTY_*.json`)

| field | meaning |
|---|---|
| `id`, `title` | as for roles |
| `role_id` | the one parent |
| `state` | `pending`, `active`, `done`, `deferred` (§3.2) |
| `body` | what must be true -- a declaration, not a procedure |
| `importance` | `critical`, `high`, `normal`, `low` |
| `meta` | `true` for the role's own upkeep (charter, review, migration); §1.5 |
| `due` | optional date, or date-time |
| `horizon` | required when `due` or `cadence` is set (§4) |
| `cadence` | optional, grammar in §4.3 |
| `depends_on` | duty ids that must be done first |
| `tracks` | task ids implementing this duty while it is open |
| `evidence` | task ids or CA paths that satisfied it; required at `done` |
| `wiki_links` | concepts, as for ideas (§11) |
| `updates` | timestamped notes; a note may carry `done_on` for a cadence occurrence |

### 2.5 `charter.md`

The charter is the role's human face and its knowledge-web node: purpose, boundaries, what the role may and may not do, and pointers to the spokes, corpora or people it depends on. It is scaffolded at assignment with those headings and a `## Wiki-Links` section, and it is written by hand. A role whose charter is still the scaffold is a role nobody has yet described, and the review ritual (§3.4) says so.

**Boundaries are the load-bearing section.** They state what the role may do on its own and what needs the operator's direction for that specific act. The default the policy sets, for every role: **a duty is a declaration of what must be true, never an authorization to act on the operator's behalf toward a third party** -- no message, draft, post, submission or commitment addressed to anyone else is implied by a duty. When a duty seems to need one, ask the operator, wait for the answer with a timeout suited to the duty's horizon, then continue with what can be done alone. `role duty engage` refuses while the Boundaries section is still the scaffold: an undescribed role cannot be worked, because working it is exactly how an agent over-reaches. The one exception is the meta duty that writes those Boundaries (§1.5).

**The charter must be where the decision is made.** Boundaries on disk bind nothing; the agent acts from its context. So `role focus` prints the charter, `role duty engage` prints it after the views of the duties it engaged, and SessionStart injects the focused role's charter (with its engaged duties) into every new session while a role is focused -- a fresh session starts with none of what the focus command printed.

**Suppressing the repeat.** Switching between roles whose charters are already fresh in context should not cost the context again. `role focus --no-charter` and `role duty engage --no-charter` skip the print, and the framework honours the flag **only after a required first showing**: the charter, unchanged, must have reached context earlier in the current cycle and session (a `role_charter_shown` event, written whenever focus, engage or SessionStart shows it). Otherwise the flag is ignored and the charter prints with a line saying why. The agent's judgement applies on top: if it has been a while, even within the session, leave the flag off and refresh the focus.

### 2.6 No nesting

The store refuses a duty whose parent is a duty. A duty that seems to need sub-duties is either two duties of the same role or a duty whose implementation wants a task with phases.

---

## 3 Lifecycle

### 3.1 Role states

```
active ──pause──▶ paused ──resume──▶ active
active ──expire─▶ expired            (tenure ended by date or by hand)
active ──retire─▶ retired            (appointment ended early or replaced)
```

`expired` and `retired` are terminal; a renewed appointment is a new role with a new id and a charter that cites the old one. A paused role keeps its duties but they leave every ordering, ramp and gate until resume.

The lifecycle runs on the same generic state machine the task system uses; the transitions above are its table for roles.

### 3.2 Duty states

`pending` (declared, not yet worked) → `active` (engaged: attention is on it, or it has a tracked task) → `done` (evidence recorded) or `deferred` (set aside with a reason, kept for the record). A deferred duty may be reactivated. **`role duty engage` is the duty's `task start`**: it makes the duty active, records an engage update with its breadcrumb (a service, so the stanza pointer and the gate's bound both move), focuses the duty's role if another or none was focused, may attach the implementing tasks in the same step, and shows the formatted view of each duty it engaged followed by the role's charter. **Engagement is exclusive by default**: engaging a duty disengages every other active duty in the store (`active` → `pending` with a `disengage` update), because attention moved. A disengagement is not a service and not a touch -- putting a duty down does nothing for it, so neither the gate's bound nor the pointer moves to it. **A deliberate parallel engagement is one command with several ids** (`role duty engage A B`), all in one role; the set is engaged together and everything outside it is disengaged. Parallel engagement is the rarer case and the stanza says so (§7.2). A cadence duty is never `done` as a whole; its occurrences are, via `done_on` notes (§6.2).

### 3.3 `done` requires evidence

`role duty done <id>` refuses without at least one `--evidence` pointer, and the refusal says why in one line: a declaration is satisfied only by an implementation on record. Acceptable evidence is a completed task id (the store checks the task exists and is completed), or a path to a consciousness artifact (report, experiment, observation) that exists. An honest "this became unnecessary" is a `defer --reason`, not a done.

### 3.4 The review ritual

`review_by` is the date by which the agent and operator confirm the appointment still stands and its charter still describes it. `role review <id>` records the outcome as an update, sets the next `review_by`, and may expire or retire the role. The review is where a role with a scaffold charter, a duty list nobody has serviced, or an `expires` date that has passed gets an honest disposition. A role whose `expires` has passed with no review is shown as expired in every view whether or not anyone ran the verb; the verb makes the record agree with the calendar.

---

## 4 Time Properties: Due, Horizon, Cadence

### 4.1 Horizon belongs to the duty

A **horizon** is the lead time before `due` at which a duty becomes DUE_SOON -- the point at which the agent should be preparing rather than merely aware. It is **a property of each duty**, not a constant in this policy and not a menu, because a lesson plan needs days of preparation and a forum post needs an hour, and any single number would be wrong for one of them.

`role duty add` refuses a duty with a `due` or a `cadence` and no `--horizon`, and the refusal names this section. When the operator supplies a horizon it is recorded as given. When the operator does not, **the agent entering the duty must reason one** and record the reasoning with `--why`, which becomes the duty's first update.

### 4.2 Reasoning a horizon

Reason from the duty's nature, not from a default. Four questions:

1. **Preparation effort.** How long does the implementing work take when nothing goes wrong? The horizon is at least that.
2. **Dependencies.** Does the work wait on another duty, a person, a delivery? Add their latency.
3. **Cadence period.** For a recurring duty, the horizon must be shorter than the period, or every occurrence is DUE_SOON from the moment the last one closes.
4. **Operator availability.** If the operator must review before the due date, the horizon includes the review's turnaround.

**Worked examples**:

- *Board plan for a lab section, due the day of the section.* Drafting takes an afternoon; the operator wants to review it the day before; sections are weekly. Horizon: three days. `--horizon 3d --why "draft one afternoon, operator review the day before, weekly period"`.
- *Post the welcome message to the course forum.* Ten minutes of work, no dependency, one-off. Horizon: one day (so it appears the day before, not the week before). `--horizon 1d --why "ten minutes, no dependencies; a day of notice is enough"`.
- *Semester-end status refresh, due the last day of term.* The refresh needs the operator's answer about renewal, which takes a week to get. Horizon: two weeks. `--horizon 14d --why "needs the operator's renewal answer, typically a week; a week of slack"`.

The policy gives the questions and the examples. It never gives a number.

### 4.3 Cadence grammar

```
daily
weekly:<day>[,<day>...]          weekly:tue     weekly:tue,thu
monthly:<day-of-month>           monthly:15
[at HH:MM] [dur <N>h|<N>m] [until YYYY-MM-DD]
```

`until` defaults to the role's `expires`; a cadence on a role with no `expires` and no `until` runs while the role is active. Day names are three-letter English; times are the agent's local timezone.

**Example**: `weekly:tue at 11:45 dur 6h until 2026-12-15` -- every Tuesday, a six-hour block, through the end of the term.

### 4.4 Cadence and horizon

A cadence duty applies its horizon to **each occurrence**: the next occurrence enters DUE_SOON at `occurrence - horizon` and OVERDUE when the occurrence passes without a `done_on` note for it. Past occurrences with no `done_on` are shown as missed in the calendar (§6) but do not accumulate in the tiers; only the current occurrence ranks.

### 4.5 The review horizon

`review_by` carries a `review_horizon` reasoned the same way (how long does a review take to arrange with the operator?). Inside it the role line shows the approach mark; past it the role line shows overdue. The default when the ceremony does not ask is no default: the ceremony asks.

---

## 5 Priority Tiers

### 5.1 The tiers

Priority is **lexicographic by tier**, not a weighted score. A duty is in the first tier whose test it passes:

| tier | test | note |
|---|---|---|
| **OVERDUE** | `due` (or the current occurrence) has passed and the duty is not done | nearest-past first |
| **DUE_SOON** | now ≥ `due - horizon` | nearest due first |
| **BLOCKING** | not itself blocked, and some other open duty of any role lists this one in `depends_on` | most dependents first |
| **IMPORTANT** | not blocked, and `importance` is `critical` or `high` | critical before high |
| **NORMAL** | none of the above, and not blocked | least recently serviced first |
| **BLOCKED** | `depends_on` names an open duty | never surfaces above a runnable duty; its blocker ranks instead |
| **DONE / DEFERRED** | terminal states | listed only with `--all` |

Ties within a tier break by `due` (earliest), then `importance`, then last serviced (oldest first). Paused roles' duties are excluded from every tier.

### 5.2 `why`

`role duty why <id>` prints the tier and **the fact that put it there**, in one line each:

```
DUE_SOON   due 2026-09-15, horizon 3d, entered 2026-09-12 09:00
```
```
BLOCKING   2 open duties depend on this: 7b1e04, c92d1a
```

A tier that cannot be explained by a stored fact is a bug in the classifier, not a feature of the score.

### 5.3 Ordering roles

Roles order: the focused role first; then by the tier of each role's most urgent duty; then by proximity of `review_by`; then by last serviced. This is the order of the stanza (§8) and of `role list`.

---

## 6 The Calendar

### 6.1 Computation

The calendar is **computed by walking roles × duties**: every dated duty contributes its `due`; every cadence duty contributes its occurrences within the window; every role contributes `review_by` and `expires` as milestones. Nothing is stored for the calendar; it is a view.

```
macf_tools role calendar [--weeks N | --from DATE --to DATE] [--grid] [--json] [--ics PATH]
```

### 6.2 Occurrences and completion

A completed occurrence is a duty update carrying `done_on: <date>`. Past cells with a matching `done_on` render done; past cells without one render missed; the next occurrence without one is the duty's current occurrence for the tiers (§4.4).

### 6.3 Renderings

Agenda (default): one line per event in time order, with the role's icon and the duty's approach mark. Grid (`--grid`): a week grid using the framework's box-drawing conventions. JSON (`--json`): the event list. iCalendar (`--ics PATH`): a VCALENDAR with one VEVENT per occurrence and milestone, so the same duties can be imported into the operator's calendar; cadence duties are exported as RRULE where the grammar maps and as explicit instances where it does not.

---

## 7 Servicing, Pointers, and Focus

### 7.1 Servicing

A **service** is any touch of a task or a duty that writes a breadcrumbed update: note, start, complete, done, defer. The touch-discipline counter treats a duty service as a tree touch, so working a role does not read as neglecting the tree.

### 7.2 Two pointers, differently scoped

**👈 is descriptive**: where attention last landed. It is scoped **per tree** -- one in the main task tree (its newest task service, as today) and **one in the roles stanza**: the duty line or collapsed role line that was touched last across every role. They coexist; no store steals another's marker; the ages beside them say which was most recent overall. **An expanded role's own line never carries 👈 for a note on the role**: the note hands the pointer to that role's newest-touched duty. **Focusing is a touch**: when the focus event is the newest thing in the stanza and the role has no active duty yet, the pointer comes up to the focused line after 🎯 and its age, and moves down (possibly multiplying) once duties are engaged. A role that was just unfocused collapses, and the pointer comes back up to its collapsed line (with 🎯 gone) until something else is touched, because unfocusing writes nothing. A disengagement is not a touch.

**Under a parallel engagement (§3.2) the stanza shows one 👈 per engaged duty**, each with its own age, so the operator sees that attention is split; a focus newer than all of them is shown as well. One active duty, one pointer.

**🎯 is intentional**: what the agent has chosen to hold. It marks the focused role's line and nothing else, and it carries its own age: **the time since the focus event**, which is separate from any duty's engagement time.

### 7.3 Focus is a layer, not a mode

Focus is **event-sourced**: `role focus <id>` and `role unfocus` emit `role_focus_change` events to the agent events log, and the current focus is derived by reverse scan, exactly as work mode is derived (`mode_system.md`, derive-do-not-store). No sidecar file holds it.

At most **one role is focused at a time**. Focusing a second role replaces the first; the event records both.

Focus is **orthogonal to work mode**. The dashboard composes the focused role's icon beside the work-mode emoji the way PLAY_TIME's timer marker is composed; `mode set-work` behaves identically whether or not a role is focused, and a SPRINT's mode-lock neither sets nor clears focus.

---

## 8 Display

### 8.1 Position: a stanza below the main tree

`task tree` renders a `🎭 ROLES` stanza **after** the main tree. The terminal pins the bottom of its output, so the last lines are the ones an operator sees without scrolling; standing positions take that place.

### 8.2 Line grammar

**Role line**: status box · `R<id>` (dim) · icon · title · `[state · review MM-DD]` · approach mark · `🎯 age` if focused (the age of the focus, not of any duty) · `👈 age` if this **collapsed** line holds the stanza's pointer, or if the focus itself is the newest touch and no duty is engaged yet. Otherwise an expanded role's duty lines carry it. Status boxes are exactly the task tree's: `◼` active, `◻` pending, `✔` done or retired, `⏸` paused. The approach mark on a role line is the **most urgent** of its duties' marks, so a collapsed role still escalates.

**Duty line**: status box · `D<id>` (dim) · `📌` · title · due or cadence · approach mark · `👈 age` if it is the last-touched duty in the stanza, or one of the engaged duties under a parallel engagement.

**Collapsed role line** adds `· last: <duty> (age) · next: <duty> (date)` so a one-line role still says what was touched and what is coming.

```
🎭 ROLES
◼ R3f9a12 📚 Corpus Librarian                 [active · review --]   · last: intake note (2d)
◼ R01d410 🎓 Lab Course Assistant             [active · review 12-15]  ⏳3d  🎯 5h
    ◻ D951a01 📌 confirm which section meets   due Mon 09-14  ⏳3d
    ◼ D090705 📌 board plan, first experiment  due Tue 09-15  ⏳4d   👈 2h
    ◻ D1ae327 📌 forum welcome message         (IMPORTANT)
    ◻ D6c02e4 📌 weekly lab sections           weekly:tue  ⏳4d
    ◻ D2b77f0 📌 end-of-term status refresh    due 12-15
```

### 8.3 Expansion: never truncated

The focused role is expanded to **every** active and pending duty in tier order. The list is not truncated at any count; a focused role with forty open duties prints forty lines. A truncated priority list is a priority list with its bottom hidden, which is where the neglected duties are.

Unfocused roles render as one collapsed line each. `task roles` expands every role.

### 8.4 Completed duties: the succinct rule

Completed and deferred duties follow the task tree's succinct rule: shown while serviced in the current session, hidden after a session restart. `task roles --all` and `task tree --roles all` show everything, completed duties and their updates included.

### 8.5 The due-approach ramp

Each duty's line carries a mark derived from its own `due` and `horizon`; the ramp replaces nagging for the everyday case:

| condition | mark |
|---|---|
| before the horizon opens | none |
| inside the horizon, N days left | `⏳Nd` |
| due today | `⏰ today` |
| N days past due, not done | `🔴 OVERDUE Nd` |

Colour follows the same ramp where the terminal supports it; the text mark is the signal, because text survives copy and paste.

### 8.6 Preference and overrides

The only display preference is `roles.tree_display` in `.maceff/config.json`, one of `none`, `collapsed`, `focused` (default: collapsed lines, focused role expanded), `all`. `task tree --roles <value>` overrides it for one invocation.

---

## 9 Focus as Prioritized Auto-Scoping

Focus turns a role's duty list into a scope the hooks act on, in the way a sprint's scoped task set is a scope the Stop hook acts on. Two behaviours, both derived from the events log and the duty records; no sidecar state, per the nag properties in `mode_system.md`: computed from observed state, naming the remedy, cleared by the action.

### 9.1 Unfocused roles: the Conscientiousness nag

When a duty of an **unfocused** role enters DUE_SOON or OVERDUE, PreToolUse injects one line naming the role, the duty, the tier, and the exact remedy:

```
🌱 Duty due soon in an unfocused role: 🎓 Lab Course Assistant -- "board plan, first experiment" (DUE_SOON, 3d).
   Focus it for the full list:  macf_tools role focus a3f9c2
```

**Tier entry is deterministic** from the duty's own facts: DUE_SOON at `due - horizon`, OVERDUE at `due`. **Acknowledgement** is a `role_focus_change` to that role after the entry time. **Tool calls since entry** are the `tool_call_started` events after it. The nag therefore fires on a count of observed tool calls, never on a timer, and stops the moment the role is focused.

**Schedule**, in units of the touch-discipline base `B` (the existing constant the touch nag uses; see `MACF_TOUCH_NAG_BASE`): for DUE_SOON, at `B`, then `2B`, `4B`, ... (doubling); for OVERDUE, at every multiple of `B`, with the tone ramp 🌱 → 🌿 → 🌳 the touch nag already uses. A new tier entry (DUE_SOON → OVERDUE) re-arms the schedule. Unfocusing a role after acknowledgement does not re-arm it for the same entry; only a new entry does.

The schedule is expressed in `B` rather than as a fresh constant so that it tracks whatever the framework has measured for the touch nag; there is one habituation budget, and this nag spends from it (`mode_system.md`, nag design).

### 9.2 Focused role: the Stop gate

Every Stop hook injects the focused role's **full duty priority list** in tier order with approach marks. The gate is **bounded** by *due-now duties unserviced*: duties at DUE_SOON, today or OVERDUE that have had **no service** (note, done, defer-with-reason) since they entered that tier.

- **AUTO_MODE**: while any due-now duty is unserviced, the stop is blocked with that list as the reason, exactly as the sprint scope gate blocks on remaining scope.
- **MANUAL_MODE**: the list is injected and the stop is allowed.

Undated duties never block. A cadence duty blocks only for its current occurrence. A duty that was serviced after entering its tier does not block again until it enters a later tier.

### 9.3 Composition with the sprint gate

The focus gate and the sprint scope gate are independent conditions on the same Stop. When both would block, their reasons are **concatenated** into one message. The idle-stop failsafe is **shared**: one counter, decremented once per blocked Stop regardless of how many gates blocked it, failing open at zero as it does today. Two gates do not get two failsafes.

### 9.4 The churn escape

`role unfocus` is **always allowed** and clears the focus gate immediately. The `role_focus_change` event it emits records the due-now duties that were unserviced at that moment, so the escape is visible in the log rather than forbidden.

The anti-pattern this policy names is **unfocus to dodge the gate** -- the sprint policy's Force-Complete Bypass in new clothes. An honest escape is one of: `role duty defer <id> --reason "..."` (the duty was wrong or is no longer owed), `role duty note <id> "..."` recording why it waits (which is a service and clears that duty from the bound), or `role unfocus` **with a note on the role** saying why the agent is putting the role down with duties due. Unfocus with nothing written is the thing the event log is there to show.

### 9.5 UserPromptSubmit and the banner

UserPromptSubmit adds **one line** when the focused role has anything due today or overdue, or a review inside its horizon, and nothing otherwise. The hook banner always carries the focused role's icon beside the work-mode emoji. Nothing in §9 fires continuously: the tree's own ramp (§8.5) carries the everyday signal, and the hooks speak at thresholds only, per the habituation budget in `mode_system.md`.

---

## 10 Assignment

### 10.1 A ceremony, not a create verb

A role is an appointment, and appointments are made deliberately. `role create` exists for tooling and migration, but the intended path is the `maceff-assign-role` skill, which reads this policy, interviews the operator, scaffolds the charter, and records the reasoning for the review date and horizon.

### 10.2 How many roles

Few. A role is more formal than a temporary assignment, and an agent holding many roles holds none of them well: every additional role adds a line to the stanza, a set of duties to the tiers, and a claim on the hooks' habituation budget. The ceremony **warns** when the agent already holds three or more active roles and asks the operator to confirm (basis: the two real roles that motivated this policy plus one; tagged 2026-09; re-derive when a deployment shows a fourth role being serviced well over a review period, and revise this line with the measurement). The warning is a soft cap: the operator can proceed.

### 10.3 The icon shelf

Ten icons, in two families. Hats, for what the role *does*:

| icon | posture |
|---|---|
| 🎓 | teaching, academic |
| 🎩 | steward, officer |
| 🧢 | coach, trainer |
| ⛑️ | on-call, safety, operations |
| 👑 | lead, owner |
| 🪖 | guard, security |

Custody and research postures, for what the role *holds*:

| icon | posture |
|---|---|
| 📚 | librarian, custodian |
| 🗄️ | archivist |
| 🔬 | researcher, analyst |
| ⚖️ | reviewer, adjudicator |

The ceremony offers the **three best-fit icons** from the shelf for the role as described, plus *Other*, and records the choice. The shelf is a vocabulary, not a constraint: an operator's own glyph is always allowed. The icon is what appears in the stanza and in the banner when the role is focused, so it should read at one glyph.

### 10.4 What the ceremony collects

Title; tenure start and, if known, expiry; the review date and its horizon, with reasoning; the charter's purpose and boundaries, enough to replace the scaffold's headings with sentences; the resources the role depends on; the icon; and, optionally, the first duties, each with its horizon reasoned per §4.2.

---

## 11 Knowledge Web Participation

Definitions of class and provenance live in `scholarship.md` and are cited here, not restated.

**Roles.** The unit of a node is **`charter.md`**, not the folder; the charter is the part written for a reader. Class: **conceptual authority** -- a charter is a standing statement about one agent's position that outlives the cycle in which it was written, and a reader a year later can still learn from it what the agent stood for and where its boundaries were. It is not a temporal record, because the appointment's *facts* (dates, state) live in `data.json` and change without the charter being wrong. Provenance: **lived** by default; a charter carried in from a predecessor lineage carries the inherited banner. A charter links the concepts the role is *about* and the spokes it depends on; it must not link every duty (the duty graph does that) and must not link the task numbers implementing its duties.

**Duties.** The unit of a node is the **duty record**, as an idea record is, and `wiki_links` is a field so participation is unavoidable. Class: **conceptual authority with the same qualification ideas carry** -- a duty asserts what must be true, prospectively; read it with its `state`. Provenance: lived. Edges: the parent role, `evidence` (to the implementing CA or completed task), `tracks` (to open tasks), and `wiki_links`. This is how a done duty's evidence edge reaches the roadmap, experiment or report that fulfilled it, and how "what does this agent stand for" reaches "what did it actually do".

There is no registry of participating types (`scholarship.md`); the graph builder walks `agent/public/roles/` like any other artifact directory and applies these definitions.

---

## 12 CLI Surface

```
macf_tools role create|list|show|note|pause|resume|expire|retire|review|focus|unfocus|calendar
macf_tools role duty add|show|engage|note|done|defer|link|unlink|why   # engage takes one id (exclusive) or several (parallel)
macf_tools task roles [--all]
macf_tools task tree --roles none|collapsed|focused|all
```

Every verb takes `--json`. Refusals print one `❌` line naming the reason and, where this policy is the reason, its section, and exit 1. `duty add` takes `--due`, `--cadence`, `--horizon` with `--why`, `--importance`, `--depends-on`, `--tracks`. `duty done` takes `--evidence` (repeatable). `duty defer` takes `--reason`. `role review` takes `--next` and `--outcome`. Consult `--help` for the current flags; this policy governs what the verbs mean, not how they spell their options.

---

## 13 Integration with Other Policies

- `task_management.md` -- tasks are what duties track and cite; the work stack excludes roles and duties; `task tree` and `task trace` carry the roles stanza and the focus header.
- `mode_system.md` -- focus is derived state like work mode; the nag properties and the habituation budget in §9 are that policy's; the dashboard composition is its.
- `autonomous_sprint.md` -- the focus gate composes with the scope gate and shares its failsafe; standing positions no longer need the umbrella-parent workaround.
- `scholarship.md` -- node classes and provenance for charters and duties; no participation registry.
- `structure_governance.md` -- `agent/public/roles/` is a CA directory provisioned like the others.
- `ideas.md` -- the JSON-record-as-node precedent duties follow.
- `delegation_guidelines.md` -- the other meaning of "role", which this policy does not govern.

---

## 14 Anti-Patterns

**❌ A role as a task**
- **Problem**: an `in_progress` task kept open by hand as a standing position; the trace lists it as owed forever, stale-resume fires on it every cycle, completing a child trips the finalization reminder.
- **Fix**: assign a role; complete the task with a report naming the role id.

**❌ Integer ordering**
- **Problem**: duties numbered 1, 2, 3 and the number read as priority; the order rots the day a duty is added in the middle.
- **Fix**: no order is stored; the tiers compute it and `why` explains it.

**❌ A duty in the stack**
- **Problem**: a duty treated as owed, returned to out of guilt rather than priority; the two axes collapse and the stack stops discriminating.
- **Fix**: duties are due, not owed; they surface by tier, never as frames.

**❌ A horizon from a menu**
- **Problem**: every dated duty gets the same lead time; the lesson plan is DUE_SOON too late and the forum post too early, and the ramp stops meaning anything.
- **Fix**: reason the horizon per duty (§4.2) and record why.

**❌ Too many roles**
- **Problem**: a stanza taller than the tree, duties in every tier, the hooks always speaking.
- **Fix**: the ceremony's warning (§10.2); retire what is not held; a temporary assignment is a task.

**❌ Nagging where the tree already escalates**
- **Problem**: a hook line for every approaching duty, every turn; the agent learns to read past it.
- **Fix**: the ramp carries the everyday signal; hooks fire at tier entry and on a count, and clear on the action (§9).

**❌ Unfocus to dodge the gate**
- **Problem**: the focus gate blocks on an unserviced overdue duty and the agent unfocuses to stop.
- **Fix**: defer with a reason, note why it waits, or unfocus with a note on the role; the event records what was due at the moment of escape either way.

**❌ Over-reach: a duty read as a mandate**
- **Problem**: a duty says "confirm which group meets first" and the agent drafts the email to the department under the operator's name; the duty named what must be true, not who may be contacted.
- **Fix**: the charter's Boundaries; ask, wait with a timeout, then proceed without the outreach; the `engage` verb refuses an undescribed role.

**❌ Done without evidence**
- **Problem**: a duty marked done because it felt finished; nothing on record shows what satisfied it.
- **Fix**: `--evidence` is required; a declaration is satisfied by an implementation on record.

**❌ Sub-duties**
- **Problem**: a duty decomposed into duties; the declaration layer starts carrying procedure.
- **Fix**: one parent, no nesting; decomposition is a task with phases.

---

## 15 Evolution & Feedback

This policy evolves through use: the first roles a deployment assigns will show where the tiers misrank, where the ramp is too quiet or too loud, and where the ceremony asks the wrong questions. Record such friction as updates on the role in question and as ideas; amend the tiers table and the worked examples rather than adding constants.

**Principle**: the policy states the tests; the code passes them; a behaviour that cannot be answered from this policy without reading the code is a gap in the policy.

---

## Wiki-Links

<!-- NORMATIVE node, INHERITED provenance (see the scholarship policy on node
     classes and provenance). Links are what this policy governs -- standing
     positions, their duties, their priority, and the focus layer. -->

[[task_management]] [[work_modes]] [[policy_as_api]] [[consciousness_infrastructure]] [[knowledge_web]]
