"""The primal daemon's names and paths, kept free of the declaration's models.

Split out of ``macf.pd.interface`` so a caller that only needs a name or a path, such
as the per-call hook asking whether this agent has a daemon (MIS-0002-R91), doesn't pay
for building the declaration's pydantic models on import. ``interface`` re-exports every
name here, so its callers are unchanged.

The card comes from an explicitly named agent home, never from the environment
(MIS-0002-R02 (pd_MUST-NOT_take_identity_from_env)), and one function names every
surface from it through ``session_identifier`` (MIS-0002-R06
(pd_identifiers_MUST_use_maceff_pd)).
"""
import json
import os
import stat
import sys
from pathlib import Path
from typing import Optional

from macf.utils.identity import session_identifier

#: MIS-0002-R06: every process, unit, label and socket name of a primal daemon carries it.
PD_IDENTIFIER = "maceff_pd"


class IdentityError(ValueError):
    """The agent home does not name an agent. The daemon refuses to start."""


# ============================================================================
# 1. Identity, names and paths
# ============================================================================

def agent_card(agent_home: Path) -> str:
    """The calling card of the agent whose home is *agent_home*, read only from that home.

    The name is ``agent_identity.calling_card`` (or ``moniker``) in
    ``<home>/.maceff/config.json``, and the suffix is the first six characters of
    ``<home>/.maceff_primary_agent.id``. No environment variable, no working directory,
    no fallback: ``get_agent_identity()`` reads ``MACEFF_AGENT_NAME`` first for a
    host-global agent, so a session and a daemon started by the outer tier, which has no
    such variable, could name different sockets for the same agent (MIS-0002-R02).
    """
    home = Path(agent_home)
    try:
        config = json.loads((home / ".maceff" / "config.json").read_text())
        uuid = (home / ".maceff_primary_agent.id").read_text().strip()
    except (OSError, ValueError) as e:
        raise IdentityError(f"{home} names no agent: {e}") from e
    identity = config.get("agent_identity") or {}
    name = next((identity[k].strip() for k in ("calling_card", "moniker")
                 if isinstance(identity.get(k), str) and identity[k].strip()), "")
    if not name or len(uuid) < 6:
        raise IdentityError(f"{home} names no agent: config.json needs agent_identity.calling_card "
                            f"and .maceff_primary_agent.id a UUID")
    return f"{name}@{uuid[:6]}"


def pd_id(card: str) -> str:
    """The per-agent part of every name: ``TheHarborMaster@ee5cd8`` -> ``TheHarborMaster_ee5cd8``.

    Several agents can share one login user, so every name carries the agent; and the
    card's ``@`` is substituted because systemd spells a template instance that way.
    """
    return session_identifier(card)


def systemd_unit(card: str) -> str:
    """The outer tier's unit on Linux: ``maceff_pd-<id>.service``."""
    return f"{PD_IDENTIFIER}-{pd_id(card)}.service"


def launchd_label(card: str) -> str:
    """The outer tier's label on macOS (MIS-0002-R05): ``maceff_pd.<id>``."""
    return f"{PD_IDENTIFIER}.{pd_id(card)}"


def name_this_process(name: str = PD_IDENTIFIER) -> bool:
    """Give this process the name ``ps``, ``top`` and ``pgrep`` show, so a daemon reads as
    ``maceff_pd`` in a process listing rather than as the interpreter (MIS-0002-R06). True when
    the name was set.

    Linux only, through ``prctl(PR_SET_NAME)``, which takes at most 15 bytes and leaves the
    command line alone, so ``pgrep -f macf.pd`` still finds it. A unit the daemon starts gets
    its own name at exec. macOS has no call that renames a running process, so this returns
    False there; the LaunchAgent names the daemon at exec instead, with ``maceff_pd`` as its
    ``argv[0]`` (``macf.platform.launchd``).
    """
    if not sys.platform.startswith("linux"):
        return False
    import ctypes
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        return libc.prctl(15, name.encode()[:15], 0, 0, 0) == 0   # 15: PR_SET_NAME
    except (OSError, AttributeError):
        return False


