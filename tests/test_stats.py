import unittest
from datetime import date, datetime, timedelta, timezone

from scripts.update_stats import END, START, render_stats, replace_stats, summarize_days


class StatsTests(unittest.TestCase):
    def test_streak_breaks_on_a_missing_day_and_ignores_future_activity(self):
        today = date(2026, 10, 9)
        raw = [
            {"date": "2026-10-03", "contributionCount": 1},
            {"date": "2026-10-04", "contributionCount": 2},
            {"date": "2026-10-06", "contributionCount": 3},
            {"date": "2026-10-07", "contributionCount": 4},
            {"date": "2026-10-08", "contributionCount": 4},
            {"date": "2026-10-09", "contributionCount": 0},
            {"date": "2026-10-10", "contributionCount": 100},
        ]
        stats = summarize_days(raw, today)
        self.assertEqual(stats["longest_streak"], 3)
        self.assertEqual(stats["active_days"], 5)
        self.assertEqual(stats["year"], 14)
        self.assertEqual(stats["busiest_date"], date(2026, 10, 8))

    def test_rolling_windows_include_the_cutoff_day_and_leave_out_older_days(self):
        today = date(2026, 10, 9)
        raw = [
            {"date": (today - timedelta(days=365)).isoformat(), "contributionCount": 100},
            {"date": (today - timedelta(days=364)).isoformat(), "contributionCount": 2},
            {"date": (today - timedelta(days=30)).isoformat(), "contributionCount": 3},
            {"date": (today - timedelta(days=29)).isoformat(), "contributionCount": 4},
            {"date": today.isoformat(), "contributionCount": 5},
        ]
        stats = summarize_days(raw, today)
        self.assertEqual(stats["year"], 14)
        self.assertEqual(stats["month"], 9)

    def test_quiet_calendar_has_no_busiest_day_and_excludes_profile_and_forks(self):
        now = datetime(2026, 10, 9, tzinfo=timezone.utc)
        activity = {
            "totalPullRequestContributions": 0,
            "contributionCalendar": {"weeks": [{"contributionDays": [
                {"date": "2026-10-09", "contributionCount": 0}
            ]}]},
        }
        repos = [
            {"name": "ak91hu", "isFork": False, "stargazerCount": 50, "forkCount": 50},
            {"name": "fork", "isFork": True, "stargazerCount": 50, "forkCount": 50},
            {"name": "app", "isFork": False, "stargazerCount": 2, "forkCount": 3},
        ]
        rendered = render_stats(activity, repos, "ak91hu", now)
        self.assertIn("No activity yet", rendered)
        self.assertIn("| Public repositories | 1 |", rendered)
        self.assertIn("2 stars and 3 forks", rendered)

    def test_refresh_preserves_the_introduction_and_rejects_broken_markers(self):
        intro = "# Hi, I'm Ákos\n\nMy introduction.\n"
        ending = "\nA link I want to keep.\n"
        result = replace_stats(intro + START + "old" + END + ending, "new")
        self.assertEqual(result, intro + START + "\nnew\n" + END + ending)
        with self.assertRaises(ValueError):
            replace_stats(intro, "new")
        with self.assertRaises(ValueError):
            replace_stats(START + START + END, "new")


if __name__ == "__main__":
    unittest.main()
