"""Step 1 of fetching: list which issues are in the pool.

Writes data/issue_ids/pool.txt, one issue number per line. That file is
committed, so anyone can rebuild exactly the same dataset with `triage.fetch`.

Run:  python -m triage.discover
"""

from triage import config, github

QUERY = (
    """
query($owner: String!, $name: String!, $cursor: String) {
  %s
  repository(owner: $owner, name: $name) {
    issues(states: CLOSED, first: 100, after: $cursor,
           orderBy: {field: CREATED_AT, direction: ASC}) {
      pageInfo { hasNextPage endCursor }
      nodes { number closedAt }
    }
  }
}
"""
    % github.RATE_LIMIT_FIELDS
)


def list_closed_issue_numbers() -> list[int]:
    numbers = []
    cursor = None
    while True:
        data = github.graphql(
            QUERY, {"owner": config.REPO_OWNER, "name": config.REPO_NAME, "cursor": cursor}
        )
        page = data["repository"]["issues"]
        for issue in page["nodes"]:
            # closedAt looks like "2026-03-01T12:00:00Z"; the first 10 chars are the date.
            if issue["closedAt"][:10] <= config.POOL_CLOSED_ON_OR_BEFORE:
                numbers.append(issue["number"])
        if not page["pageInfo"]["hasNextPage"]:
            return sorted(numbers)
        cursor = page["pageInfo"]["endCursor"]


def main() -> None:
    numbers = list_closed_issue_numbers()
    config.POOL_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.POOL_IDS_FILE.write_text("\n".join(str(n) for n in numbers) + "\n")
    print(
        f"Wrote {len(numbers)} issue numbers to {config.POOL_IDS_FILE} "
        f"({github.calls_made} API calls, {github.last_remaining} rate-limit points left)"
    )


if __name__ == "__main__":
    main()
