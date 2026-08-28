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
    start_path: Optional[Path] = None
    functions_path: Optional[Path] = None
    registry_dir: Optional[Path] = None
    # Channel plugins the supervised client must load. Empty by default and
    # never guessed: this is the agent's inbound link when nobody is at the
    # terminal, and a render that silently dropped it would take the agent
    # off the air in exactly the unattended case the harness exists to serve.
    channels: tuple = ()
    # What the operator TYPES. Deliberately separate from `agent`: the session
    # and unit derive from the Calling Card so they are traceable to an
    # identity, but nobody is going to type
    # `maceff_TheHarborMaster_ee5cd8_harness_launch`. Traceability is a property
    # the machine needs; brevity is a property the hand needs, and forcing one
    # identifier to serve both is what produced the untraceable nickname this
    # replaces.
    shell_prefix: Optional[str] = None
    # Where the supervised session starts. NOT cosmetic: `claude -c` resolves
    # which conversation to resume from the working directory, so an unset
    # value means continuity depends on wherever the caller happened to be
    # standing. A launch from the login home resumes a different conversation
    # than a launch from the project, and neither reports a substitution.
    # None keeps the previous behaviour (inherit the caller's cwd).
    project_dir: Optional[Path] = None
    proxy_port: int = DEFAULT_PROXY_PORT
    context_window: int = DEFAULT_CONTEXT_WINDOW
    term: str = "xterm-256color"
    path_prepend: tuple = ()

    @property
    def unit_name(self) -> str:
        return f"cc-harness-{self.agent}.service"

    @property
    def start(self) -> Path:
        """Where the shared start script lives.

        Defaulted rather than required so existing callers that build params by
        hand keep working; the default sits beside the child wrapper.
        """
        return self.start_path or (self.child_path.parent / f"maceff_harness_start_{self.agent}")

    @property
    def functions(self) -> Path:
        return self.functions_path or (self.home / ".maceff" / f"harness_functions_{self.agent}.bash")

    @property
    def settings_path(self) -> Path:
        """Where the install-time choices are remembered.

        Channels and the shell prefix cannot be re-derived from the environment,
        so without this a later ``install --check`` renders DIFFERENT artifacts
        and reports drift that does not exist — and a ``--force`` reinstall run
        on that false report would silently strip the channel, taking the agent
        off the air with nothing to see. The generator can only be authoritative
        about what it can reproduce.
        """
        return self.home / ".maceff" / f"harness_{self.agent}.json"

    @property
    def prefix(self) -> str:
        """Short handle for the generated shell functions.

        Defaults to the moniker half of the Calling Card, lowercased — the part
        a human already says out loud when naming the agent.
        """
        if self.shell_prefix:
            return self.shell_prefix
        head, sep, _tail = self.agent.rpartition("_")
        return (head if sep else self.agent).lower()

    @property
    def log_path(self) -> Path:
        """Where the child's own output is kept.

        The pane is not a log. It scrolls, it dies with the session, and it is
        unreadable from a phone. Three launch failures in one evening printed
        their explanation into a pane that vanished before anyone could read it.
        """
        return self.home / ".maceff" / f"harness_{self.agent}.log"

    @property
    def registry(self) -> Path:
        """Where the supervisor writes its per-process registry.

        Taken from the supervisor rather than restated, because it has already
        moved once: a shared ``/tmp/macf/auto-restart`` is owned by whichever uid
        creates it first, so it became per-user. Any copy of the old literal
        still silently matches nothing — which is not a crash but a stop that
        stops nothing, and an "is it running" check that always answers no.
        """
        if self.registry_dir is not None:
            return self.registry_dir
        from ..supervisor import REGISTRY_DIR
        return REGISTRY_DIR

    @property
    def env_path(self) -> str:
        parts = list(self.path_prepend) + [
            "/usr/local/bin",
            "/usr/bin",
            "/bin",
        ]
        return ":".join(parts)


