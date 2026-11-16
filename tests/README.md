# tests/

`test_gate.py` is the only suite. It drives the real CLI in a subprocess against
a throwaway root (`STUDY_ENGINE_ROOT`), so it tests the thing the skills
actually call rather than a reimplementation of it.

```bash
python3 tests/test_gate.py     # 51 checks
```

Most checks are negative tests: they put the engine in a state the gate is meant
to refuse and assert exit 1. Three checks then **disarm** the guarded condition
and assert the same call flips to allow, which is what separates a real check
from one passing for an unrelated reason. The last few cover what the public
kit depends on: new-topic templates, a dashboard without the news module, and
the sample-data demo.

## Proving a change

All four gate branches have been watched to fail. Replaying it:

```bash
cp engine/gate.py /tmp/gate.orig

# Disarm the struggle timer: 'if mins < need:' -> 'if False:'
# Expect: exit 1, "blocks help before the struggle minutes elapse" fails.

# Disarm the redo gate: the status check in cmd_check_help -> 'if False:'
# Expect: exit 1, "blocks a second explanation while a redo is owed" fails.

# Disarm the sitting limit: 'if mins > CLOCK_EXPIRES_HOURS * 60:' -> 'if False:'
# Expect: exit 1, "blocks help on a struggle clock from an earlier sitting"
# and "blocks help once the clock is past the sitting limit" fail. Watched
# 2026-10-14: the unfixed gate answered "struggled 1500 minutes; help
# unlocked" for a 25-hour-old clock.

# Mark a chunk redo passed: in cmd_redo_pass, the --chunk branch's
# status="attempting" -> status="unaided_pass".
# Expect: exit 1, "a chunk redo does not mark the module passed" fails.
# Watched 2026-10-15.

cp /tmp/gate.orig engine/gate.py   # and confirm 51/51 again
```

The kit checks, watched 2026-11-15 (back up and restore the file the same way):

```bash
# engine/store.py, create_topic: the template write -> 'pass' (files left empty).
# Expect: "a new topic starts with materials.md and progress.md" fails.

# engine/build_view.py: 'except ImportError: news = None' -> 'raise'.
# Expect: "dashboard builds without the news module" fails.

# engine/build_view.py, overview_html: the demo_note's 'if demo else ""' -> 'if False else ""'.
# Expect: "demo is labelled sample data and leaves the real dashboard alone" fails.

# engine/build_view.py, main: the demo out_path -> OUT.
# Expect: the same check fails: the demo overwrote the real dashboard.

# engine/build_view.py, overview_html: 'overrides = sum(...)' -> 'overrides = 0'.
# Expect: "dashboard reports the override count" fails.

# engine/store.py, log_session: 'read_topic(slug)' -> 'pass'.
# Expect: "log refuses a topic that doesn't exist and makes no folder" fails.
# Watched 2026-11-16: the unguarded log answered
# {"logged": "topics/loose-topik/sessions/...-review.md"} for a typo'd slug.
```

The diagnose checks, watched 2026-11-15:

```bash
# engine/store.py: drop "diagnose" from ROLES.
# Expect: "diagnose is a role the log accepts" fails.

# engine/store.py, gap_sections: every heading counts as a gap
# ('current = heading'), or "None." kept (drop the _EMPTY_RE test).
# Expect: "corpus cites only sessions that recorded a gap..." fails.

# engine/study.py, topic_corpus: the weak-card filter -> 'if True:'.
# Expect: "corpus lists the lapsed card and leaves out the clean one" fails.

# engine/study.py, topic_corpus: add store.write_cards(slug, store.read_cards(slug)).
# Expect: "corpus writes nothing" fails (same bytes, new mtime).

# engine/study.py: 'total < THIN_CORPUS' -> '<=', then THIN_CORPUS = 19.
# Expect: "20 sessions is not", then "19 sessions is flagged...", fails.

# engine/store.py, _sections: the continuation join -> 'if False:'.
# Expect: "corpus cites only sessions..." fails (a wrapped bullet splits).

# engine/store.py, _is_held -> 'return False', or study.py 'elif held:' -> 'elif False:'.
# Expect: "corpus carries what held..." and "the text corpus lists..." fail.

# engine/study.py, corpus_text: the gap line -> 'pass'.
# Expect: "the text corpus lists the gap and what held, by file" fails.

# engine/store.py, log_session: 'if module and role not in LOOKBACK_ROLES:' -> 'if module:'.
# Expect: "a diagnosis does not count as an attempt on its module" fails.

# engine/build_view.py, current_module: drop the LOOKBACK_ROLES test.
# Expect: 'a diagnosis does not move "You're on"' fails. Both found by a
# simulated /diagnose run, 15 Nov: the dashboard jumped back to Chapter 11.

# engine/store.py, log_session: 'while os.path.exists(path):' -> 'while False:'.
# Expect: both thin checks fail with sessions_total 2: same-second logs
# overwrote each other. This is how that bug was found.
```

The spar checks, watched 2026-11-15:

```bash
# engine/store.py: drop "spar" from ROLES.
# Expect: "spar is a role the log accepts" fails.

# engine/store.py: LOOKBACK_ROLES = ("diagnose",), dropping "spar".
# Expect: "a spar does not count as an attempt on its module" fails. Found
# by a simulated /spar, 15 Nov: a Ch 6 spar moved "You're on" back to Ch 6.

# engine/store.py, log_session, before 'return path': plant
#   if role == 'spar' and module and (score or 0) >= 1:
#       set_module(slug, module, status='unaided_pass')
# Expect: "a perfect spar does not clear the redo it owes" fails.

# engine/study.py, cmd_clock: 'elapsed >= limit' -> 'elapsed > limit'.
# Expect: "the spar clock stops at the limit, not after it" fails.

# engine/study.py, cmd_clock: 'elapsed >= limit' -> 'elapsed >= limit - 1'.
# Expect: "the spar clock runs until the limit" fails.

# Also rewatched: build_view.py current_module without the LOOKBACK_ROLES
# test still fails 'a diagnosis does not move "You're on"'. The SPAR block
# runs before DIAGNOSE so the diagnosis stays the newest session; a spar
# logged after it would make that check pass with its fix removed.
```

All four kit checks rewatched 2026-11-15 after the Chunky redesign moved the news into
`news.panel()` and rebuilt the page.

Do this for any new check before trusting it. An assertion nobody has watched
fail is not coverage, it reads as coverage, which is worse than none.

## Traps on this machine

- macOS has no `timeout`. Every subprocess call here passes `timeout=30` and a
  timeout is reported as **inconclusive**, never as a pass.
- The shell is zsh: `${PIPESTATUS[0]}` is empty. Read `$?` directly, or
  `$pipestatus[1]`, or do not pipe.
