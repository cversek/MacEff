---
name: maceff-restart-session
description: Trigger a μC (microcompaction) by restarting the current session via the auto-restart supervisor. Use when user requests restart, μC, or session refresh.
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

4. **Notify Telegram** (if channel available) that μC was triggered

## What Happens

- Supervisor sends SIGINT to the current CC process (graceful exit)
- Countdown runs (default 5s) in the supervisor terminal
- CC relaunches with same command + args via `claude -c`
- SessionStart hook fires on resume
- Cycle number does NOT increment (μC, not full compaction)
- Session ID remains the same (CC resume)