def installed_agents(unit_dir: Optional[Path] = None) -> list:
    """Agent slugs that actually have a harness unit installed here."""
    unit_dir = unit_dir or (Path.home() / ".config" / "systemd" / "user")
    if not unit_dir.is_dir():
        return []
    # The watchdog unit shares the prefix but is not an agent. Without this it
    # would enumerate as an agent literally named "<agent>-watch", which then
    # makes resolution "ambiguous" and stops every harness command that resolves
    # by enumeration -- an installed helper breaking the thing it helps.
    return sorted(
        f.name[len("cc-harness-"):-len(".service")]
        for f in unit_dir.glob("cc-harness-*.service")
        if not f.name.endswith("-watch.service")
    )


def resolve_agent(explicit: Optional[str] = None,
                  unit_dir: Optional[Path] = None) -> "tuple":
    """Resolve which agent this harness command is about, and say how.

    Returns ``(agent, source)``. The source is not decoration — it is the whole
    point. ``harness status`` used to default the agent to the literal string
    ``agent`` and then print ``unit: ... (ABSENT)`` while a healthy harness ran
    under another name. Nothing in that output was false, and it still read as
    "there is no harness here", because **the output never said the name was a
    guess**. A reader cannot discount a default they cannot see.

    Order: explicit flag, then the environment override, then the agent's own
    Calling Card, then the single installed unit if there is exactly one. When
    several are installed the caller is expected to list them rather than pick;
    ``source == "ambiguous"`` says so, and the candidates come back in place of
    a name.
    """
    if explicit:
        return explicit, "flag"
    env = os.environ.get("MACEFF_AGENT_NAME")
    if env:
        return env, "MACEFF_AGENT_NAME"
    try:
        from .identity import get_agent_identity, session_identifier
        card = get_agent_identity()
        # 'unknown' is what identity returns when no UUID resolves; deriving a
        # session name from it would manufacture an identifier for an agent
        # whose identity is precisely what could not be established.
        if card and not card.endswith("@unknown"):
            return session_identifier(card), "calling card"
    except Exception:
        pass
    units = installed_agents(unit_dir)
    if len(units) == 1:
        return units[0], "the only installed unit"
    if len(units) > 1:
        return units, "ambiguous"
    return "agent", "default"


def load_settings(p: HarnessParams) -> HarnessParams:
    """Re-apply the choices recorded at install time.

    Explicit flags win; this only fills what was not given, so a check run with
    no flags reproduces the installed artifacts instead of inventing new ones.
    """
    import json
    from dataclasses import replace
    try:
        data = json.loads(p.settings_path.read_text())
    except (OSError, ValueError):
        return p
    return replace(
        p,
        channels=p.channels or tuple(data.get("channels") or ()),
        shell_prefix=p.shell_prefix or data.get("shell_prefix"),
        project_dir=p.project_dir or (Path(data["project_dir"]) if data.get("project_dir") else None),
    )


def save_settings(p: HarnessParams) -> None:
    """Record what cannot be re-derived, so the generator stays authoritative."""
    import json
    p.settings_path.parent.mkdir(parents=True, exist_ok=True)
    p.settings_path.write_text(json.dumps(
        {"agent": p.agent, "channels": list(p.channels), "shell_prefix": p.shell_prefix,
         "project_dir": str(p.project_dir) if p.project_dir else None},
        indent=2) + "\n")


def default_params(agent: Optional[str] = None, home: Optional[Path] = None) -> HarnessParams:
    """Derive parameters from the running environment.

    Resolved rather than guessed: the interpreter is the one currently executing,
    because the ``macf`` package lives in it and a bare ``python3`` in a
    non-interactive shell resolves elsewhere — which is exactly how an earlier
    boot path ended up without the module.
    """
    home = Path(home) if home else Path(os.environ.get("MACEFF_AGENT_HOME_DIR") or Path.home())
    resolved, _source = resolve_agent(agent)
    # An ambiguous resolution is a list of candidates; rendering for "the first
    # one" would silently pick an agent. Callers that can ask are expected to
    # use resolve_agent() directly and surface the choice.
    agent = resolved if isinstance(resolved, str) else "agent"
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
        start_path=home / ".local" / "bin" / f"maceff_harness_start_{agent}",
        functions_path=home / ".maceff" / f"harness_functions_{agent}.bash",
        path_prepend=(str(python.parent), str(home / ".local" / "bin")),
    )


