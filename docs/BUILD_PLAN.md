# HapiTech platform rebuild: build plan

_Drafted 22 Nov 2026, revised the same day with Aaron's answers. Status: plan only, no work started._

**Decisions so far**
- hapitech.report and Solar Journal are **removed** from hapitech.dev.
- Reviews are **centralised on hapitech.dev** and fed into Roland's and Ray G's sites.
- Ray G's current site reviews are real (copied from his actual reviews). The "placeholder" comment only meant they're waiting to be automated. They get imported as real reviews.
- Deploys: Aaron pulls on the server himself using the one-line command in section 8.
- **No paid SMS provider.** Texts go from the tradesperson's own phone (see "Ask for a review" below).
- **Clients can make reasonable content changes themselves** (posts, photos, the text and prices of their services, opening hours). Anything bigger stays a change request to HapiTech.
- **Reviews and Updates is a paid add-on**, with a free trial so clients can see it working on real jobs first.
- **All existing reviews on both sites come from their Google Business Profiles.**
- **Build everything locally first.** Roland's and Ray G's sites must look the same afterwards unless a change is truly needed.

## Progress log

| Date | Phase | Status | Notes |
|---|---|---|---|
| 22 Nov 2026 | Public site v5 | ✅ On GitHub `main` (`1e4469a`) | Server pull pending (section 8) |
| 22 Nov 2026 | Plan | ✅ Agreed | Decisions above |
| 22 Nov 2026 | 0: Safety and clear-out | ✅ Built locally (branch `platform-rebuild`) | Solar Journal + hapitech.report code removed; seeded admin password gone (`flask create-admin`); login codes use `secrets` and are stored hashed; app refuses to start in production without `SECRET_KEY`; privacy/terms updated |
| 22 Nov 2026 | 1: Foundation | ✅ Built locally | New models + migration `a1b2c3d4e5f6` (copies clients/jobs/payments across, keeps old tables for now); CSRF on every form/fetch; DB-backed login rate limit; `flask deploy` (backup → migrate); `flask seed-dev` |
| 22 Nov 2026 | 2: Login modal | ✅ Built locally | Pop-up on every public page (password / email code / forgot); role routing to `/admin` or `/portal`; invite + reset links (48 h, single use) |
| 22 Nov 2026 | 3: Admin clients & money | ✅ Built locally | Overview (money, overdue, unpaid jobs, live site + SSL check), clients, jobs, subscriptions, payments, notes, logins, add-on switch, site keys, change requests |
| 22 Nov 2026 | 4: Benchmarks | ✅ Built locally | 3 models, all 8 prompts (+ fixtures, versioned), 11 published runs imported; upload → draft → publish; public `/lab`; Lab results in AI news |
| 22 Nov 2026 | 5: Reviews core | ✅ Built locally | "Job done → ask" (SMS/WhatsApp from own phone, email, QR, link); client-branded review form; Google hand-off; inbox, replies, reports; review pages; 16 existing Google reviews imported (dates left blank: real dates unknown) |
| 22 Nov 2026 | 6: Portal posts + client sites | 🟡 Portal side built (posts, photo upload, content-block editor, site API). **Not yet done:** switching Roland's/Ray's sites to read from the API, and defining each site's editable blocks | Sites must look identical afterwards |
| — | 7: Google sync | ⏳ Not started | Needs Google Business Profile API approval |
| — | 8: Polish | ⏳ Not started | |

**Tests:** `.venv/bin/python -m pytest -q` (17 checks: auth, lockout, CSRF, tenancy, full review flow, EXIF stripping, site API keys, benchmark upload/publish, every page renders).

---

One Flask app (hapitech.dev) serves three audiences from one login:

| Who | Lands on | Does |
|---|---|---|
| Aaron (admin) | `/admin` | Tracks clients, jobs and money; publishes AI benchmark results; manages prompts; runs the review system for clients |
| Client owners (Roland, Ray) | `/portal` | Posts updates to their website, requests reviews, reads and replies to reviews |
| Their customers | Public review link | Leave a review (no account needed) |

