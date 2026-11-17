#!/usr/bin/env python3
"""Emit view/dashboard.html: one self-contained file, no external references.

It is a read-only window onto topics/. Nothing here writes state, so it can be
rebuilt at any time and deleted without loss. The page leads with what a chat
window cannot show at a glance: the streak, what to do next, and where you are
in each subject.

Every number on it is computed from topics/. The streak counts days with at
least one session that produced something (an explanation alone does not
count). Spark, the mascot, only ever says something true about that state.

The news is optional. With engine/news.py present the page gets a News tab and
--news / --news-if-stale fetch it; without the module (the public kit) there is
no tab and both flags do nothing.

--demo renders the made-up topic in examples/demo to view/demo.html instead,
dated as if today were the day after its last session, so someone can see the
page before they have studied anything.

The look (16 Nov 2026): a study desk. Warm greys with one amber accent, a
sidebar that becomes a top bar on a phone, the next step drawn as a real index
card (the one bright thing on the overview), and the chapter map as the only
place several colours mean something. Slash commands are set as small mono
chips, because every action here happens in Claude Code.

Restyle method: unslop by Damir Sokolovsky (@heydamir), CC BY 4.0,
https://github.com/heydamir/unslop
"""

import argparse
import base64
import datetime
import html
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import store      # noqa: E402
import scheduler  # noqa: E402
try:
    import news   # optional; the public kit ships without it
except ImportError:
    news = None

OUT = os.path.join(store.ROOT, "view", "dashboard.html")
DEMO_ROOT = os.path.join(os.path.dirname(HERE), "examples", "demo")
FONT = os.path.join(HERE, "fonts", "Figtree-latin.woff2")

STATUS_LABEL = {
    "untouched": "Not started",
    "attempting": "In progress",
    "explained": "Redo owed",
    "redo_due": "Redo owed",
    "unaided_pass": "Passed unaided",
}
OWED = ("explained", "redo_due")
UNAIDED_ROLES = ("socratic", "examine")
MILESTONES = (3, 7, 14, 30, 50, 100, 150, 200, 365)
WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen", "twenty"]


def esc(x):
    return html.escape(str(x if x is not None else ""))


def word(n):
    return WORDS[n] if 0 <= n < len(WORDS) else str(n)


def plural(n, one, many=None):
    return "%d %s" % (n, one if n == 1 else (many or one + "s"))


def day(iso):
    return datetime.date.fromisoformat(iso[:10])


def short_title(title):
    """The title without a trailing "(Ch 14)" style reference."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", title or "").strip() or (title or "")


def node_label(title, index):
    """What fits inside a map node: "Ch 12.1" when the title names a chapter,
    otherwise the module's place in the curriculum. Never the module ID."""
    ref = re.search(r"\(([^)]*)\)\s*$", title or "")
    m = ref and re.match(r"\s*Ch\.?\s*(\d+(?:\.\d+)?)(?:\s+([IVX]+)\b)?", ref.group(1))
    if m:
        return "Ch %s%s" % (m.group(1), " " + m.group(2) if m.group(2) else "")
    return "Part %d" % index


# --------------------------------------------------------------------------
# Collect: everything the page shows, computed from topics/.

def depths(mods):
    memo = {}

    def d(k, seen=()):
        if k not in memo:
            ps = [p for p in mods[k]["depends_on"] if p in mods and p not in seen]
            memo[k] = 0 if not ps else 1 + max(d(p, seen + (k,)) for p in ps)
        return memo[k]
    return {k: d(k) for k in mods}


def reduced_edges(mods):
    """Dependencies minus the ones another path already implies, so a final
    module that depends on everything draws one line, not nine."""
    anc = {}

    def ancestors(k, seen=()):
        if k not in anc:
            out = set()
            for p in mods[k]["depends_on"]:
                if p in mods and p not in seen:
                    out.add(p)
                    out |= ancestors(p, seen + (k,))
            anc[k] = out
        return anc[k]
    edges = []
    for k in sorted(mods):
        ps = [p for p in mods[k]["depends_on"] if p in mods]
        for p in ps:
            if not any(p in ancestors(q) for q in ps if q != p):
                edges.append((p, k))
    return edges


def map_layout(mods, depth, edges):
    """Rows by dependency depth, each row centred, ordered by where its
    parents sit so lines cross as little as possible."""
    S, P, ROW, TOP = 62, 66, 102, 20
    rows = {}
    for k in sorted(mods):
        rows.setdefault(depth[k], []).append(k)
    parents = {k: [a for a, b in edges if b == k] for k in mods}
    widest = max(len(r) for r in rows.values()) if rows else 0
    W = max(326, (widest - 1) * P + S)
    pos = {}
    for d in sorted(rows):
        row = rows[d]
        if d:
            row.sort(key=lambda k: (sum(pos[p][0] for p in parents[k]) / len(parents[k])
                                    if parents[k] else W / 2, k))
        total = (len(row) - 1) * P + S
        x0 = (W - total) / 2.0
        for i, k in enumerate(row):
            pos[k] = (x0 + i * P, TOP + d * ROW)
    H = TOP + (max(rows) if rows else 0) * ROW + S + 30
    return {"pos": pos, "W": int(W), "H": int(H), "S": S}


def current_module(mods, sessions):
    """The module of the newest session, else the first not passed. news.py's
    class_prompt uses the same rule; change both together."""
    for s in sessions:
        if s.get("module") in mods and s.get("role") not in store.LOOKBACK_ROLES:
            return s["module"]
    return next((k for k in sorted(mods) if mods[k]["status"] != "unaided_pass"), None)


def path_chain(mods, depth, current):
    """Where you are, as a short path: up to two modules it builds on, then
    what it unlocks, four at most."""
    if current is None:
        return []
    children = {k: [c for c in mods if k in mods[c]["depends_on"]] for k in mods}
    anc, k = [], current
    while len(anc) < 2:
        ps = [p for p in mods[k]["depends_on"] if p in mods and p not in anc]
        if not ps:
            break
        k = max(ps, key=lambda p: (depth[p], mods[p].get("attempts") or 0, p))
        anc.insert(0, k)
    seq, k = anc + [current], current
    while len(seq) < 4:
        cs = sorted((c for c in children[k] if c not in seq), key=lambda c: (depth[c], c))
        if not cs:
            break
        k = cs[0]
        seq.append(k)
    return seq


