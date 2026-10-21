"""Agent Accountability Harness.

A small audit layer for AI agents. Declare what an agent is allowed to
touch, record what it does, and report it in plain language organized
around three questions:

1. What was the agent allowed to touch?
2. What did it do while nobody was watching?
3. How can its actions be undone?

The core (Harness) works with any Python tool function. The LangChain
adapter (AccountabilityHandler) is optional and needs langchain-core.
It observes by default (records and flags) and can enforce (blocks
out-of-scope calls before they run).
"""

from typing import Any

from .audit import AuditLog, verify
from .core import Harness, ToolCallBlocked
from .governance import fingerprint, load_scope
from .report import render_report
from .scope import ArgRule, Reversibility, Scope, email_domain_in, value_in

__all__ = [
    "Scope",
    "Reversibility",
    "ArgRule",
    "email_domain_in",
    "value_in",
    "Harness",
    "ToolCallBlocked",
    "AccountabilityHandler",
    "AuditLog",
    "render_report",
    "load_scope",
    "fingerprint",
    "verify",
]
__version__ = "0.8.0"


def __getattr__(name: str) -> Any:
    # Imported lazily so the core never needs LangChain.
    if name == "AccountabilityHandler":
        try:
            from .langchain_adapter import AccountabilityHandler
        except ImportError as exc:
            raise ImportError(
                "AccountabilityHandler needs langchain-core. Install it with: "
                "pip install accountability-harness[langchain]"
            ) from exc
        return AccountabilityHandler
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
