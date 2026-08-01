# The Persistent Agent Harness

A supervised, detached, continuity-anchored Claude Code session. A systemd user
unit creates a tmux session, tmux runs `macf.supervisor`, and the supervisor runs
the client through a child wrapper. The session survives client restarts and
operator detach, which is what makes unattended autonomous work possible.

Everything is **generated**. Do not hand-edit the installed artifacts — the
predecessor to this command was a hand-edited unit whose stored copy had already
drifted from the live one, and was missing the environment flag that keeps the
long-context window. Anyone installing from that artifact would have got a
silently degraded harness.

## Install

```bash
macf_tools harness generate --agent <slug>          # review first, writes nothing
macf_tools harness install  --agent <slug>
systemctl --user daemon-reload
systemctl --user enable --now cc-harness-<slug>.service
```

`--agent` names the unit, the tmux session and the supervisor instance. Use a
short slug, not a login name — it appears in the unit filename.

Three artifacts are written:

| Path | Purpose |
|---|---|
| `~/.config/systemd/user/cc-harness-<slug>.service` | creates the session at boot |
| `~/.local/bin/maceff_cc_child_<slug>` | supervised child entrypoint |
| `~/.tmux-<slug>.conf` | terminal baseline for TUI fidelity |

## Operate

```bash
macf_tools harness status --agent <slug>     # unit, session, proxy attachment
tmux attach -t <slug>                        # attach (Ctrl-b d to detach)
systemctl --user stop cc-harness-<slug>.service   # remote kill switch
```

`stop` stops the **supervisor**, not the child. Killing the child only makes the
supervisor restart it, so a stop that targets the child is not a stop.

## Check for drift

```bash
macf_tools harness install --check --agent <slug>
```

Reports, without writing, whether each installed artifact still matches what the
generator produces. Exits non-zero if any differs. `install` refuses to overwrite
a differing artifact unless `--force`.

## Uninstall

```bash
systemctl --user disable --now cc-harness-<slug>.service
rm ~/.config/systemd/user/cc-harness-<slug>.service
rm ~/.local/bin/maceff_cc_child_<slug> ~/.tmux-<slug>.conf
systemctl --user daemon-reload
tmux kill-session -t <slug>    # only if you also want the running session gone
```

## Why the unit looks the way it does

Each of these cost a real incident. They are asserted in
`macf/tests/test_harness_render.py` so they cannot regress silently.

**`$${BASE}` is escaped.** systemd expands `$VAR` and `${VAR}` in `Exec*` lines
using the *unit's* environment before any shell runs. `BASE` is not a unit
variable, so an unescaped `${BASE}` was replaced with an empty string and the
shell's own assignment never mattered. The proxy opt-in was silently inert, with
nothing but "Referenced but unset environment variable" in the journal.

**The first-party flag is emitted in the same assignment as the base URL.** When
the API base URL's host is not the default, the client stops extending the
long-context window and falls back to 200K — while every surface continues to
display the full window. There is no log line and no warning; the only symptom is
compacting early. Setting the base URL without the flag reinstates that silently,
so the two are never separated.

**Proxy attachment is probed, not assumed.** A short `curl` decides whether to
attach. A dead proxy must degrade to a direct agent, never to a dead one.

**`StartLimit*` live in `[Unit]`.** systemd honours them nowhere else. In
`[Service]` they read as configured and do nothing — it will tell you so with
"Unknown key ..., ignoring", which is easy to miss because the unit still starts.

**`Type=oneshot` with `RemainAfterExit=yes`.** This unit's job is to *create* the
session, not to be it. Restart supervision belongs to `macf.supervisor`, which
owns the client process; a `Restart=` here would fight it.

**The interpreter is absolute and unversioned.** The unit's shell is
non-interactive and inherits nothing from the operator's profile — an earlier
boot path used `bash -lc` and resolved a python without the `macf` module,
because `~/.bashrc` early-returns for non-interactive shells. The unversioned
`python3` beside the interpreter is preferred so a minor-release upgrade does not
leave the unit pointing at a path that no longer exists.

**The child wrapper nudges twice.** The client re-asks its workspace-trust prompt
when launched under the supervisor, and `SessionStart:resume` hands the turn back
to a user who is not attached. Both strand an unattended session; both are
handled in the wrapper rather than left for whoever notices the agent went quiet.

**Continuity is the default.** The child runs `claude -c`. Starting a *new*
session must be a deliberate act, because an unattended restart that silently
began a fresh conversation would discard the agent's working context with nothing
to show it had happened.

## macOS

**Documented, not tested.** The equivalent on macOS is a `launchd` user agent in
`~/Library/LaunchAgents/` with `RunAtLoad` and `KeepAlive`, wrapping the same
tmux + supervisor invocation. `systemctl --user enable --now` becomes
`launchctl bootstrap gui/$(id -u) <plist>`, and `systemctl --user stop` becomes
`launchctl bootout`. The `$${BASE}` escaping concern is systemd-specific and does
not apply; the first-party flag requirement does.

This path has never been exercised. Treat it as a starting point rather than a
recipe, and do not report it as working until someone has run it.
