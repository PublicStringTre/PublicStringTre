import html
import os
import subprocess
from collections import defaultdict
from pathlib import Path

import requests


USERNAME = "PublicStringTre"

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "languages.svg"

GRAPHQL_URL = "https://api.github.com/graphql"

TOP_LANGUAGES = 6

# A repository must contain at least this much detected source code
# before it contributes to the public language matrix.
#
# This keeps tiny exercises / practice assignments from carrying
# the same weight as complete applications.
MIN_LANGUAGE_BYTES = 10_000

# Don't let the profile generator itself skew the results.
EXCLUDED_REPOSITORIES = {
    "PublicStringTre/PublicStringTre",
}


def get_github_token():
    """
    In GitHub Actions, use GITHUB_TOKEN.

    Locally, retrieve the token from GitHub CLI.
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


def fetch_owned_repositories(token):
    """
    Fetch repositories owned by the authenticated GitHub user.

    Private repositories are included when the token has permission.

    Forks, archived repositories, and explicitly excluded repositories
    are removed before analysis.
    """

    query = """
    query($after: String) {
      viewer {
        login

        repositories(
          first: 50
          after: $after
          ownerAffiliations: [OWNER]
          orderBy: {
            field: UPDATED_AT
            direction: DESC
          }
        ) {
          pageInfo {
            hasNextPage
            endCursor
          }

          nodes {
            nameWithOwner
            isPrivate
            isFork
            isArchived

            languages(
              first: 100
              orderBy: {
                field: SIZE
                direction: DESC
              }
            ) {
              totalSize

              edges {
                size

                node {
                  name
                }
              }
            }
          }
        }
      }
    }
    """

    repositories = []
    cursor = None

    while True:
        data = graphql_request(
            token,
            query,
            {
                "after": cursor,
            },
        )

        viewer = data["viewer"]

        if viewer["login"].lower() != USERNAME.lower():
            raise RuntimeError(
                f"Authenticated as @{viewer['login']}, "
                f"expected @{USERNAME}."
            )

        connection = viewer["repositories"]

        for repo in connection["nodes"]:
            name = repo["nameWithOwner"]

            if name in EXCLUDED_REPOSITORIES:
                continue

            if repo["isFork"]:
                continue

            if repo["isArchived"]:
                continue

            repositories.append(repo)

        page_info = connection["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]

    return repositories


def aggregate_languages(repositories):
    """
    Build a project-weighted language profile using substantial repos.

    Rules:

    1. Repositories smaller than MIN_LANGUAGE_BYTES are ignored.
    2. Every remaining repository contributes exactly 1.0 total weight.
    3. Languages inside each repository are weighted according to
       their percentage of that repository.

    Example:

        Repo A:
            HTML   80%
            CSS    20%

        Repo B:
            Python 100%

    Overall contribution:

        HTML   += 0.80
        CSS    += 0.20
        Python += 1.00

    This prevents:

    - one giant repository from dominating by raw bytes
    - dozens of tiny practice repositories from dominating by count
    """

    language_scores = defaultdict(float)

    total_public_repos = 0
    total_private_repos = 0

    repos_with_code = 0
    substantial_repos = 0
    ignored_small_repos = 0

    substantial_public_repos = 0
    substantial_private_repos = 0

    for repo in repositories:

        if repo["isPrivate"]:
            total_private_repos += 1
        else:
            total_public_repos += 1

        languages = repo.get("languages")

        if not languages:
            continue

        total_size = languages["totalSize"]

        if total_size <= 0:
            continue

        repos_with_code += 1

        if total_size < MIN_LANGUAGE_BYTES:
            ignored_small_repos += 1
            continue

        substantial_repos += 1

        if repo["isPrivate"]:
            substantial_private_repos += 1
        else:
            substantial_public_repos += 1

        for edge in languages["edges"]:
            language_name = edge["node"]["name"]
            size = edge["size"]

            if size <= 0:
                continue

            repository_share = size / total_size

            language_scores[language_name] += repository_share

    total_score = sum(language_scores.values())

    if total_score == 0:
        raise RuntimeError(
            "No repositories met the minimum language size threshold."
        )

    sorted_languages = sorted(
        language_scores.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return {
        "languages": sorted_languages,
        "total_score": total_score,

        "repositories_scanned": len(repositories),

        "repos_with_code": repos_with_code,
        "substantial_repos": substantial_repos,
        "ignored_small_repos": ignored_small_repos,

        "total_public_repos": total_public_repos,
        "total_private_repos": total_private_repos,

        "substantial_public_repos": substantial_public_repos,
        "substantial_private_repos": substantial_private_repos,
    }


def build_display_languages(stats):
    languages = stats["languages"]
    total_score = stats["total_score"]

    top = languages[:TOP_LANGUAGES]
    remaining = languages[TOP_LANGUAGES:]

    display = []

    for name, score in top:
        percentage = (
            score / total_score
        ) * 100

        display.append(
            {
                "name": name,
                "score": score,
                "percentage": percentage,
            }
        )

    if remaining:
        other_score = sum(
            score
            for _, score in remaining
        )

        other_percentage = (
            other_score / total_score
        ) * 100

        display.append(
            {
                "name": "Other",
                "score": other_score,
                "percentage": other_percentage,
            }
        )

    return display


def print_language_audit(repositories):
    """
    LOCAL-ONLY diagnostic report.

    Private repository names can appear here in the terminal.

    Nothing from this function is written into the public SVG.

    Audit mode is automatically disabled inside GitHub Actions.
    """

    if os.getenv("GITHUB_ACTIONS", "").lower() == "true":
        print()
        print("Language audit skipped inside GitHub Actions.")
        return

    repo_totals = []
    language_sources = defaultdict(list)

    for repo in repositories:
        languages = repo.get("languages")

        if not languages:
            continue

        total_size = languages["totalSize"]

        if total_size <= 0:
            continue

        eligible = total_size >= MIN_LANGUAGE_BYTES

        repo_totals.append(
            {
                "repo": repo["nameWithOwner"],
                "bytes": total_size,
                "private": repo["isPrivate"],
                "eligible": eligible,
            }
        )

        for edge in languages["edges"]:
            language_name = edge["node"]["name"]
            size = edge["size"]

            if size <= 0:
                continue

            language_sources[language_name].append(
                {
                    "repo": repo["nameWithOwner"],
                    "bytes": size,
                    "private": repo["isPrivate"],
                    "eligible": eligible,
                }
            )

    repo_totals.sort(
        key=lambda item: item["bytes"],
        reverse=True,
    )

    print()
    print("=" * 88)
    print("LOCAL LANGUAGE AUDIT")
    print("=" * 88)

    print()
    print(
        f"Minimum substantial-project threshold: "
        f"{MIN_LANGUAGE_BYTES:,} detected bytes"
    )

    print()
    print("TOP REPOSITORIES BY DETECTED CODE SIZE")
    print("-" * 88)

    grand_total = sum(
        item["bytes"]
        for item in repo_totals
    )

    for item in repo_totals[:30]:
        percent = (
            item["bytes"] / grand_total * 100
            if grand_total
            else 0
        )

        visibility = (
            "PRIVATE"
            if item["private"]
            else "PUBLIC "
        )

        status = (
            "INCLUDED"
            if item["eligible"]
            else "IGNORED "
        )

        print(
            f"{status}  "
            f"{visibility}  "
            f"{item['repo']:<43} "
            f"{item['bytes']:>10,} bytes "
            f"{percent:>6.2f}%"
        )

    print()
    print("INCLUDED REPOSITORIES")
    print("-" * 88)

    included = [
        item
        for item in repo_totals
        if item["eligible"]
    ]

    if not included:
        print("No repositories meet the threshold.")

    else:
        for item in included:
            visibility = (
                "PRIVATE"
                if item["private"]
                else "PUBLIC "
            )

            print(
                f"{visibility}  "
                f"{item['repo']:<50} "
                f"{item['bytes']:>10,} bytes"
            )

    print()
    print("IGNORED SMALL REPOSITORIES")
    print("-" * 88)

    ignored = [
        item
        for item in repo_totals
        if not item["eligible"]
    ]

    print(
        f"{len(ignored)} repositories ignored "
        f"because they contain less than "
        f"{MIN_LANGUAGE_BYTES:,} detected language bytes."
    )

    print()
    print("=" * 88)
    print("END LOCAL AUDIT")
    print("=" * 88)
    print()


def generate_svg(stats):
    display_languages = build_display_languages(stats)

    row_height = 54
    graph_start_y = 175

    height = (
        graph_start_y
        + len(display_languages) * row_height
        + 125
    )

    rows = []

    max_bar_width = 650

    for index, language in enumerate(display_languages):

        y = graph_start_y + (index * row_height)

        name = html.escape(language["name"])
        percentage = language["percentage"]

        bar_width = max(
            4,
            max_bar_width * (percentage / 100),
        )

        rows.append(
            f"""
