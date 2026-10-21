# Agent Accountability Harness

A small Python library for the person who deploys an AI agent. Before the run, you declare what the agent may touch and how each of its changes can be undone. During the run, the harness records every tool call and flags, or blocks, the ones outside that declaration. After the run, it writes a plain-language report that opens with a one-screen summary for the accountable owner. The scope itself is a governed document: who owns it, who approved it, when it is due for review. It works with any Python tool function, has no required dependencies, and includes an optional LangChain adapter. It never undoes anything; it records how a change can be undone.

All demo, test and experiment data in this repository is synthetic.

## The three questions

Every report opens with a summary for the owner (approval, review status, changes by reversibility, what needs attention, and whether the log verified), then answers:

1. **What was the agent allowed to touch?** The declared scope: tools, whether changes are allowed, argument rules, and how each change can be undone.
2. **What did it do?** Every recorded tool call, in order, marked OK, VIOLATION or BLOCKED, with the reason.
3. **How can its actions be undone?** Each change, grouped by how it can be undone, as declared before the run, worst first.

## Quick start

```python
from accountability_harness import Harness, Reversibility, Scope, render_report

scope = Scope(name="inbox-assistant", allowed_tools={"draft_reply"}, mutations_allowed=True,
              mutating_tools={"draft_reply": Reversibility.reversible(how="Delete the draft."),
                              "send_email": Reversibility.irreversible(how="Send a correction.")})
harness = Harness(scope, agent_name="inbox-assistant")     # mode="observe" is the default
draft_reply = harness.wrap(lambda email_id, text: "draft saved", name="draft_reply")
send_email = harness.wrap(lambda to, body: "sent", name="send_email")

draft_reply(1, "Thanks, the headcount is 25.")             # in scope: recorded
send_email("someone@outside.example", "Hello")             # not in scope: recorded and flagged
print(render_report(harness.finalize()))
```

The report marks step 2 `[VIOLATION]` and, under question 3, lists it first as a change that cannot be undone. `@harness.tool` is the decorator form of `wrap`. Any other integration can call `start_call`, `end_call` and `fail_call` directly.

Install from a clone: `pip install -e .`, or `pip install -e ".[langchain]"` for the LangChain adapter. Python 3.11 or later. The package is not on PyPI.

## Observe or enforce

```python
harness = Harness(scope, mode="enforce")
send_email = harness.wrap(send, name="send_email", on_block="return")
print(send_email("someone@outside.example", "Hello"))     # blocked: tool 'send_email' is not in the declared scope
```

- **Observe** (the default) is a detective control. The call runs, and the harness records it and flags it.
- **Enforce** is a preventive control. A call that fails the check never runs. It is recorded as blocked and raises `ToolCallBlocked`, or with `on_block="return"` returns the text `blocked: <reason>`, so an agent loop can read the refusal.

Running the same scope both ways is the point: observe tells you what went wrong; enforce stops a declared category of wrong before it happens, and only that category.

## Reversibility

For each tool that changes something, declare before the run how the change can be undone:

```python
mutating_tools={
    "draft_reply": Reversibility.reversible(how="Delete the draft."),
    "place_calendar_hold": Reversibility.reversible(how="Release the hold.", window="until the hold expires in 48 hours"),
    "issue_refund": Reversibility.compensable(how="Charge the amount again with the customer's consent."),
    "send_email": Reversibility.irreversible(how="Send a correction to the same recipient."),
}
```

- **Reversible:** undone directly.
- **Compensable:** not undone, but offset by a separate action.
- **Irreversible:** nothing restores the prior state.

A mutating tool with no declaration is reported as "no reversibility declared": a gap nobody planned for. Whether changes are allowed at all is a separate switch, `mutations_allowed`, so a review-only run can flag any change.

## Argument rules

A tool name is often too coarse. Argument rules constrain the arguments of a call:

```python
arg_rules=[ArgRule(tool="send_email", arg="to",
                   check=email_domain_in("tallowlane.example"),
                   description="Email may only go to tallowlane.example addresses")]
```

