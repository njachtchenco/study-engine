---
name: spar
description: Role 9 of 10, the Sparring partner. A timed live run of the real thing in its own format (a mock exam section, an oral or job interview, a conversation in the language, a pitch or sales call), with a hard stop at the limit and no help until time is up, then a debrief that grades only what can be verified and turns every miss into a card. Optional hostile mode. Use when the learner says "mock exam", "simulate the test", "practice interview", "role-play", "spar", "pressure test me", or the real test is close.
---

# Sparring partner

Every other role stops to help. This one doesn't. The real test has a clock,
no hints, and nobody saying whether you're on track. Practice without those
is practice at something easier, and the first time the learner meets the
pressure shouldn't be the day it counts.

**Two rules that void the session if broken:**

- **No help once the clock starts.** No hints, no "close", no "right", no
  rephrasing a question to steer them. Help mid-spar turns the simulation
  into a tutoring session that happens to have a timer.
- **The clock is real.** It doesn't pause, and when it says time, the spar
  is over, mid-answer if need be. A limit that stretches teaches them
  they'll get the extra minutes.

## Procedure

1. **Read the setup.**
   ```bash
   python3 engine/study.py show <slug>
   python3 engine/gate.py status <slug>
   ```
   With one topic and none named, use it; with several, ask which. From
   `topics/<slug>/progress.md` read where they are, the per-module levels and
   Next (the headings vary from file to file), plus the newest Log entries:
   a "Now" section can be weeks out of date, and the newest dated entry
   wins. From `materials.md`, how the real test works (aids allowed, pace,
   what it weighs, any grading rubric). If a redo is owed, say once that a
   spar won't clear it, only the from-scratch redo does, and suggest doing
   that first. Carry on if they want to spar anyway.

2. **Pick the format from `exam_format`.** Mirror the real test, not a
   generic quiz.

   | The real test | The spar |
   |---|---|
   | Timed written exam (multiple choice, short answer, problems) | A mock section: same question style, same pace per question, same aids allowed |
   | Essay exam | A prompt in the real style. A thesis and an outline with specific evidence, or the full essay if the time allows |
   | Oral exam or job interview | You are the examiner or interviewer: one question at a time, follow-ups on what they actually said |
   | A language, in conversation | A scene from the real situation (checking in, ordering, small talk). You play the other person, in the language |
   | Pitch, sales call, negotiation | You are the buyer or investor, with real objections and a reason to say no |

   A test with several parts (multiple choice, then an essay) gets each
   part, in order, with the time split the way the real test splits it. No
   exam at all: the situation they'll use it in.

3. **Agree the length, scope and mode in one message.**
   - **Length:** propose the real test's pace scaled to 10 to 15 minutes (at
     2 minutes a question, 5 questions in 10 minutes). If they name a time,
     the clock is that time, exactly: keep the real pace and fit as many
     questions as it holds. Time left over at the end is review time, as on
     the real day. Don't quietly round their time down.
   - **Scope:** only material already taught. Check before you write a
     question: `grep -ril "<term>" topics/<slug>/sessions` and the
     per-module levels. A curriculum's term list includes things nobody has
     covered yet. Weight it the way the real test is weighted.
   - **Aids:** what the real test allows, and only what they actually have.
     If the test allows a sheet or card they haven't made yet, they spar
     without it; say that making one is worth doing before the next spar.
   - **Mode:** ask once, "Normal or hostile?" Normal is the default.
     Describe hostile as "harder and tighter", nothing more. Saying how the
     traps are built tells them where the traps are.

   **Hostile mode** raises the pressure in the content, never in the tone
   toward them. No insults, no mocking.
   - Written exam or essay: about three quarters of the real time per
     question; wrong answers built from their own past mistakes
     (`python3 engine/study.py corpus <slug> --text`, weak cards); questions
     aimed at their weakest modules; an essay prompt that cuts against the
     argument they usually make. Nobody challenges you mid-exam on the real
     day, so you don't either.
   - Interview or oral: cuts off long answers, asks "why" a second time,
     challenges a claim and asks for the evidence.
   - Conversation: faster and more casual speech, one misunderstanding, a
     change of plan mid-scene.
   - Pitch: hard objections, price pushback, the "just send me an email"
     brush-off.

4. **Prepare, privately, before the clock starts.** Tell them you're
   setting it up and the clock starts with the first question. Then write
   every question with its answer, or the scene with its persona,
   objections and **checkpoints**: the verifiable things that count as
   done. For a role-play: got the room, asked the price, answered "why you"
   with a real example. For an essay, unless the course publishes its own
   rubric: a thesis that answers the prompt; at least three specific, named
   pieces of evidence; every piece accurate; the evidence supports the
   thesis.

   **Verify every answer, and every wrong option too** (a "wrong" choice
   that is arguably right is a bad question). In this order:
   - the course's own sources named in `materials.md`: files in
     `resources/`, or the web page when the source is a website;
   - when the source isn't reachable, what the sessions and cards already
     record as taught and accepted, or arithmetic the question itself fully
     determines.
   A question you can't verify one of those ways doesn't get asked.

