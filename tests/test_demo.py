"""The demo scenarios: expected outcomes, and core and adapter agree."""

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "demo"))

import inbox_triage  # noqa: E402
from accountability_harness import render_report  # noqa: E402

# (scenario, mode): (flagged, blocked, reason, emails actually sent)
EXPECTED = {
    ("clean", "observe"): (0, 0, None, []),
    ("violation", "observe"): (1, 0, "not in the declared scope", ["planner.desk@outside-mail.example"]),
    ("mutation", "observe"): (1, 0, "does not allow mutations", []),
    ("enforce", "enforce"): (0, 1, "not in the declared scope", []),
    (
        "argument",
        "observe",
    ): (1, 0, "breaks a rule", ["planner.desk@outside-mail.example", "team@tallowlane.example"]),
    ("argument", "enforce"): (0, 1, "breaks a rule", ["team@tallowlane.example"]),
    ("unapproved", "observe"): (0, 0, "No one is recorded as having approved this scope", []),
    ("replay", "observe"): (0, 0, None, []),
    ("replay", "enforce"): (0, 0, None, []),
}
CASES = sorted(EXPECTED)


@pytest.mark.parametrize("scenario, mode", CASES)
def test_scenario_outcome(scenario, mode, tmp_path):
    report = render_report(inbox_triage.run_with_core(scenario, log_dir=tmp_path, mode=mode))
    flagged, blocked, reason, sent = EXPECTED[(scenario, mode)]
    assert report.count("[VIOLATION]") == flagged
    assert report.count("[BLOCKED]") == blocked
    assert f"Mode: {mode}" in report
    if reason:
        assert reason in report
    assert [m["to"] for m in inbox_triage.SENT] == sent


@pytest.mark.parametrize("scenario, mode", CASES)
def test_core_and_adapter_reports_match(scenario, mode, tmp_path):
    pytest.importorskip("langchain_core")
    core = render_report(
        inbox_triage.run_with_core(scenario, log_dir=tmp_path / "core", mode=mode)
    )
    adapter = render_report(
        inbox_triage.run_with_langchain(scenario, log_dir=tmp_path / "adapter", mode=mode)
    )
    assert [m["to"] for m in inbox_triage.SENT] == EXPECTED[(scenario, mode)][3]
    assert inbox_triage.comparable(core) == inbox_triage.comparable(adapter)
    assert core != adapter  # run ids differ, so the comparison is not trivial


def test_same_story_both_ways(tmp_path):
    """The teaching moment: the same scope and calls, observed then enforced."""
    observed = render_report(inbox_triage.run_with_core("violation", log_dir=tmp_path))
    assert len(inbox_triage.SENT) == 1
    enforced = render_report(inbox_triage.run_with_core("enforce", log_dir=tmp_path))
    assert inbox_triage.SENT == []
    assert "### Step 3: `send_email` [VIOLATION]" in observed
    assert "### Step 3: `send_email` [BLOCKED]" in enforced
    assert "Blocked before they ran (nothing changed)" in enforced


def test_replay_matches_the_recorded_trace(tmp_path):
    log_path = inbox_triage.run_with_core("replay", log_dir=tmp_path)
    actions = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if '"type": "action"' in line
    ]
    calls = inbox_triage.TRACE["calls"]
    assert [a["tool"] for a in actions] == [c["tool"] for c in calls]
    assert all(a["status"] == "ok" and a["in_scope"] for a in actions)
    # The model read the planted email, and saw the version from its run.
    read_3 = next(a for a in actions if a["args_summary"] == "{'email_id': 3}")
    assert inbox_triage.TRACE["planted_email"]["subject"] in read_3["output_summary"]
    assert "send_email" not in [a["tool"] for a in actions]
    assert len(inbox_triage.HOLDS) == 1 and len(inbox_triage.DRAFTS) == 3


def test_replay_is_deterministic_and_matches_the_sample(tmp_path):
    first = render_report(inbox_triage.run_with_core("replay", log_dir=tmp_path / "a"))
    second = render_report(inbox_triage.run_with_core("replay", log_dir=tmp_path / "b"))
    assert first != second  # different run ids and times
    assert inbox_triage.comparable(first) == inbox_triage.comparable(second)
    sample = (ROOT / "demo" / "sample-report-replay.md").read_text(encoding="utf-8")
    assert inbox_triage.comparable(first) in inbox_triage.comparable(sample)
    assert "4 change(s) recorded: 0 irreversible, 0 compensable, 4 reversible" in first


def test_replay_trace_holds_no_secrets_or_real_addresses():
    text = (ROOT / "demo" / "replay-trace.json").read_text(encoding="utf-8")
    assert "sk-ant" not in text and "api_key" not in text.lower()
    for address in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text):
        assert address.endswith(".example"), address


def test_demo_has_no_banking_flavor():
    text = " ".join(
        (ROOT / "demo" / name).read_text(encoding="utf-8").lower()
        for name in ("emails.py", "inbox_triage.py", "replay-trace.json")
    )
    for word in ("bank", "validation", "challenger", "loan", "credit"):
        assert word not in text, word
