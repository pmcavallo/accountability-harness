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

sys.path.insert(0, str(ROOT / "app"))

import inbox_triage as demo  # noqa: E402
import live_mode  # noqa: E402  (no model SDK at import; see live_mode.py)
from accountability_harness import (  # noqa: E402
    ArgRule,
    Harness,
    Reversibility,
    Scope,
    email_domain_in,
    fingerprint,
    load_scope,
    render_report,
)
from accountability_harness.audit import verify_text  # noqa: E402
from accountability_harness.compare import compare  # noqa: E402
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
    "Build your own test",
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
    with tempfile.TemporaryDirectory() as tmp:
        return execute(scope, mode, steps, demo.SCENARIO_INBOX.get(scenario, demo.EMAILS), demo.agent_name(scenario, mode), tmp)


def execute(scope: Scope, mode: str, steps: list, inbox: list, agent: str, log_dir: str) -> dict:
    """Run scripted tool calls through the harness, writing the log to log_dir."""
    with _LOCK:
        demo.reset_outside_world()
        demo.set_inbox(inbox)
        harness = Harness(scope, log_dir=log_dir, agent_name=agent, mode=mode)
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
    show_result(run(scenario, mode))


def show_result(result: dict) -> None:
    """Emails sent, the callouts, the owner summary, then the three questions."""
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


# -- playground: build your own test ------------------------------------

KIND_CHOICES = ["reversible", "compensable", "irreversible", "undeclared"]
# Only reserved example domains, so every address in the demo stays synthetic.
DOMAIN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+example$")
ADDRESS = re.compile(r"^[a-z0-9._%+-]{1,64}@(?P<domain>[a-z0-9.-]{1,200})$")


def parse_domains(text: str) -> list[str]:
    """Comma-separated domains, checked. Raises ValueError with a readable reason."""
    domains = [d.strip().lower().lstrip("@") for d in text.split(",") if d.strip()]
    if not domains:
        raise ValueError("The recipient rule is on but lists no domain. Add one, or switch the rule off.")
    for d in domains:
        if not DOMAIN.match(d):
            raise ValueError(f"'{d}' is not accepted: use a domain ending in .example, such as tallowlane.example.")
    return domains


def parse_address(text: str) -> str:
    """One email address on a .example domain. Raises ValueError with a readable reason."""
    address = text.strip().lower()
    match = ADDRESS.match(address)
    if not match or not DOMAIN.match(match["domain"]):
        raise ValueError(f"'{text.strip()}' is not accepted: use one address on a .example domain, such as team@tallowlane.example.")
    return address


def build_scope(allowed: list[str], mutating: list[str], mutations_allowed: bool, kinds: dict[str, str], domains: list[str] | None) -> Scope:
    """The edited scope. If it differs from the approved one in any way, it
    loses its approval: nobody has approved this version."""
    approved = demo.SCOPE
    declared: dict[str, Reversibility | None] = {}
    for tool in mutating:
        old = approved.mutating_tools.get(tool)
        if kinds[tool] == "undeclared":
            declared[tool] = None
        elif old and old.kind == kinds[tool]:
            declared[tool] = old
        else:
            declared[tool] = Reversibility(kinds[tool], "Declared in the playground; nobody wrote down how to undo it.")
    rules = []
    if domains:
        check = email_domain_in(*domains)
        rules.append(ArgRule("send_email", "to", check, f"Email may only go to {', '.join(domains)} addresses"))
    fields = dict(
        name=approved.name,
        allowed_tools=set(allowed),
        allowed_data_sources=set(approved.allowed_data_sources),
        mutating_tools=declared,
        mutations_allowed=mutations_allowed,
        arg_rules=rules,
        rationale={t: r for t, r in approved.rationale.items() if t in allowed},
        owner=approved.owner,
        review_by=approved.review_by,
    )
    same = Scope(**fields, description=approved.description, approver=approved.approver,
                 approved_on=approved.approved_on, version=approved.version, change_note=approved.change_note)
    if fingerprint(same.to_dict()) == fingerprint(approved.to_dict()):
        return same
    return Scope(**fields, description=approved.description + " Edited in the playground.",
                 version=f"{approved.version}-edited", change_note="Edited in the playground. Not approved by anyone.")


