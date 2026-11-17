#!/usr/bin/env python3
"""Prove the gate blocks, by putting it in each state it is supposed to refuse.

Every check here is a negative test: it drives the engine into the situation the
gate exists to catch and asserts the gate goes red (exit 1). Two of them then
disarm the thing being guarded and assert the gate goes green, which is what
distinguishes a real check from one that happens to pass for an unrelated
reason.

Runs the real CLI in a subprocess, against a throwaway root, with a timeout on
every call. A timeout is reported as inconclusive, never as a pass.

    python3 tests/test_gate.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ENGINE = os.path.join(REPO, "engine")

PASS, FAIL = [], []


def run(script, *args, **kw):
    """Invoke engine/<script> and return (exit_code, parsed_json_or_text)."""
    env = dict(os.environ, STUDY_ENGINE_ROOT=kw["root"], PYTHONPATH=ENGINE)
    try:
        p = subprocess.run(
            [sys.executable, "-I", os.path.join(ENGINE, script)] + [str(a) for a in args],
            capture_output=True, text=True, timeout=30, env=env,
            input=kw.get("stdin"))
    except subprocess.TimeoutExpired:
        raise AssertionError("INCONCLUSIVE: %s %s timed out" % (script, args))
    body = (p.stdout or "").strip()
    try:
        return p.returncode, json.loads(body)
    except ValueError:
        return p.returncode, body + (("\n" + p.stderr) if p.stderr else "")


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print("  ok   %s" % name)
    else:
        FAIL.append((name, detail))
        print("  FAIL %s %s" % (name, detail))


def backdate(root, slug, module, minutes):
    """Rewind the struggle clock, standing in for actually waiting."""
    import datetime
    path = os.path.join(root, "topics", slug, "attempts.json")
    with open(path) as fh:
        data = json.load(fh)
    data[module]["started"] = (
        datetime.datetime.now() - datetime.timedelta(minutes=minutes)
    ).replace(microsecond=0).isoformat()
    with open(path, "w") as fh:
        json.dump(data, fh)


def main():
    root = tempfile.mkdtemp(prefix="study-engine-test-")
    os.makedirs(os.path.join(root, "topics"))
    try:
        print("\nGATE")
        rc, _ = run("study.py", "new", "Test Topic", "--struggle-minutes", "12", root=root)
        check("topic created", rc == 0)
        tdir = os.path.join(root, "topics", "test-topic")
        texts = {}
        for name in ("materials.md", "progress.md"):
            path = os.path.join(tdir, name)
            texts[name] = open(path, encoding="utf-8").read() if os.path.isfile(path) else ""
        # /start reads progress.md's Study plan, Next and Log by heading, so a
        # template without them would leave a new topic unreadable to it.
        check("a new topic starts with materials.md and progress.md",
              "Test Topic" in texts["materials.md"]
              and all(h in texts["progress.md"] for h in ("## Study plan", "## Next", "## Log")),
              {k: len(v) for k, v in texts.items()})
        rc, _ = run("study.py", "add-module", "test-topic", "m1", "--title", "First", root=root)
        check("module m1 added", rc == 0)
        run("study.py", "add-module", "test-topic", "m2", "--title", "Second", root=root)

        # 1. No attempt on record at all.
        rc, out = run("gate.py", "check-help", "test-topic", "m1", root=root)
        check("blocks help with no unaided attempt",
              rc == 1 and "no unaided attempt" in out["reason"], out)

        # 2. Attempt started but the struggle time has not elapsed.
        run("gate.py", "attempt", "test-topic", "m1", root=root)
        rc, out = run("gate.py", "check-help", "test-topic", "m1", root=root)
        check("blocks help before the struggle minutes elapse",
              rc == 1 and "struggled" in out["reason"], out)

        # 2b. Disarm the thing being guarded: the SAME call must flip to allow
        #     once the clock is satisfied. Without this, check 2 would pass even
        #     if the gate were refusing for some unrelated reason.
        backdate(root, "test-topic", "m1", 13)
        rc, out = run("gate.py", "check-help", "test-topic", "m1", root=root)
        check("allows help once the struggle time is served",
              rc == 0 and out["allow"] is True, out)

        # 2c. A clock from an earlier sitting proves nothing about today's
        #     struggle. Yesterday's attempt must not unlock help today.
        backdate(root, "test-topic", "m1", 25 * 60)
        rc, out = run("gate.py", "check-help", "test-topic", "m1", root=root)
        check("blocks help on a struggle clock from an earlier sitting",
              rc == 1 and "earlier sitting" in out["reason"], out)

        # 2d. Disarm it from both sides: the same clock just inside the limit
        #     still counts, just outside it does not. That pins the line at 3
        #     hours, not at "some time after the minutes are served".
        backdate(root, "test-topic", "m1", 3 * 60 - 1)
        rc, out = run("gate.py", "check-help", "test-topic", "m1", root=root)
        check("allows help on a clock started earlier in the same sitting",
              rc == 0 and out["allow"] is True, out)
        backdate(root, "test-topic", "m1", 3 * 60 + 1)
        rc, out = run("gate.py", "check-help", "test-topic", "m1", root=root)
        check("blocks help once the clock is past the sitting limit",
              rc == 1 and "earlier sitting" in out["reason"], out)

        # 3. Help given: the module now owes a redo, and help is refused again.
        rc, _ = run("gate.py", "explained", "test-topic", "m1", root=root)
        mods = json.load(open(os.path.join(root, "topics", "test-topic", "modules.json")))
        check("explanation sets status to redo_due", mods["m1"]["status"] == "redo_due",
              mods["m1"]["status"])
        rc, out = run("gate.py", "check-help", "test-topic", "m1", root=root)
        check("blocks a second explanation while a redo is owed",
              rc == 1 and "owes an unaided redo" in out["reason"], out)

        # 4. A different module may not start while that redo is owed.
        rc, out = run("gate.py", "check-advance", "test-topic", "m2", root=root)
        check("blocks starting a new module while a redo is owed",
              rc == 1 and out["blocked_by"] == ["m1"], out)

        # 5. Redo passes: both blocks lift.
        rc, _ = run("gate.py", "redo-pass", "test-topic", "m1", "--score", "0.9", root=root)
        mods = json.load(open(os.path.join(root, "topics", "test-topic", "modules.json")))
        check("redo-pass sets status to unaided_pass",
              mods["m1"]["status"] == "unaided_pass", mods["m1"]["status"])
        rc, out = run("gate.py", "check-advance", "test-topic", "m2", root=root)
        check("allows a new module once nothing is owed", rc == 0 and out["blocked_by"] == [], out)

        # 5b. A chunk redo clears the debt but must not mark the module done:
        #     more of it is still ahead. Plain redo-pass (5) is the control.
        run("gate.py", "attempt", "test-topic", "m2", root=root)
        run("gate.py", "explained", "test-topic", "m2", root=root)
        rc, _ = run("gate.py", "redo-pass", "test-topic", "m2", "--chunk",
                    "--score", "0.75", root=root)
        mods = json.load(open(os.path.join(root, "topics", "test-topic", "modules.json")))
        check("a chunk redo does not mark the module passed",
              rc == 0 and mods["m2"]["status"] == "attempting", mods["m2"]["status"])
        rc, out = run("gate.py", "check-advance", "test-topic", "m1", root=root)
        check("a chunk redo clears the debt", rc == 0 and out["blocked_by"] == [], out)
        rc, out = run("gate.py", "check-help", "test-topic", "m2", root=root)
        check("the next chunk needs its own struggle clock",
              rc == 1 and "no unaided attempt" in out["reason"], out)

        # 6. The override needs a reason, and lands in the log.
        rc, out = run("gate.py", "override", "test-topic", "m2", "--action", "x", root=root)
        check("override without a reason is refused", rc == 1, out)
        rc, out = run("gate.py", "override", "test-topic", "m2",
                      "--action", "explain early", "--reason", "deadline", root=root)
        check("override with a reason is allowed", rc == 0, out)
        rc, sessions = run("study.py", "sessions", "test-topic", root=root)
        check("the override is on the record",
              any(s["override"] for s in sessions), sessions)

        # 7. Advisory topics are advisory: no attempt, help still allowed.
        run("study.py", "new", "Loose Topic", root=root)
        run("study.py", "set-profile", "loose-topic", "--strictness", "advisory", root=root)
        run("study.py", "add-module", "loose-topic", "m1", "--title", "First", root=root)
        rc, out = run("gate.py", "check-help", "loose-topic", "m1", root=root)
        check("advisory strictness allows help with no attempt",
              rc == 0 and "advisory" in out["reason"], out)

        print("\nSCHEDULER")
        cards = '[{"q":"What is 2+2?","a":"4"},{"q":"What is 3+3?","a":"6"}]'
        rc, out = run("study.py", "add-cards", "test-topic", cards, "--module", "m1", root=root)
        check("cards added", rc == 0 and out["added"] == 2, out)
        rc, out = run("study.py", "add-cards", "test-topic", cards, "--module", "m1", root=root)
        check("duplicate questions are skipped", out["skipped_duplicates"] == 2, out)

        rc, out = run("study.py", "due", "test-topic", root=root)
        check("new cards are due today", out["due"] == 2, out)

        rc, card = run("study.py", "grade", "test-topic", "c001", "good", root=root)
        check("a pass pushes the card into the future",
              card["interval"] == 1 and card["due"] > card["created"], card)
        rc, card = run("study.py", "grade", "test-topic", "c001", "good", root=root)
        check("a second pass lengthens the interval", card["interval"] == 6, card)
        ease_before = card["ease"]
        rc, card = run("study.py", "grade", "test-topic", "c001", "again", root=root)
        check("a lapse drops the interval to 1 and the ease with it",
              card["interval"] == 1 and card["ease"] < ease_before and card["lapses"] == 1, card)

        misses = '[{"q":"Why does a price ceiling cause a shortage?","a":"Qd > Qs"}]'
        rc, out = run("study.py", "misses-to-cards", "test-topic", "m1", misses, root=root)
        check("a miss becomes a card", rc == 0 and out["added"] == 1, out)
        rc, out = run("study.py", "due", "test-topic", root=root)
        check("that card is due immediately",
              any("price ceiling" in c["q"] for c in out["cards"]), out["due"])

        print("\nSPAR")
        # A spar is practice under pressure, not the redo an explanation owes.
        # A perfect spar on a module with a redo owed must leave the debt in
        # place, or a mock exam becomes a way around the gate. It runs before
        # DIAGNOSE so the diagnosis stays the newest session there.
        run("gate.py", "explained", "test-topic", "m2", root=root)
        tries = json.load(open(os.path.join(tdir, "modules.json")))["m2"].get("attempts", 0)
        rc, out = run("study.py", "log", "test-topic", "--role", "spar", "--module", "m2",
                      "--score", "1.0", "--body-file", "# Spar\n\n## Right\n- all of it",
                      root=root)
        check("spar is a role the log accepts", rc == 0, out)
        mods = json.load(open(os.path.join(tdir, "modules.json")))
        status = mods["m2"]["status"]
        # A mock exam on an old chapter is practice, not the learner moving
        # back to it: no attempt counted (and, like a diagnosis, "You're on"
        # stays put; both read LOOKBACK_ROLES).
        check("a spar does not count as an attempt on its module",
              mods["m2"].get("attempts", 0) == tries, (tries, mods["m2"]))
        rc, out = run("gate.py", "check-advance", "test-topic", "m1", root=root)
        check("a perfect spar does not clear the redo it owes",
              status == "redo_due" and rc == 1 and "m2" in out.get("blocked_by", []),
              (status, out))

        # The hard stop, pinned at both edges: 4:59 into a 5-minute spar is
        # still running, 5:00 is time.
        start = 1700000000
        rc, out = run("study.py", "clock", "--start", start, "--minutes", 5,
                      "--now", start + 299, root=root)
        check("the spar clock runs until the limit",
              rc == 0 and out["over"] is False and out["left"] == 1, out)
        rc, out = run("study.py", "clock", "--start", start, "--minutes", 5,
                      "--now", start + 300, root=root)
        check("the spar clock stops at the limit, not after it",
              rc == 1 and out["over"] is True and out["say"].startswith("TIME"), out)

        print("\nDIAGNOSE")
        # /diagnose may only cite what is on disk. The corpus must hand it the
        # sessions that recorded a gap, by a real file name, and nothing else,
        # with a bullet that wraps onto a second line kept as one item.
        def snapshot(path):
            seen = {}
            for base, _, files in os.walk(path):
                for f in files:
                    p = os.path.join(base, f)
                    seen[p] = (os.stat(p).st_mtime_ns, open(p, "rb").read())
            return seen

        run("study.py", "log", "test-topic", "--role", "socratic", "--module", "m1",
            "--score", "0.5", "--body-file", "-", root=root,
            stdin="# S\n\n## Held up under questioning\n- supply shifts\n\n"
                  "## Gaps found\n- Treats a shift of demand\n  as a movement along it\n\n"
                  "## Wrong\n- None.\n")
        # Session files sort by their to-the-second names; a second apart
        # keeps the order socratic m1, examine m2, diagnose m1.
        import time
        time.sleep(1.1)
        run("study.py", "log", "test-topic", "--role", "examine", "--module", "m2",
            "--score", "1.0", "--body-file", "-", root=root,
            stdin="# E\n\n## Right\n- everything\n\n## Wrong\n- None.\n")
        time.sleep(1.1)
        mods_before = json.load(open(os.path.join(tdir, "modules.json")))
        rc, out = run("study.py", "log", "test-topic", "--role", "diagnose", "--module", "m1",
                      "--body-file", "# D\n\n## Root\n- shift against movement", root=root)
        check("diagnose is a role the log accepts", rc == 0, out)
        # A diagnosis filed under m1 is about m1, not work on it: it must not
        # count as an attempt (and, checked under DASHBOARD, must not move
        # "You're on" back to m1).
        mods_after = json.load(open(os.path.join(tdir, "modules.json")))
        check("a diagnosis does not count as an attempt on its module",
              mods_after["m1"]["attempts"] == mods_before["m1"]["attempts"],
              (mods_before["m1"]["attempts"], mods_after["m1"]["attempts"]))

        before = snapshot(tdir)
        rc, corpus = run("study.py", "corpus", "test-topic", root=root)
        ok = rc == 0 and isinstance(corpus, dict)
        cited = {s["file"]: s for s in corpus["sessions"]} if ok else {}
        soc = [s for f, s in cited.items() if "-socratic-m1" in f]
        check("corpus cites only sessions that recorded a gap, by a file that exists",
              ok and len(soc) == 1
              and soc[0]["gaps"] == {"Gaps found": ["Treats a shift of demand as a movement along it"]}
              and not any("-examine-m2" in f for f in cited)
              and all(os.path.isfile(os.path.join(tdir, "sessions", f)) for f in cited),
              corpus)
        held_only = {s["file"]: s for s in corpus.get("held_only", [])} if ok else {}
        clean = [s for f, s in held_only.items() if "-examine-m2" in f]
        check("corpus carries what held, and keeps a clean session as counter-evidence",
              ok and soc and soc[0]["held"] == {"Held up under questioning": ["supply shifts"]}
              and len(clean) == 1 and clean[0]["held"] == {"Right": ["everything"]},
              (soc, held_only))
        rc, text = run("study.py", "corpus", "test-topic", "--text", root=root)
        check("the text corpus lists the gap and what held, by file",
              rc == 0 and isinstance(text, str)
              and "x Gaps found: Treats a shift of demand as a movement along it" in text
              and "+ Right: everything" in text and "-socratic-m1.md" in text, text)
        weak = [c["id"] for c in corpus.get("weak_cards", [])] if ok else []
        check("corpus lists the lapsed card and leaves out the clean one",
              "c001" in weak and "c002" not in weak, weak)
        check("corpus writes nothing", snapshot(tdir) == before)

        # The thin-corpus warning, pinned at both edges: 19 sessions is thin,
        # 20 is not.
        for i in range(19):
            run("study.py", "log", "loose-topic", "--role", "review",
                "--body-file", "# R%d" % i, root=root)
        rc, out = run("study.py", "corpus", "loose-topic", root=root)
        check("19 sessions is flagged as a thin corpus",
              rc == 0 and out["sessions_total"] == 19 and out["thin"] is True, out)
        run("study.py", "log", "loose-topic", "--role", "review", "--body-file", "# R19", root=root)
        rc, out = run("study.py", "corpus", "loose-topic", root=root)
        check("20 sessions is not",
              rc == 0 and out["sessions_total"] == 20 and out["thin"] is False, out)

        # A mistyped slug must not make a stray topic and lose the session.
        rc, out = run("study.py", "log", "loose-topik", "--role", "review",
                      "--body-file", "# typo", root=root)
        check("log refuses a topic that doesn't exist and makes no folder",
              rc != 0 and "no such topic" in str(out)
              and not os.path.exists(os.path.join(root, "topics", "loose-topik")), out)

        # /review's first-day branch reads this count line.
        rc, text = run("study.py", "due", "loose-topic", "--text", root=root)
        check("due --text says when the deck is empty",
              rc == 0 and text.strip() == "loose-topic: 0 due, 0 cards in the deck", text)

        print("\nDASHBOARD")
        rc, out = run("build_view.py", root=root)
        check("dashboard builds", rc == 0 and out["topics"] == 2, out)
        html = open(os.path.join(root, "view", "dashboard.html"), encoding="utf-8").read()
        check("dashboard is self-contained",
              not any(n in html for n in ("<link href", "<script src", "<img src")))
        # The figure itself, not a bare ">1<": the chapter detail panel prints
        # "<dd>1</dd>" for one attempt, which kept the loose test green with
        # the count forced to 0.
        check("dashboard reports the override count",
              'Gate overrides on record</p><p class="figure">1</p>' in html,
              re.findall(r"Gate overrides on record</p><p[^>]*>[^<]*<", html))
        check("a diagnosis does not move \"You're on\"",
              "You\u2019re on <b>Second</b>" in html,   # Loose Topic is really on First
              [l for l in html.split("<") if "re on" in l][:3])

        # The public kit ships without engine/news.py. Build from a copy of the
        # engine that lacks it: the dashboard must still build, with no news.
        bare = os.path.join(root, "bare-engine")
        shutil.copytree(ENGINE, bare, ignore=shutil.ignore_patterns("news.py", "__pycache__"))
        env = dict(os.environ, STUDY_ENGINE_ROOT=root)
        try:
            p = subprocess.run([sys.executable, "-I", os.path.join(bare, "build_view.py"),
                                "--news-if-stale"],
                               capture_output=True, text=True, timeout=30, env=env)
            ok = p.returncode == 0 and '"news"' not in p.stdout
            html = open(os.path.join(root, "view", "dashboard.html"), encoding="utf-8").read()
            check("dashboard builds without the news module",
                  ok and "<h2>News</h2>" not in html, (p.returncode, p.stderr[-300:]))
        except subprocess.TimeoutExpired:
            check("dashboard builds without the news module", False, "INCONCLUSIVE: timed out")

        # --demo renders examples/demo to view/demo.html, labelled as sample
        # data, and leaves the learner's own dashboard exactly as it was.
        before = open(os.path.join(root, "view", "dashboard.html"), encoding="utf-8").read()
        rc, out = run("build_view.py", "--demo", root=root)
        demo_path = os.path.join(root, "view", "demo.html")
        demo = open(demo_path, encoding="utf-8").read() if os.path.isfile(demo_path) else ""
        after = open(os.path.join(root, "view", "dashboard.html"), encoding="utf-8").read()
        check("demo is labelled sample data and leaves the real dashboard alone",
              rc == 0 and isinstance(out, dict) and out.get("demo") is True and "Sample data" in demo
              and "Test Topic" not in demo and "<h2>News</h2>" not in demo and before == after, out)

    finally:
        shutil.rmtree(root, ignore_errors=True)

    print("\n%d/%d checks passed" % (len(PASS), len(PASS) + len(FAIL)))
    if FAIL:
        for name, detail in FAIL:
            print("  FAILED: %s -- %s" % (name, detail))
        sys.exit(1)


if __name__ == "__main__":
    main()
