"""Change comparison: did a change (a prompt edit, a new scope version)
change what the agent does?

compare(a_dir, b_dir) reads every audit log in two folders and returns a
Markdown comparison built from counts only: tool names, numbers and scope
fingerprints, never arguments or results. It flags a material behavior
change when one of the documented rules below fires. The rules are a
heuristic: they point a person at a difference worth reviewing; they do
not say whether the change is good or bad, or what caused it.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .governance import fingerprint

USE_RATE_POINTS = 25  # rule 1: share of runs using a mutating tool, in percentage points
VOLUME_RATIO = 0.5  # rule 2: relative change in a mutating tool's calls per run...
VOLUME_MIN = 0.5  # ...and at least this many calls per run
KINDS = ["irreversible", "compensable", "reversible", "undeclared"]
RULES = [
    f"A tool that changes something is used in a share of runs that differs by "
    f"{USE_RATE_POINTS} percentage points or more.",
    f"A tool that changes something is called per run {VOLUME_RATIO:.0%} more or less "
    f"often, and the difference is at least {VOLUME_MIN} calls per run.",
    "A tool is used in one set and never in the other.",
    "The two sets ran under different scope fingerprints.",
    "Violations, blocked calls or incomplete calls per run rise from zero.",
]


def load_runs(folder: str | Path) -> list[dict[str, Any]]:
    """One summary per audit log in folder: counts only."""
    runs = []
    for path in sorted(Path(folder).glob("audit-*.jsonl")):
        entries = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        scope_entry = next((e for e in entries if e["type"] == "scope"), {})
        actions = [e for e in entries if e["type"] == "action"]
        mutations = [e for e in entries if e["type"] == "mutation"]
        runs.append({
            "tools": Counter(a["tool"] for a in actions),
            "mutating": set(scope_entry.get("scope", {}).get("mutating_tools", [])),
            "kinds": Counter((m.get("reversibility") or {}).get("kind", "undeclared") for m in mutations),
            "violations": sum(not a.get("in_scope") for a in actions),
            "blocked": sum(a.get("status") == "blocked" for a in actions),
            "incomplete": sum(a.get("status") == "incomplete" for a in actions),
            "fingerprint": scope_entry.get("fingerprint") or fingerprint(scope_entry.get("scope", {})),
        })  # fmt: skip
    if not runs:
        raise ValueError(f"no audit logs (audit-*.jsonl) found in {folder}")
    return runs


def _stats(runs: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(runs)
    calls = sum((r["tools"] for r in runs), Counter())
    return {
        "n": n,
        "calls": calls,
        "per_run": {t: c / n for t, c in calls.items()},
        "runs_using": {t: sum(t in r["tools"] for r in runs) for t in calls},
        "mutating": set().union(*(r["mutating"] for r in runs)),
        "kinds": {k: sum(r["kinds"][k] for r in runs) / n for k in KINDS},
        **{k: sum(r[k] for r in runs) / n for k in ("violations", "blocked", "incomplete")},
        "fingerprints": sorted({r["fingerprint"] for r in runs}),
    }


def material_changes(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    """The rules that fired, in plain language."""
    found = []
    for tool in sorted((a["mutating"] | b["mutating"]) & (set(a["calls"]) | set(b["calls"]))):
        share_a = 100 * a["runs_using"].get(tool, 0) / a["n"]
        share_b = 100 * b["runs_using"].get(tool, 0) / b["n"]
        if abs(share_b - share_a) >= USE_RATE_POINTS:
            found.append(
                f"Rule 1: `{tool}` was used in {a['runs_using'].get(tool, 0)} of {a['n']} runs in A "
                f"and {b['runs_using'].get(tool, 0)} of {b['n']} runs in B "
                f"({share_a:.0f}% to {share_b:.0f}%)."
            )
        rate_a, rate_b = a["per_run"].get(tool, 0), b["per_run"].get(tool, 0)
        if abs(rate_b - rate_a) >= VOLUME_MIN and abs(rate_b - rate_a) >= VOLUME_RATIO * max(rate_a, 1e-9):
            found.append(f"Rule 2: `{tool}` calls per run went from {rate_a:.2f} in A to {rate_b:.2f} in B.")
    for tool in sorted(set(a["calls"]) ^ set(b["calls"])):
        where = "B but never in A" if tool in b["calls"] else "A but never in B"
        found.append(f"Rule 3: `{tool}` was used in {where}.")
    if a["fingerprints"] != b["fingerprints"]:
        found.append("Rule 4: the two sets ran under different scope fingerprints (see below).")
    for key in ("violations", "blocked", "incomplete"):
        if a[key] == 0 < b[key]:
            found.append(f"Rule 5: {key} per run rose from 0 in A to {b[key]:.2f} in B.")
    return found


def compare(a_dir: str | Path, b_dir: str | Path) -> str:
    """A Markdown comparison of the audit logs in two folders."""
    a, b = _stats(load_runs(a_dir)), _stats(load_runs(b_dir))
    changes = material_changes(a, b)
    lines = [
        "# Behavior comparison",
        "",
        f"- **A:** `{Path(a_dir).as_posix()}` ({a['n']} runs)",
        f"- **B:** `{Path(b_dir).as_posix()}` ({b['n']} runs)",
        "",
        "Built from counts in the audit logs only: tool names, numbers and scope fingerprints. "
        "A material behavior change is flagged by a heuristic when one of these rules fires:",
        "",
        *[f"{i}. {rule}" for i, rule in enumerate(RULES, 1)],
        "",
        "## Material behavior changes (heuristic)",
        "",
        *([f"- {c}" for c in changes] or ["None of the rules fired."]),
        "",
        "## Overview",
        "",
        "| | A | B |",
        "|---|---|---|",
        f"| Runs | {a['n']} | {b['n']} |",
        f"| Tool calls per run (mean) | {sum(a['calls'].values()) / a['n']:.2f} | {sum(b['calls'].values()) / b['n']:.2f} |",
        *[f"| Changes per run, {k} | {a['kinds'][k]:.2f} | {b['kinds'][k]:.2f} |" for k in KINDS],
        *[f"| {k.capitalize()} per run | {a[k]:.2f} | {b[k]:.2f} |" for k in ("violations", "blocked", "incomplete")],
        f"| Scope fingerprints | {', '.join(f'`{f[:12]}`' for f in a['fingerprints'])} "
        f"| {', '.join(f'`{f[:12]}`' for f in b['fingerprints'])} |",
        "",
        "## Tool use",
        "",
        "| Tool | Share of calls, A | Share of calls, B | Runs using it, A | Runs using it, B | Calls per run, A | Calls per run, B |",
        "|---|---|---|---|---|---|---|",
    ]
    total_a, total_b = sum(a["calls"].values()) or 1, sum(b["calls"].values()) or 1
    for tool in sorted(set(a["calls"]) | set(b["calls"])):
        mark = " (changes something)" if tool in a["mutating"] | b["mutating"] else ""
        lines.append(
            f"| `{tool}`{mark} | {a['calls'][tool] / total_a:.0%} | {b['calls'][tool] / total_b:.0%} "
            f"| {a['runs_using'].get(tool, 0)} | {b['runs_using'].get(tool, 0)} "
            f"| {a['per_run'].get(tool, 0):.2f} | {b['per_run'].get(tool, 0):.2f} |"
        )
    only = sorted(set(a["calls"]) ^ set(b["calls"]))
    lines += ["", "## Tools used in only one set", "", ", ".join(f"`{t}`" for t in only) or "None.", ""]
    return "\n".join(lines)
