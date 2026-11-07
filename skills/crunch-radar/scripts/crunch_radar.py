#!/usr/bin/env python3
"""Crunch Radar: when to *start* coursework, Crunch Week warnings, Grace Days, and Estimate Bias.

State is one JSON file (default $HERMES_HOME/crunch_radar.json). Standard library only, no credentials.
Run with --help for the commands.
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import tempfile

DEFAULT_SETTINGS = {"pace_hours_per_day": 2, "crunch_threshold_hours": 15, "grace_days_per_course": 2}


class InputError(Exception):
    pass


def default_state_path():
    return os.path.join(os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes"), "crunch_radar.json")


def load(path):
    if not os.path.exists(path):
        return {"settings": dict(DEFAULT_SETTINGS), "courses": {}, "items": []}
    try:
        with open(path) as f:
            state = json.load(f)
    except ValueError as e:
        raise InputError(f"state file {path} is not valid JSON ({e}); fix or move it, nothing was changed")
    if not isinstance(state, dict):
        raise InputError(f"state file {path} is not a JSON object; fix or move it, nothing was changed")
    state["settings"] = {**DEFAULT_SETTINGS, **state.get("settings", {})}
    s = state["settings"]
    if not all(isinstance(s[k], (int, float)) and s[k] > 0 for k in ("pace_hours_per_day", "crunch_threshold_hours")):
        raise InputError("settings pace_hours_per_day and crunch_threshold_hours must be numbers above 0")
    state.setdefault("courses", {})
    state.setdefault("items", [])
    for i in state["items"]:
        if not valid_item(i):
            raise InputError(f"state file {path} has a broken item {i!r}; fix or remove it, nothing was changed")
    return state


def valid_item(i):
    try:
        dt.date.fromisoformat(i["due"])
    except (TypeError, KeyError, ValueError):
        return False
    hours = i.get("hours")
    return (isinstance(i.get("id"), int) and isinstance(i.get("title"), str)
            and (hours is None or isinstance(hours, (int, float)) and hours > 0))


def save(path, state):
    # Write a temp file and rename it over the old one, so a crash mid-write never leaves half a file.
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".crunch_radar.")
    with os.fdopen(fd, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def parse_date(s):
    try:
        return dt.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {s!r}")


def text(s):
    if not s.strip():
        raise argparse.ArgumentTypeError("must not be blank")
    return s.strip()


def whole_number(s, top=10000):
    try:
        n = int(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a whole number: {s!r}")
    if not 0 <= n <= top:
        raise argparse.ArgumentTypeError(f"must be 0 to {top}, got {s}")
    return n


def grace_days(s):
    return whole_number(s, 30)


def positive_hours(s):
    try:
        h = float(s)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number of hours: {s!r}")
    if not 0 < h <= 1000:
        raise argparse.ArgumentTypeError(f"hours must be above 0 and at most 1000, got {s}")
    return h


def estimate_bias(state):
    """Ratio of total actual to total estimated hours over completed items; 1.0 until one is done."""
    done = [i for i in state["items"] if i.get("done") and i.get("hours") and i.get("actual_hours")]
    est = sum(i["hours"] for i in done)
    return sum(i["actual_hours"] for i in done) / est if est else 1.0


def bias_text(state):
    return f"Estimate Bias: {round(estimate_bias(state), 2):g}"


def corrected_hours(state, item):
    # Round the product, not the bias: 3 h × 2/3 must be 2 h (1 day), not 3 × 0.67 = 2.01 h (2 days).
    return round(item["hours"] * estimate_bias(state), 2) if item.get("hours") else 0.0


def start_by(state, item):
    if not item.get("hours"):
        return None  # a date-only item (exam day, admin deadline) has nothing to start
    days = math.ceil(corrected_hours(state, item) / state["settings"]["pace_hours_per_day"])
    return dt.date.fromisoformat(item["due"]) - dt.timedelta(days=days)


def describe(state, item):
    sb = start_by(state, item)
    effort = f"{item['hours']:g} h est, {corrected_hours(state, item):g} h corrected" if item.get("hours") else "no effort"
    when = f"start by {sb}" if sb else "date only"
    course = f" [{item['course']}]" if item.get("course") else ""
    return f"#{item['id']} {item['title']}{course}: due {item['due']}, {when} ({effort})"


def cmd_add(state, args):
    item = {"id": max((i["id"] for i in state["items"]), default=0) + 1, "title": args.title,
            "due": args.due.isoformat(), "hours": args.hours, "course": args.course, "kind": args.kind, "done": False}
    state["items"].append(item)
    print("added " + describe(state, item))
    return True


def find(state, item_id):
    for i in state["items"]:
        if i["id"] == item_id:
            return i
    raise InputError(f"no Crunch Item #{item_id}; see `upcoming` for ids")


def cmd_done(state, args):
    item = find(state, args.id)
    if item.get("done"):
        raise InputError(f"#{item['id']} {item['title']} is already done")
    on = args.on or args.today
    item.update(done=True, submitted=on.isoformat(), actual_hours=args.hours)
    late = (on - dt.date.fromisoformat(item["due"])).days
    print(f"done #{item['id']} {item['title']}" + (f", {late} day(s) late" if late > 0 else ""))
    print(bias_text(state))
    return True


def open_items(state):
    return sorted((i for i in state["items"] if not i.get("done")), key=lambda i: i["due"])


def cmd_upcoming(state, args):
    horizon = (args.today + dt.timedelta(days=args.days)).isoformat()
    items = [i for i in open_items(state) if i["due"] <= horizon]
    print("\n".join(describe(state, i) for i in items) or f"nothing due in the next {args.days} days")
    print(bias_text(state))
    return False


def nudge(state, item, today):
    """One nudge dict, or None. Levels: date, start, behind (≤ 2× pace needed), urgent, overdue."""
    due = dt.date.fromisoformat(item["due"])
    days_left = (due - today).days
    base = {"id": item["id"], "title": item["title"], "course": item.get("course"), "due": item["due"]}
    sb = start_by(state, item)
    if sb is None:
        return {**base, "level": "date", "days_left": days_left} if 0 <= days_left <= 1 else None
    if today < sb:
        return None
    if days_left < 0:
        return {**base, "level": "overdue", "start_by": sb.isoformat(), "days_late": -days_left}
    pace = state["settings"]["pace_hours_per_day"]
    per_day = round(corrected_hours(state, item) / max(days_left, 1), 1)  # on the due day it is all due today
    level = "start" if today == sb else "behind" if per_day <= 2 * pace else "urgent"
    return {**base, "level": level, "start_by": sb.isoformat(), "days_left": days_left, "hours_per_day": per_day}


def cmd_crunch(state, args):
    threshold = state["settings"]["crunch_threshold_hours"]
    monday = args.today - dt.timedelta(days=args.today.weekday())
    for w in range(args.weeks):
        start, end = monday + dt.timedelta(weeks=w), monday + dt.timedelta(weeks=w, days=6)
        items = [i for i in open_items(state) if start.isoformat() <= i["due"] <= end.isoformat()]
        total = round(sum(corrected_hours(state, i) for i in items), 1)
        flag = "CRUNCH WEEK " if total > threshold else ""
        names = ", ".join(i["title"] for i in items if i.get("hours"))
        print(f"{flag}{start} to {end}: {total:g} h" + (f" ({names})" if names else ""))
    print(f"threshold {threshold:g} h, {bias_text(state)}")
    return False


def grace_ledger(state, course):
    total = state["courses"].get(course, {}).get("grace_days", state["settings"]["grace_days_per_course"])
    used = [(i["title"], (dt.date.fromisoformat(i["submitted"]) - dt.date.fromisoformat(i["due"])).days)
            for i in state["items"] if i.get("course") == course and i.get("done") and i.get("submitted")]
    used = [(t, d) for t, d in used if d > 0]
    return total, used, total - sum(d for _, d in used)


def cmd_grace(state, args):
    if args.set is not None:
        if not args.course:
            raise InputError("--set needs --course")
        state["courses"].setdefault(args.course, {})["grace_days"] = args.set
    courses = [args.course] if args.course else sorted({i["course"] for i in state["items"] if i.get("course")}
                                                       | set(state["courses"]))
    for c in courses:
        total, used, left = grace_ledger(state, c)
        print(f"{c}: {left} of {total} Grace Days left" + "".join(f"\n  {t}: {d} day(s) late" for t, d in used))
        if args.if_late:
            print(f"  {args.if_late} days late would leave {left - args.if_late}"
                  + (" (past the allowance: late penalty applies)" if left - args.if_late < 0 else ""))
    if not courses:
        print("no courses yet; add items with --course")
    return args.set is not None


def cmd_nudges(state, args):
    found = (nudge(state, i, args.today) for i in open_items(state))
    print(json.dumps({"today": args.today.isoformat(), "nudges": [n for n in found if n]}, indent=2))
    return False


def build_parser():
    # --state/--today work before or after the command. The subcommand copies default to SUPPRESS so they
    # never overwrite a value given before the command; they must be separate actions from the top-level ones.
    def common_flags(parser, state_default, today_default):
        parser.add_argument("--state", default=state_default, help="state file (default $HERMES_HOME/crunch_radar.json)")
        parser.add_argument("--today", type=parse_date, default=today_default, help="override today (YYYY-MM-DD)")
        return parser

    common = common_flags(argparse.ArgumentParser(add_help=False), argparse.SUPPRESS, argparse.SUPPRESS)
    p = common_flags(argparse.ArgumentParser(prog="crunch_radar.py", description=__doc__.split("\n")[0]),
                     os.environ.get("CRUNCH_RADAR_STATE") or default_state_path(), dt.date.today())
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("add", parents=[common], help="add a Crunch Item")
    a.add_argument("--title", type=text, required=True)
    a.add_argument("--due", type=parse_date, required=True)
    a.add_argument("--hours", type=positive_hours, help="Effort Estimate; leave out for a date-only item")
    a.add_argument("--course", type=text, help="course code, e.g. CSCI599 (needed for Grace Days)")
    a.add_argument("--kind", choices=["assignment", "exam", "admin"], default="assignment")
    a.set_defaults(fn=cmd_add)

    d = sub.add_parser("done", parents=[common], help="mark an item done, with the hours it really took")
    d.add_argument("id", type=int)
    d.add_argument("--hours", type=positive_hours, help="actual hours spent (teaches Estimate Bias)")
    d.add_argument("--on", type=parse_date, help="submission date, if not today (each day late uses a Grace Day)")
    d.set_defaults(fn=cmd_done)

    u = sub.add_parser("upcoming", parents=[common], help="open items due soon, with Start-by Dates")
    u.add_argument("--days", type=whole_number, default=14)
    u.set_defaults(fn=cmd_upcoming)

    c = sub.add_parser("crunch", parents=[common], help="corrected effort per week; flags Crunch Weeks")
    c.add_argument("--weeks", type=whole_number, default=4)
    c.set_defaults(fn=cmd_crunch)

    g = sub.add_parser("grace", parents=[common], help="Grace Day ledger per course")
    g.add_argument("--course", type=text)
    g.add_argument("--set", type=grace_days, help="set the course's Grace Day allowance (needs --course)")
    g.add_argument("--if-late", type=grace_days, help="show what a submission this many days late would leave")
    g.set_defaults(fn=cmd_grace)

    n = sub.add_parser("nudges", parents=[common], help="JSON list of items to act on today (for scheduled alert checks)")
    n.set_defaults(fn=cmd_nudges)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        state = load(args.state)
        if args.fn(state, args):
            save(args.state, state)
    except InputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
