"""Draw a sample of answer keys for a human to check by hand.

The answer key is built by rules, and rules can be wrong. This writes a CSV of
40 recent issues, spread across the rules, with two empty columns to fill in.
The sheet does not show the key's answer, so the check is blind. The share of
rows where the human disagrees is the key's measured error rate.

Run:  python -m triage.audit
"""

import csv
import random

from triage.answer_key import load_answer_key

AUDIT_FILE = "grading/answer_key_audit.csv"
SEED = 7  # fixed, so the same sample is drawn every time
ONLY_CREATED_SINCE = "2025-01-01"  # the period the dev and test sets will come from

# How many rows to draw for each rule (matched on the start of `evidence`).
ROWS_PER_RULE = {
    "closed by merged PR": 11,
    "maintainer linked merged PR": 7,
    "closed as not planned": 11,
    "closed as completed after a reply": 11,
}


def draw_sample(keys: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    recent = [
        k for k in keys
        if k["exclude_reason"] is None and k["created_at"] >= ONLY_CREATED_SINCE
    ]
    sample = []
    for rule, how_many in ROWS_PER_RULE.items():
        matching = [k for k in recent if k["evidence"].startswith(rule)]
        sample += rng.sample(matching, min(how_many, len(matching)))
    rng.shuffle(sample)  # so the rules are not grouped together in the sheet
    return sample


def main() -> None:
    try:
        # Mode "x" refuses to overwrite, so a half-filled sheet is never lost.
        file = open(AUDIT_FILE, "x", newline="")
    except FileExistsError:
        raise SystemExit(f"{AUDIT_FILE} already exists; delete it yourself to redraw.")

    sample = draw_sample(load_answer_key())
    with file:
        writer = csv.writer(file)
        # The key's own answer is deliberately left out: seeing it first would
        # nudge the checker towards agreeing with it.
        writer.writerow(["number", "url", "your_class", "notes"])
        for key in sample:
            writer.writerow([key["number"], key["url"], "", ""])
    print(f"Wrote {len(sample)} rows to {AUDIT_FILE}")


if __name__ == "__main__":
    main()
