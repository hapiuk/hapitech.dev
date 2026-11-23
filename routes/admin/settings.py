# routes/admin/settings.py — email test and AI news feed health.
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from utils.mailer import send_email

from . import admin_bp


@admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "test-email":
            try:
                from utils import email_html
                email_html.send(current_user.email, "HapiTech test email", heading="Email is working",
                                lines=["If you can read this, outgoing email from hapitech.dev works."])
                mode = current_app.config.get("MAIL_MODE")
                flash("Test email sent." if mode == "smtp" else "Test email written to instance/mail_outbox (log mode).", "ok")
            except Exception as exc:
                flash(f"Email failed: {exc}", "err")
        return redirect(url_for("admin.settings"))

    from utils.news import FEEDS, get_news, humanise_age
    news = get_news(blocking=False)
    per_source = {}
    for it in news.get("items", []):
        per_source[it["source_id"]] = per_source.get(it["source_id"], 0) + 1
    return render_template("admin/settings.html", feeds=FEEDS, news=news, per_source=per_source,
                           updated=humanise_age(news.get("fetched_at")),
                           mail_mode=current_app.config.get("MAIL_MODE"))
