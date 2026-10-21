"""Tests for observe and enforce modes and argument rules (no LangChain needed)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from accountability_harness import (  # noqa: E402
    ArgRule,
    Harness,
    Reversibility,
    Scope,
    ToolCallBlocked,
    email_domain_in,
    render_report,
    value_in,
)

INTERNAL_ONLY = ArgRule(
    tool="send_email",
    arg="to",
    check=email_domain_in("tallowlane.example"),
    description="Email may only go to tallowlane.example addresses",
)

# Each failure path: (scope kwargs, call args, expected reason).
FAILURE_PATHS = {
    "not in scope": (
        {"allowed_tools": {"read_inbox"}},
        {"to": "team@tallowlane.example"},
        "not in the declared scope",
    ),
    "mutation not allowed": (
        {"allowed_tools": {"send_email"}, "mutations_allowed": False},
        {"to": "team@tallowlane.example"},
        "does not allow mutations",
    ),
    "argument rule failed": (
        {"allowed_tools": {"send_email"}, "mutations_allowed": True, "arg_rules": [INTERNAL_ONLY]},
        {"to": "planner.desk@outside-mail.example"},
        "breaks a rule: Email may only go to tallowlane.example addresses",
    ),
}


def make_harness(tmp_path, mode="observe", **scope_kwargs) -> Harness:
    scope_kwargs.setdefault(
        "mutating_tools",
        {"send_email": Reversibility.irreversible(how="Send a correction.")},
    )
    return Harness(Scope(name="t", **scope_kwargs), log_dir=tmp_path, mode=mode)


def read_log(log_path: Path) -> list[dict]:
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


def make_send(sent: list):
    def send_email(to: str) -> str:
        sent.append(to)
        return f"sent to {to}"

    return send_email


# -- both modes on every failure path -----------------------------------------


@pytest.mark.parametrize("path", sorted(FAILURE_PATHS))
def test_observe_mode_flags_but_runs(tmp_path, path):
    scope_kwargs, args, reason = FAILURE_PATHS[path]
    harness = make_harness(tmp_path, **scope_kwargs)
    sent: list = []
    assert harness.wrap(make_send(sent))(**args).startswith("sent to")
    assert sent == [args["to"]]
    log_path = harness.finalize()
    [action] = [e for e in read_log(log_path) if e["type"] == "action"]
    assert (action["status"], action["in_scope"]) == ("ok", False)
    assert reason in action["scope_reason"]
    assert (harness.violations, harness.blocked) == (1, 0)
    assert "[VIOLATION]" in render_report(log_path)


@pytest.mark.parametrize("path", sorted(FAILURE_PATHS))
def test_enforce_mode_blocks_and_never_runs(tmp_path, path):
    scope_kwargs, args, reason = FAILURE_PATHS[path]
    harness = make_harness(tmp_path, mode="enforce", **scope_kwargs)
    sent: list = []
    with pytest.raises(ToolCallBlocked) as blocked:
        harness.wrap(make_send(sent))(**args)
    assert sent == []
    assert blocked.value.tool == "send_email"
    assert reason in blocked.value.reason
    log_path = harness.finalize()
    entries = read_log(log_path)
    [action] = [e for e in entries if e["type"] == "action"]
    assert (action["status"], action["in_scope"]) == ("blocked", False)
    assert not [e for e in entries if e["type"] == "mutation"]
    assert (harness.violations, harness.blocked, harness.mutations) == (1, 1, 0)
    report = render_report(log_path)
    assert "### Step 1: `send_email` [BLOCKED]" in report
    assert report.count("the tool did not run") == 2  # violations list and Result, said once each
    assert "Blocked before it ran" not in report


def test_enforce_mode_lets_in_scope_calls_run(tmp_path):
    harness = make_harness(
        tmp_path,
        mode="enforce",
        allowed_tools={"send_email"},
        mutations_allowed=True,
        arg_rules=[INTERNAL_ONLY],
    )
    sent: list = []
    harness.wrap(make_send(sent))("team@tallowlane.example")
    assert sent == ["team@tallowlane.example"]
    assert (harness.violations, harness.blocked, harness.mutations) == (0, 0, 1)


# -- raise or return a refusal ------------------------------------------------


def test_on_block_return_gives_a_plain_text_refusal(tmp_path):
    harness = make_harness(tmp_path, mode="enforce", allowed_tools={"read_inbox"})
    sent: list = []
    result = harness.wrap(make_send(sent), on_block="return")("x@outside-mail.example")
    assert result == "blocked: tool 'send_email' is not in the declared scope"
    assert sent == []
    assert harness.blocked == 1


def test_decorator_accepts_on_block(tmp_path):
    harness = make_harness(tmp_path, mode="enforce", allowed_tools={"read_inbox"})

    @harness.tool(on_block="return")
    def send_email(to: str) -> str:
        raise AssertionError("must not run")

    assert send_email("x@outside-mail.example").startswith("blocked: ")


def test_direct_start_call_raises_in_enforce_mode(tmp_path):
    harness = make_harness(tmp_path, mode="enforce", allowed_tools={"read_inbox"})
    with pytest.raises(ToolCallBlocked):
        harness.start_call("delete_records", {})
    assert harness.blocked == 1
    harness.finalize()
    assert harness.incomplete == 0  # a blocked call is not left open


def test_invalid_mode_and_on_block_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        make_harness(tmp_path, mode="block")
    with pytest.raises(ValueError):
        make_harness(tmp_path).wrap(lambda: "x", on_block="ignore")


# -- summary and report agreement -----------------------------------------------


def test_summary_and_report_agree_with_blocked_calls(tmp_path):
    harness = make_harness(
        tmp_path,
        mode="enforce",
        allowed_tools={"read_inbox", "send_email"},
        mutations_allowed=True,
        arg_rules=[INTERNAL_ONLY],
    )
    send = harness.wrap(make_send([]), on_block="return")
    harness.wrap(lambda: "inbox", name="read_inbox")()
    send("planner.desk@outside-mail.example")
    send("team@tallowlane.example")
    harness.wrap(lambda: "x", name="delete_records", on_block="return")()
    log_path = harness.finalize()
    end = read_log(log_path)[-1]
    report = render_report(log_path)
    assert (end["violations"], end["blocked"], end["mutations"], end["mode"]) == (2, 2, 1, "enforce")
    assert report.count("[BLOCKED]") == end["blocked"]
    assert report.count("[VIOLATION]") + report.count("[BLOCKED]") == end["violations"]
    assert "### Violations: 2 (2 blocked)" in report
    assert report.splitlines()[-1].startswith(
        "Summary (enforce mode): 4 actions (0 incomplete, 2 blocked), 2 violation(s), 1 mutation(s)"
    )
    assert "does not match the log" not in report


def test_report_warns_when_blocked_count_disagrees(tmp_path):
    harness = make_harness(tmp_path, mode="enforce", allowed_tools={"read_inbox"})
    harness.wrap(lambda: "x", name="send_email", on_block="return")()
    log_path = harness.finalize()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    end = json.loads(lines[-1])
    end["blocked"] = 0
    lines[-1] = json.dumps(end)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert "does not match the log" in render_report(log_path)


def test_report_shows_mode(tmp_path):
    observe = render_report(make_harness(tmp_path / "o").finalize())
    enforce = render_report(make_harness(tmp_path / "e", mode="enforce").finalize())
    assert "Mode: observe (records and flags out-of-scope calls; does not block them)" in observe
    assert "Mode: enforce (blocks out-of-scope calls before they run)" in enforce
    assert "Summary (enforce mode)" in enforce


def test_report_without_mode_in_log_reads_as_observe(tmp_path):
    log_path = make_harness(tmp_path).finalize()
    lines = log_path.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])
    del meta["mode"]
    lines[0] = json.dumps(meta)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert "Mode: observe" in render_report(log_path)


def test_question_3_says_a_blocked_change_changed_nothing(tmp_path):
    harness = make_harness(tmp_path, mode="enforce", allowed_tools={"read_inbox"})
    harness.wrap(make_send([]), on_block="return")("x@outside-mail.example")
    harness.wrap(lambda: "x", name="delete_records", on_block="return")()
    q3 = render_report(harness.finalize()).split("## 3.")[1]
    assert "No state-mutating actions were recorded in this run." in q3
    assert "### Blocked before they ran (nothing changed)" in q3
    assert (
        "- Step 1, `send_email`: blocked before it ran, so nothing changed. "
        "Declared reversibility: irreversible." in q3
    )
    assert "delete_records" not in q3  # not a mutating tool, so not a change


# -- argument rules and helpers -----------------------------------------------------


@pytest.mark.parametrize(
    "value, allowed",
    [
        ("team@tallowlane.example", True),
        ("Team@TallowLane.Example", True),
        (["a@tallowlane.example", "b@tallowlane.example"], True),
        ("a@tallowlane.example, b@tallowlane.example", True),
        ("planner.desk@outside-mail.example", False),
        ("x@evil-tallowlane.example", False),
        ("a@tallowlane.example, b@outside-mail.example", False),
        ("tallowlane.example", False),
        ("@tallowlane.example", False),
        ("", False),
        ([], False),
    ],
)
def test_email_domain_in(value, allowed):
    assert email_domain_in("tallowlane.example")(value) is allowed


def test_value_in():
    check = value_in("draft", "review")
    assert check("draft") and not check("publish")


def test_rule_only_applies_to_its_tool():
    scope = Scope(name="t", allowed_tools={"send_email", "draft_reply"}, arg_rules=[INTERNAL_ONLY])
    assert scope.check("draft_reply", {"to": "x@outside-mail.example"}) == (True, "in scope")
    assert scope.check("draft_reply", None) == (True, "in scope")
    assert scope.check("send_email", {"to": "team@tallowlane.example"}) == (True, "in scope")
    ok, reason = scope.check("send_email", {"to": "x@outside-mail.example"})
    assert not ok and "Email may only go to tallowlane.example addresses" in reason


# -- argument rules fail closed ------------------------------------------------

MISSING = "argument 'to' was not provided, so the rule could not be checked"
UNNAMED = "the call has no named arguments, so the rule on argument 'to' could not be checked"


@pytest.mark.parametrize(
    "args, reason",
    [
        ({"subject": "no recipient given"}, MISSING),
        ({}, MISSING),
        (None, UNNAMED),
        ("x@outside-mail.example", UNNAMED),
        (("team@tallowlane.example",), UNNAMED),
    ],
)
def test_a_rule_that_cannot_be_checked_fails(args, reason):
    scope = Scope(name="t", allowed_tools={"send_email"}, arg_rules=[INTERNAL_ONLY])
    assert scope.check("send_email", args) == (False, reason)


def internal_only_harness(tmp_path, mode):
    return make_harness(
        tmp_path, mode=mode, allowed_tools={"send_email"}, mutations_allowed=True,
        arg_rules=[INTERNAL_ONLY],
    )


def send_with_optional_to(sent: list):
    def send_email(subject: str, to: str | None = None) -> str:
        sent.append(to)
        return f"sent to {to}"

    return send_email


def test_missing_argument_is_a_violation_in_observe_mode(tmp_path):
    harness = internal_only_harness(tmp_path, "observe")
    sent: list = []
    send = harness.wrap(lambda **kwargs: sent.append(kwargs) or "sent", name="send_email")
    send(subject="hello")
    assert sent == [{"subject": "hello"}]
    [action] = [e for e in read_log(harness.finalize()) if e["type"] == "action"]
    assert (action["in_scope"], action["scope_reason"]) == (False, MISSING)
    assert harness.violations == 1


def test_missing_argument_is_blocked_in_enforce_mode(tmp_path):
    harness = internal_only_harness(tmp_path, "enforce")
    sent: list = []
    send = harness.wrap(lambda **kwargs: sent.append(kwargs) or "sent", name="send_email")
    with pytest.raises(ToolCallBlocked) as blocked:
        send(subject="hello")
    assert sent == [] and blocked.value.reason == MISSING
    assert MISSING in render_report(harness.finalize())


@pytest.mark.parametrize("mode", ["observe", "enforce"])
def test_a_default_value_is_checked_like_any_other(tmp_path, mode):
    harness = internal_only_harness(tmp_path, mode)
    sent: list = []
    send = harness.wrap(send_with_optional_to(sent), on_block="return")
    result = send("hello")  # to defaults to None, which is not an address
    entries = read_log(harness.finalize())
    [action] = [e for e in entries if e["type"] == "action"]
    assert action["in_scope"] is False
    assert "breaks a rule" in action["scope_reason"]
    assert "'to': None" in action["args_summary"]
    if mode == "enforce":
        assert sent == [] and result.startswith("blocked: argument 'to' breaks a rule")
    else:
        assert sent == [None]


def test_an_allowed_default_passes(tmp_path):
    harness = internal_only_harness(tmp_path, "enforce")

    def send_email(subject: str, to: str = "team@tallowlane.example") -> str:
        return f"sent to {to}"

    assert harness.wrap(send_email)("hello") == "sent to team@tallowlane.example"
    assert harness.violations == 0


def test_a_check_that_raises_fails_the_rule():
    rule = ArgRule(tool="t", arg="n", check=lambda v: 1 / v > 0, description="must be positive")
    assert rule.allows(2) and not rule.allows(0)


def test_rules_are_written_to_the_log_and_listed_in_question_1(tmp_path):
    harness = make_harness(tmp_path, allowed_tools={"send_email"}, arg_rules=[INTERNAL_ONLY])
    log_path = harness.finalize()
    [scope_entry] = [e for e in read_log(log_path) if e["type"] == "scope"]
    assert scope_entry["scope"]["arg_rules"] == [
        {
            "tool": "send_email",
            "arg": "to",
            "check": "email_domain_in('tallowlane.example')",
            "description": "Email may only go to tallowlane.example addresses",
        }
    ]
    q1 = render_report(log_path).split("## 2.")[0]
    assert (
        "  - `send_email`, argument `to`: Email may only go to tallowlane.example addresses."
        in q1
    )


def test_question_1_with_no_rules(tmp_path):
    assert "- **Argument rules:** none" in render_report(make_harness(tmp_path).finalize())
