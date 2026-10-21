"""Human-readable audit report, organized around the three questions."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .audit import verify
from .governance import findings, fingerprint
from .scope import COMPENSABLE, IRREVERSIBLE, REVERSIBLE

# Question 3 groups, in the order they are reported: worst first.
GROUPS = [
    (IRREVERSIBLE, "Cannot be undone (irreversible)"),
    (COMPENSABLE, "Cannot be undone, but can be offset (compensable)"),
    (REVERSIBLE, "Can be undone (reversible)"),
    (None, "No reversibility declared"),
]

MODES = {
    "observe": "records and flags out-of-scope calls; does not block them",
    "enforce": "blocks out-of-scope calls before they run",
}


def _load_entries(log_path: str | Path) -> list[dict[str, Any]]:
    entries = []
    with Path(log_path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def _kind(declaration: dict[str, Any] | None) -> str | None:
    return declaration["kind"] if declaration else None


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _clause(text: str) -> str:
    """A declared sentence, continued after a label: "Undo: delete the draft."
    The first letter is lowercased unless the word looks like an acronym."""
    text = _sentence(text)
    if len(text) > 1 and not text[1].isupper():
        text = text[0].lower() + text[1:]
    return text


def _describe(declaration: dict[str, Any] | None) -> str:
    """One or two plain sentences on how a change can be undone."""
    if not declaration:
        return "no reversibility declared. Nobody wrote down how to undo this change before the run."
    how = _clause(declaration["how"])
    text = {
        IRREVERSIBLE: f"cannot be undone. Nothing restores the prior state. What can still be done: {how}",
        COMPENSABLE: f"cannot be undone, but can be offset. Offset: {how}",
        REVERSIBLE: f"can be undone. Undo: {how}",
    }[declaration["kind"]]
    if declaration.get("window"):
        text += f" Window: {_clause(declaration['window'])}"
    return text


def _field(label: str, text: Any, indent: str = "") -> list[str]:
    """A list item. Multi-line text goes in an indented fenced block so it
    cannot break the Markdown list."""
    text = str(text)
    if "\n" not in text:
        return [f"{indent}- {label}: {text}"]
    fence = "```"
    while fence in text:
        fence += "`"
    pad = indent + "  "
    body = [pad + line if line else "" for line in text.splitlines()]
    return [f"{indent}- {label}:", "", f"{pad}{fence}text", *body, f"{pad}{fence}", ""]


def chain_status(log_path: str | Path) -> str:
    """One plain sentence on whether the log's hash chain verified."""
    state, number = verify(log_path)
    if state == "intact":
        return (
            f"hash chain intact across {number} entries: no edit detected since the log was "
            "written. This cannot detect a rewrite of the whole file, or lines cut from the "
            "end, unless the final hash is kept somewhere else."
        )
    if state == "broken":
        return f"hash chain BROKEN: the log was changed after it was written; the first break is at line {number}."
    return "not chained: this log was written by an older version without a hash chain."


OWNER_KINDS = [
    (IRREVERSIBLE, "that cannot be undone"),
    (COMPENSABLE, "that cannot be undone but can be offset"),
    (REVERSIBLE, "that can be undone"),
    (None, "with no undo plan"),
]


def _owner_summary(log_path, scope, gov, mutations, violations, blocked, gaps) -> list[str]:
    """The top of the report, for the accountable owner: one screen, no internals."""
    approved = "not approved by anyone on record"
    if gov.get("approver"):
        approved = f"approved by {gov['approver']}" + (f" on {gov['approved_on']}" if gov.get("approved_on") else "")
    review = gov.get("review_by")
    overdue = any(gap.startswith("The scope was due for review") for gap in gaps)
    changes = []
    for kind, label in OWNER_KINDS:
        tools = Counter(m["tool"] for m in mutations if _kind(m.get("reversibility")) == kind)
        if tools:
            names = ", ".join(f"`{t}`" + (f" x{n}" if n > 1 else "") for t, n in tools.items())
            changes.append(f"{sum(tools.values())} {label} ({names})")
    undeclared = sum(_kind(m.get("reversibility")) is None for m in mutations)
    attention = []
    if blocked:
        attention.append(f"{len(blocked)} action(s) blocked before they ran")
    if len(violations) > len(blocked):
        attention.append(f"{len(violations) - len(blocked)} action(s) outside the scope that were flagged")
    if undeclared:
        attention.append(f"{undeclared} change(s) with no undo plan")
    if gaps:
        attention.append(f"{len(gaps)} governance finding(s), listed under question 1")
    version = f" version {gov['version']}" if gov.get("version") else ""
    return [
        "## Summary for the owner",
        "",
        f"- **Scope:** `{scope.get('name', '?')}`{version}, owned by {gov.get('owner') or 'nobody on record'}, {approved}.",
        "- **Review:** "
        + ("no review date set." if not review else f"was due by {review}; it is overdue." if overdue else f"due by {review}."),
        "- **Changes made in this run:** " + ("; ".join(changes) + "." if changes else "none."),
        "- **Needs your attention:** " + ("; ".join(attention) + "." if attention else "nothing."),
        f"- **Audit log:** {chain_status(log_path)}",
        f"- **To re-create this report from the log:** `accountability-harness report {Path(log_path).name}`",
        "",
    ]


