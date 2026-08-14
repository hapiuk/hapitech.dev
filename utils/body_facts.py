"""
Curated body-type + fun facts for the Solar System info panel.
Deliberately hand-curated rather than scraped — accurate, static,
well-established facts. No live fetching, no external dependency.
"""

BODY_FACTS = {
    "Mercury": {
        "type": "Rocky planet",
        "facts": [
            "A year on Mercury (88 Earth days) is shorter than its day (176 Earth days) — the Sun rises very slowly.",
            "Despite being closest to the Sun, it's not the hottest planet — Venus is, because of its thick atmosphere.",
            "Has almost no atmosphere, so its surface temperature swings by hundreds of degrees between day and night."
        ]
    },
    "Venus": {
        "type": "Rocky planet",
        "facts": [
            "The hottest planet in the solar system, thanks to a runaway greenhouse effect from its thick CO2 atmosphere.",
            "Spins backwards compared to most planets — the Sun rises in the west.",
            "A day on Venus (243 Earth days) is longer than its year (225 Earth days)."
        ]
    },
    "Earth": {
        "type": "Rocky planet",
        "facts": [
            "The only known planet with liquid water on its surface and confirmed life.",
            "Its axial tilt (23.4°) is what gives us seasons.",
            "The Moon's gravity stabilizes Earth's tilt, helping keep the climate relatively steady over long timescales."
        ]
    },
    "Mars": {
        "type": "Rocky planet",
        "facts": [
            "Home to Olympus Mons, the largest volcano in the solar system — about 2.5 times the height of Mt. Everest.",
            "Has seasons similar to Earth's, since its axial tilt is nearly the same (25.2°).",
            "Its reddish colour comes from iron oxide (rust) covering much of its surface."
        ]
    },
    "Jupiter": {
        "type": "Gas giant",
        "facts": [
            "The largest planet in the solar system — over 1,300 Earths could fit inside it by volume.",
            "The Great Red Spot is a storm that's been raging for at least 150 years, and possibly much longer.",
            "Has the shortest day of any planet, rotating fully in under 10 hours."
        ]
    },
    "Saturn": {
        "type": "Gas giant",
        "facts": [
            "Its rings are made almost entirely of ice particles, with a small amount of rocky debris.",
            "Less dense than water — if you had a bathtub big enough, Saturn would float.",
            "Has 146 known moons, more than any other planet in the solar system."
        ]
    },
    "Uranus": {
        "type": "Ice giant",
        "facts": [
            "Rotates on its side — its axial tilt is about 98°, so its poles point almost directly at the Sun during its seasons.",
            "The coldest planetary atmosphere in the solar system, despite not being the furthest from the Sun.",
            "Its blue-green colour comes from methane in its atmosphere absorbing red light."
        ]
    },
    "Neptune": {
        "type": "Ice giant",
        "facts": [
            "Has the strongest winds in the solar system, reaching up to 2,100 km/h (1,300 mph).",
            "Takes about 165 Earth years to orbit the Sun once — it's completed just over one orbit since its discovery in 1846.",
            "Was the first planet located by mathematical prediction rather than direct observation."
        ]
    },
    "Moon": {
        "type": "Natural satellite (of Earth)",
        "facts": [
            "Slowly drifting away from Earth at about 3.8cm per year.",
            "Always shows the same face to Earth because its rotation is tidally locked to its orbit.",
            "Responsible for most of Earth's tides, alongside a smaller contribution from the Sun."
        ]
    }
}

GENERAL_FACTS = {
    "type": "General",
    "facts": [
        "Select a planet or moon to see facts and community entries specific to it."
    ]
}


def get_body_facts(name: str) -> dict:
    return BODY_FACTS.get(name, {
        "type": "Moon",
        "facts": [f"No curated facts for {name} yet — check back soon."]
    }) if name and name != "General" else GENERAL_FACTS