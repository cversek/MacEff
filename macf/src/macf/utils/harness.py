"""Render the persistent agent harness from live parameters.

The harness is a supervised, detached, continuity-anchored Claude Code session:
a systemd user unit starts a tmux session, tmux runs ``macf.supervisor``, and the
supervisor runs the client through a child wrapper. It survives client restarts
and operator detach, and it is what makes an unattended autonomous session
possible at all.

It existed for a while as a hand-edited unit on a single host with a real
username in it. That is why this module exists rather than a ``.sample`` file:
the stored copy had already drifted from the live one and was missing the very
environment flag that makes it work, so anyone installing from the artifact
would have got a silently degraded harness. A rendered unit cannot drift from
itself.

Every non-obvious line below cost a real incident to learn. The comments say
which, because the point of moving this into the framework is that the next
operator does not pay for them again.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# The port the supervised proxy listens on by default. Attachment is probed,
# never assumed — see the ExecStart comment on degradation.
DEFAULT_PROXY_PORT = 8019

# Claude Code's long-context window. Carried explicitly because the unit's shell
# is non-interactive and inherits nothing from the operator's shell profile.
DEFAULT_CONTEXT_WINDOW = 1_000_000

# Seconds to wait for the proxy to answer before falling back to a direct
# connection. Short: this runs on every harness start, including at boot.
PROXY_PROBE_TIMEOUT = 2


@dataclass(frozen=True)
class HarnessParams:
    """Everything the rendered artifacts need, and nothing host-specific beyond it.

    ``agent`` names the unit, the tmux session and the supervisor instance. It is
    the only identifier that appears in the published unit name, so it should be
    a short slug rather than a person's login.
    """

    agent: str
    home: Path
    python: Path
    macf_tools: Path
    child_path: Path
    proxy_port: int = DEFAULT_PROXY_PORT
    context_window: int = DEFAULT_CONTEXT_WINDOW
    term: str = "xterm-256color"
    path_prepend: tuple = ()

    @property
    def unit_name(self) -> str:
        return f"cc-harness-{self.agent}.service"

    @property
    def env_path(self) -> str:
        parts = list(self.path_prepend) + [
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]
        return ":".join(parts)


def default_params(agent: Optional[str] = None, home: Optional[Path] = None) -> HarnessParams:
    """Derive parameters from the running environment.

    Resolved rather than guessed: the interpreter is the one currently executing,
    because the ``macf`` package lives in it and a bare ``python3`` in a
    non-interactive shell resolves elsewhere — which is exactly how an earlier
    boot path ended up without the module.
    """
    home = Path(home) if home else Path(os.environ.get("MACEFF_AGENT_HOME_DIR") or Path.home())
    agent = agent or os.environ.get("MACEFF_AGENT_NAME") or "agent"
    # Prefer the unversioned python3 beside the running interpreter. sys.executable
    # is often versioned (python3.10), and baking that into a unit pins the harness
    # to a specific minor release — an interpreter upgrade would leave a unit
    # pointing at a path that no longer exists, and the failure would surface at
    # boot as a session that simply never appeared.
    python = Path(sys.executable)
    unversioned = python.parent / "python3"
    if unversioned.exists():
        python = unversioned
    macf_tools = Path(shutil.which("macf_tools") or (python.parent / "macf_tools"))
    return HarnessParams(
        agent=agent,
        home=home,
        python=python,
        macf_tools=macf_tools,
        child_path=home / ".local" / "bin" / f"maceff_cc_child_{agent}",
        path_prepend=(str(python.parent), str(home / ".local" / "bin")),
    )


def render_unit(p: HarnessParams, attach_proxy: bool = True) -> str:
    """Render the systemd user unit.

    Four properties of this text are load-bearing and each has a test:

    1. ``$${BASE}`` is escaped. systemd expands ``$VAR``/``${VAR}`` in ``Exec*``
       using the UNIT's environment before any shell runs. ``BASE`` is not a unit
       variable, so an unescaped ``${BASE}`` was substituted with an empty string
       and the shell's own assignment never mattered — the proxy opt-in was
       silently inert, with only "Referenced but unset environment variable" in
       the journal.
    2. The first-party flag is emitted in the SAME assignment as the base URL.
       Their separation is what let the context-window defect survive for months.
    3. Proxy attachment is probed and degrades to direct. A dead proxy must
       degrade to a direct agent, never to a dead one.
    4. ``StartLimit*`` directives, when emitted, go in ``[Unit]``. systemd honours
       them nowhere else, so in ``[Service]`` they read as configured and do
       nothing.
    """
    proxy_url = f"http://localhost:{p.proxy_port}"
    probe_url = f"http://127.0.0.1:{p.proxy_port}/"

    if attach_proxy:
        # INVARIANT 2: base URL and first-party flag in one assignment. Never
        # split these — the flag is what keeps the long-context window, and a
        # base URL without it silently drops the client to the 200K fallback
        # while every UI surface continues to display the full window.
        base_branch = (
            f'BASE=""; '
            f'if curl -s --max-time {PROXY_PROBE_TIMEOUT} -o /dev/null {probe_url}; then '
            f'BASE="ANTHROPIC_BASE_URL={proxy_url} _CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1 "; '
            f'fi; '
        )
        wants = "\nAfter=network-online.target macf-proxy.service\nWants=network-online.target macf-proxy.service"
    else:
        base_branch = 'BASE=""; '
        wants = "\nAfter=network-online.target\nWants=network-online.target"

    # INVARIANT 1: $${BASE} — a literal ${BASE} must reach bash.
    exec_start = (
        f"ExecStart=/bin/bash -c '{base_branch}"
        f'tmux has-session -t {p.agent} 2>/dev/null || '
        f'tmux new-session -d -s {p.agent} '
        f'"$${{BASE}}{p.python} -m macf.supervisor _run_loop '
        f'--name {p.agent} --delay 5 --tmux-session {p.agent} -- {p.child_path}"\''
    )

    return f"""# MacEff persistent Claude Code harness — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {p.agent}