def render_report(log_path: str | Path, run_date: str | None = None) -> str:
    """Render the audit log at log_path as a Markdown report. run_date (YYYY-MM-DD)
    is the "today" for the governance findings; by default, the day the run was logged."""
    entries = _load_entries(log_path)
    meta = next((e for e in entries if e["type"] == "run_meta"), {})
    scope_entry = next((e for e in entries if e["type"] == "scope"), {})
    scope = scope_entry.get("scope", {})
    gov = scope.get("governance") or {}
    rationale = scope.get("rationale") or {}
    gaps = findings(scope, run_date or str(meta.get("logged_at", ""))[:10])
    actions = [e for e in entries if e["type"] == "action"]
    mutations = [e for e in entries if e["type"] == "mutation"]
    end = next((e for e in entries if e["type"] == "run_end"), {})
    violations = [a for a in actions if not a.get("in_scope")]
    blocked = [a for a in actions if a.get("status") == "blocked"]
    incomplete = [a for a in actions if a.get("status") == "incomplete"]
    mode = meta.get("mode", "observe")
    rules = scope.get("arg_rules", [])
    declared = scope.get("reversibility") or {t: None for t in scope.get("mutating_tools", [])}
    order = [kind for kind, _ in GROUPS]

    lines = [
        "# Agent Accountability Report",
        "",
        f"Agent: `{meta.get('agent_name', '?')}`",
        f"Run: `{meta.get('run_id', '?')}`",
        f"Logged: {meta.get('logged_at', '?')}",
        f"Mode: {mode} ({MODES.get(mode, '')})",
        "",
        "## 1. What was the agent allowed to touch?",
        "",
    ]
    if scope.get("description"):
        lines += [scope["description"], ""]
    lines += [
        f"- **Scope:** `{scope.get('name', '?')}`"
        + (f", version {gov['version']}" if gov.get("version") else ""),
        f"- **Owner:** {gov.get('owner') or 'not recorded'}. **Approved by:** "
        f"{gov.get('approver') or 'not recorded'}"
        + (f", on {gov['approved_on']}" if gov.get("approved_on") else "")
        + f". **Review by:** {gov.get('review_by') or 'not set'}.",
        *([f"- **Change note:** {gov['change_note']}"] if gov.get("change_note") else []),
        f"- **Scope fingerprint (SHA-256):** `{scope_entry.get('fingerprint') or fingerprint(scope)}`",
        f"- **Allowed tools:** {', '.join(f'`{t}`' for t in scope.get('allowed_tools', [])) or 'none'}",
        *[f"  - `{t}`: {rationale[t]}" for t in scope.get("allowed_tools", []) if rationale.get(t)],
        f"- **Allowed data sources:** {', '.join(f'`{d}`' for d in scope.get('allowed_data_sources', [])) or 'none'}",
        f"- **Mutations allowed:** {'yes' if scope.get('mutations_allowed') else 'no'}",
        f"- **Tools that change something, and how each change can be undone:**"
        + ("" if declared else " none"),
    ]
    for tool, decl in sorted(declared.items(), key=lambda item: (order.index(_kind(item[1])), item[0])):
        label = f" ({decl['kind']})" if decl else ""
        lines.append(f"  - `{tool}`{label}: {_describe(decl)}")
    lines.append("- **Argument rules:**" + ("" if rules else " none"))
    lines += [f"  - `{r['tool']}`, argument `{r['arg']}`: {_sentence(r['description'])}" for r in rules]
    if gaps:
        lines += ["", "### Governance findings", "", *[f"- {gap}" for gap in gaps]]
    lines += [
        "",
        "## 2. What did it do while nobody was watching?",
        "",
        f"{len(actions)} tool call(s) recorded.",
        "",
    ]
    if violations:
        lines += [f"### Violations: {len(violations)} ({len(blocked)} blocked)", ""]
        for v in violations:
            note = " (blocked; the tool did not run)" if v in blocked else ""
            lines.append(f"- **Step {v['seq']}:** `{v['tool']}`{note}: {v.get('scope_reason', '')}")
        lines += [""]
    for a in actions:
        mark = "BLOCKED" if a in blocked else "OK" if a.get("in_scope") else "VIOLATION"
        lines += [f"### Step {a['seq']}: `{a['tool']}` [{mark}]", ""]
        if a.get("status", "ok") not in ("ok", "blocked"):
            lines.append(f"- Status: {a['status']}")
        lines += _field("Args", a.get("args_summary", ""))
        lines += _field("Result", a.get("output_summary", ""))
        lines += [f"- Duration: {a.get('duration_ms', '?')} ms", ""]

    counts = {kind: 0 for kind in order}
    for m in mutations:
        counts[_kind(m.get("reversibility"))] += 1
    lines += [
        "## 3. How can its actions be undone?",
        "",
    ]
    blocked_changes = [a for a in blocked if a["tool"] in declared]
    if not mutations:
        lines += ["No state-mutating actions were recorded in this run.", ""]
    else:
        lines += [
            f"{len(mutations)} change(s) recorded: {counts[IRREVERSIBLE]} irreversible, "
            f"{counts[COMPENSABLE]} compensable, {counts[REVERSIBLE]} reversible, "
            f"{counts[None]} with no reversibility declared.",
            "",
        ]
        for kind, heading in GROUPS:
            group = [m for m in mutations if _kind(m.get("reversibility")) == kind]
            if not group:
                continue
            lines += [f"### {heading}", ""]
            for m in group:
                allowed = "" if m.get("allowed") else " (NOT permitted by scope)"
                text = _describe(m.get("reversibility"))
                if m.get("outcome") == "unknown":
                    text += " Outcome unknown: the call did not complete normally, so check whether anything changed."
                lines.append(f"- Step {m.get('action_seq')}, `{m.get('tool')}`{allowed}: {text}")
                lines += _field("What changed", m.get("what_changed", ""), indent="  ")
            lines += [""]
    if blocked_changes:
        lines += ["### Blocked before they ran (nothing changed)", ""]
        for a in blocked_changes:
            decl = declared[a["tool"]]
            kind = f"Declared reversibility: {decl['kind']}." if decl else "No reversibility declared."
            lines.append(
                f"- Step {a['seq']}, `{a['tool']}`: blocked before it ran, so nothing changed. {kind}"
            )
        lines += [""]
    lines += [
        "---",
        f"Summary ({mode} mode): {len(actions)} actions "
        f"({len(incomplete)} incomplete, {len(blocked)} blocked), "
        f"{len(violations)} violation(s), "
        f"{len(mutations)} mutation(s): {counts[IRREVERSIBLE]} irreversible, "
        f"{counts[COMPENSABLE]} compensable, {counts[REVERSIBLE]} reversible, "
        f"{counts[None]} undeclared.",
    ]
    at = lines.index("## 1. What was the agent allowed to touch?")
    lines[at:at] = _owner_summary(log_path, scope, gov, mutations, violations, blocked, gaps)
    recorded = tuple(end.get(k, 0) for k in ("violations", "mutations", "incomplete", "blocked"))
    if end and recorded != (len(violations), len(mutations), len(incomplete), len(blocked)):
        lines.append(
            f"Warning: the run summary recorded {recorded[0]} violation(s), "
            f"{recorded[1]} mutation(s), {recorded[2]} incomplete and {recorded[3]} blocked "
            "call(s), which does not match the log."
        )
    return "\n".join(lines)
