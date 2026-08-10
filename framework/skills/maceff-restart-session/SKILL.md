---
name: maceff-restart-session
description: Trigger a session resume by restarting the current session via the auto-restart supervisor. The process restarts; the conversation continues. Use when user requests a session resume, restart, session refresh, or reload of settings/permissions (also recognizes the deprecated term "μC").
---

# Restart Session via Auto-Restart Supervisor

Trigger a graceful session restart. The auto-restart supervisor catches the exit and relaunches with `claude -c`, preserving the session.

## Prerequisite

Session must be running under `macf_tools auto-restart` supervisor.

## Steps

1. **Verify supervisor is running**:
```bash
macf_tools auto-restart list
```
If no supervisor is running, inform the user:
> No auto-restart supervisor detected. Start one with:
> `macf_tools auto-restart launch --name <NAME> -- <your claude command>`

2. **Get supervisor PID** from the list output (first column of running entry)

3. **Send restart signal**:
```bash
macf_tools auto-restart restart <PID>
```

4. **Notify Telegram** (if channel available) that a session resume was triggered

## What Happens

- Supervisor sends SIGINT to the current CC process (graceful exit)
- Countdown runs (default 5s) in the supervisor terminal
- CC relaunches with same command + args via `claude -c`
- SessionStart hook fires on resume
- Cycle number does NOT increment (a session resume is not a compaction)
- Session ID remains the same (CC resume)

## What a Session Resume Is NOT

A session resume is **not** a context loss. The conversation continues via
`claude -c` — the process restarted, the context did not. This is a rejoin, not a
rebirth.

So no recovery ritual applies: do not re-read consciousness artifacts, do not
re-orient the work stack, and do not report to the user as though returning from a
mind-wipe. Pick up where you left off.

The orientation rituals belong to the events that actually destroy context —
compaction, a cleared session, or work resumed from an earlier cycle — not to a
process that restarted underneath a continuous conversation.
