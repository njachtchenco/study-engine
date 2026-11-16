# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Study Engine

A study system built on one claim: **learning is production, not consumption.**
Reading, watching and being explained to feel like learning and mostly are not.
Memory encoding happens when you actively recall, predict, explain or attempt.

The evidence this is built on:

| Method | Recall at 5 min | Recall at 1 week |
|---|---|---|
| Reread the source 4x | 83% | 40% |
| Read once, self-test 3x | 71% | 61% |

Rereading wins the short test and loses the week. The thing that feels most like
learning decays fastest. Everything in this repo exists to keep the learner on
the second row.

Source: Nick Saraev, "How I Learn Complex Skills & Difficult Subjects So Fast
with AI" (3 Oct 2026). Ten roles AI can play; most people only ever use the one
that is pure consumption. The table is Roediger and Karpicke, "Test-Enhanced
Learning", *Psychological Science* 17(3), 2006, Experiment 2 (checked against
the paper 15 Nov 2026); the self-testers read the passage 3.4 times on
average, the rereaders 14.2.

The subject can be anything: a class, a language, a certification, interview
prep, a skill for work. The interview turns it into a goal and a test format,
and everything downstream mirrors that format.

## The roles

Nine are built. Two are designed and not yet written (see "Not built yet").

| Skill | Role | Gives answers? |
|---|---|---|
| `/interview` | Finds the real goal, the level, the test format | no, asks only |
| `/map` | Shapeless subject to an ordered curriculum | no |
| `/explain` | The one everybody uses. **Gated.** | yes, and it owes a redo |
| `/socratic` | Questions until the learner finds their own gap | **never** |
| `/examine` | Escalating quiz, stops at the edge, reports the level | after the fact |
| `/clerk` | Their notes to an outline and cards, adds nothing | no |
| `/review` | The spaced-repetition session | reveals after the attempt |
| `/diagnose` | Finds the one root misunderstanding behind many misses, cites it, tests it | **never**, names the gap only |
| `/spar` | Timed live run of the real test in its format, hard stop, optional hostile mode | after time is up |

The roles are a **loop, not a sequence**: socratic finds a gap, explain fills
it, map adds the module nobody knew was needed, back to socratic.

`/start <topic>` opens a sitting: what the last session did, whether the
study plan is on track, and the first thing to do. It isn't a role. It reads
the state and writes nothing, so the role it hands off to does the logging.
`/dashboard` rebuilds the view and opens it.

## The gate — the part that makes this a codebase

Two mechanics a human will always skip, so they are enforced in code:

1. **Help unlocks only after a real unaided attempt** (default 10 minutes,
   set per topic), **in the same sitting.** A struggle clock older than 3
   hours doesn't count, so yesterday's attempt can't unlock today's
   explanation; `gate.py attempt` starts a fresh one.
2. **Every explanation owes a from-scratch redo**, and no new module starts
   until that redo passes unaided.

`engine/gate.py` is authoritative. Skills run it and obey the exit code: 0
allow, 1 block. An override is always available, always needs a reason, and is
always written to the session log, so the count shows up on the dashboard.

```bash
python3 engine/gate.py attempt <topic> <module>        # start the struggle clock
python3 engine/gate.py check-help <topic> <module>     # may /explain run?
python3 engine/gate.py explained <topic> <module>      # help given -> redo owed
python3 engine/gate.py redo-pass <topic> <module>      # redo passed unaided
python3 engine/gate.py redo-pass <topic> <module> --chunk  # ...one chunk of several
python3 engine/gate.py check-advance <topic> <module>  # may a new module start?
python3 engine/gate.py override <topic> <module> --action ... --reason ...
python3 engine/gate.py status <topic>
```

**What the gate cannot do:** it is enforced by the skills choosing to run it,
not by the harness. A session that ignores `check-help` will not be stopped.
The state it writes is real, so the dashboard and `/diagnose` still see the
shortcut, but the block itself is a convention. A `PreToolUse` hook would make
it hard; that is deliberately not built yet.

## Quick commands

Every command runs from the repo root, the folder that holds `engine/`. The
skills use paths relative to it; if the shell has moved somewhere else, `cd`
back to the root first.

