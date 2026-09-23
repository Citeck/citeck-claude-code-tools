"""Tests for citeck-planfact skill script (plan / fact / delta arithmetic)."""
import os
import sys
import unittest
import unittest.mock

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "skills", "citeck-planfact", "scripts"),
)

import planfact  # noqa: E402


def issue(key, estimate="", epic=None, worklogs=None, issue_type="Task", summary=None):
    return {
        "key": key,
        "summary": summary or key,
        "type": issue_type,
        "epic_key": epic,
        "estimate": estimate,
        "worklogs": worklogs or [],
    }


def log(minutes, date="2026-08-10", user="ivan"):
    return {"minutes": minutes, "date": date, "user": user}


class TestParseWorkDuration(unittest.TestCase):
    def test_full_format_uses_platform_norms(self):
        # 1w = 5d, 1d = 8h → (5*8 + 2*8 + 3) * 60 + 30 = 3570
        self.assertEqual(planfact.parse_work_duration("1w 2d 3h 30m"), 3570)

    def test_hours_only(self):
        self.assertEqual(planfact.parse_work_duration("4h"), 240)

    def test_empty_and_none_are_zero(self):
        self.assertEqual(planfact.parse_work_duration(""), 0)
        self.assertEqual(planfact.parse_work_duration(None), 0)


class TestNorms(unittest.TestCase):
    def test_minutes_to_hours_days_weeks_months(self):
        # 8h day, 5d week, 4w month → 160h month
        n = planfact.to_norms(160 * 60)
        self.assertEqual(n, {"hours": 160.0, "days": 20.0, "weeks": 4.0, "months": 1.0})


class TestEpicPlanRule(unittest.TestCase):
    def test_epic_plan_is_sum_of_children_when_any_child_estimated(self):
        report = planfact.build_report([
            issue("E-1", estimate="1w", issue_type="Epic"),
            issue("E-2", estimate="2h", epic="E-1"),
            issue("E-3", estimate="", epic="E-1"),
        ])
        epic = report["epics"][0]
        self.assertEqual(epic["key"], "E-1")
        self.assertEqual(epic["plan"], 120)
        self.assertEqual(epic["plan_source"], "children")

    def test_epic_plan_is_own_estimate_when_no_child_estimated(self):
        report = planfact.build_report([
            issue("E-1", estimate="1d", issue_type="Epic"),
            issue("E-2", estimate="", epic="E-1"),
        ])
        epic = report["epics"][0]
        self.assertEqual(epic["plan"], 480)
        self.assertEqual(epic["plan_source"], "own")

    def test_tasks_without_epic_go_to_orphans(self):
        report = planfact.build_report([issue("E-9", estimate="1h")])
        self.assertEqual(report["epics"], [])
        self.assertEqual([t["key"] for t in report["orphans"]], ["E-9"])


class TestFactAndDelta(unittest.TestCase):
    def test_fact_is_sum_of_worklogs_and_delta_is_plan_minus_fact(self):
        report = planfact.build_report([
            issue("E-1", estimate="4h", worklogs=[log(60), log(120)]),
        ])
        task = report["orphans"][0]
        self.assertEqual(task["fact"], 180)
        self.assertEqual(task["delta"], 60)

    def test_epic_fact_includes_own_and_children_worklogs(self):
        report = planfact.build_report([
            issue("E-1", estimate="", issue_type="Epic", worklogs=[log(30)]),
            issue("E-2", estimate="1h", epic="E-1", worklogs=[log(45)]),
        ])
        epic = report["epics"][0]
        self.assertEqual(epic["fact"], 75)
        self.assertEqual(epic["delta"], 60 - 75)

    def test_totals_sum_epics_and_orphans_without_double_counting(self):
        report = planfact.build_report([
            issue("E-1", estimate="1d", issue_type="Epic", worklogs=[log(10)]),
            issue("E-2", estimate="2h", epic="E-1", worklogs=[log(20)]),
            issue("E-3", estimate="1h", worklogs=[log(30)]),
        ])
        # epic plan = children (120), not own (480)
        self.assertEqual(report["totals"], {"plan": 180, "fact": 60, "delta": 120, "fact_unestimated": 0})


class TestPeriodFilter(unittest.TestCase):
    def test_only_worklogs_inside_period_count_toward_fact(self):
        report = planfact.build_report(
            [issue("E-1", estimate="1h", worklogs=[
                log(10, date="2026-07-31"),
                log(20, date="2026-08-01"),
                log(30, date="2026-08-31"),
                log(40, date="2026-09-01"),
            ])],
            period=("2026-08-01", "2026-08-31"),
        )
        self.assertEqual(report["orphans"][0]["fact"], 50)

    def test_plan_is_not_affected_by_period(self):
        report = planfact.build_report(
            [issue("E-1", estimate="1h", worklogs=[log(10, date="2020-01-01")])],
            period=("2026-08-01", "2026-08-31"),
        )
        self.assertEqual(report["orphans"][0]["plan"], 60)
        self.assertEqual(report["orphans"][0]["fact"], 0)