def collect(today):
    t_iso = today.isoformat()
    tomorrow = (today + datetime.timedelta(days=1)).isoformat()
    topics, prod_days, all_sessions = [], set(), []
    for slug in store.topic_slugs():
        t = store.read_topic(slug)
        mods = store.read_modules(slug)
        cards = store.read_cards(slug)
        sessions = sorted(store.read_sessions(slug), key=lambda s: s["at"], reverse=True)
        for s in sessions:
            all_sessions.append(dict(s, topic=t["title"]))
            if s["role"] != "explain":
                prod_days.add(s["at"][:10])
        order = sorted(mods)
        index = {k: i + 1 for i, k in enumerate(order)}
        labels = {k: node_label(mods[k]["title"], index[k]) for k in mods}
        depth = depths(mods)
        edges = reduced_edges(mods)
        current = current_module(mods, sessions)
        topics.append({
            "slug": slug,
            "title": t["title"],
            "demo": bool(t.get("demo")),
            "mods": mods,
            "order": order,
            "labels": labels,
            "depth": depth,
            "edges": edges,
            "layout": map_layout(mods, depth, edges) if mods else None,
            "current": current,
            "chain": path_chain(mods, depth, current),
            "started": sum(1 for m in mods.values() if m["status"] != "untouched"),
            "owed": [k for k in order if mods[k]["status"] in OWED],
            "cards": len(cards),
            "due": sum(1 for c in cards if c["due"] <= t_iso),
            "overdue": sum(1 for c in cards if c["due"] < t_iso),
            "tomorrow": sum(1 for c in cards if c["due"] == tomorrow),
            "reviewed_today": sum(1 for c in cards if c.get("last_review") == t_iso),
            "level": (int(round(sum(100 * math.sqrt(max(c.get("interval") or 0, 0) / 100.0)
                                    for c in cards) / len(cards))) if cards else None),
            "overrides": sum(1 for s in sessions if s.get("override")),
            "sessions": sessions,
            "passed_today": [k for k in order if (mods[k].get("unaided_pass_at") or "")[:10] == t_iso],
        })
    return {"today": today, "topics": topics, "prod_days": prod_days,
            "sessions": sorted(all_sessions, key=lambda s: s["at"], reverse=True)}


def streaks(prod_days, today):
    days = sorted(day(d) for d in prod_days)
    best, run, prev = 0, 0, None
    for d in days:
        run = run + 1 if prev and (d - prev).days == 1 else 1
        best = max(best, run)
        prev = d
    studied_today = today.isoformat() in prod_days
    d = today if studied_today else today - datetime.timedelta(days=1)
    current = 0
    while d.isoformat() in prod_days:
        current += 1
        d -= datetime.timedelta(days=1)
    return current, best, studied_today


def week(prod_days, today):
    """Monday to Sunday of this week, one key per day."""
    first = min((day(d) for d in prod_days), default=today)
    monday = today - datetime.timedelta(days=today.weekday())
    out = []
    for i in range(7):
        d = monday + datetime.timedelta(days=i)
        iso = d.isoformat()
        if iso in prod_days:
            state = "done"
        elif d == today:
            state = "today"
        elif d > today or d < first:
            state = "blank"
        else:
            state = "miss"
        out.append({"letter": "MTWTFSS"[i], "state": state, "date": d})
    return out


def spark_state(c):
    """Spark's mood and line. Celebration is kept for real milestones so it
    still means something on the hundredth visit; nothing guilt-trips."""
    today = c["today"]
    streak, best, studied = streaks(c["prod_days"], today)
    due = sum(t["due"] for t in c["topics"])
    owed = any(t["owed"] for t in c["topics"])
    yesterday = (today - datetime.timedelta(days=1)).isoformat()
    earlier = any(d < yesterday for d in c["prod_days"])
    if not c["prod_days"]:
        return "waiting", "Hi, I’m Spark. Your first session starts your streak."
    if studied:
        passed = [(t, k) for t in c["topics"] for k in t["passed_today"]]
        if passed:
            t, k = passed[0]
            return "celebrating", "%s passed unaided." % short_title(t["mods"][k]["title"])
        if streak in MILESTONES:
            tail = " A new best." if streak >= best and streak > 3 else ""
            return "celebrating", "%d-day streak.%s" % (streak, tail)
        if due == 0 and sum(t["reviewed_today"] for t in c["topics"]):
            return "celebrating", "Every due card cleared."
        if yesterday not in c["prod_days"] and earlier:
            return "comeback", ("Welcome back. Your best is still %d." % best) if best > 1 \
                else "Welcome back."
        return "proud", "Day %s done. Your streak is safe." % word(streak)
    if due == 0 and not owed:
        return "resting", ("Nothing due today. One session keeps your streak going."
                           if streak else "Nothing due today. Read ahead or rest.")
    if streak == 1:
        return "waiting", "You studied yesterday. One session today makes it two in a row."
    if streak > 1:
        return "waiting", "%s days in a row. One session today makes it %s." % (
            word(streak).capitalize(), word(streak + 1))
    if best > 1:
        return "waiting", "Your best run is %d days. One session today starts a new one." % best
    return "waiting", "One session today starts a streak."


# --------------------------------------------------------------------------
# Render.

# Lucide-style line icons on a 24 grid, drawn at 18px with a 2 stroke.
ICON = {
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "book": '<path d="M2 4h6a4 4 0 0 1 4 4v13a3 3 0 0 0-3-3H2zM22 4h-6a4 4 0 0 0-4 4v13a3 3 0 0 1 3-3h7z"/>',
    "news": '<path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2zm0 0a2 2 0 0 1-2-2v-9'
            'c0-1.1.9-2 2-2h2M18 14h-8M15 18h-5M10 6h8v4h-8z"/>',
    "cards": '<path d="M5 7h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z'
             'M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-2"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    "copy": '<rect x="8" y="8" width="14" height="14" rx="2"/><path d="M4 16a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "left": '<path d="m15 18-6-6 6-6"/>',
    "right": '<path d="m9 18 6-6-6-6"/>',
}


def icon(name, size=18, cls="ic"):
    return ('<svg class="%s" width="%d" height="%d" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">%s</svg>'
            % (cls, size, size, ICON[name]))


def cmd_chip(cmd):
    return '<code class="cmd">%s</code>' % esc(cmd)


def date_text(d, pattern):
    """strftime, with {d} for the day of the month without a leading zero.
    "%-d" does that on macOS and Linux but not on Windows."""
    return d.strftime(pattern).replace("{d}", str(d.day))


