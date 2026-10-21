"""The owner summary at the top of every report."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from accountability_harness import Harness, Reversibility, Scope, render_report  # noqa: E402

MUTATING = {
    "send": Reversibility.irreversible(how="Send a correction."),
    "refund": Reversibility.compensable(how="Charge again."),
    "draft": Reversibility.reversible(how="Delete it."),
    "tag": None,
}


def summary_of(report: str) -> str:
    return report.split("## Summary for the owner")[1].split("## 1.")[0]


def run(tmp_path, calls, mode="observe", **scope_kw):
    kw = dict(name="s", allowed_tools={"send", "refund", "draft", "tag"}, mutating_tools=MUTATING, mutations_allowed=True)
    kw.update(scope_kw)
    harness = Harness(Scope(**kw), log_dir=tmp_path, mode=mode)
    for name in calls:
        harness.wrap(lambda: "done", name=name, on_block="return")()
    return render_report(harness.finalize())


def test_the_summary_comes_first_and_fits_one_screen(tmp_path):
    report = run(tmp_path, ["draft"])
    assert report.index("## Summary for the owner") < report.index("## 1. What was")
    assert len(summary_of(report).strip().splitlines()) <= 8


def test_changes_are_grouped_irreversible_first(tmp_path):
    line = next(
        l for l in summary_of(run(tmp_path, ["draft", "tag", "draft", "refund", "send"])).splitlines()
        if "Changes made" in l
    )
    assert line == (
        "- **Changes made in this run:** 1 that cannot be undone (`send`); "
        "1 that cannot be undone but can be offset (`refund`); "
        "2 that can be undone (`draft` x2); 1 with no undo plan (`tag`)."
    )


def test_approval_review_and_attention(tmp_path):
    gov = dict(owner="Operations lead", approver="Managing director", approved_on="2026-10-01",
               version="3", review_by="2027-01-01")
    summary = summary_of(run(tmp_path, ["draft"], allowed_tools={"draft"},
                             rationale={"draft": "Replies need drafts."}, **gov))
    assert "`s` version 3, owned by Operations lead, approved by Managing director on 2026-10-01." in summary
    assert "- **Review:** due by 2027-01-01." in summary
    assert "- **Needs your attention:** nothing." in summary


def test_missing_approval_overdue_review_blocked_and_flagged(tmp_path):
    summary = summary_of(run(tmp_path, ["send"], mode="enforce", allowed_tools={"draft"}, review_by="2026-01-01"))
    assert "owned by nobody on record, not approved by anyone on record." in summary
    assert "was due by 2026-01-01; it is overdue." in summary
    assert "1 action(s) blocked before they ran" in summary
    assert "governance finding(s), listed under question 1" in summary
    assert "- **Changes made in this run:** none." in summary
    flagged = summary_of(run(tmp_path / "o", ["send"], allowed_tools={"draft"}))
    assert "1 action(s) outside the scope that were flagged" in flagged


def test_chain_status_and_how_to_recreate(tmp_path):
    harness = Harness(Scope(name="s"), log_dir=tmp_path)
    log = harness.finalize()
    summary = summary_of(render_report(log))
    assert "- **Audit log:** hash chain intact" in summary
    assert f"`accountability-harness report {log.name}`" in summary
    assert "no review date set." in summary