The public site (home, news, privacy, terms) is unaffected.

---

## 1. What exists today (audit)

**Keep, because it works and is in use**
- Public site v5 (`templates/site/`, `templates/home.html`, `/news`): just shipped.
- `utils/mailer.py`: SMTP sending, used by the contact form and login codes.

**Remove entirely (decided)**
- Solar Journal: `routes/solar_system.py`, `routes/journal_api.py`, `models/solar_user.py`, `utils/journal_db.py`, `utils/solar_journal_limits.py`, `utils/body_*.py`, `templates/solar_system/`, `static/solar-system/`, the `solar` DB bind and its startup `ALTER TABLE` patches, the `solar-` branch in `load_user`, and the `/solar-system/` prefixes in the JSON error handler.
- hapitech.report: `routes/report_tenants.py` (the tenant parts), `REPORT_DATABASE_URL`, `models/pricing_tier.py`, `routes/pricing_config.py`, `templates/admin/report_tenants/`, `templates/admin/pricing_config/`.
- **Privacy policy and terms:** remove the Solar Journal sections in the same release, and add a section covering the review system (what we store about reviewers, and why).
- Back up the `solar_journal.db` file and the related tables before deleting, in case they're ever needed.

**Replace (the "wipe")**
| Current | Problem | Replacement |
|---|---|---|
| `Client`, `User.client_id` | Two client tables (`clients` and `webdev_clients`) that don't link to each other | One `Account` model |
| `WebdevClient`, `WebdevJob`, `RecurringPayment`, `MonthlyPaymentStatus` | Finance spread over 4 tables, with `client_type` strings instead of foreign keys | `Job`, `Subscription`, `Payment` |
| `templates/admin/*` (inline styles, R&D "Labs" panel) | Hard to extend | New admin UI on the `site.css` tokens (dark/light) |
| `templates/client/dashboard.html` (726 lines, only 3 template tags) | A static mock with no backend | The real `/portal` |
| `templates/login.html` page | Separate page | A login modal on every public page |
| `routes/ai_benchmarks.py` + JSONL files in git | Results only publish through git commits | Benchmark tables + an upload flow in the admin |

**Security issues to fix during the rebuild**
1. `app.py` seeds `aaron@hapitech.dev` with the password `Password1234!` when the users table is empty. Remove it and add a `flask create-admin` CLI command instead.
2. Login codes use `random.randint`. Switch to `secrets.randbelow`, store a hash instead of the plain code, and limit attempts.
3. `SECRET_KEY` falls back to `"dev-only-fallback-change-me"`. Make the app refuse to start in production without a real key.
4. There's no CSRF protection on admin POST routes (`/admin/api/service/<svc>/restart` and others). Add Flask-WTF CSRF, or a same-origin check plus a token for the JSON endpoints.
5. There's no login rate limiting. Add Flask-Limiter (hapitech.report already plans Redis for this).

**Client sites today**
- Both sites hard-code their reviews in `app.py`: Roland's in a `reviews` list, and Ray G's under a comment reading `PLACEHOLDER REVIEWS` (these are real reviews; the comment means "to be automated"). Reword that comment when the sites switch to the API, so nobody reading the code later takes them for invented reviews.

---

## 2. Data model (new)

