"""`macf_tools browser <backend> ...`: the command surface (MIS-0009 R03, R04, R25).

Each command records one event, whatever its outcome, and says what refused it. Exit codes: 0 done,
1 the browser failed, 2 the capability is unavailable here, 3 a rule refused the act.
"""
import argparse
import json
import sys
import time
from typing import Optional

from macf.browser import events, guard
from macf.browser import plugins as plugin_mod


def _agent_home():
    try:
        from macf.utils import find_agent_home
        return find_agent_home()
    except (ImportError, OSError, RuntimeError) as e:
        print(f"⚠️ MACF: agent home not found (downloads are checked against nothing): {e}", file=sys.stderr)
        return None


def _backend(args, plugin=None):
    from macf.browser.cdp import Backend
    hosts = list(plugin.hosts) if plugin else list(args.host or [])
    return Backend(args.cdp, hosts, plugin=plugin, agent_home=_agent_home()).start()


def _emit(args, payload) -> None:
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    elif isinstance(payload, dict):
        for k, v in payload.items():
            print(f"{k}: {v}")
    else:
        for line in payload:
            print(line)


def run_guarded(args, verb: str, act, plugin=None) -> int:
    """Run one act with its event and its refusals said plainly."""
    started = time.monotonic()
    host = ",".join(plugin.hosts if plugin else (args.host or [])) or None
    common = {"backend": "cdp", "plugin": plugin.name if plugin else None, "host": host}
    backend = None
    try:
        backend = _backend(args, plugin)
        result = act(backend)
        events.record(verb, "allowed", operator_said=getattr(args, "operator_said", None),
                      elapsed_s=round(time.monotonic() - started, 2), **common)
        if result is not None:
            _emit(args, result)
        return 0
    except guard.Refused as e:
        events.record(verb, "refused", reason=str(e)[:200], **common)
        print(f"❌ refused: {e}", file=sys.stderr)
        return 3
    except guard.Unavailable as e:
        events.record(verb, "failed", reason=str(e)[:200], **common)
        print(f"❌ unavailable: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - a browser failure of any kind is reported and recorded, never hidden
        events.record(verb, "failed", reason=f"{type(e).__name__}: {str(e)[:160]}", **common)
        print(f"❌ {verb} failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        if backend:
            backend.stop()


### core verbs

def cmd_status(args):
    def act(b):
        tabs = b.tabs()
        return {"endpoint": args.cdp, "browser": b.browser.version, "tabs": len(tabs),
                "in_scope": len(guard.tabs_in_scope(tabs, args.host)) if args.host else "no --host given"}
    if not args.host:
        args.host = ["*.invalid"]
    return run_guarded(args, "status", act)


def cmd_tabs(args):
    def act(b):
        return [f"[{t['index']}] {t['url']}" for t in guard.tabs_in_scope(b.tabs(), args.host)]
    return run_guarded(args, "tabs", act)


def cmd_read(args):
    def act(b):
        snap = b.observe(b.page_for(args.tab, interact=False))
        if args.json:
            return snap
        return [f"{snap['title']}  <{snap['url']}>"] + [f"{n['role']}: {n['name']}" for n in snap["nodes"]]
    return run_guarded(args, "read", act)


def cmd_screenshot(args):
    return run_guarded(args, "screenshot", lambda b: {"saved": b.screenshot(b.page_for(args.tab, False), args.out)})


def cmd_goto(args):
    return run_guarded(args, "goto", lambda b: b.goto(b.page_for(args.tab, True, open_url=args.url), args.url,
                                                     discard=args.discard))


def cmd_click(args):
    return run_guarded(args, "click", lambda b: b.click(b.page_for(args.tab, True), args.role, args.name,
                                                       exact=args.exact, operator_said=args.operator_said,
                                                       real_input=args.real_input))


def cmd_fill(args):
    text = open(args.text_file).read() if args.text_file else args.text
    return run_guarded(args, "fill", lambda b: b.fill(b.page_for(args.tab, True), args.role, args.name, text,
                                                     exact=args.exact))


def cmd_press(args):
    return run_guarded(args, "press", lambda b: b.press(b.page_for(args.tab, True), args.chord,
                                                       operator_said=args.operator_said))


def cmd_download(args):
    return run_guarded(args, "download", lambda b: b.download(b.page_for(args.tab, True), args.role, args.name,
                                                             args.out, exact=args.exact,
                                                             operator_said=args.operator_said))


def cmd_launch(args):
    from macf.browser import cdp
    try:
        pid = cdp.launch(args.profile_dir, port=args.port, chrome=args.chrome)
    except guard.Refused as e:
        events.record("launch", "refused", backend="cdp", reason=str(e)[:200])
        print(f"❌ refused: {e}", file=sys.stderr)
        return 3
    except OSError as e:
        events.record("launch", "failed", backend="cdp", reason=str(e)[:200])
        print(f"❌ launch failed: {e}", file=sys.stderr)
        return 1
    events.record("launch", "allowed", backend="cdp")
    print(f"browser started (pid {pid}) on port {args.port}; sign in by hand where the agent should help")
    return 0


### the parser

def _common(p, scoped: bool = True):
    p.add_argument("--cdp", default="http://localhost:9222", help="the debugging endpoint (this machine only)")
    if scoped:
        p.add_argument("--host", action="append", help="a host this command may touch (repeat; *.x for subdomains)")
        p.add_argument("--tab", type=int, help="a tab index from `tabs`; needed to drive a tab the operator opened")
    p.add_argument("--json", action="store_true", help="machine-readable output")


def _target(p):
    p.add_argument("--role", required=True, help="the element's accessible role (button, link, textbox, ...)")
    p.add_argument("--name", required=True, help="the element's accessible name")
    p.add_argument("--exact", action="store_true", help="match the name exactly")


def add_browser_parser(sub, private_dir: Optional[str] = None) -> None:
    browser = sub.add_parser("browser", help="the operator's browser, governed (MIS-0009): backends and plugins",
                             formatter_class=argparse.RawDescriptionHelpFormatter,
                             description="Observe and operate a browser the operator started and signed into. "
                                         "Every act is in the event log; irreversible acts need the operator's "
                                         "words (--operator-said). The operator's permission rules are the boundary.")
    backends = browser.add_subparsers(dest="browser_backend")
    cdp = backends.add_parser("cdp", help="Chrome DevTools Protocol backend (attach only)")
    verbs = cdp.add_subparsers(dest="cdp_cmd")

    p = verbs.add_parser("status", help="is a debug browser reachable? how many tabs?")
    _common(p)
    p.set_defaults(func=cmd_status)
    p = verbs.add_parser("tabs", help="tabs on the given hosts (matched by host, never by title)")
    _common(p)
    p.set_defaults(func=cmd_tabs)
    p = verbs.add_parser("read", help="read a page through its accessibility tree (no page script)")
    _common(p)
    p.set_defaults(func=cmd_read)
    p = verbs.add_parser("screenshot", help="save an image of a page (refused on pages marked secret)")
    _common(p)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_screenshot)
    p = verbs.add_parser("goto", help="navigate (refused while a form holds unsaved input, unless --discard)")
    _common(p)
    p.add_argument("url")
    p.add_argument("--discard", action="store_true")
    p.set_defaults(func=cmd_goto)
    p = verbs.add_parser("click", help="click a visible control; irreversible ones need --operator-said")
    _common(p)
    _target(p)
    p.add_argument("--operator-said", help="the operator's words for this act, verbatim; recorded with it")
    p.add_argument("--real-input", action="store_true", help="real mouse input, for pages that ignore scripted clicks")
    p.set_defaults(func=cmd_click)
    p = verbs.add_parser("fill", help="set a visible field's value (never a credential field)")
    _common(p)
    _target(p)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--text-file")
    p.set_defaults(func=cmd_fill)
    p = verbs.add_parser("press", help="press a key chord; send/submit chords need --operator-said")
    _common(p)
    p.add_argument("chord", help="e.g. Enter, Escape, Control+Enter")
    p.add_argument("--operator-said")
    p.set_defaults(func=cmd_press)
    p = verbs.add_parser("download", help="click a control that downloads; save by event with a sha256")
    _common(p)
    _target(p)
    p.add_argument("--out", required=True, help="destination directory (never inside the agent's home)")
    p.add_argument("--operator-said")
    p.set_defaults(func=cmd_download)
    p = verbs.add_parser("launch", help="start a browser on a separate profile with its debugging port open")
    p.add_argument("--profile-dir", required=True, help="a separate profile directory, never the default one")
    p.add_argument("--port", type=int, default=9222)
    p.add_argument("--chrome", help="the browser executable")
    p.set_defaults(func=cmd_launch)

    from pathlib import Path
    found = plugin_mod.discover(Path(private_dir) if private_dir else plugin_mod.private_dir_default())
    for name, plugin in sorted(found.items()):
        pp = verbs.add_parser(name, help=f"{plugin.origin} plugin on {', '.join(plugin.hosts)}")
        pp.set_defaults(plugin=plugin, func=cmd_plugin)
        plugin.module.add_arguments(pp, _common)


def cmd_plugin(args):
    """Run a plugin verb inside its declaration (R31): its hosts are the scope, its verbs the only verbs."""
    plugin, verb = args.plugin, getattr(args, "plugin_verb", None)
    if not verb:
        print(f"usage: macf_tools browser cdp {plugin.name} {{{','.join(plugin.verbs)}}} ...", file=sys.stderr)
        return 2

    def act(b):
        return plugin.module.run(b, args)
    return run_guarded(args, f"{plugin.name} {verb}", act, plugin=plugin)