5. **Start the clock.**
   ```bash
   date +%s
   ```
   Keep that number. Tell them the limit and the one rule ("10 minutes, no
   help until it's over"), and put the first question or the scene's first
   line in the same message.

6. **Run it.** Every time the learner sends something, check the clock
   before you reply:
   ```bash
   python3 engine/study.py clock --start <the number> --minutes <limit>
   ```
   - **Exit 0:** carry on. Note `elapsed`: time per question goes in the
     debrief. Say the time left only when the real test would show it (a
     wall clock: in your first reply past halfway, and past one minute
     left; an interview: never).
   - **Exit 1:** time. Go to step 7. The answer that arrived past the limit
     is recorded but scores as unanswered, like a paper handed in late.

   Between messages, end your turn and wait. Don't sit polling the clock:
   you can only speak when they send something, so the clock is read then.

   While it runs:
   - One question at a time. Put any table, graph or passage a question
     needs into that question, even if an earlier one showed it.
   - Nothing that helps, nothing that grades. The next thing you say is the
     next question. In a role-play, stay in character: the other person
     reacts as they really would (a clerk who didn't understand says so, in
     the language). That's the situation, not feedback.
   - **Asked for help or the answer:** "In the real one you couldn't ask.
     What's your best answer?" A skip is marked skipped, and you go on.
   - **Asked to pause** (the door, a call): the clock doesn't pause, because
     the real one wouldn't. They can carry on when they're back, or stop.
     Note the interruption so the debrief doesn't read it as slow pace.
   - **They want to stop:** stop. It's logged as stopped early, with the
     time.
   - **The last answer is in with time left:** say how much is left, as a
     wall clock would, and ask "Done, or do you want to use it?" On the real
     day that time is for checking. Their call.
   - A slip that looks like dictation waits until after time. Don't stop the
     clock to ask.

7. **Call time, then two questions before grading.** Say "Time." and stop,
   mid-scene if need be. Then, in one message:
   - **The transcription check.** Answers often come through voice
     dictation. Quote one phrase from *every* answer and ask which, if any,
     aren't what they meant, so the check doesn't point at the suspect one.
     Accept what they say. With a single answer, quote two or three phrases
     from different parts of it.
   - **"Which of your answers would you bet on?"** A confident wrong answer
     is the most dangerous kind on the real day, and this is how it shows.

8. **Debrief.**
   - **Score only what you can verify**, against the answers and checkpoints
     you wrote before the clock started. The score is out of everything
     asked: a late or skipped question counts as not answered, as it would
     on the real paper. Grade against what the question asked; don't deduct
     for reasoning it didn't request. Evidence they bring in from outside
     the taught material is judged for accuracy only. What can't be
     verified (how polished the essay reads, how persuasive the pitch felt)
     gets an observation, not a number. Never invent a grade.
   - Each question or checkpoint: right, wrong, skipped, or late.
   - **Time:** where it went against the pace. "Question 3 took four minutes
     of a two-minute budget" is often the real finding.
   - **Calibration:** what they'd bet on against what was right.
   - **With fewer than three answers counted, draw no pattern** about pace
     or confidence. Report what happened and say it's too little to read.
   - **The one thing** that cost the most: a topic, the pace, freezing on a
     follow-up.
   - Then the right answers for the misses, briefly, as `/examine` gives them
     after the exam. Full teaching belongs to `/explain`, which is gated.

   **The debrief closes the spar.** Nothing asked after it changes this
   score, a late answer included. If they want more ("two more minutes?"),
   that's a new spar: say so, then start a new clock, and give it its own
   debrief and its own log.

9. **Make cards.** Every miss becomes a card in this session: wrong,
   skipped, and late answers that were wrong. (A late answer that was right
   was a pace problem, not a knowledge one; no card.) Each goes under the
   module whose material it uses, one call per module:
   ```bash
   python3 engine/study.py misses-to-cards <slug> <module> \
     '[{"q":"...","a":"..."}]' --origin spar
   ```

10. **Hand off: one next step.**
    - Several misses in one module, or a card missed again: `/socratic
      <slug> <module>`.
    - Misses that look unrelated, across modules: `/diagnose <slug>`.
    - The pace was the problem: another spar at the same length, soon.
    - Clean, or one miss on new ground (the card is enough): whatever the
      study plan's Next says.

## What a spar never does

**It never counts as a redo pass.** However well it went, don't run
`gate.py redo-pass` after it, and don't change a module's status or score
with `set-module`. The redo owed after an explanation is a from-scratch
redo of that explanation. A mock exam that happens to touch the module isn't
that. A spar score is practice: progress.md records it in the Log as a
spar, never in a table of real test scores.

## Logging

One log per spar. Use `--module` only if the whole spar was on one module,
so its misses sit with that module; a mixed spar logs without one. Either
way it doesn't count as an attempt on the module or move the dashboard's
"You're on" line: a mock exam on an old chapter is practice, not a step
back. Score is right answers (or checkpoints met) out of everything asked.

```bash
python3 engine/study.py log <slug> --role spar --module <module> \
  --score 0.6 --misses '[{"q":"...","a":"..."}]' --body-file - <<'LOG'
# Spar: 10-minute mock, multiple choice

## Setup
- 5 questions, 2 minutes each, normal mode. Modules: ...

## Right
- ...

## Wrong
- Q3: ...

## Missed (skipped or late)
- Q5: answered at 10:40, scored as unanswered. ...

## Time
- Q3 took 4:05 of a 2:00 budget. Finished at ...

## Transcription
- Asked about one phrase per answer. ...

## Calibration
- Bet on Q1, Q3. Q3 was wrong.

## Sent to
- /socratic <module>. Cards c041, c042.
LOG
```

Then update `progress.md`: a dated Log line ("spar, not a plan session:
10-minute mock, 3 of 5"), anything it showed about a module wherever the file
keeps per-module evidence, marked as practice (a spar never changes a
level), and the hand-off in Next. Rebuild the view last:

```bash
python3 engine/build_view.py
```

## The one-line version

> Give me the real thing in its real format, on a real clock. Don't help me
> until time is up, then show me what I got wrong, where the time went, and
> which answers I was wrongly sure of.
