"""A task's close-out on GitHub: posted as the agent, through the publishing checks, when it says something.

Completing a task that tracks a GitHub issue or pull request posts a close-out comment (#582).
On a login that several agents and the operator share, a bare ``gh`` acts as whichever account
is active, usually the operator's. So a close-out goes out only under an identity of the agent's
own: ``GH_TOKEN`` from its settings, or its own GitHub App where the app is installed on that
repository (git_discipline section 4). With neither, nothing is posted. The composed close-out
and the command that would post it are printed, and the task still completes.

The body passes the commit-message hooklets a pull request body passes, and a finding stops the
post; a check that cannot run counts as a finding. By default a close-out is posted while the
item is open or when this agent closed or merged it, not when someone else did, where a comment
tells nobody anything. ``--closeout`` and ``--no-closeout`` override the default.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

#: The hooklets every close-out body passes; the card's own check joins them when the
#: deployment signs its comments (opsec.public_attribution).
CHECKS = ("10-no-session-url", "20-no-private-refs")
CARD_CHECK = "30-calling-card"

Run = Callable[..., "subprocess.CompletedProcess"]


def _maceff_tree() -> Optional[Path]:
    """The MacEff source tree this package ships in, or None outside one."""
    from .githooks import _canonical_hooks_dir
    try:
        return _canonical_hooks_dir().parent
    except ValueError:
        return None  # noqa: MACEFF003 - None is the answer "outside a tree", and every caller says so


def _ghapp_root() -> Path:
    return Path(os.environ.get("MACEFF_AGENT_HOME_DIR") or os.path.expanduser("~")) / ".maceff" / "ghapp"


def _ghapp_tool() -> Optional[Path]:
    """The tool that mints this agent's app tokens: in the source tree, else in the image."""
    tree = _maceff_tree()
    for candidate in ([tree / "docker" / "ghapp" / "ghapp.py"] if tree else []) + \
            [Path("/opt/maceff-ghapp/ghapp.py")]:
        if candidate.is_file():
            return candidate
    return None


def agent_login() -> Optional[str]:
    """This agent's GitHub login when it has an app of its own: ``<slug>[bot]``.

    Read from the app's facts, the way the app tool picks the app: ``GHAPP_NAME``, else the
    only app under the agent's home. Several apps and no name is no answer.
    """
    root = _ghapp_root()
    name = os.environ.get("GHAPP_NAME")
    apps = [root / name] if name else (sorted(p for p in root.glob("*") if (p / "app.json").is_file())
                                       if root.is_dir() else [])
    if len(apps) != 1:
        return None
    try:
        slug = json.loads((apps[0] / "app.json").read_text()).get("slug")
    except (OSError, ValueError) as e:
        print(f"   ⚠️  cannot read the app's facts: {e}", file=sys.stderr)
        return None
    return f"{slug}[bot]" if slug else None


def agent_env(repo_slug: str, run: Optional[Run] = None) -> Tuple[Optional[Dict[str, str]], str]:
    """The environment in which ``gh`` acts as this agent on repo_slug, or None and why not."""
    run = run or subprocess.run
    env = dict(os.environ)
    if env.get("GH_TOKEN") or env.get("GITHUB_TOKEN"):
        return env, "the agent's GH_TOKEN"
    tool = _ghapp_tool()
    if tool is None:
        return None, "no GH_TOKEN, and no GitHub App tool in this install"
    try:
        # The token stays in this process's memory and the child's environment: never printed.
        r = run([sys.executable, "-I", str(tool), "token", "--repo", repo_slug],
                capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"the app tool did not run: {e}"
    if r.returncode == 0 and r.stdout.strip():
        env["GH_TOKEN"] = r.stdout.strip()
        return env, "the agent's GitHub App"
    if r.returncode == 3:
        return None, f"the agent's GitHub App is not installed on {repo_slug}"
    if r.returncode == 2:
        return None, "no GH_TOKEN, and no GitHub App of the agent's own"
    return None, "the agent's GitHub App gave no token: " + (r.stderr.strip()[:200] or f"exit {r.returncode}")


def check_body(body: str, signed: bool, run: Optional[Run] = None) -> Optional[str]:
    """The first finding of the publishing hooklets on body, or None when it passes."""
    run = run or subprocess.run
    tree = _maceff_tree()
    if tree is None:
        return "the publishing checks cannot run: no MacEff source tree (set MACEFF_ROOT_DIR)"
    hooks = tree / ".githooks" / "portable" / "commit-msg.d"
    names = CHECKS + ((CARD_CHECK,) if signed else ())
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body)
    try:
        for name in names:
            hook = hooks / name
            if not hook.is_file():
                return f"the publishing checks cannot run: {hook} is missing"
            try:
                r = run(["bash", str(hook), f.name], capture_output=True, text=True, timeout=30)
            except (OSError, subprocess.TimeoutExpired) as e:
                return f"the publishing checks cannot run: {name}: {e}"
            if r.returncode != 0:
                return f"{name}: " + ((r.stderr or "") + (r.stdout or "")).strip()[:600]
    finally:
        os.unlink(f.name)
    return None