def spark_svg(mood, size):
    """Spark in amber, the colour the streak uses."""
    def star(x, y, s):
        a, b = 1.4 * s, 2.6 * s
        return ("M%g %gl%g %g %g %g-%g %g-%g %g-%g-%g-%g-%g %g-%gz"
                % (x, y - 4 * s, a, b, b, a, b, a, a, b, a, b, b, a, b, a))
    g = dict(wx1=31, wx2=53, wr=8, px1=31, px2=53, py=49, pr=4, lids="", blush=0,
             mouth="M36 60q6 5 12 0", mfill="none", arms="", sparks="", zz="")
    g.update({
        "waiting": dict(px1=34, px2=56, py=51),
        "proud": dict(wr=0, pr=0, lids="M24 51q7-7 14 0M46 51q7-7 14 0", blush=5,
                      mouth="M33 58q9 9 18 0", sparks=star(72, 22, 1)),
        "celebrating": dict(wr=9, pr=4.5, py=48, blush=5, mouth="M34 58q8 12 16 0z", mfill="#1f1b16",
                            arms="M14 42c-7-8-6-17 1-18s7 10 5 19zM70 42c7-8 6-17-1-18s-7 10-5 19z",
                            sparks=star(10, 16, 1.2) + star(74, 10, 1) + star(78, 32, .8) + star(6, 36, .7)),
        "resting": dict(wr=0, pr=0, lids="M24 51q7 4 14 0M46 51q7 4 14 0", mouth="M39 61h6",
                        zz="M62 20h7l-7 8h7M71 8h5l-5 6h5"),
        "comeback": dict(arms="M71 46c7-6 9-15 2-17s-9 9-7 19z", mouth="M35 59q7 6 14 0"),
    }.get(mood, {}))
    p = ['<svg class="spark" width="%d" height="%d" viewBox="0 0 84 84" aria-hidden="true">' % (size, size),
         '<ellipse cx="42" cy="81" rx="22" ry="2.5" fill="rgba(0,0,0,.18)"/>']
    if g["arms"]:
        p.append('<path d="%s" fill="#c9831f"/>' % g["arms"])
    p.append('<path d="M42 6l3.2 7 7.6.6-5.8 4.9 1.8 7.4-6.8-4-6.8 4 1.8-7.4-5.8-4.9 7.6-.6z" fill="#c9831f"/>'
             '<ellipse cx="42" cy="54" rx="30" ry="26" fill="#f0a53a"/>'
             '<ellipse cx="42" cy="62" rx="17" ry="12" fill="#f8d49a"/>')
    if g["wr"]:
        p.append('<circle cx="%g" cy="49" r="%g" fill="#fff"/><circle cx="%g" cy="49" r="%g" fill="#fff"/>'
                 % (g["wx1"], g["wr"], g["wx2"], g["wr"]))
        p.append('<circle cx="%g" cy="%g" r="%g" fill="#1f1b16"/><circle cx="%g" cy="%g" r="%g" fill="#1f1b16"/>'
                 % (g["px1"], g["py"], g["pr"], g["px2"], g["py"], g["pr"]))
    if g["lids"]:
        p.append('<path d="%s" fill="none" stroke="#1f1b16" stroke-width="3" stroke-linecap="round"/>' % g["lids"])
    if g["blush"]:
        p.append('<ellipse cx="23" cy="59" rx="5" ry="3" fill="#e98a6a" opacity=".85"/>'
                 '<ellipse cx="61" cy="59" rx="5" ry="3" fill="#e98a6a" opacity=".85"/>')
    p.append('<path d="%s" fill="%s" stroke="#1f1b16" stroke-width="2.6" stroke-linecap="round" '
             'stroke-linejoin="round"/>' % (g["mouth"], g["mfill"]))
    if g["sparks"]:
        p.append('<path d="%s" fill="#c9831f"/>' % g["sparks"])
    if g["zz"]:
        p.append('<path d="%s" fill="none" stroke="#8a847a" stroke-width="2.2" stroke-linecap="round" '
                 'stroke-linejoin="round"/>' % g["zz"])
    p.append("</svg>")
    return "".join(p)


def pct(score):
    return "" if score is None else "%d%%" % round(score * 100)


def node_kind(t, k):
    st = t["mods"][k]["status"]
    if k == t["current"] and st not in OWED:
        return "now"
    if st == "unaided_pass":
        return "passed"
    if st in OWED:
        return "owed"
    if st == "untouched":
        return "new"
    return "doing"


def node(t, k, size, tag="div", extra=""):
    """One chapter as a ring: the arc is the last score."""
    m = t["mods"][k]
    kind = node_kind(t, k)
    s = m.get("last_score")
    deg = 0 if s is None or kind == "new" else int(round(s * 360))
    inner = "" if kind == "new" else (pct(s) or "–")
    return ('<%s class="node %s" style="--deg:%ddeg;--n:%dpx"%s><span>%s</span></%s>'
            % (tag, kind, deg, size, extra, inner, tag))


# --------------------------------------------------------------------------
# Overview

def next_step(c):
    """The one thing to do next: (command, headline, subline)."""
    topics = c["topics"]
    if not topics:
        return "/interview", "Start a subject", 'For example: /interview "Spanish for travel"'
    for t in topics:
        if t["owed"]:
            k = t["owed"][0]
            return ("/explain", "Redo %s from scratch" % short_title(t["mods"][k]["title"]),
                    "No notes and no help. Nothing new starts until the redo passes")
    due = sum(t["due"] for t in topics)
    if due:
        overdue = sum(t["overdue"] for t in topics)
        tomorrow = sum(t["tomorrow"] for t in topics)
        bits = ["%d overdue" % overdue if overdue else "%d due today" % due]
        if tomorrow:
            bits.append("%d more tomorrow" % tomorrow)
        return "/review", "Review %s" % plural(due, "due card"), " · ".join(bits)
    if not any(t["mods"] for t in topics):
        return "/map", "Plan the chapters", "Turn the subject into an ordered list of parts"
    cur = next((t for t in topics if t["current"]), None)
    tomorrow = sum(t["tomorrow"] for t in topics)
    lead = "Nothing due" + (", %d tomorrow." % tomorrow if tomorrow else ".")
    tail = " You’re on %s." % short_title(cur["mods"][cur["current"]]["title"]) if cur else ""
    return "/socratic", "Keep going", lead + tail


def index_card(c):
    """The next step, drawn as an index card: the one bright thing on the
    overview. Its command runs in Claude Code, not here, so the button copies
    it, ready to paste."""
    cmd, head, sub = next_step(c)
    return ('<section class="icard" aria-label="Next step">'
            '<div class="icard-top"><span class="icard-label">Next</span>%s</div>'
            '<div class="icard-body"><h2>%s</h2><p>%s</p></div>'
            '<button class="copy" type="button" data-copy="%s" data-say="Copied. Paste it into Claude Code">'
            '%s<span>Copy %s</span></button></section>'
            % (cmd_chip(cmd), esc(head), esc(sub), esc(cmd), icon("copy", 16), esc(cmd)))


