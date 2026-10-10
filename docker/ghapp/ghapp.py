#!/opt/maceff-venv/bin/python3
"""ghapp: a GitHub App identity for one agent.

Three subcommands, one state directory per app (~/.maceff/ghapp/<name>/, mode 0700):

  convert CODE  Exchange the one-hour code from the App Manifest flow for the app's
                id and private key. The key is written straight to private-key.pem
                (0600) and NEVER printed. app.json keeps only non-secret facts.
  token         Print an installation access token on stdout, for
                GH_TOKEN="$(ghapp.py token --repo OWNER/NAME)". Exit 3 when the app is not
                installed on that repository, so a caller can fall back. Tokens last one
                hour by GitHub's rule; one is cached (0600) and reused until five minutes
                before it expires.
  whoami        Print the app's slug, id and installations (no secrets).

Which app: --name, else $GHAPP_NAME, else the one app under the agent's home
($MACEFF_AGENT_HOME_DIR, else ~)/.maceff/ghapp/. More than one and no name is an error, never
a guess.

A token is a live credential: an agent runs ``token`` only inside a command substitution
(``GH_TOKEN="$(ghapp.py token --repo O/R)"``), never where its output is captured, since an
agent's tool output is a transcript.

Why: an agent that posts through the operator's own token cannot be told apart from the
operator on the platform, and a leaked personal token lives for months. An installation
token reaches only the repositories the app is installed on and dies within the hour; the
key that mints it never leaves the agent's home. Policy: git_discipline, section 4.

These tools live read-only in the image (/opt/maceff-ghapp/); each agent's key, facts and
token cache are its own, under its home.
"""
import argparse
import calendar
import json
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import jwt  # PyJWT, with cryptography for RS256; both in /opt/maceff-venv

API = "https://api.github.com"
# The agent's own home, not the login's: where several agents share one login, ~ is the
# login's, and "the only app there" could be another agent's. MACEFF_AGENT_HOME_DIR names the
# agent's home, as macf.utils.paths.find_agent_home reads it; inside a container it is ~.
ROOT = Path(os.environ.get("MACEFF_AGENT_HOME_DIR") or os.path.expanduser("~")) / ".maceff" / "ghapp"


class NoApp(Exception):
    pass


def resolve_name(given):
    """The app's state directory name: given, else $GHAPP_NAME, else the only app here."""
    name = given or os.environ.get("GHAPP_NAME")
    if name:
        return name
    apps = sorted(p.name for p in ROOT.glob("*") if (p / "app.json").is_file()) if ROOT.is_dir() else []
    if len(apps) == 1:
        return apps[0]
    if not apps:
        raise NoApp(f"no app under {ROOT}: run convert first")
    raise NoApp(f"several apps under {ROOT} ({', '.join(apps)}): pass --name or set GHAPP_NAME")


def state_dir(name: str, create: bool = False) -> Path:
    """The app's state directory. Only ``convert`` creates one; any other command naming an
    app that does not exist is told so in a sentence, not left with an empty directory."""
    d = ROOT / name
    if not create and not (d / "app.json").is_file():
        raise NoApp(f"no app named {name!r} under {ROOT} (run convert first, or check --name / GHAPP_NAME)")
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    return d


