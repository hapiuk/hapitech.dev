# utils/review_platforms.py — where else a local trade can collect reviews (shown on the client's Reviews page).
# "collect": HapiTech can already bring those reviews in. Links go to each site's front page (sign-up lives there).
PLATFORMS = [
    ("google", "Google", "https://business.google.com/", "The most important one: Google reviews decide who shows up for \"near me\" searches.", True),
    ("facebook", "Facebook", "https://www.facebook.com/pages/create", "Recommendations show up to your customers' friends and neighbours.", True),
    ("trustpilot", "Trustpilot", "https://business.trustpilot.com/", "A badge lots of people recognise. Free to start.", False),
    ("checkatrade", "Checkatrade", "https://www.checkatrade.com/", "Vetted trades directory with verified reviews (paid membership).", False),
    ("yell", "Yell", "https://www.yell.com/", "Free UK business listing with reviews.", False),
    ("nextdoor", "Nextdoor", "https://business.nextdoor.com/", "Neighbours recommending local tradespeople. Free business page.", False),
    ("mybuilder", "MyBuilder", "https://www.mybuilder.com/", "Job leads plus customer feedback on every job.", False),
    ("bark", "Bark", "https://www.bark.com/", "Job leads with a reviews profile.", False),
    ("trustatrader", "TrustATrader", "https://www.trustatrader.com/", "Checked trades directory with reviews.", False),
    ("ratedpeople", "Rated People", "https://www.ratedpeople.com/", "Job leads plus ratings from customers.", False),
]


def for_account(account):
    have = {"google": bool(account.google_maps_url or account.google_reviews_url or account.google_profile_url),
            "facebook": bool(account.facebook_url)}
    return [{"key": k, "name": n, "url": u, "why": w, "collect": c, "have": have.get(k, False)} for k, n, u, w, c in PLATFORMS]
