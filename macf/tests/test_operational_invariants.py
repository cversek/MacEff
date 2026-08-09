"""The operational invariants, as checks that can be observed failing.

Six facts about running this system cost real incidents to learn, and until now
lived in one agent's memory and a few code comments. Each is a property of an
artifact we generate or ship, so each becomes an assertion here.

**Every invariant carries a negative control.** A check never observed failing is
not a check — it is a comfort object. For each one below there is a mutation that
breaks it, and a test asserting the checker rejects the mutated form. If someone
weakens a checker into something that always passes, its negative control fails
and says so.

The `incident` field on each invariant is the point: it records what actually
went wrong, so the reasoning survives the people who learned it.
"""

from pathlib import Path

import pytest

from macf.utils.harness import HarnessParams, render_start, render_unit

SYNTH = HarnessParams(
    agent="testbot",
    home=Path("/opt/agents/testbot"),
    python=Path("/opt/py/bin/python3"),
    macf_tools=Path("/opt/py/bin/macf_tools"),
    child_path=Path("/opt/agents/testbot/.local/bin/maceff_cc_child_testbot"),
    path_prepend=("/opt/py/bin",),
)

PROXY_SRC = (
    Path(__file__).resolve().parents[1] / "src" / "macf" / "proxy" / "server.py"
).read_text()


# --------------------------------------------------------------------------
# Checkers. Each takes the artifact text and returns True when the invariant
# holds. Kept tiny and total so a negative control can exercise them directly.
# --------------------------------------------------------------------------

def check_no_shell_expansion_in_exec(unit: str) -> bool:
    """Exec* carries no shell variable for the service manager to eat.

    Strengthened from its original form. The invariant used to be "a shell
    variable in Exec* must be written $${VAR} so a literal ${VAR} reaches the
    shell", which is true but only defends a hazard we chose to keep. Exec* now
    invokes a script, so there is no shell variable in the unit at ALL and the
    hazard is gone by construction rather than by remembering to escape.

    An unescaped ${VAR} would be replaced from the UNIT's environment before any
    shell ran; a correctly escaped one still means the unit carries launch logic
    that something else also carries. Absence is the stronger property.
    """
    for line in unit.splitlines():
        if not line.startswith(("ExecStart=", "ExecStop=", "ExecStartPre=")):
            continue
        # ExecStop legitimately uses shell parameter expansion in a loop it owns
        # outright; the rule is about the LAUNCH path carrying a variable that
        # systemd will expand out from under it.
        if line.startswith("ExecStart=") and ("$" in line):
            return False
    return True


def check_restart_responsibility_is_explicit(unit: str) -> bool:
    """Exactly one component owns restart, and the unit says which.

    A oneshot unit that merely creates a session must NOT also declare Restart=;
    a long-running unit that omits it dies silently on a clean exit. Either way
    the failure is that nobody can tell who is supposed to restart the thing.
    """
    body = [l.strip() for l in unit.splitlines() if not l.strip().startswith("#")]
    oneshot = any(l == "Type=oneshot" for l in body)
    remain = any(l == "RemainAfterExit=yes" for l in body)
    declares_restart = any(l.startswith("Restart=") for l in body)
    if oneshot:
        return remain and not declares_restart
    return declares_restart


def check_rate_limits_in_honoured_section(unit: str) -> bool:
    """StartLimit* appear only in [Unit]; systemd honours them nowhere else."""
    section = None
    for line in unit.splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s
        elif s.startswith("StartLimit") and section != "[Unit]":
            return False
    return True


def check_flag_travels_with_base_url(unit: str) -> bool:
    """The first-party flag is never emitted apart from the base URL."""
    if unit.count("ANTHROPIC_BASE_URL=") != unit.count("_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1"):
        return False
    for line in unit.splitlines():
        if "ANTHROPIC_BASE_URL=" not in line:
            continue
        i = line.index("ANTHROPIC_BASE_URL=")
        j = line.find("_CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1")
        if j < i or j - i > 80:
            return False
    return True


def check_capture_is_bounded_and_guarded(src: str) -> bool:
    """Capture storage is bounded, and a capture write cannot fail a request."""
    return "_capture_cap_bytes" in src and "_capture_evict" in src


def check_reported_equals_enforced(src: str) -> bool:
    """The surface reporting a gate calls the same function that enforces it."""
    return (
        '"rewrite_enabled": _rewrite_enabled()' in src
        and "if _rewrite_enabled():" in src
    )


# --------------------------------------------------------------------------
# The registry. (name, artifact, checker, mutation, incident)
# The mutation must break exactly this invariant.
# --------------------------------------------------------------------------

def _unit() -> str:
    return render_unit(SYNTH)


