"""Read and write the state under topics/.

Everything a session needs to know lives in a few places per topic:

    topics/<slug>/topic.json      the profile the Interviewer built
    topics/<slug>/curriculum.md   the human-readable map
    topics/<slug>/materials.md    facts about the course or goal: dates, format, sources
    topics/<slug>/progress.md     where the learner is, levels with their evidence, a log
    topics/<slug>/modules.json    per-module status, including what redo is owed
    topics/<slug>/cards.json      the spaced-repetition deck
    topics/<slug>/sessions/*.md   one file per session, JSON meta in an HTML comment

The session files are the audit trail. They are markdown so a human can read
them and JSON-headed so the engine can. There is no second copy of that data.
"""

import json
import os
import re
import datetime

# STUDY_ENGINE_ROOT lets the tests point the whole engine at a temp directory,
# so they exercise the real CLI rather than a reimplementation of it.
ROOT = os.environ.get("STUDY_ENGINE_ROOT") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))
TOPICS = os.path.join(ROOT, "topics")


def set_root(path):
    """Point the whole engine at another root for the rest of this process.
    build_view.py --demo uses it to render examples/demo without touching the
    learner's own topics."""
    global ROOT, TOPICS
    ROOT = path
    TOPICS = os.path.join(path, "topics")

# A module moves through these. The gate cares about `explained` and `redo_due`:
# those two mean the learner has been handed an answer and has not yet
# reproduced it unaided, which is the exact state the video says destroys
# retention.
STATUSES = ("untouched", "attempting", "explained", "redo_due", "unaided_pass")

ROLES = ("interview", "map", "explain", "socratic", "examine", "clerk", "review",
         "diagnose", "spar")

# Roles that look back over material already covered instead of working on
# the next thing: a diagnosis, or a spar (mock exam) on an old chapter. Their
# --module says where the material lives, not where the learner is, so they
# don't count as an attempt on it and don't move "You're on". A dry-run spar
# on an old chapter sent the dashboard back to it (15 Nov).
LOOKBACK_ROLES = ("diagnose", "spar")


def now():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def today():
    return datetime.date.today().isoformat()


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "topic"


def topic_dir(slug):
    return os.path.join(TOPICS, slug)


def topic_slugs():
    if not os.path.isdir(TOPICS):
        return []
    out = []
    for name in sorted(os.listdir(TOPICS)):
        if os.path.isfile(os.path.join(TOPICS, name, "topic.json")):
            out.append(name)
    return out


def _read_json(path, default):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def read_topic(slug):
    data = _read_json(os.path.join(topic_dir(slug), "topic.json"), None)
    if data is None:
        raise SystemExit("no such topic: %s (have: %s)" % (slug, ", ".join(topic_slugs()) or "none"))
    return data


def write_topic(slug, data):
    _write_json(os.path.join(topic_dir(slug), "topic.json"), data)


def read_modules(slug):
    return _read_json(os.path.join(topic_dir(slug), "modules.json"), {})


def write_modules(slug, data):
    _write_json(os.path.join(topic_dir(slug), "modules.json"), data)


def read_cards(slug):
    return _read_json(os.path.join(topic_dir(slug), "cards.json"), [])


def write_cards(slug, data):
    _write_json(os.path.join(topic_dir(slug), "cards.json"), data)


# Every topic starts with these two, so "read materials.md and progress.md
# first, update progress.md last" holds for a topic made today, not only for
# the ones someone wrote them for by hand. /start reads the Study plan, Next and
# Log sections by name, so keep those headings.
MATERIALS_TEMPLATE = """# %(title)s: materials

The reference for this topic: what you're aiming at, how you'll be tested or
use it, the dates that matter, and every resource handed over while studying.
Where you are and how well you know it lives in `progress.md`.

## The goal

Filled in by `/interview`: the real goal, not the first one stated.

## How you'll be tested

The format to mirror in practice. An exam (length, question types, open or
closed book), an interview, a conversation, a real task. Practice that doesn't
resemble the test is practice at something else.

## Dates

| Date | What | Notes |
|---|---|---|

## Sources

Syllabus, textbook (with edition), course pages, job description, exam
blueprint: whatever defines what's covered. Files go in `resources/`.

## Resources log

Newest first: every resource handed over while studying, with the date.
"""

