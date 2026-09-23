#!/usr/bin/env python3
"""Plan / fact / delta report for a Citeck Project Tracker (EPT) project.

Plan   = issue estimate (`estimatedWorks`, platform format "1w 2d 3h 30m").
         Epic plan = sum of children estimates when at least one child is
         estimated, otherwise the epic's own estimate.
Fact   = sum of time-tracking records (minutes), optionally limited to a period.
Delta  = plan - fact.
Norms  = 8h day, 5d week, 4w month (160h).
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))

from lib import config  # noqa: E402
from lib import records_api  # noqa: E402

ISSUE_SOURCE = "emodel/ept-issue"
ISSUE_ATTS = {
    "key": "issueKey?str",
    "summary": "summary?str",
    "type": "_type?localId",
    "epic": "epicLink.issueKey?str",
    "estimate": "estimatedWorks?str",
    "worklogs": "time-trackable:timeTracking[]{minutes:durationInMinutes?num,date:startDate?str,user:user?localId}",
}

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 8
DAYS_PER_WEEK = 5
WEEKS_PER_MONTH = 4

MINUTES_PER_DAY = HOURS_PER_DAY * MINUTES_PER_HOUR
MINUTES_PER_WEEK = DAYS_PER_WEEK * MINUTES_PER_DAY
MINUTES_PER_MONTH = WEEKS_PER_MONTH * MINUTES_PER_WEEK

# Same grammar as IssueWorkDurationUtils in ecos-project-tracker.
_DURATION_RE = re.compile(
    r"^\s*(?:(\d+)w)?\s*(?:(\d+)d)?\s*(?:(\d+)h)?\s*(?:(\d+)m)?\s*$"
)


def parse_work_duration(value):
    """Convert platform work duration ("1w 2d 3h 30m") to minutes."""
    if not value:
        return 0
    m = _DURATION_RE.match(value)
    if not m:
        raise ValueError(f'Unable to parse work duration "{value}"')
    weeks, days, hours, minutes = (int(x) if x else 0 for x in m.groups())
    return (
        weeks * MINUTES_PER_WEEK
        + days * MINUTES_PER_DAY
        + hours * MINUTES_PER_HOUR
        + minutes
    )


def to_norms(minutes):
    """Express minutes in hours / days / weeks / months by the norms."""
    hours = minutes / MINUTES_PER_HOUR
    return {
        "hours": hours,
        "days": hours / HOURS_PER_DAY,
        "weeks": hours / (HOURS_PER_DAY * DAYS_PER_WEEK),
        "months": hours / (HOURS_PER_DAY * DAYS_PER_WEEK * WEEKS_PER_MONTH),
    }


def _in_period(date, period):
    if not period:
        return True
    start, end = period
    day = (date or "")[:10]
    return (not start or day >= start) and (not end or day <= end)


def _row(item, plan, fact, **extra):
    row = {
        "key": item["key"],
        "summary": item.get("summary", ""),
        "type": item.get("type", ""),
        "plan": plan,
        "fact": fact,
        "delta": plan - fact,
    }
    row.update(extra)
    return row


def build_report(issues, period=None):
    """Aggregate issues into epics / orphans / totals / by_user."""
    by_user = defaultdict(int)

    def fact_of(item):
        total = 0
        for w in item.get("worklogs", []):
            if _in_period(w.get("date"), period):
                total += w["minutes"]
                by_user[w.get("user", "")] += w["minutes"]
        return total

    by_key = {i["key"]: i for i in issues}
    children = defaultdict(list)
    for i in issues:
        if i.get("epic_key") and i["epic_key"] in by_key:
            children[i["epic_key"]].append(i)

    epic_keys = [k for k in by_key if k in children]
    epics, orphans = [], []
    total_plan = total_fact = fact_unestimated = 0

    for item in issues:
        key = item["key"]
        if key in children:
            task_rows = [
                _row(c, parse_work_duration(c.get("estimate")), fact_of(c))
                for c in children[key]
            ]
            own_plan = parse_work_duration(item.get("estimate"))
            children_plan = sum(t["plan"] for t in task_rows)
            if any(t["plan"] for t in task_rows):
                plan, source = children_plan, "children"
            else:
                plan, source = own_plan, "own"
            fact = fact_of(item) + sum(t["fact"] for t in task_rows)
            epics.append(
                _row(item, plan, fact, plan_source=source, own_plan=own_plan, tasks=task_rows)
            )
            total_plan += plan
            total_fact += fact
            if plan == 0:
                fact_unestimated += fact
        elif item.get("epic_key") in epic_keys:
            continue  # counted inside its epic
        else:
            row = _row(item, parse_work_duration(item.get("estimate")), fact_of(item))
            orphans.append(row)
            total_plan += row["plan"]
            total_fact += row["fact"]
            if row["plan"] == 0:
                fact_unestimated += row["fact"]

    return {
        "period": list(period) if period else None,
        "epics": epics,
        "orphans": orphans,
        "totals": {
            "plan": total_plan,
            "fact": total_fact,
            "delta": total_plan - total_fact,
            "fact_unestimated": fact_unestimated,
        },
        "by_user": dict(by_user),
    }


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def _map_record(raw):
    a = raw.get("attributes", {})
    return {
        "id": raw.get("id"),
        "key": a.get("key") or "",
        "summary": a.get("summary") or "",
        "type": a.get("type") or "",
        "epic_key": a.get("epic") or None,
        "estimate": a.get("estimate") or "",
        "worklogs": [
            {"minutes": int(w.get("minutes") or 0), "date": w.get("date"), "user": w.get("user") or ""}
            for w in (a.get("worklogs") or [])
        ],
    }


def fetch_issues(project, epic=None, profile=None, config_dir=None, page_size=100):
    """Page through all issues of a project (workspace) and map them."""
    issues, skip = [], 0
    while True:
        resp = records_api.records_query(
            source_id=ISSUE_SOURCE,
            attributes=ISSUE_ATTS,
            page={"maxItems": page_size, "skipCount": skip},
            sort_by=[{"attribute": "_created", "ascending": True}],
            workspaces=[project],
            profile=profile,
            config_dir=config_dir,
        )
        records = resp.get("records", [])
        issues.extend(_map_record(r) for r in records)
        skip += len(records)
        if not resp.get("hasMore") or not records:
            break
    if epic:
        issues = [i for i in issues if i["key"] == epic or i["epic_key"] == epic]
    return issues


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _h(minutes):
    return f"{minutes / MINUTES_PER_HOUR:.1f}"


def _norms_str(minutes):
    n = to_norms(minutes)
    return f"{n['hours']:.1f} ч = {n['days']:.1f} дн = {n['weeks']:.2f} нед = {n['months']:.2f} мес"


def render_markdown(report, project):
    period = report.get("period")
    lines = [f"# План · факт · дельта — {project}", ""]
    lines.append(
        "Период факта: " + (f"{period[0] or '…'} — {period[1] or '…'}" if period else "весь")
    )
    lines.append("Нормы: 8 ч/день, 5 дн/нед, 4 нед/мес (160 ч). Дельта = план − факт, часы.")
    lines.append("")
    lines.append("| Ключ | Название | План, ч | Факт, ч | Дельта, ч |")
    lines.append("|---|---|---:|---:|---:|")

    def row(r, indent=""):
        lines.append(f"| {indent}{r['key']} | {r['summary']} | {_h(r['plan'])} | {_h(r['fact'])} | {_h(r['delta'])} |")

    for e in report["epics"]:
        marker = "[дети]" if e["plan_source"] == "children" else "[своя]"
        own = f" (своя оценка {_h(e['own_plan'])})" if e["plan_source"] == "children" and e["own_plan"] else ""
        lines.append(
            f"| **{e['key']}** | **{e['summary']}** {marker}{own} | **{_h(e['plan'])}** | **{_h(e['fact'])}** | **{_h(e['delta'])}** |"
        )
        for t in e["tasks"]:
            row(t, indent="↳ ")
    if report["orphans"]:
        lines.append("| | *Без эпика* | | | |")
        for t in report["orphans"]:
            row(t)
    tot = report["totals"]
    lines.append(f"| | **Итого** | **{_h(tot['plan'])}** | **{_h(tot['fact'])}** | **{_h(tot['delta'])}** |")
    lines.append("")
    lines.append(f"План по нормам: {_norms_str(tot['plan'])}")
    lines.append(f"Факт по нормам: {_norms_str(tot['fact'])}")
    lines.append(
        f"Факт без оценки (строки с планом 0): {_h(tot['fact_unestimated'])} ч — это не перерасход, а отсутствие оценки."
    )
    lines.append("")
    if report["by_user"]:
        lines.append("## Факт по людям")
        lines.append("")
        lines.append("| Пользователь | Часы |")
        lines.append("|---|---:|")
        for user, minutes in sorted(report["by_user"].items(), key=lambda kv: -kv[1]):
            lines.append(f"| {user} | {_h(minutes)} |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description="Plan / fact / delta for an EPT project")
    parser.add_argument("project", help="Project key (workspace), e.g. EMTC")
    parser.add_argument("--from", dest="date_from", help="Fact period start, YYYY-MM-DD")
    parser.add_argument("--to", dest="date_to", help="Fact period end, YYYY-MM-DD (inclusive)")
    parser.add_argument("--epic", help="Limit to one epic key and its children")
    parser.add_argument("--profile", help="Credentials profile (default: ept_profile or active)")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown")
    args = parser.parse_args(argv)

    config_dir = os.environ.get("CITECK_CONFIG_DIR")
    profile, _ = config.resolve_ept_profile(profile=args.profile, config_dir=config_dir)
    period = (args.date_from, args.date_to) if (args.date_from or args.date_to) else None

    try:
        issues = fetch_issues(args.project, epic=args.epic, profile=profile, config_dir=config_dir)
    except records_api.RecordsApiError as e:
        print(json.dumps({"ok": False, "error": str(e), "profile": profile}), file=sys.stderr)
        return 1

    report = build_report(issues, period=period)
    report["project"] = args.project
    report["profile"] = profile
    report["issues_total"] = len(issues)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report, project=args.project))
        print(f"Задач выгружено: {len(issues)}. Профиль: {profile}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
