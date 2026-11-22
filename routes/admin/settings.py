# routes/admin/settings.py — your own password, email test, AI news feed health.
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user

from models import db
from utils.mailer import send_email

from . import admin_bp


@admin_bp.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "password":
            cur, new, new2 = (request.form.get(k, "") for k in ("current", "new", "new2"))
            if not current_user.check_password(cur):
                flash("Your current password isn't right.", "err")
            elif len(new) < 12:
                flash("Use at least 12 characters.", "err")
            elif new != new2:
                flash("The new passwords don't match.", "err")
            else:
                current_user.set_password(new)
                db.session.commit()
                flash("Password changed.", "ok")
        elif action == "test-email":
            try:
                send_email(to=current_user.email, subject="HapiTech test email",
                           text="If you can read this, outgoing email works.")
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