def render_start(p: HarnessParams, attach_proxy: bool = True) -> str:
    """Render the one script that decides whether to create the session.

    This exists because the decision had three implementations — the unit, an
    operator shell function, and a stored artifact — which is not a style
    complaint. They disagreed, and the disagreement was silent: the shell
    function set ``ANTHROPIC_BASE_URL`` without the first-party flag, so a
    harness launched from the terminal ran on a 200K window while every surface
    reported 1M. One implementation cannot disagree with itself, so systemd and
    the shell now call this same script.

    The other half of the script is the identity guard. Establishing that the
    harness is already up is harder than it looks, and the two obvious checks
    are both wrong in ways observed on a live host:

    * ``tmux has-session -t <agent>`` matches a NAME. On 2026-07-29 an unrelated
      ssh login owned the name, the guard matched, and the harness silently
      never started — there was no error to see, because a session did exist.
    * ``pgrep -f 'macf.supervisor ... --name <agent>'`` matches the TMUX SERVER.
      When tmux starts a server it keeps the command it was asked to run in its
      own argv, so this reports a live supervisor for as long as the server
      lives — nine days after the supervisor exited, when measured on
      2026-08-07.

    So identity is taken from the supervisor's own registry, which is keyed by
    the supervisor's pid, and then confirmed against the process table: an entry
    can outlive its process, and a pid can be recycled.

    Every ``-t`` target is written ``=<name>``, which forces tmux to match the
    session name EXACTLY. Without it tmux resolves a target by prefix, so
    ``-t thm`` matches a session called ``thm-stale-ssh`` — and "rename it out of
    the way" is exactly the remedy an operator reaches for, so the workaround for
    a name collision silently failed to resolve the collision. Measured on tmux
    3.6, 2026-08-07: the harness still reported its session "up" nine days after
    the only session by that prefix had been renamed and handed to an ssh login.
    """
    proxy_url = f"http://localhost:{p.proxy_port}"
    probe_url = f"http://127.0.0.1:{p.proxy_port}/"

    if attach_proxy:
        # INVARIANT: the base URL and the first-party flag are ONE assignment.
        # Splitting them is what cost months of unexplained early compaction —
        # a base URL whose host is not api.anthropic.com makes the client stop
        # extending the long-context window and fall back to 200K, silently,
        # while every UI surface keeps displaying the full window.
        probe = f"""if curl -s --max-time {PROXY_PROBE_TIMEOUT} -o /dev/null {probe_url}; then
  BASE="ANTHROPIC_BASE_URL={proxy_url} _CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1 "
fi"""
    else:
        probe = "# proxy attachment not configured for this agent"

    return f"""#!/bin/bash
# MacEff harness start — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {p.agent} --what start
#
# The single implementation of "create the session unless it is already ours".
# systemd's ExecStart and the operator's shell function both call this, because
# when they each had their own copy the copies drifted and the drift was silent.
#
# Exit codes: 0 created or already running; 3 the session NAME is held by
# something that is not this harness (a decision for a human, not for a script).
set -u

AGENT={p.agent}
SESSION="$AGENT"

# --- identity -------------------------------------------------------------
# Which pid, if any, is a LIVE supervisor for this agent. Read the module
# docstring before replacing this with something shorter; the two shorter
# checks are both known to report a harness that is not there.
harness_supervisor_pid() {{
  local f pid
  for f in {p.registry}/*.json; do
    [ -e "$f" ] || continue
    grep -q "\\"name\\": \\"$AGENT\\"" "$f" || continue
    grep -q '"status": "running"' "$f" || continue
    pid=${{f##*/}}; pid=${{pid%.json}}
    # The registry entry outlives the process it describes, so liveness is
    # confirmed here rather than assumed from the file existing...
    kill -0 "$pid" 2>/dev/null || continue
    # ...and the pid may have been recycled by something unrelated, so the
    # process is confirmed to still BE a supervisor.
    ps -o args= -p "$pid" 2>/dev/null | grep -q 'macf\\.supervisor' || continue
    printf '%s\\n' "$pid"
    return 0
  done
  return 1
}}

if pid=$(harness_supervisor_pid); then
  if tmux has-session -t "=$SESSION" 2>/dev/null; then
    echo "[harness] already running (supervisor $pid, session $SESSION)"
    exit 0
  fi
  # A live supervisor with no session is not a state to start over; starting a
  # second one would give this agent two clients writing one task store.
  echo "[harness] supervisor $pid is running but session '$SESSION' is gone." >&2
  echo "[harness] stop it first: {p.macf_tools} auto-restart disable $pid" >&2
  exit 3
fi

if tmux has-session -t "=$SESSION" 2>/dev/null; then
  # The 2026-07-29 failure, now said out loud instead of silently attached to.
  echo "[harness] ERROR: a tmux session named '$SESSION' exists but hosts no" >&2
  echo "[harness] macf supervisor, so it is not this harness. Launch has NOT" >&2
  echo "[harness] started anything -- the previous behaviour was to attach to" >&2
  echo "[harness] whatever held the name, which is how the harness once stayed" >&2
  echo "[harness] down for days without an error." >&2
  echo "[harness]   inspect:      tmux attach -t =$SESSION" >&2
  echo "[harness]   move aside:   tmux rename-session -t =$SESSION $SESSION-stale" >&2
  exit 3
fi

# --- start ----------------------------------------------------------------
BASE=""
# Probed, never assumed: a dead proxy must degrade to a direct agent rather
# than to no agent at all.
{probe}

# Everything the session needs is stated HERE. The launching shell's exported
# environment does not reach a command started with `tmux new-session` — the
# command runs under the tmux SERVER, which may have been created days earlier
# by an unrelated login (verified 2026-08-07: an exported probe variable did
# not arrive, and the server in question predated the shell by nine days).
# The working directory is DECLARED, and it decides which conversation resumes.
# `claude -c` keys continuity off the cwd, so inheriting the caller's directory
# makes continuity depend on where a human happened to be standing. An absent or
# deleted directory is REPORTED rather than silently substituted -- falling back
# without a word is how a resume quietly lands in a different conversation.
PROJECT_DIR="{p.project_dir or ''}"
CD_ARG=()
if [ -n "$PROJECT_DIR" ]; then
  if [ -d "$PROJECT_DIR" ]; then
    CD_ARG=(-c "$PROJECT_DIR")
  else
    echo "[harness] WARNING: declared project dir '$PROJECT_DIR' does not exist;" >&2
    echo "[harness] starting in $PWD instead -- 'claude -c' may resume a DIFFERENT" >&2
    echo "[harness] conversation than the one this agent was working in." >&2
  fi
fi
tmux new-session -d -s "$SESSION" "${{CD_ARG[@]}}" "MACF_CONTEXT_WINDOW={p.context_window} TERM={p.term} $BASE{p.python} -m macf.supervisor _run_loop --name $AGENT --delay 5 --tmux-session $SESSION -- {p.child_path}" \\; set-option -t "=$SESSION" remain-on-exit on
# ^ remain-on-exit is chained into the SAME tmux invocation, not run after it.
# Without this a pane whose command dies immediately can take the session with
# it before a second `tmux` process gets to set the option -- so the one case
# the option exists for, a launch that fails instantly, is the case it would
# most often miss. Keeping a dead pane readable is why this is here at all: the
# same failure showed up three times in one evening as nothing but "[exited]"
# and a shell prompt, the explanation printed and discarded each time.

echo "[harness] started session '$SESSION'"
echo "[harness] child log: {p.log_path}"
"""


