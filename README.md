# Study Engine

An AI study system for Claude Code that makes you do the work, because doing
the work is the part that sticks.

**Two ways to use it.** The full version runs in the Claude desktop app and
needs a paid Claude plan ([set it up](#set-it-up)). On the free plan, use the
lite version: **[open the lite setup page](https://njachtchenco.github.io/study-engine/lite/setup.html)**.
Nothing to download.

Most people use AI to study by asking it to explain things. That feels like
learning. The research says it mostly isn't:

| How you study | Remembered after 5 minutes | Remembered after 1 week |
|---|---|---|
| Reread the material 4 times | 83% | 40% |
| Read it once, then test yourself 3 times | 71% | 61% |

Rereading wins today and loses the week, even though the self-testers read
the material only 3.4 times on average and the rereaders 14.2 times (Roediger
and Karpicke, 2006, *Psychological Science*). Getting something explained is
the same kind of thing as rereading: you take it in, you don't produce it.

Study Engine keeps you on the second row. It asks you questions instead of
answering them, makes you try before it helps, makes you redo anything it
explained from scratch, and turns every mistake you make into a flashcard that
comes back right before you'd forget it.

## What's inside

Nine study roles, each a slash command in Claude Code:

| Command | What it does | Does it give you answers? |
|---|---|---|
| `/interview` | Finds out what you actually need: the real goal, your level, how you'll be tested, the deadline | No, it only asks |
| `/map` | Turns the subject into an ordered list of modules and a session plan | No |
| `/socratic` | Asks you questions until you find what you don't know yourself | Never |
| `/explain` | Explains the one part you're stuck on, but only after you've really tried | Yes, and you owe a redo |
| `/examine` | A quiz that gets harder each question and stops where you start guessing | Afterwards |
| `/clerk` | Turns your messy notes into a clean outline and flashcards, adding nothing | No |
| `/review` | Your daily flashcards, scheduled on the forgetting curve | After you answer |
| `/diagnose` | Reads all your past sessions and finds the one misunderstanding behind many mistakes, then tests it | Never, it names the gap |
| `/spar` | A timed run of the real thing: a mock exam, an interview, a conversation, a pitch. No help until time is up | After time is up |

Plus `/start` (where you left off and what to do first) and `/dashboard` (a
page showing what's due, what you owe, and how far along you are).

## The two rules

These are built into the code, because they're exactly what a person skips:

1. **Help unlocks only after a real attempt.** `/explain` won't explain a
   module until you've worked on it alone for 10 minutes (you can change the
   number) in the same sitting.
2. **Every explanation owes a redo.** After it explains something, you do the
   whole module again from scratch with no help, and nothing new starts until
   you pass.

You can always override either one. It asks for a reason, writes it down, and
the count shows on your dashboard. That's the whole consequence.

## On the free plan? Use the lite version

**[Open the lite setup page](https://njachtchenco.github.io/study-engine/lite/setup.html).**
It gets you going in about three minutes on claude.ai, free account included:
make a Project, paste the instructions, add your syllabus or notes, start. Do
the setup on a computer, not a phone. Seven of the roles and the
same two rules, with three things missing: nothing enforces the rules (it asks, you answer
honestly), there's no dashboard, and there's no spaced scheduling (use Anki
for your cards). Every session ends with your mistakes as flashcards and a
short "where I am" note you paste back into the Project.

## What you need

- **A paid Claude plan.** The full version needs one (Pro or higher, see
  [claude.com/pricing](https://claude.com/pricing)). On the free plan, use the
  [lite version](#on-the-free-plan-use-the-lite-version).
- **The Claude desktop app**, signed in:
  [claude.com/download](https://claude.com/download). Claude Code is built
  into its **Code** tab, so you don't need Terminal or a code editor.
- **Python 3.9 or newer.** Study Engine is a few small Python programs that
  Claude runs for you. On a Mac, the first time Claude runs one, your Mac may
  say the `python3` command needs the command line developer tools. Click
  **Install**, wait a few minutes (it's a download of about 1 GB), then tell
  Claude to try again. On Windows, install Python from
  [python.org](https://www.python.org/downloads/) first.
- **A Mac or a Windows PC.** It's tested on a Mac. Windows should work but
  isn't tested yet.

## Set it up

1. **Get the folder.** On this page, click the green **Code** button, then
   **Download ZIP**. Open your Downloads folder and double-click
   `study-engine-main.zip`. That makes a folder called `study-engine-main`.
2. **Open it in Claude.** Open the Claude desktop app and click **Code** at
   the top of the sidebar. In the row under the message box, click the first
   button and choose the top entry under **Local**. Then click the folder
   button next to it, choose **Open folder…**, and pick `study-engine-main`.
   Your Mac asks whether Claude can access your Downloads folder. Click
   **Allow**.
3. **See an example first (optional).** Type `Show me the demo dashboard`.
   Claude builds a made-up example topic and opens it in your browser, so
   you can see what a few weeks of studying looks like.

Claude asks before it saves a file or runs a command. That's normal: allow
it. Everything Study Engine saves stays in this folder. If it asks before
every save, open the mode menu in the row under the message box and choose
**Accept edits**. Claude remembers that for this folder.

Already use Claude Code in a terminal or a code editor? It works there too:
clone this repo, start Claude Code in the folder and type `/interview`.

## Your first session

Say you have a trip to Spain in March. In the **Code** tab, type:

```
/interview Spanish for my trip
```

It asks you questions, one at a time, and teaches nothing yet. By the end it
knows your real goal ("order food, ask directions and check into a hotel
without switching to English"), your level, and how you'll be tested (a spoken
conversation, so your practice will be spoken too).

```
/map spanish-for-my-trip
```

(Use the short name the interview gave your topic.) It breaks the goal into modules in the right order, says what it cut and why,
and plans your sessions up to the deadline.

From then on, each sitting starts with:

```
/start spanish
```

It tells you what last time found, whether you're on track, and the one thing
to do first. Usually that's `/socratic` on the next module, with `/explain` only
when you're truly stuck, and `/examine` when you think you've got it.

Every mistake you make in those sessions becomes a flashcard. Once you have
some, spend a few minutes a day on:

```
/review
```

(On day one there's nothing to review yet. That's normal.)

## It works for any subject

The interview turns whatever you're learning into a goal and a test, and every
role practices in the shape of that test. Some examples:

- **A class:** "pass the Dec 5 final, 60 multiple choice, closed book". Give
  `/interview` your syllabus and it plans around the exam dates.
- **A language:** "hold a 5-minute conversation with a waiter, no notes".
- **A certification:** "pass the exam, 65 questions in 90 minutes".
- **A job interview:** "explain my last project and answer follow-ups for 20
  minutes".
- **A skill for work:** "write a SQL query that answers my manager's question
  without asking a colleague".
- **The science behind your training:** "plan my own program and explain why
  each choice is there".

## Your data

Everything lives in plain files in the `topics/` folder: your goal, your
modules, your flashcards, and a written record of every session. Nothing is
uploaded anywhere except the conversation itself, which goes to Claude like any
Claude Code session. Delete the folder and it's gone.

## Tips

- **Talk your answers.** Voice dictation works well. The grading checks for
  transcription slips ("elastic" heard as "inelastic") before marking you wrong.
- **Need the gist fast, not mastery?** Tell `/interview` you want working
  knowledge. That makes the rules advisory: shortcuts get recorded, never
  blocked.
- **A card you keep failing isn't a card problem.** `/review` will send you
  back to `/socratic` on that module instead of scheduling the
  misunderstanding again.

## Not built yet

Two more roles are designed but not written: a **Checker** that grades your
method and shows a shorter route, and a **Listener** you explain things back
to by talking, drawing and writing.

## The case against all of this

Worth knowing before you start:

- **Learning happens in the struggle.** The minutes of squinting at a problem
  are the part that sticks. AI makes it easy to skip them, and skipping them
  means remembering nothing. That's the only reason the rules exist.
- **An explanation feels like understanding, and it isn't.**
- **Offload the thinking and you weaken the skill.** People who navigate only
  by GPS end up with weaker mental maps of their own cities.

Any change that makes it easier to get an answer and harder to produce one
makes this worse, however convenient it feels.

## Credits

The ten-roles framework comes from Nick Saraev's video "How I Learn Complex
Skills & Difficult Subjects So Fast with AI" (Oct 2026). This is one way of
building it. The retention numbers are from H. L. Roediger and J. D. Karpicke,
"Test-Enhanced Learning", *Psychological Science* 17(3), 2006, Experiment 2.

Made by Nick Jachtchenco (@nick.jach). Free to use, change and share under the MIT
license in `LICENSE`.
