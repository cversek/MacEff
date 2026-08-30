"""OPSEC pre-commit gate — keep private agent/dev context out of public repos.

Installs a git pre-commit hook that scans STAGED ADDED LINES against a
pattern profile and rejects the commit on any hit. The profile lives OUTSIDE
the target repo (default: {agent_home}/.maceff/opsec_profiles/) because the
pattern list is itself the private vocabulary — committing it would leak the
very things it guards. The installed hook is a thin shim that reads the
profile path baked in at install time.

Born from a working single-repo implementation (2026-07-22) that caught two
real leaks on its first day — an internal idea-number in a code comment and a
non-ASCII em-dash — both of which had slipped past manual grep sweeps.
Deliberate disclosures bypass with a reviewed `git commit --no-verify`.
"""
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


### Default profile: agent-infrastructure vocabulary + private dev markers.
### Each entry is [regex, human label]. "hard" always rejects; "soft" rejects
### with a wording that says why it is a style smell rather than a leak.
DEFAULT_PROFILE: Dict[str, Any] = {
    "hard": [
        [r"\bc[0-9]{1,2}\b(?![0-9a-fA-F])", "cycle code (c15/c22/c25...)"],
        [r"[Cc]ycle[-_ ][0-9]+", "cycle-N reference"],
        [r"\bEXPERIMENT\s*#?[0-9]", "experiment number"],
        [r"\bMISSION\b|\bDETOUR\b", "internal task-type label"],
        [r"\btask\s*#[0-9]+|\bidea\s*#[0-9]+", "task/idea number"],
        [r"[Mm]ac[Ee]ff|\bMACF\b|\bmacf_tools\b", "framework name"],
        [r"\bbreadcrumb\b|\bJOTEWR\b|\bCCP\b", "framework artifact term"],
        [r"calling.card|ULTRATHINK|\bsubagent\b|\bconsciousness\b", "agent infrastructure term"],
        [r"\bClaude\b|\bAnthropic\b|\bChatGPT\b|\bLLM\b", "AI tool reference"],
        [r"[^\x00-\x7f]", "non-ASCII character"],
    ],
    "soft": [
        [r"\barm [A-HJ-Z]\b", "measurement-arm label from private notes"],
    ],
}

### ---------------------------------------------------------------------------
### THE SIX CATEGORIES THE STATIC PROFILE ABOVE CANNOT HOLD.
###
### The **amail spec** O5e.4 "the-gate-states-its-coverage-as-a-threat-model"
### records these as uncovered, and they are uncovered for a structural reason
### rather than an oversight: THEY ARE PROPERTIES OF THE RUNNING ENVIRONMENT.
### A static JSON profile cannot know this host's name, this account's name, or
### where this agent's home is, so no amount of editing DEFAULT_PROFILE would
### have added them. They must be derived when the scan runs.
###
### (This module is framework-wide, not part of amail, so the spec reference is
### qualified. An unqualified clause number is only resolvable by someone
### already inside the subsystem that owns it.)
###
### Derived values are themselves private -- that is the point of them -- so
### they are never written to the profile on disk, and a finding reports the
### CATEGORY and the span while REDACTING the matched text. A gate that echoes
### the secret it caught into a log has moved the leak, not stopped it.
### ---------------------------------------------------------------------------

