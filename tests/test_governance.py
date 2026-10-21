"""The scope as a governed artifact: TOML files, fingerprints, findings."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from accountability_harness import Harness, Scope, fingerprint, load_scope, render_report  # noqa: E402
from accountability_harness.governance import findings  # noqa: E402

SCOPES = ROOT / "demo" / "scopes"
COMPLETE = """
name = "s"
version = "2.1"
owner = "Operations lead"
approver = "Managing director"
approved_on = 2026-10-01
review_by = 2027-01-01
change_note = "Adds send_email."
allowed_tools = ["read_inbox", "send_email"]
mutations_allowed = true

[rationale]
read_inbox = "Needs to see what arrived."
send_email = "Internal alerts only."

[mutating_tools.send_email]
kind = "irreversible"
how = "Send a correction."

[mutating_tools.archive]

[[arg_rules]]
tool = "send_email"
arg = "to"
check = "email_domain_in"
values = ["tallowlane.example"]
description = "Internal email only"

[[arg_rules]]
tool = "send_email"
arg = "priority"
check = "value_in"
values = ["low", "normal"]
description = "No urgent email"
"""


def write(tmp_path, text, name="scope.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def read_log(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_scope_file_loads_every_field(tmp_path):
    scope = load_scope(write(tmp_path, COMPLETE))
    assert scope.allowed_tools == {"read_inbox", "send_email"}
    assert (scope.owner, scope.approver, scope.version) == ("Operations lead", "Managing director", "2.1")
    assert (scope.approved_on, scope.review_by) == ("2026-10-01", "2027-01-01")
    assert scope.rationale["send_email"] == "Internal alerts only."
    assert scope.reversibility("send_email").kind == "irreversible"
    assert scope.is_mutation("archive") and scope.reversibility("archive") is None
    ok, _ = scope.check("send_email", {"to": "team@tallowlane.example", "priority": "low"})
    assert ok
    ok, reason = scope.check("send_email", {"to": "x@outside.example", "priority": "low"})
    assert not ok and "Internal email only" in reason
    ok, reason = scope.check("send_email", {"to": "team@tallowlane.example", "priority": "urgent"})
    assert not ok and "No urgent email" in reason
    assert [r["check"] for r in scope.to_dict()["arg_rules"]] == [
        "email_domain_in('tallowlane.example')",
        "value_in('low', 'normal')",
    ]


def test_a_scope_file_cannot_name_a_custom_check(tmp_path):
    text = COMPLETE.replace('check = "value_in"', 'check = "my_check"')
    with pytest.raises(ValueError, match="custom checks in Python"):
        load_scope(write(tmp_path, text))


def test_python_built_scopes_still_work_and_custom_checks_are_labeled():
    from accountability_harness import ArgRule

    rule = ArgRule("t", "n", lambda v: v > 0, "positive")
    scope = Scope(name="p", allowed_tools={"t"}, arg_rules=[rule])
    assert scope.check("t", {"n": 1}) == (True, "in scope")
    assert scope.to_dict()["arg_rules"][0]["check"] == "custom Python check"


def test_demo_scope_files_load_with_complete_governance():
    for name in ("inbox-assistant", "inbox-assistant-review-only", "inbox-assistant-internal-email"):
        scope = load_scope(SCOPES / f"{name}.toml")
        assert scope.name == name and scope.approver and scope.owner
        assert findings(scope.to_dict(), "2026-10-21") == []


def test_fingerprint_is_written_to_the_log_and_identifies_the_version(tmp_path):
    scope = load_scope(write(tmp_path, COMPLETE))
    log = Harness(scope, log_dir=tmp_path).finalize()
    [entry] = [e for e in read_log(log) if e["type"] == "scope"]
    assert entry["fingerprint"] == fingerprint(scope.to_dict()) == fingerprint(entry["scope"])
    assert len(entry["fingerprint"]) == 64
    assert entry["scope"]["governance"]["approver"] == "Managing director"
    assert fingerprint(load_scope(write(tmp_path, COMPLETE, "again.toml")).to_dict()) == entry["fingerprint"]
    edited = load_scope(write(tmp_path, COMPLETE.replace('version = "2.1"', 'version = "2.2"'), "b.toml"))
    assert fingerprint(edited.to_dict()) != entry["fingerprint"]
    assert entry["fingerprint"] in render_report(log)


def test_findings_for_each_gap():
    gaps = findings(Scope(name="bare", allowed_tools={"a", "b"}).to_dict(), "2026-10-21")
    assert gaps == [
        "No one is recorded as having approved this scope.",
        "No one is recorded as the owner of this scope.",
        "No reason is recorded for allowing: `a`, `b`.",
    ]
    overdue = Scope(name="o", owner="x", approver="y", review_by="2026-09-30").to_dict()
    assert findings(overdue, "2026-10-21") == [
        "The scope was due for review by 2026-09-30; this run was on 2026-10-21."
    ]
    assert findings(overdue, "2026-09-30") == []  # due on the day, not yet passed


def test_a_log_from_an_older_version_says_so():
    assert findings({"name": "old", "allowed_tools": ["a"]}, "2026-10-21") == [
        "This log was written by an older version that did not record governance fields."
    ]


def test_an_unapproved_scope_still_runs_and_the_report_lists_findings(tmp_path):
    scope = load_scope(SCOPES / "inbox-assistant-unapproved.toml")
    harness = Harness(scope, log_dir=tmp_path)
    assert harness.wrap(lambda: "ok", name="read_inbox")() == "ok"
    report = render_report(harness.finalize())
    assert "### Governance findings" in report
    assert "No one is recorded as having approved this scope." in report
    assert "The scope was due for review by 2026-09-30" in report
    assert "No reason is recorded for allowing: `add_client_contact`." in report
    assert "### Step 1: `read_inbox` [OK]" in report


def test_the_report_takes_an_injectable_run_date(tmp_path):
    scope = load_scope(SCOPES / "inbox-assistant.toml")  # review_by 2027-04-15
    log = Harness(scope, log_dir=tmp_path).finalize()
    assert "- **Review:** due by 2027-04-15." in render_report(log)  # logged on the pinned test date
    assert "- **Review:** due by 2027-04-15." in render_report(log, run_date="2027-04-15")
    late = render_report(log, run_date="2027-04-16")
    assert "- **Review:** was due by 2027-04-15; it is overdue." in late
    assert "The scope was due for review by 2027-04-15; this run was on 2027-04-16." in late


def test_tests_run_on_a_pinned_clock(tmp_path):
    from conftest import FIXED_NOW

    log = Harness(Scope(name="s", allowed_tools={"a"}), log_dir=tmp_path).finalize()
    assert all(e["logged_at"] == FIXED_NOW for e in read_log(log))
