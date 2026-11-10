"""Each answer-key rule, checked against a tiny hand-made issue."""

from triage.answer_key import build_key, normalise_docs_url

THIS_REPO = {"nameWithOwner": "huggingface/huggingface_hub"}


def make_issue(**overrides) -> dict:
    """A plain externally-filed issue, closed as completed, with no comments or events."""
    issue = {
        "number": 500,
        "url": "https://github.com/huggingface/huggingface_hub/issues/500",
        "title": "Download fails",
        "body": "### Describe the bug\nIt fails.",
        "createdAt": "2026-01-01T00:00:00Z",
        "closedAt": "2026-01-05T00:00:00Z",
        "stateReason": "COMPLETED",
        "authorAssociation": "NONE",
        "author": {"login": "reporter", "__typename": "User"},
        "labels": {"nodes": []},
        "comments": {"totalCount": 0, "nodes": []},
        "closedByPullRequestsReferences": {"nodes": []},
        "timelineItems": {"nodes": []},
    }
    issue.update(overrides)
    return issue


def comment(body: str, who: str = "maintainer", association: str = "MEMBER") -> dict:
    return {
        "createdAt": "2026-01-02T00:00:00Z",
        "authorAssociation": association,
        "author": {"login": who, "__typename": "User"},
        "body": body,
    }


def pull_request(number: int, paths: list[str]) -> dict:
    return {
        "__typename": "PullRequest",
        "number": number,
        "merged": True,
        "repository": THIS_REPO,
        "files": {"nodes": [{"path": p} for p in paths]},
    }


def cross_reference(pr: dict) -> dict:
    return {"__typename": "CrossReferencedEvent", "source": pr}


def key_for(issue: dict, pool=frozenset()) -> dict:
    return build_key(issue, set(pool))


def test_closing_pr_that_changes_code_is_a_code_fix():
    pr = pull_request(501, ["src/huggingface_hub/file_download.py", "docs/source/en/guides/download.md"])
    key = key_for(make_issue(closedByPullRequestsReferences={"nodes": [pr]}))
    assert key["resolution_class"] == "code_fix"
    assert key["needs_code_fix"] is True
    assert key["exclude_reason"] is None


def test_closing_pr_that_only_changes_docs_is_a_docs_fix():
    pr = pull_request(501, ["docs/source/en/guides/download.md"])
    key = key_for(make_issue(closedByPullRequestsReferences={"nodes": [pr]}))
    assert key["resolution_class"] == "docs_fix"
    assert key["needs_code_fix"] is False


def test_pr_named_by_a_maintainer_counts_as_the_fix():
    pr = pull_request(501, ["src/huggingface_hub/hf_api.py"])
    issue = make_issue(
        timelineItems={"nodes": [cross_reference(pr)]},
        comments={"totalCount": 1, "nodes": [comment("Fixed in #501, thanks!")]},
    )
    assert key_for(issue)["resolution_class"] == "code_fix"


def test_pr_that_only_mentions_the_issue_is_excluded_as_unconfirmed():
    pr = pull_request(501, ["src/huggingface_hub/hf_api.py"])
    issue = make_issue(
        timelineItems={"nodes": [cross_reference(pr)]},
        comments={"totalCount": 1, "nodes": [comment("Thanks for the report.")]},
    )
    key = key_for(issue)
    assert key["resolution_class"] is None
    assert key["exclude_reason"] == "unconfirmed_fix"


def test_closed_as_not_planned_is_not_actionable():
    key = key_for(make_issue(stateReason="NOT_PLANNED"))
    assert key["resolution_class"] == "not_actionable"
    assert key["needs_code_fix"] is False


def test_closed_as_duplicate_is_not_actionable():
    assert key_for(make_issue(stateReason="DUPLICATE"))["resolution_class"] == "not_actionable"


def test_completed_after_a_reply_is_answered_no_change():
    issue = make_issue(comments={"totalCount": 1, "nodes": [comment("Set HF_HUB_OFFLINE=1.")]})
    assert key_for(issue)["resolution_class"] == "answered_no_change"


def test_reporter_talking_to_themselves_is_not_a_reply():
    own = comment("Never mind, solved it.", who="reporter", association="NONE")
    key = key_for(make_issue(comments={"totalCount": 1, "nodes": [own]}))
    assert key["resolution_class"] is None
    assert key["exclude_reason"] == "no_reply"


def test_staff_authored_issue_is_excluded():
    assert key_for(make_issue(authorAssociation="MEMBER"))["exclude_reason"] == "staff_author"


def test_feature_request_is_excluded():
    body = "**Is your feature request related to a problem? Please describe.**\nI want X."
    assert key_for(make_issue(body=body))["exclude_reason"] == "feature_request"
    labelled = make_issue(labels={"nodes": [{"name": "enhancement"}]})
    assert key_for(labelled)["exclude_reason"] == "feature_request"


def test_retrieval_targets_come_from_replies_not_from_the_reporter():
    issue = make_issue(
        comments={
            "totalCount": 2,
            "nodes": [
                comment("See https://hf.co/docs/huggingface_hub/guides/download#filter-files. Same as #120 and #999."),
                comment("I read https://huggingface.co/docs/hub/index", who="reporter", association="NONE"),
            ],
        }
    )
    key = key_for(issue, pool={120, 999})
    assert key["target_docs"] == ["https://huggingface.co/docs/huggingface_hub/guides/download"]
    assert key["target_issues"] == [120]  # 999 is newer than issue 500, so it cannot be a target


def test_normalise_docs_url_strips_anchor_query_and_punctuation():
    url = "http://huggingface.co/docs/huggingface_hub/guides/cli?x=1#login)."
    assert normalise_docs_url(url) == "https://huggingface.co/docs/huggingface_hub/guides/cli"
