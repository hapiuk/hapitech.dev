# utils/review_search.py — the search + filter bar on the Reviews pages (client dashboard and admin).
from models import db
from models.reviews import Review, ReviewReply

OWN = ("hapitech", "website", "manual")
SORTS = {"new": "Newest first", "old": "Oldest first", "low": "Lowest rating", "high": "Highest rating"}


def apply(q, args):
    """Filter a Review query by ?q= (words, name or service), src, stars, replied and sort. Returns (query, active)."""
    text = (args.get("q") or "").strip()[:80]
    src, stars, replied, sort = args.get("src", ""), args.get("stars", ""), args.get("replied", ""), args.get("sort", "new")
    if text:
        like = f"%{text}%"
        q = q.filter(db.or_(Review.body.ilike(like), Review.author_name.ilike(like), Review.service.ilike(like),
                            Review.replies.any(ReviewReply.body.ilike(like))))
    if src in ("google", "facebook"):
        q = q.filter(Review.source == src)
    elif src == "hapitech":
        q = q.filter(Review.source.in_(OWN))
    if stars.isdigit() and 1 <= int(stars) <= 5:
        q = q.filter(Review.rating == int(stars))
    if replied == "yes":
        q = q.filter(Review.replies.any())
    elif replied == "no":
        q = q.filter(~Review.replies.any())
    order = {"old": (Review.reviewed_at.asc().nullslast(),), "low": (Review.rating.asc(), Review.reviewed_at.desc().nullslast()),
             "high": (Review.rating.desc(), Review.reviewed_at.desc().nullslast())}.get(sort, (Review.reviewed_at.desc().nullslast(), Review.sort_hint))
    active = bool(text or src or stars or replied or sort not in ("", "new"))
    return q.order_by(*order), active
