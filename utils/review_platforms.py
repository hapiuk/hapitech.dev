# utils/review_platforms.py — review sites HapiTech can bring reviews in from (all have public review pages),
# plus logos for the "find more work" shortcuts on Jobs. Logos live in static/img/platforms/<host>.png.
from urllib.parse import urlparse

# key, name, sign-up link, why, collected already (False = possible, set up on request as a paid add-on)
PLATFORMS = [
    ("google", "Google", "https://business.google.com/", "The most important one: Google reviews decide who shows up for \"near me\" searches.", True),
    ("facebook", "Facebook", "https://www.facebook.com/pages/create", "Recommendations show up to your customers' friends and neighbours.", True),
    ("trustpilot", "Trustpilot", "https://business.trustpilot.com/", "A badge lots of people recognise. Free to start.", False),
    ("checkatrade", "Checkatrade", "https://www.checkatrade.com/", "Vetted trades directory with verified reviews (paid membership).", False),
    ("yell", "Yell", "https://www.yell.com/", "Free UK business listing with reviews.", False),
    ("trustatrader", "TrustATrader", "https://www.trustatrader.com/", "Checked trades directory with reviews.", False),
]
LOGOS = {"google": "google.com", "facebook": "facebook.com", "trustpilot": "trustpilot.com", "checkatrade": "checkatrade.com",
         "yell": "yell.com", "trustatrader": "trustatrader.com", "bark": "bark.com", "taskrabbit": "taskrabbit.co.uk",
         "mybuilder": "mybuilder.com", "ratedpeople": "ratedpeople.com", "nextdoor": "nextdoor.co.uk"}


def logo_for(url):
    """Static path of a known site's logo for a link (or None): e.g. https://www.bark.com/… → img/platforms/bark.com.png."""
    host = (urlparse(url or "").hostname or "").lower()
    for word, file in LOGOS.items():
        if word in host.replace(".", "").replace("-", ""):
            return f"img/platforms/{file}.png"
    return None


def for_account(account):
    have = {"google": bool(account.google_maps_url or account.google_reviews_url or account.google_profile_url),
            "facebook": bool(account.facebook_url)}
    return [{"key": k, "name": n, "url": u, "why": w, "collect": c, "have": have.get(k, False),
             "logo": f"img/platforms/{LOGOS[k]}.png"} for k, n, u, w, c in PLATFORMS]