def scope_toml(scope: Scope, domains: list[str] | None) -> str:
    """The scope as a TOML scope file that load_scope reads back."""
    d = scope.to_dict()
    gov = d["governance"]
    q = json.dumps  # a JSON string or list of strings is valid TOML
    lines = ["# Built in the playground. Synthetic.", f"name = {q(d['name'])}", f"description = {q(d['description'])}"]
    for key in ("version", "owner", "approver", "approved_on", "review_by", "change_note"):
        if gov.get(key):
            lines.append(f"{key} = {gov[key]}" if key in ("approved_on", "review_by") else f"{key} = {q(gov[key])}")
    lines += [
        f"allowed_tools = {q(d['allowed_tools'])}",
        f"allowed_data_sources = {q(d['allowed_data_sources'])}",
        f"mutations_allowed = {'true' if d['mutations_allowed'] else 'false'}",
        "",
        "[rationale]",
        *[f"{t} = {q(r)}" for t, r in d["rationale"].items()],
    ]
    for tool, decl in d["reversibility"].items():
        lines += ["", f"[mutating_tools.{tool}]"]
        if decl:
            lines += [f"kind = {q(decl['kind'])}", f"how = {q(decl['how'])}"]
            lines += [f"window = {q(decl['window'])}"] if decl.get("window") else []
    if domains:
        rule = d["arg_rules"][0]
        lines += ["", "[[arg_rules]]", 'tool = "send_email"', 'arg = "to"', 'check = "email_domain_in"',
                  f"values = {q(domains)}", f"description = {q(rule['description'])}"]
    return "\n".join(lines) + "\n"


def describe_call(tool: str, args: dict) -> str:
    short = ", ".join(f"{k}={str(v)[:30]!r}" for k, v in args.items())
    return f"{tool}({short})"


def page_playground() -> None:
    st.header("Build your own test")
    st.write(
        "Start from the approved `inbox-assistant` scope, change what the agent may do, pick which scripted "
        "calls it makes, and run it. Nothing here calls a model: the calls are a fixed script. Any change to "
        "the scope makes it a new, unapproved version, because changing a scope is a governance decision, "
        "not a configuration tweak."
    )
    approved = demo.SCOPE.to_dict()
    tools = list(demo.TOOLS)
    st.subheader("1. The scope")
    st.markdown("**Allowed tools**")
    columns = st.columns(4)
    allowed = [
        t for i, t in enumerate(tools)
        if columns[i % 4].checkbox(t, value=t in approved["allowed_tools"], key=f"pg-allow-{t}")
    ]
    mutating = st.multiselect("Tools that change something", tools, default=approved["mutating_tools"], key="pg-mutating")
    mutations_allowed = st.checkbox("Changes allowed in this run", value=approved["mutations_allowed"], key="pg-changes")
    kinds = {}
    if mutating:
        st.markdown("**How each change can be undone**")
        columns = st.columns(len(mutating))
        for column, tool in zip(columns, mutating):
            decl = approved["reversibility"].get(tool)
            default = decl["kind"] if decl else "undeclared"
            kinds[tool] = column.selectbox(tool, KIND_CHOICES, index=KIND_CHOICES.index(default), key=f"pg-kind-{tool}")
    rule_on = st.checkbox("Limit `send_email` recipients to these domains", value=False, key="pg-rule")
    domain_text = st.text_input("Allowed domains, comma-separated", "tallowlane.example", max_chars=300, key="pg-domains")
    mode = st.radio("Mode", ["observe", "enforce"], horizontal=True, key="pg-mode")

    st.subheader("2. The script")
    scenario = st.selectbox(
        "Starting scenario", [s for s in SCENARIO_LABELS if s != "replay"], format_func=SCENARIO_LABELS.get, key="pg-scenario"
    )
    script = demo.SCENARIOS[scenario][2]
    enabled = [
        st.checkbox(f"{i}. `{describe_call(tool, args)}`", value=True, key=f"pg-step-{scenario}-{i}")
        for i, (tool, args) in enumerate(script, 1)
    ]
    sends = [args["to"] for tool, args in script if tool == "send_email"]
    recipient = st.text_input("Recipient for every `send_email` call", sends[0], max_chars=200, key=f"pg-to-{scenario}") if sends else None

    if not st.button("Run the edited test", type="primary", key="pg-run"):
        return
    try:
        domains = parse_domains(domain_text) if rule_on else None
        to = parse_address(recipient) if recipient is not None else None
    except ValueError as error:
        st.error(f"Not run. {error}")
        return
    scope = build_scope(allowed, mutating, mutations_allowed, kinds, domains)
    steps = [(t, {**a, "to": to} if t == "send_email" else a) for (t, a), on in zip(script, enabled) if on]
    st.session_state["pg-scope"] = scope
    with tempfile.TemporaryDirectory() as tmp:
        edited_dir, approved_dir = Path(tmp, "edited"), Path(tmp, "approved")
        result = execute(scope, mode, steps, demo.EMAILS, f"inbox-assistant (playground, {mode} mode)", str(edited_dir))
        execute(demo.SCOPE, mode, steps, demo.EMAILS, f"inbox-assistant (approved scope, {mode} mode)", str(approved_dir))
        comparison = compare(approved_dir, edited_dir)
        comparison = comparison.replace(approved_dir.as_posix(), "approved scope").replace(edited_dir.as_posix(), "edited scope")

    st.subheader("3. What the harness did")
    edited_print, approved_print = fingerprint(scope.to_dict()), fingerprint(approved)
    if edited_print != approved_print:
        st.warning(
            f"Changed scope: fingerprint `{edited_print[:12]}` is not the approved version `{approved_print[:12]}`. "
            "Until someone approves this version, every run under it reports that no one approved it."
        )
    else:
        st.success(f"Unchanged scope: this is the approved version, fingerprint `{approved_print[:12]}`.")
    show_result(result)
    st.subheader("The edited scope as a file")
    st.caption(f"Fingerprint (SHA-256): {edited_print}")
    st.code(scope_toml(scope, domains), language="toml")
    st.subheader("Compared with the approved scope")
    st.caption("The same script under the approved scope (A) and the edited one (B), in the same mode.")
    flagged = comparison.split("## Material behavior changes (heuristic)")[1].split("\n## ")[0]
    flags = [line[2:] for line in flagged.strip().splitlines() if line.startswith("- ")]
    for flag in flags:
        st.warning(flag)
    if not flags:
        st.info("No material behavior change flagged between the two runs.")
    with st.expander("The full comparison"):
        st.markdown(comparison)


