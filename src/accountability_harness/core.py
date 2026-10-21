"""Framework-neutral core: the Harness.

The Harness owns the declared Scope, the AuditLog and the run counters.
Any integration (a plain Python decorator, a LangChain callback, or
something you write yourself) records a tool call with three methods:

    call_id = harness.start_call("read_email", {"email_id": 1})
    harness.end_call(call_id, output)      # the tool returned
    harness.fail_call(call_id, error)      # the tool raised

This module does not import LangChain or any other agent framework.
In observe mode (the default) the harness records and flags calls. In
enforce mode it also blocks calls that fail the scope check: they are
recorded as blocked and the tool does not run.
"""

from __future__ import annotations

import functools
import inspect
import time
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from .audit import AuditLog
from .governance import fingerprint
from .scope import Scope

MAX_TEXT = 500

F = TypeVar("F", bound=Callable[..., Any])

OBSERVE = "observe"
ENFORCE = "enforce"


class ToolCallBlocked(Exception):
    """Raised in enforce mode when a tool call fails the scope check.

    The tool did not run. tool and reason say which call and why.
    """

    def __init__(self, tool: str, reason: str) -> None:
        super().__init__(f"blocked: {reason}")
        self.tool = tool
        self.reason = reason


def summarize(text: Any, limit: int = MAX_TEXT) -> str:
    """Return str(text), truncated to limit characters with a marker."""
    s = str(text)
    return s if len(s) <= limit else s[:limit] + f"... [truncated, {len(s)} chars]"