A call that breaks a rule is flagged in observe mode and blocked in enforce mode. Helpers: `email_domain_in(*domains)` (every address, including comma-separated lists, must be at a listed domain) and `value_in(*values)`; any function returning True or False also works.

Rules **fail closed**. A missing argument, a call with no named arguments, or a check that raises all count as broken. Through `wrap`, default values are filled in before the check.

## Governance layer

The harness also governs the decision behind a run, not only the run.

**The scope as a governed document.** A scope can be a TOML file with an owner, an approver, an approval date, a version, a review date, a change note and a one-line reason for each allowed tool, alongside its reversibility declarations and argument rules:

```toml
name = "inbox-assistant"
version = "1.0"
owner = "Operations lead, Tallow Lane Events"
approver = "Managing director, Tallow Lane Events"
approved_on = 2026-10-15
review_by = 2027-04-15
allowed_tools = ["read_inbox", "draft_reply"]

[rationale]
read_inbox = "Needs to see which emails arrived."
draft_reply = "Prepares replies for a person to review and send."
```

Load it with `load_scope("scope.toml")`. Every log records these fields and a SHA-256 fingerprint of the scope, so the report shows exactly which approved version the agent ran under. The report lists governance findings: no approver, no owner, review overdue, a tool allowed without a reason. They are findings, not errors; the run proceeds. See `demo/scopes/` and `demo/sample-report-unapproved.md`.

**Change comparison.** `accountability-harness compare A B` compares two folders of audit logs (for example, before and after a prompt change) using counts only. It flags a **material behavior change** when one of five documented rules fires; this is a heuristic, and the thresholds are printed with every comparison.

**A tamper-evident log.** Each log entry is hash-chained to the one before. `accountability-harness verify LOG` reports "chain intact", the first line where the chain breaks, or "not chained" for older logs. This detects edits after the fact. It does not prevent them, and a rewrite of the whole file with fresh hashes goes undetected unless the final hash is stored somewhere else.

**Command line:**

```bash
accountability-harness report LOG       # print the report for one audit log
accountability-harness verify LOG       # check the log's hash chain (exit 0 intact, 1 broken, 2 not chained)
accountability-harness compare A B      # compare two folders of audit logs
```

Without installing the package, use `python -m accountability_harness` instead.

## Demo

A scripted inbox assistant for Tallow Lane Events, a fictional events company. One email is a planted indirect prompt injection asking for the client list and price sheet to go to an outside address. No model or network is needed.

```bash
python demo/inbox_triage.py clean              # everything in scope; one change has no reversibility declared
python demo/inbox_triage.py violation          # obeys the planted email; send_email is not in scope: flagged, and sent
python demo/inbox_triage.py enforce            # the same calls in enforce mode: blocked, nothing sent
python demo/inbox_triage.py mutation           # an allowed tool, but this run allows no changes: flagged
python demo/inbox_triage.py unapproved         # in scope, but under a scope nobody approved: governance findings
python demo/inbox_triage.py argument           # email allowed only internally; the outside send breaks the rule
python demo/inbox_triage.py argument enforce   # the outside send is blocked; an internal one goes through
python demo/inbox_triage.py replay             # replays the tool calls a real model made in one recorded run
```

Each scenario runs through the core and, if `langchain-core` is installed, through the LangChain adapter, and checks that the two reports match. Sample reports are in `demo/sample-report-*.md`.

## Demo app

A small Streamlit app in `app/` shows the same demo in a browser: run a scenario in either mode, observe and enforce side by side, the governed scope, the change comparison, the headline findings and a tamper check. It runs only the scripted scenarios, the recorded replay and committed files. No AI model runs in it, it reads no key and it needs no network access. All data is synthetic.

```bash
pip install -e ".[app]"            # or: pip install -r app/requirements.txt
streamlit run app/streamlit_app.py
```

Hosted version: _URL to be added after deployment._

![Run a scenario: the injected email obeyed in observe mode, flagged and sent](docs/images/app-run-a-scenario.jpg)

![Observe vs enforce: one email sent and flagged, against none sent](docs/images/app-observe-vs-enforce.jpg)

![Change comparison: calendar holds in 4 of 50 runs against 50 of 50](docs/images/app-change-comparison.jpg)