# -- live model (local only) ---------------------------------------------

LIVE_PAGE = "Live model (local)"


def page_live() -> None:
    st.error("LIVE: a real model is called and your API credits are charged.")
    st.header(LIVE_PAGE)
    st.write(
        f"Runs `{live_mode.MODEL}` as the inbox assistant through the harness, with the planted email in the "
        f"inbox. At most {live_mode.agent_loop.MAX_STEPS} tool calls and {live_mode.agent_loop.MAX_TOKENS} "
        "output tokens per reply. This page exists only in a local run with live mode switched on."
    )
    prompt = st.radio("System prompt", list(live_mode.PROMPTS), horizontal=True, key="live-prompt")
    st.caption(live_mode.PROMPTS[prompt])
    choices = ["approved"] + (["playground"] if "pg-scope" in st.session_state else [])
    which = st.radio(
        "Scope",
        choices,
        format_func={"approved": "The approved inbox-assistant scope", "playground": "The scope from the last playground run"}.get,
        horizontal=True,
        key="live-scope",
    )
    if len(choices) == 1:
        st.caption("Run a test on the 'Build your own test' page to use its scope here.")
    scope = st.session_state["pg-scope"] if which == "playground" else demo.SCOPE
    mode = st.radio("Mode", ["observe", "enforce"], horizontal=True, key="live-mode")
    high = live_mode.cost(live_mode.EST_MAX_INPUT, live_mode.EST_MAX_OUTPUT)
    typical = live_mode.cost(live_mode.TYPICAL_INPUT, live_mode.TYPICAL_OUTPUT)
    st.info(
        f"Estimated cost per run: about ${typical:.4f} for a typical run, at most about ${high:.4f}. "
        f"An estimate at ${live_mode.PRICE_PER_MTOK['input']:.2f} per million input tokens and "
        f"${live_mode.PRICE_PER_MTOK['output']:.2f} per million output tokens."
    )
    used = st.session_state.get("live-runs", 0)
    st.caption(f"{used} of {live_mode.MAX_LIVE_RUNS} live runs used in this session.")
    capped = used >= live_mode.MAX_LIVE_RUNS
    if capped:
        st.warning(f"Session limit reached: {live_mode.MAX_LIVE_RUNS} live runs. Restart the app to run more.")
    if st.button("Run with real model", type="primary", disabled=capped, key="live-run") and not capped:
        st.session_state["live-runs"] = used + 1  # counted before the call, so failed runs count too
        with st.spinner("Calling the model..."):
            st.session_state["live-last"] = live_mode.run_live(scope, mode, prompt)
        st.rerun()  # redraw with the new count; the rerun shows the stored result and calls nothing
    result = st.session_state.get("live-last")
    if not result:
        return
    if "error" in result:
        st.error(f"Live run failed: {result['error']}")
        return
    st.subheader("Last live run")
    columns = st.columns(2)
    columns[0].metric("Tool calls made", len(result["calls"]))
    columns[1].metric("Blocked calls", result["blocked"])
    st.write(
        f"Model reported: `{result['model']}`. Tokens: {result['input_tokens']:,} in, {result['output_tokens']:,} out, "
        f"over {result['api_calls']} API call(s). Estimated cost: ${result['cost']:.4f}."
    )
    show_result(result)


# -- layout ---------------------------------------------------------------

st.set_page_config(page_title="Agent Accountability Harness", layout="wide")
st.sidebar.title("Agent Accountability Harness")
# The live page exists only when the local gate is open; otherwise it is not listed at all.
page = st.sidebar.radio("Page", PAGES + ([LIVE_PAGE] if live_mode.gate_open() else []))
st.sidebar.caption(f"Governance checks use the demo date, {demo.DEMO_DATE}.")
if page != LIVE_PAGE:
    st.info(HEADER)  # the live page shows its own red banner instead
{
    LIVE_PAGE: page_live,
    "Run a scenario": page_run,
    "Observe vs enforce": page_side_by_side,
    "The scope": page_scope,
    "Change comparison": page_compare,
    "Findings": page_findings,
    "Tamper check": page_tamper,
    "Build your own test": page_playground,
}[page]()
