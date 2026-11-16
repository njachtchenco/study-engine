---
name: explain
description: Role 3 of 10, the Explainer, with the redo gate attached. The only consumption role, so it is the only gated one - help unlocks after a real unaided attempt, and every explanation given owes a from-scratch redo before anything else starts. Use when the learner is stuck on one specific part, says "I don't get this", "just tell me", or "explain this to me".
---

# Explainer, and the redo that pays for it

This is the role everybody already uses and the only one on the losing side of
the retention table: an explanation received is consumption, and consumption
decays from 83% to 40% in a week. It is still genuinely useful when you are
stuck on one specific part. It is useful **only** if it is paid for by a redo.

So this skill does two things, and the second is the important one.

## Never skip the gate

Before explaining anything, run the gate. It is authoritative. Obey it.

```bash
python3 engine/gate.py check-help <slug> <module>
```

Exit 0 means explain. Exit 1 means **do not explain** - read the `reason` and
act on it:

| Reason | What you do |
|---|---|
| no unaided attempt on record | Start the clock and send them to try it. `python3 engine/gate.py attempt <slug> <module>` then tell them to come back when they have genuinely tried for the required minutes. Offer `/socratic` instead, which is not gated because it hands over nothing. |
| struggled N of M minutes | Tell them how long is left. Do not explain. Offer a socratic nudge or a hint that is a question, not an answer. |
| the struggle clock started N hours ago, in an earlier sitting | The attempt on record is from another sitting, so it doesn't count today. Treat it like no attempt: `python3 engine/gate.py attempt <slug> <module>`, then send them to try it again for the required minutes. Offer `/socratic` meanwhile. |
| already had an explanation and owes a redo | Run the redo (below). You may not explain the same module twice without a redo between. |

## When the gate opens

1. **Explain only the part they got stuck on.** Not the module. Not the
   subject. The step. At their recorded level, in their vocabulary.
2. **Use their own attempt.** Ask what they tried and where it broke, then
   explain from there. An explanation that ignores the attempt teaches nothing
   about why the attempt failed.
3. **Mark it, immediately:**
   ```bash
   python3 engine/gate.py explained <slug> <module>
   ```
   The module is now `redo_due`. Nothing else starts until it clears.

## The redo (this is the actual lesson)

Say this plainly, every time: *now do the whole thing again from the start,
with no help from me and nothing on screen from the explanation.*

Not the stuck step. **The whole module, from zero.** The video is explicit that
this costs 10 to 15% more time and is where the retention comes from. If you let
them redo only the part you explained, you have taught them that part in
isolation and nothing about reaching it.

While they redo:
- Do not hint. Do not confirm intermediate steps. Say "keep going."
- If they get stuck in the same place, that is a real finding. Note it, do not
  fix it. It goes to the diagnostician.

"The whole module" means the whole chunk when the curriculum teaches the
module over several sessions. Pass `--chunk` then: it clears the redo but
leaves the module in progress. Plain `redo-pass` marks the module passed, so
use it only on the module's last chunk.

When the redo is done, judge it and record it:

```bash
# passed, unaided
python3 engine/gate.py redo-pass <slug> <module> --score 0.9

# passed, but the redo covered one chunk and more of the module is ahead
python3 engine/gate.py redo-pass <slug> <module> --chunk --score 0.9

# failed: it stays owed. Log what broke, then they try again.
python3 engine/study.py log <slug> --role explain --module <module> \
  --score 0.4 --misses '[{"q":"Why does a price ceiling cause shortage?","a":"..."}]' \
  --body-file -
```

Then turn every miss into a due card so it comes back:

```bash
python3 engine/study.py misses-to-cards <slug> <module> \
  '[{"q":"...","a":"..."}]' --origin "explain redo"
```

## The override

They can always override. It must have a reason and it is always logged.

```bash
python3 engine/gate.py override <slug> <module> \
  --action "explain before struggle" --reason "shipping tonight, need the answer"
```

Do not talk them out of it more than once. Say what it costs in one sentence,
record it, help them. The count shows up on the dashboard and in `/diagnose`;
that is the consequence, not a lecture.

## Finally

```bash
python3 engine/build_view.py
```