```
Account            id, name, slug, kind (client|internal), status, domain, notes, created_at
User               id, email (unique), name, password_hash (argon2), role (admin|owner|staff),
                   account_id → Account (null for admin), last_login_at, is_active
Job                id, account_id, title, type (build|change|hosting|ai_setup|ai_intro|it_support|other),
                   status (quote|booked|in_progress|done|cancelled), price_gbp, due_date, notes
Subscription       id, account_id, title, amount_gbp, interval (monthly|yearly), next_due, status
Payment            id, account_id, job_id?/subscription_id?, amount_gbp, paid_at, method, ref
Note               id, account_id, author_id, body, created_at              (client timeline)

Post               id, account_id, title, body (markdown), cover_image, status (draft|published),
                   published_at, author_id
Media              id, account_id, file_path, width, height, alt, uploaded_by
ContentBlock       id, account_id, key (e.g. services.bathrooms.price), type (text|longtext|price|images|hours),
                   label, value (JSON), max_length, sort, updated_by, updated_at
ContentBlockVersion id, block_id, value (JSON), saved_by, saved_at              (undo history)
ChangeRequest      id, account_id, body, status (new|doing|done), created_by, created_at
AddOn              id, account_id, kind (reviews_updates), status (trial|active|paused), trial_ends_at

Review             id, account_id, source (hapitech|google|facebook|checkatrade|manual),
                   external_id?, author_name, rating 1–5, body, photos[], service?, job_date?,
                   status (pending|published|reported|removed), verified (bool),
                   source_url?, created_at, imported_at?
ReviewReply        id, review_id, body, author_id, created_at
ReviewRequest      id, account_id, customer_name, contact (email|phone),
                   token (unique, single-use), job_ref?, sent_via (sms|whatsapp|email|qr|link),
                   created_at, opened_at, completed_at, reminder_sent_at
ReviewSource       id, account_id, kind (google|facebook), external_account_id, oauth_token_enc,
                   last_synced_at, status

BenchModel         id, slug, display_name, maintainer, quant, file_size_bytes, native_ctx,
                   supports_vision, supports_tools, source_url, blurb, hardware_profile, status
BenchPrompt        id, slug (e.g. 02-tool-calling), name, category, kind, description, prompt_text,
                   pass_criteria, grading, max_tokens, repeats, fixtures (JSON), version, is_current
BenchRun           id, prompt_id, model_id, started_at, engine (JSON), harness (JSON),
                   context_length, status (draft|published|withdrawn), notes, published_at
BenchResult        id, run_id, repeat_n, passed, score, ttft_ms, prefill_tps, decode_tps,
                   prompt_tokens, completion_tokens, total_seconds, raw (JSON), artefact_path?
```

Notes
- Everything a client can touch is filtered by `account_id` in one shared query helper, never by hand in each route.
- `BenchPrompt` is versioned: editing a prompt creates v2, and old runs keep pointing at the version they actually used.
- External reviews keep `source` and `source_url`, so they're always shown with attribution and a link back.

---

## 3. Login modal and routing

1. "Client login" on every public page opens a modal (no page change). It has two tabs: **Password**, and **Email me a code** (the existing OTP flow, hardened).
2. `POST /auth/login` returns `{ok, redirect}`: `/admin` for admins, `/portal` for owners and staff. Failures get one generic message.
3. `/login` stays as a full page for no-JS visitors and for redirects from protected pages (`?next=` is allowed only for same-site paths).
4. Session hardening: `SESSION_COOKIE_SECURE`, `HTTPONLY`, `SAMESITE=Lax`; 14-day "remember me"; logout clears the session server-side.
5. The admin can invite a client user: they get an email link to set a password (a signed token with a 48-hour expiry).

---

## 4. Admin dashboard (`/admin`), the part for Aaron

**Home:** money this month (paid / due / overdue), jobs in progress, review requests awaiting a reply, latest benchmark run, site status for each client domain (HTTP check plus SSL expiry date).

**Clients:** list → account page with tabs:
- Overview (domain, contacts, notes timeline)
- Jobs and quotes
- Subscriptions and payments (mark paid, next due)
- Users (invite, disable)
- Reviews (see everything they see, help moderate)
- Posts (draft on their behalf)

**AI benchmarks**
- **Models:** imported from `ai-benchmarks/models.json`. Edit specs, mark candidates as blocked or retired.
- **Prompts:** all eight current prompts (`00`–`07`) imported from `ai-benchmarks/prompts/*.json`, with fixtures from `ai-benchmarks/fixtures/` and the originals in `/mnt/data/Hapitech_AI/docs/local_ai_benchmark_prompts/`. You can view, copy, version and attach fixtures.
- **Runs:** "New run" → pick prompt + model → paste or upload the result JSONL (the format `publish_results.py` already writes) → preview the parsed numbers → **Publish**. Published runs show on the public results page and in AI News as a "HapiTech Lab" item.
- **Import:** a one-off script loads the historical published results from the `benchmark-wip` branch (`ai-benchmarks/published/00…05.jsonl`) as published runs.

