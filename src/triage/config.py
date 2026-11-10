"""Project-wide settings. Everything that defines "which data" lives here."""

from pathlib import Path

# The tracker we triage.
REPO_OWNER = "huggingface"
REPO_NAME = "huggingface_hub"

# The pool is every issue closed on or before this date. Fixing the date means
# the pool does not grow each time someone re-runs discovery.
POOL_CLOSED_ON_OR_BEFORE = "2026-10-31"

DATA_DIR = Path("data")
POOL_IDS_FILE = DATA_DIR / "issue_ids" / "pool.txt"  # committed
ISSUE_CACHE_DIR = DATA_DIR / "cache" / "issues"  # not committed
