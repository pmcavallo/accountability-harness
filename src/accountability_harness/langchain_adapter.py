"""LangChain adapter: a callback handler that delegates to the Harness.

Requires langchain-core:  pip install accountability-harness[langchain]

Register an AccountabilityHandler in a tool's callbacks (or an agent's)
and every tool call is passed to the core Harness, which checks it
against the declared Scope and records it. Nothing LangChain-specific
is written to the log, so the report is the same as for plain functions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .core import ENFORCE, MAX_TEXT, OBSERVE, Harness
from .scope import Scope


class AccountabilityHandler(BaseCallbackHandler):
    """Records LangChain tool calls against a declared Scope.

    Usage:
        handler = AccountabilityHandler(scope, agent_name="inbox-assistant")
        tool.invoke(args, config={"callbacks": [handler]})
        log_path = handler.finalize()
        print(render_report(log_path))

    Pass harness= to share one Harness with other integrations; otherwise
    the handler creates its own from scope, log_dir, agent_name and mode.

    In enforce mode an out-of-scope call raises ToolCallBlocked from the
    tool's invoke() before the tool body runs (tested for sync and async
    invoke on the installed langchain-core).
    """

    def __init__(
        self,
        scope: Scope | None = None,
        log_dir: str | Path = "audit_logs",
        agent_name: str = "agent",
        max_text: int = MAX_TEXT,
        harness: Harness | None = None,
        mode: str = OBSERVE,
    ) -> None:
        super().__init__()
        if harness is None:
            if scope is None:
                raise ValueError("AccountabilityHandler needs a scope or a harness.")
            harness = Harness(
                scope, log_dir=log_dir, agent_name=agent_name, max_text=max_text, mode=mode
            )
        self.harness = harness
        # In enforce mode, on_tool_start raises ToolCallBlocked for an
        # out-of-scope call. raise_error tells LangChain to let that
        # exception through instead of logging it, so the tool never runs.
        self.raise_error = harness.mode == ENFORCE

    @property
    def scope(self) -> Scope:
        return self.harness.scope

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = (serialized or {}).get("name") or kwargs.get("name") or "unknown"
        args = inputs if inputs is not None else input_str
        self.harness.start_call(tool_name, args, call_id=str(run_id))

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self.harness.end_call(str(run_id), output)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        self.harness.fail_call(str(run_id), error)

    def finalize(self) -> Path:
        """Close the run, write the summary, return the log path."""
        return self.harness.finalize()
