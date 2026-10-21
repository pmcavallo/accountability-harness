"""Tests for the framework-neutral core (no LangChain needed)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from accountability_harness import Harness, Scope, render_report


def make_harness(tmp_path, **scope_kwargs) -> Harness:
    scope_kwargs.setdefault("allowed_tools", {"read_data"})
    return Harness(Scope(name="t", **scope_kwargs), log_dir=tmp_path, agent_name="t")


def read_log(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def actions(log_path: Path) -> list[dict]:
    return [e for e in read_log(log_path) if e["type"] == "action"]


def test_decorator_records_call_and_returns_result(tmp_path):
    harness = make_harness(tmp_path)

    @harness.tool
    def read_data(key: str) -> str:
        return f"value for {key}"

    assert read_data("a") == "value for a"
    assert read_data.__name__ == "read_data"
    log_path = harness.finalize()
    [action] = actions(log_path)
    assert action["tool"] == "read_data"
    assert action["in_scope"] is True
    assert action["status"] == "ok"
    assert "VIOLATION" not in render_report(log_path)


def test_decorator_with_explicit_name(tmp_path):
    harness = make_harness(tmp_path)

    @harness.tool(name="read_data")
    def fetch() -> str:
        return "x"

    fetch()
    [action] = actions(harness.finalize())
    assert action["tool"] == "read_data"
    assert action["in_scope"] is True


def test_wrap_records_positional_and_keyword_args_the_same(tmp_path):
    harness = make_harness(tmp_path)

    def read_data(email_id: int, verbose: bool = False) -> str:
        return "ok"

    wrapped = harness.wrap(read_data)
    wrapped(1)
    wrapped(email_id=1)
    first, second = actions(harness.finalize())
    assert first["args_summary"] == second["args_summary"] == "{'email_id': 1, 'verbose': False}"  # defaults filled in


def test_tool_not_in_scope_is_flagged(tmp_path):
    harness = make_harness(tmp_path)
    send_email = harness.wrap(lambda to: "sent", name="send_email")
    send_email("someone@outside.example")
    log_path = harness.finalize()
    [action] = actions(log_path)
    assert action["in_scope"] is False
    assert "not in the declared scope" in action["scope_reason"]
    assert "[VIOLATION]" in render_report(log_path)
    assert harness.violations == 1


def test_mutation_not_allowed_is_flagged(tmp_path):
    harness = make_harness(
        tmp_path,
        allowed_tools={"read_data", "write_data"},
        mutating_tools={"write_data"},
        mutations_allowed=False,
    )
    harness.wrap(lambda payload: "wrote", name="write_data")("x")
    log_path = harness.finalize()
    [action] = actions(log_path)
    [mutation] = [e for e in read_log(log_path) if e["type"] == "mutation"]
    assert action["in_scope"] is False
    assert "does not allow mutations" in action["scope_reason"]
    assert mutation["allowed"] is False
    assert "NOT permitted by scope" in render_report(log_path)


def test_mutation_allowed_is_recorded_without_violation(tmp_path):
    harness = make_harness(
        tmp_path,
        allowed_tools={"write_data"},
        mutating_tools={"write_data"},
        mutations_allowed=True,
    )
    harness.wrap(lambda payload: "wrote", name="write_data")("x")
    log_path = harness.finalize()
    [mutation] = [e for e in read_log(log_path) if e["type"] == "mutation"]
    assert mutation["allowed"] is True
    assert harness.violations == 0
    assert harness.mutations == 1


def test_error_is_recorded_and_reraised(tmp_path):
    harness = make_harness(tmp_path)

    @harness.tool
    def read_data() -> str:
        raise ValueError("source unavailable")

    with pytest.raises(ValueError):
        read_data()
    [action] = actions(harness.finalize())
    assert action["status"] == "error"
    assert "source unavailable" in action["output_summary"]
    assert action["in_scope"] is True


def test_out_of_scope_error_counts_as_violation(tmp_path):
    harness = make_harness(tmp_path)

    @harness.tool
    def delete_records() -> str:
        raise RuntimeError("permission denied")

    with pytest.raises(RuntimeError):
        delete_records()
    log_path = harness.finalize()
    end = read_log(log_path)[-1]
    assert end["violations"] == 1
    assert render_report(log_path).count("[VIOLATION]") == 1


def test_failed_mutating_call_is_recorded_as_unknown_change(tmp_path):
    harness = make_harness(tmp_path, mutating_tools={"send_email"})

    @harness.tool
    def send_email(to: str) -> str:
        raise RuntimeError("mail server unavailable")

    with pytest.raises(RuntimeError):
        send_email("someone@outside.example")
    log_path = harness.finalize()
    [mutation] = [e for e in read_log(log_path) if e["type"] == "mutation"]
    assert mutation["what_changed"].startswith("unknown")
    assert harness.mutations == 1


def test_summary_and_report_agree_on_mixed_run(tmp_path):
    harness = make_harness(
        tmp_path,
        allowed_tools={"read_data", "write_data"},
        mutating_tools={"write_data", "send_email"},
    )
    read_data = harness.wrap(lambda: "x", name="read_data")
    write_data = harness.wrap(lambda: "y", name="write_data")

    def fail() -> str:
        raise RuntimeError("boom")

    send_email = harness.wrap(fail, name="send_email")
    read_data()
    write_data()
    with pytest.raises(RuntimeError):
        send_email()
    log_path = harness.finalize()
    end = read_log(log_path)[-1]
    report = render_report(log_path)
    assert (end["violations"], end["mutations"]) == (2, 2)
    assert report.count("[VIOLATION]") == end["violations"]
    assert "3 actions (0 incomplete, 0 blocked), 2 violation(s), 2 mutation(s)" in report
    assert "does not match the log" not in report


def test_report_warns_when_summary_disagrees_with_log(tmp_path):
    harness = make_harness(tmp_path)
    harness.wrap(lambda: "x", name="send_email")()
    log_path = harness.finalize()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    end = json.loads(lines[-1])
    end["violations"] = 0
    lines[-1] = json.dumps(end)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert "does not match the log" in render_report(log_path)


def test_long_output_and_args_are_truncated(tmp_path):
    harness = Harness(
        Scope(name="t", allowed_tools={"read_data"}), log_dir=tmp_path, max_text=50
    )
    harness.wrap(lambda text: "y" * 200, name="read_data")("x" * 200)
    [action] = actions(harness.finalize())
    assert action["output_summary"] == "y" * 50 + "... [truncated, 200 chars]"
    assert action["args_summary"].startswith("{'text': 'xxx")
    assert action["args_summary"].endswith("[truncated, 212 chars]")


def test_direct_start_and_end_calls(tmp_path):
    harness = make_harness(tmp_path)
    call_id = harness.start_call("read_data", {"key": "a"}, call_id="call-1")
    assert call_id == "call-1"
    entry = harness.end_call(call_id, "value")
    assert entry["seq"] == 1
    assert harness.end_call("unknown-id", "value") is None
    assert harness.fail_call("unknown-id", RuntimeError()) is None


def test_three_questions_present(tmp_path):
    report = render_report(make_harness(tmp_path).finalize())
    assert "What was the agent allowed to touch?" in report
    assert "What did it do while nobody was watching?" in report
    assert "How can its actions be undone?" in report
