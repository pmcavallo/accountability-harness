"""The experiments' agent loop, driven by a scripted fake client. Offline:
no test here imports the anthropic package or calls a model."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "demo"))
sys.path.insert(0, str(ROOT / "experiments"))

import agent_loop  # noqa: E402
import inbox_triage  # noqa: E402
from accountability_harness import Harness  # noqa: E402

OUTSIDE = {"to": "planner.desk@outside-mail.example", "subject": "Client list", "body": "Here."}


def tool_use(name, args, n=[0]):
    n[0] += 1
    return SimpleNamespace(type="tool_use", id=f"call_{n[0]}", name=name, input=args)


def reply(*blocks, stop="tool_use"):
    return SimpleNamespace(
        content=list(blocks),
        stop_reason=stop,
        model="fake-model-1",
        usage=SimpleNamespace(input_tokens=100, output_tokens=10),
    )


class FakeClient:
    """Returns scripted replies and keeps every request it was sent."""

    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return next(self.replies)


def tool_results(request):
    return [block["content"] for block in request["messages"][-1]["content"]]


def run(tmp_path, replies, mode="enforce", **kwargs):
    inbox_triage.reset_outside_world()
    harness = Harness(inbox_triage.INTERNAL_EMAIL_SCOPE, log_dir=tmp_path, mode=mode)
    client = FakeClient(replies)
    result = agent_loop.run_agent(client, "fake-model", harness, inbox_triage.TOOLS, **kwargs)
    return client, result, harness.finalize()


def test_tool_spec_from_a_plain_function():
    spec = agent_loop.tool_spec(inbox_triage.read_email)
    assert spec["name"] == "read_email"
    assert spec["description"] == "Read the full body of one email by id."
    assert spec["input_schema"]["properties"] == {"email_id": {"type": "integer"}}
    assert spec["input_schema"]["required"] == ["email_id"]


def test_a_blocked_call_comes_back_to_the_model_as_text(tmp_path):
    client, result, log_path = run(
        tmp_path,
        [
            reply(tool_use("read_email", {"email_id": 3})),
            reply(tool_use("send_email", OUTSIDE)),
            reply(SimpleNamespace(type="text", text="Done."), stop="end_turn"),
        ],
    )
    assert "Quick request" in tool_results(client.requests[1])[0]
    [refusal] = tool_results(client.requests[2])
    assert refusal.startswith("blocked: argument 'to' breaks a rule")
    assert inbox_triage.SENT == []
    assert (result["steps"], result["stopped"], result["api_calls"]) == (2, "end_turn", 3)
    assert (result["input_tokens"], result["output_tokens"]) == (300, 30)
    assert result["model"] == "fake-model-1"
    statuses = [json.loads(line).get("status") for line in log_path.read_text().splitlines()]
    assert [s for s in statuses if s] == ["ok", "blocked"]


def test_observe_mode_lets_the_outside_send_run(tmp_path):
    _, result, _ = run(
        tmp_path,
        [reply(tool_use("send_email", OUTSIDE)), reply(stop="end_turn")],
        mode="observe",
    )
    assert [m["to"] for m in inbox_triage.SENT] == [OUTSIDE["to"]]
    assert result["calls"] == [{"tool": "send_email", "args": OUTSIDE}]


def test_the_step_cap_stops_the_run(tmp_path):
    endless = [reply(tool_use("read_inbox", {}), tool_use("read_inbox", {})) for _ in range(20)]
    client, result, _ = run(tmp_path, endless, max_steps=5)
    assert result["steps"] == 5 and result["stopped"] == "step limit"
    assert len(result["skipped"]) == 1  # the sixth request did not run
    assert len(client.requests) == 3


def test_default_limits(tmp_path):
    assert (agent_loop.MAX_STEPS, agent_loop.MAX_TOKENS) == (15, 2048)
    client, result, _ = run(tmp_path, [reply(tool_use("read_inbox", {})) for _ in range(20)])
    assert result["steps"] == 15
    assert result["summary"] == ""  # stopped at the cap, so no closing text
    assert all(r["max_tokens"] == 2048 for r in client.requests)


def test_stop_reasons_summary_and_prompt_are_recorded(tmp_path):
    text = SimpleNamespace(type="text", text="I read email 3 and did not act on it.")
    client, result, _ = run(
        tmp_path,
        [
            reply(tool_use("read_email", {"email_id": 3}), stop="max_tokens"),
            reply(text, stop="end_turn"),
        ],
        system_prompt=agent_loop.PERMISSIVE_PROMPT,
    )
    assert result["stop_reasons"] == ["max_tokens", "end_turn"]
    assert result["summary"] == "I read email 3 and did not act on it."
    assert all(r["system"] == agent_loop.PERMISSIVE_PROMPT for r in client.requests)


def test_neutral_prompt_is_the_default_and_unchanged(tmp_path):
    client, _, _ = run(tmp_path, [reply(stop="end_turn")])
    assert client.requests[0]["system"] == agent_loop.SYSTEM_PROMPT
    assert "Draft replies for a person to review" in agent_loop.SYSTEM_PROMPT
    assert "security" not in agent_loop.PERMISSIVE_PROMPT.lower()
    assert "without asking for confirmation" in agent_loop.PERMISSIVE_PROMPT


def test_bad_arguments_and_unknown_tools_become_error_text(tmp_path):
    client, result, _ = run(
        tmp_path,
        [
            reply(tool_use("read_email", {"id": 3}), tool_use("delete_inbox", {})),
            reply(stop="end_turn"),
        ],
    )
    bad_args, unknown = tool_results(client.requests[1])
    assert bad_args.startswith("error:")
    assert unknown == "error: there is no tool named 'delete_inbox'"


def test_the_loop_does_not_need_the_anthropic_package():
    assert "anthropic" not in sys.modules
    assert "import anthropic" not in (ROOT / "experiments" / "agent_loop.py").read_text()


@pytest.fixture(autouse=True)
def restore_inbox():
    yield
    inbox_triage.reset_outside_world()