def runtime_dir() -> Path:
    """Where the daemon's sockets and record live: per user, never shared."""
    base = os.environ.get("XDG_RUNTIME_DIR")
    if base:
        return Path(base) / PD_IDENTIFIER
    return Path(f"/tmp/{PD_IDENTIFIER}-{os.getuid()}")


def ensure_runtime_dir(path: Optional[Path] = None) -> Path:
    """Create the runtime directory with mode 0700, or refuse an existing one that is not
    private: owned by another user, or open to its group or to others.

    Without ``XDG_RUNTIME_DIR`` the directory is in ``/tmp``, where anyone could have made
    it first, so this check is the difference between private and guessable.
    """
    path = path or runtime_dir()
    try:
        path.mkdir(mode=0o700, parents=False)
    except FileExistsError:
        pass
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode):
        raise OSError(f"{path} is not a directory; refusing it as the runtime directory")
    if info.st_uid != os.getuid():
        raise OSError(f"{path} is owned by uid {info.st_uid}, not this user; refusing it")
    if info.st_mode & 0o077:
        raise OSError(f"{path} is open to its group or others (mode {oct(info.st_mode & 0o777)}); refusing it")
    return path


def control_socket(card: str, base: Optional[Path] = None) -> Path:
    return (base or runtime_dir()) / f"{pd_id(card)}.control.sock"


def channel_socket(card: str, base: Optional[Path] = None) -> Path:
    return (base or runtime_dir()) / f"{pd_id(card)}.channel.sock"


def events_socket(card: str, base: Optional[Path] = None) -> Path:
    """The event stream's socket (persistent_layer 11.4), beside the control and channel sockets."""
    return (base or runtime_dir()) / f"{pd_id(card)}.events.sock"


def record_path(card: str, base: Optional[Path] = None) -> Path:
    return (base or runtime_dir()) / f"{pd_id(card)}.json"


#: Where a container's provisioning renders each agent's declaration from the deployment's
#: agents.yaml, owned by root in a directory the agent can't write: a run executes as the agent,
#: so a declaration in the agent's own home is one a run could rewrite before a daemon restart
#: (MIS-0002-R33 (run_MUST-NOT_change_schedules)). Hosts have none.
RENDERED_DECLARATIONS = Path("/etc/maceff/pd")


def rendered_declaration_path(agent_home: Path) -> Path:
    """Where the deployment renders this agent's declaration, keyed by the home's name, which
    in a container is the agent's account."""
    return RENDERED_DECLARATIONS / Path(agent_home).name / "declaration.json"


def declaration_path(agent_home: Path) -> Path:
    """The agent's declaration: the one the deployment rendered, when there is one, and
    otherwise the one in the agent's own home. Every reader goes through here, so the daemon,
    the readout and the outside watch read the same file. The outer tier holds none
    (MIS-0002-R04 (outer_tier_MUST-NOT_hold_agent_config))."""
    rendered = rendered_declaration_path(agent_home)
    if os.path.lexists(rendered):
        return rendered
    return Path(agent_home) / ".maceff" / "pd" / "declaration.json"


#: The owner a rendered declaration and its directories must have. A test that is not root
#: sets it to its own uid.
SEAL_UID = 0


def rendered_declaration_problem(path: Path) -> Optional[str]:
    """Why a rendered declaration can't be trusted, or None when it can: the file and every
    directory up to the rendered root must be real (not symlinks), owned by root, and closed to
    group and others. Otherwise the agent, or a run as the agent, could change what the
    daemon reads."""
    path = Path(path)
    # Up to and including the rendered root's parent: whoever could write that could move the
    # rendered root aside and put another in its place.
    for p in [path] + [d for d in path.parents if RENDERED_DECLARATIONS.parent in [d, *d.parents]]:
        try:
            st = os.lstat(p)
        except OSError as e:
            return f"{p} cannot be read: {e.strerror}"
        if stat.S_ISLNK(st.st_mode):
            return f"{p} is a symlink"
        if st.st_uid != SEAL_UID:
            return f"{p} is owned by uid {st.st_uid}, not root"
        if st.st_mode & 0o022:
            return f"{p} can be written by its group or others (mode {stat.S_IMODE(st.st_mode):o})"
    return None