<!-- {name} -->

<text
    x="55"
    y="{y}"
    fill="#e4e4e7"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="14"
    font-weight="600"
>
    {name}
</text>

<text
    x="945"
    y="{y}"
    text-anchor="end"
    fill="#a1a1aa"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="13"
>
    {percentage:.1f}%
</text>

<rect
    x="55"
    y="{y + 15}"
    width="{max_bar_width}"
    height="10"
    rx="5"
    fill="#1c1723"
/>

<rect
    x="55"
    y="{y + 15}"
    width="{bar_width:.1f}"
    height="10"
    rx="5"
    fill="url(#purpleBar)"
/>
"""
        )

    rows_svg = "\n".join(rows)

    footer_y = height - 52

    svg = f"""<svg
xmlns="http://www.w3.org/2000/svg"
width="1000"
height="{height}"
viewBox="0 0 1000 {height}"
role="img"
aria-labelledby="title desc">

<title id="title">
PublicStringTre Language Matrix
</title>

<desc id="desc">
Project-weighted programming language composition from substantial
personal repositories owned by Anthony Fieldings III.
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
        id="purpleBar"
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
            offset="55%"
            stop-color="#a855f7"
        />

        <stop
            offset="100%"
            stop-color="#c084fc"
        />
    </linearGradient>

