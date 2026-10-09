"""Refresh the profile with visible GitHub activity and public repository totals."""

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen


START = "<!-- github-stats:start -->"
END = "<!-- github-stats:end -->"
README = Path(__file__).resolve().parents[1] / "README.md"

ACTIVITY_QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalPullRequestContributions
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

REPOSITORIES_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER,
                 privacy: PUBLIC) {
      nodes { name isFork stargazerCount forkCount }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""


def graphql(query, variables, token):
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-stats",
        },
        method="POST",
    )
    with urlopen(request, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        messages = ", ".join(error["message"] for error in payload["errors"])
        raise RuntimeError(f"GitHub could not return the stats: {messages}")
    if not payload.get("data", {}).get("user"):
        raise RuntimeError("GitHub did not return the requested user")
    return payload["data"]["user"]


def fetch_data(login, now, token):
    first_day = now.date() - timedelta(days=364)
    since = datetime.combine(first_day, time.min, timezone.utc)
    activity = graphql(
        ACTIVITY_QUERY,
        {"login": login, "from": since.isoformat(), "to": now.isoformat()},
        token,
    )["contributionsCollection"]
    repositories = []
    cursor = None
    while True:
        page = graphql(
            REPOSITORIES_QUERY, {"login": login, "cursor": cursor}, token
        )["repositories"]
        repositories.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        next_cursor = page["pageInfo"]["endCursor"]
        if not next_cursor or next_cursor == cursor:
            raise RuntimeError("GitHub returned an invalid repository page")
        cursor = next_cursor
    return activity, repositories


def summarize_days(raw_days, today):
    first_day = today - timedelta(days=364)
    counts = {}
    for entry in raw_days:
        day = date.fromisoformat(entry["date"])
        count = entry["contributionCount"]
        if not isinstance(count, int) or count < 0:
            raise ValueError("Invalid contribution count")
        if first_day <= day <= today:
            counts[day] = count

    if not counts:
        raise ValueError("GitHub returned no contribution calendar days")
    # Fill quiet or missing dates so a gap cannot inflate an activity streak.
    days = [(first_day + timedelta(days=i)) for i in range(365)]
    run = longest = 0
    for day in days:
        run = run + 1 if counts.get(day, 0) > 0 else 0
        longest = max(longest, run)
    busiest = max(counts, key=lambda day: (counts[day], day))
    recent_start = today - timedelta(days=29)
    return {
        "year": sum(counts.values()),
        "month": sum(count for day, count in counts.items() if day >= recent_start),
        "active_days": sum(count > 0 for count in counts.values()),
        "longest_streak": longest,
        "busiest_date": busiest,
        "busiest_count": counts[busiest],
    }


def render_stats(activity, repositories, login, now):
    raw_days = [
        day
        for week in activity["contributionCalendar"]["weeks"]
        for day in week["contributionDays"]
    ]
    stats = summarize_days(raw_days, now.date())
    projects = [
        repo for repo in repositories
        if not repo["isFork"] and repo["name"].casefold() != login.casefold()
    ]
    stars = sum(repo["stargazerCount"] for repo in projects)
    forks = sum(repo["forkCount"] for repo in projects)
    if stats["busiest_count"]:
        busiest = (
            f"{stats['busiest_date']:%d %b %Y} "
            f"with {stats['busiest_count']:,} contributions"
        )
    else:
        busiest = "No activity yet"
    rows = [
        ("Contributions in the past year", f"{stats['year']:,}"),
        ("Contributions in the past 30 days", f"{stats['month']:,}"),
        ("Days with activity in the past year", f"{stats['active_days']:,}"),
        ("Longest daily streak in the past year", f"{stats['longest_streak']:,} days"),
        ("Busiest day in the past year", busiest),
        ("Pull requests opened in the past year", f"{activity['totalPullRequestContributions']:,}"),
        ("Public repositories", f"{len(projects):,}"),
        ("Stars and forks across those repositories", f"{stars:,} stars and {forks:,} forks"),
    ]
    table = "| What | Count |\n| :--- | :--- |\n"
    table += "\n".join(f"| {label} | {value} |" for label, value in rows)
    return (
        table
        + f"\n\nLast updated {now:%d %b %Y at %H:%M} UTC.\n\n"
        + "Activity follows GitHub's visible contribution calendar over the past 365 days. "
        + "Repository totals leave out forks and this profile repo."
    )


def replace_stats(readme, stats):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("The README must contain exactly one pair of stats markers")
    before, rest = readme.split(START)
    _, after = rest.split(END)
    return f"{before}{START}\n{stats}\n{END}{after}"


def main():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("A GitHub token is required to read the stats")
    login = os.environ.get("PROFILE_USERNAME", "ak91hu")
    now = datetime.now(timezone.utc)
    original = README.read_text(encoding="utf-8")
    # Check the markers before fetching, and only write after every request succeeds.
    replace_stats(original, "")
    activity, repositories = fetch_data(login, now, token)
    stats = render_stats(activity, repositories, login, now)
    updated = replace_stats(original, stats)
    if updated != original:
        README.write_text(updated, encoding="utf-8")
    print("Profile stats refreshed from GitHub")


if __name__ == "__main__":
    main()
