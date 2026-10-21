"""Tests for the LangChain adapter. Skipped if langchain-core is not installed."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

pytest.importorskip("langchain_core")

from langchain_core.tools import StructuredTool, tool  # noqa: E402

from accountability_harness import (  # noqa: E402
    AccountabilityHandler,
    ArgRule,
    Harness,
    Scope,
    ToolCallBlocked,
    email_domain_in,
    render_report,
)


@tool
def read_data() -> str:
    """Read-only tool."""
    return "some data"


@tool
def write_data(payload: str) -> str:
    """Mutating tool."""
    return f"wrote: {payload}"


@tool
def broken_send(to: str) -> str:
    """Mutating tool that fails."""
    raise RuntimeError("mail server unavailable")


def make_handler(log_dir, **scope_kwargs):
    scope_kwargs.setdefault("allowed_tools", {"read_data"})
    return AccountabilityHandler(
        Scope(name="test", **scope_kwargs), agent_name="test-agent", log_dir=str(log_dir)
    )


def test_in_scope_action_logged(tmp_path):
    handler = make_handler(tmp_path)
    read_data.invoke({}, config={"callbacks": [handler]})
    report = render_report(handler.finalize())
    assert "read_data" in report
    assert "VIOLATION" not in report


def test_out_of_scope_flagged(tmp_path):
    handler = make_handler(tmp_path, mutating_tools={"write_data"})
    write_data.invoke({"payload": "x"}, config={"callbacks": [handler]})
    report = render_report(handler.finalize())
    assert "VIOLATION" in report
    assert "not in the declared scope" in report


def test_mutation_not_allowed_flagged(tmp_path):
    handler = make_handler(
        tmp_path, allowed_tools={"write_data"}, mutating_tools={"write_data"}
    )
    write_data.invoke({"payload": "x"}, config={"callbacks": [handler]})
    report = render_report(handler.finalize())
    assert "does not allow mutations" in report
    assert "NOT permitted by scope" in report


def test_mutation_recorded(tmp_path):
    handler = make_handler(
        tmp_path,
        allowed_tools={"read_data", "write_data"},
        mutating_tools={"write_data"},
        mutations_allowed=True,
    )
    write_data.invoke({"payload": "x"}, config={"callbacks": [handler]})
    report = render_report(handler.finalize())
    assert "How can its actions be undone?" in report
    assert "Step 1, `write_data`: no reversibility declared" in report


def test_args_recorded_like_the_core(tmp_path):
    handler = make_handler(tmp_path, allowed_tools={"write_data"}, mutations_allowed=True)
    write_data.invoke({"payload": "x"}, config={"callbacks": [handler]})
    log_path = handler.finalize()
    [action] = [
        json.loads(line)
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if '"type": "action"' in line
    ]
    assert action["args_summary"] == "{'payload': 'x'}"


def test_out_of_scope_error_counts_as_violation_and_summary_agrees(tmp_path):
    handler = make_handler(tmp_path, mutating_tools={"broken_send"})
    read_data.invoke({}, config={"callbacks": [handler]})
    with pytest.raises(RuntimeError):
        broken_send.invoke({"to": "someone@outside.example"}, config={"callbacks": [handler]})
    log_path = handler.finalize()
    end = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
    report = render_report(log_path)
    assert end["violations"] == 1
    assert report.count("[VIOLATION]") == end["violations"]
    assert f"{end['violations']} violation(s), {end['mutations']} mutation(s)" in report
    assert "does not match the log" not in report


def test_handler_can_share_a_harness_with_plain_functions(tmp_path):
    harness = Harness(Scope(name="t", allowed_tools={"read_data"}), log_dir=tmp_path)
    handler = AccountabilityHandler(harness=harness)
    read_data.invoke({}, config={"callbacks": [handler]})
    harness.wrap(lambda: "x", name="read_data")()
    report = render_report(handler.finalize())
    assert "2 tool call(s) recorded" in report


def test_handler_needs_scope_or_harness():
    with pytest.raises(ValueError):
        AccountabilityHandler()


# -- enforce mode: the handler must stop the tool before it runs ----------

RAN: list[str] = []


def _send(to: str) -> str:
    """Send an email (test double)."""
    RAN.append(to)
    return f"sent to {to}"


async def _send_async(to: str) -> str:
    """Send an email (async test double)."""
    RAN.append(to)
    return f"sent to {to}"


def enforce_handler(tmp_path, **scope_kwargs):
    scope_kwargs.setdefault("allowed_tools", {"read_data"})
    return AccountabilityHandler(Scope(name="t", **scope_kwargs), log_dir=tmp_path, mode="enforce")


INVOCATIONS = {
    "invoke": lambda tool, cb: tool.invoke({"to": "x@outside.example"}, config=cb),
    "tool_call": lambda tool, cb: tool.invoke(
        {"name": tool.name, "args": {"to": "x@outside.example"}, "id": "1", "type": "tool_call"},
        config=cb,
    ),
    "ainvoke": lambda tool, cb: asyncio.run(tool.ainvoke({"to": "x@outside.example"}, config=cb)),
}


@pytest.mark.parametrize("how", sorted(INVOCATIONS))
@pytest.mark.parametrize("handle_tool_error", [False, True])
def test_enforce_blocks_before_the_tool_runs(tmp_path, how, handle_tool_error):
    RAN.clear()
    tool = StructuredTool.from_function(_send, name="send_email", handle_tool_error=handle_tool_error)
    handler = enforce_handler(tmp_path)
    with pytest.raises(ToolCallBlocked) as blocked:
        INVOCATIONS[how](tool, {"callbacks": [handler]})
    assert RAN == []
    assert "not in the declared scope" in blocked.value.reason
    assert handler.harness.blocked == 1
    log_path = handler.finalize()
    statuses = [
        json.loads(line).get("status") for line in log_path.read_text(encoding="utf-8").splitlines()
    ]
    assert "blocked" in statuses
    assert "### Step 1: `send_email` [BLOCKED]" in render_report(log_path)


def test_enforce_blocks_an_async_tool(tmp_path):
    RAN.clear()
    tool = StructuredTool.from_function(coroutine=_send_async, name="send_email", description="Send.")
    handler = enforce_handler(tmp_path)
    with pytest.raises(ToolCallBlocked):
        asyncio.run(tool.ainvoke({"to": "x@outside.example"}, config={"callbacks": [handler]}))
    assert RAN == []


def test_enforce_lets_in_scope_calls_run(tmp_path):
    RAN.clear()
    tool = StructuredTool.from_function(_send, name="send_email")
    handler = enforce_handler(
        tmp_path, allowed_tools={"send_email"}, mutating_tools={"send_email"}, mutations_allowed=True
    )
    assert tool.invoke({"to": "a@tallowlane.example"}, config={"callbacks": [handler]}) == (
        "sent to a@tallowlane.example"
    )
    assert RAN == ["a@tallowlane.example"]
    assert handler.harness.blocked == 0


def test_observe_handler_does_not_raise_or_block(tmp_path):
    RAN.clear()
    tool = StructuredTool.from_function(_send, name="send_email")
    handler = make_handler(tmp_path)
    assert handler.raise_error is False
    tool.invoke({"to": "x@outside.example"}, config={"callbacks": [handler]})
    assert RAN == ["x@outside.example"]


def test_enforce_applies_argument_rules(tmp_path):
    RAN.clear()
    tool = StructuredTool.from_function(_send, name="send_email")
    handler = enforce_handler(
        tmp_path,
        allowed_tools={"send_email"},
        mutations_allowed=True,
        arg_rules=[
            ArgRule("send_email", "to", email_domain_in("tallowlane.example"), "internal only")
        ],
    )
    with pytest.raises(ToolCallBlocked):
        tool.invoke({"to": "x@outside.example"}, config={"callbacks": [handler]})
    tool.invoke({"to": "team@tallowlane.example"}, config={"callbacks": [handler]})
    assert RAN == ["team@tallowlane.example"]


@pytest.mark.parametrize("mode", ["observe", "enforce"])
def test_bare_string_call_fails_argument_rules(tmp_path, mode):
    """A bare string input gives the handler no named arguments, so the
    rule on 'to' cannot be checked and counts as failed."""
    RAN.clear()
    tool = StructuredTool.from_function(_send, name="send_email")
    handler = AccountabilityHandler(
        Scope(
            name="test",
            allowed_tools={"send_email"},
            mutations_allowed=True,
            arg_rules=[
                ArgRule("send_email", "to", email_domain_in("tallowlane.example"), "internal only")
            ],
        ),
        log_dir=str(tmp_path),
        mode=mode,
    )
    if mode == "enforce":
        with pytest.raises(ToolCallBlocked):
            tool.invoke("team@tallowlane.example", config={"callbacks": [handler]})
        assert RAN == []
    else:
        tool.invoke("team@tallowlane.example", config={"callbacks": [handler]})
        assert RAN == ["team@tallowlane.example"]
    report = render_report(handler.finalize())
    assert "the call has no named arguments, so the rule on argument 'to' could not be checked" in report


def test_handler_mode_follows_a_shared_harness(tmp_path):
    harness = Harness(Scope(name="t"), log_dir=tmp_path, mode="enforce")
    assert AccountabilityHandler(harness=harness).raise_error is True