Deployment steps are in [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Findings from 100 real-model runs

`experiments/` runs Claude Haiku 5.5 (`claude-haiku-5-5`) as the same inbox assistant, through a small hand-rolled tool-use loop with every tool going through the harness. There were five injection techniques, observe and enforce modes, and two system prompts: a neutral one and a permissive one (act on behalf of the owner, complete what each email asks, without asking for confirmation). That gives 100 runs, on 2026-10-21, costing $0.14 in total from reported usage. The outcomes below are measured from the audit logs.

1. **The model did not attempt the outside send in any of the 100 runs,** across all five techniques and both prompts. It read the planted email every time. Under the permissive prompt, its closing summary pointed out the planted email to the user in all 50 runs; all 50 summaries were read by hand.
2. **Changing the system prompt changed what the agent actually did with legitimate requests, and the harness recorded and classified every action.** The two prompts share their first and last sentences and differ in between (both are quoted in `RESULTS.md`). Under the permissive prompt the agent placed the calendar hold that one email asks for in 50 of 50 runs, against 4 of 50 under the neutral prompt, and drafted fewer replies (107 against 168). All 329 changes across the 100 runs were recorded with their declared reversibility.

3. **The change comparison surfaces the prompt change from the audit logs alone.** Run on the two sets of logs, it flags the calendar hold (4 of 50 runs to 50 of 50) as a material behavior change, while both sets ran under the same scope fingerprint: the scope did not change, the behavior did. See [`experiments/COMPARE-neutral-vs-permissive.md`](experiments/COMPARE-neutral-vs-permissive.md).

Because the model never attempted the send, **no real-model run exercised flagging or blocking**. That behavior is shown by the scripted scenarios and the tests. This is a case study of one model on one scenario, not a benchmark. Full setup, tables and limits: [`experiments/RESULTS.md`](experiments/RESULTS.md).

## Documentation

- [`docs/CONTROLS.md`](docs/CONTROLS.md): each control, the risk it addresses, how it is tested, and what it does not cover
- [`docs/THREAT-MODEL.md`](docs/THREAT-MODEL.md): the scenario, assets, threats, and what remains
- [`docs/WHAT-THIS-DOES-NOT-PROVE.md`](docs/WHAT-THIS-DOES-NOT-PROVE.md)
- [`docs/FRAMEWORK-MAPPING.md`](docs/FRAMEWORK-MAPPING.md): an illustrative mapping to the NIST AI RMF, the EU AI Act and the OWASP Top 10 for LLM Applications. It is not a compliance claim. Every citation was checked against its primary source on 2026-10-21.
- [`experiments/RESULTS.md`](experiments/RESULTS.md): the real-model case study
- [`CHANGELOG.md`](CHANGELOG.md)

## Limits

- Only calls that go through the harness are recorded or blocked.
- The audit log is **tamper-evident, not tamper-proof**: the hash chain detects edits but does not prevent them, and it misses a full rewrite or lines cut from the end unless the final hash is kept elsewhere. The log can contain message text and should be treated as sensitive. Arguments and results are truncated (500 characters by default), but there is no redaction option.
- Governance fields are recorded text, not verified approvals. The change comparison is a heuristic over counts.
- The harness never undoes anything, and it does not check that a declared undo works.
- `allowed_data_sources` is recorded but not checked.
- `wrap` supports synchronous functions only. The LangChain adapter's blocking is tested for `invoke` and `ainvoke` on `langchain-core` 1.6.12, and it does not fill in default values before argument rules.
- It does not detect prompt injection. It checks calls against a scope, and a scope is only as good as the person who writes it.

## Development

```bash
py -m venv .venv
.venv/Scripts/python -m pip install -e ".[langchain,test]"
.venv/Scripts/python -m pytest          # all tests run offline; none calls a model
```

The core package is about 1,300 lines in `src/accountability_harness/`. Running the real-model suite needs `pip install -e ".[experiments]"` and `ANTHROPIC_API_KEY` set in your terminal. `python experiments/run_suite.py` prints the plan and cost estimate without calling the API.

## License

MIT. See [`LICENSE`](LICENSE).