def render_unit(p: HarnessParams, attach_proxy: bool = True) -> str:
    """Render the systemd user unit.

    ``ExecStart`` delegates to the rendered start script rather than carrying
    its own copy of the launch logic. That is not tidiness: the unit and the
    operator's shell function each used to carry a copy, they drifted, and the
    drift was a silently degraded context window. It also removes a whole class
    of systemd escaping hazard from this file — an earlier ``ExecStart`` had to
    write ``$${BASE}`` because systemd expands ``$VAR`` in ``Exec*`` from the
    UNIT's environment before any shell runs, and the one time it was written
    unescaped the proxy opt-in became inert with nothing but "Referenced but
    unset environment variable" in the journal.

    Two properties of what remains are load-bearing and each has a test:

    1. ``ExecStart`` invokes the start script, so there is exactly one
       implementation of the decision to create a session.
    2. ``StartLimit*`` directives, when emitted, go in ``[Unit]``. systemd
       honours them nowhere else, so in ``[Service]`` they read as configured
       and do nothing at all.
    """
    if attach_proxy:
        wants = "\nAfter=network-online.target macf-proxy.service\nWants=network-online.target macf-proxy.service"
    else:
        wants = "\nAfter=network-online.target\nWants=network-online.target"

    exec_start = f"ExecStart={p.start}"

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

