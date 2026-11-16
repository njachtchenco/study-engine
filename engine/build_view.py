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
FONT = os.path.join(HERE, "fonts", "Nunito-latin.woff2")

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
            return "celebrating", "%s passed unaided!" % short_title(t["mods"][k]["title"])
        if streak in MILESTONES:
            tail = " A new best!" if streak >= best and streak > 3 else ""
            return "celebrating", "%d-day streak!%s" % (streak, tail)
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

ICON = {
    "cards": "M5 7h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z"
             "M8 7V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-2",
    "target": "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8zM12 11.5v1",
    "redo": "M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4",
    "check": "M5 12.5l4.5 4.5L19 7.5",
    "chevron": "M6 9l6 6 6-6",
}
FLAME = ("M12 2.5c.6 3.2 3.2 4.9 4.6 7.3 1 1.7 1.4 3.4 1.4 4.7a6 6 0 0 1-12 0c0-2.1.9-3.9 "
         "2.3-5.2.1 1.6.9 2.9 2.1 3.3-.4-3.6.4-7.1 1.6-10.1z")


def icon(name, cls="ic", size=26, stroke=2.2):
    return ('<svg class="%s" width="%d" height="%d" viewBox="0 0 24 24" fill="none" '
            'stroke="currentColor" stroke-width="%s" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true"><path d="%s"/></svg>'
            % (cls, size, size, stroke, ICON[name]))


