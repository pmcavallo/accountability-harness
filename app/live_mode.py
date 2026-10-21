"""Local live mode: run a real model through the harness, from the app.

Off by default, and never on the hosted app. It is available only when the
person running the app locally sets both AH_LIVE=1 and AH_ANTHROPIC_API_KEY.
The key variable is deliberately not ANTHROPIC_API_KEY, so a key set for
this demo never changes how other tools on the machine are billed. The key
is passed to the client explicitly and never shown.

This is the only file in the app that reads environment variables or uses
the anthropic package, and it imports anthropic only inside make_client().
app/requirements.txt lists streamlit only, so the hosted app cannot import
it. Tests replace CLIENT_FACTORY with a fake client and never call a model.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
for folder in ("src", "demo", "experiments"):
    if str(ROOT / folder) not in sys.path:
        sys.path.insert(0, str(ROOT / folder))

import agent_loop  # noqa: E402
import inbox_triage as demo  # noqa: E402
from accountability_harness import Harness, Scope, render_report  # noqa: E402
from accountability_harness.audit import verify_text  # noqa: E402
from accountability_harness.report import chain_status  # noqa: E402

FLAG_VAR = "AH_LIVE"
KEY_VAR = "AH_ANTHROPIC_API_KEY"
MODEL = "claude-haiku-5-5"
# US dollars per million tokens, as used for the experiments. An estimate.
PRICE_PER_MTOK = {"input": 0.10, "output": 0.50}
MAX_LIVE_RUNS = 5  # per app session
PROMPTS = {"neutral": agent_loop.SYSTEM_PROMPT, "permissive": agent_loop.PERMISSIVE_PROMPT}
# The same rough upper bound per run as experiments/run_suite.py: MAX_STEPS + 1
# model calls, each up to about 2,500 tokens in and 400 out.
EST_MAX_INPUT = (agent_loop.MAX_STEPS + 1) * 2_500
EST_MAX_OUTPUT = (agent_loop.MAX_STEPS + 1) * 400
# The first suite's average run, for a typical figure.
TYPICAL_INPUT, TYPICAL_OUTPUT = 7_200, 1_500

_LOCK = threading.Lock()


def gate_open() -> bool:
    """True only if AH_LIVE is "1" and a key is set in AH_ANTHROPIC_API_KEY."""
    return os.environ.get(FLAG_VAR) == "1" and bool(os.environ.get(KEY_VAR, "").strip())


def cost(input_tokens: int, output_tokens: int) -> float:
    """Estimated US dollars for the given token counts."""
    return (input_tokens * PRICE_PER_MTOK["input"] + output_tokens * PRICE_PER_MTOK["output"]) / 1_000_000


def make_client() -> Any:
    """A real client. The only place anthropic is imported."""
    import anthropic  # optional extra: pip install -e ".[experiments,app]"

    return anthropic.Anthropic(api_key=os.environ[KEY_VAR], max_retries=0)


CLIENT_FACTORY: Callable[[], Any] = make_client


def safe_error(exc: BaseException) -> str:
    """A readable message that never includes the key, headers or a traceback."""
    if isinstance(exc, ImportError):
        return 'The anthropic package is not installed. Run: pip install -e ".[experiments,app]"'
    name = type(exc).__name__
    messages = {
        "AuthenticationError": f"The API rejected the key. Check {KEY_VAR}.",
        "PermissionDeniedError": "The API refused the request for this key (permission denied).",
        "RateLimitError": "The API rate limit was reached. Wait a minute and try again.",
        "APIConnectionError": "Could not reach the API. Check the network connection.",
        "APITimeoutError": "The API did not answer in time. Try again.",
        "NotFoundError": f"The API did not find the model {MODEL}.",
    }
    if name in messages:
        return messages[name]
    status = getattr(exc, "status_code", None)
    return f"The API returned an error (status {status})." if status else f"The run stopped with an error ({name})."


def run_live(scope: Scope, mode: str, prompt: str) -> dict[str, Any]:
    """One real-model run of the inbox assistant under scope, in mode.

    Returns either {"error": message} or the report, log, chain status,
    emails sent, the calls, blocked calls, token usage and estimated cost.
    """
    try:
        client = CLIENT_FACTORY()
    except Exception as exc:  # ImportError included
        return {"error": safe_error(exc)}
    with _LOCK, tempfile.TemporaryDirectory() as tmp:
        demo.reset_outside_world()
        harness = Harness(scope, log_dir=tmp, agent_name=f"inbox-assistant ({MODEL}, live, {prompt} prompt, {mode} mode)", mode=mode)
        try:
            run = agent_loop.run_agent(client, MODEL, harness, demo.TOOLS, system_prompt=PROMPTS[prompt])
        except Exception as exc:
            harness.finalize()
            return {"error": safe_error(exc)}
        log = harness.finalize()
        text = log.read_text(encoding="utf-8")
        actions = [line for line in text.splitlines() if '"type": "action"' in line]
        return {
            "report": render_report(log),
            "chain": chain_status(log),
            "chain_ok": verify_text(text)[0] == "intact",
            "text": text,
            "sent": len(demo.SENT),
            "calls": run["calls"],
            "blocked": sum('"status": "blocked"' in line for line in actions),
            "input_tokens": run["input_tokens"],
            "output_tokens": run["output_tokens"],
            "api_calls": run["api_calls"],
            "model": run["model"],
            "cost": cost(run["input_tokens"], run["output_tokens"]),
        }