class Harness:
    """Records tool calls against a declared Scope.

    Usage:
        harness = Harness(scope, agent_name="inbox-assistant")

        @harness.tool
        def read_inbox() -> str: ...

        read_inbox()
        log_path = harness.finalize()
        print(render_report(log_path))

    Args:
        scope: What the agent is allowed to touch in this run.
        log_dir: Directory for the JSONL audit log.
        agent_name: Label shown in the report.
        max_text: Arguments and outputs longer than this are truncated
            before they are written to the log.
        mode: "observe" records and flags out-of-scope calls but lets them
            run. "enforce" blocks them before they run.
    """

    def __init__(
        self,
        scope: Scope,
        log_dir: str | Path = "audit_logs",
        agent_name: str = "agent",
        max_text: int = MAX_TEXT,
        mode: str = OBSERVE,
    ) -> None:
        if mode not in (OBSERVE, ENFORCE):
            raise ValueError(f"mode must be '{OBSERVE}' or '{ENFORCE}'; got {mode!r}")
        self.scope = scope
        self.mode = mode
        self.agent_name = agent_name
        self.max_text = max_text
        self.log = AuditLog(log_dir)
        self.log.write_meta(agent_name=agent_name, mode=mode)
        scope_dict = scope.to_dict()
        self.log.write_scope(scope_dict, fingerprint=fingerprint(scope_dict))
        self._started: dict[str, dict[str, Any]] = {}
        self.violations = 0
        self.mutations = 0
        self.incomplete = 0
        self.blocked = 0

    # -- the three integration methods --------------------------------

    def start_call(self, tool_name: str, args: Any = None, call_id: str | None = None) -> str:
        """Record that a tool call is starting. Returns its call id.

        In enforce mode, a call that fails the scope check is recorded as
        blocked and ToolCallBlocked is raised: the caller must not run
        the tool.
        """
        call_id = call_id or str(uuid4())
        ok, reason = self.scope.check(tool_name, args)
        started = {
            "tool": tool_name,
            "args_summary": summarize({} if args is None else args, self.max_text),
            "started_at": time.time(),
            "in_scope": ok,
            "scope_reason": reason,
        }
        if not ok and self.mode == ENFORCE:
            self.blocked += 1
            self._write_action(started, "blocked", "BLOCKED: the tool did not run")
            raise ToolCallBlocked(tool_name, reason)
        self._started[call_id] = started
        return call_id

    def end_call(self, call_id: str, output: Any) -> dict[str, Any] | None:
        """Record that the tool call returned output. Returns the log entry."""
        started = self._started.pop(call_id, None)
        if started is None:
            return None
        entry = self._write_action(started, "ok", summarize(output, self.max_text))
        if self.scope.is_mutation(started["tool"]):
            self._write_mutation(entry, summarize(output, self.max_text), "completed")
        return entry

    def fail_call(self, call_id: str, error: BaseException) -> dict[str, Any] | None:
        """Record that the tool call raised error. Returns the log entry."""
        started = self._started.pop(call_id, None)
        if started is None:
            return None
        entry = self._write_action(started, "error", f"ERROR: {error!r}")
        if self.scope.is_mutation(started["tool"]):
            # A mutating tool can fail partway, so a change cannot be ruled out.
            self._write_mutation(
                entry,
                "unknown: the tool raised an error; check whether anything changed",
                "unknown",
            )
        return entry

    # -- wrapping plain functions -------------------------------------

    def wrap(self, fn: F, name: str | None = None, on_block: str = "raise") -> F:
        """Return fn wrapped so every call is recorded as a tool call.

        The tool name defaults to the function name. Arguments are
        recorded by parameter name, with the function's default values
        filled in, so read_email(1) and read_email(email_id=1) produce the
        same log entry and a default is checked like any other argument.

        In enforce mode a blocked call does not run fn. With
        on_block="raise" (the default) it raises ToolCallBlocked; with
        on_block="return" it returns the text "blocked: <reason>", for an
        agent loop that reads tool results as text.
        """
        if on_block not in ("raise", "return"):
            raise ValueError("on_block must be 'raise' or 'return'")
        tool_name = name or fn.__name__
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def recorded(*args: Any, **kwargs: Any) -> Any:
            try:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                call_args: Any = dict(bound.arguments)
            except TypeError:
                call_args = {"args": args, "kwargs": kwargs}
            try:
                call_id = self.start_call(tool_name, call_args)
            except ToolCallBlocked as blocked:
                if on_block == "return":
                    return str(blocked)
                raise
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                self.fail_call(call_id, exc)
                raise
            self.end_call(call_id, result)
            return result

        return recorded  # type: ignore[return-value]

    def tool(self, fn: F | None = None, *, name: str | None = None, on_block: str = "raise") -> Any:
        """Decorator form of wrap: @harness.tool or @harness.tool(name="x")."""
        if fn is None:
            return lambda f: self.wrap(f, name=name, on_block=on_block)
        return self.wrap(fn, name=name, on_block=on_block)

    # -- lifecycle ----------------------------------------------------

    def finalize(self) -> Path:
        """Close the run, write the summary, return the log path.

        Calls that started but never ended are recorded as incomplete.
        """
        for call_id in list(self._started):
            started = self._started.pop(call_id)
            self.incomplete += 1
            entry = self._write_action(
                started, "incomplete", "INCOMPLETE: no result or error was recorded"
            )
            if self.scope.is_mutation(started["tool"]):
                self._write_mutation(entry, "unknown: the call did not finish", "unknown")
        self.log.write_end(
            {
                "agent_name": self.agent_name,
                "violations": self.violations,
                "mutations": self.mutations,
                "incomplete": self.incomplete,
                "mode": self.mode,
                "blocked": self.blocked,
            }
        )
        return self.log.path

    # -- internals ----------------------------------------------------

    def _write_action(
        self, started: dict[str, Any], status: str, output_summary: str
    ) -> dict[str, Any]:
        if not started["in_scope"]:
            self.violations += 1
        return self.log.write_action(
            {
                "tool": started["tool"],
                "args_summary": started["args_summary"],
                "output_summary": output_summary,
                "status": status,
                "duration_ms": int((time.time() - started["started_at"]) * 1000),
                "in_scope": started["in_scope"],
                "scope_reason": started["scope_reason"],
            }
        )

    def _write_mutation(self, entry: dict[str, Any], what_changed: str, outcome: str) -> None:
        # outcome is "completed", or "unknown" when the call failed or never
        # finished. The reversibility is the declaration from the Scope, or
        # None if nobody declared how to undo this tool's change.
        self.mutations += 1
        declared = self.scope.reversibility(entry["tool"])
        self.log.write_mutation(
            {
                "action_seq": entry["seq"],
                "tool": entry["tool"],
                "what_changed": what_changed,
                "outcome": outcome,
                "allowed": self.scope.mutations_allowed and entry["in_scope"],
                "reversibility": declared.to_dict() if declared else None,
            }
        )
