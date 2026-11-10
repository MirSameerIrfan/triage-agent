"""Step 2 of fetching: download every pool issue into a local cache.

One JSON file per issue in data/cache/issues/. An issue that already has a
file is skipped, so a second run makes zero API calls.

Run:  python -m triage.fetch
"""

import json

from triage import config, github

# How many issues to ask for in one request.
BATCH_SIZE = 20

# Everything we need about one issue: the ticket itself (what the agent sees),
# plus the conversation and close events (what the answer key is built from).
ISSUE_FIELDS = """
fragment IssueFields on Issue {
  number title body url createdAt closedAt stateReason
  authorAssociation
  author { login __typename }
  labels(first: 20) { nodes { name } }
  comments(first: 50) {
    totalCount
    nodes { createdAt authorAssociation author { login __typename } body }
  }
  closedByPullRequestsReferences(first: 5, includeClosedPrs: true) {
    nodes {
      number url merged mergedAt
      repository { nameWithOwner }
      files(first: 100) { nodes { path } }
    }
  }
  timelineItems(first: 100, itemTypes: [CLOSED_EVENT, REOPENED_EVENT,
                                        CROSS_REFERENCED_EVENT, MARKED_AS_DUPLICATE_EVENT]) {
    nodes {
      __typename
      ... on ClosedEvent {
        createdAt
        actor { login __typename }
        closer {
          __typename
          ... on PullRequest { number url merged repository { nameWithOwner } }
          ... on Commit { oid url }
        }
      }
      ... on ReopenedEvent { createdAt }
      ... on CrossReferencedEvent {
        createdAt willCloseTarget
        source {
          __typename
          ... on PullRequest {
            number url merged mergedAt
            author { login }
            repository { nameWithOwner }
            files(first: 100) { nodes { path } }
          }
          ... on Issue { number url repository { nameWithOwner } }
        }
      }
      ... on MarkedAsDuplicateEvent {
        createdAt
        canonical { ... on Issue { number url } }
      }
    }
  }
}
"""


def cache_path(number: int):
    return config.ISSUE_CACHE_DIR / f"{number}.json"


def read_pool_ids() -> list[int]:
    return [int(line) for line in config.POOL_IDS_FILE.read_text().split()]


def missing_from_cache(numbers: list[int]) -> list[int]:
    return [n for n in numbers if not cache_path(n).exists()]


def build_batch_query(numbers: list[int]) -> str:
    """One query that asks for several issues at once.

    GraphQL lets us name each result ("i123: issue(number: 123)"), so 20 issues
    cost one request instead of 20.
    """
    issue_lines = "\n".join(
        f"    i{n}: issue(number: {n}) {{ ...IssueFields }}" for n in numbers
    )
    return (
        "query($owner: String!, $name: String!) {\n"
        f"  {github.RATE_LIMIT_FIELDS}\n"
        "  repository(owner: $owner, name: $name) {\n"
        f"{issue_lines}\n"
        "  }\n"
        "}\n" + ISSUE_FIELDS
    )


def fetch_batch(numbers: list[int]) -> None:
    data = github.graphql(
        build_batch_query(numbers), {"owner": config.REPO_OWNER, "name": config.REPO_NAME}
    )
    for number in numbers:
        issue = data["repository"][f"i{number}"]
        # Write to a temp file first so a crash never leaves a half-written cache file.
        temp = cache_path(number).with_suffix(".tmp")
        temp.write_text(json.dumps(issue, indent=1))
        temp.rename(cache_path(number))


def main() -> None:
    config.ISSUE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pool = read_pool_ids()
    todo = missing_from_cache(pool)
    print(f"Pool: {len(pool)} issues. Cached: {len(pool) - len(todo)}. To fetch: {len(todo)}.")

    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo[start : start + BATCH_SIZE]
        fetch_batch(batch)
        done = start + len(batch)
        if done % 200 == 0 or done == len(todo):
            print(f"  {done}/{len(todo)} fetched ({github.last_remaining} rate-limit points left)")

    print(f"Done. API calls this run: {github.calls_made}.")


if __name__ == "__main__":
    main()
