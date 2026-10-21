"""Pin the audit log's clock for every test.

The report checks a scope's review date against the day the run was
logged, and the demo scopes are due for review by 2027-04-15. With the
real clock, tests that expect "due by" would start failing after that
day. Every log written during the tests is dated FIXED_NOW instead.
Real runs keep the real date.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from accountability_harness import audit  # noqa: E402

FIXED_NOW = "2026-10-21T12:00:00+00:00"


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(audit, "utcnow_iso", lambda: FIXED_NOW)
