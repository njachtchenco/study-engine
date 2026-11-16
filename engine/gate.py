#!/usr/bin/env python3
"""The anti-shortcut gate.

The video's sharpest claim is that learning happens in the struggle, and that
an explanation received feels like understanding while producing none. The two
mechanics that follow from it are the two a human will always skip, so they
live here instead of in good intentions:

  1. A minimum unaided attempt, in the same sitting, before help unlocks.
  2. After help, the module is owed a redo from scratch, and nothing else
     starts until that redo passes.

Every decision prints JSON and sets an exit code: 0 allow, 1 block. Skills must
run the relevant check and obey it. An override is always available and is
always written to the session log, so `/diagnose` can later show how often the
struggle got skipped and on which modules.
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

ATTEMPTS = "attempts.json"

# A struggle clock belongs to one sitting. The longest planned session is two
# hours, so a clock older than this was started in an earlier sitting and says
# nothing about whether today's struggle happened.
CLOCK_EXPIRES_HOURS = 3


def _attempts_path(slug):
    return os.path.join(store.topic_dir(slug), ATTEMPTS)


def _read_attempts(slug):
    p = _attempts_path(slug)
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _write_attempts(slug, data):
    with open(_attempts_path(slug), "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def _emit(allow, reason, **extra):
    payload = {"allow": bool(allow), "reason": reason}
    payload.update(extra)
    print(json.dumps(payload, indent=2))
    sys.exit(0 if allow else 1)


def redo_owed(slug):
    """Modules that were explained and never reproduced unaided."""
    return [mid for mid, m in sorted(store.read_modules(slug).items())
            if m.get("status") in ("explained", "redo_due")]


# ------------------------------------------------------------------ commands

def cmd_attempt(args):
    """Start the clock on an unaided attempt."""
    store.get_module(args.topic, args.module)
    a = _read_attempts(args.topic)
    a[args.module] = {"started": store.now()}
    _write_attempts(args.topic, a)
    store.set_module(args.topic, args.module, status="attempting")
    _emit(True, "attempt started; struggle clock running", module=args.module,
          started=a[args.module]["started"])


def cmd_check_help(args):
    """May the explainer run on this module?"""
    topic = store.read_topic(args.topic)
    mod = store.get_module(args.topic, args.module)
    strict = topic.get("strictness", "enforced")

    if mod.get("status") in ("explained", "redo_due"):
        _emit(False, "this module already had an explanation and owes an unaided "
                     "redo; finish the redo before asking for more help",
              module=args.module, status=mod["status"])

    if strict == "advisory":
        _emit(True, "advisory topic: help allowed, shortcut will be recorded",
              module=args.module)

    need = int(topic.get("struggle_minutes", 10))
    a = _read_attempts(args.topic).get(args.module)
    if not a:
        _emit(False, "no unaided attempt on record; run `gate.py attempt` and "
                     "actually try it for %d minutes first" % need,
              module=args.module, struggle_minutes_required=need)

    started = datetime.datetime.fromisoformat(a["started"])
    mins = (datetime.datetime.now() - started).total_seconds() / 60.0
    if mins > CLOCK_EXPIRES_HOURS * 60:
        _emit(False, "the struggle clock started %.1f hours ago, in an earlier "
                     "sitting; run `gate.py attempt` and try it again for %d "
                     "minutes" % (mins / 60.0, need),
              module=args.module, started=a["started"],
              hours_since_start=round(mins / 60.0, 1),
              clock_expires_hours=CLOCK_EXPIRES_HOURS,
              struggle_minutes_required=need)

    if mins < need:
        _emit(False, "struggled %.1f of the %d minutes this topic requires" % (mins, need),
              module=args.module, minutes_so_far=round(mins, 1),
              struggle_minutes_required=need)

    _emit(True, "struggled %.0f minutes; help unlocked" % mins,
          module=args.module, minutes_so_far=round(mins, 1))


def cmd_explained(args):
    """Record that help was given. The module now owes a redo."""
    store.set_module(args.topic, args.module, status="redo_due",
                     explained_at=store.now())
    _emit(True, "module marked redo_due: it must be redone from scratch, "
                "unaided, before anything else starts", module=args.module)


def cmd_redo_pass(args):
    """The unaided redo succeeded."""
    mod = store.get_module(args.topic, args.module)
    if mod.get("status") not in ("explained", "redo_due", "attempting"):
        _emit(False, "module is %r; nothing is owed" % mod.get("status"),
              module=args.module)
    a = _read_attempts(args.topic)
    a.pop(args.module, None)
    _write_attempts(args.topic, a)
    # A module taught over several chunks isn't passed by one chunk's redo.
    # --chunk clears the debt and leaves the module in progress, so the next
    # chunk still starts with its own clock and the module isn't counted done.
    if args.chunk:
        store.set_module(args.topic, args.module, status="attempting",
                         last_score=args.score)
        _emit(True, "chunk redo passed unaided; redo cleared, module still in "
                    "progress", module=args.module, score=args.score)
    store.set_module(args.topic, args.module, status="unaided_pass",
                     unaided_pass_at=store.now(), last_score=args.score)
    _emit(True, "redo passed unaided; module cleared", module=args.module,
          score=args.score)


def cmd_check_advance(args):
    """May a new module start?"""
    topic = store.read_topic(args.topic)
    owed = redo_owed(args.topic)
    if args.module in owed:
        owed = [m for m in owed if m != args.module]
    if not owed:
        _emit(True, "nothing owed; clear to start", blocked_by=[])
    if topic.get("strictness", "enforced") == "advisory":
        _emit(True, "advisory topic: proceeding with %d redo(s) owed" % len(owed),
              blocked_by=owed)
    _emit(False, "%d module(s) owe an unaided redo before a new one starts: %s"
          % (len(owed), ", ".join(owed)), blocked_by=owed)


def cmd_override(args):
    """Allow a blocked action, on the record."""
    if not args.reason:
        _emit(False, "an override needs a reason; it goes in the log")
    store.log_session(
        args.topic, "explain",
        body="# Gate override\n\nAction: %s\n\nReason given: %s\n" % (args.action, args.reason),
        module=args.module, override=True, override_reason=args.reason)
    _emit(True, "override recorded in the session log", module=args.module,
          action=args.action, override_reason=args.reason)


def cmd_status(args):
    mods = store.read_modules(args.topic)
    owed = redo_owed(args.topic)
    by_status = {}
    for m in mods.values():
        by_status[m["status"]] = by_status.get(m["status"], 0) + 1
    overrides = [s for s in store.read_sessions(args.topic) if s.get("override")]
    print(json.dumps({
        "topic": args.topic,
        "modules": len(mods),
        "by_status": by_status,
        "redo_owed": owed,
        "overrides": len(overrides),
        "clear_to_advance": not owed,
    }, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, module=True):
        s = sub.add_parser(name)
        s.add_argument("topic")
        if module:
            s.add_argument("module")
        s.set_defaults(fn=fn)
        return s

    add("attempt", cmd_attempt)
    add("check-help", cmd_check_help)
    add("explained", cmd_explained)
    s = add("redo-pass", cmd_redo_pass)
    s.add_argument("--score", type=float, default=None)
    s.add_argument("--chunk", action="store_true",
                   help="the redo covered one chunk; more of the module is ahead")
    add("check-advance", cmd_check_advance)
    s = add("override", cmd_override)
    s.add_argument("--action", default="unspecified")
    s.add_argument("--reason", default="")
    add("status", cmd_status, module=False)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