def subject_card(t):
    if not t["mods"]:
        body = '<p class="muted">No chapters yet. Run %s to lay out this subject</p>' % cmd_chip("/map")
    else:
        steps = []
        for k in t["chain"]:
            here = k == t["current"]
            steps.append('<li class="%s">%s<span class="plabel">%s</span></li>'
                         % ("here" if here else "", node(t, k, 44), esc(t["labels"][k])))
        cur = short_title(t["mods"][t["current"]]["title"]) if t["current"] else ""
        body = ('<ol class="path">%s</ol>'
                '<p class="on">You’re on <b>%s</b></p>' % ("".join(steps), esc(cur)))
    return ('<section class="card subject"><div class="card-head"><div><h2>%s</h2>'
            '<p class="meta">%d of %d started · %s due</p></div>'
            '<a class="link" href="#tab-%s">Open map %s</a></div>%s</section>'
            % (esc(t["title"]), t["started"], len(t["mods"]), plural(t["due"], "card"),
               esc(t["slug"]), icon("arrow", 16), body))


def overview_html(c, demo):
    topics, today = c["topics"], c["today"]
    demo_note = ('<p class="note"><b>Sample data</b> A made-up topic so you can see the dashboard before '
                 'you have studied anything. Your own topics appear after %s</p>'
                 % cmd_chip("/interview")) if demo else ""
    head = '<header class="phead"><h1>%s</h1></header>' % date_text(today, "%A {d} %B")
    if not topics:
        return (head + demo_note +
                '<div class="hello">%s<p>Hi, I’m Spark. Start a subject and I’ll keep score.</p></div>'
                % spark_svg("waiting", 56) +
                '<div class="ov"><div class="ov-main">%s</div></div>' % index_card(c))

    mood, line = spark_state(c)
    streak, best, _ = streaks(c["prod_days"], today)
    days = []
    for d in week(c["prod_days"], today):
        inner = icon("check", 14) if d["state"] == "done" else ""
        days.append('<li class="%s" title="%s"><i>%s</i><span>%s</span></li>'
                    % (d["state"], date_text(d["date"], "%a {d} %b"), inner, d["letter"]))

    due = sum(t["due"] for t in topics)
    reviewed = sum(t["reviewed_today"] for t in topics)
    total = due + reviewed
    t_iso = today.isoformat()
    unaided = any(s["at"][:10] == t_iso and s["role"] in UNAIDED_ROLES for s in c["sessions"])
    rows = []
    if total:
        rows.append(("cards", "Due cards reviewed", "%d of %d" % (reviewed, total), reviewed / float(total)))
    else:
        rows.append(("cards", "No cards due today", "Done", 1.0))
    rows.append(("target", "One unaided attempt", "Done" if unaided else "0 of 1", 1.0 if unaided else 0.0))
    today_rows = "".join(
        '<li>%s<div><div class="trow"><span>%s</span><span class="fig">%s</span></div>'
        '<div class="bar%s"><i style="width:%d%%"></i></div></div></li>'
        % (icon(ic), esc(label), esc(count), " full" if frac >= 1 else "", round(frac * 100))
        for ic, label, count, frac in rows)

    overrides = sum(t["overrides"] for t in topics)
    side = ('<section class="card"><p class="label">Streak</p>'
            '<p class="figure">%s</p><p class="meta">Best %d</p>'
            '<ol class="week">%s</ol></section>'
            '<section class="card"><p class="label">Gate overrides on record</p>'
            '<p class="figure">%d</p><p class="meta">Each one is a shortcut past the struggle, logged with its reason</p></section>'
            % (plural(streak, "day"), best, "".join(days), overrides))
    main = (index_card(c) +
            '<section class="card"><h2>Today</h2><ul class="today">%s</ul></section>' % today_rows +
            "".join(subject_card(t) for t in topics))
    return (head + demo_note +
            '<div class="hello">%s<p>%s</p></div>' % (spark_svg(mood, 56), esc(line)) +
            '<div class="ov"><div class="ov-main">%s</div><aside class="ov-side">%s</aside></div>' % (main, side))


# --------------------------------------------------------------------------
# One topic

def topic_html(t):
    mods = t["mods"]
    level = ('<div class="level" title="How long this topic’s cards stay remembered, on average. '
             'It only rises when cards stick."><p class="label">Level</p><p class="figure">%d</p></div>'
             % t["level"]) if t["level"] is not None else ""
    head = ('<header class="phead topic-head"><div><h1>%s</h1><p class="meta">%d of %d started · %s due · %s</p></div>%s</header>'
            % (esc(t["title"]), t["started"], len(mods), plural(t["due"], "card"),
               plural(t["overrides"], "gate override"), level))
    if not mods:
        return head + ('<section class="card"><p class="muted">No chapters yet. Run %s to lay out this subject</p></section>'
                       % cmd_chip("/map"))
    L = t["layout"]
    S = L["S"]
    edges = []
    for a, b in t["edges"]:
        (xa, ya), (xb, yb) = L["pos"][a], L["pos"][b]
        x1, y1, x2, y2 = xa + S / 2.0, ya + S / 2.0, xb + S / 2.0, yb + S / 2.0
        my = (y1 + y2) / 2.0
        edges.append('<path data-a="%s" data-b="%s" d="M%.1f %.1fC%.1f %.1f %.1f %.1f %.1f %.1f"/>'
                     % (esc(a), esc(b), x1, y1, x1, my, x2, my, x2, y2))
    nodes, details = [], []
    for k in t["order"]:
        x, y = L["pos"][k]
        m = mods[k]
        lab = t["labels"][k]
        status = STATUS_LABEL.get(m["status"], m["status"])
        aria = "%s, %s, %s%s" % (lab, short_title(m["title"]), status,
                                 ", last score " + pct(m.get("last_score")) if m.get("last_score") is not None else "")
        here = k == t["current"]
        nodes.append('<div class="mnode%s" style="left:%.1fpx;top:%.1fpx">%s<span class="plabel">%s</span>%s</div>' % (
            " here" if here else "", x, y,
            node(t, k, 48, tag="button", extra=' type="button" data-mod="%s" aria-label="%s"' % (esc(k), esc(aria))),
            esc(lab), '<span class="you">You</span>' if here else ""))
        needs = [t["labels"][a] for a, b in t["edges"] if b == k]
        unlocks = [t["labels"][b] for a, b in t["edges"] if a == k]
        facts = [("Status", status)]
        if m.get("attempts"):
            facts.append(("Attempts", str(m["attempts"])))
        if m.get("last_score") is not None:
            facts.append(("Last score", pct(m["last_score"])))
        facts.append(("Needs", ", ".join(needs) if needs else "Nothing, a starting point"))
        if unlocks:
            facts.append(("Unlocks", ", ".join(unlocks)))
        shown = here or (t["current"] is None and k == t["order"][0])
        details.append(
            '<div class="detail" data-detail="%s"%s><p class="label">%s%s</p><h2>%s</h2><dl>%s</dl></div>' % (
                esc(k), "" if shown else " hidden", esc(lab),
                ' <span class="you inline">You’re on this one</span>' if here else "",
                esc(short_title(m["title"])),
                "".join("<div><dt>%s</dt><dd>%s</dd></div>" % (esc(a), esc(b)) for a, b in facts)))
    log = ""
    if t["sessions"]:
        rows = "".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td class=\"fig\">%s</td></tr>" % (
                esc(date_text(day(s["at"]), "{d} %b")), esc(s["role"].capitalize()),
                esc(t["labels"].get(s.get("module"), "")),
                ("Override" if s.get("override") else pct(s.get("score"))))
            for s in t["sessions"][:12])
        log = ('<section class="card log"><div class="card-head"><h2>Recent sessions</h2>'
               '<span class="meta">%s logged</span></div><table><thead><tr><th>Date</th><th>Role</th><th>Part</th>'
               '<th class="fig">Score</th></tr></thead><tbody>%s</tbody></table></section>'
               % (plural(len(t["sessions"]), "session"), rows))
    legend = ('<ul class="legend"><li><i class="lg passed"></i>Passed unaided</li><li><i class="lg doing"></i>In progress</li>'
              '<li><i class="lg owed"></i>Redo owed</li><li><i class="lg new"></i>Not started</li></ul>')
    return (head +
            '<div class="tgrid"><section class="card mapcard"><div class="card-head"><h2>Chapter map</h2>%s</div>'
            '<div class="mapscroll"><div class="map" style="width:%dpx;height:%dpx">'
            '<svg class="edges" width="%d" height="%d" viewBox="0 0 %d %d" aria-hidden="true">%s</svg>%s</div></div></section>'
            '<aside class="tside"><section class="card details">%s</section>%s</aside></div>'
            % (legend, L["W"], L["H"], L["W"], L["H"], L["W"], L["H"], "".join(edges), "".join(nodes),
               "".join(details), log))


