# Support-ticket triage agent, with a published evaluation

An agent that triages the public GitHub issues of
[`huggingface/huggingface_hub`](https://github.com/huggingface/huggingface_hub),
scored against what the maintainers actually did with each issue.

**Status: in progress.** The results table goes here once there is a run to
report. Every number in this README will come from a file in `results/`.

## What exists so far

| Stage | What it does | Command |
|---|---|---|
| 1 | List the pool of closed issues, then download them into a local cache | `python -m triage.discover`, `python -m triage.fetch` |
| 2 | Build the answer key from the cached issues | `python -m triage.answer_key` |
| 2 | Draw 40 keys for a hand audit | `python -m triage.audit` |

## Reproduce the data

```bash
uv sync
export GITHUB_TOKEN=$(gh auth token)   # any token that can read public repos
uv run python -m triage.fetch          # downloads the issues listed in data/issue_ids/pool.txt
uv run python -m triage.answer_key     # rebuilds data/answer_key.jsonl
uv run pytest
```

Issue text is never committed. The repo holds the list of issue numbers
(`data/issue_ids/`) and the derived answer key (`data/answer_key.jsonl`: labels,
evidence and links only). `triage.fetch` rebuilds the rest and skips anything
already cached.

## How the answer key is built

The agent sees only an issue's title and body. The key is derived from what
happened afterwards, by the first rule that matches:

| Rule | Class |
|---|---|
| Closed by a merged pull request, or a maintainer named the merged pull request that fixed it | `code_fix` (or `docs_fix` if the pull request changed only docs files) |
| A merged pull request mentions the issue but nobody confirmed it was the fix | excluded, not guessed |
| Closed as duplicate or "not planned" | `not_actionable` |
| Closed as completed after someone other than the reporter replied | `answered_no_change` |
| Closed with no reply and no linked change | excluded |

Issues filed by maintainers or bots, and feature requests, are also excluded
from scoring: they are not support tickets.