#: Categories that hold whatever the environment. Ordered most-specific first
#: so a key blob is reported as key material rather than as a generic blob.
SECRET_SHAPED: List[List[str]] = [
    [r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key material"],
    [r"\bssh-(?:rsa|ed25519|dss)\s+AAAA[0-9A-Za-z+/=]{20,}", "ssh public key"],
    [r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{20,}", "github token"],
    [r"\bxox[baprs]-[A-Za-z0-9-]{10,}", "slack token"],
    [r"\bAKIA[0-9A-Z]{16}\b", "aws access key id"],
    [r"\bsk-[A-Za-z0-9]{20,}", "api key"],
    [r"(?i)\b(?:api[_-]?key|secret|passwd|password|token|bearer)\s*[:=]\s*"
     r"[\"']?[A-Za-z0-9_\-./+=]{12,}", "credential assignment"],
    [r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
     "uuid"],
]


def _literal(value: str) -> str:
    """A literal value as a word-bounded pattern.

    The boundaries exclude word characters and NOTHING ELSE, which is a
    narrower rule than it first looks and was corrected by a test. An earlier
    version also excluded a trailing hyphen, on the reasoning that it kept the
    match inside one word -- and that silently passed `deployer-keys.txt`,
    where the username is disclosed by the FILENAME. In a path or a filename a
    hyphen is a separator, not a continuation.

    A trailing LETTER still blocks: `deployers` is a different word that merely
    contains the value, and matching it would produce the noise that gets a
    gate muted.
    """
    import re as _re
    return r"(?<!\w)" + _re.escape(value) + r"(?!\w)"


def environment_patterns(env: Optional[Dict[str, str]] = None) -> List[List[str]]:
    """Patterns for the six environment-derived categories.

    `env` overrides discovery, and that parameter is what makes this testable
    at all: a test that had to use the REAL hostname in order to check the
    hostname rule would be committing the disclosure it exists to prevent.

    Short values are deliberately DROPPED rather than matched. A three-letter
    username turns every scan into a wall of false positives, and a gate whose
    output is mostly noise gets muted within a week -- which leaves the real
    leak unreviewed. Covering less and being believed is the better trade, and
    it is the same reasoning the private scanner records for its own omissions.
    """
    import getpass
    import socket

    e = dict(env or {})
    if env is None:
        try:
            e.setdefault("hostname", socket.gethostname())
        except OSError:
            pass
        try:
            e.setdefault("username", getpass.getuser())
        except (OSError, KeyError):
            pass
        try:
            from .utils.paths import find_agent_home
            home = find_agent_home()
            if home:
                e.setdefault("agent_home", str(home))
                mon = _moniker_from(home)
                if mon:
                    e.setdefault("moniker", mon)
        except (ImportError, OSError):
            pass

    out: List[List[str]] = []
    host = (e.get("hostname") or "").strip()
    if len(host) >= 4:
        out.append([_literal(host), "hostname"])
        first = host.split(".")[0]
        # The FQDN and its first label are the SAME disclosure, and the bare
        # label is the form that actually appears in prose -- matching only the
        # FQDN would pass the sentence a human would really write.
        if first != host and len(first) >= 4:
            out.append([_literal(first), "hostname"])

    user = (e.get("username") or "").strip()
    if len(user) >= 4:
        out.append([_literal(user), "local username"])

    home_path = (e.get("agent_home") or "").strip()
    if home_path:
        out.append([_literal(home_path), "agent home path"])
    # Absolute paths into ANY user home, not only this one: a collaborator's
    # path is someone else's disclosure and belongs to the same category.
    out.append([r"(?:/home|/Users|/root)/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*",
                "filesystem path"])

    mon = (e.get("moniker") or "").strip()
    if len(mon) >= 4:
        out.append([_literal(mon), "agent moniker"])
    # The @-suffixed short id, which is the form that actually leaks: it reads
    # as an email-ish token, so it survives the review that would have caught
    # the moniker spelled out.
    out.append([r"@[0-9a-f]{6}\b", "agent uuid"])
    return out


def _moniker_from(home) -> Optional[str]:
    """The agent's moniker from its calling card, or None.

    Read rather than configured: the card already names the agent, and a second
    source of the same fact would drift from it.
    """
    from pathlib import Path as _P
    try:
        text = (_P(home) / ".maceff_primary_agent.id").read_text().strip()
    except FileNotFoundError:
        # A LEGITIMATE None: no calling card means no moniker to redact, which
        # is a fact about this home rather than a failure to read it. This is
        # the case the rule asks to be distinguished, and it IS distinguished
        # -- from the unreadable case immediately below, which warns.
        return None  # noqa: MACEFF003 - absence is the answer here, not a failure to get one
    except OSError as e:
        # NOT legitimate. The file exists and could not be read, so the scan is
        # about to run WITHOUT the agent's own moniker in its pattern set --
        # a quieter gate than the caller asked for. Say so.
        print(f"⚠️ MACF: could not read the calling card at {home} ({e}); the "
              f"OPSEC scan will not redact this agent's moniker",
              file=sys.stderr, flush=True)
        return None
    return text.split("@", 1)[0].strip() or None


### The hook body written into <repo>/.git/hooks/. Reads the profile at run
### time so pattern edits do not require reinstallation. Kept dependency-free
### (stdlib only) because it runs in whatever python3 the committer has.
HOOK_TEMPLATE = '''#!/usr/bin/env python3
"""Pre-commit gate: reject staged lines that leak private context.

Installed by an external tool; the pattern profile lives outside this repo
on purpose. Bypass after human review with: git commit --no-verify
"""
import json
import re
import subprocess
import sys

PROFILE_PATH = {profile_path!r}


def staged_added_lines():
    out = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color"],
        capture_output=True, text=True,
    ).stdout
    fname = None
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            fname = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            yield fname, line[1:]


def main():
    try:
        with open(PROFILE_PATH) as f:
            profile = json.load(f)
    except (OSError, ValueError) as e:
        print("pre-commit gate: cannot read profile %s (%s); failing closed" % (PROFILE_PATH, e))
        return 1
    checks = [(re.compile(p), label, "hard") for p, label in profile.get("hard", [])]
    checks += [(re.compile(p), label, "soft") for p, label in profile.get("soft", [])]
    # Labels a profile marks as SECRET-CLASS. A finding of this class is
    # reported WITHOUT the matched text and WITHOUT the surrounding line.
    #
    # THE GATE MUST NOT PRINT WHAT IT REFUSES. For the original private-context
    # patterns, quoting the match is exactly right -- you need to see which
    # cycle code or task number leaked, and the string is harmless. For a
    # credential it inverts completely: the gate that stops the secret reaching
    # git prints it into a terminal, a CI log and an agent transcript instead,
    # and those are harder to rotate out of than a rejected commit.
    #
    # Measured, not theorised: a service token was disclosed into a transcript
    # by this hook's own refusal message during the test that added these
    # patterns, and had to be rotated.
    #
    # The reader needs to know THAT a credential is in the diff and WHERE. Never
    # what it is -- they have the file, and `git diff --cached` is one command.
    secret_labels = set(profile.get("secret_class", []))

    def is_secret(label):
        return label in secret_labels or any(
            k in label.lower() for k in
            ("credential", "secret", "token", "password", "private key",
             "api key", "email address"))

    hits = []
    for fname, text in staged_added_lines():
        for rx, label, kind in checks:
            m = rx.search(text)
            if m:
                if is_secret(label):
                    hits.append((fname, label, None, None))
                else:
                    hits.append((fname, label, m.group(0), text.strip()[:100]))
    if hits:
        print("COMMIT REJECTED: leakage in staged changes")
        print("-" * 60)
        redacted = 0
        for fname, label, tok, ctx in hits:
            if tok is None:
                redacted += 1
                print("%s: [%s]" % (fname, label))
                print("    <REDACTED -- this gate does not print the material "
                      "it refuses; inspect with: git diff --cached -- %s>" % fname)
            else:
                print("%s: [%s] %r" % (fname, label, tok))
                print("    %s" % ctx)
        print("-" * 60)
        print("%d hit(s)%s." % (len(hits),
              ", %d withheld as secret-class" % redacted if redacted else ""))
        if redacted:
            print("A refused credential is still a DISCLOSED credential if it "
                  "reached a log or a transcript. If this material has been "
                  "printed anywhere, ROTATE it -- deletion does not reach the "
                  "copies, rotation does.")
        print("Fix, or bypass after review: git commit --no-verify")
        print("Why this gate exists:")
        print("  macf_tools policy navigate capability_boundaries")
        print("  Related: credential custody, private context, public surfaces")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

SHIM_TEMPLATE = '''#!/bin/sh
exec python3 "$(git rev-parse --git-common-dir)/hooks/check_context_leakage.py"
'''


def default_profiles_dir() -> Path:
    """Profile home, outside any target repo."""
    from .utils.paths import find_agent_home
    home = find_agent_home() or Path.home()
    d = home / ".maceff" / "opsec_profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure_default_profile() -> Path:
    """Write the default profile if absent; never overwrite user edits."""
    path = default_profiles_dir() / "default.json"
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_PROFILE, indent=2))
    return path


def install_hook(repo: Path, profile: Optional[Path] = None) -> Dict[str, Any]:
    """Install the leakage gate into repo's git hooks. Returns install facts."""
    repo = Path(repo).resolve()
    git_dir = repo / ".git"
    if not git_dir.exists():
        raise ValueError(f"not a git repository (no .git): {repo}")
    # Worktree checkouts have a .git FILE pointing at the real git dir; hooks
    # live in the common dir so one install covers all worktrees.
    if git_dir.is_file():
        gitdir_line = git_dir.read_text().strip()
        actual = Path(gitdir_line.split("gitdir:", 1)[1].strip())
        common = actual / "commondir"
        if common.exists():
            actual = (actual / common.read_text().strip()).resolve()
        git_dir = actual
    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    profile_path = Path(profile).resolve() if profile else ensure_default_profile()
    if not profile_path.exists():
        raise ValueError(f"profile not found: {profile_path}")
    # Refuse a profile inside the repo tree: it would get committed.
    inside = True
    try:
        profile_path.relative_to(repo)
    except ValueError:
        inside = False
    if inside:
        raise ValueError(
            f"profile {profile_path} is inside the target repo -- the pattern "
            "list is private vocabulary and must live outside the tree"
        )

    checker = hooks_dir / "check_context_leakage.py"
    checker.write_text(HOOK_TEMPLATE.format(profile_path=str(profile_path)))
    os.chmod(checker, checker.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Install the dispatcher and take a NUMBERED SLOT rather than owning the
    # single pre-commit file.
    #
    # This used to refuse when another hook held the slot, which is the correct
    # posture for a lone installer and the wrong shape for a second one. The
    # framework wants two things in pre-commit -- this scan and the style gate --
    # and git offers one file, so whichever installed second lost and was silent
    # about it afterwards. Refusing was better than clobbering and still meant
    # one of the two gates did not exist.
    #
    # The hooklet goes in the PER-CLONE directory, never the versioned one: it
    # hardcodes the path to a private pattern file, and committing that would
    # publish one developer's private vocabulary to everyone who clones.
    from .githooks import install_dispatcher

    dispatch = install_dispatcher(repo)
    local_d = Path(dispatch["local_dir"]) / "pre-commit.d"
    local_d.mkdir(parents=True, exist_ok=True)
    hooklet = local_d / "10-opsec"
    hooklet.write_text(SHIM_TEMPLATE)
    os.chmod(hooklet, hooklet.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    return {
        "repo": str(repo),
        "hooks_dir": str(hooks_dir),
        "profile": str(profile_path),
        "hooklet": str(hooklet),
        "dispatcher_actions": dispatch["actions"],
        "adopted": dispatch["adopted"],
    }


### ---------------------------------------------------------------------------
### THE TEXT-LEVEL ENTRY POINT.
###
### Before this, the matching logic in this module existed ONLY as a string --
### HOOK_TEMPLATE, written to disk and run by subprocess against `git diff
### --cached`. It could not be imported, called, or pointed at anything that
### was not a staged diff. The amail spec O5e.1
### "the-gate-must-accept-a-composed-message" requires a gate that takes a
### composed message, and the honest description of the starting state was not
### "the scanner only exposes staged lines" but "there is no scanner to expose".
###
### So the matching moves here, where it can be called and tested. The hook
### template keeps its own small matcher because it must run stdlib-only in
### whatever python3 a committer has, with macf possibly not installed at all
### -- but both read the SAME profile, so the vocabulary cannot diverge even
### though the two loops are separate.
### ---------------------------------------------------------------------------

#: A part that could not be read as text. NOT an empty finding list: the amail
#: spec O5e.6 "fail-closed-applies-to-the-scan-not-the-message" makes this its
#: own outcome, because "nothing found" and "nothing looked at" are different
#: facts and only one of them is safe to treat as clean.
UNSCANNED = "unscanned"


class Finding:
    """One hit. Carries the category and the span, never the matched text.

    Redaction is not decoration. A finding travels into logs, refusal messages
    and operator alerts -- all of which are outward-facing surfaces the amail
    spec O5e.0a "the-scrub-is-scoped-to-the-act-of-emission" puts IN SCOPE. A
    gate that quotes the secret it caught has relocated the disclosure into the
    record of having prevented it.
    """

    __slots__ = ("part", "label", "start", "end", "length")

    def __init__(self, part: str, label: str, start: int, end: int):
        self.part, self.label = part, label
        self.start, self.end, self.length = start, end, end - start

    def __repr__(self) -> str:
        return (f"Finding(part={self.part!r}, label={self.label!r}, "
                f"at={self.start}:{self.end}, len={self.length})")

    def as_dict(self) -> Dict[str, Any]:
        return {"part": self.part, "label": self.label,
                "start": self.start, "end": self.end, "length": self.length}


class ScanResult:
    """What a scan found, and what it could not look at.

    `clean` is False when ANYTHING was unscanned, which is the whole of the
    fail-closed rule: a caller asking "is this clean?" must not get True for a
    message half of which was never read.
    """

    __slots__ = ("findings", "unscanned")

    def __init__(self, findings: Optional[List[Finding]] = None,
                 unscanned: Optional[List[str]] = None):
        self.findings = findings or []
        self.unscanned = unscanned or []

    @property
    def clean(self) -> bool:
        return not self.findings and not self.unscanned

    def reason(self) -> str:
        """A refusal message that names categories and quotes nothing."""
        bits = []
        if self.findings:
            counts: Dict[str, int] = {}
            for f in self.findings:
                counts[f"{f.part}:{f.label}"] = counts.get(f"{f.part}:{f.label}", 0) + 1
            bits.append("; ".join(f"{k} x{v}" for k, v in sorted(counts.items())))
        if self.unscanned:
            bits.append("unscanned parts: " + ", ".join(sorted(self.unscanned)))
        return " | ".join(bits) or "clean"

    def as_dict(self) -> Dict[str, Any]:
        return {"clean": self.clean, "unscanned": list(self.unscanned),
                "findings": [f.as_dict() for f in self.findings]}


def compiled_checks(profile: Optional[Dict[str, Any]] = None,
                    env: Optional[Dict[str, str]] = None) -> List[Any]:
    """Every pattern this gate applies, compiled once.

    Three sources, and they are combined here rather than merged into the
    profile on disk: the static vocabulary, the always-on secret shapes, and
    the environment-derived six. The last two never touch the profile file
    because writing this host's name into a file that lives on this host --
    and that a future hand might copy somewhere -- would create the disclosure.
    """
    import re as _re
    prof = profile if profile is not None else DEFAULT_PROFILE
    checks = []
    for pattern, label in prof.get("hard", []):
        checks.append((_re.compile(pattern), label))
    for pattern, label in SECRET_SHAPED:
        checks.append((_re.compile(pattern), label))
    for pattern, label in environment_patterns(env):
        checks.append((_re.compile(pattern), label))
    return checks


def scan_text(text: Any, *, part: str = "body",
              profile: Optional[Dict[str, Any]] = None,
              env: Optional[Dict[str, str]] = None,
              checks: Optional[List[Any]] = None) -> ScanResult:
    """Scan one piece of text. The entry point that did not exist.

    Non-text input is reported UNSCANNED rather than coerced. `str(b"...")`
    would produce `b'\\x00...'` and scan the REPR -- a scan that looks like it
    ran, reports clean, and examined a string the sender never wrote. That is
    the dead instrument this gate is most at risk of becoming.
    """
    if text is None:
        return ScanResult(unscanned=[part])
    if isinstance(text, (bytes, bytearray)):
        try:
            text = bytes(text).decode("utf-8")
        except UnicodeDecodeError:
            return ScanResult(unscanned=[part])
    if not isinstance(text, str):
        return ScanResult(unscanned=[part])

    use = checks if checks is not None else compiled_checks(profile, env)
    found = [Finding(part, label, m.start(), m.end())
             for rx, label in use for m in rx.finditer(text)]
    return ScanResult(findings=found)


def scan_parts(parts: Dict[str, Any], *,
               profile: Optional[Dict[str, Any]] = None,
               env: Optional[Dict[str, str]] = None) -> ScanResult:
    """Scan a named collection of parts, compiling the patterns once."""
    use = compiled_checks(profile, env)
    findings: List[Finding] = []
    unscanned: List[str] = []
    for name, value in parts.items():
        r = scan_text(value, part=name, checks=use)
        findings.extend(r.findings)
        unscanned.extend(r.unscanned)
    return ScanResult(findings=findings, unscanned=unscanned)


#: Headers the SENDER DOES NOT AUTHOR: the addressing the protocol requires a
#: message to carry. Exempt from the scrub by default, and the exemption is
#: STATED here rather than discovered, per the amail spec O5e.4
#: "coverage-is-a-claim-about-a-threat-model".
#:
#: WHY, and this is a threat-model correction rather than a relaxation. A leak
#: is private context appearing WHERE IT DOES NOT BELONG. A sender's own
#: address in its own From header is the return path: the recipient already
#: has it by construction, it is the one string a message may not omit, and
#: the protocol -- not the agent -- decides its shape.
#:
#: MEASURED, on the first real send: an agent address of the form
#: `<agent>@<container>.<domain>` carried the framework name twice, in the
#: local part and in the domain, so the gate refused EVERY message the
#: deployment could compose. Not occasionally: totally. A gate that refuses
#: one hundred percent of legitimate traffic is not strict, it is misaimed,
#: and the only pressure it generates is to switch it off.
#:
#: WHAT IS DELIBERATELY NOT EXEMPT: `subject`. It is a header AND it is the
#: agent's own text, and O5e.5 exists because "a gate scanning only the body
#: passes a leak in a subject line". Exempting headers WHOLESALE would have
#: satisfied the request that produced this change while reopening the exact
#: attack that produced O5e.5. The axis is AUTHORSHIP OF THE TEXT, not
#: header-versus-body.
ADDRESSING_PARTS = ("header:from", "header:to")


def scan_message(message: Any, *, attachments: Optional[Dict[str, Any]] = None,
                 profile: Optional[Dict[str, Any]] = None,
                 env: Optional[Dict[str, str]] = None,
                 include_addressing: bool = False) -> ScanResult:
    """Scan a composed message across its ENUMERATED surface.

    The amail spec O5e.5 "the-gate's-scope-is-enumerated" names it: headers,
    body, and attachment FILENAMES and metadata. A gate reading only the body
    passes a leak in a subject line and still satisfies a rule that says
    "scan the message".

    Attachment CONTENT is not read here. That is a scoping decision and it is
    stated rather than left implicit: a filename and its metadata are text and
    are scanned; arbitrary bytes are reported UNSCANNED, and the deployment
    decides whether an unscanned part may be sent (the amail spec O5e.6). What
    is forbidden is the third option -- an unscanned part silently counting as
    scanned.

    ADDRESSING HEADERS ARE EXEMPT BY DEFAULT (``ADDRESSING_PARTS``): the sender
    does not author them and the recipient already holds them. Pass
    ``include_addressing=True`` to scan the full surface -- correct when what
    is being scanned is an outward RENDERING of a message (an operator
    listing, a published directory entry) rather than the message itself,
    because there the addresses are exactly what leaks (O5e.0a/O5e.0b). The
    capability is retained and defaulted off, not removed.
    """
    parts: Dict[str, Any] = {
        "header:from": getattr(message, "sender", None),
        "header:to": ", ".join(getattr(message, "to", None) or []),
        "header:subject": getattr(message, "subject", None),
        "body": getattr(message, "body", None),
    }
    for name, meta in (attachments or {}).items():
        parts[f"attachment:name:{name}"] = name
        if isinstance(meta, (str, bytes, bytearray)):
            parts[f"attachment:meta:{name}"] = meta
        elif isinstance(meta, dict):
            parts[f"attachment:meta:{name}"] = " ".join(
                f"{k}={v}" for k, v in sorted(meta.items()))
        elif meta is not None:
            # Something we cannot read as text. Say so; do not stringify it.
            parts[f"attachment:meta:{name}"] = meta
    if not include_addressing:
        for name in ADDRESSING_PARTS:
            parts.pop(name, None)
    return scan_parts(parts, profile=profile, env=env)