# --------------------------------------------------------------------------
# Page. The News tab's rules live in news.py and are appended after these.

CSS = """
:root{
  color-scheme:dark;
  --deep:#12110f;--bg:#161513;--card:#1c1a18;--raised:#262421;
  --line:rgba(239,233,222,.08);--line2:rgba(239,233,222,.14);
  --ink:#efe9de;--ink2:#aaa398;--muted:#8a847a;
  --accent:#f0a53a;--accent-ink:#1f1b16;--accent-text:#f0a53a;
  --pos:#4cc38a;--neg:#e5484d;--neg-soft:#e98a6a;
  --paper:#f6f0e2;--paper-ink:#1f1b16;--paper-ink2:#5e554a;--paper-rule:rgba(70,110,170,.16);--paper-red:#c8473f;
  --shadow:0 1px 0 rgba(255,255,255,.04) inset;
  --paper-shadow:0 1px 2px rgba(0,0,0,.4),0 12px 32px rgba(0,0,0,.35);
  --ease:cubic-bezier(.22,1,.36,1);
}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){
  color-scheme:light;
  --deep:#f1ece3;--bg:#f7f4ee;--card:#fdfbf7;--raised:#efe9df;
  --line:rgba(31,27,22,.08);--line2:rgba(31,27,22,.14);
  --ink:#1f1b16;--ink2:#5e554a;--muted:#736a5e;
  --accent:#e9992b;--accent-ink:#1f1b16;--accent-text:#8f5200;
  --pos:#16a34a;--neg:#dc2626;--neg-soft:#d9694a;
  --paper:#fffdf6;--shadow:0 1px 2px rgba(0,0,0,.05);
  --paper-shadow:0 1px 2px rgba(31,27,22,.08),0 8px 24px rgba(31,27,22,.08);
}}
:root[data-theme="light"]{
  color-scheme:light;
  --deep:#f1ece3;--bg:#f7f4ee;--card:#fdfbf7;--raised:#efe9df;
  --line:rgba(31,27,22,.08);--line2:rgba(31,27,22,.14);
  --ink:#1f1b16;--ink2:#5e554a;--muted:#736a5e;
  --accent:#e9992b;--accent-ink:#1f1b16;--accent-text:#8f5200;
  --pos:#16a34a;--neg:#dc2626;--neg-soft:#d9694a;
  --paper:#fffdf6;--shadow:0 1px 2px rgba(0,0,0,.05);
  --paper-shadow:0 1px 2px rgba(31,27,22,.08),0 8px 24px rgba(31,27,22,.08);
}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);
  font:400 15px/22px Figtree,-apple-system,system-ui,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
h1,h2,p,ol,ul,dl,dd{margin:0;padding:0}
ol,ul{list-style:none}
a{color:inherit}
::selection{background:var(--accent);color:var(--accent-ink)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;border-radius:6px}
.ic{flex:none;color:var(--muted)}
.muted{color:var(--muted)}
.fig,.figure{font-variant-numeric:tabular-nums}
.meta{font-size:13px;line-height:20px;color:var(--muted)}
.label{font-size:13px;line-height:20px;color:var(--ink2)}
code,.cmd{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:13px}
.cmd{display:inline-block;padding:0 6px;line-height:22px;border-radius:6px;background:var(--raised);
  box-shadow:inset 0 0 0 1px var(--line);color:var(--ink);white-space:nowrap}

/* Shell */
.shell{display:grid;grid-template-columns:268px minmax(0,1fr);min-height:100vh}
.side{background:var(--deep);border-right:1px solid var(--line);padding:20px 12px;display:flex;flex-direction:column;gap:24px;
  position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:10px;padding:0 8px;font-size:16px;font-weight:600;line-height:24px}
.mark{width:20px;height:16px;border-radius:3px;background:var(--paper);position:relative;flex:none}
.mark::before{content:"";position:absolute;left:0;right:0;top:4px;height:1.5px;background:var(--paper-red)}
.mark::after{content:"";position:absolute;left:3px;right:3px;top:9px;height:1px;background:var(--paper-rule);box-shadow:0 3px 0 var(--paper-rule)}
.navlabel{font-size:12px;line-height:16px;color:var(--muted);padding:0 10px;margin-bottom:8px}
.tabwrap{position:relative}
.tabs{display:flex;flex-direction:column;gap:2px}
.tabs a{display:flex;align-items:center;gap:10px;height:36px;padding:0 10px;border-radius:8px;text-decoration:none;
  color:var(--ink2);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  transition:background-color .15s var(--ease),color .15s var(--ease)}
.tabs a span{overflow:hidden;text-overflow:ellipsis}
.tabs a:hover{background:var(--card);color:var(--ink)}
.tabs a[aria-current="page"]{background:var(--raised);color:var(--ink);box-shadow:inset 0 1px 0 rgba(255,255,255,.06),inset 0 0 0 1px var(--line)}
.tabs a[aria-current="page"] .ic{color:var(--ink)}
.more{display:none}
.side-foot{margin-top:auto;padding:0 10px;font-size:12px;line-height:16px;color:var(--muted)}
.main{min-width:0;padding:32px 32px 64px}
.panel{max-width:1160px;margin:0 auto;display:flex;flex-direction:column;gap:24px;animation:rise .4s var(--ease)}
.panel[hidden]{display:none}
@keyframes rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

/* Headers */
.phead{display:flex;justify-content:space-between;align-items:flex-end;gap:16px}
.phead h1{font-size:32px;line-height:36px;font-weight:500;letter-spacing:-.01em}
.phead .meta{margin-top:4px;font-size:14px}
.hello{display:flex;align-items:center;gap:12px;margin-top:-12px}
.hello .spark{flex:none}
.hello p{font-size:17px;line-height:24px;color:var(--ink2)}
.note{background:var(--raised);border-radius:10px;padding:12px 16px;font-size:14px;color:var(--ink2)}
.note b{color:var(--ink);font-weight:600;margin-right:4px}

/* Cards */
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;box-shadow:var(--shadow);
  display:flex;flex-direction:column;gap:16px}
.card h2{font-size:16px;line-height:24px;font-weight:500}
.card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.figure{font-size:32px;line-height:36px;font-weight:500;margin-top:-8px}
.link{display:inline-flex;align-items:center;gap:6px;font-size:14px;font-weight:500;color:var(--ink2);text-decoration:none;
  padding:4px 8px;margin:-4px -8px;border-radius:8px;white-space:nowrap;transition:background-color .15s var(--ease),color .15s var(--ease)}
.link:hover{background:var(--raised);color:var(--ink)}
.link .ic{color:currentColor}

/* Overview grid */
.ov{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px;align-items:start}
.ov-main,.ov-side{display:flex;flex-direction:column;gap:16px}

/* The index card: the one bright thing on the overview */
.icard{position:relative;background:var(--paper);color:var(--paper-ink);border-radius:6px;box-shadow:var(--paper-shadow);
  padding:20px 24px 24px;display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"top top" "body btn";
  gap:12px 24px;align-items:end;overflow:hidden;
  background-image:linear-gradient(var(--paper-red),var(--paper-red)),
    repeating-linear-gradient(to bottom,transparent 0,transparent 27px,var(--paper-rule) 27px,var(--paper-rule) 28px);
  background-size:100% 1.5px,100% 100%;background-position:0 52px,0 52px;background-repeat:no-repeat,no-repeat}
.icard-top{grid-area:top;display:flex;align-items:center;gap:12px;height:24px;margin-bottom:12px}
.icard-label{font-size:13px;color:var(--paper-ink2)}
.icard .cmd{background:rgba(31,27,22,.06);box-shadow:inset 0 0 0 1px rgba(31,27,22,.1);color:var(--paper-ink)}
.icard-body{grid-area:body}
.icard h2{font-size:28px;line-height:32px;font-weight:500;letter-spacing:-.01em}
.icard p{margin-top:8px;color:var(--paper-ink2);font-size:15px}
.copy{grid-area:btn;display:inline-flex;align-items:center;gap:8px;height:40px;padding:0 16px;border:0;border-radius:8px;
  background:var(--paper-ink);color:var(--paper);font:500 14px/1 Figtree,system-ui,sans-serif;cursor:pointer;white-space:nowrap;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.12);transition:background-color .15s var(--ease),transform .12s var(--ease)}
.copy .ic{color:currentColor}
.copy:hover{background:#3a332b}
.copy:active{transform:scale(.97)}
.copy.done{background:#2f6b4a}

/* Today */
.today{display:flex;flex-direction:column;gap:16px}
.today li{display:grid;grid-template-columns:18px minmax(0,1fr);gap:10px;align-items:start}
.today li>.ic{margin-top:2px}
.trow{display:flex;justify-content:space-between;gap:12px}
.trow .fig{color:var(--ink2);font-size:14px}
.bar{height:4px;border-radius:2px;background:var(--raised);margin-top:8px;overflow:hidden}
.bar i{display:block;height:100%;border-radius:2px;background:var(--ink2)}
.bar.full i{background:var(--pos)}

/* Subjects */
.path{display:flex;align-items:flex-start;position:relative;padding:4px 0}
.path::before{content:"";position:absolute;left:12.5%;right:12.5%;top:26px;height:1px;background:var(--line2)}
.path li{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;position:relative}
.path .plabel{font-size:13px;color:var(--muted)}
.path li.here .plabel{color:var(--ink)}
.on{font-size:14px;color:var(--ink2)}
.on b{font-weight:500;color:var(--ink)}

/* Nodes: the arc is the last score */
.node{position:relative;width:var(--n);height:var(--n);border-radius:50%;border:0;padding:0;display:grid;place-items:center;
  background:conic-gradient(var(--arc) var(--deg),var(--line2) 0deg);--arc:var(--ink2);color:var(--ink);font:inherit}
.node::before{content:"";position:absolute;inset:3px;border-radius:50%;background:var(--card)}
.node span{position:relative;font-size:12px;font-weight:500;font-variant-numeric:tabular-nums}
.node.passed{--arc:var(--pos)}
.node.owed{--arc:var(--neg-soft)}
.node.now{--arc:var(--accent)}
.node.now::before{background:var(--accent)}
.node.now span{color:var(--accent-ink)}
.node.new{background:none}
.node.new::before{inset:0;background:var(--card);border:1.5px dashed var(--line2)}

/* Streak */
.week{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-top:4px}
.week li{display:flex;flex-direction:column;align-items:center;gap:6px}
.week i{display:grid;place-items:center;width:100%;height:32px;border-radius:6px;background:var(--raised)}
.week span{font-size:12px;line-height:16px;color:var(--muted)}
.week .done i{background:var(--accent)}
.week .done .ic{color:var(--accent-ink)}
.week .today i{background:transparent;box-shadow:inset 0 0 0 1.5px var(--accent)}
.week .today span{color:var(--accent-text)}
.week .blank i{background:transparent;box-shadow:inset 0 0 0 1px var(--line2)}

/* Topic */
.level{text-align:right}
.tgrid{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:24px;align-items:start}
.tside{display:flex;flex-direction:column;gap:16px}
.mapcard{padding-bottom:24px}
.mapscroll{overflow-x:auto}
.map{position:relative;margin:0 auto}
.edges{position:absolute;left:0;top:0}
.edges path{fill:none;stroke:var(--line2);stroke-width:1.5}
.edges path.hot{stroke:var(--ink2)}
.mnode{position:absolute;width:62px;display:flex;flex-direction:column;align-items:center;gap:6px;z-index:1}
.mnode .node{cursor:pointer;margin-top:7px;transition:box-shadow .15s var(--ease)}
.mnode .node:hover{box-shadow:0 0 0 3px var(--line2)}
.mnode .node.sel{box-shadow:0 0 0 2px var(--bg),0 0 0 3.5px var(--ink)}
.mnode .plabel{font-size:12px;line-height:16px;color:var(--muted);background:var(--card);padding:0 4px;border-radius:4px;white-space:nowrap}
.mnode.here .plabel{color:var(--ink)}
.you{position:absolute;top:-14px;font-size:11px;line-height:16px;font-weight:600;color:var(--accent-text)}
.you.inline{position:static;margin-left:8px}
.legend{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:4px 16px;font-size:13px;color:var(--muted)}
.legend li{display:flex;align-items:center;gap:6px}
.lg{width:8px;height:8px;border-radius:50%;display:inline-block}
.lg.passed{background:var(--pos)}.lg.doing{background:var(--ink2)}.lg.owed{background:var(--neg-soft)}
.lg.new{box-shadow:inset 0 0 0 1.5px var(--muted)}
.detail{display:flex;flex-direction:column;gap:4px}
.detail[hidden]{display:none}
.detail h2{font-size:20px;line-height:28px}
.detail dl{margin-top:12px;display:flex;flex-direction:column}
.detail dl div{display:flex;justify-content:space-between;gap:16px;padding:8px 0;border-top:1px solid var(--line);font-size:14px}
.detail dt{color:var(--muted)}
.detail dd{text-align:right;font-variant-numeric:tabular-nums}
.log table{width:100%;border-collapse:collapse;font-size:14px}
.log th{text-align:left;font-weight:400;font-size:13px;color:var(--muted);padding:0 0 8px}
.log td{padding:8px 0;border-top:1px solid var(--line);color:var(--ink2)}
.log td:first-child{color:var(--ink);font-variant-numeric:tabular-nums}
.log .fig{text-align:right}

/* Narrow screens: the sidebar becomes a top bar, everything stacks */
@media (max-width:1100px){
  .ov,.tgrid{grid-template-columns:minmax(0,1fr)}
}
@media (max-width:860px){
  .shell{display:block}
  .side{position:sticky;top:0;z-index:5;height:auto;padding:12px 16px 8px;gap:8px;border-right:0;border-bottom:1px solid var(--line)}
  .navlabel,.side-foot{display:none}
  .tabs{flex-direction:row;overflow-x:auto;scrollbar-width:none;gap:4px}
  .tabs::-webkit-scrollbar{display:none}
  .tabs a{flex:none;height:32px}
  .tabs a .ic{display:none}
  .more{position:absolute;top:0;bottom:0;z-index:1;width:48px;display:flex;align-items:center;padding:0;border:0;cursor:pointer;color:var(--ink)}
  .more[hidden]{display:none}
  .more.left{left:0;justify-content:flex-start;background:linear-gradient(90deg,var(--deep) 55%,transparent)}
  .more.right{right:0;justify-content:flex-end;background:linear-gradient(270deg,var(--deep) 55%,transparent)}
  .more span{display:grid;place-items:center;width:28px;height:28px;border-radius:8px;background:var(--raised);box-shadow:inset 0 0 0 1px var(--line)}
  .more .ic{color:var(--ink)}
  .main{padding:24px 16px 48px}
  .phead h1{font-size:28px;line-height:32px}
  .icard{grid-template-columns:minmax(0,1fr);grid-template-areas:"top" "body" "btn";padding:16px 20px 20px}
  .icard h2{font-size:24px;line-height:28px}
  .copy{justify-self:start}
  .card{padding:16px}
  .hello{margin-top:-8px}
}
@media (prefers-reduced-motion: reduce){*{transition:none!important;animation:none!important}}
"""