#
# The unit's shell is non-interactive, so it inherits nothing from the operator's
# profile: interpreter, PATH and context window are all made explicit here. An
# earlier boot path relied on `bash -lc` and silently resolved a python without
# the macf module, because ~/.bashrc early-returns for non-interactive shells.
[Unit]
Description=Claude Code persistent TUI harness (tmux + macf supervisor, continuity-anchored){wants}
# INVARIANT: StartLimit* belong in [Unit]. systemd honours them nowhere else —
# placed in [Service] they read as configured and do nothing at all.
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
# oneshot + RemainAfterExit: this unit's job is to CREATE the session, not to be
# the session. Restart supervision belongs to macf.supervisor, which owns the
# client process and restarts it in place; a Restart= here would fight it.
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={p.home}
Environment=MACF_CONTEXT_WINDOW={p.context_window}
Environment=PATH={p.env_path}
Environment=TERM={p.term}

# Idempotent: creates the detached session only when absent, so re-running is safe.
{exec_start}

# The client re-asks its workspace-trust prompt when launched under the
# supervisor. At boot nobody is attached to answer, so nudge Enter twice.
# Harmless when no prompt is showing.
ExecStartPost=/bin/bash -c 'sleep 20; tmux send-keys -t {p.agent} Enter 2>/dev/null; sleep 8; tmux send-keys -t {p.agent} Enter 2>/dev/null; true'

# Stop the SUPERVISOR, not the child. Killing the child just makes the
# supervisor restart it, so a stop that targets the child is not a stop.
ExecStop=/bin/bash -c 'for f in /tmp/macf/auto-restart/*.json; do grep -q "{p.agent}" "$f" 2>/dev/null && grep -q "running" "$f" 2>/dev/null && {p.macf_tools} auto-restart disable "$(basename "$f" .json)"; done; true'

[Install]
WantedBy=default.target
"""


def render_child(p: HarnessParams) -> str:
    """Render the supervised child entrypoint.

    The supervisor has no post-restart hook, and two things reliably strand an
    unattended session after a restart: the workspace-trust prompt, and
    SessionStart returning the turn to a user who is not there. Both are nudged
    here rather than left to whoever notices the agent has gone quiet.
    """
    return f"""#!/bin/bash
# MacEff harness child wrapper — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {p.agent}
#
# The supervisor has no post-restart hook. Two things strand an unattended
# session on relaunch and both are handled below.
SESS="${{MACEFF_TMUX_SESSION:-{p.agent}}}"
MACF={p.macf_tools}
(
  # 1. The client can park at the workspace-trust prompt. Enter is a no-op on an
  #    empty input, so this is safe when no prompt is showing.
  sleep 18; tmux send-keys -t "$SESS" Enter 2>/dev/null
  sleep 12
  # 2. SessionStart:resume hands the turn back to the user. With nobody attached
  #    an autonomous session would idle at the prompt forever, so if persistent
  #    AUTO_MODE is active, type a re-orientation prompt and submit it.
  if "$MACF" mode get 2>/dev/null | grep -q AUTO_MODE; then
    tmux send-keys -t "$SESS" "AUTO_MODE RESUME: session restarted (SessionStart:resume returned the turn with nobody attached). Re-orient via the task tree and continue authorized scoped work." 2>/dev/null
    # Paste-detection debounces an Enter that follows a fast text burst: settle,
    # then Enter twice. The second is a no-op if the first already submitted.
    sleep 3; tmux send-keys -t "$SESS" Enter 2>/dev/null
    sleep 2; tmux send-keys -t "$SESS" Enter 2>/dev/null
  fi
) &

# Continuity is the DEFAULT. `-c` resumes the prior conversation; starting a new
# one must be a deliberate act, because an unattended restart that silently
# began a fresh session would discard the agent's working context with nothing
# to show that it had happened.
exec claude -c "$@"
"""


def render_tmux_conf(p: HarnessParams) -> str:
    """Terminal baseline for TUI fidelity across attach and detach."""
    return f"""# MacEff harness tmux baseline — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {p.agent}
set -g default-terminal "{p.term}"
set -ga terminal-overrides ",*256col*:Tc"
# A short escape delay keeps the client's key handling responsive; the default
# 500ms makes a TUI feel broken on attach.
set -sg escape-time 10
set -g history-limit 50000
set -g mouse on
"""