**Settings:** SMTP test, news feed health (last refresh and errors per feed), the admin's own password and 2FA (TOTP, later).

### How to post a benchmark result (draft instructions)
1. Run the test through Hermes as today (`hapitech-model-tester` → target profile). `capture_telemetry.py` records the hardware metrics.
2. When the tester approves a result, `hapitech-benchmark` writes the JSONL record (unchanged format).
3. Open **Admin → AI benchmarks → New run**. Pick the prompt and model, then drop in the JSONL (and any HTML artefact, such as the game builds from prompts 06/07).
4. Check the preview: pass/fail, tokens/sec, time to first token. Add a plain-English note.
5. Click **Publish**. The run appears on the public results page and in AI News, credited "HapiTech Lab".
6. Wrong numbers? Open the run and click **Withdraw**. It's hidden at once and kept for the record.

Later (optional): an authenticated `POST /api/bench/runs` endpoint with an API key, so `hapitech-benchmark` can submit drafts directly. Publishing would still be a human click.

---

## 5. Client portal (`/portal`), for Roland and Ray

Kept deliberately small, mobile-first and in plain language.

**Home:** "3 new reviews · 1 waiting for a reply · Your last post was 12 days ago" plus two big buttons: **Ask for a review** and **Post an update**.

**Posts:** title, a few lines of text, up to 6 photos taken straight from the phone camera, then Publish. Shown on their website in a "Latest work" section. Drafts are allowed, and the admin can edit.

**My website (reasonable self-service changes):** each site exposes a small set of named, editable content blocks. These are service names, descriptions and "from" prices, gallery photos (add, remove, reorder), opening hours, service-area towns, and the phone and WhatsApp numbers. Each block has a type (short text, long text, price, image list) and a length limit, so nothing can break the layout. Changes go live within 10 minutes (the site's cache window), with an **Undo** for the last version of each block. For anything else (new pages, layout or design) there's a **Request a change** form that goes to HapiTech. Until a site is switched over, each block's default is its current hard-coded text, so the site looks identical.

**Reviews**
- The inbox lists all reviews from every source, newest first, with filters.
- **Reply** publishes the reply under the review on their site (and to Google, when that's connected).
- **Report** flags an abusive or fake review to HapiTech for removal. Owners can't delete or hide genuine negative reviews: the law requires all genuine reviews to be shown fairly (it's also what makes the system trustworthy).

**Ask for a review: the "job done" moment (like Uber asking for a rating)**
- On their phone at the end of a job, the tradesperson taps **Job done → Ask for a review**, types the customer's name and number, and taps **Send text**. Their phone's messaging app opens with the message and link already written ("Thanks for having me round today, Sarah! Could you leave a quick review? It takes 20 seconds: <link>"). They press send, so it **comes from their own number**: no SMS provider, no cost per text, and the customer recognises the sender. Under the hood this is a standard `sms:` link.
- The same screen offers **WhatsApp** (pre-filled the same way), **Email** (sent by HapiTech from their branded address) and **Show QR code** (the customer scans it on the doorstep).
- The customer opens the link and sees the business logo, "How did Roland do?", five big stars, an optional comment and optional photos, then a thank-you screen with an "Also post on Google" button. It's built to take about 20 seconds on a phone.
- **Reminders:** the portal lists requests that haven't been answered after 5 days with a **Send reminder** button (from their phone again). Fully automatic texts would need an Android phone running an SMS-gateway app (it sends texts from that phone's own SIM). That's a possible later add-on, not part of v1.
- **Optional:** printed leave-behind cards with a QR code that goes straight to their review page.
- The link is single-use (`hapitech.dev/r/<token>`, or `<their-domain>/review/<token>`). It opens a 3-tap review form: stars, words, optional photos. Reviews from links are marked **Verified customer**.
- One automatic reminder after 5 days if the review isn't done, then stop.
- Never gate reviews (for example, only sending happy customers to Google). Every request gets the same form.

