import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


USERNAME = "PublicStringTre"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "stats.svg"

GRAPHQL_URL = "https://api.github.com/graphql"
REST_USER_URL = f"https://api.github.com/users/{USERNAME}"


def get_github_token():
    """
    Use GITHUB_TOKEN when running in GitHub Actions.

    When developing locally, securely retrieve the token
    from the authenticated GitHub CLI.
    """

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
            "No GitHub token found.\n"
            "Run `gh auth login` locally or provide GITHUB_TOKEN."
        )


def fetch_github_stats(token):
    """
    Fetch the last 365 days of GitHub contribution data.
    """

    now = datetime.now(timezone.utc)

    # 365-day window
    start = now - timedelta(days=364)

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
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
        "to": now.isoformat(),
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "PublicStringTre-profile-generator",
    }

    response = requests.post(
        GRAPHQL_URL,
        json={
            "query": query,
            "variables": variables,
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

    user = payload.get("data", {}).get("user")

    if not user:
        raise RuntimeError(
            f"Could not find GitHub user: {USERNAME}"
        )

    contributions = user["contributionsCollection"]
    calendar = contributions["contributionCalendar"]

    # Also fetch basic public-profile statistics
    rest_response = requests.get(
        REST_USER_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "PublicStringTre-profile-generator",
        },
        timeout=30,
    )

    rest_response.raise_for_status()

    profile = rest_response.json()

    days = []

    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            days.append(
                {
                    "date": day["date"],
                    "count": day["contributionCount"],
                }
            )

    days.sort(key=lambda item: item["date"])

    return {
        "total_contributions": calendar["totalContributions"],
        "commits": contributions["totalCommitContributions"],
        "pull_requests": contributions[
            "totalPullRequestContributions"
        ],
        "issues": contributions["totalIssueContributions"],
        "private_contributions": contributions[
            "restrictedContributionsCount"
        ],
        "public_repos": profile.get("public_repos", 0),
        "followers": profile.get("followers", 0),
        "days": days,
        "weeks": calendar["weeks"],
    }


def calculate_active_days(days):
    return sum(1 for day in days if day["count"] > 0)


def calculate_current_streak(days):
    """
    Calculate current contribution streak.

    If today has no contribution yet, yesterday is allowed
    to be the end of the current streak.
    """

    if not days:
        return 0

    today = datetime.now(timezone.utc).date()

    index = len(days) - 1

    last_date = datetime.strptime(
        days[index]["date"],
        "%Y-%m-%d",
    ).date()

    # If today has no contribution yet, start with yesterday.
    if last_date == today and days[index]["count"] == 0:
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


def get_weekly_totals(weeks):
    totals = []

    for week in weeks:
        total = sum(
            day["contributionCount"]
            for day in week["contributionDays"]
        )

        totals.append(total)

    # Keep the most recent 52 weeks.
    return totals[-52:]


def create_graph_points(values, x, y, width, height):
    """
    Convert weekly contribution totals into SVG points.
    """

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
            px = x + (index / (count - 1)) * width

        normalized = value / maximum

        py = y + height - (normalized * height)

        points.append(f"{px:.1f},{py:.1f}")

    return " ".join(points)


def generate_svg(stats):
    active_days = calculate_active_days(stats["days"])

    current_streak = calculate_current_streak(
        stats["days"]
    )

    longest_streak = calculate_longest_streak(
        stats["days"]
    )

    weekly_totals = get_weekly_totals(stats["weeks"])

    graph_points = create_graph_points(
        weekly_totals,
        x=65,
        y=330,
        width=870,
        height=75,
    )

    svg = f"""<svg
    xmlns="http://www.w3.org/2000/svg"
    width="1000"
    height="500"
    viewBox="0 0 1000 500"
    role="img"
    aria-labelledby="title desc"
>
    <title id="title">
        PublicStringTre GitHub Telemetry
    </title>

    <desc id="desc">
        Automatically generated GitHub statistics for Anthony Fieldings III.
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
        height="498"
        rx="18"
        fill="url(#background)"
        stroke="#342044"
        stroke-width="2"
    />


    <!-- TERMINAL HEADER -->

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


    <!-- SECTION TITLE -->

    <text
        x="55"
        y="95"
        fill="#c084fc"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="14"
        letter-spacing="2"
    >
        02 // GITHUB TELEMETRY
    </text>

    <text
        x="55"
        y="125"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="13"
    >
        PROFILE ACTIVITY // LAST 365 DAYS
    </text>


    <!-- PRIMARY METRIC 1 -->

    <text
        x="55"
        y="190"
        fill="#ffffff"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="34"
        font-weight="700"
    >
        {stats["total_contributions"]:,}
    </text>

    <text
        x="55"
        y="216"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        CONTRIBUTIONS
    </text>


    <!-- PRIMARY METRIC 2 -->

    <text
        x="290"
        y="190"
        fill="#ffffff"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="34"
        font-weight="700"
    >
        {stats["commits"]:,}
    </text>

    <text
        x="290"
        y="216"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        COMMITS
    </text>


    <!-- PRIMARY METRIC 3 -->

    <text
        x="515"
        y="190"
        fill="#ffffff"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="34"
        font-weight="700"
    >
        {stats["pull_requests"]:,}
    </text>

    <text
        x="515"
        y="216"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        PULL REQUESTS
    </text>


    <!-- PRIMARY METRIC 4 -->

    <text
        x="740"
        y="190"
        fill="#ffffff"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="34"
        font-weight="700"
    >
        {stats["public_repos"]:,}
    </text>

    <text
        x="740"
        y="216"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        PUBLIC REPOS
    </text>


    <!-- DIVIDER -->

    <line
        x1="55"
        y1="248"
        x2="945"
        y2="248"
        stroke="#342044"
        stroke-width="1"
    />


    <!-- SECONDARY STATS -->

    <text
        x="55"
        y="285"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        ACTIVE DAYS
    </text>

    <text
        x="150"
        y="285"
        fill="#e4e4e7"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="15"
        font-weight="700"
    >
        {active_days}
    </text>


    <text
        x="310"
        y="285"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        CURRENT STREAK
    </text>

    <text
        x="435"
        y="285"
        fill="#c084fc"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="15"
        font-weight="700"
    >
        {current_streak} DAYS
    </text>


    <text
        x="620"
        y="285"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        LONGEST STREAK
    </text>

    <text
        x="750"
        y="285"
        fill="#e4e4e7"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="15"
        font-weight="700"
    >
        {longest_streak} DAYS
    </text>


    <!-- GRAPH LABEL -->

    <text
        x="55"
        y="325"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="11"
    >
        CONTRIBUTION SIGNAL
    </text>


    <!-- GRAPH BASELINE -->

    <line
        x1="65"
        y1="405"
        x2="935"
        y2="405"
        stroke="#27272a"
        stroke-width="1"
    />


    <!-- CONTRIBUTION GRAPH -->

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
        cy="453"
        r="5"
        fill="#22c55e"
    />

    <text
        x="75"
        y="458"
        fill="#a1a1aa"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="12"
    >
        SYSTEM ONLINE
    </text>

    <text
        x="945"
        y="458"
        text-anchor="end"
        fill="#52525b"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="11"
    >
        DATA SOURCE // GITHUB API
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

    return {
        "active_days": active_days,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
    }


def main():
    print("Connecting to GitHub...")

    token = get_github_token()

    print(f"Fetching telemetry for @{USERNAME}...")

    stats = fetch_github_stats(token)

    calculated = generate_svg(stats)

    print()
    print("GitHub telemetry:")
    print(
        f"  Contributions:  {stats['total_contributions']:,}"
    )
    print(
        f"  Commits:        {stats['commits']:,}"
    )
    print(
        f"  Pull requests:  {stats['pull_requests']:,}"
    )
    print(
        f"  Public repos:   {stats['public_repos']:,}"
    )
    print(
        f"  Active days:    {calculated['active_days']}"
    )
    print(
        f"  Current streak: {calculated['current_streak']} days"
    )
    print(
        f"  Longest streak: {calculated['longest_streak']} days"
    )

    print()
    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    main()