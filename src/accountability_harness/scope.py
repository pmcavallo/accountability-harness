"""Scope declaration: what an agent is allowed to touch.

The Scope is written by the developer *before* the run. The harness
compares every tool call against it and flags anything outside it.
Writing the scope down is itself a governance act: it forces the
question "what should this agent be allowed to do?" before deployment.

For each tool that changes something, the Scope can also declare how
that change can be undone (a Reversibility). A change with no
declaration is reported as "no reversibility declared".

Argument rules (ArgRule) extend the scope past tool names: an allowed
tool can still be out of scope when one of its arguments breaks a rule.

The governance fields (owner, approver, approved_on, version, review_by,
change_note and a rationale per tool) record who stands behind the scope.
They are plain text; the harness reports gaps in them but never enforces them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

REVERSIBLE = "reversible"
COMPENSABLE = "compensable"
IRREVERSIBLE = "irreversible"
KINDS = (IRREVERSIBLE, COMPENSABLE, REVERSIBLE)
GOVERNANCE_FIELDS = ("owner", "approver", "approved_on", "version", "review_by", "change_note")


@dataclass(frozen=True)
class Reversibility:
    """How one tool's change can be undone, declared before the run.

    Attributes:
        kind: "reversible" (can be undone directly, e.g. delete a draft),
            "compensable" (cannot be undone, but a separate action can
            offset it, e.g. issue a refund), or "irreversible" (nothing
            restores the prior state).
        how: One plain sentence on how to undo or offset the change, or
            for an irreversible change, what can still be done.
        window: How long undo stays possible, in plain text, or None.
    """

    kind: str
    how: str
    window: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}; got {self.kind!r}")
        if not self.how.strip():
            raise ValueError("how must say how to undo or offset the change")

    @classmethod
    def reversible(cls, how: str, window: str | None = None) -> Reversibility:
        return cls(REVERSIBLE, how, window)

    @classmethod
    def compensable(cls, how: str, window: str | None = None) -> Reversibility:
        return cls(COMPENSABLE, how, window)

    @classmethod
    def irreversible(cls, how: str) -> Reversibility:
        return cls(IRREVERSIBLE, how)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "how": self.how, "window": self.window}


@dataclass(frozen=True)
class ArgRule:
    """A declared rule on one argument of one tool.

    Attributes:
        tool: The tool the rule applies to.
        arg: The argument name the rule checks.
        check: Returns True if the value is allowed. A check that raises
            counts as a failed rule.
        description: The rule in plain language, for the report.

    A call to the tool that leaves out the argument fails the rule, since
    the rule could not be checked. Through Harness.wrap, the function's
    default values are filled in first, so a default is checked too.
    """

    tool: str
    arg: str
    check: Callable[[Any], bool]
    description: str

    def allows(self, value: Any) -> bool:
        try:
            return bool(self.check(value))
        except Exception:
            return False

    def to_dict(self) -> dict[str, Any]:
        check = getattr(self.check, "spec", "custom Python check")
        return {"tool": self.tool, "arg": self.arg, "check": check, "description": self.description}


def email_domain_in(*domains: str) -> Callable[[Any], bool]:
    """Check that every address in a value is at one of the given domains.

    Accepts one address, a comma-separated string, or a list of addresses,
    so "a@ours.example, b@theirs.example" fails if theirs is not listed.
    """
    allowed = {d.lower().lstrip("@") for d in domains}

    def check(value: Any) -> bool:
        addresses = value.split(",") if isinstance(value, str) else list(value)
        parts = [str(a).strip().rpartition("@") for a in addresses]
        return bool(parts) and all(
            local and at and domain.lower() in allowed for local, at, domain in parts
        )

    check.spec = f"email_domain_in({', '.join(map(repr, domains))})"  # type: ignore[attr-defined]
    return check


def value_in(*allowed: Any) -> Callable[[Any], bool]:
    """Check that the value is one of the allowed values."""

    def check(value: Any) -> bool:
        return value in allowed

    check.spec = f"value_in({', '.join(map(repr, allowed))})"  # type: ignore[attr-defined]
    return check


@dataclass
class Scope:
    """Declared permissions for one agent run.

    Attributes:
        name: Human label for this scope (e.g. "inbox-triage-readonly").
        allowed_tools: Tool names the agent may call. Anything else is
            flagged as out of scope.
        allowed_data_sources: Data the agent may read (e.g. "inbox",
            "calendar"). Informational for now; recorded in the report.
        mutating_tools: Tools that change external state (send, write,
            delete). Either a set of names, or a mapping of name to
            Reversibility (or None) declaring how each change can be
            undone. Names without a Reversibility are "undeclared".
            Calling one is always recorded as a mutation.
        mutations_allowed: Whether mutations are permitted at all in
            this run. A mutating tool call in a run where mutations are
            not allowed is flagged as a violation.
        description: Plain-language summary for the report.
        arg_rules: Rules on tool arguments. A call that breaks one is
            out of scope, with the rule's description as the reason.
        owner, approver, approved_on, version, review_by, change_note:
            Governance fields, plain text. Dates are "YYYY-MM-DD".
        rationale: One line per allowed tool on why the agent needs it.
    """

    name: str
    allowed_tools: set[str] = field(default_factory=set)
    allowed_data_sources: set[str] = field(default_factory=set)
    mutating_tools: Mapping[str, Reversibility | None] | Iterable[str] = field(
        default_factory=dict
    )
    mutations_allowed: bool = False
    description: str = ""
    arg_rules: list[ArgRule] = field(default_factory=list)
    owner: str = ""
    approver: str = ""
    approved_on: str = ""
    version: str = ""
    review_by: str = ""
    change_note: str = ""
    rationale: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if isinstance(self.mutating_tools, Mapping):
            self.mutating_tools = dict(self.mutating_tools)
        else:
            self.mutating_tools = {name: None for name in self.mutating_tools}

    def tool_in_scope(self, tool_name: str) -> bool:
        return tool_name in self.allowed_tools

    def is_mutation(self, tool_name: str) -> bool:
        return tool_name in self.mutating_tools

    def reversibility(self, tool_name: str) -> Reversibility | None:
        """The declared Reversibility for tool_name, or None if undeclared."""
        return self.mutating_tools.get(tool_name)  # type: ignore[union-attr]

    def check(self, tool_name: str, args: Any = None) -> tuple[bool, str]:
        """Return (ok, reason) for a tool call against this scope.

        args is the call's arguments by name. Argument rules fail closed:
        a rule that cannot be checked, because the argument is missing or
        the call has no named arguments, counts as a failed rule.
        """
        if not self.tool_in_scope(tool_name):
            return False, f"tool '{tool_name}' is not in the declared scope"
        if self.is_mutation(tool_name) and not self.mutations_allowed:
            return False, (
                f"tool '{tool_name}' mutates external state, but this run "
                f"does not allow mutations"
            )
        for rule in self.arg_rules:
            if rule.tool != tool_name:
                continue
            if not isinstance(args, dict):
                return False, (
                    f"the call has no named arguments, so the rule on argument "
                    f"'{rule.arg}' could not be checked"
                )
            if rule.arg not in args:
                return False, f"argument '{rule.arg}' was not provided, so the rule could not be checked"
            if not rule.allows(args[rule.arg]):
                return False, f"argument '{rule.arg}' breaks a rule: {rule.description}"
        return True, "in scope"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "allowed_tools": sorted(self.allowed_tools),
            "allowed_data_sources": sorted(self.allowed_data_sources),
            "mutating_tools": sorted(self.mutating_tools),
            "reversibility": {
                name: decl.to_dict() if decl else None
                for name, decl in sorted(self.mutating_tools.items())  # type: ignore[union-attr]
            },
            "mutations_allowed": self.mutations_allowed,
            "arg_rules": [rule.to_dict() for rule in self.arg_rules],
            "governance": {key: getattr(self, key) for key in GOVERNANCE_FIELDS},
            "rationale": dict(sorted(self.rationale.items())),
        }