```bash
python3 engine/study.py topics                  # every topic and its progress
python3 engine/study.py show <topic>            # one topic in full
python3 engine/study.py due                     # cards due, all topics
python3 engine/study.py due <topic>             # the cards themselves
python3 engine/study.py grade <topic> c003 good # again | hard | good | easy
python3 engine/study.py corpus <topic> --text   # every miss, gap, hold, weak card (/diagnose)
python3 engine/study.py clock --start <epoch> --minutes 10  # /spar's clock, exit 1 at time
python3 engine/gate.py status <topic>           # what is owed

python3 engine/build_view.py                    # rebuild view/dashboard.html
python3 engine/build_view.py --demo             # the sample topic, to view/demo.html
open view/dashboard.html                        # look at it
```

```bash
python3 tests/test_gate.py                      # the whole suite (49 checks), ~seconds
python3 engine/study.py log <topic> --role socratic --module m02 \
    --score ... --misses '[{"q":"...","a":"..."}]' --body-file -   # write a session file
```

Run `python3 engine/study.py <command> --help` for any one command. Rebuild the
view at the end of any session that changed state; it is gitignored and
regenerates in well under a second.

## Code notes

- **Standard library only, Python 3.9** (the system `python3`). No
  `requirements.txt`, nothing to install. Don't use 3.10+ syntax (`match`,
  `X | Y` type unions).
- `engine/store.py` is the only module that touches `topics/`. `gate.py`,
  `scheduler.py`, `study.py` and `build_view.py` all go through it. Setting
  `STUDY_ENGINE_ROOT` re-roots the whole engine, which is how the tests run the
  real CLI against a throwaway directory; `store.set_root()` does the same
  inside one process (how `--demo` renders `examples/demo`).
- `tests/test_gate.py` is one script, not pytest: there is no single-test
  selector. Add a check to it, then follow the disarm-and-watch-it-fail
  procedure in `tests/README.md` before trusting the check. Its check count
  appears in this file, `README.md` and `tests/README.md`; keep them in step.
- `study.py log` increments the module's `attempts` counter as a side effect,
  so logging the same sitting twice inflates it. Session file names go to
  the second; a second session logged in the same second gets a `-2` suffix
  rather than overwriting the first. Roles in `LOOKBACK_ROLES` (`diagnose`, `spar`)
  log against a module without counting as an attempt on it or moving the
  dashboard's "You're on" line. The role list (`ROLES` in
  `store.py`) is a closed set: a new skill needs an entry there before it can
  log.
- Skills live in `.claude/skills/<name>/SKILL.md`, one per role plus
  `/start` and `/dashboard`. They are prose procedures that shell out to the
  engine; the rules in "Rules for any session working in here" are enforced by
  what the SKILL.md says, so change role behaviour there, not in `engine/`.
- `build_view.py` imports `engine/news.py` only if it exists and asks it for
  one thing, `news.panel()`. A copy without it has no News tab, and `--news` /
  `--news-if-stale` do nothing.
- The dashboard's font is Nunito, read from `engine/fonts/` and embedded in the
  page as base64, so the page stays one offline file. It is under the SIL Open
  Font License (`engine/fonts/OFL.txt`, which ships with it). Without the font
  file the page falls back to the system's rounded font.
- Spark, the dashboard's mascot, only says things computed from `topics/`
  (`spark_state` in `build_view.py`). Never give it a line the data can't back.
- `lite/` is the no-install version for a claude.ai Project:
  `instructions.md` is every role cut down to prose, with the gate on the
  honour system, and `setup.html` is its setup page, carrying the same text.
  It is a hand-written mirror of the skills, so a change to a role's rules
  belongs in both.
- `examples/demo/` is a made-up topic, marked `"demo": true` in its
  `topic.json`, so the dashboard labels it as sample data. It is never read
  unless `--demo` is passed.

## Where state lives

```
topics/<slug>/
  topic.json       profile from /interview: goal, level, exam format, deadline,
                   strictness, struggle_minutes
  curriculum.md    the human-readable map, ending in the session plan
  materials.md     facts about the course or goal: how it's tested, dates,
                   sources, and a log of every resource handed over
  progress.md      where the learner is: real scores, level per module with
                   its evidence, the study plan, Next, a dated log
  resources/       source files (syllabus PDF, handouts) that materials.md indexes
  modules.json     per-module status. The gate reads this.
  cards.json       the spaced-repetition deck (SM-2)
  attempts.json    open struggle clocks (gate bookkeeping)
  sessions/*.md    one file per session. Markdown body a human reads, JSON meta
                   in an HTML comment that the engine parses. The audit trail.
  notes/*.md       raw notes the clerk organized
```

