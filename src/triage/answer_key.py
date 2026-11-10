"""Build the answer key: what the maintainers actually did with each issue.

The agent only ever sees an issue's title and body. Everything here is read
from what happened *afterwards* (comments, close events, linked pull requests),
so it is what we score the agent against.

For each issue we derive:
  resolution_class   code_fix | docs_fix | answered_no_change | not_actionable
  needs_code_fix     True only for code_fix (the "should have escalated" truth)
  exclude_reason     why an issue cannot be used for scoring, or None
  evidence           one line saying which rule fired, for auditing
  target_docs        docs pages a human pointed the reporter to
  target_issues      older issues a maintainer pointed the reporter to

Run:  python -m triage.answer_key
"""

import json
import re
from collections import Counter

from triage import config
from triage.fetch import cache_path, read_pool_ids

ANSWER_KEY_FILE = config.DATA_DIR / "answer_key.jsonl"  # committed

THIS_REPO = f"{config.REPO_OWNER}/{config.REPO_NAME}"
STAFF_ASSOCIATIONS = {"MEMBER", "OWNER", "COLLABORATOR"}
FEATURE_TEMPLATE_MARKER = "Is your feature request related to a problem"

DOCS_URL = re.compile(r"https?://(?:huggingface\.co|hf\.co)/docs/[^\s)>\]\"'`]+")
ISSUE_REF = re.compile(r"(?:#|/issues/|/pull/)(\d+)")


# --- small helpers -----------------------------------------------------------


def is_staff(association: str) -> bool:
    return association in STAFF_ASSOCIATIONS


def is_bot(author: dict | None) -> bool:
    return bool(author) and author.get("__typename") == "Bot"


def login(author: dict | None) -> str | None:
    return author.get("login") if author else None


def label_names(issue: dict) -> set[str]:
    return {label["name"] for label in issue["labels"]["nodes"]}


def is_docs_path(path: str) -> bool:
    return path.startswith("docs/") or path.endswith((".md", ".mdx"))


def human_replies(issue: dict) -> list[dict]:
    """Comments written by a person other than the reporter."""
    reporter = login(issue["author"])
    return [
        c
        for c in issue["comments"]["nodes"]
        if not is_bot(c["author"]) and login(c["author"]) != reporter
    ]


def staff_comments(issue: dict) -> list[dict]:
    return [c for c in issue["comments"]["nodes"] if is_staff(c["authorAssociation"])]


# --- finding the fix ---------------------------------------------------------


def recorded_closing_prs(issue: dict) -> list[dict]:
    """Merged PRs that GitHub itself recorded as closing this issue."""
    return [
        pr
        for pr in issue["closedByPullRequestsReferences"]["nodes"]
        if pr["merged"] and pr["repository"]["nameWithOwner"].startswith(config.REPO_OWNER + "/")
    ]


def cross_referenced_prs(issue: dict) -> list[dict]:
    """Merged PRs in this repo that mention the issue (without formally closing it)."""
    prs = {}
    for event in issue["timelineItems"]["nodes"]:
        if event["__typename"] != "CrossReferencedEvent":
            continue
        source = event["source"]
        if (
            source.get("__typename") == "PullRequest"
            and source["merged"]
            and source["repository"]["nameWithOwner"] == THIS_REPO
        ):
            prs[source["number"]] = source
    return list(prs.values())


def staff_linked_prs(issue: dict) -> list[dict]:
    """Cross-referenced PRs that a maintainer also named in a comment.

    Maintainers often close by hand and write "Fixed in #123" instead of using
    GitHub's closing keywords. We accept that as a fix only when the link goes
    both ways: the PR mentions the issue AND a maintainer mentions the PR.
    """
    mentioned = set()
    for comment in staff_comments(issue):
        mentioned.update(int(n) for n in ISSUE_REF.findall(comment["body"]))
    return [pr for pr in cross_referenced_prs(issue) if pr["number"] in mentioned]


def closed_by_commit(issue: dict) -> bool:
    closes = [e for e in issue["timelineItems"]["nodes"] if e["__typename"] == "ClosedEvent"]
    closer = closes[-1].get("closer") if closes else None
    return bool(closer) and closer["__typename"] == "Commit"


def only_touches_docs(prs: list[dict]) -> bool:
    paths = [f["path"] for pr in prs for f in (pr.get("files") or {}).get("nodes", [])]
    return bool(paths) and all(is_docs_path(p) for p in paths)


# --- the rules ---------------------------------------------------------------


