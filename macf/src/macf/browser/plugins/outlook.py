"""Outlook on the web: read and draft mail in the operator's signed-in client. No send (MIS-0009 6.7).

For mail behind a client whose organization does not let its users grant an API. Everything is located by
role and accessible name, never by generated class names, and a page that lacks a needed control is refused
with the control named (R38). Message text is set by value, so no keystroke can fire the send shortcut (R37).
The composed message is left in Drafts for the operator to send (R35, R36).
"""
import re
from typing import List

from macf.browser import guard
from macf.browser.plugins import Plugin, enforce

PLUGIN = Plugin(
    name="outlook",
    hosts=("outlook.cloud.microsoft", "outlook.office.com", "outlook.office365.com", "outlook.live.com"),
    verbs=("status", "list", "read", "attachments", "save", "draft"),
    irreversible=(),
)
HOME_URL = "https://outlook.cloud.microsoft/mail/"
DRAFT_SAVED_PATTERN = re.compile(r"\bdraft saved\b", re.I)
_ATTACHMENTS = re.compile(r"\battachments?\b", re.I)


def add_arguments(parser, common) -> None:
    verbs = parser.add_subparsers(dest="plugin_verb")
    p = verbs.add_parser("status", help="is the mail client reachable, signed in, and its search present?")
    common(p, scoped=False)
    p = verbs.add_parser("list", help="search, then list result rows (id, sender and subject, time)")
    common(p, scoped=False)
    p.add_argument("query", help="the client's own search syntax, e.g. from:someone hasattachments:yes")
    p.add_argument("--limit", type=int, default=20)
    p = verbs.add_parser("read", help="open one message by id and print it")
    common(p, scoped=False)
    p.add_argument("id")
    p = verbs.add_parser("attachments", help="list one message's attachments")
    common(p, scoped=False)
    p.add_argument("id")
    p = verbs.add_parser("save", help="save one attachment through the download event, with its sha256")
    common(p, scoped=False)
    p.add_argument("id")
    p.add_argument("name", help="the attachment's file name, as `attachments` lists it")
    p.add_argument("--out", required=True, help="destination directory (never inside the agent's home)")
    p = verbs.add_parser("draft", help="compose a message and leave it in Drafts (there is no send)")
    common(p, scoped=False)
    p.add_argument("--to", action="append", default=[])
    p.add_argument("--cc", action="append", default=[])
    p.add_argument("--bcc", action="append", default=[])
    p.add_argument("--subject", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--body")
    g.add_argument("--body-file")


### pure parts, tested without a browser

def parse_rows(rows: List[dict]) -> List[dict]:
    """Result rows from the message list: id from the row, the rest from its accessible name."""
    out = []
    for r in rows:
        label = (r.get("name") or "").strip()
        unread = label.lower().startswith("unread")
        if unread:
            label = label[len("unread"):].strip()
        out.append({"id": r.get("convid") or "", "label": label, "unread": unread,
                    "attachments": bool(_ATTACHMENTS.search(label))})
    return out


def find_control(nodes: List[dict], role: str, name: str) -> dict:
    """The accessibility node a verb needs, or a refusal that names it (R38)."""
    for n in nodes:
        if n.get("role") == role and (n.get("name") or "").strip().lower() == name.lower():
            return n
    raise guard.Refused(f"the mail page has no {role} named {name!r}: the client's layout may have changed "
                        f"(MIS-0009-R38)")


### live parts

def _page(backend):
    page = backend.page_for(None, interact=True, open_url=HOME_URL)
    return page


def _search_box(page):
    for role in ("searchbox", "combobox", "textbox"):
        loc = page.get_by_role(role, name="Search", exact=True)
        if loc.count() == 1:
            return loc
    raise guard.Refused("the mail page has no Search box (MIS-0009-R38)")


def _open(backend, page, convid: str):
    row = page.locator(f'[data-convid="{convid}"]').first
    if row.count() == 0:
        raise guard.Refused(f"no message {convid!r} in the current list: list it first (MIS-0009-R38)")
    row.click()
    backend.settle(page)


def status(backend, args):
    page = _page(backend)
    enforce(PLUGIN, "status", page.url, None)
    nodes = backend.observe(page)["nodes"]

    def has(role, name):
        return any(n["role"] == role and n["name"].strip() == name for n in nodes)
    return {"host": guard.host_of(page.url), "search": any(n["name"].strip() == "Search" for n in nodes),
            "new_mail": has("button", "New mail"), "rows": sum(1 for n in nodes if n["role"] == "option")}


def list_rows(backend, args):
    page = _page(backend)
    enforce(PLUGIN, "list", page.url, None)
    box = _search_box(page)
    box.fill(args.query)
    backend.press(page, "Enter")
    options = page.get_by_role("option")
    rows = []
    for i in range(min(options.count(), args.limit)):
        o = options.nth(i)
        convid = o.get_attribute("data-convid") or o.locator("[data-convid]").first.get_attribute("data-convid")
        rows.append({"name": o.get_attribute("aria-label") or o.inner_text(), "convid": convid})
    return parse_rows(rows)


def read(backend, args):
    page = _page(backend)
    enforce(PLUGIN, "read", page.url, None)
    _open(backend, page, args.id)
    body = page.get_by_role("document", name="Message body")
    if body.count() == 0:
        body = page.locator('[aria-label="Message body"]')
    if body.count() == 0:
        raise guard.Refused("the mail page shows no Message body (MIS-0009-R38)")
    subject = page.get_by_role("heading").first.inner_text() if page.get_by_role("heading").count() else ""
    return {"id": args.id, "subject": subject, "body": body.first.inner_text()}


def _attachment_names(page) -> List[str]:
    names = []
    for o in page.locator('[role="listbox"][aria-label*="ttachment"] [role="option"]').all():
        names.append((o.get_attribute("aria-label") or o.inner_text()).strip())
    return names


def attachments(backend, args):
    page = _page(backend)
    enforce(PLUGIN, "attachments", page.url, None)
    _open(backend, page, args.id)
    return {"id": args.id, "attachments": _attachment_names(page)}


def save(backend, args):
    page = _page(backend)
    enforce(PLUGIN, "save", page.url, None)
    _open(backend, page, args.id)
    att = page.locator('[role="listbox"][aria-label*="ttachment"] [role="option"]').filter(has_text=args.name)
    guard.check_target(att.count(), att.count() == 1 and att.first.is_visible(), True, f"attachment {args.name!r}")
    att.first.get_by_role("button", name="More actions").click()
    backend.settle(page)
    return backend.download(page, "menuitem", "Download", args.out, exact=True)


def draft(backend, args):
    """Compose and leave the message in Drafts. Fields are set by value with fill(); nothing is typed."""
    page = _page(backend)
    enforce(PLUGIN, "draft", page.url, None)
    backend.click(page, "button", "New mail", exact=True)
    for label in ("Cc", "Bcc"):
        if getattr(args, label.lower()):
            btn = page.get_by_role("button", name=f"Show {label}")
            if btn.count() == 0:
                btn = page.get_by_role("button", name=label, exact=True)
            if btn.count():
                btn.first.click()
    for label, values in (("To", args.to), ("Cc", args.cc), ("Bcc", args.bcc)):
        if not values:
            continue
        field = page.get_by_role("textbox", name=label, exact=True)
        guard.check_target(field.count(), field.count() == 1 and field.is_visible(), True, f"{label} field")
        field.fill("; ".join(values) + ";")
    subject = page.get_by_role("textbox", name="Subject")
    if subject.count() == 0:
        subject = page.get_by_role("textbox", name="Add a subject")
    guard.check_target(subject.count(), subject.count() == 1 and subject.is_visible(), True, "Subject field")
    subject.fill(args.subject)
    text = open(args.body_file).read() if args.body_file else args.body
    body = page.get_by_role("textbox", name="Message body")
    guard.check_target(body.count(), body.count() == 1 and body.is_visible(), True, "Message body")
    body.fill(text)
    page.get_by_text(DRAFT_SAVED_PATTERN).first.wait_for(timeout=30000)
    return {"left_in": "Drafts", "to": args.to, "cc": args.cc, "bcc": args.bcc, "subject": args.subject,
            "next": "open Drafts in the mail client, check it, and send it yourself"}


VERBS = {"status": status, "list": list_rows, "read": read, "attachments": attachments, "save": save,
         "draft": draft}


def run(backend, args):
    return VERBS[args.plugin_verb](backend, args)
