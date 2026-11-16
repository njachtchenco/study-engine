#!/usr/bin/env python3
"""Front door for the skills. Everything that writes state goes through here.

Run `python3 engine/study.py <command> --help` for any one command.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store      # noqa: E402
import scheduler  # noqa: E402


def out(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _load_json_arg(value):
    """Accept inline JSON, a path, or - for stdin."""
    if value == "-":
        return json.loads(sys.stdin.read())
    if os.path.isfile(value):
        with open(value, encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(value)


# ------------------------------------------------------------------ topics

def cmd_new(a):
    slug = store.create_topic(a.title, strictness=a.strictness)
    t = store.read_topic(slug)
    t["struggle_minutes"] = a.struggle_minutes
    store.write_topic(slug, t)
    out({"created": slug, "dir": store.topic_dir(slug), "topic": t})


def cmd_topics(a):
    rows = []
    for slug in store.topic_slugs():
        t = store.read_topic(slug)
        mods = store.read_modules(slug)
        rows.append({
            "slug": slug,
            "title": t["title"],
            "strictness": t.get("strictness"),
            "interviewed": t.get("interviewed"),
            "mapped": t.get("mapped"),
            "modules": len(mods),
            "unaided_pass": sum(1 for m in mods.values() if m["status"] == "unaided_pass"),
            "redo_owed": sum(1 for m in mods.values() if m["status"] in ("explained", "redo_due")),
            "cards": len(store.read_cards(slug)),
            "due": len(scheduler.due(slug)),
        })
    out(rows)


def cmd_show(a):
    out({
        "topic": store.read_topic(a.topic),
        "modules": store.read_modules(a.topic),
        "cards": len(store.read_cards(a.topic)),
        "due": len(scheduler.due(a.topic)),
        "retention": scheduler.retention(a.topic),
        "sessions": len(store.read_sessions(a.topic)),
    })


def cmd_set_profile(a):
    t = store.read_topic(a.topic)
    for field in ("goal", "level", "exam_format", "deadline"):
        v = getattr(a, field)
        if v is not None:
            t[field] = v
    if a.struggle_minutes is not None:
        t["struggle_minutes"] = a.struggle_minutes
    if a.strictness is not None:
        t["strictness"] = a.strictness
    t["interviewed"] = True
    store.write_topic(a.topic, t)
    out(t)


# ----------------------------------------------------------------- modules

def cmd_add_module(a):
    m = store.set_module(a.topic, a.id, title=a.title,
                         depends_on=[s for s in (a.depends_on or "").split(",") if s],
                         notes=a.notes or "")
    t = store.read_topic(a.topic)
    t["mapped"] = True
    store.write_topic(a.topic, t)
    out(m)


def cmd_set_module(a):
    fields = {}
    if a.status:
        fields["status"] = a.status
    if a.score is not None:
        fields["last_score"] = a.score
    if a.notes is not None:
        fields["notes"] = a.notes
    if not fields:
        raise SystemExit("nothing to set")
    out(store.set_module(a.topic, a.module, **fields))


def cmd_modules(a):
    out(store.read_modules(a.topic))


# ------------------------------------------------------------------- cards

def cmd_add_cards(a):
    data = _load_json_arg(a.cards)
    cards = [scheduler.new_card(c.get("module", a.module or ""), c["q"], c["a"],
                                origin=a.origin) for c in data]
    added = scheduler.add_cards(a.topic, cards)
    out({"added": len(added), "skipped_duplicates": len(cards) - len(added),
         "ids": [c["id"] for c in added]})


def cmd_due(a):
    if a.topic and a.text:
        # One header line, then "id | question | answer" per due card. The
        # header tells an empty deck (nothing studied yet) from a deck with
        # nothing due today, which /review answers differently.
        store.read_topic(a.topic)
        deck = store.read_cards(a.topic)
        cards = scheduler.due(a.topic)
        line = "%s: %d due, %d card%s in the deck" % (
            a.topic, len(cards), len(deck), "" if len(deck) == 1 else "s")
        later = sorted(c["due"] for c in deck if c not in cards)
        if not cards and later:
            line += ", next due %s" % later[0]
        print(line)
        for c in cards:
            print("%s | %s | %s" % (c["id"], c["q"], c["a"]))
    elif a.topic:
        cards = scheduler.due(a.topic)
        out({"topic": a.topic, "due": len(cards), "cards": cards})
    else:
        out(scheduler.due_counts())


def cmd_grade(a):
    out(scheduler.grade(a.topic, a.card, a.grade))


def cmd_misses_to_cards(a):
    misses = _load_json_arg(a.misses)
    added = scheduler.cards_from_misses(a.topic, a.module, misses, origin=a.origin)
    out({"added": len(added), "ids": [c["id"] for c in added]})


# ---------------------------------------------------------------- sessions

def cmd_log(a):
    if a.body_file == "-":
        body = sys.stdin.read()
    elif os.path.isfile(a.body_file):
        with open(a.body_file, encoding="utf-8") as fh:
            body = fh.read()
    else:
        body = a.body_file
    misses = _load_json_arg(a.misses) if a.misses else []
    path = store.log_session(a.topic, a.role, body, module=a.module,
                             score=a.score, misses=misses)
    out({"logged": os.path.relpath(path, store.ROOT)})


def cmd_sessions(a):
    rows = store.read_sessions(a.topic, role=a.role, module=a.module, limit=a.limit)
    if not a.full:
        for r in rows:
            r.pop("body", None)
    out(rows)


# ---------------------------------------------------------------- diagnose

# Under this many sessions a topic's history is thin: /diagnose still runs,
# but says the root it finds rests on little evidence.
THIN_CORPUS = 20


def topic_corpus(slug, limit=None):
    """Everything /diagnose reasons from, for one topic, in one read.

    Sessions with something to diagnose (misses, a gap section, a score below
    1) are listed newest first with the file name to cite, each with what
    held up in it too. Sessions where nothing went wrong but something is
    recorded as held are `held_only`: the counter-evidence. Cards that have
    lapsed or were last graded again/hard are the review-side evidence.
    Reads only; writes nothing.
    """
    t = store.read_topic(slug)
    sessions = store.read_sessions(slug, limit=limit)
    signal, held_only = [], []
    for s in sessions:
        body = s.get("body", "")
        gaps = store.gap_sections(body)
        held = store.held_sections(body)
        score = s.get("score")
        row = {"file": s["file"], "at": s["at"], "role": s["role"],
               "module": s.get("module"), "score": score}
        if s.get("misses") or gaps or (score is not None and score < 1):
            row.update(misses=s.get("misses") or [], gaps=gaps, held=held)
            signal.append(row)
        elif held:
            row["held"] = held
            held_only.append(row)
    weak = []
    for c in store.read_cards(slug):
        if c.get("lapses", 0) > 0 or c.get("last_grade") in ("again", "hard"):
            weak.append({k: c.get(k) for k in (
                "id", "module", "q", "a", "lapses", "last_grade",
                "last_review", "origin", "created")})
    weak.sort(key=lambda c: (-(c["lapses"] or 0), c["id"]))
    total = len(store.read_sessions(slug))
    return {
        "topic": slug,
        "title": t.get("title", slug),
        "exam_format": t.get("exam_format", ""),
        "sessions_total": total,
        "sessions_read": len(sessions),
        "sessions_with_signal": len(signal),
        "thin": total < THIN_CORPUS,
        "modules": {mid: m.get("title", mid)
                    for mid, m in sorted(store.read_modules(slug).items())},
        "sessions": signal,
        "held_only": held_only,
        "weak_cards": weak,
    }


HELD_CLIP = 120


def _clip(text, n):
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " ..."


def corpus_text(c):
    """The corpus as plain lines, oldest first, for reading a history in
    order. x = went wrong, + = held, ? = a recorded miss (question -> answer)."""
    lines = ["%s: %s. %d sessions, %d with misses or gaps, %d weak cards.%s" % (
        c["topic"], c["title"], c["sessions_total"], c["sessions_with_signal"],
        len(c["weak_cards"]), " THIN (under %d sessions)." % THIN_CORPUS if c["thin"] else "")]
    if c["exam_format"]:
        lines.append("Test format: " + c["exam_format"])
    lines.append("Modules: " + "; ".join("%s %s" % kv for kv in c["modules"].items()))
    rows = sorted(c["sessions"] + c["held_only"], key=lambda r: (r["at"], r["file"]))
    for r in rows:
        lines.append("")
        lines.append("%s  [%s%s%s]" % (
            r["file"], r["role"], " " + r["module"] if r["module"] else "",
            "" if r["score"] is None else " score %g" % r["score"]))
        for heading, items in (r.get("gaps") or {}).items():
            for item in items:
                lines.append("  x %s: %s" % (heading, item))
        # What held is counter-evidence to find, not to quote: a short line
        # points at the session, and the file has the rest.
        for heading, items in (r.get("held") or {}).items():
            for item in items:
                lines.append("  + %s: %s" % (heading, _clip(item, HELD_CLIP)))
        for m in r.get("misses") or []:
            lines.append("  ? %s -> %s" % (m.get("q", ""), m.get("a", "")))
    if c["weak_cards"]:
        lines.append("")
        lines.append("Weak cards, most lapses first:")
        for w in c["weak_cards"]:
            lines.append("%s [%s] lapses %s, last %s %s: %s -> %s" % (
                w["id"], w["module"], w["lapses"], w["last_grade"],
                w["last_review"] or "", w["q"], w["a"]))
    return "\n".join(lines)


def cmd_corpus(a):
    slugs = [a.topic] if a.topic else store.topic_slugs()
    corpora = [topic_corpus(slug, limit=a.limit) for slug in slugs]
    if a.text:
        print("\n\n".join(corpus_text(c) for c in corpora))
    else:
        out(corpora[0] if a.topic else corpora)


def cmd_clock(a):
    """How long a timed /spar has run. Exit 1 once the limit is reached.

    Read-only: the start is the `date +%s` the skill took when the clock
    started, so there is no state to write and nothing to forget to clear.
    """
    now = int(a.now) if a.now is not None else int(time.time())
    limit = int(round(a.minutes * 60))
    elapsed = now - int(a.start)
    if elapsed < 0 or limit <= 0:
        raise SystemExit("clock: start is in the future or the limit is not positive")
    over = elapsed >= limit

    def mmss(sec):
        return "%d:%02d" % (sec // 60, sec % 60)

    out({"elapsed": elapsed, "limit": limit, "left": max(limit - elapsed, 0),
         "over": over,
         "say": ("TIME. %s of %s, over by %s" % (mmss(elapsed), mmss(limit), mmss(elapsed - limit))
                 if over else "%s left of %s" % (mmss(limit - elapsed), mmss(limit)))})
    if over:
        sys.exit(1)


# -------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("new", help="create a topic")
    s.add_argument("title")
    s.add_argument("--strictness", choices=["enforced", "advisory"], default="enforced")
    s.add_argument("--struggle-minutes", type=int, default=10)
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("topics", help="list every topic with its progress")
    s.set_defaults(fn=cmd_topics)

    s = sub.add_parser("show", help="everything about one topic")
    s.add_argument("topic")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("set-profile", help="record what the interviewer learned")
    s.add_argument("topic")
    s.add_argument("--goal")
    s.add_argument("--level")
    s.add_argument("--exam-format", dest="exam_format")
    s.add_argument("--deadline")
    s.add_argument("--struggle-minutes", type=int)
    s.add_argument("--strictness", choices=["enforced", "advisory"])
    s.set_defaults(fn=cmd_set_profile)

    s = sub.add_parser("add-module", help="one module of the curriculum")
    s.add_argument("topic")
    s.add_argument("id")
    s.add_argument("--title", required=True)
    s.add_argument("--depends-on", dest="depends_on", help="comma-separated module ids")
    s.add_argument("--notes", help="where people usually get stuck")
    s.set_defaults(fn=cmd_add_module)

    s = sub.add_parser("set-module")
    s.add_argument("topic")
    s.add_argument("module")
    s.add_argument("--status", choices=list(store.STATUSES))
    s.add_argument("--score", type=float)
    s.add_argument("--notes")
    s.set_defaults(fn=cmd_set_module)

    s = sub.add_parser("modules")
    s.add_argument("topic")
    s.set_defaults(fn=cmd_modules)

    s = sub.add_parser("add-cards", help='JSON list of {"module","q","a"}')
    s.add_argument("topic")
    s.add_argument("cards", help="inline JSON, a file path, or -")
    s.add_argument("--module")
    s.add_argument("--origin", default="clerk")
    s.set_defaults(fn=cmd_add_cards)

    s = sub.add_parser("misses-to-cards", help="turn what you got wrong into due cards")
    s.add_argument("topic")
    s.add_argument("module")
    s.add_argument("misses", help='JSON list of {"q","a"}, a file, or -')
    s.add_argument("--origin", default="miss")
    s.set_defaults(fn=cmd_misses_to_cards)

    s = sub.add_parser("due", help="what is due now")
    s.add_argument("topic", nargs="?")
    s.add_argument("--text", action="store_true",
                   help="with a topic: a count line, then 'id | question | answer' per due card")
    s.set_defaults(fn=cmd_due)

    s = sub.add_parser("grade")
    s.add_argument("topic")
    s.add_argument("card")
    s.add_argument("grade", choices=list(scheduler.GRADES))
    s.set_defaults(fn=cmd_grade)

    s = sub.add_parser("log", help="write a session file")
    s.add_argument("topic")
    s.add_argument("--role", required=True, choices=list(store.ROLES))
    s.add_argument("--module")
    s.add_argument("--score", type=float)
    s.add_argument("--misses", help='JSON list of {"q","a"}, a file, or -')
    s.add_argument("--body-file", required=True, help="path, inline text, or -")
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("sessions")
    s.add_argument("topic")
    s.add_argument("--role", choices=list(store.ROLES))
    s.add_argument("--module")
    s.add_argument("--limit", type=int)
    s.add_argument("--full", action="store_true", help="include session bodies")
    s.set_defaults(fn=cmd_sessions)

    s = sub.add_parser("corpus", help="every miss, gap and weak card, for /diagnose (read-only)")
    s.add_argument("topic", nargs="?", help="one topic; every topic if left out")
    s.add_argument("--limit", type=int, help="read only the newest N sessions per topic")
    s.add_argument("--text", action="store_true",
                   help="plain lines, oldest first, instead of JSON")
    s.set_defaults(fn=cmd_corpus)

    s = sub.add_parser("clock", help="time left in a timed /spar; exit 1 at the limit (read-only)")
    s.add_argument("--start", type=int, required=True, help="epoch seconds, from `date +%%s`")
    s.add_argument("--minutes", type=float, required=True)
    s.add_argument("--now", type=int, help=argparse.SUPPRESS)  # tests pin the edge with it
    s.set_defaults(fn=cmd_clock)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
