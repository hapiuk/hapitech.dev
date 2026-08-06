"""
Computes normalized "scan meter" percentages from the real orbital data in
bodies.json — radius, orbital distance, day length, year length — for the
planetary-scan style readout in the info panel.

Percentages are for the visual bar only; the actual value (with units) is
always shown alongside it, so the bar is a nice-to-look-at comparison,
never the source of truth.
"""

import json
import os

_cache = None


def _load_raw(static_folder):
    global _cache
    if _cache is not None:
        return _cache

    path = os.path.join(static_folder, "solar-system", "data", "bodies.json")
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception:
        _cache = {}
        return _cache

    all_bodies = {}
    for b in data.get("bodies", []):
        if b.get("name"):
            all_bodies[b["name"]] = b
    for m in data.get("moons", []):
        if m.get("name"):
            all_bodies[m["name"]] = m

    _cache = all_bodies
    return _cache


# Reference maximums for scaling the bars — Jupiter/Neptune-ish, so the
# largest/furthest/longest known body in this dataset reads close to 100%.
DAY_LENGTH_REFERENCE_HOURS = 6000     # Venus-ish, longest rotation period here
YEAR_LENGTH_REFERENCE_DAYS = 60190    # Neptune's orbital period


KM_PER_AU = 149_597_870.7


def _get_distance_km(b: dict) -> float:
    if b.get("a_km"):
        return b["a_km"]
    if b.get("a_AU"):
        return b["a_AU"] * KM_PER_AU
    return 0


def get_body_stats(name: str, static_folder: str) -> dict:
    bodies = _load_raw(static_folder)

    if not bodies or name not in bodies:
        return None

    b = bodies[name]
    max_radius = max((v.get("radius", 0) or 0) for v in bodies.values()) or 1
    max_distance = max(_get_distance_km(v) for v in bodies.values()) or 1

    radius = b.get("radius", 0) or 0
    a_km = _get_distance_km(b)
    rot_hours = abs(b.get("rot_hours", 0) or 0)
    period_days = b.get("period_days", 0) or 0

    return {
        "size": {
            "pct": round(min(100, radius / max_radius * 100)),
            "value": f"{radius:g} (visual units)"
        },
        "distance": {
            "pct": round(min(100, a_km / max_distance * 100)),
            "value": f"{a_km:,.0f} km"
        },
        "day_length": {
            "pct": round(min(100, rot_hours / DAY_LENGTH_REFERENCE_HOURS * 100)),
            "value": f"{rot_hours:,.1f} hours"
        },
        "year_length": {
            "pct": round(min(100, period_days / YEAR_LENGTH_REFERENCE_DAYS * 100)),
            "value": f"{period_days:,.2f} days"
        }
    }