SCRIPT = """<script>
(function () {
  var q = new URLSearchParams(location.search).get("theme");
  if (q === "dark" || q === "light") document.documentElement.setAttribute("data-theme", q);
  var panels = [].slice.call(document.querySelectorAll(".panel"));
  var tabs = [].slice.call(document.querySelectorAll(".tabs a"));
  // On a phone the sidebar is a top bar. More tabs than fit: arrows at
  // whichever end has more, the wheel scrolls it sideways, and the chosen
  // tab slides into view.
  var bar = document.querySelector(".tabs");
  var moreL = document.querySelector(".more.left"), moreR = document.querySelector(".more.right");
  function edges() {
    var max = bar.scrollWidth - bar.clientWidth;
    moreL.hidden = bar.scrollLeft <= 2;
    moreR.hidden = bar.scrollLeft >= max - 2;
  }
  function reveal(a, smooth) {
    var pad = 48, x = a.offsetLeft, w = a.offsetWidth, to = null;
    if (bar.scrollWidth <= bar.clientWidth) return;
    if (x - pad < bar.scrollLeft) to = x - pad;
    else if (x + w + pad > bar.scrollLeft + bar.clientWidth) to = x + w + pad - bar.clientWidth;
    if (to !== null) bar.scrollTo({left: Math.max(0, to), behavior: smooth ? "smooth" : "auto"});
  }
  moreL.addEventListener("click", function () { bar.scrollBy({left: -Math.round(bar.clientWidth * .7), behavior: "smooth"}); });
  moreR.addEventListener("click", function () { bar.scrollBy({left: Math.round(bar.clientWidth * .7), behavior: "smooth"}); });
  bar.addEventListener("scroll", edges, {passive: true});
  window.addEventListener("resize", edges);
  window.addEventListener("load", edges);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(edges);
  bar.addEventListener("wheel", function (e) {
    if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
    var max = bar.scrollWidth - bar.clientWidth;
    if (max <= 0) return;
    if ((e.deltaY < 0 && bar.scrollLeft <= 0) || (e.deltaY > 0 && bar.scrollLeft >= max)) return;
    bar.scrollLeft = Math.max(0, Math.min(max, bar.scrollLeft + e.deltaY));
    e.preventDefault();
  }, {passive: false});
  function show(id, scroll) {
    if (!document.getElementById("p-" + id)) id = "tab-overview";
    panels.forEach(function (p) { p.hidden = p.id !== "p-" + id; });
    tabs.forEach(function (a) {
      if (a.getAttribute("href") === "#" + id) { a.setAttribute("aria-current", "page"); reveal(a, scroll); }
      else a.removeAttribute("aria-current");
    });
    if (scroll) window.scrollTo(0, 0);
    edges();
  }
  document.addEventListener("click", function (e) {
    var a = e.target.closest('a[href^="#tab-"]');
    if (!a) return;
    e.preventDefault();
    var id = a.getAttribute("href").slice(1);
    history.replaceState(null, "", "#" + id);
    show(id, true);
  });
  show(location.hash.slice(1) || "tab-overview", false);
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-copy]");
    if (!b) return;
    var text = b.getAttribute("data-copy"), label = b.querySelector("span");
    function said() {
      var was = label.textContent;
      label.textContent = b.getAttribute("data-say");
      b.classList.add("done");
      setTimeout(function () { label.textContent = was; b.classList.remove("done"); }, 2200);
    }
    function fallback() {
      var t = document.createElement("textarea");
      t.value = text; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); said(); } catch (err) {}
      document.body.removeChild(t);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(said, fallback);
    else fallback();
  });
  document.querySelectorAll(".mapcard").forEach(function (card) {
    var panel = card.closest(".panel");
    function pick(id) {
      card.querySelectorAll(".node[data-mod]").forEach(function (b) { b.classList.toggle("sel", b.getAttribute("data-mod") === id); });
      card.querySelectorAll(".edges path").forEach(function (p) {
        p.classList.toggle("hot", p.getAttribute("data-a") === id || p.getAttribute("data-b") === id);
      });
      panel.querySelectorAll(".detail").forEach(function (d) { d.hidden = d.getAttribute("data-detail") !== id; });
    }
    card.addEventListener("click", function (e) {
      var b = e.target.closest(".node[data-mod]");
      if (b) pick(b.getAttribute("data-mod"));
    });
    var start = panel.querySelector(".detail:not([hidden])");
    if (start) pick(start.getAttribute("data-detail"));
  });
})();
</script>"""


