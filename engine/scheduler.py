"""Spaced repetition: SM-2, with the one change the video asks for.

The Ebbinghaus point is that each successful review both flattens the decay
curve and raises the floor, so intervals grow and a lapse does not send you
back to zero knowledge, only back to a short interval.

The change: a card can be born from a miss. `cards_from_misses()` turns what
you got wrong in an examiner or socratic session straight into due-today cards,
which is the mechanism that stops the same gap recurring.
"""

import datetime
import store

MIN_EASE = 1.3
START_EASE = 2.5

# Grade meanings, kept deliberately coarse. A learner grading themselves on six
# levels lies; on three they mostly do not.
GRADES = {
    "again": 0,   # did not recall it
    "hard": 3,    # recalled with real effort
    "good": 4,    # recalled
    "easy": 5,    # instant
}


def _date(s):
    return datetime.date.fromisoformat(s)


def new_card(module, question, answer, origin="", cid=None):
    return {
        "id": cid or "",
        "module": module,
        "q": question.strip(),
        "a": answer.strip(),
        "due": store.today(),
        "interval": 0,
        "ease": START_EASE,
        "reps": 0,
        "lapses": 0,
        "origin": origin,
        "created": store.today(),
        "last_grade": None,
    }


def _next_id(cards):
    n = 0
    for c in cards:
        if c.get("id", "").startswith("c"):
            try:
                n = max(n, int(c["id"][1:]))
            except ValueError:
                pass
    return "c%03d" % (n + 1)


def add_cards(slug, new):
    """`new` is a list of dicts from new_card(). Skips exact question dupes."""
    cards = store.read_cards(slug)
    existing = set(c["q"].strip().lower() for c in cards)
    added = []
    for c in new:
        if c["q"].strip().lower() in existing:
            continue
        c = dict(c)
        c["id"] = _next_id(cards)
        cards.append(c)
        existing.add(c["q"].strip().lower())
        added.append(c)
    store.write_cards(slug, cards)
    return added


def cards_from_misses(slug, module, misses, origin=""):
    """misses: list of {"q": ..., "a": ...} the learner got wrong."""
    return add_cards(slug, [
        new_card(module, m["q"], m["a"], origin=origin or "miss")
        for m in misses if m.get("q") and m.get("a")
    ])


def due(slug, on=None):
    on = _date(on or store.today())
    return [c for c in store.read_cards(slug) if _date(c["due"]) <= on]


def due_counts():
    """Across every topic, for the dashboard."""
    out = {}
    for slug in store.topic_slugs():
        out[slug] = len(due(slug))
    return out


def grade(slug, card_id, grade_name):
    """Apply one review. Returns the updated card."""
    if grade_name not in GRADES:
        raise SystemExit("grade must be one of: %s" % ", ".join(GRADES))
    q = GRADES[grade_name]
    cards = store.read_cards(slug)
    for c in cards:
        if c["id"] != card_id:
            continue
        if q < 3:
            # Lapse: short interval, ease down, but reps and history survive.
            c["lapses"] += 1
            c["interval"] = 1
            c["ease"] = max(MIN_EASE, c["ease"] - 0.20)
        else:
            if c["reps"] == 0:
                c["interval"] = 1
            elif c["reps"] == 1:
                c["interval"] = 6
            else:
                c["interval"] = int(round(c["interval"] * c["ease"]))
            c["reps"] += 1
            c["ease"] = max(
                MIN_EASE,
                c["ease"] + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)),
            )
        c["due"] = (datetime.date.today() + datetime.timedelta(days=c["interval"])).isoformat()
        c["last_grade"] = grade_name
        c["last_review"] = store.today()
        store.write_cards(slug, cards)
        return c
    raise SystemExit("no card %r in %s" % (card_id, slug))


def retention(slug):
    """Crude but honest: share of reviewed cards whose last grade was a pass."""
    cards = [c for c in store.read_cards(slug) if c.get("last_grade")]
    if not cards:
        return None
    passed = sum(1 for c in cards if GRADES[c["last_grade"]] >= 3)
    return round(100.0 * passed / len(cards))