def spark_svg(mood, size):
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
        "celebrating": dict(wr=9, pr=4.5, py=48, blush=5, mouth="M34 58q8 12 16 0z", mfill="#1e1a33",
                            arms="M14 42c-7-8-6-17 1-18s7 10 5 19zM70 42c7-8 6-17-1-18s-7 10-5 19z",
                            sparks=star(10, 16, 1.2) + star(74, 10, 1) + star(78, 32, .8) + star(6, 36, .7)),
        "resting": dict(wr=0, pr=0, lids="M24 51q7 4 14 0M46 51q7 4 14 0", mouth="M39 61h6",
                        zz="M62 20h7l-7 8h7M71 8h5l-5 6h5"),
        "comeback": dict(arms="M71 46c7-6 9-15 2-17s-9 9-7 19z", mouth="M35 59q7 6 14 0"),
    }.get(mood, {}))
    p = ['<svg class="spark" width="%d" height="%d" viewBox="0 0 84 84" aria-hidden="true">' % (size, size),
         '<ellipse cx="42" cy="81" rx="22" ry="2.5" fill="rgba(0,0,0,.22)"/>']
    if g["arms"]:
        p.append('<path d="%s" fill="#6a4de0"/>' % g["arms"])
    p.append('<path d="M42 6l3.2 7 7.6.6-5.8 4.9 1.8 7.4-6.8-4-6.8 4 1.8-7.4-5.8-4.9 7.6-.6z" fill="#ffb938"/>'
             '<ellipse cx="42" cy="54" rx="30" ry="26" fill="#8b6cff"/>'
             '<ellipse cx="42" cy="62" rx="17" ry="12" fill="#c9bcff"/>')
    if g["wr"]:
        p.append('<circle cx="%g" cy="49" r="%g" fill="#fff"/><circle cx="%g" cy="49" r="%g" fill="#fff"/>'
                 % (g["wx1"], g["wr"], g["wx2"], g["wr"]))
        p.append('<circle cx="%g" cy="%g" r="%g" fill="#1e1a33"/><circle cx="%g" cy="%g" r="%g" fill="#1e1a33"/>'
                 % (g["px1"], g["py"], g["pr"], g["px2"], g["py"], g["pr"]))
    if g["lids"]:
        p.append('<path d="%s" fill="none" stroke="#1e1a33" stroke-width="3" stroke-linecap="round"/>' % g["lids"])
    if g["blush"]:
        p.append('<ellipse cx="23" cy="59" rx="5" ry="3" fill="#ff9fb2" opacity=".85"/>'
                 '<ellipse cx="61" cy="59" rx="5" ry="3" fill="#ff9fb2" opacity=".85"/>')
    p.append('<path d="%s" fill="%s" stroke="#1e1a33" stroke-width="2.6" stroke-linecap="round" '
             'stroke-linejoin="round"/>' % (g["mouth"], g["mfill"]))
    if g["sparks"]:
        p.append('<path d="%s" fill="#ffb938"/>' % g["sparks"])
    if g["zz"]:
        p.append('<path d="%s" fill="none" stroke="#a9a4cf" stroke-width="2.2" stroke-linecap="round" '
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


def node_html(t, k, big=False, tag="div", extra=""):
    """(the YOU tag or "", the ring). The tag sits outside the ring so the
    caller decides where it hangs."""
    m = t["mods"][k]
    kind = node_kind(t, k)
    score = m.get("last_score")
    deg = 0 if score is None or kind == "new" else int(round(score * 360))
    inner = "" if kind == "new" else (pct(score) or "&ndash;")
    you = '<span class="you">YOU</span>' if k == t["current"] else ""
    return you, ('<%s class="ring %s%s" style="--deg:%ddeg"%s><span class="face">%s</span></%s>'
                 % (tag, kind, " big" if big else "", deg, extra, inner, tag))


def overview_topic(t):
    if not t["mods"]:
        body = '<p class="muted">No chapters yet. Run <code>/map</code> to lay out this subject.</p>'
    else:
        nodes = []
        for k in t["chain"]:
            you, ring = node_html(t, k, big=(k == t["current"]))
            nodes.append('<div class="pnode">%s<div class="rwrap">%s</div><span class="plabel%s">%s</span></div>' % (
                you, ring, " here" if k == t["current"] else "", esc(t["labels"][k])))
        nodes = "".join(nodes)
        cur = t["mods"][t["current"]]["title"] if t["current"] else ""
        body = ('<p class="muted meta">%d of %d started &middot; %s due</p>'
                '<div class="path">%s</div>'
                '<div class="pfoot"><span>You’re on %s.</span>'
                '<a class="key small" href="#tab-%s">Full map</a></div>'
                % (t["started"], len(t["mods"]), plural(t["due"], "card"), nodes,
                   esc(short_title(cur)), esc(t["slug"])))
    return ('<details class="topic"><summary><span>%s</span>%s</summary>'
            '<div class="tbody">%s</div></details>' % (esc(t["title"]), icon("chevron", "chev", 22, 2.6), body))


def do_next(c):
    topics = c["topics"]
    for t in topics:
        if t["owed"]:
            k = t["owed"][0]
            return ("redo", "/explain", "<code>/explain</code> &middot; redo first",
                    "%s, from scratch with no help" % esc(short_title(t["mods"][k]["title"])))
    due = sum(t["due"] for t in topics)
    if due:
        overdue = sum(t["overdue"] for t in topics)
        tomorrow = sum(t["tomorrow"] for t in topics)
        bits = ["%d overdue" % overdue if overdue else "%d due today" % due]
        if tomorrow:
            bits.append("%d more tomorrow" % tomorrow)
        return ("cards", "/review", "<code>/review</code> &middot; %s first" % plural(due, "card"),
                " &middot; ".join(bits))
    if not any(t["mods"] for t in topics):
        return ("target", "/map", "<code>/map</code> &middot; plan the chapters",
                "Turn the subject into an ordered list of parts.")
    cur = next((t for t in topics if t["current"]), None)
    tomorrow = sum(t["tomorrow"] for t in topics)
    tail = "You’re on %s." % esc(short_title(cur["mods"][cur["current"]]["title"])) if cur else ""
    lead = "Nothing due" + (", %d tomorrow." % tomorrow if tomorrow else ".")
    return ("target", "/socratic", "<code>/socratic</code> &middot; keep going", "%s %s" % (lead, tail))


def go_button(kind, cmd, l1, l2):
    """The one big action. Its command runs in Claude Code, not here, so a tap
    copies it, ready to paste."""
    return ('<button class="go" type="button" data-copy="%s" aria-label="Copy %s">%s'
            '<span><b>%s</b><small data-say="%s">%s</small></span></button>'
            % (esc(cmd), esc(cmd), icon(kind, "ic", 30), l1,
               esc("Copied %s. Paste it into Claude Code." % cmd), l2))


def overview_html(c, demo):
    topics, today = c["topics"], c["today"]
    demo_note = ('<div class="demo-note"><b>Sample data.</b> A made-up topic so you can see the '
                 'dashboard before you have studied anything. Your own topics show up in '
                 '<code>view/dashboard.html</code> after <code>/interview</code>.</div>') if demo else ""
    if not topics:
        return demo_note + (
            '<div class="hello">%s<p class="bubble">Hi, I’m Spark. Start a subject and I’ll keep score.</p></div>'
            '%s'
            '<p class="muted center">Once you have a topic, your streak, today’s quests and '
            'where you are in each subject appear here.</p>'
            % (spark_svg("waiting", 100),
               go_button("target", "/interview", "<code>/interview</code> &middot; start a subject",
                         "For example: /interview &quot;Spanish for travel&quot;")))

    mood, line = spark_state(c)
    streak, best, studied = streaks(c["prod_days"], today)
    keys = []
    for d in week(c["prod_days"], today):
        inner = ""
        if d["state"] == "done":
            inner = icon("check", "tick", 20, 3)
        elif d["state"] == "today":
            inner = ('<svg class="flame" width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">'
                     '<path d="%s"/></svg>' % FLAME)
        keys.append('<div class="day"><div class="dkey %s" title="%s">%s</div><span>%s</span></div>' % (
            d["state"], d["date"].strftime("%a %d %b"), inner, d["letter"]))

    due = sum(t["due"] for t in topics)
    reviewed = sum(t["reviewed_today"] for t in topics)
    total = due + reviewed
    t_iso = today.isoformat()
    unaided = any(s["at"][:10] == t_iso and s["role"] in UNAIDED_ROLES for s in c["sessions"])
    quests = []
    if total:
        quests.append(("cards", "mint", "Review the %s" % plural(total, "due card"),
                       "Done" if reviewed >= total else "%d / %d" % (reviewed, total), reviewed / float(total)))
    else:
        quests.append(("cards", "mint", "No cards due today", "Done", 1.0))
    quests.append(("target", "violet", "One unaided attempt", "Done" if unaided else "0 / 1", 1.0 if unaided else 0.0))
    quest_html = "".join(
        '<div class="quest q-%s">%s<div class="qbody"><div class="qrow"><span>%s</span>'
        '<span class="muted num">%s</span></div><div class="bar"><i style="width:%d%%"></i></div></div></div>'
        % (color, icon(ic), esc(label), esc(count), round(frac * 100))
        for ic, color, label, count, frac in quests)

    kind, cmd, l1, l2 = do_next(c)
    overrides = sum(t["overrides"] for t in topics)
    return (
        demo_note +
        '<div class="hello">%s<p class="bubble">%s</p></div>' % (spark_svg(mood, 100), esc(line)) +
        '<section class="card"><div class="row"><h2 class="streak"><span>%d</span> day streak</h2>'
        '<span class="muted">Best %d</span></div><div class="week">%s</div></section>'
        % (streak, best, "".join(keys)) +
        '<section class="card"><h2 class="h3">Today’s quests</h2>%s</section>' % quest_html +
        go_button(kind, cmd, l1, l2) +
        "".join(overview_topic(t) for t in topics) +
        '<p class="foot">Gate overrides on record: <b>%d</b> &middot; Rebuilt %s</p>'
        % (overrides, datetime.datetime.now().strftime("%d %b, %H:%M"))
    )


def topic_html(t):
    mods = t["mods"]
    level = ('<span class="lv" title="Level: how long this topic’s cards stay remembered, '
             'on average. It only rises when cards stick.">LV %d</span>' % t["level"]) if t["level"] is not None else ""
    head = ('<div class="thead"><div><h1>%s</h1><p class="muted">%d of %d started &middot; %s due'
            ' &middot; %s</p></div>%s</div>' % (
                esc(t["title"]), t["started"], len(mods), plural(t["due"], "card"),
                plural(t["overrides"], "gate override"), level))
    if not mods:
        return head + '<section class="card"><p class="muted">No chapters yet. Run <code>/map</code> to lay out this subject.</p></section>'
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
        aria = "%s, %s, %s%s" % (lab, short_title(m["title"]), STATUS_LABEL.get(m["status"], m["status"]),
                                 ", last score " + pct(m.get("last_score")) if m.get("last_score") is not None else "")
        you, ring = node_html(t, k, tag="button",
                              extra=' type="button" data-mod="%s" aria-label="%s"' % (esc(k), esc(aria)))
        nodes.append('<div class="mnode" style="left:%.1fpx;top:%.1fpx">%s%s<span class="plabel%s">%s</span></div>' % (
            x, y, you, ring, " here" if k == t["current"] else "", esc(lab)))
        needs = [t["labels"][a] for a, b in t["edges"] if b == k]
        unlocks = [t["labels"][b] for a, b in t["edges"] if a == k]
        meta = [STATUS_LABEL.get(m["status"], m["status"])]
        if m.get("attempts"):
            meta.append(plural(m["attempts"], "attempt"))
        if m.get("last_score") is not None:
            meta.append("last score " + pct(m["last_score"]))
        links = (esc("Needs " + ", ".join(needs)) if needs else "A starting point") + \
            (" &middot; Unlocks " + esc(", ".join(unlocks)) if unlocks else "")
        shown = k == t["current"] or (t["current"] is None and k == t["order"][0])
        details.append(
            '<div class="detail" data-detail="%s"%s><div class="row"><h2 class="h3">%s &middot; %s</h2>%s</div>'
            '<p class="muted">%s</p><p class="muted small">%s</p></div>' % (
                esc(k), "" if shown else " hidden", esc(lab), esc(short_title(m["title"])),
                '<span class="you inline">YOU</span>' if k == t["current"] else "",
                esc(" · ".join(meta)), links))
    rows = "".join(
        "<tr><td>%s</td><td>%s</td><td>%s</td><td class=\"num\">%s</td></tr>" % (
            esc(day(s["at"]).strftime("%d %b")), esc(s["role"]),
            esc(t["labels"].get(s.get("module"), "")),
            ("override" if s.get("override") else pct(s.get("score"))))
        for s in t["sessions"][:12])
    table = ('<details class="log"><summary>%s logged</summary><table><tr><th>When</th><th>Role</th>'
             '<th>Part</th><th class="num">Score</th></tr>%s</table></details>'
             % (plural(len(t["sessions"]), "session"), rows)) if t["sessions"] else ""
    return (head +
            '<section class="card mapcard"><div class="mapscroll"><div class="map" style="width:%dpx;height:%dpx">'
            '<svg class="edges" width="%d" height="%d" viewBox="0 0 %d %d" aria-hidden="true">%s</svg>%s</div></div>'
            '<div class="legend"><span><i class="lg passed"></i>Passed unaided</span><span><i class="lg doing"></i>In progress</span>'
            '<span><i class="lg owed"></i>Redo owed</span><span><i class="lg new"></i>Not started</span></div></section>'
            % (L["W"], L["H"], L["W"], L["H"], L["W"], L["H"], "".join(edges), "".join(nodes)) +
            '<section class="card details">%s</section>%s' % ("".join(details), table))


CSS = """
:root{
  color-scheme:dark;
  --bg:#17142b;--surf:#221e3d;--track:#332e57;--line:rgba(255,255,255,.08);--ink:#f4f2ff;--muted:#aba6d1;
  --violet:#6a4de0;--violet-lip:#4a32b0;--violet-soft:#8b6cff;--violet-text:#b9a8ff;
  --mint:#2bd9a0;--mint-lip:#1a9c72;--mint-ink:#0f2e24;--sun:#ffb938;--sun-lip:#c98a12;--sun-ink:#3a2400;
  --gold:#ffd23f;--gold-lip:#c79e10;--coral:#ff8a7a;--coral-lip:#c9584a;
  --key:#2c2752;--key-lip:#100d22;--slot:#1d1a35;--card-shadow:none;
}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){
  color-scheme:light;
  --bg:#f7f5ff;--surf:#fff;--track:#ece9fa;--line:rgba(45,42,69,.08);--ink:#2d2a45;--muted:#625d82;
  --violet-soft:#7c5cff;--violet-text:#5a3fd0;--mint-lip:#1fa57a;--sun-lip:#d69414;--gold:#ffc61a;--gold-lip:#cf9c00;
  --key:#fff;--key-lip:#d9d4ef;--slot:#ece9fa;--card-shadow:0 1px 2px rgba(45,42,69,.06),0 6px 16px rgba(45,42,69,.07);
}}
:root[data-theme="light"]{
  color-scheme:light;
  --bg:#f7f5ff;--surf:#fff;--track:#ece9fa;--line:rgba(45,42,69,.08);--ink:#2d2a45;--muted:#625d82;
  --violet-soft:#7c5cff;--violet-text:#5a3fd0;--mint-lip:#1fa57a;--sun-lip:#d69414;--gold:#ffc61a;--gold-lip:#cf9c00;
  --key:#fff;--key-lip:#d9d4ef;--slot:#ece9fa;--card-shadow:0 1px 2px rgba(45,42,69,.06),0 6px 16px rgba(45,42,69,.07);
}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;background:var(--bg);color:var(--ink);
  font:700 16px/1.4 Nunito,ui-rounded,"SF Pro Rounded",-apple-system,system-ui,"Segoe UI",sans-serif;
  -webkit-font-smoothing:antialiased}
::selection{background:#6a4de0;color:#fff}
:focus-visible{outline:3px solid #ffb938;outline-offset:2px}
a{color:inherit}
code{font-family:ui-monospace,"SF Mono",Menlo,Consolas,monospace;font-size:.92em;font-weight:700}
h1,h2,p{margin:0}
.app{max-width:460px;margin:0 auto;padding:18px 16px 40px;display:flex;flex-direction:column;gap:16px}
.muted{color:var(--muted)}
.small{font-size:.86rem}
.center{text-align:center}
.num{font-variant-numeric:tabular-nums}
.tabwrap{position:relative}
.tabs{position:relative;display:flex;gap:8px;overflow-x:auto;padding:0 2px 6px;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.more{position:absolute;top:0;bottom:6px;z-index:1;width:56px;display:flex;align-items:center;padding:0;border:0;
  cursor:pointer;color:var(--ink);font:inherit}
.more[hidden]{display:none}
.more.left{left:0;justify-content:flex-start;background:linear-gradient(90deg,var(--bg) 55%,transparent)}
.more.right{right:0;justify-content:flex-end;background:linear-gradient(270deg,var(--bg) 55%,transparent)}
.more span{display:grid;place-items:center;width:34px;height:34px;border-radius:50%;background:var(--key);
  box-shadow:0 3px 0 var(--key-lip)}
.more:active span{transform:translateY(3px);box-shadow:none}
.tabs a{flex:none;font-size:15px;font-weight:700;padding:8px 14px;border-radius:12px;text-decoration:none;
  background:var(--key);box-shadow:0 3px 0 var(--key-lip)}
.tabs a[aria-current="page"]{background:var(--violet);color:#fff;box-shadow:none;transform:translateY(3px);font-weight:800}
.panel{display:flex;flex-direction:column;gap:16px}
.panel[hidden]{display:none}
.card{background:var(--surf);box-shadow:var(--card-shadow);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:14px}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.h3{font-size:18px;font-weight:900}
.hello{display:flex;align-items:center;gap:12px}
.spark{flex:none}
.bubble{flex:1;background:var(--surf);box-shadow:var(--card-shadow);border-radius:18px;padding:14px 16px;font-size:18px;font-weight:800;line-height:1.3}
.demo-note{background:var(--key);border-radius:14px;padding:12px 14px;font-size:.9rem;line-height:1.45}
.demo-note b{color:var(--sun)}
.streak{font-size:26px;font-weight:900;letter-spacing:-.5px}
.streak span{color:var(--sun)}
.week{display:flex;gap:6px;padding-bottom:6px}
.day{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px}
.day span{font-size:13px;font-weight:800;margin-top:6px;color:var(--muted)}
.dkey{width:100%;height:54px;border-radius:14px;display:flex;align-items:center;justify-content:center}
.dkey.done{background:var(--sun);color:var(--sun-ink);transform:translateY(6px);box-shadow:inset 0 3px 0 rgba(0,0,0,.14)}
.dkey.miss{background:var(--slot);transform:translateY(6px);box-shadow:inset 0 2px 0 rgba(0,0,0,.25)}
.dkey.blank{background:transparent;border:2px dashed var(--track);transform:translateY(6px)}
.dkey.today{background:var(--key);border:2.5px solid var(--sun);box-shadow:0 6px 0 var(--key-lip)}
.dkey.today+span{color:var(--sun)}
.flame path{fill:none;stroke:var(--sun);stroke-width:2.2;stroke-linejoin:round}
.quest{display:flex;align-items:center;gap:12px}
.quest .ic{flex:none}
.q-mint .ic{color:var(--mint)} .q-mint .bar i{background:var(--mint)}
.q-violet .ic{color:var(--violet-soft)} .q-violet .bar i{background:var(--violet-soft)}
.qbody{flex:1;display:flex;flex-direction:column;gap:6px}
.qrow{display:flex;justify-content:space-between;gap:8px}
.bar{height:10px;border-radius:5px;background:var(--track);overflow:hidden}
.bar i{display:block;height:100%;border-radius:5px}
.go{display:flex;align-items:center;gap:12px;width:100%;border:0;font:inherit;text-align:left;cursor:pointer;
  background:var(--mint);color:var(--mint-ink);border-radius:16px;
  padding:14px 16px;box-shadow:0 5px 0 var(--mint-lip);margin-bottom:5px;text-decoration:none;
  transition:transform .12s ease-out,box-shadow .12s ease-out}
.go:active{transform:translateY(5px);box-shadow:0 0 0 var(--mint-lip)}
.go .ic{flex:none}
.go span{flex:1;display:flex;flex-direction:column;gap:1px}
.go b{font-size:19px;font-weight:900}
.go code{font-weight:800}
.go small{font-size:14px;font-weight:700;opacity:.85}
.topic{border-radius:16px;background:var(--key);box-shadow:0 4px 0 var(--key-lip);margin-bottom:4px}
.topic[open]{background:var(--surf);box-shadow:var(--card-shadow);margin-bottom:0}
.topic summary{list-style:none;display:flex;align-items:center;justify-content:space-between;padding:16px;cursor:pointer;
  font-size:19px;font-weight:900}
.topic summary::-webkit-details-marker{display:none}
.chev{color:var(--muted);transition:transform .2s cubic-bezier(.2,.8,.2,1)}
.topic[open] .chev{transform:rotate(180deg)}
.tbody{display:flex;flex-direction:column;gap:14px;padding:0 16px 16px}
.meta{font-size:14px;margin-top:-6px}
.path{position:relative;display:flex;justify-content:space-between;align-items:flex-start;padding-top:18px}
.path::before{content:"";position:absolute;left:36px;right:36px;top:53px;height:8px;border-radius:4px;background:var(--track)}
.pnode{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;gap:6px;width:80px}
.rwrap{height:78px;display:flex;align-items:center}
.pfoot{display:flex;justify-content:space-between;align-items:center;gap:10px;font-size:15px;line-height:1.35}
.key{flex:none;text-decoration:none;font-weight:800;border-radius:10px;background:var(--key);box-shadow:0 3px 0 var(--key-lip)}
.key.small{font-size:14px;padding:8px 12px}
.ring{position:relative;width:68px;height:68px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:conic-gradient(var(--violet-soft) var(--deg), var(--track) 0deg);border:0;padding:0;font:inherit;color:inherit}
.ring.big{width:78px;height:78px}
.ring .face{width:54px;height:54px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  font-size:17px;font-weight:900;font-variant-numeric:tabular-nums;background:var(--violet);color:#fff;box-shadow:0 4px 0 var(--violet-lip)}
.ring.big .face{width:62px;height:62px;font-size:19px}
.ring.now{background:conic-gradient(var(--sun) var(--deg), var(--track) 0deg)}
.ring.now .face{background:var(--sun);color:var(--sun-ink);box-shadow:0 4px 0 var(--sun-lip)}
.ring.passed{background:conic-gradient(var(--gold) var(--deg), var(--track) 0deg)}
.ring.passed .face{background:var(--gold);color:#2d2a45;box-shadow:0 4px 0 var(--gold-lip)}
.ring.owed{background:conic-gradient(var(--coral) var(--deg), var(--track) 0deg)}
.ring.owed .face{background:var(--coral);color:#3a0f0a;box-shadow:0 4px 0 var(--coral-lip)}
.ring.new{background:var(--surf)}
.ring.new .face{background:var(--slot);border:2px dashed var(--muted);box-shadow:none}
.you{position:absolute;top:-18px;left:50%;transform:translateX(-50%);z-index:2;font-size:11px;font-weight:900;
  background:var(--sun);color:var(--sun-ink);padding:2px 9px;border-radius:8px;white-space:nowrap}
.you.inline{position:static;transform:none;flex:none}
.plabel{font-size:13px;font-weight:800;white-space:nowrap;color:var(--muted)}
.plabel.here{color:var(--ink)}
.thead{display:flex;justify-content:space-between;align-items:flex-end;gap:10px}
.thead h1{font-size:28px;font-weight:900;letter-spacing:-.5px;line-height:1.1}
.thead p{font-size:14px;margin-top:2px}
.lv{font-size:18px;font-weight:900;color:var(--violet-text);white-space:nowrap;cursor:help}
.mapcard{padding:12px}
.mapscroll{overflow-x:auto}
.map{position:relative;margin:0 auto}
.edges{position:absolute;left:0;top:0}
.edges path{fill:none;stroke:var(--track);stroke-width:5;stroke-linecap:round}
.edges path.hot{stroke:var(--violet-soft)}
.mnode{position:absolute;width:62px;display:flex;flex-direction:column;align-items:center;gap:4px;z-index:1}
.mnode .ring{width:62px;height:62px;cursor:pointer}
.mnode .ring .face{width:48px;height:48px;font-size:15px;box-shadow:0 3px 0 var(--violet-lip)}
.mnode .ring.now .face{box-shadow:0 3px 0 var(--sun-lip)}
.mnode .ring.passed .face{box-shadow:0 3px 0 var(--gold-lip)}
.mnode .ring.owed .face{box-shadow:0 3px 0 var(--coral-lip)}
.mnode .ring.new .face{box-shadow:none}
.mnode .ring.sel{box-shadow:0 0 0 3px var(--ink)}
.mnode .plabel{font-size:12px;background:var(--surf);padding:0 4px;border-radius:6px}
.legend{display:flex;flex-wrap:wrap;gap:6px 14px;font-size:13px;color:var(--muted);padding:0 4px}
.legend span{display:flex;align-items:center;gap:6px}
.lg{width:14px;height:14px;border-radius:7px;display:inline-block}
.lg.passed{background:var(--gold)} .lg.doing{background:var(--violet)} .lg.owed{background:var(--coral)}
.lg.new{border:2px dashed var(--muted)}
.details .detail{display:flex;flex-direction:column;gap:6px}
.details .detail[hidden]{display:none}
.log summary{cursor:pointer;color:var(--violet-text);font-weight:800}
.log table{width:100%;border-collapse:collapse;margin-top:10px;font-size:14px}
.log th,.log td{text-align:left;padding:6px 4px;border-bottom:1px solid var(--line)}
.log th{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.log .num{text-align:right}
.foot{text-align:center;font-size:13px;color:var(--muted);margin-top:4px}
.empty{color:var(--muted)}
@media (prefers-reduced-motion: reduce){*{transition:none!important;animation:none!important}}
"""

SCRIPT = """<script>
(function () {
  var q = new URLSearchParams(location.search).get("theme");
  if (q === "dark" || q === "light") document.documentElement.setAttribute("data-theme", q);
  var panels = [].slice.call(document.querySelectorAll(".panel"));
  var tabs = [].slice.call(document.querySelectorAll(".tabs a"));
  // More tabs than fit the column: arrows at whichever end has more, the
  // wheel scrolls the bar sideways, and the chosen tab slides into view.
  var bar = document.querySelector(".tabs");
  var moreL = document.querySelector(".more.left"), moreR = document.querySelector(".more.right");
  function edges() {
    var max = bar.scrollWidth - bar.clientWidth;
    moreL.hidden = bar.scrollLeft <= 2;
    moreR.hidden = bar.scrollLeft >= max - 2;
  }
  function reveal(a, smooth) {
    var pad = 56, x = a.offsetLeft, w = a.offsetWidth, to = null;
    if (x - pad < bar.scrollLeft) to = x - pad;
    else if (x + w + pad > bar.scrollLeft + bar.clientWidth) to = x + w + pad - bar.clientWidth;
    if (to !== null) bar.scrollTo({left: Math.max(0, to), behavior: smooth ? "smooth" : "auto"});
  }
  function nudge(dir) {
    bar.scrollBy({left: dir * Math.round(bar.clientWidth * 0.7), behavior: "smooth"});
  }
  moreL.addEventListener("click", function () { nudge(-1); });
  moreR.addEventListener("click", function () { nudge(1); });
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
      if (a.getAttribute("href") === "#" + id) {
        a.setAttribute("aria-current", "page");
        reveal(a, scroll);
      } else a.removeAttribute("aria-current");
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
    var text = b.getAttribute("data-copy"), small = b.querySelector("small");
    function said() {
      if (!small) return;
      var was = small.innerHTML;
      small.textContent = small.getAttribute("data-say");
      setTimeout(function () { small.innerHTML = was; }, 2200);
    }
    function fallback() {
      var t = document.createElement("textarea");
      t.value = text; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); said(); } catch (err) {}
      document.body.removeChild(t);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(said, fallback);
    } else { fallback(); }
  });
  document.querySelectorAll(".mapcard").forEach(function (card) {
    var panel = card.closest(".panel");
    function pick(id) {
      card.querySelectorAll(".ring[data-mod]").forEach(function (b) {
        b.classList.toggle("sel", b.getAttribute("data-mod") === id);
      });
      card.querySelectorAll(".edges path").forEach(function (p) {
        p.classList.toggle("hot", p.getAttribute("data-a") === id || p.getAttribute("data-b") === id);
      });
      panel.querySelectorAll(".detail").forEach(function (d) {
        d.hidden = d.getAttribute("data-detail") !== id;
      });
    }
    card.addEventListener("click", function (e) {
      var b = e.target.closest(".ring[data-mod]");
      if (b) pick(b.getAttribute("data-mod"));
    });
    var start = panel.querySelector(".detail:not([hidden])");
    if (start) pick(start.getAttribute("data-detail"));
  });
})();
</script>"""


def font_face():
    """Nunito, carried inside the page so it stays one file and works offline.
    SIL Open Font License; the license ships beside the font in engine/fonts/."""
    if not os.path.isfile(FONT):
        return ""
    with open(FONT, "rb") as fh:
        data = base64.b64encode(fh.read()).decode("ascii")
    return ('@font-face{font-family:"Nunito";font-style:normal;font-weight:600 900;font-display:swap;'
            'src:url(data:font/woff2;base64,%s) format("woff2")}' % data)


def render(c, news_data=None, show_news=True, demo=False):
    topics = c["topics"]
    tabs = ['<a href="#tab-overview" aria-current="page">Overview</a>']
    # Panel ids carry a "p-" the tab links don't, so a "#tab-x" address
    # never matches an element and the browser can't jump past the tab bar.
    panels = ['<section class="panel" id="p-tab-overview">%s</section>' % overview_html(c, demo)]
    for t in topics:
        tabs.append('<a href="#tab-%s">%s</a>' % (esc(t["slug"]), esc(t["title"])))
        panels.append('<section class="panel" id="p-tab-%s">%s</section>' % (esc(t["slug"]), topic_html(t)))
    extra_css = ""
    if news is not None and show_news:
        n = news.panel(news_data)
        tabs.append('<a href="#tab-news">News</a>')
        panels.append('<section class="panel" id="p-tab-news">%s</section>' % n["html"])
        extra_css = n["css"]
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<title>Study Engine</title>
<style>%s%s%s</style></head>
<body><div class="app">
<div class="tabwrap">
<button class="more left" type="button" aria-label="Scroll tabs left" hidden><span><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M9 2 4 7l5 5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>
<nav class="tabs" aria-label="Sections">%s</nav>
<button class="more right" type="button" aria-label="Scroll tabs right" hidden><span><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M5 2l5 5-5 5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></span></button>
</div>
%s
</div>
%s
</body></html>
""" % (font_face(), CSS, extra_css, "".join(tabs), "\n".join(panels), SCRIPT)


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
