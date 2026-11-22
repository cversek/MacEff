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
    verbs=("status", "list", "read", "attachments", "save", "draft", "discard"),
    irreversible=("discard",),
)
HOME_URL = "https://outlook.cloud.microsoft/mail/"
DRAFT_SAVED_PATTERN = re.compile(r"\bdraft saved\b", re.I)
_ATTACHMENTS = re.compile(r"\battachments?\b", re.I)
# The search box is "Search" in one state and "Search for email, meetings, files and more." in another.
SEARCH_NAME = re.compile(r"^Search\b(?! Folders)")
# The tab of an open compose form: "Editing <subject> Close". Closing it keeps the draft in Drafts.
OPEN_DRAFT_TAB = re.compile(r"^Editing .* Close$")


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
    p = verbs.add_parser("discard", help="discard one draft by id (irreversible: needs the operator's words)")
    common(p, scoped=False)
    p.add_argument("id")
    p.add_argument("--operator-said", help="the operator's words for this discard, verbatim")
    p.add_argument("--said-source", help="where the operator said it: a channel message id or a transcript turn")


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
    """The plugin's own tab, opened on first use, once the client has drawn its message list."""
    page = backend.page_for(None, interact=True, open_url=HOME_URL)
    ready = page.get_by_role("listbox", name="Message list")
    try:
        ready.first.wait_for(timeout=45000)
    except Exception as e:
        raise guard.Refused(f"the mail client drew no Message list within 45 s (MIS-0009-R38): {e}") from e
    return page


def _search_box(page):
    for role in ("combobox", "searchbox"):
        loc = page.get_by_role(role, name=SEARCH_NAME)
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
    return {"host": guard.host_of(page.url), "search": any(n["role"] in ("combobox", "searchbox") and SEARCH_NAME.match(n["name"]) for n in nodes),
            "new_mail": has("button", "New mail"), "rows": sum(1 for n in nodes if n["role"] == "option")}


def list_rows(backend, args):
    page = _page(backend)
    enforce(PLUGIN, "list", page.url, None)
    box = _search_box(page)
    box.fill(args.query)
    backend.press(page, "Enter")
    # Results draw after the search returns: wait for the Results heading, then for the row count to hold still.
    page.get_by_role("heading", name="Results").first.wait_for(timeout=30000)
    options = page.get_by_role("listbox", name="Message list").get_by_role("option")
    last, steady = -1, 0
    for _ in range(40):
        n = options.count()
        steady = steady + 1 if n == last else 0
        if steady >= 3:
            break
        last = n
        page.wait_for_timeout(500)
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
    pane = page.get_by_role("main", name="Reading Pane")
    heads = (pane if pane.count() else page).get_by_role("heading")
    subject = heads.first.inner_text().strip() if heads.count() else ""
    links = [{"text": (a.inner_text() or "").strip()[:80], "href": a.get_attribute("href")}
             for a in body.first.locator("a[href]").all()]
    return {"id": args.id, "subject": subject, "body": body.first.inner_text(), "links": links}


def _attachment_names(page) -> List[str]:
    names = []
    for o in page.locator('[role="listbox"][aria-label*="ttachment"] [role="option"]').all():
        names.append(attachment_name((o.get_attribute("aria-label") or o.inner_text()).strip()))
    return names


_FILE = re.compile(r"^(.+?\.[A-Za-z0-9]{1,6})(?=\s|$)")


def attachment_name(label: str) -> str:
    """The file name from an attachment's label, which also carries its actions and size ("x.xlsx Open 40 KB")."""
    m = _FILE.match(label.strip())
    return m.group(1) if m else label.strip()


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
    # A compose form already open is never closed or refilled by the plugin: on 2026-11-21 closing one to start the
    # next draft lost the earlier draft from Drafts. The operator closes it (and sees what the client does with it).
    open_form = page.get_by_role("button", name=OPEN_DRAFT_TAB)
    if open_form.count():
        raise guard.Refused(f"a compose form is open ({open_form.first.inner_text()!r}); close it in the mail client "
                            f"and check Drafts before the next draft")
    leave_search = page.get_by_role("button", name="Exit search", exact=True)
    if leave_search.count() == 1 and leave_search.is_visible():  # the search ribbon hides New mail
        backend.click(page, "button", "Exit search", exact=True)
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
        # The recipient wells are editable regions labeled To, Cc and Bcc, not text boxes in the tree.
        field = page.locator(f'[contenteditable="true"][aria-label="{label}"]')
        guard.check_target(field.count(), field.count() == 1 and field.is_visible(), True, f"{label} field")
        # The client's recipient picker answers only to typed characters: fill() replaced the well (wiping
        # resolved recipients) and inserted text never resolved. So each address is typed as plain characters,
        # which can't form a sending chord, and Enter, checked by the guard, turns it into a recipient (R18).
        # Message text is still set by value (R37).
        field.focus()
        for address in values:
            page.keyboard.type(address, delay=20)
            page.wait_for_timeout(1500)
            backend.press(page, "Enter")
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


def discard(backend, args):
    """Discard one draft. Irreversible, so the operator's words are checked twice: by the plugin's declaration and
    by the guard on the Discard control and on any confirming button (R17)."""
    page = _page(backend)
    enforce(PLUGIN, "discard", page.url, args.operator_said)
    _open(backend, page, args.id)
    if page.get_by_text(re.compile(r"^\[Draft\]|^Draft$")).count() == 0 and \
            page.get_by_role("button", name="Discard", exact=True).count() == 0:
        raise guard.Refused(f"message {args.id!r} is not a draft: only drafts are discarded")
    report = backend.click(page, "button", "Discard", exact=True, operator_said=args.operator_said)
    confirm = page.get_by_role("dialog").get_by_role("button", name=re.compile(r"^(Discard|OK|Delete)$"))
    if confirm.count() == 1:
        name = confirm.first.get_attribute("aria-label") or confirm.first.inner_text()
        report = backend.click(page, "button", name.strip(), exact=True, operator_said=args.operator_said)
    return {"id": args.id, "discarded": True, "changed": report.get("changed"),
            "where": "Deleted Items, where the operator can still recover it"}


VERBS = {"status": status, "list": list_rows, "read": read, "attachments": attachments, "save": save,
         "draft": draft, "discard": discard}


def run(backend, args):
    return VERBS[args.plugin_verb](backend, args)