PROGRESS_TEMPLATE = """# %(title)s: progress

Where you are and how well you actually know each part. Facts about the goal
and the dates live in `materials.md`.

**How this file is kept**

- Updated at the end of every session that changes what's known: a level
  reached, a score reported, the material moving on.
- A level goes in only with its evidence: an `/examine` result or a real score
  you report. Nothing guessed, nothing "probably fine".
- What redo is owed is the gate's job, not this file's:
  `python3 engine/gate.py status %(slug)s`.

**Levels** use the same ladder as `/examine`. The level is the highest rung
reached before guessing started.

| | Can you... |
|---|---|
| L1 | recall the definition |
| L2 | apply it to a clean textbook case |
| L3 | apply it to a messy or unfamiliar case |
| L4 | compare it to a competing idea, or find where it breaks |
| L5 | use it to explain something you've never seen |
| - | not assessed yet |

## Now

Not started. `/interview` records the goal, `/map` builds the modules.

## Study plan

How often you study and for how long (e.g. 3 sessions a week, about an hour
each). The session-by-session plan, with a When window per session, is in
`curriculum.md`.

## Scores

Real results only, with dates: quizzes, mock exams, `/examine` levels.

## Board

| Module | Level | Evidence |
|---|---|---|

## Next

1. `/interview` if it hasn't run, then `/map`.

## Log

Newest first. Each entry names the plan session it was ("session 3") and the
modules or chunk covered. That's how `/start` tells where the queue is.
"""


def create_topic(title, strictness="enforced", goal="", level="", exam_format="", deadline=""):
    slug = slugify(title)
    d = topic_dir(slug)
    if os.path.isdir(d):
        raise SystemExit("topic already exists: %s" % slug)
    os.makedirs(os.path.join(d, "sessions"), exist_ok=True)
    write_topic(slug, {
        "slug": slug,
        "title": title,
        "created": today(),
        "strictness": strictness,
        "struggle_minutes": 10,
        "goal": goal,
        "level": level,
        "exam_format": exam_format,
        "deadline": deadline,
        "interviewed": False,
        "mapped": False,
    })
    write_modules(slug, {})
    write_cards(slug, [])
    with open(os.path.join(d, "curriculum.md"), "w", encoding="utf-8") as fh:
        fh.write("# %s\n\nNot mapped yet. Run `/map %s`.\n" % (title, slug))
    for name, template in (("materials.md", MATERIALS_TEMPLATE),
                           ("progress.md", PROGRESS_TEMPLATE)):
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(template % {"title": title, "slug": slug})
    return slug


# ---------------------------------------------------------------- modules

def set_module(slug, mid, **fields):
    mods = read_modules(slug)
    m = mods.setdefault(mid, {
        "id": mid,
        "title": mid,
        "depends_on": [],
        "status": "untouched",
        "attempts": 0,
        "last_score": None,
        "explained_at": None,
        "unaided_pass_at": None,
        "notes": "",
    })
    m.update(fields)
    if m["status"] not in STATUSES:
        raise SystemExit("bad status %r (want one of %s)" % (m["status"], ", ".join(STATUSES)))
    mods[mid] = m
    write_modules(slug, mods)
    return m


def get_module(slug, mid):
    mods = read_modules(slug)
    if mid not in mods:
        raise SystemExit("no module %r in %s (have: %s)" % (mid, slug, ", ".join(mods) or "none"))
    return mods[mid]


# ---------------------------------------------------------------- sessions

META_RE = re.compile(r"<!--meta\s*(\{.*?\})\s*-->", re.S)


