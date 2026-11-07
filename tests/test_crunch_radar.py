"""Crunch Radar CLI tests (seam 3): a fixture state file and a fixed "today", CLI in, text/JSON/state file out.

Run: python3 scripts/test_crunch_radar.py (or tests/test_crunch_radar.py in the public tap repo).
Kept outside the skill folder: Hermes's install scan flags subprocess/os.environ in tests and blocks a community install.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

CLI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "skills", "crunch-radar", "scripts", "crunch_radar.py")


class CrunchRadar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "crunch_radar.json")
        # The default state path is under HERMES_HOME: point it here so a lost --state can't touch a real file.
        self.env = {**os.environ, "HERMES_HOME": self.tmp.name}
        self.env.pop("CRUNCH_RADAR_STATE", None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args, today="2026-11-07", ok=True):
        p = subprocess.run([sys.executable, CLI, "--state", self.state, "--today", today, *args],
                           capture_output=True, text=True, env=self.env)
        if ok:
            self.assertEqual(p.returncode, 0, p.stderr)
        return p

    def add(self, title, due, hours=None, course="CSCI599", today="2026-11-07"):
        args = ["add", "--title", title, "--due", due] + (["--course", course] if course else [])
        if hours is not None:
            args += ["--hours", str(hours)]
        return self.run_cli(*args, today=today).stdout

    # Start-by Date = due − ceil(effort × Estimate Bias ÷ pace) days; pace 2 h/day by default.
    def test_add_shows_start_by_date(self):
        out = self.add("A3", "2026-11-19", 12)
        self.assertIn("start by 2026-11-13", out)

    def test_upcoming_lists_items_with_start_by_dates_in_due_order(self):
        self.add("A3", "2026-11-19", 12)
        self.add("Quiz 4 prep", "2026-11-12", 3)
        out = self.run_cli("upcoming").stdout
        self.assertLess(out.index("Quiz 4 prep"), out.index("A3"))
        self.assertIn("start by 2026-11-10", out)  # 3 h / 2 h a day → 2 days
        self.assertIn("start by 2026-11-13", out)

    # Estimate Bias = total actual ÷ total estimated hours over completed items.
    def test_done_items_teach_estimate_bias_which_moves_new_start_by_dates(self):
        self.add("A1", "2026-11-01", 4, today="2026-10-20")
        self.add("A2", "2026-11-05", 6, today="2026-10-20")
        self.run_cli("done", "1", "--hours", "6", today="2026-11-01")
        out = self.run_cli("done", "2", "--hours", "9", today="2026-11-05").stdout
        self.assertIn("Estimate Bias: 1.5", out)
        # 12 h × 1.5 = 18 h at 2 h/day = 9 days before Nov 19
        self.assertIn("start by 2026-11-10", self.add("A3", "2026-11-19", 12))

    def test_estimate_bias_is_1_before_anything_is_done(self):
        self.assertIn("Estimate Bias: 1", self.run_cli("upcoming").stdout)

    def nudges(self, today):
        return json.loads(self.run_cli("nudges", today=today).stdout)["nudges"]

    # A3: 12 h due Nov 19 → start by Nov 13. hours/day = corrected hours ÷ days left before the due date.
    def test_nudges_escalate_once_past_the_start_by_date(self):
        self.add("A3", "2026-11-19", 12)
        self.assertEqual(self.nudges("2026-11-12"), [])
        cases = {"2026-11-13": ("start", 2.0), "2026-11-15": ("behind", 3.0),
                 "2026-11-17": ("urgent", 6.0), "2026-11-19": ("urgent", 12.0)}
        for today, (level, per_day) in cases.items():
            [n] = self.nudges(today)
            self.assertEqual((n["title"], n["level"], n["hours_per_day"], n["start_by"]),
                             ("A3", level, per_day, "2026-11-13"), today)
        [n] = self.nudges("2026-11-20")
        self.assertEqual((n["level"], n["days_late"]), ("overdue", 1))

    def test_done_items_stop_nudging(self):
        self.add("A3", "2026-11-19", 12)
        self.run_cli("done", "1", "--hours", "10", today="2026-11-15")
        self.assertEqual(self.nudges("2026-11-15"), [])

    def test_date_only_items_nudge_the_day_before_and_the_day_of(self):
        self.add("Drop deadline", "2026-11-13", course=None)
        self.assertEqual(self.nudges("2026-11-11"), [])
        self.assertEqual([n["level"] for n in self.nudges("2026-11-12")], ["date"])
        self.assertEqual([n["level"] for n in self.nudges("2026-11-13")], ["date"])
        self.assertEqual(self.nudges("2026-11-14"), [])

    # Crunch Week = a Monday–Sunday week whose open corrected effort due exceeds 15 h.
    def test_crunch_week_needs_more_than_the_threshold(self):
        self.add("Paper draft", "2026-11-18", 8)    # Wed, week of Mon Nov 16
        self.add("A3", "2026-11-20", 7)             # Fri, same week: exactly 15 h
        self.add("Lab 5", "2026-11-23", 6)          # next Monday: a different week
        out = self.run_cli("crunch").stdout
        self.assertNotIn("CRUNCH", out)
        self.assertIn("2026-11-16 to 2026-11-22: 15 h", out)
        self.add("Reading notes", "2026-11-22", 1)  # Sunday: same week, now 16 h
        out = self.run_cli("crunch").stdout
        self.assertIn("CRUNCH WEEK 2026-11-16 to 2026-11-22: 16 h", out)
        self.assertIn("2026-11-23 to 2026-11-29: 6 h", out)

    # Grace Days: 2 per course by default; each day late on a done item uses one.
    def test_grace_day_ledger_after_late_submissions(self):
        self.add("A1", "2026-10-10", 4, today="2026-10-01")
        self.add("A2", "2026-10-20", 4, today="2026-10-01")
        self.add("HW1", "2026-10-15", 2, course="MATH541", today="2026-10-01")
        self.run_cli("done", "1", "--hours", "4", "--on", "2026-10-11")   # 1 day late
        self.run_cli("done", "2", "--hours", "4", "--on", "2026-10-20")   # on time
        self.run_cli("done", "3", "--hours", "2", "--on", "2026-10-15")
        out = self.run_cli("grace").stdout
        self.assertIn("CSCI599: 1 of 2 Grace Days left", out)
        self.assertIn("MATH541: 2 of 2 Grace Days left", out)
        out = self.run_cli("grace", "--course", "CSCI599", "--if-late", "2").stdout
        self.assertIn("2 days late would leave -1", out)

    def test_grace_balance_can_be_set_per_course(self):
        self.run_cli("grace", "--course", "MATH541", "--set", "3")
        self.assertIn("MATH541: 3 of 3 Grace Days left", self.run_cli("grace").stdout)

    def test_bad_input_is_rejected_and_the_state_file_is_unchanged(self):
        self.add("A3", "2026-11-19", 12)
        with open(self.state, "rb") as f:
            before = f.read()
        bad = [["add", "--title", "X", "--due", "Nov 19"], ["add", "--title", "X", "--due", "2026-11-31"],
               ["add", "--title", "X", "--due", "2026-11-19", "--hours", "-3"],
               ["add", "--title", "X", "--due", "2026-11-19", "--hours", "lots"],
               ["add", "--title", "  ", "--due", "2026-11-19"],
               ["done", "7", "--hours", "3"], ["done", "1", "--hours", "0"], ["grace", "--set", "2"],
               ["grace", "--course", "CSCI599", "--set", "-1"]]
        for args in bad:
            p = self.run_cli(*args, ok=False)
            self.assertNotEqual(p.returncode, 0, args)
            self.assertIn("error", p.stderr, args)
            with open(self.state, "rb") as f:
                self.assertEqual(f.read(), before, args)

    def test_a_corrupt_state_file_is_reported_and_left_alone(self):
        with open(self.state, "w") as f:
            f.write('{"items": [')
        p = self.run_cli("add", "--title", "A3", "--due", "2026-11-19", ok=False)
        self.assertEqual(p.returncode, 2)
        self.assertIn("not valid JSON", p.stderr)
        with open(self.state) as f:
            self.assertEqual(f.read(), '{"items": [')

    def test_marking_an_item_done_twice_is_rejected(self):
        self.add("A3", "2026-11-19", 12)
        self.run_cli("done", "1", "--hours", "10")
        self.assertIn("already done", self.run_cli("done", "1", "--hours", "10", ok=False).stderr)

    def test_state_and_today_also_work_after_the_command(self):
        self.add("A3", "2026-11-19", 12)
        p = subprocess.run([sys.executable, CLI, "nudges", "--state", self.state, "--today", "2026-11-13"],
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(json.loads(p.stdout)["nudges"][0]["level"], "start")


if __name__ == "__main__":
    unittest.main()
