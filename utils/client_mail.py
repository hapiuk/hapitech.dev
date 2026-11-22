# utils/client_mail.py — emails sent to a client's customers, in the client's name.
# From: "<Business name> <SMTP_FROM>", Reply-To: the client's own email, so customers reply to them.
from flask import url_for

from utils.links import public_url
from utils.mailer import send_email


def _send(lead, subject, body):
    a = lead.account
    if not lead.email:
        raise ValueError("This customer has no email address.")
    sign = a.contact_name or a.name
    send_email(to=lead.email, subject=subject, from_name=a.name, reply_to=a.contact_email or None,
               text=f"{body}\n\n{sign}\n{a.name}" + (f"\n{a.contact_phone}" if a.contact_phone else ""))


def _when(lead):
    d = lead.start_at
    day = d.strftime("%A %-d %B")
    t = d.strftime("%-I:%M%p").lower().replace(":00", "")
    span = f" ({lead.days} days)" if lead.days and lead.days > 1 else ""
    return f"{day} at {t}{span}"


def send_quote(quote):
    lead = quote.lead
    link = public_url(url_for("customer.quote", token=quote.token))
    _send(lead, f"Your quote from {lead.account.name}",
          f"Hi {lead.name.split()[0]},\n\nThanks for getting in touch. Here's your quote for "
          f"{lead.label.lower()}:\n{link}\n\nYou can accept it, or let us know it's not for you, from that page.")


def send_booking_confirmation(lead):
    _send(lead, f"Booked: {lead.label} on {lead.start_at.strftime('%-d %B')}",
          f"Hi {lead.name.split()[0]},\n\nYou're booked in for {_when(lead)}"
          + (f" at {lead.postcode}" if lead.postcode else "") + ".\n\n"
          "We'll send a reminder the day before. If anything changes, just reply to this email.")


def send_booking_reminder(lead):
    _send(lead, f"See you tomorrow: {lead.label}",
          f"Hi {lead.name.split()[0]},\n\nJust a reminder that we're booked in for {_when(lead)}.\n\n"
          "If anything has changed, reply to this email.")


def send_invoice(invoice):
    lead = invoice.lead
    link = public_url(url_for("customer.invoice", token=invoice.token))
    due = f" by {invoice.due_date.strftime('%-d %B %Y')}" if invoice.due_date else ""
    _send(lead, f"Invoice {invoice.number} from {lead.account.name}",
          f"Hi {lead.name.split()[0]},\n\nThanks again for having us. Your invoice for {lead.label.lower()} "
          f"(£{invoice.totals[2]:,.2f}) is here:\n{link}\n\nPayment details are on the invoice. "
          f"Please pay{due}.")


def send_review_request(lead, link):
    _send(lead, f"How did we do?",
          f"Hi {lead.name.split()[0]},\n\nThanks for choosing {lead.account.name}! "
          f"Would you mind leaving a quick review? It takes about 20 seconds:\n{link}")


def send_repeat_reminder(rem):
    lead = rem.lead
    stop = public_url(url_for("customer.reminder_stop", token=rem.token))
    _send(lead, f"A reminder from {lead.account.name}",
          f"Hi {lead.name.split()[0]},\n\nYou asked us to remind you: {rem.note}\n\n"
          f"If you'd like to book, just reply to this email.\n\n"
          f"(You asked for this reminder. To stop it: {stop})")
