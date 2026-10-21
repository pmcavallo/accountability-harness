"""Tests for reversibility declarations, the report built from them, and
the M2 fixes (multi-line rendering, incomplete calls). No LangChain needed."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "demo"))

from accountability_harness import Harness, Reversibility, Scope, render_report  # noqa: E402

UNDO_DRAFT = Reversibility.reversible(how="Delete the draft.")
UNDO_HOLD = Reversibility.reversible(how="Release the hold", window="until the hold expires in 48 hours")
REFUND = Reversibility.compensable(how="Issue a refund to the same card", window="within 30 days")
SEND = Reversibility.irreversible(how="Send a correction to the same recipient")

DECLARED = {
    "draft_reply": UNDO_DRAFT,
    "place_hold": UNDO_HOLD,
    "charge_card": REFUND,
    "send_email": SEND,
    "add_contact": None,
}


def make_harness(tmp_path, mutating_tools=DECLARED, **kwargs) -> Harness:
    kwargs.setdefault("allowed_tools", set(DECLARED))
    kwargs.setdefault("mutations_allowed", True)
    scope = Scope(name="t", mutating_tools=mutating_tools, **kwargs)
    return Harness(scope, log_dir=tmp_path, agent_name="t")


def read_log(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def of_type(log_path: Path, kind: str) -> list[dict]:
    return [e for e in read_log(log_path) if e["type"] == kind]


def call(harness: Harness, name: str, output: str = "done") -> None:
    harness.wrap(lambda: output, name=name)()


# -- the declaration ----------------------------------------------------


def test_each_kind_from_factories():
    assert (UNDO_DRAFT.kind, UNDO_DRAFT.window) == ("reversible", None)
    assert (REFUND.kind, REFUND.window) == ("compensable", "within 30 days")
    assert SEND.kind == "irreversible"
    assert Reversibility("reversible", "Undo it.").to_dict() == {
        "kind": "reversible",
        "how": "Undo it.",
        "window": None,
    }


def test_invalid_declarations_are_rejected():
    with pytest.raises(ValueError):
        Reversibility("maybe", "Try something.")
    with pytest.raises(ValueError):
        Reversibility.reversible(how="  ")


def test_set_form_is_backward_compatible_and_undeclared():
    scope = Scope(name="t", allowed_tools={"send_email"}, mutating_tools={"send_email"})
    assert scope.is_mutation("send_email")
    assert scope.reversibility("send_email") is None
    assert scope.to_dict()["mutating_tools"] == ["send_email"]
    assert scope.to_dict()["reversibility"] == {"send_email": None}


def test_mapping_form_with_undeclared_tool():
    scope = Scope(name="t", mutating_tools=DECLARED)
    assert scope.reversibility("place_hold") == UNDO_HOLD
    assert scope.reversibility("add_contact") is None
    assert scope.is_mutation("add_contact")
    assert not scope.is_mutation("read_inbox")


def test_declarations_are_written_to_the_log_before_the_run(tmp_path):
    log_path = make_harness(tmp_path).finalize()
    [scope_entry] = of_type(log_path, "scope")
    declared = scope_entry["scope"]["reversibility"]
    assert declared["place_hold"] == {
        "kind": "reversible",
        "how": "Release the hold",
        "window": "until the hold expires in 48 hours",
    }
    assert declared["add_contact"] is None
    entries = read_log(log_path)
    assert entries.index(scope_entry) < len(entries) - 1


def test_mutation_entry_carries_its_declaration(tmp_path):
    harness = make_harness(tmp_path)
    call(harness, "charge_card")
    call(harness, "add_contact")
    declared, undeclared = of_type(harness.finalize(), "mutation")
    assert declared["reversibility"]["kind"] == "compensable"
    assert declared["outcome"] == "completed"
    assert undeclared["reversibility"] is None


def test_failed_mutation_keeps_unknown_outcome_and_declaration(tmp_path):
    harness = make_harness(tmp_path)

    def fail() -> str:
        raise RuntimeError("mail server unavailable")

    with pytest.raises(RuntimeError):
        harness.wrap(fail, name="send_email")()
    log_path = harness.finalize()
    [mutation] = of_type(log_path, "mutation")
    assert mutation["outcome"] == "unknown"
    assert mutation["reversibility"]["kind"] == "irreversible"
    report = render_report(log_path)
    assert "Step 1, `send_email`: cannot be undone." in report
    assert "Outcome unknown" in report


# -- the report ---------------------------------------------------------


def test_question_1_lists_each_mutating_tool_with_its_declaration(tmp_path):
    report = render_report(make_harness(tmp_path).finalize())
    q1 = report.split("## 2.")[0]
    assert "  - `send_email` (irreversible): cannot be undone." in q1
    assert "  - `charge_card` (compensable): cannot be undone, but can be offset." in q1
    assert "Window: until the hold expires in 48 hours." in q1
    assert "  - `add_contact`: no reversibility declared." in q1
    position = {name: q1.index(f"  - `{name}`") for name in DECLARED}
    assert position["send_email"] < position["charge_card"] < position["draft_reply"]
    assert position["draft_reply"] < position["add_contact"]


def test_question_1_with_no_mutating_tools(tmp_path):
    report = render_report(make_harness(tmp_path, mutating_tools=set()).finalize())
    assert "how each change can be undone:** none" in report


def test_question_3_sentences(tmp_path):
    harness = make_harness(tmp_path)
    for name in ("draft_reply", "place_hold", "charge_card", "send_email", "add_contact"):
        call(harness, name)
    q3 = render_report(harness.finalize()).split("## 3.")[1]
    assert "- Step 1, `draft_reply`: can be undone. Undo: delete the draft." in q3
    assert (
        "- Step 2, `place_hold`: can be undone. Undo: release the hold. "
        "Window: until the hold expires in 48 hours." in q3
    )
    assert "Offset: issue a refund to the same card. Window: within 30 days." in q3
    assert (
        "- Step 4, `send_email`: cannot be undone. Nothing restores the prior state. "
        "What can still be done: send a correction to the same recipient." in q3
    )
    assert "### No reversibility declared" in q3
    assert "- Step 5, `add_contact`: no reversibility declared." in q3


def test_question_3_leads_with_irreversible(tmp_path):
    harness = make_harness(tmp_path)
    for name in ("add_contact", "draft_reply", "charge_card", "send_email"):
        call(harness, name)
    q3 = render_report(harness.finalize()).split("## 3.")[1]
    headings = [line for line in q3.splitlines() if line.startswith("### ")]
    assert headings == [
        "### Cannot be undone (irreversible)",
        "### Cannot be undone, but can be offset (compensable)",
        "### Can be undone (reversible)",
        "### No reversibility declared",
    ]


def test_question_3_marks_changes_not_permitted(tmp_path):
    harness = make_harness(tmp_path, allowed_tools={"draft_reply"})
    call(harness, "send_email")
    report = render_report(harness.finalize())
    assert "- Step 1, `send_email` (NOT permitted by scope): cannot be undone." in report


def test_summary_counts_by_kind(tmp_path):
    harness = make_harness(tmp_path)
    for name in ("draft_reply", "draft_reply", "place_hold", "charge_card", "send_email", "add_contact"):
        call(harness, name)
    report = render_report(harness.finalize())
    assert (
        "6 change(s) recorded: 1 irreversible, 1 compensable, 3 reversible, "
        "1 with no reversibility declared." in report
    )
    assert report.splitlines()[-1] == (
        "Summary (observe mode): 6 actions (0 incomplete, 0 blocked), 0 violation(s), 6 mutation(s): "
        "1 irreversible, 1 compensable, 3 reversible, 1 undeclared."
    )


# -- multi-line rendering ---------------------------------------------------


def test_multiline_demo_output_does_not_break_the_list(tmp_path):
    import inbox_triage

    report = render_report(inbox_triage.run_with_core("violation", log_dir=tmp_path))
    lines = report.splitlines()
    # Every line of the inbox listing sits inside the indented block.
    assert "  [2] orders@green-fork-catering.example: Menu options for the Nov 8 reception" in lines
    assert not any(line.startswith(("[2]", "Subject:", "Hi! Note")) for line in lines)
    assert "  ```text" in lines


def test_text_containing_a_fence_gets_a_longer_fence(tmp_path):
    harness = make_harness(tmp_path, allowed_tools={"read_data"})
    call(harness, "read_data", output="line one\n```\nline three")
    lines = render_report(harness.finalize()).splitlines()
    assert "  ````text" in lines
    assert "  ```" in lines  # the text's own fence, indented as content


# -- incomplete calls -------------------------------------------------------


def test_incomplete_in_scope_call(tmp_path):
    harness = make_harness(tmp_path, allowed_tools={"read_data"})
    harness.start_call("read_data", {"key": "a"})
    log_path = harness.finalize()
    [action] = of_type(log_path, "action")
    assert action["status"] == "incomplete"
    assert action["in_scope"] is True
    assert read_log(log_path)[-1]["incomplete"] == 1
    report = render_report(log_path)
    assert "- Status: incomplete" in report
    assert "1 actions (1 incomplete, 0 blocked), 0 violation(s)" in report
    assert "does not match the log" not in report


def test_incomplete_out_of_scope_call_is_a_violation(tmp_path):
    harness = make_harness(tmp_path, allowed_tools={"read_data"})
    harness.start_call("delete_records")
    log_path = harness.finalize()
    assert harness.violations == 1
    assert render_report(log_path).count("[VIOLATION]") == 1


def test_incomplete_mutating_call_has_unknown_outcome(tmp_path):
    harness = make_harness(tmp_path)
    harness.start_call("place_hold", {"date": "2026-11-21"})
    log_path = harness.finalize()
    [mutation] = of_type(log_path, "mutation")
    assert mutation["outcome"] == "unknown"
    assert mutation["reversibility"]["kind"] == "reversible"
    report = render_report(log_path)
    assert "Outcome unknown" in report
    assert "Undo: release the hold." in report


# -- demo ---------------------------------------------------------------


def test_demo_reports_show_declarations(tmp_path):
    import inbox_triage

    clean = render_report(inbox_triage.run_with_core("clean", log_dir=tmp_path))
    violation = render_report(inbox_triage.run_with_core("violation", log_dir=tmp_path))
    assert "- Step 6, `add_client_contact`: no reversibility declared." in clean
    assert "Window: until the hold expires, 48 hours after it is placed." in clean
    assert "### Cannot be undone (irreversible)" in violation
    assert "1 irreversible, 0 compensable, 0 reversible, 0 undeclared." in violation