`study.py new` creates the topic with `materials.md` and `progress.md`
templates; `/interview` fills them in.

Module statuses, in order: `untouched`, `attempting`, `explained`, `redo_due`,
`unaided_pass`. The gate cares about `explained` and `redo_due`: both mean an
answer was handed over and not yet reproduced unaided.

**All writes go through `engine/study.py` or `engine/gate.py`.** Do not
hand-edit the JSON. `curriculum.md`, `materials.md`, `progress.md` and
`notes/*.md` are the exception; they are prose and are written directly.

## Rules for any session working in here

- **Never give an answer in a role that does not give answers.** `/socratic`
  giving an answer is not a small style slip, it voids the session: the learner
  stops producing the moment the answer arrives.
- **Never fabricate a grade, a score or a source.** If you cannot verify their
  answer, say so instead of grading it. A confident wrong grade calibrates them
  wrong for the real test, and sycophancy on a half-right answer is one of the
  four named failure modes in the source material.
- **A miss becomes a card, in the same session.** `misses-to-cards` exists so
  the gap comes back. A gap found and not carded will be found again.
- **A repeatedly failing card is not a card problem.** It is a module problem.
  Send it to `/socratic`, do not schedule the misunderstanding.
- **Log every session.** `/diagnose` is unimplementable without the history,
  and it is the role with the highest payoff.
- **Read `materials.md` and `progress.md` first, update `progress.md` last**,
  on every topic (both are created with it). The goal and the test format
  answer half the interview and set the format to mirror. Any session that
  changed what is known (a level reached, a score reported, the material
  moving on) ends by updating `progress.md`. A level goes in only with its
  evidence, the same as a grade. Its Log entry names the plan session it
  was ("session 3") and the chunk or modules covered. That's how `/start`
  tells where the queue is.
- **Match the exam format.** Practice that does not resemble the test is
  practice at something else. With no exam, the test is the situation the
  learner will use it in.
- **Prove a guard before trusting it.** `tests/test_gate.py` plants the defect
  each check is supposed to catch and asserts it goes red. Run it after any
  change to `gate.py` or `scheduler.py`.

## Grading

Applies to every role that grades: `/review`, `/examine`, the redo check.

- **Answers often come through voice transcription.** If a single word flips
  the meaning (elastic/inelastic, increase/decrease), ask whether it's a
  transcription error before marking it wrong.
- **Grade only against what the card actually asks.** Don't deduct for leaving
  out reasoning the question didn't request.
- **During `/examine`, give no feedback mid-exam**, including confirming
  answers. Right or wrong, the next thing said is the next question.
- **The textbook edition may differ from the class edition.** Check before
  citing section numbers or titles.

## Study / Review

### Flashcard grading rules

Mirrored in `.claude/skills/review/SKILL.md`; change both together.

- Grade only against what the card's question actually asks. Missing extra
  details (dates, links to other topics) are not gaps.
- Never serve cards on material not yet taught. Skip them and flag them.
- Load all due cards in one call, never one at a time.
- Review only the topic(s) the user names. Don't add other topics.

## Not built yet

Designed, data model already supports them, deliberately out of v1:

- **Checker** (role 6) - grades the *process* not the answer, and finds the
  shorter route, so next time the method is faster. Needs an artifact to grade.
- **Listener** (role 7) - explain it back across three channels (spoken, drawn,
  written) and grade all three against the source. Needs voice and image input.
- Also pending: the per-topic multi-level explanation check (child / beginner /
  expert), and resource curation (find the best human-written explanation for
  this learner's exact profile).

## The case against all of this

Kept here on purpose, because it should shape every change:

- **Learning happens in the struggle.** The hump of squinting at the screen
  *is* the encoding. AI lets you skip the hump, and skipping it means
  remembering nothing. The gate exists only because of this.
- **Explanation feels like understanding and is not.**
- **The GPS result.** People who navigate by app have measurably weaker mental
  maps of their own cities. Offload the thinking, weaken the faculty.
- **Sycophancy and fabrication** turn a learning session into note collecting.

Any feature that makes it easier to get an answer and harder to produce one is a
regression, however convenient it feels.