</defs>

<!-- BACKGROUND -->

<rect
    x="1"
    y="1"
    width="998"
    height="{height - 2}"
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
    linguist@publicstringtre: ~/repositories
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
    03 // LANGUAGE MATRIX
</text>

<text
    x="55"
    y="120"
    fill="#71717a"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
>
    PROJECT-WEIGHTED // SUBSTANTIAL REPOSITORIES
</text>

<text
    x="55"
    y="145"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    PUBLIC + PRIVATE // FORKS + ARCHIVES + PRACTICE REPOS FILTERED
</text>

{rows_svg}

<!-- FOOTER -->

<line
    x1="55"
    y1="{footer_y - 25}"
    x2="945"
    y2="{footer_y - 25}"
    stroke="#342044"
    stroke-width="1"
/>

<circle
    cx="61"
    cy="{footer_y}"
    r="5"
    fill="#22c55e"
/>

<text
    x="75"
    y="{footer_y + 5}"
    fill="#a1a1aa"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="12"
>
    {stats["substantial_repos"]} SUBSTANTIAL PROJECTS ANALYZED
</text>

<text
    x="945"
    y="{footer_y + 5}"
    text-anchor="end"
    fill="#52525b"
    font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
    font-size="11"
>
    PRIVATE REPOSITORY NAMES // HIDDEN
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
        f"Scanning repositories owned by @{USERNAME}..."
    )

    repositories = fetch_owned_repositories(
        token
    )

    stats = aggregate_languages(
        repositories
    )

    # Audit is OFF normally.
    #
    # Enable locally with:
    #
    # LANGUAGE_AUDIT=1 python3 scripts/generate_languages.py
    #
    audit_enabled = (
        os.getenv("LANGUAGE_AUDIT", "0") == "1"
    )

    if audit_enabled:
        print_language_audit(
            repositories
        )

    generate_svg(
        stats
    )

    display_languages = build_display_languages(
        stats
    )

    print()
    print("PROJECT-WEIGHTED LANGUAGE MATRIX")
    print("--------------------------------")

    print(
        f"Repositories scanned:       "
        f"{stats['repositories_scanned']}"
    )

    print(
        f"Repositories with code:     "
        f"{stats['repos_with_code']}"
    )

    print(
        f"Substantial repositories:   "
        f"{stats['substantial_repos']}"
    )

    print(
        f"Small repos ignored:        "
        f"{stats['ignored_small_repos']}"
    )

    print(
        f"Included public repos:      "
        f"{stats['substantial_public_repos']}"
    )

    print(
        f"Included private repos:     "
        f"{stats['substantial_private_repos']}"
    )

    print()

    for language in display_languages:
        print(
            f"{language['name']:<20} "
            f"{language['percentage']:>6.2f}%"
        )

    print()
    print(
        f"Minimum project size:       "
        f"{MIN_LANGUAGE_BYTES:,} detected bytes"
    )

    print()
    print(
        f"Generated: {OUTPUT}"
    )


if __name__ == "__main__":
    main()