def should_post(choice: Optional[bool], is_open: Optional[bool], closed_by: Optional[str],
                me: Optional[str]) -> Tuple[bool, str]:
    """Whether to post, and why. ``choice`` is --closeout (True) or --no-closeout (False)."""
    if choice is not None:
        return choice, "--closeout" if choice else "--no-closeout"
    if is_open is None:
        return True, "the item's state could not be read"
    if is_open:
        return True, "the item is open"
    if closed_by and me and closed_by.lower() == me.lower():
        return True, "this agent closed it"
    if not closed_by:
        return False, "it is closed and who closed it is unknown; pass --closeout to post anyway"
    return False, f"{closed_by} closed it, not this agent; pass --closeout to post anyway"


def _token_login(run: Run) -> Optional[str]:
    """The account behind a GH_TOKEN from the agent's settings, when there is one."""
    if not (os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")):
        return None
    try:
        r = run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"   ⚠️  cannot read the GH_TOKEN account: {e}", file=sys.stderr)
        return None  # noqa: MACEFF003 - unknown login; the caller withholds the post and names --closeout
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def item_state(repo_slug: str, number, run: Optional[Run] = None) -> Tuple[Optional[bool], Optional[str]]:
    """Whether the issue or pull request is open, and who closed or merged it, if anyone."""
    run = run or subprocess.run
    try:
        r = run(["gh", "api", f"repos/{repo_slug}/issues/{number}"],
                capture_output=True, text=True, timeout=15)
        d = json.loads(r.stdout) if r.returncode == 0 else {}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        d = {}
    if not d.get("state"):
        return None, None
    return d["state"] == "open", (d.get("closed_by") or {}).get("login")


def post(kind: str, number, repo_slug: str, body: str, *, choice: Optional[bool],
         is_open: Optional[bool], closed_by: Optional[str], signed: bool,
         run: Optional[Run] = None) -> Optional[Dict[str, str]]:
    """Post body as this agent's close-out on an issue or pull request (kind 'issue' or 'pr').

    Returns the environment it posted under, which a following ``gh issue close`` must use
    too, or None when nothing was posted. Never raises: the task is complete either way.
    """
    run = run or subprocess.run
    me = agent_login()
    if me is None and choice is None and is_open is False and closed_by:
        me = _token_login(run)      # only asked when the answer decides
    ok, why = should_post(choice, is_open, closed_by, me)
    if not ok:
        print(f"   ℹ️  Close-out not posted: {why}")
        return None
    finding = check_body(body, signed, run)
    if finding:
        _not_posted(kind, number, repo_slug, body, f"a publishing check refused it: {finding}")
        return None
    env, how = agent_env(repo_slug, run)
    if env is None:
        _not_posted(kind, number, repo_slug, body, f"no identity of this agent's own ({how})")
        return None
    try:
        r = run(["gh", kind, "comment", str(number), "--repo", repo_slug, "--body", body],
                capture_output=True, text=True, timeout=15, env=env)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"   ⚠️  gh unavailable, close-out not posted: {e}")
        return None
    if r.returncode != 0:
        print(f"   ⚠️  Failed to post the close-out: {r.stderr.strip()}")
        return None
    print(f"   📝 Close-out posted to {repo_slug}#{number} as {how}")
    return env


def _not_posted(kind: str, number, repo_slug: str, body: str, why: str) -> None:
    with tempfile.NamedTemporaryFile("w", prefix="closeout-", suffix=".md", delete=False) as f:
        f.write(body)
    print(f"   ⚠️  Close-out not posted: {why}")
    print("   It reads:")
    for line in body.splitlines():
        print(f"      {line}")
    print(f"   To post it under the right identity: gh {kind} comment {number} --repo {repo_slug} "
          f"--body-file {f.name}")