**Import existing reviews**
| Source | How | Notes |
|---|---|---|
| Google Business Profile | Owner connects Google once (OAuth). We sync all reviews and can post replies through the Business Profile API | Needs Google API access approval for the HapiTech project. Apply early, as it takes weeks. Don't use the Places API: it returns only 5 reviews and its terms forbid storing them |
| Facebook page | Page admin connects once (Graph API, `pages_read_user_content`) | Needs Meta app review |
| Checkatrade, MyBuilder, Yell, etc. | No public API. Manual import: paste the review text, author and date, plus a link to the original | Shown as "via Checkatrade" with a link, so it can be checked |
| Reviews already in the sites' `app.py` (both Roland's and Ray G's) | One-off import, including photos, with `source = google` (all came from their Google Business Profiles) | Shown as "via Google" with a link to the business's Google profile. Replaced by API-synced copies once Phase 7 connects Google |

### Centralised on hapitech.dev, shown on their sites
- **hapitech.dev is the system of record.** Review links, the review form, moderation, replies and imports all live there: `hapitech.dev/r/<token>` for requests, plus a public page for each business, for example `hapitech.dev/reviews/rolands-handyman`.
- **Their sites show the reviews as their own content.** Both sites fetch `GET https://hapitech.dev/api/v1/sites/<slug>/reviews` (and `/posts`) on the server, with a per-site read key and a 10-minute cache, and render the reviews into the page HTML. They don't use a JavaScript widget or iframe, because search engines need the text in the HTML for it to count towards the site. If HapiTech is down, they show the last good copy.

