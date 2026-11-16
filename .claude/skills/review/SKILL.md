---
name: review
description: The spaced-repetition review session. Runs the cards that are due today in the topic(s) the learner names (every topic only if none is named), grades recall, reschedules on the forgetting curve, and turns fresh misses into new cards. Use daily, or when the learner says "review", "what's due", "run my cards", "quiz me on everything".
---

# Review

This is the one that compounds. Each successful review both flattens the decay
curve and raises the floor, which is why a few minutes a day beats a weekend of
rereading. It is also the only skill meant to be run on a schedule rather than
when something comes up.

## Flashcard grading rules

Mirrored from "Study / Review" in the repo's `CLAUDE.md`; change both together.

- Grade only against what the card's question actually asks. Missing extra
  details (dates, links to other topics) are not gaps.
- Never serve cards on material not yet taught. Skip them and flag them.
- Load all due cards in one call, never one at a time.
- Review only the topic(s) the user names. Don't add other topics.

## Procedure

1. **What is due** (only in the topic(s) the learner named, if they named
   any; every topic only when they didn't):
   ```bash
   python3 engine/study.py due
   ```
   Then per topic, which gives you the cards themselves:
   ```bash
   python3 engine/study.py due <slug>
   ```
   **Load the whole deck once, answers included, and read from it for the
   rest of the session.** Never fetch cards one call at a time: a five-card
   review took six calls that one call would have covered. Trim the output so
   it stays small:
   ```bash
   python3 engine/study.py due <slug> | python3 -c "
   import json,sys
   for c in json.load(sys.stdin)['cards']:
       print(c['id'], '|', c['q'], '|', c['a'])"
   ```
   Having the answers in context is not showing them. Say nothing from the
   answer until the learner has attempted that card (step 2 and 3 still hold).

   Before asking anything, drop cards on material not covered yet (the class
   hasn't reached it, or the learner hasn't studied it; check the topic's
   `progress.md`). Don't serve them; list them at the end so the learner
   knows they're waiting.

2. **Ask the question. Nothing else.** Do not show the answer, do not hint, do
   not show the module name if it narrows it. Recall under a blank screen is the
   entire exercise.

3. **Wait for their attempt, then show the answer and ask them to grade
   themselves** against it:

   | Grade | Means |
   |---|---|
   | `again` | Did not recall it |
   | `hard` | Got there with real effort |
   | `good` | Recalled it |
   | `easy` | Instant |

   Three real levels plus instant, on purpose. People given six levels lie.

4. **Record each one as you go,** not at the end. A session that dies halfway
   should keep the reviews it did.
   ```bash
   python3 engine/study.py grade <slug> c003 good
   ```

5. **A miss is not just a lapse, it is a finding.** When they fail a card, ask
   one follow-up: do they not know the fact, or not understand the thing behind
   it? If it is the thing behind it, say which module it belongs to and tell
   them to run `/socratic <slug> <module>`. Carding a misunderstanding just
   schedules the misunderstanding.

6. **Close the session:**
   ```bash
   python3 engine/study.py log <slug> --role review --body-file - <<'LOG'
   # Review

   14 due, 11 recalled, 3 missed.

   ## Missed
   - c007 price ceilings: recited the definition, could not predict the effect.
     Not a card problem, a m1 problem. Sent to socratic.
   LOG
   python3 engine/build_view.py
   ```

7. **Report in one line:** how many were due, how many held, what is due
   tomorrow, and anything that should go back to another role.

## When the pile is too big

Do not grind through 80 cards. Do the oldest-due 20 and say plainly that the
rest are waiting. Honest partial review beats a session they abandon and then
avoid for a week.

## What does not belong here

Reviewing is retrieval practice, not learning. If a card is failing repeatedly
it does not need more reviews, it needs `/socratic` or `/explain` on the module
it came from. The dashboard's lapse count is the tell.