# Idempotent, and safe to re-run: the start script establishes whether THIS
# harness is already up before creating anything. Re-running is exactly when a
# name-only check goes wrong, because that is when someone else may hold the
# name — so the check lives in one script both entry points share.
{exec_start}

# The client re-asks its workspace-trust prompt when launched under the
# supervisor. At boot nobody is attached to answer, so nudge Enter twice.
# Harmless when no prompt is showing.
ExecStartPost=/bin/bash -c 'sleep 20; tmux send-keys -t ={p.agent} Enter 2>/dev/null; sleep 8; tmux send-keys -t ={p.agent} Enter 2>/dev/null; true'

# Stop the SUPERVISOR, not the child. Killing the child just makes the
# supervisor restart it, so a stop that targets the child is not a stop.
ExecStop=/bin/bash -c 'for f in {p.registry}/*.json; do grep -q "{p.agent}" "$f" 2>/dev/null && grep -q "running" "$f" 2>/dev/null && {p.macf_tools} auto-restart disable "$(basename "$f" .json)"; done; true'

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
    channels = f" --channels {','.join(p.channels)}" if p.channels else ""
    return f"""#!/bin/bash
# MacEff harness child wrapper — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {p.agent}
#
# The supervisor has no post-restart hook. Two things strand an unattended
# session on relaunch and both are handled below.
SESS="${{MACEFF_TMUX_SESSION:-{p.agent}}}"
MACF={p.macf_tools}
# NO BLIND KEYSTROKES ON LAUNCH. A timed `sleep 18; send-keys Enter` used to
# live here to clear the workspace-trust prompt, justified as "Enter is a no-op
# on an empty input". That justification only holds if the thing on screen is
# the prompt we expect. The client's startup dialogs are not stable across
# versions, and an unattended Enter does not accept a known prompt -- it accepts
# WHATEVER is focused, including a resume dialog whose default is to summarize
# rather than continue as-is. Silently discarding the session's own context is
# not a recoverable mistake, and nothing would record that a choice was made.
#
# Operator directive: a menu that a human has not seen is a menu a machine must
# not answer. First launch is the operator's to select. If a trust prompt blocks
# an unattended restart, the fix is to grant trust beforehand -- state that
# survives restarts -- not to guess at the keyboard.

# Continuity is the DEFAULT. `-c` resumes the prior conversation; starting a new
# one must be a deliberate act, because an unattended restart that silently
# began a fresh session would discard the agent's working context with nothing
# to show that it had happened.
#
# Channels are part of that continuity. Losing them costs no error and no log
# line -- the session comes up, the terminal looks right, and the agent is
# simply unreachable from outside. It has happened here: a resume that dropped
# --channels took the inbound link down with nothing to see.
# LOG THE PANE FROM OUTSIDE THE CHILD. `tmux pipe-pane` copies what the pane
# renders to a file without touching any of the client's descriptors, so the
# client keeps the terminal tmux gave it.
#
# The previous form, `exec > >(tee -a "$LOG") 2>&1`, was a redirection, and it
# replaced the client's stdout with a PIPE. That matters more than it looks:
# a terminal is not a cosmetic property, it is what an interactive client
# inspects to decide whether to BE interactive. Deprived of one it can render
# a single turn and exit 0 -- whereupon the supervisor, behaving exactly as
# designed, restarts it. The result is a restart loop in which no layer is
# misbehaving and no error is logged anywhere, which is why it survived a
# night of reading logs that all said things were fine.
#
# The diagnostic caused the fault it was added to diagnose. Measured, not
# reasoned: in a tmux pane `[ -t 1 ]` is true, and after that exec it is false
# (tests/test_harness_runtime.py).
#
# pipe-pane is also strictly better as logging: it captures what the pane
# actually showed, including anything written straight to the terminal, which
# a stdout redirect never sees. `-o` toggles off any prior pipe first so a
# restart does not stack writers onto one file.
LOG="{p.log_path}"
mkdir -p "$(dirname "$LOG")"
{{ echo; echo "=== $(date -Is) starting: claude -c{channels} ==="; }} >> "$LOG"
# NO -t: pipe-pane takes a PANE target, and `=name` is exact-match syntax for a
# SESSION. `pipe-pane -t "=$SESS"` therefore fails with "can't find pane" every
# single time -- which the first version of this line hid behind
# `2>/dev/null || true`, producing a log containing start markers and nothing
# else. Run from inside the pane, pipe-pane defaults to $TMUX_PANE, which is
# both correct and unambiguous: no name resolution, so no prefix-match hazard.
#
# The failure is reported INTO the log rather than swallowed. A diagnostic that
# can fail silently is the thing being diagnosed here; if the pipe does not
# attach, whoever reads this file later must learn that from the file.
if [ -n "$TMUX_PANE" ]; then
  tmux pipe-pane -o "cat >> '$LOG'" \
    || echo "=== pipe-pane FAILED: pane output is NOT captured below ===" >> "$LOG"
else
  echo "=== not running inside tmux: pane output is NOT captured below ===" >> "$LOG"
fi

# A RESUME MUST CARRY A PROMPT. `claude -c` with no prompt can refuse to resume
# outright -- "No deferred tool marker found in the resumed session ... Provide a
# prompt to continue the conversation" -- and then exit 1. The supervisor does
# exactly what it should with that: it retries, forever, a command that cannot
# succeed. Measured A/B on one conversation, same minute: without a prompt, exit
# 1 every time; with one, the client came up.
#
# ARGUMENT ORDER IS LOAD-BEARING. `--channels` is VARIADIC: it keeps consuming
# following words, so a prompt placed after it is parsed as another channel and
# the client dies with "--channels entries must be tagged: <your prompt>". The
# prompt therefore goes first and the variadic flag goes LAST, where the only
# thing it can consume is its own values. Reproduced both ways before choosing.
#
# It also replaces a timing hack. The re-orientation used to be typed in by
# send-keys ~30s after launch, which meant guessing when the client was ready
# and defeating paste-detection with a double Enter. Passing it as the initial
# prompt is not a workaround for that -- it is the thing send-keys was
# approximating, done at the only moment that cannot race.
if "$MACF" mode get 2>/dev/null | grep -q AUTO_MODE; then
  PROMPT="AUTO_MODE RESUME: this session restarted. Re-orient via the task tree and continue authorized scoped work."
else
  PROMPT="Session resumed by the harness. Summarize where things stand and await instructions."
fi

exec claude -c "$PROMPT" "$@"{channels}
"""