def log_session(slug, role, body, module=None, score=None, misses=None,
                override=False, override_reason="", at=None):
    """Write one session file and return its path.

    `body` is markdown a human will actually read later. The meta block is what
    the diagnostician and the dashboard parse. `at` (an ISO timestamp) is for
    tools that write a fixed history, like tools/make_demo.py; sessions logged
    from the CLI always take the current time.
    """
    if role not in ROLES:
        raise SystemExit("unknown role %r (want one of %s)" % (role, ", ".join(ROLES)))
    # A mistyped slug would otherwise make a stray topic folder and file the
    # session where nothing reads it.
    read_topic(slug)
    d = os.path.join(topic_dir(slug), "sessions")
    os.makedirs(d, exist_ok=True)
    when = datetime.datetime.fromisoformat(at) if at else datetime.datetime.now()
    stamp = when.strftime("%Y-%m-%d-%H%M%S")
    name = "%s-%s%s" % (stamp, role, "-" + module if module else "")
    path = os.path.join(d, name + ".md")
    # Names go to the second, so two sessions logged in the same second would
    # share one. Never overwrite the audit trail: number the later one.
    n = 2
    while os.path.exists(path):
        path = os.path.join(d, "%s-%d.md" % (name, n))
        n += 1
    meta = {
        "at": when.replace(microsecond=0).isoformat(),
        "role": role,
        "module": module,
        "score": score,
        "misses": misses or [],
        "override": bool(override),
        "override_reason": override_reason,
    }
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("<!--meta\n%s\n-->\n\n" % json.dumps(meta, indent=2, ensure_ascii=False))
        fh.write(body.rstrip() + "\n")
    if module and role not in LOOKBACK_ROLES:
        m = read_modules(slug).get(module)
        if m is not None:
            set_module(slug, module, attempts=m.get("attempts", 0) + 1)
    return path


def read_sessions(slug, role=None, module=None, limit=None):
    """Newest first."""
    d = os.path.join(topic_dir(slug), "sessions")
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d), reverse=True):
        if not name.endswith(".md"):
            continue
        path = os.path.join(d, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        m = META_RE.search(text)
        if not m:
            continue
        try:
            meta = json.loads(m.group(1))
        except ValueError:
            continue
        if role and meta.get("role") != role:
            continue
        if module and meta.get("module") != module:
            continue
        meta["path"] = path
        meta["file"] = name
        meta["body"] = META_RE.sub("", text, count=1).strip()
        out.append(meta)
        if limit and len(out) >= limit:
            break
    return out


# Headings under which a session records what went wrong. The roles write
# "Gaps found", "Wrong", "Missed", "Hard", "Weak", "Held, but shaky"; a
# diagnose session writes "Root". Matched as substrings, case-insensitive.
GAP_WORDS = ("gap", "wrong", "miss", "hard", "shaky", "weak", "dropped",
             "watch", "not passed", "mistake", "error", "confus", "root")

# Headings under which a session records what held up: "Right", "Held up
# under questioning", "Good". A heading that also names a gap ("Held, but
# shaky") counts as a gap, not as held.
HELD_WORDS = ("right", "held", "good", "solid", "correct")

_HEADING_RE = re.compile(r"^#{2,3}\s+(.+?)\s*$")
_EMPTY_RE = re.compile(r"^(none|nothing|n/a)\b", re.I)
_BULLET_RE = re.compile(r"^([-*]|\d+[.)])\s+")


def _is_gap(low):
    return any(w in low for w in GAP_WORDS)


def _is_held(low):
    return not _is_gap(low) and any(w in low for w in HELD_WORDS)


def gap_sections(body):
    """{heading: [item, ...]} for every section of a session body whose
    heading names a gap. One item per bullet: a bullet wrapped over several
    lines comes back as one item. A section that only says "None." is left
    out."""
    return _sections(body, _is_gap)


def held_sections(body):
    """The same, for the sections that record what held up."""
    return _sections(body, _is_held)


def _sections(body, pick):
    out, current, prev_blank = {}, None, True
    for line in body.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            low = m.group(1).lower()
            current = m.group(1) if pick(low) else None
            prev_blank = True
            continue
        if current is None:
            continue
        text = line.strip()
        if not text:
            prev_blank = True
            continue
        bullet = _BULLET_RE.match(text)
        items = out.get(current)
        if not bullet and not prev_blank and items:
            items[-1] += " " + text          # continuation of the item above
        else:
            text = text[bullet.end():].strip() if bullet else text
            if not _EMPTY_RE.match(text):
                out.setdefault(current, []).append(text)
        prev_blank = False
    return out