### SEO and getting them more work (what helps, honestly)
- **Fresh, local text on their own domain** helps most of all: reviews that mention the job and the town ("fitted a bathroom in Swindon"), plus regular "Latest work" posts with town names. That only counts if it's in the HTML on rolandshandyman.co.uk and rayghandymanservice.co.uk themselves, which is why the sites render it server-side.
- **Google Business Profile reviews** carry the most weight for local "near me" searches. After a customer submits a review, the thank-you screen offers everyone (never just happy customers) a one-tap "Also post this on Google" link with their text ready to copy.
- **Duplicate content:** the same review text appears on hapitech.dev and on the client site. The client site is the copy search engines should index. The hapitech.dev business pages point to it with a canonical tag and add a "Verified by HapiTech" note.
- **Star ratings in Google results:** Google doesn't show review stars for a business's reviews of itself on its own site. Mark up only reviews collected first-hand through this system, and don't promise clients stars in search results.
- **Links:** the HapiTech case studies and business pages link to each client site (a small, real link boost), and each client site's footer links back to its HapiTech review page ("Read all reviews / Leave a review").
- **Measuring it:** monthly summary per client showing new reviews, average rating, review-link clicks, quote-form enquiries (counted when their site's form emails), and Google Search Console clicks once each site is verified.

---

## 6. Build phases

| # | Phase | Delivers | Size |
|---|---|---|---|
| 0 | **Safety and clear-out** | Back up the prod DB and `solar_journal.db`; remove Solar Journal and hapitech.report code (see section 1); create the `flask create-admin` command and remove the seeded password; fix the login code RNG; update the privacy policy | 1 day |
| 1 | **Foundation** | New models + Alembic migration; data migration from `webdev_clients`/`webdev_jobs`/`recurring_payments`/`clients`; tenancy helper; CSRF + rate limits; admin layout on `site.css`; local review accounts (section 9) | 2–3 days |
| 2 | **Login modal** | Modal, `/auth/login`, role routing, invite and set-password emails | 1 day |
| 3 | **Admin: clients and money** | Clients, jobs, subscriptions, payments, notes, site status | 2–3 days |
| 4 | **Admin: benchmarks** | Models, versioned prompts with fixtures, run upload → preview → publish, history import, public results page, AI News integration | 3 days |
| 5 | **Reviews core** | Review model, request links, public review form, business review pages on hapitech.dev, portal inbox and replies, manual import, import of both sites' existing reviews | 3 days |
| 6 | **Client portal, posts and site integration** | `/portal` home, posts with photo upload, client-site API, both client sites rendering reviews and posts server-side, Search Console set up | 3 days |
| 7 | **External sources** | Google Business Profile sync and replies; Facebook (once Meta approves) | 2–4 days + approval wait |
| 8 | **Polish** | Email templates, SMS provider (optional), TOTP for admin, monthly "your reviews and enquiries" summary email to clients | 2 days |

Each phase ships on its own: deploy it, check it on the live site, then move to the next.

**Testing:** pytest for models, the tenancy guard (a client can't read another account's data), the auth flows and the JSONL parser; a headless-browser check of the modal, portal and review form at phone size.

---

## 7. Add-on packaging and pricing

**"Reviews and Updates" add-on.** It includes the portal, review links and QR codes, the review inbox and replies, Google review sync, posts, and self-service content edits.

- **Hook (free trial):** turn it on for 30 days at no cost. Roland and Ray use **Job done → Ask for a review** on real jobs, then the dashboard shows "4 new reviews this month, now showing on your website". When the trial ends, the reviews they collected stay on their site. The portal and new requests pause until they subscribe.
- **What we're charging for:** the system, not the texts. Texts go from their own phone, so each extra job costs HapiTech nothing.
- **Suggested price:** a flat monthly fee on top of hosting, roughly in the £10–£20 a month range. That's well under one job's profit for a tradesperson. Aaron sets the actual figure, and the admin stores it per client as a `Subscription`.
- Without the add-on, a client still gets their existing site exactly as now. Reviews already imported stay visible, frozen at that point.

## 7a. Open questions for Aaron

1. The add-on's price and trial length (suggested above: a 30-day trial, then £10–£20 a month).
2. **Reviews newer than the ones on the sites:** I can't read Google reviews automatically without the owner's permission. Scraping Google is against its terms and breaks easily. The reliable route is Phase 7: Roland and Ray each click "Connect Google" once, and every review syncs, including any we've missed. Until then, they can send screenshots of newer ones to add by hand.

---

## 8. Deploying (Aaron runs this on the server)

The app runs as the systemd service `hapitech` from a git checkout under `/var/www`. After each phase is pushed to GitHub `main`, run this one line on the server:

```bash
cd "$(systemctl show -p WorkingDirectory --value hapitech | grep . || echo /var/www/hapitech.dev)" && git pull --ff-only && "$(ls -d .venv/bin/python venv/bin/python 2>/dev/null | head -1)" -m flask deploy && sudo systemctl restart hapitech && sleep 3 && curl -s -o /dev/null -w "hapitech.dev -> %{http_code}\n" https://hapitech.dev/
```

It changes to the service's folder, pulls (refusing to overwrite local edits), runs `flask deploy` (backs up the SQLite database to `instance/backups/`, then applies any migrations, safely stamping an old un-versioned database first), restarts, and prints `200` if the site is up. It's safe to run when nothing has changed.

**One-off after the first platform deploy** (from the same folder; `.venv` or `venv`, whichever exists):

```bash
.venv/bin/python -m flask setup-clients && .venv/bin/python -m flask import-site-reviews rolands-handyman /var/www/rolandshandyman.co.uk && .venv/bin/python -m flask import-site-reviews ray-g-handyman /var/www/rayghandymanservice.co.uk
```

Then, from your own machine, import the Lab data (models, prompts, results) the same way with `flask import-bench <folder>`, or upload result files through Admin → Benchmark runs.

---

## 9. Logins for reviewing the work

- **Locally (each phase):** the seed script creates three accounts with demo data: your admin, plus one owner each for Roland's and Ray G. It writes random passwords to `instance/dev-credentials.txt` (gitignored) and prints them once. Use the "Client login" pop-up at `http://127.0.0.1:5077` to check each portal.
- **On the server:** no passwords are kept in code or git. After the Phase 1 deploy, run `flask create-admin aaron@hapitech.dev` once; it asks for the password interactively. Roland and Ray get invite emails to set their own passwords when you're ready to hand over.
- Your existing production admin login keeps working until Phase 1 replaces the users table, and the migration carries it across.