def render_watchdog(p: HarnessParams) -> tuple:
    """Render a periodic health check that resurrects a dead session.

    The harness has a single point of failure that is easy to miss because the
    diagram hides it: **the supervisor is a child of the tmux server.** It
    restarts the client in place, which is what it is for, but if the tmux
    server itself dies the supervisor dies with it — and the main unit is
    ``oneshot`` with ``RemainAfterExit=yes``, so systemd neither notices nor
    acts. Supervision nested inside the thing whose death it should survive
    survives nothing. Observed: the session went away, two registry entries were
    left still claiming "running" because the cleanup never ran, and the harness
    stayed down until a human typed the launcher.

    The repair is cheap because the start script is already idempotent and
    already refuses to touch a name it does not own: run it on a timer. When the
    harness is healthy this costs one registry read and one ``has-session``;
    when it is gone, it comes back without anyone noticing it left.

    Returned as (service, timer) and installed only on request — a machine that
    resurrects an agent unattended is a decision for the operator, not a default.
    """
    service = f"""# MacEff harness watchdog — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {p.agent} --what watchdog
#
# Runs the SAME idempotent start script the boot unit runs. It exits 0 when the
# harness is already up and refuses (3) when the session name is held by
# something else, so a timer cannot start a second client or steal a name.
[Unit]
Description=Ensure the {p.agent} harness session exists
After=cc-harness-{p.agent}.service

[Service]
Type=oneshot
WorkingDirectory={p.home}
Environment=PATH={p.env_path}
ExecStart={p.start}
# 3 means "a session by this name exists and is not ours" — a state a human
# must resolve. Reporting it as failure is correct; retrying would not help.
SuccessExitStatus=0
"""
    timer = f"""# MacEff harness watchdog timer — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {p.agent} --what watchdog
[Unit]
Description=Periodically ensure the {p.agent} harness session exists

[Timer]
# First check shortly after boot, then steadily. A minute is well under the
# time it takes anyone to notice an agent has gone quiet, and the check is
# cheap enough that frequency is not the cost.
OnBootSec=2min
OnUnitActiveSec=1min
AccuracySec=10s
Unit=cc-harness-{p.agent}-watch.service

[Install]
WantedBy=timers.target
"""
    return service, timer


