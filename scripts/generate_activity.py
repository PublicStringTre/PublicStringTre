import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


USERNAME = "PublicStringTre"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "activity.svg"

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


def fetch_activity(token):
    today = datetime.now(timezone.utc).date()

    start = today - timedelta(days=364)

    start_iso = (
        datetime.combine(
            start,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        .isoformat()
        .replace("+00:00", "Z")
    )

    end_iso = (
        datetime.combine(
            today,
            datetime.max.time(),
            tzinfo=timezone.utc,
        )
        .isoformat()
        .replace("+00:00", "Z")
    )

    query = """
    query($from: DateTime!, $to: DateTime!) {
      viewer {
        login

        contributionsCollection(
          from: $from
          to: $to
        ) {
          restrictedContributionsCount

          contributionCalendar {
            totalContributions

            weeks {
              contributionDays {
                date
                contributionCount
                weekday
              }
            }
          }
        }
      }
    }
    """

    data = graphql_request(
        token,
        query,
        {
            "from": start_iso,
            "to": end_iso,
        },
    )

    viewer = data["viewer"]

    if viewer["login"].lower() != USERNAME.lower():
        raise RuntimeError(
            f"Authenticated as @{viewer['login']}, "
            f"expected @{USERNAME}."
        )

    collection = viewer["contributionsCollection"]
    calendar = collection["contributionCalendar"]

    return {
        "weeks": calendar["weeks"],
        "total_contributions": calendar["totalContributions"],
        "restricted_contributions": (
            collection["restrictedContributionsCount"]
        ),
        "start": start,
        "end": today,
    }


def calculate_activity_stats(activity):
    days = []

    for week in activity["weeks"]:
        for day in week["contributionDays"]:
            date = datetime.strptime(
                day["date"],
                "%Y-%m-%d",
            ).date()

            if activity["start"] <= date <= activity["end"]:
                days.append(
                    {
                        "date": date,
                        "count": day["contributionCount"],
                    }
                )

    active_days = sum(
        1
        for day in days
        if day["count"] > 0
    )

    max_day = max(
        (
            day["count"]
            for day in days
        ),
        default=0,
    )

    total = sum(
        day["count"]
        for day in days
    )

    average_active_day = (
        total / active_days
        if active_days
        else 0
    )

    return {
        "days": days,
        "active_days": active_days,
        "max_day": max_day,
        "total": total,
        "average_active_day": average_active_day,
    }


def get_level(count, max_count):
    """
    Convert contribution count into one of five visual levels.
    """

    if count <= 0:
        return 0

    if max_count <= 1:
        return 4

    ratio = count / max_count

    if ratio <= 0.25:
        return 1

    if ratio <= 0.50:
        return 2

    if ratio <= 0.75:
        return 3

    return 4


def generate_svg(activity, stats):
    weeks = activity["weeks"]

    width = 1000
    height = 460

    grid_x = 120
    grid_y = 176

    cell_size = 11
    gap = 4

    step = cell_size + gap

    colors = {
        0: "#17131d",
        1: "#352044",
        2: "#5b21b6",
        3: "#8b5cf6",
        4: "#c084fc",
    }

    rectangles = []

    for week_index, week in enumerate(weeks):

        for day in week["contributionDays"]:

            date = datetime.strptime(
                day["date"],
                "%Y-%m-%d",
            ).date()

            if not (
                activity["start"]
                <= date
                <= activity["end"]
            ):
                continue

            count = day["contributionCount"]

            level = get_level(
                count,
                stats["max_day"],
            )

            weekday = day["weekday"]

            x = grid_x + (
                week_index * step
            )

            y = grid_y + (
                weekday * step
            )

            rectangles.append(
                f"""
<rect
    x="{x}"
    y="{y}"
    width="{cell_size}"
    height="{cell_size}"
    rx="2"
    fill="{colors[level]}"
>
    <title>{date.isoformat()} // {count} contributions</title>
</rect>
"""
            )

    rectangles_svg = "\n".join(
        rectangles
    )

    month_positions = []
    seen_months = set()

    for week_index, week in enumerate(weeks):

        if not week["contributionDays"]:
            continue

        for day in week["contributionDays"]:

            date = datetime.strptime(
                day["date"],
                "%Y-%m-%d",
            ).date()

            if not (
                activity["start"]
                <= date
                <= activity["end"]
            ):
                continue

            month_key = (
                date.year,
                date.month,
            )

            if month_key in seen_months:
                continue

            if date.day > 14:
                continue

            seen_months.add(
                month_key
            )

            x = grid_x + (
                week_index * step
            )

            month_positions.append(
                (
                    x,
                    date.strftime("%b").upper(),
                )
            )

    month_labels = []

    for x, label in month_positions:
        month_labels.append(
            f"""
<text
    x="{x}"
    y="158"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
>
    {label}
</text>
"""
        )

    month_labels_svg = "\n".join(
        month_labels
    )

    svg = f"""<svg
xmlns="http://www.w3.org/2000/svg"
width="{width}"
height="{height}"
viewBox="0 0 {width} {height}"
role="img"
aria-labelledby="title desc">

<title id="title">
PublicStringTre GitHub Activity
</title>

<desc id="desc">
GitHub contribution activity over the last 365 days.
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

</defs>

<!-- BACKGROUND -->

<rect
    x="1"
    y="1"
    width="998"
    height="458"
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
    signal@publicstringtre: ~/activity
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
    05 // ACTIVITY SIGNAL
</text>

<text
    x="55"
    y="120"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
>
    LAST 365 DAYS // CONTRIBUTION FIELD
</text>

<!-- MONTHS -->

{month_labels_svg}

<!-- WEEKDAY LABELS -->

<text
    x="55"
    y="{grid_y + step + 9}"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
>
    MON
</text>

<text
    x="55"
    y="{grid_y + (step * 3) + 9}"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
>
    WED
</text>

<text
    x="55"
    y="{grid_y + (step * 5) + 9}"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
>
    FRI
</text>

<!-- CONTRIBUTION FIELD -->

{rectangles_svg}

<!-- DIVIDER -->

<line
    x1="55"
    y1="310"
    x2="945"
    y2="310"
    stroke="#342044"
    stroke-width="1"
/>

<!-- METRICS -->

<text
    x="55"
    y="350"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="25"
    font-weight="700"
>
    {stats["total"]:,}
</text>

<text
    x="55"
    y="374"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
    letter-spacing="1"
>
    CONTRIBUTIONS
</text>

<text
    x="300"
    y="350"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="25"
    font-weight="700"
>
    {stats["active_days"]:,}
</text>

<text
    x="300"
    y="374"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
    letter-spacing="1"
>
    ACTIVE DAYS
</text>

<text
    x="545"
    y="350"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="25"
    font-weight="700"
>
    {stats["max_day"]:,}
</text>

<text
    x="545"
    y="374"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
    letter-spacing="1"
>
    PEAK DAY
</text>

<text
    x="790"
    y="350"
    fill="#ffffff"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="25"
    font-weight="700"
>
    {stats["average_active_day"]:.1f}
</text>

<text
    x="790"
    y="374"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
    letter-spacing="1"
>
    AVG / ACTIVE DAY
</text>

<!-- LEGEND -->

<text
    x="55"
    y="423"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
>
    SIGNAL
</text>

<rect
    x="110"
    y="414"
    width="10"
    height="10"
    rx="2"
    fill="{colors[0]}"
/>

<rect
    x="126"
    y="414"
    width="10"
    height="10"
    rx="2"
    fill="{colors[1]}"
/>

<rect
    x="142"
    y="414"
    width="10"
    height="10"
    rx="2"
    fill="{colors[2]}"
/>

<rect
    x="158"
    y="414"
    width="10"
    height="10"
    rx="2"
    fill="{colors[3]}"
/>

<rect
    x="174"
    y="414"
    width="10"
    height="10"
    rx="2"
    fill="{colors[4]}"
/>

<text
    x="945"
    y="423"
    text-anchor="end"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="10"
>
    CONTRIBUTION COUNTS // REPOSITORY DETAILS HIDDEN
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
        f"Fetching activity for @{USERNAME}..."
    )

    activity = fetch_activity(
        token
    )

    stats = calculate_activity_stats(
        activity
    )

    generate_svg(
        activity,
        stats,
    )

    print()
    print("ACTIVITY SIGNAL")
    print("---------------")

    print(
        f"Period:              "
        f"{activity['start']} → {activity['end']}"
    )

    print(
        f"Contributions:       "
        f"{stats['total']:,}"
    )

    print(
        f"Active days:         "
        f"{stats['active_days']:,}"
    )

    print(
        f"Peak contribution day: "
        f"{stats['max_day']:,}"
    )

    print(
        f"Average active day:  "
        f"{stats['average_active_day']:.2f}"
    )

    print()

    print(
        f"Generated: {OUTPUT}"
    )


if __name__ == "__main__":
    main()