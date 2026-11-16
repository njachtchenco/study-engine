---
name: start
description: Open a study session on one topic - what the last session did, whether you're on track against the study plan, and the one thing to do first. Read-only. Use when the user says /start <topic> (e.g. /start spanish, /start statistics), "start a session", "where did I leave off", "am I on track", or "what do I do first today".
---

# Start

Not a study role. It reads the state the roles leave behind and says, in a
few lines, where the learner is and what to do first. It writes nothing,
logs nothing and starts no clock. The role it hands off to does all of that.

## Procedure

1. **Find the topic.**
   ```bash
   python3 engine/study.py topics
   ```
   Match the argument case-insensitively against each slug and title, by
   whole word or prefix: "stats" and "statistics" both match a topic titled
   "Intro Statistics"; "spanish" matches `spanish-for-travel`. With one topic,
   no argument means that topic. With no argument and several topics, or no
   single match, list the topics by title and ask which. Don't guess. With no
   topics at all, say so and point to `/interview`.

2. **Get today.**
   ```bash
   date "+%A %B %-d, %Y"
   ```
   Every "days out" and "this week" in the answer is counted from this.
   Never copy them from `progress.md`, whose Now section was true on the day
   it was written.

3. **Read the state.** All read-only:
   ```bash
   python3 engine/study.py sessions <slug> --limit 5
   python3 engine/gate.py status <slug>
   python3 engine/study.py due <slug>
   cat topics/<slug>/attempts.json 2>/dev/null
   ```
   Then, from `topics/<slug>/`:
   - `progress.md`: Study plan, Next, and the newest two Log entries.
   - `curriculum.md`: the date it was built, and the session plan (the table
     with a Session column). "This week" in that table means the week the map
     was built.
   - The newest session file in full (open its `path`), for what it
     actually found.
   - `materials.md`: only the dated tables (exams, quizzes, essays,
     interviews, any deadline), for anything graded or due in the next 7
     days. For a topic with a weekly discussion section, also that week's
     primary sources if section is still ahead.

4. **Last session.** Take the newest session file and its Log entry. Give the
   role, module, date and how long ago, then what it found in one or two
   lines: what held, what didn't, what was left open, how many cards it made.
   If the newest is a `/review`, give it half a line and summarize the study
   session before it. If the only sessions are the interview and the map, say
   no study session has run yet.

5. **On track?** Compare where the plan says they should be today with where
   they are.
   - *Should be:* every plan row whose When window ended before today should
     be done. A row whose window includes today is the current window, not
     overdue.
   - *Are:* the plan rows the Log and the session files show done. Log
     entries name the plan session and the chunk. Where one doesn't, match by
     module, counting the study sessions (`socratic`, `explain`, `examine`)
     logged since the map, and say it's an estimate.
   - **Verdict in one line:** on track, ahead by N, or behind by N sessions.
     If behind, show the arithmetic once: sessions left before the next exam
     against plan rows left, and what the study plan allows (a 4th day in a
     week that isn't landing). Don't pad an on-track verdict.
   - A redo owed (`redo_owed` in the gate status) counts as behind whatever
     the dates say. The gate won't let a new module start until it passes.

6. **First thing.** One action, with the command that starts it. Take the
   first of these that applies:
   1. **A redo owed:** the from-scratch redo, unaided. Nothing new can start
      before it passes.
   2. **Something graded within 24 hours** that a session can still help (a
      quiz closing tomorrow morning, an exam tomorrow).
   3. **Cards due:** `/review` first. It takes a few minutes, and the spacing
      only works on the day it asks for. If more than about 15 are due, put
      them after the main work instead and say so.
   4. **The plan's next step:** progress.md's Next item 1, checked against
      the plan's next row. If the row has an "Opens with" (an `/examine` on
      the module just finished), that's the first thing. If Next and the
      plan disagree, follow the plan and say why.

   If the next step is new material, it starts with an unaided attempt and
   the struggle clock: name `python3 engine/gate.py attempt <slug> <module>`,
   don't run it. If `attempts.json` holds a clock for that module that's more
   than 3 hours old, say it has expired and the attempt starts a fresh one.
   The gate won't count an old clock, so skipping the attempt means
   `check-help` refuses later in the session.

   If the next plan row can't be done yet (it needs a lecture, lesson or
   material that isn't available yet), say so and give the first thing that
   can be done now.

   Name an open question as a question. Never answer it, and never preview
   the content. That's the role's job, and an answer here voids the attempt.

7. **Report.** About 12 lines at most, in this shape:

   ```
   **<Topic> · <Weekday Mon D> · <next exam or deadline> in N days**

   **Last session:** ...
   **On track:** ...
   **Start with:** ... `<command>`
   **This week:** ...
   ```

   Leave out "This week" when nothing is due or graded in the next 7 days.
   Then offer to begin. On a yes, invoke the role named in "Start with". That
   role starts the clock, logs the session and updates `progress.md`.

## Rules

- **Read-only.** No `study.py log`, no `gate.py attempt`, no edits to
  `progress.md`. A session that only ran `/start` didn't happen.
- **Report contradictions, don't smooth them over.** If Next names a module
  the gate calls untouched, or a session file has no Log entry, say so in the
  On track line. That's the state telling you a session didn't finish its
  bookkeeping.
- **No em dashes**, and nothing longer than the shape above. The point is to
  get to the first step, not to read about it.