class TestUnestimatedFact(unittest.TestCase):
    def test_totals_report_fact_logged_on_rows_without_estimate(self):
        report = planfact.build_report([
            issue("E-1", estimate="", issue_type="Epic", worklogs=[log(10)]),
            issue("E-2", estimate="", epic="E-1", worklogs=[log(20)]),
            issue("E-3", estimate="1h", worklogs=[log(30)]),
            issue("E-4", estimate="", worklogs=[log(40)]),
        ])
        # epic E-1 has no plan at all (10 + 20), orphan E-4 has none (40); E-3 is estimated
        self.assertEqual(report["totals"]["fact_unestimated"], 70)

    def test_markdown_shows_unestimated_fact_line(self):
        report = planfact.build_report([issue("E-4", estimate="", worklogs=[log(90)])])
        md = planfact.render_markdown(report, project="X")
        self.assertIn("без оценки", md)
        self.assertIn("1.5", md)


class TestByUser(unittest.TestCase):
    def test_fact_is_broken_down_by_user(self):
        report = planfact.build_report([
            issue("E-1", worklogs=[log(10, user="ivan"), log(20, user="olga")]),
            issue("E-2", worklogs=[log(30, user="ivan")]),
        ])
        self.assertEqual(report["by_user"], {"ivan": 40, "olga": 20})


class TestRenderMarkdown(unittest.TestCase):
    def test_markdown_has_epic_task_rows_totals_and_source_marker(self):
        report = planfact.build_report([
            issue("E-1", estimate="1d", issue_type="Epic", summary="Эпик"),
            issue("E-2", estimate="2h", epic="E-1", summary="Задача", worklogs=[log(60)]),
        ])
        md = planfact.render_markdown(report, project="EMTC")
        self.assertIn("E-1", md)
        self.assertIn("[дети]", md)
        self.assertIn("E-2", md)
        self.assertIn("Итого", md)
        # totals: plan 2h, fact 1h, delta 1h
        self.assertRegex(md, r"Итого.*\b2\.0\b.*\b1\.0\b.*\b1\.0\b")

    def test_markdown_shows_period_and_norms_line(self):
        report = planfact.build_report(
            [issue("E-1", estimate="1w", worklogs=[log(480, date="2026-08-05")])],
            period=("2026-08-01", "2026-08-31"),
        )
        md = planfact.render_markdown(report, project="EMTC")
        self.assertIn("2026-08-01", md)
        self.assertIn("8 ч/день", md)


class TestFetchIssues(unittest.TestCase):
    """Paging through emodel/ept-issue and mapping raw records to issue dicts."""

    def _page(self, records, has_more):
        return {"records": records, "hasMore": has_more, "totalCount": 0}

    def test_pages_until_has_more_is_false_and_maps_records(self):
        raw1 = {
            "id": "emodel/ept-issue@1",
            "attributes": {
                "key": "EMTC-1", "summary": "Эпик", "type": "Epic",
                "epic": None, "estimate": "1w",
                "worklogs": [{"minutes": 30, "date": "2026-08-01T10:00:00Z", "user": "ivan"}],
            },
        }
        raw2 = {
            "id": "emodel/ept-issue@2",
            "attributes": {
                "key": "EMTC-2", "summary": "Задача", "type": "Task",
                "epic": "EMTC-1", "estimate": "",
                "worklogs": [],
            },
        }
        calls = []

        def fake_query(**kwargs):
            calls.append(kwargs)
            return self._page([raw1], True) if len(calls) == 1 else self._page([raw2], False)

        with unittest.mock.patch.object(planfact.records_api, "records_query", side_effect=fake_query):
            issues = planfact.fetch_issues("EMTC", profile="p", page_size=1)

        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["workspaces"], ["EMTC"])
        self.assertEqual(calls[0]["page"], {"maxItems": 1, "skipCount": 0})
        self.assertEqual(calls[1]["page"], {"maxItems": 1, "skipCount": 1})
        self.assertEqual(calls[0]["profile"], "p")
        self.assertEqual(issues[0]["key"], "EMTC-1")
        self.assertEqual(issues[0]["epic_key"], None)
        self.assertEqual(issues[0]["worklogs"], [{"minutes": 30, "date": "2026-08-01T10:00:00Z", "user": "ivan"}])
        self.assertEqual(issues[1]["epic_key"], "EMTC-1")

    def test_epic_filter_keeps_epic_and_its_children_only(self):
        raws = [
            {"id": "a", "attributes": {"key": "E-1", "summary": "", "type": "Epic", "epic": None, "estimate": "", "worklogs": []}},
            {"id": "b", "attributes": {"key": "E-2", "summary": "", "type": "Task", "epic": "E-1", "estimate": "", "worklogs": []}},
            {"id": "c", "attributes": {"key": "E-3", "summary": "", "type": "Task", "epic": None, "estimate": "", "worklogs": []}},
        ]
        with unittest.mock.patch.object(planfact.records_api, "records_query", return_value=self._page(raws, False)):
            issues = planfact.fetch_issues("EMTC", epic="E-1")
        self.assertEqual([i["key"] for i in issues], ["E-1", "E-2"])


if __name__ == "__main__":
    unittest.main()