def classify_resolution(issue: dict) -> tuple[str | None, str]:
    """Return (resolution_class, evidence). The first rule that matches wins."""
    fix_prs = recorded_closing_prs(issue)
    how = "closed by merged PR"
    if not fix_prs:
        fix_prs = staff_linked_prs(issue)
        how = "maintainer linked merged PR"

    if fix_prs:
        numbers = ", ".join(f"#{pr['number']}" for pr in fix_prs)
        if only_touches_docs(fix_prs):
            return "docs_fix", f"{how} {numbers} (docs files only)"
        return "code_fix", f"{how} {numbers}"

    if closed_by_commit(issue):
        return "code_fix", "closed by a commit"

    if cross_referenced_prs(issue):
        # A merged PR mentions this issue but nobody confirmed it was the fix.
        # We cannot tell either way, so we do not guess.
        return None, "unconfirmed: merged PR mentions the issue"

    labels = label_names(issue)
    was_marked_duplicate = any(
        e["__typename"] == "MarkedAsDuplicateEvent" for e in issue["timelineItems"]["nodes"]
    )
    if issue["stateReason"] == "DUPLICATE" or was_marked_duplicate or "duplicate" in labels:
        return "not_actionable", "closed as duplicate"

    if issue["stateReason"] == "NOT_PLANNED" or labels & {"wontfix", "invalid"}:
        return "not_actionable", "closed as not planned"

    if human_replies(issue):
        return "answered_no_change", "closed as completed after a reply, no linked change"

    return None, "no reply and no linked change"


def exclusion_reason(issue: dict, resolution_class: str | None, evidence: str) -> str | None:
    """Why this issue cannot be scored, or None if it can."""
    if is_staff(issue["authorAssociation"]):
        return "staff_author"  # an internal task, not a support ticket
    if is_bot(issue["author"]):
        return "bot_author"
    if "enhancement" in label_names(issue) or FEATURE_TEMPLATE_MARKER in (issue["body"] or ""):
        return "feature_request"
    if resolution_class is None:
        return "unconfirmed_fix" if evidence.startswith("unconfirmed") else "no_reply"
    return None


# --- retrieval targets -------------------------------------------------------


def normalise_docs_url(url: str) -> str:
    """Reduce a docs link to its page: drop anchors, queries and trailing punctuation."""
    url = url.split("#")[0].split("?")[0].rstrip(".,;:!*_/")
    return url.replace("http://", "https://").replace("https://hf.co/", "https://huggingface.co/")


def target_docs(issue: dict) -> list[str]:
    urls = set()
    for comment in human_replies(issue):
        urls.update(normalise_docs_url(u) for u in DOCS_URL.findall(comment["body"]))
    return sorted(urls)


def target_issues(issue: dict, pool: set[int]) -> list[int]:
    """Older pool issues a maintainer referred to (duplicates, "see #123")."""
    numbers = set()
    for comment in staff_comments(issue):
        numbers.update(int(n) for n in ISSUE_REF.findall(comment["body"]))
    for event in issue["timelineItems"]["nodes"]:
        if event["__typename"] == "MarkedAsDuplicateEvent" and event.get("canonical"):
            numbers.add(event["canonical"]["number"])
    # Only issues that exist in our pool and were filed before this one.
    return sorted(n for n in numbers if n in pool and n < issue["number"])


# --- putting it together -----------------------------------------------------


def build_key(issue: dict, pool: set[int]) -> dict:
    resolution_class, evidence = classify_resolution(issue)
    return {
        "number": issue["number"],
        "url": issue["url"],
        "created_at": issue["createdAt"],
        "closed_at": issue["closedAt"],
        "resolution_class": resolution_class,
        "needs_code_fix": None if resolution_class is None else resolution_class == "code_fix",
        "exclude_reason": exclusion_reason(issue, resolution_class, evidence),
        "evidence": evidence,
        "target_docs": target_docs(issue),
        "target_issues": target_issues(issue, pool),
    }


def load_answer_key() -> list[dict]:
    return [json.loads(line) for line in ANSWER_KEY_FILE.read_text().splitlines()]


def main() -> None:
    pool_ids = read_pool_ids()
    pool = set(pool_ids)
    keys = [build_key(json.loads(cache_path(n).read_text()), pool) for n in pool_ids]
    ANSWER_KEY_FILE.write_text("".join(json.dumps(k) + "\n" for k in keys))

    usable = [k for k in keys if k["exclude_reason"] is None]
    print(f"Wrote {len(keys)} keys to {ANSWER_KEY_FILE}\n")
    print(f"Excluded from scoring: {len(keys) - len(usable)}")
    for reason, count in Counter(k["exclude_reason"] for k in keys if k["exclude_reason"]).most_common():
        print(f"  {reason:<18}{count:>5}")
    print(f"\nUsable for scoring: {len(usable)}")
    for name, count in Counter(k["resolution_class"] for k in usable).most_common():
        print(f"  {name:<20}{count:>5}  {100 * count / len(usable):5.1f}%")
    with_docs = sum(bool(k["target_docs"]) for k in usable)
    with_issues = sum(bool(k["target_issues"]) for k in usable)
    with_either = sum(bool(k["target_docs"] or k["target_issues"]) for k in usable)
    print(f"\nUsable issues with a retrieval target: {with_either} "
          f"(docs link: {with_docs}, older issue: {with_issues})")


if __name__ == "__main__":
    main()