def font_face():
    """Figtree, carried inside the page so it stays one file and works offline.
    SIL Open Font License; OFL-Figtree.txt ships beside it in engine/fonts/."""
    if not os.path.isfile(FONT):
        return ""
    with open(FONT, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    return ('@font-face{font-family:"Figtree";font-style:normal;font-weight:400 600;font-display:swap;'
            'src:url(data:font/woff2;base64,%s) format("woff2")}' % data)


def render(c, news_data=None, show_news=True, demo=False):
    topics = c["topics"]
    tabs = ['<a href="#tab-overview" aria-current="page">%s<span>Overview</span></a>' % icon("overview")]
    # Panel ids carry a "p-" the tab links don't, so a "#tab-x" address
    # never matches an element and the browser can't jump past the tab bar.
    panels = ['<section class="panel" id="p-tab-overview">%s</section>' % overview_html(c, demo)]
    for t in topics:
        tabs.append('<a href="#tab-%s">%s<span>%s</span></a>' % (esc(t["slug"]), icon("book"), esc(t["title"])))
        panels.append('<section class="panel" id="p-tab-%s" hidden>%s</section>' % (esc(t["slug"]), topic_html(t)))
    extra_css = ""
    if news is not None and show_news:
        n = news.panel(news_data)
        tabs.append('<a href="#tab-news">%s<span>News</span></a>' % icon("news"))
        panels.append('<section class="panel" id="p-tab-news" hidden>%s</section>' % n["html"])
        extra_css = n["css"]
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>Study Engine</title>
<style>%s%s%s</style></head>
<body><div class="shell">
<aside class="side">
<div class="brand"><span class="mark" aria-hidden="true"></span>Study Engine</div>
<div>
<div class="tabwrap">
<button class="more left" type="button" aria-label="Scroll tabs left" hidden><span>%s</span></button>
<nav class="tabs" aria-label="Sections">%s</nav>
<button class="more right" type="button" aria-label="Scroll tabs right" hidden><span>%s</span></button>
</div></div>
<p class="side-foot">Rebuilt %s</p>
</aside>
<main class="main">
%s
</main></div>
%s
</body></html>
""" % (font_face(), CSS, extra_css, icon("left", 16), "".join(tabs), icon("right", 16),
       date_text(datetime.datetime.now(), "{d} %b, %H:%M"), "\n".join(panels), SCRIPT)


def demo_today():
    """The sample topic is dated: render it as of the day after its last
    session, so it looks lived-in whenever someone opens the kit."""
    last = [s["at"] for slug in store.topic_slugs() for s in store.read_sessions(slug)]
    return day(max(last)) + datetime.timedelta(days=1) if last else datetime.date.today()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--news", action="store_true",
                   help="fetch the news before building (what the 6:00 job runs)")
    p.add_argument("--news-if-stale", action="store_true",
                   help="fetch only if the 6:00 refresh has not run since it was due "
                        "(what /dashboard runs)")
    p.add_argument("--demo", action="store_true",
                   help="render the sample topic in examples/demo to view/demo.html")
    a = p.parse_args()
    out_path, real_root = OUT, store.ROOT
    news_data, fetch_now = None, False
    if a.demo:
        # The sample never mixes with real topics and never shows news.
        out_path = os.path.join(real_root, "view", "demo.html")
        store.set_root(DEMO_ROOT)
        today = demo_today()
    else:
        today = datetime.date.today()
        if news is not None:
            fetch_now = a.news or (a.news_if_stale and news.stale(news.load()))
            if fetch_now:
                news.fetch()
            news_data = news.load()
    c = collect(today)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(render(c, news_data, show_news=not a.demo, demo=a.demo))
    # The single-file rule: nothing may reach outside this document.
    with open(out_path, encoding="utf-8") as fh:
        text = fh.read()
    for needle in ("<link href", "<link rel=", "<script src", "<img src", "url(http", "@import"):
        if needle in text:
            raise SystemExit("external reference leaked into the dashboard: %s" % needle)
    report = {"wrote": os.path.relpath(out_path, real_root),
              "bytes": len(text), "topics": len(c["topics"]),
              "cards_due": sum(t["due"] for t in c["topics"]),
              "redo_owed": sum(len(t["owed"]) for t in c["topics"])}
    if a.demo:
        report["demo"] = True
        report["as_of"] = today.isoformat()
    elif news is not None:
        as_of = None
        if news_data and news_data.get("fetched"):
            try:
                as_of = datetime.datetime.strptime(news_data["fetched"], "%Y-%m-%dT%H:%M:%SZ").replace(
                    tzinfo=datetime.timezone.utc).astimezone().strftime("%a %d %b, %H:%M")
            except ValueError:
                as_of = None
        report["news"] = {"fetched_now": bool(fetch_now), "as_of": as_of,
                          "unreachable": sorted({n for col in news.columns(news_data)
                                                 for n in col["failed"]})}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
