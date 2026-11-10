"""A thin GitHub GraphQL client: one function, `graphql(query, variables)`.

It does three things beyond a plain POST:
  * counts calls, so we can prove a cached run makes none;
  * retries when GitHub answers with a temporary error;
  * reads the rate-limit numbers GitHub returns and waits if we are nearly out.
"""

import os
import time
from datetime import datetime, timezone

import requests

API_URL = "https://api.github.com/graphql"

# Every query we send must include this block so we can see our remaining budget.
RATE_LIMIT_FIELDS = "rateLimit { cost remaining resetAt }"

# Stop and wait for the hourly reset when fewer than this many points remain.
MIN_REMAINING = 200

calls_made = 0
last_remaining = None


def graphql(query: str, variables: dict | None = None) -> dict:
    """Run one GraphQL query and return its `data`. Raises if GitHub reports errors."""
    global calls_made, last_remaining
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN first (see .env.example).")

    for attempt in range(5):
        response = requests.post(
            API_URL,
            json={"query": query, "variables": variables or {}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=90,
        )
        calls_made += 1

        temporary = response.status_code in (502, 503, 504)
        secondary_limit = response.status_code in (403, 429)
        if temporary or secondary_limit:
            # Honour Retry-After if GitHub sent one, otherwise back off: 10s, 20s, 40s...
            wait = int(response.headers.get("Retry-After", 10 * 2**attempt))
            print(f"  GitHub returned {response.status_code}; retrying in {wait}s")
            time.sleep(wait)
            continue

        response.raise_for_status()
        payload = response.json()
        if payload.get("errors"):
            raise RuntimeError(f"GraphQL errors: {payload['errors']}")

        data = payload["data"]
        _wait_if_nearly_out(data["rateLimit"])
        return data

    raise RuntimeError("GitHub kept failing after 5 attempts.")


def _wait_if_nearly_out(rate_limit: dict) -> None:
    global last_remaining
    last_remaining = rate_limit["remaining"]
    if last_remaining >= MIN_REMAINING:
        return
    reset_at = datetime.fromisoformat(rate_limit["resetAt"].replace("Z", "+00:00"))
    seconds = max(0, (reset_at - datetime.now(timezone.utc)).total_seconds()) + 5
    print(f"  Rate limit nearly used up; sleeping {seconds:.0f}s until it resets")
    time.sleep(seconds)
