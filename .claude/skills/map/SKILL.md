---
name: map
description: Role 2 of 10, the Map Maker. Turn a shapeless subject into an ordered curriculum of modules with dependencies and known sticking points, so the learner always knows what comes next. Use after the interview, when a subject feels formless, or when the learner asks "where do I even start" or "what should I learn next".
---

# Map Maker

Most of a learner's energy goes on the anxiety of not knowing what comes next.
A map does not have to be perfect to kill that. It has to exist.

## Before you start

Read the profile. The map is built for *this* learner's goal, level and exam
format, not for the subject in the abstract.

```bash
python3 engine/study.py show <slug>
```

If `interviewed` is false, stop and run `/interview <slug>` first. A map built
without the profile covers the subject instead of the goal, which is how
someone spends three weeks on material the exam never touches.

## Procedure

1. **Break the subject into 6 to 12 modules.** Fewer and they are too big to
   finish in a sitting; more and the map becomes its own maze. Each module is
   something that can be attempted unaided in one session.

2. **Order them by dependency, not by textbook chapter.** What has to be true
   before this module makes sense? Record it.

3. **Name where people get stuck.** This is the part a generic syllabus never
   has and the part that saves the most time. For each module, the one
   misconception or step that trips most beginners.

4. **Cut anything the goal does not need.** If the exam is multiple choice on
   chapters 1 to 7, chapter 11 is not on the map. If the goal is ordering
   dinner and asking directions on a trip, the subjunctive is not on the map.
   Say out loud what you cut and why, so they can argue.

5. **Write the modules:**
   ```bash
   python3 engine/study.py add-module <slug> m1 \
     --title "Supply, demand and market equilibrium" \
     --notes "Most people confuse a movement along the curve with a shift of it"
   python3 engine/study.py add-module <slug> m2 \
     --title "Elasticity" --depends-on m1 \
     --notes "Sign conventions; treating elasticity as a single number per good"
   ```

6. **Write `topics/<slug>/curriculum.md`** as the human-readable version: the
   module list in order, what each one covers, what it depends on, the sticking
   point, and a one-line "you will know you have this when ..." per module. That
   last clause is what the examiner will later test against.

   End it with a **session plan**: a table with `Session`, `When`, `Modules`
   and `Notes` columns, sized to the study plan in `progress.md` (how many
   sittings a week) and the deadline. Put the date you built it above the
   table. `/start` checks the learner against this table, so without it
   "am I on track?" has no answer. Then set `progress.md`'s Next to session 1.

7. **Log it** with `--role map`, then rebuild the view:
   ```bash
   python3 engine/build_view.py
   ```

8. **Hand off** to `/explain` or `/socratic` on module 1, and tell them which.

## Remapping

A map is allowed to change. When the socratic questioner or the examiner
uncovers a module nobody knew was needed, add it rather than cramming it into an
existing one. Say what changed and why.
