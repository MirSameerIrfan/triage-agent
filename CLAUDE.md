# Triage agent: project guide for Claude

A portfolio project: an agent that triages the public GitHub issues of
`huggingface/huggingface_hub`, scored against what the maintainers actually did.
The owner will be asked about it in job interviews and must be able to explain
every line. The evaluation matters more than the agent.

## How we work

- **One small stage at a time.** Before a stage: say what it will build and why.
  Build only that stage. After it: explain the code. Then stop and wait for the
  owner's go-ahead. Never chain stages, even when the next one is unblocked.
- A stage is roughly one module. If it feels bigger, split it.
- Prefer the simple version. When there is a real choice, name the options and
  recommend one.
- No frameworks or abstractions the owner cannot explain line by line. Plain
  functions, small files, comments that say why.
- Do not commit or push unless asked.
- Keep the stage table below up to date when a stage changes status.

## Hard rules

- **Public data only.** Nothing from the owner's employer or its client: no
  data, prompts, procedures or design details. Never name either anywhere.
- **No secrets in the repo.** Keys come from environment variables; `.env` is
  git-ignored and `.env.example` documents the names.
- **Never invent results.** Every number in the README must come from a file in
  `results/` produced by a run that can be repeated.
- **Never commit issue text.** Commit issue numbers and derived labels only.
  `data/cache/` is git-ignored and rebuilt by `triage.fetch`.
- **Respect GitHub rate limits** and reuse the cache.
- **No leakage.** The agent sees only an issue's title and body. The test set is
  frozen before the agent exists and is run only for reported numbers; all
  tuning and failure analysis happen on the dev set. Retrieval may only return
  issues closed before the query issue was created, and never pull requests.
- If time runs short, cut features, not the evaluation.

## Decisions made

- Tracker: `huggingface/huggingface_hub`. Pool: all issues closed on or before
  2026-10-31 (1,655).
- LLM: Gemini API, behind one small swappable interface. Planned models:
  `gemini-3.8-flash` for headline numbers, `gemini-3.5-flash-lite` as a cheap
  second row. Check Google's docs for the current SDK call before writing it.
- Embeddings: local `bge-small-en-v1.5`, so retrieval numbers need no API key.
- Retrieval store: PostgreSQL with pgvector, run through Docker Compose.
- GitHub data comes through the GraphQL API (one field answers "which pull
  request closed this issue"; REST needs three chained calls).
- Classification is scored against resolution classes derived from how each
  issue was closed, because the tracker's own type labels come from the issue
  template, not from maintainers. Severity has no answer key and is hand-graded.
- Test set: about 100 recent issues at the natural class rate (code fixes are
  about 35% of recent usable issues, so no stratifying).

## Open questions for the owner

- Fold `docs_fix` (15 issues in total) into `answered_no_change`? Recommended.
- The 40-row hand audit in `grading/answer_key_audit.csv` is not filled in yet.
- No `GEMINI_API_KEY` yet (needed at stage 9). Docker is not installed on the
  owner's machine (needed at stage 11).

## Commands

```bash
uv sync
export GITHUB_TOKEN=$(gh auth token)
uv run python -m triage.discover     # rewrites data/issue_ids/pool.txt
uv run python -m triage.fetch        # fills data/cache/issues/, skips cached issues
uv run python -m triage.answer_key   # rewrites data/answer_key.jsonl
uv run python -m triage.audit        # writes the audit sheet; refuses to overwrite
uv run pytest
```

## Layout

```
src/triage/config.py       settings: repo, pool cut-off date, paths
src/triage/github.py       graphql(): call counter, retries, rate-limit wait
src/triage/discover.py     lists the pool -> data/issue_ids/pool.txt
src/triage/fetch.py        downloads issues -> data/cache/issues/<number>.json
src/triage/answer_key.py   rules -> data/answer_key.jsonl
src/triage/audit.py        draws 40 keys for a blind hand check
tests/test_answer_key.py   one test per answer-key rule
data/issue_ids/            committed issue-number lists
grading/                   the owner's hand audits and hand grades
```

## Stages

"Built" means the code exists and runs. A stage is "done" only when the owner
has had it explained and says they understand it.

| # | Stage | Status |
|---|---|---|
| 1 | Project skeleton and settings | Built, awaiting owner review |
| 2 | GitHub client | Built, awaiting owner review |
| 3 | List the pool of issues | Built and run, awaiting owner review |
| 4 | Download and cache issues | Built and run, awaiting owner review |
| 5 | Answer-key rules and tests | Built, awaiting owner review |
| 6 | Hand audit of 40 keys | Sheet generated; owner's audit not started |
| 7 | Freeze dev and test sets, leakage tests | Not started |
| 8 | Metrics and harness, checked with trivial baselines | Not started |
| 9 | LLM interface and no-retrieval baseline | Not started |
| 10 | Docs snapshot at a date before the test issues | Not started |
| 11 | Postgres + pgvector index (docs and past issues) | Not started |
| 12 | Retrieval and retrieval hit-rate eval | Not started |
| 13 | Agent: classify, retrieve, diagnose, decide | Not started |
| 14 | First full eval | Not started |
| 15 | Failure analysis on the dev set | Not started |
| 16 | One or two fixes, before-and-after numbers | Not started |
| 17 | Docker Compose one-command run | Not started |
| 18 | README: results table, setup, failure analysis | Not started |
| 19 | Write-up, demo recording, posts | Not started |
