---
name: crunch-radar
description: Student deadline radar. Tracks assignments, exams and admin dates, says when to START each one (Start-by Date), warns about Crunch Weeks, keeps a per-course Grace Day ledger, and learns the student's Estimate Bias from actual hours.
version: 1.0.0
author: Kusai Hajuri
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [students, deadlines, planning, reminders, productivity]
    related_skills: []
---

# Crunch Radar

Tracks a student's Crunch Items (assignments, exams, admin deadlines) in one JSON file and answers
"when must I start?", "is a crunch week coming?" and "how many grace days do I have left?".
No credentials and no network: one standard-library Python script.

## When to Use

- The user mentions coursework with a due date ("A3 due Nov 19, about 12 hours") → `add`.
- The user finished something ("submitted A3, took 15 hours") → `done` with the real hours.
- The user asks what's coming up, when to start, whether a week looks heavy, or about late/grace days.
- A briefing or scheduled check needs today's Crunch Radar status → `nudges`, `upcoming`, `crunch`.

## Quick Reference

Every command is `python3 ${HERMES_SKILL_DIR}/scripts/crunch_radar.py <command> …`; the table shortens that to `CR`.

| Task | Command |
|---|---|
| Add an item with an Effort Estimate | `CR add --title "A3" --due 2026-11-19 --hours 12 --course CSCI599` |
| Add a date-only item (exam day, drop deadline) | `CR add --title "Drop deadline" --due 2026-11-13 --kind admin` |
| Mark done, with actual hours | `CR done 3 --hours 15` (add `--on YYYY-MM-DD` if submitted on another day) |
| Open items in the next N days | `CR upcoming --days 14` |
| Crunch Weeks ahead | `CR crunch --weeks 4` |
| Grace Day ledger | `CR grace` · what-if: `CR grace --course CSCI599 --if-late 1` |
| Set a course's Grace Day allowance | `CR grace --course CSCI599 --set 2` |
| What to act on today (JSON) | `CR nudges` |

Every command takes `--today YYYY-MM-DD` (default: the system date) and `--state PATH`
(default `$HERMES_HOME/crunch_radar.json`, or `$CRUNCH_RADAR_STATE`).

## Procedure

1. Turn the user's words into the command's arguments yourself: dates as `YYYY-MM-DD` (assume the
   next occurrence of a date with no year), hours as a number, a course code if one is given.
   Leave `--hours` out when no effort applies. Don't invent an estimate; ask if it's unclear.
2. Run the command with the `terminal` tool and relay the result in plain words. Lead with the
   Start-by Date after an `add`, and with the new Estimate Bias after a `done`.
3. To mark something done you need its `#id`: run `upcoming` first if you don't have it.
4. For `nudges`, an empty `nudges` list means there is nothing to say. Levels:
   `date` (date-only item due today or tomorrow), `start` (start today),
   `behind` (past the Start-by Date, still at most 2× the daily pace), `urgent` (more than 2×),
   `overdue` (past due and not done; mention the Grace Days left). Quote `hours_per_day`.

## How it calculates

- **Estimate Bias** = total actual hours ÷ total estimated hours over done items (1.0 until one is done).
- **Start-by Date** = due date − ceil(estimate × Estimate Bias ÷ daily pace) days. Pace defaults to 2 h/day.
- **Crunch Week** = a Monday–Sunday week whose open corrected effort due is above the threshold (default 15 h).
- **Grace Days**: each day a done item was submitted after its due date uses one from its course
  (default 2 per course).
- Pace, threshold and the default allowance live in the state file's `settings` object.

## Pitfalls

- Exit code 2 with `error:` on stderr means the input was rejected and the state file was not touched.
  Show the error and ask the user to correct the value; don't retry with a guess.
- Ids are per state file. Never edit the JSON file by hand to add or complete items.

## Verification

After `add`, the output line starts with `added #<id>` and shows `start by <date>` (or `date only`).
`upcoming` should then list the item.
