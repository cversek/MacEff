"""
Agent identity utilities for MACF.

Provides functions to get agent identity information combining
display name (from GECOS) and UUID.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


def get_agent_identity() -> str:
    """
    Get agent identity in format 'DisplayName@uuid_prefix'.

    Both halves resolve from layered sources, and the layers have scopes:
    per-project (``.maceff/config.json`` ``agent_identity.calling_card`` /
    ``moniker``, ``{agent_home}/.maceff_primary_agent.id``) versus
    host-global (``MACEFF_AGENT_NAME``, GECOS, ``~/.maceff_primary_agent.id``).

    Name resolution, host-global UUID (highest priority first):
    1. ``MACEFF_AGENT_NAME`` env var — explicit override
    2. config ``calling_card`` (preferred) or ``moniker`` (fallback)
    3. GECOS / Directory-Services display name (spaces stripped)
    4. ``$USER`` — last-resort fallback

    Name resolution, per-project UUID: same chain but the env var drops to
    just above ``$USER``. A host-global ``MACEFF_AGENT_NAME`` (typically baked
    into a shell rc for the host's resident agent) must not rename a
    per-project agent: pairing the global name with the per-project UUID
    composes an identity that belongs to no agent. If the env var is
    nonetheless the only name source available in per-project scope, it is
    used and a scope-mismatch warning goes to stderr.

    The config layer is the unified-config-layer slot added per
    cversek/MacEff#96 (Phase 1) and is the right place to pin a per-project
    agent's display name.

    Returns:
        str: Agent identity (e.g., 'Card@abcdef') or fallback

    Examples:
        >>> get_agent_identity()
        'Card@abcdef'
    """
    # Get current user
    username = os.environ.get('USER', 'unknown')

    uuid_prefix, uuid_scope = _resolve_uuid_prefix()

    # Lazy name sources, in host-global priority order
    candidates = [
        ('env', lambda: os.environ.get('MACEFF_AGENT_NAME')),
        ('config', _get_config_identity_name),
        ('gecos', _get_gecos_name),
    ]
    if uuid_scope == 'project':
        # Per-project agent: the host-global env var loses its override
        # power and becomes the last resort before $USER.
        candidates.append(candidates.pop(0))

    display_name, name_source = username, 'user'
    for source, getter in candidates:
        value = getter()
        if value:
            display_name, name_source = value, source
            break

    if uuid_scope == 'project' and name_source == 'env':
        print(
            f"⚠️ MACF: identity scope mismatch — name '{display_name}' comes "
            f"from host-global MACEFF_AGENT_NAME but UUID {uuid_prefix} comes "
            f"from the per-project identity file; set "
            f"agent_identity.calling_card in {{agent_home}}/.maceff/config.json "
            f"to pin this agent's name",
            file=sys.stderr,
        )

    # Compose identity
    return f"{display_name}@{uuid_prefix}"


# Characters that cannot survive a round trip through the session and service
# managers, established by measurement on 2026-08-07 (tmux 3.6, systemd 257)
# rather than from documentation:
#
#   tmux     '.' and ':' are accepted by ``new-session`` and then SILENTLY
#            rewritten to '_'. The session is created, the command reports
#            success, and the name you asked for no longer addresses anything.
#            That is the worst available failure: it does not announce itself,
#            and every later `-t` lookup simply misses.
#   systemd  ':' breaks unit processing ("Couldn't process aliases").
#
# '@' is NOT in this set on the evidence: a concrete unit file named
# ``cc-harness-Name@abc123.service`` enables, symlinks into default.target.wants,
# starts, and reports is-active, and tmux keeps it verbatim. It is substituted
# anyway, by CONVENTION — '@' is how systemd spells a template instance, and a
# concrete unit wearing that shape invites both human and tooling confusion.
# Recording the distinction matters: this is a style choice we could revisit,
# not a constraint we discovered, and an earlier write-up of this work asserted
# the opposite ("@ → _ is correct for systemd") without having measured it.
_UNSAFE_IN_IDENTIFIER = ".:/@ \t"

_IDENTIFIER_SEPARATOR = "_"


def session_identifier(calling_card: Optional[str] = None) -> str:
    """Map a Calling Card to a session/service identifier.

    The harness names a tmux session, a systemd unit and a supervisor instance.
    Before this existed those carried a nickname that appeared nowhere else in
    the framework, so an operator holding the Calling Card could not derive the
    session name and a tool holding the session name could not recover the
    Calling Card. The identifier is now a pure function of identity.

    ``TheHarborMaster@ee5cd8`` becomes ``TheHarborMaster_ee5cd8``.

    Collisions are possible in principle — two Calling Cards differing only in a
    substituted character map to one identifier — and are not resolved here.
    They are made harmless downstream instead: the harness resolver refuses to
    pick between multiple matching units rather than guessing, which is the same
    rule that keeps a defaulted name from being reported as a resolved one. The
    six-hex-character suffix comes from a UUID, so a real collision requires two
    agents whose monikers differ only by punctuation *and* whose UUIDs share a
    prefix.
    """
    card = (calling_card or get_agent_identity()).strip()
    out = []
    for ch in card:
        if ch in _UNSAFE_IN_IDENTIFIER:
            out.append(_IDENTIFIER_SEPARATOR)
        elif ch.isalnum() or ch in "_-":
            out.append(ch)
        else:
            # Anything else is unproven rather than known-bad. Substituting is
            # the conservative move; passing it through would make the failure
            # someone else's, in a tmux lookup that just quietly misses.
            out.append(_IDENTIFIER_SEPARATOR)
    # Collapse runs so "A..B" and "A_B" do not become distinguishable only by
    # underscore count, which no human would notice in a session list.
    ident = ""
    for ch in out:
        if ch == _IDENTIFIER_SEPARATOR and ident.endswith(_IDENTIFIER_SEPARATOR):
            continue
        ident += ch
    return ident.strip(_IDENTIFIER_SEPARATOR)


def calling_card_from_identifier(identifier: str) -> str:
    """Recover the Calling Card from a session identifier.

    Reversible by convention, not by escaping: a Calling Card is
    ``Moniker@uuidprefix``, so the LAST separator is the one that was an '@'.
    Splitting on the last one keeps monikers that legitimately contain '_'.

    This direction is what lets ``harness status`` name the agent behind a
    session it found, instead of reporting on an identifier nobody can trace.
    """
    head, sep, tail = identifier.rpartition(_IDENTIFIER_SEPARATOR)
    return f"{head}@{tail}" if sep else identifier


def _get_config_identity_name() -> Optional[str]:
    """Read display name from .maceff/config.json agent_identity block.

    Prefers ``calling_card`` (the short-form display name added by
    cversek/MacEff#96), falling back to ``moniker`` (the existing
    formal-name field).

    Resolution starts from the agent home base, so per-project config
    is picked up correctly. Returns None on any failure — caller will
    fall through to GECOS / username.
    """
    import json
    try:
        from macf.utils.paths import find_agent_home
        try:
            agent_home = find_agent_home()
        except ImportError:
            return None
        if agent_home is None:
            return None
        config_file = agent_home / '.maceff' / 'config.json'
        if not config_file.exists():
            return None
        try:
            with open(config_file) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️ MACF: .maceff/config.json read failed: {e}", file=sys.stderr)
            return None
        identity = data.get('agent_identity') or {}
        # Prefer calling_card (short) over moniker (formal name)
        for key in ('calling_card', 'moniker'):
            value = identity.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    except (OSError, ImportError) as e:
        print(f"⚠️ MACF: config-based identity lookup failed: {e}", file=sys.stderr)
        return None


def _get_gecos_name() -> Optional[str]:
    """
    Extract display name from GECOS field.

    Removes spaces from GECOS field to create display name.
    Example: "Manny MacEff" -> "MannyMacEff"

    Platform-aware:
    - Linux: `getent passwd $USER` (5th colon-delimited field)
    - macOS: `id -F` (full name from Directory Services)

    Returns:
        str: Display name with spaces removed, or None if unavailable
    """
    import sys
    try:
        username = os.environ.get('USER')
        if not username:
            return None

        full_name = None

        if sys.platform == 'darwin':
            # macOS: id -F returns full name from Directory Services
            result = subprocess.run(
                ['id', '-F'],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0 and result.stdout.strip():
                full_name = result.stdout.strip()
        else:
            # Linux: getent passwd
            result = subprocess.run(
                ['getent', 'passwd', username],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                fields = result.stdout.strip().split(':')
                if len(fields) >= 5 and fields[4]:
                    # GECOS: comma-separated, first field is full name
                    full_name = fields[4].split(',')[0].strip()

        if not full_name:
            return None

        # Remove spaces
        display_name = full_name.replace(' ', '')
        return display_name if display_name else None

    except (OSError, subprocess.SubprocessError, ValueError) as e:
        print(f"⚠️ MACF: agent display name detection failed: {e}", file=sys.stderr)
        return None


def _resolve_uuid_source() -> "tuple[Optional[str], str, Optional[Path]]":
    """
    Resolve the agent UUID together with its scope and the file it came from.

    Resolution order:
    1. {agent_home}/.maceff_primary_agent.id when agent_home is somewhere
       other than ~ (per-project identity, via find_agent_home) — scope
       'project'
    2. ~/.maceff_primary_agent.id — scope 'global'

    This is the single implementation of that precedence; callers that only
    need the display prefix go through _resolve_uuid_prefix(). Callers that
    need to *move* an identity between scopes need the whole value and its
    origin, which is what this returns — reading the file a second time from
    a caller's own copy of the precedence rules is how identities drift.

    Returns:
        tuple: (full UUID or None when nothing resolves, scope, source path
        or None)
    """
    try:
        agent_home = None
        try:
            from macf.utils.paths import find_agent_home
            agent_home = find_agent_home()
        except ImportError as e:
            print(f"⚠️ MACF: find_agent_home unavailable for identity resolution: {e}", file=sys.stderr)

        # Priority 1: Per-project identity (agent home distinct from ~)
        if agent_home is not None and agent_home != Path.home():
            per_project = agent_home / '.maceff_primary_agent.id'
            try:
                if per_project.exists():
                    uuid_full = per_project.read_text().strip()
                    if uuid_full:
                        return uuid_full, 'project', per_project
            except (OSError, IOError) as e:
                print(f"Warning: could not read per-project agent ID: {e}", file=sys.stderr)

        # Priority 2: Global fallback
        uuid_file = Path.home() / '.maceff_primary_agent.id'
        if not uuid_file.exists():
            return None, 'global', None

        uuid_full = uuid_file.read_text().strip()
        if not uuid_full:
            return None, 'global', None

        return uuid_full, 'global', uuid_file

    except (OSError, IOError) as e:
        print(f"Warning: could not read agent ID: {e}", file=sys.stderr)
        return None, 'global', None


def _resolve_uuid_prefix() -> "tuple[str, str]":
    """
    Read the agent UUID prefix together with the scope it resolved from.

    Thin projection of _resolve_uuid_source(); see that function for the
    resolution order. The scope feeds get_agent_identity()'s name resolution:
    a per-project UUID must not be paired with a host-global name override.

    Returns:
        tuple[str, str]: (first 6 characters of UUID or 'unknown', scope)
    """
    uuid_full, scope, _source = _resolve_uuid_source()
    if not uuid_full:
        return 'unknown', scope
    return uuid_full[:6], scope


def _get_uuid_prefix() -> str:
    """Read UUID prefix from the agent identity file (scope-blind wrapper)."""
    return _resolve_uuid_prefix()[0]
