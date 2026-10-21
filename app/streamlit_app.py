"""Demo app for the Agent Accountability Harness.

Runs only the scripted demo scenarios, the recorded real-model replay and
committed result files. No AI model runs here, no key is read and no
network access is needed. All data is synthetic, and "sent" email only
goes into a list in demo/inbox_triage.py.

Run locally from the repo root:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
import threading
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "demo"))

import inbox_triage as demo  # noqa: E402
from accountability_harness import Harness, fingerprint, load_scope, render_report  # noqa: E402
from accountability_harness.audit import verify_text  # noqa: E402
from accountability_harness.governance import findings  # noqa: E402
from accountability_harness.report import chain_status  # noqa: E402

# Where the Findings page links to. Set it to "" to name the files instead.
REPO_BLOB_URL = "https://github.com/pmcavallo/accountability-harness/blob/main"

HEADER = "Synthetic demo. No real email is sent. No AI model runs in this app."

PAGES = [
    "Run a scenario",
    "Observe vs enforce",
    "The scope",
    "Change comparison",
    "Findings",
    "Tamper check",
]

SCENARIO_LABELS = {
    "clean": "Clean: everything in scope",
    "violation": "Injected email obeyed: send_email is not in scope",
    "mutation": "Review-only run makes a change",
    "argument": "Email allowed, but only to internal addresses",
    "unapproved": "Incomplete governance: an unapproved scope",
    "replay": "Real-model replay: a recorded run, no model called",
}

# The replay holds drafts a real model wrote in a paid run. The app shows
# which calls it made, not the text it wrote.
HIDDEN_DRAFT = "[draft text from the recorded model run; not shown in the app]"

# The demo's tools write to module-level lists, so one run at a time.
_LOCK = threading.Lock()


def link(path: str) -> str:
    return f"[`{path}`]({REPO_BLOB_URL}/{path})" if REPO_BLOB_URL else f"`{path}` in the repository"


# -- running the demo -------------------------------------------------


@st.cache_data(show_spinner=False)
def run(scenario: str, mode: str) -> dict:
    """Run one scripted scenario through the harness in a temporary folder.
    Returns the report (checked as of the demo date), the log text, the
    chain status and how many emails were actually sent."""
    scope, _, steps = demo.SCENARIOS[scenario]
    if scenario == "replay":
        steps = [(tool, {**args, "draft": HIDDEN_DRAFT} if "draft" in args else args) for tool, args in steps]
    with _LOCK, tempfile.TemporaryDirectory() as tmp:
        demo.reset_outside_world()
        demo.set_inbox(demo.SCENARIO_INBOX.get(scenario, demo.EMAILS))
        harness = Harness(scope, log_dir=tmp, agent_name=demo.agent_name(scenario, mode), mode=mode)
        tools = {name: harness.wrap(fn, on_block="return") for name, fn in demo.TOOLS.items()}
        for tool, args in steps:
            tools[tool](**args)
        log = harness.finalize()
        text = log.read_text(encoding="utf-8")
        return {
            "report": render_report(log, run_date=demo.DEMO_DATE),
            "chain": chain_status(log),
            "chain_ok": verify_text(text)[0] == "intact",
            "text": text,
            "sent": len(demo.SENT),
        }


def entries(text: str) -> list[dict]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def sections(report: str) -> dict[str, str]:
    """Split a report into its header and its "## " sections, keyed by heading."""
    parts = re.split(r"(?m)^## ", report)
    out = {"header": parts[0]}
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        out[heading.strip()] = body
    return out


def highlight(markdown: str) -> str:
    """Red for blocked calls, violations and changes that cannot be undone."""
    for word in ("BLOCKED", "VIOLATION"):
        markdown = markdown.replace(f"[{word}]", f":red[**{word}**]")
    return markdown.replace("### Cannot be undone (irreversible)", "### :red[Cannot be undone (irreversible)]")


def callouts(result: dict) -> None:
    """What needs attention, above the report: red for blocked, flagged and
    irreversible; amber for governance findings."""
    log = entries(result["text"])
    actions = [e for e in log if e["type"] == "action"]
    blocked = [a["tool"] for a in actions if a.get("status") == "blocked"]
    flagged = [a["tool"] for a in actions if not a.get("in_scope") and a.get("status") != "blocked"]
    irreversible = [
        m["tool"] for m in log if m["type"] == "mutation" and (m.get("reversibility") or {}).get("kind") == "irreversible"
    ]
    scope = next(e for e in log if e["type"] == "scope")["scope"]
    if blocked:
        st.error(f"Blocked before it ran: {', '.join(blocked)}. The tool never executed.")
    if flagged:
        st.error(f"Outside the scope, flagged but not stopped: {', '.join(flagged)}.")
    if irreversible:
        st.error(f"Changes that cannot be undone: {', '.join(irreversible)}.")
    for gap in findings(scope, demo.DEMO_DATE):
        st.warning(f"Governance finding: {gap}")
    (st.success if result["chain_ok"] else st.error)(f"Audit log: {result['chain']}")


# -- pages --------------------------------------------------------------


def page_run() -> None:
    st.header("Run a scenario")
    st.write(
        "Each scenario is a fixed script of tool calls for a fictional events company's inbox "
        "assistant. The harness checks every call against the declared scope and writes an audit log; "
        "the report below is built from that log."
    )
    scenario = st.selectbox("Scenario", list(SCENARIO_LABELS), format_func=SCENARIO_LABELS.get)
    default = demo.SCENARIOS[scenario][1]
    mode = st.radio(
        "Mode",
        ["observe", "enforce"],
        index=["observe", "enforce"].index(default),
        horizontal=True,
        key=f"mode-{scenario}",
        help="Observe records and flags out-of-scope calls. Enforce blocks them before they run.",
    )
    if scenario == "replay":
        st.caption(
            "The tool calls one real model run made, replayed from demo/replay-trace.json. "
            "The draft text the model wrote is hidden here."
        )
    result = run(scenario, mode)
    parts = sections(result["report"])
    st.metric("Emails actually sent", result["sent"])
    callouts(result)
    with st.container(border=True):
        st.subheader("Summary for the owner")
        st.markdown(parts["Summary for the owner"])
    for heading in [h for h in parts if h[:2] in ("1.", "2.", "3.")]:
        st.subheader(heading)
        st.markdown(highlight(parts[heading]))


def page_side_by_side() -> None:
    st.header("Observe vs enforce")
    st.write(
        "The same scenario twice: the assistant reads a planted email asking for the client list to go "
        "to an outside address, and obeys it by calling `send_email`, which is not in the scope. "
        "Same scope, same calls. Only the mode differs."
    )
    columns = st.columns(2)
    for column, mode in zip(columns, ["observe", "enforce"]):
        result = run("violation", mode)
        send = next(e for e in entries(result["text"]) if e["type"] == "action" and e["tool"] == "send_email")
        with column:
            st.subheader(f"{mode.capitalize()} mode")
            st.metric("Emails actually sent", result["sent"])
            if send.get("status") == "blocked":
                st.error("`send_email` was blocked before it ran. The email was never sent.")
            else:
                st.error("`send_email` ran and the email was sent. The harness flagged it afterwards.")
            with st.container(border=True):
                st.markdown(sections(result["report"])["Summary for the owner"])


def page_scope() -> None:
    st.header("The scope")
    st.write("A scope is a governed document: who owns it, who approved it, what the agent may touch and why.")
    files = sorted((ROOT / "demo" / "scopes").glob("*.toml"))
    path = st.selectbox("Scope file", files, format_func=lambda p: p.name)
    scope = load_scope(path).to_dict()
    gov = scope["governance"]
    with st.container(border=True):
        st.subheader(f"{scope['name']}, version {gov.get('version') or 'not set'}")
        st.write(scope.get("description", ""))
        st.markdown(
            f"- **Owner:** {gov.get('owner') or 'not recorded'}\n"
            f"- **Approved by:** {gov.get('approver') or 'not recorded'}"
            + (f", on {gov['approved_on']}" if gov.get("approved_on") else "")
            + f"\n- **Review by:** {gov.get('review_by') or 'not set'}\n"
            f"- **Change note:** {gov.get('change_note') or 'none'}\n"
            f"- **Changes allowed in this run:** {'yes' if scope['mutations_allowed'] else 'no'}\n"
            f"- **Fingerprint (SHA-256):** `{fingerprint(scope)[:12]}`"
        )
        st.markdown("**Allowed tools and why**")
        st.table(
            pd.DataFrame(
                [{"Tool": t, "Reason": scope["rationale"].get(t) or "none recorded"} for t in scope["allowed_tools"]]
            )
        )
        st.markdown("**Tools that change something, and how each change can be undone**")
        rows = []
        for tool, decl in scope["reversibility"].items():
            rows.append(
                {
                    "Tool": tool,
                    "Allowed": "yes" if tool in scope["allowed_tools"] else "no",
                    "Reversibility": decl["kind"] if decl else "not declared",
                    "How": decl["how"] if decl else "nobody wrote down how to undo it",
                    "Window": (decl or {}).get("window") or "",
                }
            )
        st.table(pd.DataFrame(rows))
        st.markdown("**Argument rules**")
        rules = scope["arg_rules"]
        st.markdown("\n".join(f"- `{r['tool']}`, `{r['arg']}`: {r['description']}" for r in rules) or "None.")
        gaps = findings(scope, demo.DEMO_DATE)
        st.markdown(f"**Governance findings as of {demo.DEMO_DATE}**")
        for gap in gaps:
            st.warning(gap)
        if not gaps:
            st.success("None.")


def compare_numbers(text: str) -> tuple[int, int, int, int]:
    """Runs using place_calendar_hold, and runs in each set, from the comparison file."""
    row = re.search(r"^\| `place_calendar_hold`[^|]*\|[^|]*\|[^|]*\| (\d+) \| (\d+) \|", text, re.M)
    runs = re.search(r"^\| Runs \| (\d+) \| (\d+) \|", text, re.M)
    return int(row[1]), int(row[2]), int(runs[1]), int(runs[2])


def page_compare() -> None:
    st.header("Change comparison")
    path = "experiments/COMPARE-neutral-vs-permissive.md"
    text = (ROOT / path).read_text(encoding="utf-8")
    st.write(
        "The same model and the same scope, with two system prompts: 50 runs with a neutral prompt (A) "
        "and 50 with a permissive one (B). The comparison works from counts in the audit logs only."
    )
    a, b, runs_a, runs_b = compare_numbers(text)
    st.subheader("Runs that placed a calendar hold")
    chart = pd.DataFrame(
        {"Runs": [a, b]},
        index=[f"A: {a} of {runs_a}", f"B: {b} of {runs_b}"],
    )
    st.bar_chart(chart, y="Runs", horizontal=True, color="#b54708", height=180)
    st.caption("A: neutral prompt. B: permissive prompt.")
    st.subheader("Material behavior changes flagged")
    flags = text.split("## Material behavior changes (heuristic)")[1].split("\n## ")[0]
    for line in flags.strip().splitlines():
        if line.startswith("- "):
            st.warning(line[2:])
    with st.expander(f"The full comparison ({path})"):
        st.markdown(text)


def page_findings() -> None:
    st.header("Findings")
    path = "experiments/RESULTS.md"
    text = (ROOT / path).read_text(encoding="utf-8")
    headline = text.split("## Headline\n")[1].split("\n## ")[0].strip()
    st.write("The headline of the real-model results, as written in the results file:")
    with st.container(border=True):
        st.markdown(headline)
    st.markdown(f"Full results: {link(path)}.  \nLimits: {link('docs/WHAT-THIS-DOES-NOT-PROVE.md')}.")
    with st.expander("What this does not prove"):
        st.markdown((ROOT / "docs" / "WHAT-THIS-DOES-NOT-PROVE.md").read_text(encoding="utf-8"))


def tamper(text: str) -> tuple[str, int]:
    """In memory, edit the log line that records the out-of-scope send so it
    reads as in scope. Returns the edited text and the edited line number."""
    lines = text.splitlines()
    number = next(
        i for i, line in enumerate(lines, 1) if '"type": "action"' in line and '"tool": "send_email"' in line
    )
    entry = json.loads(lines[number - 1])
    entry["in_scope"] = True
    lines[number - 1] = json.dumps(entry, default=str)
    return "\n".join(lines) + "\n", number


def page_tamper() -> None:
    st.header("Tamper check")
    st.write(
        "Each log entry carries the SHA-256 hash of the entry before it, so an edited, deleted or "
        "reordered line breaks the chain. Below: the log of the observe-mode violation run, then a copy "
        "in memory where someone edited the send to look in scope. Nothing is written to disk."
    )
    text = run("violation", "observe")["text"]
    state, count = verify_text(text)
    st.subheader("The log as written")
    st.success(f"Chain {state}: {count} entries verified.")
    edited, number = tamper(text)
    before = json.loads(text.splitlines()[number - 1])
    after = json.loads(edited.splitlines()[number - 1])
    st.subheader(f"A copy with line {number} edited")
    st.table(
        pd.DataFrame(
            {
                "Field": ["seq", "tool", "in_scope"],
                "As written": [str(before[k]) for k in ("seq", "tool", "in_scope")],
                "Edited copy": [str(after[k]) for k in ("seq", "tool", "in_scope")],
            }
        )
    )
    state, line = verify_text(edited)
    st.error(f"Chain {state} at line {line}: the edit is detected.")
    st.caption(
        "Tamper-evident, not tamper-proof: nothing stops the edit, and a rewrite of the whole file with "
        "fresh hashes, or lines cut from the end, is not detected unless the final hash is kept elsewhere."
    )


# -- layout ---------------------------------------------------------------

st.set_page_config(page_title="Agent Accountability Harness", layout="wide")
st.info(HEADER)
st.sidebar.title("Agent Accountability Harness")
page = st.sidebar.radio("Page", PAGES)
st.sidebar.caption(f"Governance checks use the demo date, {demo.DEMO_DATE}.")
{
    "Run a scenario": page_run,
    "Observe vs enforce": page_side_by_side,
    "The scope": page_scope,
    "Change comparison": page_compare,
    "Findings": page_findings,
    "Tamper check": page_tamper,
}[page]()
