"""The scope as a governed artifact: load it from a TOML file, fingerprint
it, and list the gaps in who stands behind it.

A scope file holds the same content as a Python-built Scope, plus the
governance fields. Argument rules in a file can use only the built-in
helpers by name ("email_domain_in", "value_in"); custom checks stay in
Python. See demo/scopes/ for complete examples.

The findings are reported, never enforced: a run under a scope with no
approver still proceeds.
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any

from .scope import ArgRule, Reversibility, Scope, email_domain_in, value_in

HELPERS = {"email_domain_in": email_domain_in, "value_in": value_in}


def canonical(data: Any) -> str:
    """The one JSON text used for hashing: sorted keys, no spaces."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def fingerprint(scope_dict: dict[str, Any]) -> str:
    """SHA-256 of the scope's canonical content, as written to the log."""
    return hashlib.sha256(canonical(scope_dict).encode("utf-8")).hexdigest()


def load_scope(path: str | Path) -> Scope:
    """Build a Scope from a TOML scope file."""
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    mutating = {
        name: Reversibility(**decl) if decl else None
        for name, decl in data.pop("mutating_tools", {}).items()
    }
    rules = []
    for rule in data.pop("arg_rules", []):
        if rule["check"] not in HELPERS:
            names = ", ".join(HELPERS)
            raise ValueError(f"unknown check {rule['check']!r}; a scope file can use {names}. Write custom checks in Python.")
        check = HELPERS[rule["check"]](*rule.get("values", []))
        rules.append(ArgRule(rule["tool"], rule["arg"], check, rule["description"]))
    for key in ("approved_on", "review_by"):
        if key in data:
            data[key] = str(data[key])  # TOML dates arrive as date objects
    return Scope(
        **{k: v for k, v in data.items() if k not in ("allowed_tools", "allowed_data_sources")},
        allowed_tools=set(data.get("allowed_tools", [])),
        allowed_data_sources=set(data.get("allowed_data_sources", [])),
        mutating_tools=mutating,
        arg_rules=rules,
    )


def findings(scope_dict: dict[str, Any], run_date: str) -> list[str]:
    """Plain-language gaps in the scope's governance, as of run_date (YYYY-MM-DD), the injectable "today"."""
    if "governance" not in scope_dict:
        return ["This log was written by an older version that did not record governance fields."]
    gov = scope_dict["governance"]
    found = []
    if not gov.get("approver"):
        found.append("No one is recorded as having approved this scope.")
    if not gov.get("owner"):
        found.append("No one is recorded as the owner of this scope.")
    review_by = gov.get("review_by")
    if review_by and run_date > review_by:
        found.append(f"The scope was due for review by {review_by}; this run was on {run_date}.")
    rationale = scope_dict.get("rationale") or {}
    missing = [t for t in scope_dict.get("allowed_tools", []) if not rationale.get(t)]
    if missing:
        found.append(
            "No reason is recorded for allowing: " + ", ".join(f"`{t}`" for t in missing) + "."
        )
    return found
