# Crunch Radar: a Hermes skill tap

Crunch Radar is a [Hermes Agent](https://hermes-agent.nousresearch.com/) skill for students. Most reminder apps
tell you when something is *due*. Crunch Radar tells you when to *start* it.

- **Start-by Date**: the latest day to begin, worked back from your effort estimate at a sustainable pace
  (default 2 hours a day).
- **Escalating nudges** once you are past that date, showing how many hours a day you now need.
- **Crunch Week** warnings when a week's total effort crosses a threshold (default 15 hours).
- **Grace Day ledger** per course: how many late days you have left, and what a late submission would leave you with.
- **Estimate Bias**: log the hours a finished item really took, and future Start-by Dates are corrected by how
  far off your estimates tend to be.

It needs no API keys, accounts or network access. All state is one JSON file, and the script uses only the
Python standard library.

## Install

```sh
hermes skills tap add RottenBanana420/hermes-crunch-radar
hermes skills install RottenBanana420/hermes-crunch-radar/crunch-radar
```

Then ask your agent something like *"A3 is due Nov 19, about 12 hours. When should I start?"*

## Use it without the agent

```sh
CR="python3 ~/.hermes/skills/crunch-radar/scripts/crunch_radar.py"
$CR add --title "A3" --due 2026-11-19 --hours 12 --course CSCI599
# added #1 A3 [CSCI599]: due 2026-11-19, start by 2026-11-13 (12 h est, 12 h corrected)
$CR upcoming            # open items with Start-by Dates
$CR crunch              # effort per week, Crunch Weeks flagged
$CR grace --if-late 1   # Grace Days left per course
$CR nudges              # JSON: what to act on today (for scheduled checks)
$CR done 1 --hours 15   # log real hours; this updates Estimate Bias
```

If `hermes skills install` placed the skill in a category folder, run `hermes skills list` to find its path.

Every command accepts `--today YYYY-MM-DD` to pretend it is another day, and `--state PATH` to use another state
file. The default state file is `$HERMES_HOME/crunch_radar.json`. The daily pace, the Crunch Week threshold and
the default Grace Days per course live in that file's `settings` object. [SKILL.md](skills/crunch-radar/SKILL.md)
has the formulas.

Bad input (an unparseable date, negative hours, an unknown item) exits with code 2 and leaves the state file
untouched.

## Tests

```sh
python3 skills/crunch-radar/tests/test_crunch_radar.py
```

The tests drive the CLI with a fixture state file and a fixed "today". They cover the Start-by maths,
escalation, Crunch Weeks at and around the threshold, the Grace Day ledger after late submissions, Estimate Bias,
and rejection of bad input. They need Python 3.9 or later.

## Layout

This repo is a Hermes skill tap: one folder per skill under `skills/`.

```
skills/crunch-radar/
  SKILL.md                 instructions the agent loads
  scripts/crunch_radar.py  the CLI
  tests/                   CLI tests
```

Built for USC CSCI 599 (Agentic AI), Assignment 3. MIT licensed.