def call(method: str, path: str, token: str = "", bearer_jwt: str = "", body=None):
    req = urllib.request.Request(API + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if bearer_jwt:
        req.add_header("Authorization", f"Bearer {bearer_jwt}")
    elif token:
        req.add_header("Authorization", f"token {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def write_secret(path: Path, data: str) -> None:
    """Write 0600, whole or not at all: a full disk or a killed process leaves the old file
    (or none), never an empty one."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def read_cache(path: Path):
    """A cached token, or None when there is none usable: missing, empty, or unparseable
    (a write cut short by a full disk) all mean "mint a new one"."""
    if not path.exists():
        return None
    try:
        c = json.loads(path.read_text())
    except ValueError:
        c = None
    if not isinstance(c, dict) or not c.get("token"):
        print(f"ghapp: token cache {path.name} is damaged (empty or unparseable); minting a new token",
              file=sys.stderr)
        return None
    return c


def cmd_convert(args) -> int:
    if not args.name:
        print("convert needs --name: the state directory this app will live in", file=sys.stderr)
        return 2
    d = state_dir(args.name, create=True)
    if (d / "private-key.pem").exists() and not args.force:
        print(f"refusing: {d}/private-key.pem exists (use --force to replace)", file=sys.stderr)
        return 1
    resp = call("POST", f"/app-manifests/{args.code}/conversions")
    write_secret(d / "private-key.pem", resp["pem"])
    facts = {k: resp.get(k) for k in ("id", "slug", "client_id", "html_url", "name")}
    facts["owner"] = (resp.get("owner") or {}).get("login")
    (d / "app.json").write_text(json.dumps(facts, indent=1) + "\n")
    # webhook_secret and client_secret are not needed (no webhook, no user OAuth); not kept.
    print(f"app {facts['slug']} id {facts['id']} owner {facts['owner']} -> {d} (key stored 0600, not shown)")
    return 0


def app_jwt(d: Path) -> str:
    facts = json.loads((d / "app.json").read_text())
    key = (d / "private-key.pem").read_text()
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(facts["id"])}, key, algorithm="RS256")


def _installed_repos(token: str) -> list:
    """Every repository the installation reaches, following the pages (100 a page)."""
    repos, page = [], 1
    while True:
        got = call("GET", f"/installation/repositories?per_page=100&page={page}", token=token)
        batch = got.get("repositories", []) if isinstance(got, dict) else []
        repos += [r["full_name"].lower() for r in batch]
        total = got.get("total_count", len(repos)) if isinstance(got, dict) else len(repos)
        if not batch or len(repos) >= total:
            return repos
        page += 1


def cmd_token(args) -> int:
    d = state_dir(resolve_name(args.name))
    facts = json.loads((d / "app.json").read_text())
    owner = (args.owner or facts.get("owner") or "").lower()
    want = (args.repo or "").lower()
    if want:
        owner = want.split("/")[0]
    cache = d / f"token-{owner}.json"

    def emit(c) -> int:
        # A token reaches only the repositories the app is installed on; say no rather
        # than hand back a token that would fail, so the caller can fall back.
        if want and want not in c.get("repos", []):
            return 3
        sys.stdout.write(c["token"])
        if args.expiry:
            sys.stdout.write("\n" + str(int(c["expires_epoch"])))
        return 0

    c = read_cache(cache)
    if c and c.get("expires_epoch", 0) - time.time() > 300:
        # A repository added to the installation after this token was cached is not in its
        # list; mint once more before answering "not installed", rather than act as the
        # operator there until the cached token nears expiry.
        if not want or want in c.get("repos", []):
            return emit(c)
    j = app_jwt(d)
    inst = [i for i in call("GET", "/app/installations", bearer_jwt=j)
            if (i.get("account") or {}).get("login", "").lower() == owner]
    if not inst:
        print(f"no installation of {facts['slug']} on '{owner}': install the app there first", file=sys.stderr)
        return 3
    tok = call("POST", f"/app/installations/{inst[0]['id']}/access_tokens", bearer_jwt=j)
    exp = calendar.timegm(time.strptime(tok["expires_at"], "%Y-%m-%dT%H:%M:%SZ"))  # UTC
    repos = _installed_repos(tok["token"])
    c = {"token": tok["token"], "expires_epoch": exp, "installation": inst[0]["id"], "repos": repos}
    write_secret(cache, json.dumps(c))
    return emit(c)


def cmd_whoami(args) -> int:
    d = state_dir(resolve_name(args.name))
    facts = json.loads((d / "app.json").read_text())
    insts = call("GET", "/app/installations", bearer_jwt=app_jwt(d))
    print(f"{facts['slug']} (id {facts['id']}), bot login {facts['slug']}[bot]")
    for i in insts:
        print(f"  installed on {i['account']['login']}: repository_selection={i['repository_selection']}, "
              f"permissions={i.get('permissions')}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--name", help="state directory name (default: $GHAPP_NAME, else the only app)")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert"); c.add_argument("code"); c.add_argument("--force", action="store_true")
    t = sub.add_parser("token"); t.add_argument("--owner"); t.add_argument("--repo", help="owner/name; exit 3 if not installed there")
    t.add_argument("--expiry", action="store_true", help="also print the token's expiry (epoch seconds) on a second line")
    sub.add_parser("whoami")
    args = p.parse_args(argv)
    try:
        return {"convert": cmd_convert, "token": cmd_token, "whoami": cmd_whoami}[args.cmd](args)
    except NoApp as e:
        print(f"ghapp: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
