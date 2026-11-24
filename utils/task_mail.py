# utils/task_mail.py — emails about tasks and change requests. Every email links straight to the item:
# clients to /portal/changes/…, Aaron to /admin/tasks/… . Clients only ever hear about shared tasks.
from flask import url_for

from utils.links import public_url

ADMIN_EMAIL = "aaron@hapitech.dev"


def client_task_url(t):
    return public_url(url_for("portal.request_task", tid=t.id))


def client_request_url(cr):
    return public_url(url_for("portal.request_cr", rid=cr.id))


def admin_task_url(t):
    return public_url(url_for("admin.task", tid=t.id))


def admin_request_url(cr):
    return public_url(url_for("admin.change_requests", r=cr.id) + f"#r{cr.id}")


def _client_emails(account, extra_user=None):
    """The business's contact address plus its owners' logins (never Aaron's admin address)."""
    out = []
    people = [u.email for u in (account.users if account else []) if u.role == "owner" and u.is_active and not u.is_admin]
    for e in [account.contact_email if account else None, extra_user.email if extra_user else None] + people:
        e = (e or "").strip()
        if e and e.lower() != ADMIN_EMAIL and e.lower() not in [x.lower() for x in out]:
            out.append(e)
    return out


def _send(to_list, subject, **content):
    from utils import email_html
    for to in to_list:
        try:
            email_html.send(to, subject, **content)
        except Exception as exc:
            print(f"[TASK_MAIL] {to}: {exc}")


def tell_client_task(t, subject, heading, lines, box=None):
    """A shared task changed (accepted, status, a reply from Aaron)."""
    if not (t.shared and t.account):
        return
    cr_author = t.change_request.author if t.change_request else None
    _send(_client_emails(t.account, cr_author), f"{subject} ({t.ref})", heading=heading, lines=lines,
          box=[("Reference", t.ref + (f" (your request {t.change_request.ref})" if t.change_request else "")),
               ("What", t.title)] + (box or []),
          button={"label": "Open it", "url": client_task_url(t)},
          after=["You can reply to Aaron on that page."])


def tell_client_request(cr, subject, heading, lines):
    """A change request changed but has no task (e.g. marked done straight away)."""
    _send(_client_emails(cr.account, cr.author), f"{subject} ({cr.ref})", heading=heading, lines=lines,
          box=[("Reference", cr.ref), ("Your request", (cr.body or "")[:300])],
          button={"label": "Open it", "url": client_request_url(cr)})


def tell_aaron_new_request(cr, user):
    _send([ADMIN_EMAIL], f"Change request {cr.ref}: {cr.account.name}", heading=f"{cr.account.name} asked for a change",
          lines=[f"From {user.name or user.email}:", cr.body], box=[("Reference", cr.ref)],
          button={"label": "Open the request", "url": admin_request_url(cr)})


def tell_aaron_comment(t, note, user):
    _send([ADMIN_EMAIL], f"{t.tag} replied on {t.ref}: {t.title[:60]}", heading=f"New comment on {t.ref}",
          lines=[f"{user.name or user.email} ({t.tag}) wrote:", note.body], box=[("Task", f"{t.ref} · {t.title}")],
          button={"label": "Open the task", "url": admin_task_url(t)})
