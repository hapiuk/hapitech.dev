# utils/site_blocks.py — which parts of each client site the client can edit themselves.
# Keys must match the block('key', 'default') calls in that site's templates/home.html, and each
# default must match the text in the template, so an unedited block renders exactly as before.

ROLANDS = [
    ("furniture", "Furniture Assembly",
     "Professional flat-pack assembly you can trust. All work is completed personally by Rolands — no subcontractors, no shortcuts."),
    ("wall", "Wall Mounting Service",
     "Secure, precise wall mounting — done properly by Rolands using the correct fixings for your wall type."),
    ("electrical", "Minor Electrical Work",
     "Safe, careful minor electrical work completed professionally by Rolands. Work is limited to non-complex electrical tasks only."),
    ("plumbing", "Minor Plumbing Work",
     "Reliable minor plumbing work — completed carefully by Rolands. Small, non-complex tasks handled with attention to detail and cleanliness."),
]

RAYG = [
    ("bathrooms", "Bathrooms", "Complete bathroom installations, renovations and repairs."),
    ("kitchens", "Kitchens", "Kitchen fitting and refurbishment."),
    ("carpentry", "Carpentry", "Doors, flooring, skirting, shelving and bespoke woodwork."),
    ("lofts", "Loft Conversions", "Turning unused loft space into practical living areas."),
    ("extensions", "Extensions", "Professional home extensions built to last."),
    ("paving", "Paving & Landscaping", "Patios, paths, driveways and outdoor improvements."),
]


def definitions_for(account, site_dir=None):
    out = []
    if account.domain == "rolandshandyman.co.uk":
        for i, (key, title, intro) in enumerate(ROLANDS):
            out.append(dict(key=f"services.{key}.title", type="text", label=f"{title}: heading", group="Services",
                            default=title, max_length=40, sort=i * 2))
            out.append(dict(key=f"services.{key}.intro", type="longtext", label=f"{title}: intro", group="Services",
                            default=intro, max_length=260, sort=i * 2 + 1,
                            help="The short paragraph under the heading."))
    elif account.domain == "rayghandymanservice.co.uk":
        for i, (key, title, text) in enumerate(RAYG):
            out.append(dict(key=f"services.{key}.title", type="text", label=f"{title}: name", group="Services",
                            default=title, max_length=32, sort=i * 2))
            out.append(dict(key=f"services.{key}.text", type="longtext", label=f"{title}: description",
                            group="Services", default=text, max_length=110, sort=i * 2 + 1,
                            help="One short sentence. It sits on a small card."))
    return out