def render_launch_functions(p: HarnessParams) -> str:
    """Render the operator's shell entry points to the harness.

    These were the last hand-maintained copy of the harness. The unit and the
    child wrapper were moved into this generator precisely because a stored copy
    had drifted from the live one; the shell functions were left behind, drifted
    the same way, and drifted worse — a terminal launch set the proxy base URL
    without the first-party flag, so the operator's own session ran on a fifth of
    the context window it reported.

    Nothing here re-implements starting: ``launch`` calls the start script and
    then attaches. The functions exist for what a systemd unit cannot do, which
    is put a human at a terminal in front of the session.
    """
    a = p.agent          # session / unit / supervisor identity
    n = p.prefix         # what the operator types
    return f"""# MacEff harness shell functions — generated, do not hand-edit.
# Regenerate with: macf_tools harness generate --agent {a} --what functions
# Source this from your shell profile:  . {p.functions}
#
# These are entry points, not a second implementation. Creating the session is
# {p.start}, which systemd calls too, so a terminal
# launch and a boot launch cannot disagree about what they started.

# Terminal-window title: which agent am I attached to, and how did I get here.
__maceff_title()   {{ printf '\\033]0;%s\\007' "$1"; }}
__maceff_untitle() {{ printf '\\033]0;%s\\007' "${{USER}}@${{HOSTNAME}}: ${{PWD/#$HOME/\\~}}"; }}

# The supervisor registry is the source of truth for "is it up". Same reasoning
# as the start script: a session name proves nothing, and pgrep on the
# supervisor's command line matches the tmux server that merely carries it.
__maceff_{n}_supervisor_pid() {{
  local f pid
  for f in {p.registry}/*.json; do
    [ -e "$f" ] || continue
    grep -q '"name": "{a}"' "$f" || continue
    grep -q '"status": "running"' "$f" || continue
    pid=${{f##*/}}; pid=${{pid%.json}}
    kill -0 "$pid" 2>/dev/null || continue
    ps -o args= -p "$pid" 2>/dev/null | grep -q 'macf\\.supervisor' || continue
    printf '%s\\n' "$pid"; return 0
  done
  return 1
}}

# Create the session if needed, then put this terminal in front of it.
maceff_{n}_harness_launch() {{
  {p.start} || return $?
  __maceff_title "{a} via tmux on $(hostname)"
  # -d evicts other clients. Two clients of different geometries was the root
  # cause of the fragmented redraws; single-client is the discipline.
  tmux attach -d -t ={a}
  __maceff_untitle
}}

# Attach without creating: for joining a session that should already be up.
__maceff_{n}_attach() {{
  local flags="$1"
  tmux has-session -t ={a} 2>/dev/null || {{
    echo "no {a} session — use maceff_{n}_harness_launch" >&2; return 1
  }}
  __maceff_title "{a} via tmux on $(hostname)${{flags:+ [read-only]}}"
  tmux attach -t ={a} ${{flags:--d}}
  __maceff_untitle
}}
maceff_{n}_harness_attach() {{ __maceff_{n}_attach ""; }}
maceff_{n}_harness_watch()  {{ __maceff_{n}_attach "-r"; }}

# Clean stop from any login, including over ssh. Never bare-kill the tmux
# server: that leaves the supervisor to restart a client into nothing.
maceff_{n}_harness_stop() {{
  local pid
  pid=$(__maceff_{n}_supervisor_pid) || {{ echo "no running {a} supervisor found"; return 1; }}
  {p.macf_tools} auto-restart disable "$pid" && echo "harness {a} (supervisor $pid) disabled"
}}

# Reclaim from a remote client: evict, attach, and trigger one restart so the
# client re-measures THIS terminal. Without the restart it keeps the geometry of
# the terminal that attached first, which is the "untrimmed input box" symptom.
# The conversation survives, because the child wrapper resumes with -c.
maceff_{n}_harness_reclaim() {{
  local pid
  tmux has-session -t ={a} 2>/dev/null || {{
    echo "no {a} session — use maceff_{n}_harness_launch" >&2; return 1
  }}
  if pid=$(__maceff_{n}_supervisor_pid); then
    echo "[harness] reclaiming: evicting clients, re-measuring geometry (supervisor $pid)"
    ( setsid nohup bash -c "sleep 6; {p.macf_tools} auto-restart restart $pid" >/dev/null 2>&1 & )
  else
    echo "[harness] warning: no running supervisor; attaching without a restart" >&2
  fi
  __maceff_title "{a} via tmux on $(hostname) [reclaimed]"
  tmux attach -d -t ={a}
  __maceff_untitle
}}

# Status reports what IS, from the same sources the start script decides on, so
# it cannot claim a harness the launcher would refuse to reuse.
maceff_{n}_harness_status() {{
  local pid
  if pid=$(__maceff_{n}_supervisor_pid); then
    echo "supervisor: running (pid $pid)"
  else
    echo "supervisor: not running"
  fi
  if tmux has-session -t ={a} 2>/dev/null; then
    echo "session:    present (tmux -t {a})"
    # Say whose it is. A present session that is NOT ours is the failure this
    # whole family exists to stop being invisible.
    [ -n "${{pid:-}}" ] || echo "            ^ holds the name but is NOT this harness"
  else
    echo "session:    absent"
  fi
  {p.macf_tools} harness status --agent {a} 2>/dev/null
}}
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
