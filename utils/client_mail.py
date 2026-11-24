# utils/client_mail.py — emails sent to a client's customers, in the client's name and colours.
# From: "<Business name> <SMTP_FROM>", Reply-To: the client's own email, so customers reply to them.
from flask import url_for

from utils import email_html
from utils.links import public_url


def _send(lead, subject, **content):
    a = lead.account
    if not lead.email:
        raise ValueError("This customer has no email address.")
    sign = f"Thanks,\n{a.contact_name or a.name}"
    footer = " · ".join(x for x in [a.name, a.contact_phone] if x)
    email_html.send(lead.email, subject, account=a, from_name=a.name, reply_to=a.contact_email or None,
                    sign=sign, footer=footer, **content)


def _first(lead):
    return lead.name.split()[0]


def _when(lead):
    d = lead.start_at
    day = d.strftime("%A %-d %B")
    t = d.strftime("%-I:%M%p").lower().replace(":00", "")
    return f"{day}, {t}"


def _booking_box(lead):
    box = [("When", _when(lead))]
    if lead.days and lead.days > 1:
        box.append(("How long", f"{lead.days} days"))
    box.append(("Job", lead.label))
    if lead.postcode:
        box.append(("Where", lead.postcode))
    return box


def send_quote(quote):
    lead = quote.lead
    total = f"£{quote.totals[2]:,.2f}"
    _send(lead, f"Your quote from {lead.account.name}",
          heading=f"Your quote is ready, {_first(lead)}",
          lines=[f"Thanks for getting in touch. Here's your quote for {lead.label.lower()}."],
          box=[("Quote", quote.number), ("Total", total)] +
              ([("Valid until", quote.valid_until.strftime("%-d %B %Y"))] if quote.valid_until else []),
          button={"label": "View and accept your quote", "url": public_url(url_for("customer.quote", token=quote.token))},
          after=["If it's not for you, you can say so on the same page. No hard feelings."])


def send_booking_confirmation(lead):
    _send(lead, f"You're booked in: {lead.start_at.strftime('%A %-d %B')}",
          heading=f"You're booked in, {_first(lead)}",
          lines=["Here are the details."], box=_booking_box(lead),
          after=["We'll send you a reminder the day before. If anything changes, just reply to this email."])


def send_booking_reminder(lead):
    _send(lead, f"See you tomorrow, {_first(lead)}",
          heading="See you tomorrow",
          lines=[f"Just a quick reminder, {_first(lead)}."], box=_booking_box(lead),
          after=["If anything has changed, reply to this email and let us know."])


def send_invoice(invoice):
    lead = invoice.lead
    box = [("Invoice", invoice.number), ("Amount", f"£{invoice.totals[2]:,.2f}")]
    if invoice.due_date:
        box.append(("Please pay by", invoice.due_date.strftime("%-d %B %Y")))
    from utils.pay_links import for_invoice
    page = public_url(url_for("customer.invoice", token=invoice.token))
    pay = for_invoice(lead.account, float(invoice.totals[2]))
    if pay:                                          # one tap to pay; the invoice itself is a link underneath
        _send(lead, f"Invoice {invoice.number} from {lead.account.name}",
              heading=f"Thanks again, {_first(lead)}",
              lines=[f"Here's the invoice for {lead.label.lower()}."],
              box=box + [("Reference", invoice.number)],
              button={"label": f"Pay £{invoice.totals[2]:,.2f} " + ("online" if pay["kind"] == "other" else f"with {pay['label']}"),
                      "url": pay["url"]},
              after=[("" if pay["with_amount"] else f"Enter £{invoice.totals[2]:,.2f} and ") + f"use {invoice.number} as the reference.",
                     f"See the full invoice (or other ways to pay): {page}"])
        return
    _send(lead, f"Invoice {invoice.number} from {lead.account.name}",
          heading=f"Thanks again, {_first(lead)}",
          lines=[f"Here's the invoice for {lead.label.lower()}. Payment details are on it."],
          box=box,
          button={"label": "View your invoice", "url": page},
          after=["You can print it or save it as a PDF from that page."])


def send_receipt(invoice):
    """A paid invoice, sent as a receipt (the same page shows "Receipt" and "✓ Paid")."""
    lead = invoice.lead
    _send(lead, f"Receipt {invoice.number} from {lead.account.name}",
          heading=f"Thanks, {_first(lead)}: all done ✓",
          lines=[f"Here's your receipt for {lead.label.lower()}."],
          box=[("Receipt", invoice.number), ("Amount", f"£{invoice.totals[2]:,.2f}"),
               ("Paid", (invoice.paid_at or invoice.updated_at).strftime("%-d %B %Y") if invoice.totals[2] else "Nothing to pay")],
          button={"label": "View your receipt", "url": public_url(url_for("customer.invoice", token=invoice.token))},
          after=["You can print it or save it as a PDF from that page."])


def send_review_request(lead, link, first_name=None):
    who = first_name or (_first(lead) if getattr(lead, "name", None) else None)
    a = lead.account
    _send(lead, f"How did {a.contact_name or a.name} do?",
          heading=f"Thanks for choosing {a.name}" + (f", {who}" if who else "") + "!",
          lines=["Would you mind leaving a quick review? It really helps a small local business, "
                 "and it only takes about 20 seconds."],
          button={"label": "⭐ Leave a review", "url": link})


def send_repeat_reminder(rem):
    lead = rem.lead
    stop = public_url(url_for("customer.reminder_stop", token=rem.token))
    _send(lead, f"A reminder from {lead.account.name}",
          heading=f"Hi {_first(lead)}, a friendly reminder",
          lines=[f"You asked us to remind you: {rem.note}.", "If you'd like to book it in, just reply to this email."],
          after=[f"You asked for this reminder. Don't want it? Stop it here: {stop}"])


class _OneOff:
    """Lets send_review_request work for the "email them the link" button, which has no job record."""
    def __init__(self, account, email, name=None):
        self.account, self.email, self.name, self.label = account, email, name or "", ""


def send_review_link(account, email, link, first_name=None):
    send_review_request(_OneOff(account, email, first_name), link, first_name=first_name)
