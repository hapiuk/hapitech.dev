# utils/extras.py — paid extras a client can ask for (Aaron switches them on). Each is an AddOn row with kind=<key>:
#   requested -> active (Aaron switched it on) | paused. The extras themselves are separate projects.
EXTRAS = [
    {"key": "ai_chat", "icon": "🤖", "name": "AI chat assistant",
     "line": "A friendly chat on your website that answers customers' questions day and night (prices, areas, availability) "
             "using information you give it, and passes enquiries straight to your Jobs.",
     "price": "Monthly add-on · coming soon"},
]


def status(account, key):
    ad = account.addon(key)
    return ad.status if ad else None
