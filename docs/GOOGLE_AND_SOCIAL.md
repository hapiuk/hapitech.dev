# Google reviews and social posting: options

Written 23 Nov 2026. API rules and prices change, so re-check each one when we set it up.

## Google reviews

### Already live
- **"Leave a review" goes to their own review page**, then offers "Post it on Google" with the text ready to paste.
  The offer shows for **every** rating. Google bans "review gating", meaning only sending happy customers to Google. Keep it that way.
- **The Google review link** is stored per client. Clients can open it from the Ask page or the QR code.

### Options

| # | Option | What it gives us | What it needs | Cost | Effort |
|---|---|---|---|---|---|
| G1 | **Google Business Profile API**, connected by the client signing in with Google once | **All** their Google reviews pulled into the dashboard and onto their website (with "via Google"). **Reply to Google reviews from the dashboard.** New-review alerts. Also lets us **publish posts to their Google profile** (see S1). | A Google Cloud project, plus applying for Business Profile API access (a form; Google reviews it, typically a few days to weeks). Each client taps "Connect Google" and approves (OAuth). We store only a refresh token, encrypted. | Free | Medium. Best value |
| G2 | **Places API**, read-only | Rating, total review count, and up to 5 "most relevant" reviews. No replies, and not all reviews. | An API key with billing turned on | Pay per call, small if cached daily | Low |
| G3 | **Manual import** (what we did for Ray) | Real reviews copied in, marked "via Google" | Nothing | Free | Low, but it goes stale |
| G4 | **Review widget services** (Trustindex, Elfsight and similar) | A ready-made Google review widget | A third-party script on the client sites (changes their look, adds tracking) | Monthly | Low. Not recommended |

What Google does **not** allow, whatever the option:
- writing or posting reviews for customers
- paying or rewarding customers for reviews
- gating reviews by rating
- checking whether a particular customer actually left a Google review (the API gives the reviewer's display name only)

**Recommendation:** G1. Apply for API access now, because approval is the slow part. Use G2 meanwhile for a live "4.9★ from 37 Google reviews" badge.

## Posting to social media from the dashboard

### Already built (23 Nov)
- **Website posts pages:** posts appear on `/posts` and `/posts/<id>` on both sites, with share previews (title and photo) for Facebook, LinkedIn and WhatsApp.
- **"Share it" card:** after publishing, the client sees **Share with photos**, which opens the phone's own share menu with the photos attached. From there they can pick Instagram, Facebook, WhatsApp, Messenger and so on. The card also has Facebook, LinkedIn and WhatsApp links and a **Copy text** button.
- **No accounts needed:** this works today without connecting any accounts. It's still one tap per network, not automatic.

### Automatic posting options

| # | Network | How | What it needs | Notes |
|---|---|---|---|---|
| S1 | **Google Business Profile** | Business Profile API (same approval as G1) | Client connects Google once | **Biggest local-search win.** Posts show on their Google listing and in Maps. Do this first. |
| S2 | **Facebook Page** | Meta Graph API (`pages_manage_posts`) | A Meta app; client logs in with Facebook once and picks their Page. Meta **app review + business verification** before it works for accounts that aren't app testers. | We can start by adding Roland and Ray as app testers, which works without review. |
| S3 | **Instagram** | Instagram Graph API (content publishing) | Instagram **Business/Creator** account linked to their Facebook Page; same Meta app and review as S2 | Photo posts only (needs at least one photo). Their photos are already at public URLs, which the API requires. |
| S4 | **LinkedIn** | "Share on LinkedIn" (personal profile) is self-serve. Company Pages need the Community Management API (approval, harder). | Client signs in with LinkedIn | Low value for handymen. Skip unless asked. |
| S5 | **X / TikTok / Nextdoor** | Each has its own API and approval; X write access is paid | n/a | Not worth it for these clients |
| S6 | **Third-party posting service** (Ayrshare, Buffer and similar) | One API we call; the client connects their accounts inside that service | A monthly subscription per profile | Fastest route to "all networks", but it adds a paid dependency and another login for the client |

Planned flow once connected: a "Also post to: ☑ Google ☑ Facebook ☑ Instagram" row on the post form. We post in the
background and show ✓ or a "try again" next to each network. If a network fails, the website post is still fine.

**Recommendation:**
1. Google first (S1, with G1): one approval covers reviews and posts.
2. Then Facebook + Instagram (S2/S3) with Roland and Ray as app testers, so it works before Meta's review.
3. Apply for Meta review in parallel.
4. Skip the rest unless a client asks.

**What Aaron needs to do:**
1. Create a Google Cloud project and submit the Business Profile API access form.
2. Create a Meta developer app (Business type) and start business verification for HapiTech.
3. Check Roland and Ray have Business/Creator Instagram accounts linked to a Facebook Page.
