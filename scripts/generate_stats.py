import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


USERNAME = "PublicStringTre"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "stats.svg"

GRAPHQL_URL = "https://api.github.com/graphql"


def get_github_token():
    token = os.getenv("GITHUB_TOKEN")

    if token:
        return token

    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()

    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError(
            "No GitHub token found. "
            "Run `gh auth login` locally or provide GITHUB_TOKEN."
        )


def graphql_request(token, query, variables=None):
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "PublicStringTre-profile-generator",
    }

    response = requests.post(
        GRAPHQL_URL,
        json={
            "query": query,
            "variables": variables or {},
        },
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()

    if "errors" in payload:
        raise RuntimeError(
            f"GitHub GraphQL error: {payload['errors']}"
        )

    return payload["data"]


def fetch_profile_metadata(token):
    query = """
    query($login: String!) {
      user(login: $login) {
        login
        createdAt

        contributionsCollection {
          contributionYears
        }

        repositories(
          first: 1
          ownerAffiliations: OWNER
        ) {
          totalCount
        }
      }
    }
    """

    data = graphql_request(
        token,
        query,
        {"login": USERNAME},
    )

    user = data.get("user")

    if not user:
        raise RuntimeError(
            f"Could not find GitHub user: {USERNAME}"
        )

    created_at = datetime.fromisoformat(
        user["createdAt"].replace("Z", "+00:00")
    )

    return {
        "created_at": created_at,
        "contribution_years":
            user["contributionsCollection"]["contributionYears"],
        "repositories":
            user["repositories"]["totalCount"],
    }


def fetch_year(token, year):
    now = datetime.now(timezone.utc)

    start = datetime(
        year,
        1,
        1,
        tzinfo=timezone.utc,
    )

    next_year = datetime(
        year + 1,
        1,
        1,
        tzinfo=timezone.utc,
    )

    end = next_year - timedelta(seconds=1)

    if end > now:
        end = now

    query = """
    query(
      $login: String!,
      $from: DateTime!,
      $to: DateTime!
    ) {
      user(login: $login) {
        contributionsCollection(
          from: $from,
          to: $to
        ) {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          restrictedContributionsCount

          contributionCalendar {
            totalContributions

            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """

    variables = {
        "login": USERNAME,
        "from": start.isoformat(),
        "to": end.isoformat(),
    }

    data = graphql_request(
        token,
        query,
        variables,
    )

    collection = data["user"]["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    days = {}

    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            date = day["date"]

            # Keep only dates actually belonging to this year.
            if date.startswith(f"{year}-"):
                days[date] = day["contributionCount"]

    return {
        "year": year,
        "contributions": calendar["totalContributions"],
        "commits": collection["totalCommitContributions"],
        "pull_requests":
            collection["totalPullRequestContributions"],
        "issues": collection["totalIssueContributions"],
        "restricted":
            collection["restrictedContributionsCount"],
        "days": days,
    }


def build_complete_calendar(
    raw_days,
    start_date,
    end_date,
):
    """
    Fill every calendar date between account creation and today.

    Missing dates become zero-contribution days. This is important
    for accurate all-time streak calculations.
    """

    calendar = []

    current = start_date

    while current <= end_date:
        date_string = current.isoformat()

        calendar.append(
            {
                "date": date_string,
                "count": raw_days.get(date_string, 0),
            }
        )

        current += timedelta(days=1)

    return calendar


def calculate_active_days(days):
    return sum(
        1
        for day in days
        if day["count"] > 0
    )


def calculate_current_streak(days):
    if not days:
        return 0

    index = len(days) - 1

    # Today may simply not have activity yet.
    if days[index]["count"] == 0:
        index -= 1

    streak = 0

    while index >= 0:
        if days[index]["count"] > 0:
            streak += 1
            index -= 1
        else:
            break

    return streak


def calculate_longest_streak(days):
    longest = 0
    current = 0

    for day in days:
        if day["count"] > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return longest


def get_last_365_days(days):
    cutoff = (
        datetime.now(timezone.utc).date()
        - timedelta(days=364)
    )

    return [
        day
        for day in days
        if datetime.strptime(
            day["date"],
            "%Y-%m-%d",
        ).date() >= cutoff
    ]


def calculate_recent_contributions(days):
    return sum(
        day["count"]
        for day in days
    )


def build_weekly_totals(days):
    """
    Turn the most recent 365 days into roughly 52 weekly values
    for the SVG activity signal.
    """

    values = []

    for index in range(0, len(days), 7):
        week = days[index:index + 7]

        values.append(
            sum(day["count"] for day in week)
        )

    return values[-52:]


def create_graph_points(
    values,
    x,
    y,
    width,
    height,
):
    if not values:
        return ""

    maximum = max(values)

    if maximum == 0:
        maximum = 1

    points = []
    count = len(values)

    for index, value in enumerate(values):

        if count == 1:
            px = x
        else:
            px = (
                x
                + (index / (count - 1))
                * width
            )

        normalized = value / maximum

        py = (
            y
            + height
            - (normalized * height)
        )

        points.append(
            f"{px:.1f},{py:.1f}"
        )

    return " ".join(points)


def fetch_all_time_stats(token):
    metadata = fetch_profile_metadata(token)

    now = datetime.now(timezone.utc)

    first_year = metadata["created_at"].year
    current_year = now.year

    raw_days = {}

    lifetime_contributions = 0
    lifetime_commits = 0
    lifetime_pull_requests = 0
    lifetime_issues = 0
    lifetime_restricted = 0

    print()
    print(
        f"Scanning GitHub history "
        f"{first_year} → {current_year}..."
    )

    for year in range(
        first_year,
        current_year + 1,
    ):
        print(f"  Fetching {year}...")

        result = fetch_year(
            token,
            year,
        )

        lifetime_contributions += (
            result["contributions"]
        )

        lifetime_commits += (
            result["commits"]
        )

        lifetime_pull_requests += (
            result["pull_requests"]
        )

        lifetime_issues += (
            result["issues"]
        )

        lifetime_restricted += (
            result["restricted"]
        )

        raw_days.update(
            result["days"]
        )

    created_date = metadata[
        "created_at"
    ].date()

    today = now.date()

    all_days = build_complete_calendar(
        raw_days,
        created_date,
        today,
    )

    recent_days = get_last_365_days(
        all_days
    )

    return {
        "contributions":
            lifetime_contributions,

        "commits":
            lifetime_commits,

        "pull_requests":
            lifetime_pull_requests,

        "issues":
            lifetime_issues,

        "private_contributions":
            lifetime_restricted,

        "repositories":
            metadata["repositories"],

        "active_days":
            calculate_active_days(all_days),

        "current_streak":
            calculate_current_streak(all_days),

        "longest_streak":
            calculate_longest_streak(all_days),

        "recent_contributions":
            calculate_recent_contributions(
                recent_days
            ),

        "recent_active_days":
            calculate_active_days(
                recent_days
            ),

        "weekly_totals":
            build_weekly_totals(
                recent_days
            ),

        "first_year":
            first_year,
    }


def generate_svg(stats):
    graph_points = create_graph_points(
        stats["weekly_totals"],
        x=65,
        y=405,
        width=870,
        height=70,
    )

    svg = f"""<svg
xmlns="http://www.w3.org/2000/svg"
width="1000"
height="590"
viewBox="0 0 1000 590"
role="img"
aria-labelledby="title desc">

<title id="title">
PublicStringTre GitHub Telemetry
</title>

<desc id="desc">
All-time GitHub statistics and recent activity
for Anthony Fieldings III.
</desc>

<defs>

    <linearGradient
        id="background"
        x1="0"
        y1="0"
        x2="1"
        y2="1"
    >
        <stop
            offset="0%"
            stop-color="#08080d"
        />

        <stop
            offset="60%"
            stop-color="#0d0914"
        />

        <stop
            offset="100%"
            stop-color="#160923"
        />
    </linearGradient>

    <linearGradient
        id="graphGradient"
        x1="0"
        y1="0"
        x2="1"
        y2="0"
    >
        <stop
            offset="0%"
            stop-color="#7c3aed"
        />

        <stop
            offset="50%"
            stop-color="#c084fc"
        />

        <stop
            offset="100%"
            stop-color="#8b5cf6"
        />
    </linearGradient>

    <filter
        id="glow"
        x="-50%"
        y="-50%"
        width="200%"
        height="200%"
    >
        <feGaussianBlur
            stdDeviation="3"
            result="blur"
        />

        <feMerge>
            <feMergeNode in="blur"/>
            <feMergeNode in="SourceGraphic"/>
        </feMerge>
    </filter>

</defs>


<!-- BACKGROUND -->

<rect
    x="1"
    y="1"
    width="998"
    height="588"
    rx="18"
    fill="url(#background)"
    stroke="#342044"
    stroke-width="2"
/>


<!-- TERMINAL BAR -->

<rect
    x="1"
    y="1"
    width="998"
    height="48"
    rx="18"
    fill="#111118"
/>

<rect
    x="1"
    y="30"
    width="998"
    height="19"
    fill="#111118"
/>

<circle
    cx="28"
    cy="25"
    r="6"
    fill="#ff5f57"
/>

<circle
    cx="49"
    cy="25"
    r="6"
    fill="#febc2e"
/>

<circle
    cx="70"
    cy="25"
    r="6"
    fill="#28c840"
/>

<text
    x="500"
    y="30"
    text-anchor="middle"
    fill="#777786"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="13"
>
    telemetry@publicstringtre: ~/github
</text>


<!-- TITLE -->

<text
    x="55"
    y="91"
    fill="#c084fc"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="14"
    font-weight="600"
    letter-spacing="2"
>
    02 // GITHUB TELEMETRY
</text>

<text
    x="55"
    y="120"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
>
    LIFETIME ACTIVITY // SINCE {stats["first_year"]}
</text>


<!-- LEFT TOP METRIC -->

<text
    x="55"
    y="184"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="38"
    font-weight="700"
>
    {stats["contributions"]:,}
</text>

<text
    x="55"
    y="211"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
    letter-spacing="1"
>
    CONTRIBUTIONS
</text>


<!-- RIGHT TOP METRIC -->

<text
    x="525"
    y="184"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="38"
    font-weight="700"
>
    {stats["commits"]:,}
</text>

<text
    x="525"
    y="211"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
    letter-spacing="1"
>
    COMMITS
</text>


<!-- LEFT BOTTOM METRIC -->

<text
    x="55"
    y="270"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="32"
    font-weight="700"
>
    {stats["repositories"]:,}
</text>

<text
    x="55"
    y="296"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
    letter-spacing="1"
>
    REPOSITORIES
</text>


<!-- RIGHT BOTTOM METRIC -->

<text
    x="525"
    y="270"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="32"
    font-weight="700"
>
    {stats["active_days"]:,}
</text>

<text
    x="525"
    y="296"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
    letter-spacing="1"
>
    ACTIVE DAYS
</text>


<!-- DIVIDER -->

<line
    x1="55"
    y1="326"
    x2="945"
    y2="326"
    stroke="#342044"
    stroke-width="1"
/>


<!-- STREAKS -->

<text
    x="55"
    y="362"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    CURRENT STREAK
</text>

<text
    x="166"
    y="362"
    fill="#c084fc"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="15"
    font-weight="700"
>
    {stats["current_streak"]} DAYS
</text>


<text
    x="390"
    y="362"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    LONGEST STREAK
</text>

<text
    x="509"
    y="362"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="15"
    font-weight="700"
>
    {stats["longest_streak"]} DAYS
</text>


<!-- RECENT ACTIVITY -->

<text
    x="55"
    y="402"
    fill="#c084fc"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
    font-weight="600"
    letter-spacing="1"
>
    LAST 365 DAYS
</text>

<text
    x="183"
    y="402"
    fill="#a1a1aa"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    {stats["recent_contributions"]:,} CONTRIBUTIONS
</text>

<text
    x="385"
    y="402"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    //
</text>

<text
    x="415"
    y="402"
    fill="#a1a1aa"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    {stats["recent_active_days"]:,} ACTIVE DAYS
</text>


<!-- GRAPH -->

<line
    x1="65"
    y1="475"
    x2="935"
    y2="475"
    stroke="#27272a"
    stroke-width="1"
/>

<polyline
    points="{graph_points}"
    fill="none"
    stroke="url(#graphGradient)"
    stroke-width="3"
    stroke-linecap="round"
    stroke-linejoin="round"
    filter="url(#glow)"
/>


<!-- BOTTOM STATUS -->

<circle
    cx="61"
    cy="535"
    r="5"
    fill="#22c55e"
/>

<text
    x="75"
    y="540"
    fill="#a1a1aa"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
>
    SYSTEM ONLINE
</text>

<text
    x="945"
    y="540"
    text-anchor="end"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    ALL-TIME DATA // GITHUB API
</text>

</svg>
"""

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.write_text(
        svg,
        encoding="utf-8",
    )
def main():
    print("Connecting to GitHub...")

    token = get_github_token()

    print(
        f"Fetching all-time telemetry "
        f"for @{USERNAME}..."
    )

    stats = fetch_all_time_stats(
        token
    )

    generate_svg(
        stats
    )

    print()
    print("ALL-TIME GITHUB TELEMETRY")
    print("-------------------------")

    print(
        f"Contributions:      "
        f"{stats['contributions']:,}"
    )

    print(
        f"Commits:            "
        f"{stats['commits']:,}"
    )

    print(
        f"Pull requests:      "
        f"{stats['pull_requests']:,}"
    )

    print(
        f"Repositories:       "
        f"{stats['repositories']:,}"
    )

    print(
        f"Active days:        "
        f"{stats['active_days']:,}"
    )

    print(
        f"Current streak:     "
        f"{stats['current_streak']} days"
    )

    print(
        f"Longest streak:     "
        f"{stats['longest_streak']} days"
    )

    print()
    print("LAST 365 DAYS")
    print("-------------")

    print(
        f"Contributions:      "
        f"{stats['recent_contributions']:,}"
    )

    print(
        f"Active days:        "
        f"{stats['recent_active_days']:,}"
    )

    print()
    print(
        f"Generated: {OUTPUT}"
    )


if __name__ == "__main__":
    main()