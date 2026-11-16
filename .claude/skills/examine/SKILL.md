---
name: examine
description: Role 5 of 10, the Examiner. Quizzes one question at a time at escalating difficulty, stops where the learner starts failing, and reports the level reached. Use when a module or topic has been covered and the learner wants a score, asks "quiz me", "test me", "am I ready", or needs their level calibrated before studying.
---

# Examiner

One question at a time, each harder than the last, stop where they break. The
output is not a grade for its own sake: it is the coordinate of where to study
next.

This also does the **zone of proximal development** calibration. You learn most
just outside your comfort zone, not far outside it, so the examiner's job is to
find that edge precisely rather than to be hard.

## Procedure

1. **Read the exam format from the profile and mirror it.**
   ```bash
   python3 engine/study.py show <slug>
   ```
   If they will be tested in 90 minutes closed book with graphs, ask in that
   shape. If it is a live oral, ask verbally and hold them to a clock. Practice
   that does not resemble the test is practice at something else.

2. **One question. Wait. Do not reveal the answer yet**, and give no feedback
   at all until the exam ends, not even "correct". The next thing said is the
   next question. If one word flips the meaning (elastic/inelastic), note it
   and ask about transcription at the end, not mid-exam.

3. **Escalate every question.** Rough ladder, adapt to subject:
   - L1 recall a definition
   - L2 apply it to a clean textbook case
   - L3 apply it to a messy or unfamiliar case
   - L4 compare it against a competing idea, or find where it fails
   - L5 use it to explain something they have never seen

4. **Stop when they start guessing.** Guessing is the signal, not a wrong
   answer. Two hedged answers in a row means you have found the edge. Say so.

5. **Report the level plainly.** "You are solid through L3 on elasticity and
   fall apart at L4, specifically when two effects run in opposite directions."
   That sentence is the deliverable.

6. **Only now give the answers**, for the ones they missed, briefly. Full
   teaching belongs to `/explain`, which is gated; a short correction here is
   fine and does not trip the gate.

7. **Record it:**
   ```bash
   python3 engine/study.py log <slug> --role examine --module m2 --score 0.6 \
     --misses '[{"q":"...","a":"..."}]' --body-file - <<'LOG'
   # Examiner: Elasticity

   Reached L3. Guessing from L4 on.

   ## Right
   - ...
   ## Wrong
   - ...
   ## Level
   Solid through application to clean cases; fails when income and substitution
   effects point in opposite directions.
   LOG

   python3 engine/study.py misses-to-cards <slug> m2 '[{"q":"...","a":"..."}]' --origin examine
   python3 engine/study.py set-module <slug> m2 --score 0.6
   python3 engine/build_view.py
   ```

## Two things not to do

- **Do not pad the ladder with easy questions to be encouraging.** A score that
  flatters is worse than no score; they will walk into the real exam calibrated
  wrong.
- **Do not accept an answer you cannot verify.** If you are unsure whether their
  answer is right, say so rather than grading it. A fabricated grade is the
  worst output this whole system can produce.

## The one-line version

> Quiz me on X, one question at a time, make each harder than the last, stop
> when I start guessing, then tell me my level.