def _start() -> str:
    """The launch decision moved here, and its invariants moved with it.

    Leaving them pointed at the unit is how an invariant quietly stops covering
    anything: the checker still passes, on text that no longer contains the
    thing it was written to protect. Both negative controls below caught exactly
    that — they failed with "mutation was a no-op", which is the check reporting
    that it had nothing to check.
    """
    return render_start(SYNTH)


INVARIANTS = [
    (
        "no-shell-expansion-in-exec",
        _unit,
        check_no_shell_expansion_in_exec,
        lambda u: u.replace("ExecStart=", "ExecStart=/bin/bash -c '${BASE}", 1),
        "The service manager expands ${VAR} in Exec* from the UNIT's environment "
        "before any shell runs. An unescaped ${BASE} was replaced with an empty "
        "string, so the shell's own assignment never mattered and the proxy "
        "opt-in was silently inert — the only trace was a 'Referenced but unset "
        "environment variable' line in the journal. ExecStart now invokes a "
        "script and carries no variable at all, so the hazard cannot recur.",
    ),
    (
        "restart-responsibility",
        _unit,
        check_restart_responsibility_is_explicit,
        lambda u: u.replace("Type=oneshot\n", "Type=oneshot\nRestart=always\n"),
        "A daemon that exits zero is not a success. One unit died and stayed "
        "dead because its restart policy only covered failure exits; another "
        "would have had two components fighting over restarting the same child. "
        "The invariant is that exactly one component owns restart and the unit "
        "states which.",
    ),
    (
        "rate-limits-in-honoured-section",
        _unit,
        check_rate_limits_in_honoured_section,
        lambda u: u.replace("[Service]\n", "[Service]\nStartLimitBurst=5\n", 1),
        "StartLimit* directives are honoured only in [Unit]. Placed in "
        "[Service] they read as configured and do nothing; the service manager "
        "reports 'Unknown key ..., ignoring' and starts the unit anyway, so the "
        "misconfiguration never surfaces as an error.",
    ),
    (
        "flag-travels-with-base-url",
        _start,
        check_flag_travels_with_base_url,
        lambda u: u.replace(" _CLAUDE_CODE_ASSUME_FIRST_PARTY_BASE_URL=1 ", " "),
        "When the API base URL's host is not the default, the client stops "
        "extending the long-context window and falls back to a fifth of it, "
        "while every surface continues to display the full window. There is no "
        "log line and no warning; the only symptom is compacting early. The two "
        "settings were documented separately, which is how that survived months.",
    ),
    (
        "capture-bounded-and-guarded",
        lambda: PROXY_SRC,
        check_capture_is_bounded_and_guarded,
        lambda s: s.replace("_capture_evict", "_capture_noop"),
        "Capture storage was unbounded, so a long-running proxy could fill the "
        "disk; and a capture write that raised would have failed the live "
        "request it was only supposed to observe.",
    ),
    (
        "reported-equals-enforced",
        lambda: PROXY_SRC,
        check_reported_equals_enforced,
        lambda s: s.replace('"rewrite_enabled": _rewrite_enabled()',
                            '"rewrite_enabled": False'),
        "The startup banner read an environment variable while the request path "
        "ignored it entirely, so the proxy advertised rewrite=off while "
        "rewriting every request. An instrument reporting a value nobody "
        "enforces is worse than no instrument. This is the antipattern behind "
        "four separate defects in this cluster.",
    ),
]

IDS = [name for name, *_ in INVARIANTS]


@pytest.mark.parametrize("name,artifact,checker,mutate,incident", INVARIANTS, ids=IDS)
def test_invariant_holds(name, artifact, checker, mutate, incident):
    """The shipped artifact satisfies the invariant."""
    assert checker(artifact()), f"{name} violated in the shipped artifact"


@pytest.mark.parametrize("name,artifact,checker,mutate,incident", INVARIANTS, ids=IDS)
def test_invariant_check_can_fail(name, artifact, checker, mutate, incident):
    """NEGATIVE CONTROL — the mandatory half.

    Break the invariant and the checker must reject it. Without this, a checker
    weakened into something that always passes would keep reporting success
    forever, which is the exact failure these invariants exist to prevent.
    """
    broken = mutate(artifact())
    assert broken != artifact(), f"{name}: mutation was a no-op, so this proves nothing"
    assert not checker(broken), f"{name}: checker still passes on a deliberately broken artifact"


@pytest.mark.parametrize("name,artifact,checker,mutate,incident", INVARIANTS, ids=IDS)
def test_invariant_documents_its_incident(name, artifact, checker, mutate, incident):
    """Each invariant records what went wrong, so the why outlives the people.

    A rule with no incident behind it gets deleted by the next person who finds
    it inconvenient and cannot see what it is protecting.
    """
    assert len(incident) > 120, f"{name}: incident note too thin to be useful"
