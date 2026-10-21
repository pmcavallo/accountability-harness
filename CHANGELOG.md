# Changelog

All notable changes, summarized from the project's development milestones. Versions 0.2.0 to 0.8.0 were all built on 2026-10-21. 0.8.0 is the first public release; this repository starts there, as a single commit.

## 0.8.0 (Milestone 7)

The demo app. No paid runs, no model calls.

- **Demo app** in `app/streamlit_app.py`, with six pages: run a scenario, observe vs enforce side by side, the scope card, the change comparison with a chart, the headline findings, and an in-memory tamper check. It runs only the scripted scenarios, the recorded replay (with the model-written drafts hidden) and committed files. No model, no key, no network. Streamlit is the optional `[app]` extra; `app/requirements.txt` is for Streamlit Community Cloud. `docs/DEPLOY.md` has the deploy steps, and the README has a "Demo app" section with screenshots.
- **Verified citations.** `docs/FRAMEWORK-MAPPING.md` now gives exact identifiers, paraphrases and source URLs for every citation (V1 to V22 and V24 to V27), checked against the primary sources on 2026-10-21. V13 was removed. The mapping is no longer a draft.
- **Injectable run date.** `render_report(log, run_date=...)` sets the "today" the governance findings are checked against; by default it is still the day the run was logged. The tests pin the log clock, and the demo takes `--as-of YYYY-MM-DD`, so nothing breaks when the demo scopes' review date passes.
- `verify_text(text)` in `accountability_harness.audit` checks a log held in memory; `verify(path)` uses it.

## 0.7.0 (Milestone 6)

The governance layer. No paid runs.

- **Python 3.11 or later is now required** (`requires-python = ">=3.11"`), for `tomllib`.
- **Governed scope.** `load_scope(path)` builds a scope from a TOML file. New governance fields: `owner`, `approver`, `approved_on`, `version`, `review_by`, `change_note`, and a `rationale` per allowed tool. Argument rules in a file can use only `email_domain_in` and `value_in`. Every log records the governance fields and a SHA-256 fingerprint of the scope. The report lists governance findings: no approver, no owner, review overdue, a tool without a reason. Built-in rule helpers now record what they check in the log.
- **Change comparison.** `compare(a_dir, b_dir)` compares two folders of audit logs using counts only, and flags material behavior changes by five documented heuristic rules. `experiments/COMPARE-neutral-vs-permissive.md` shows it on the M4 logs.
- **Tamper-evident log.** Every entry carries `prev_hash` and `hash` (SHA-256 over canonical JSON). `verify(log)` reports intact, the first broken line, or "not chained" for older logs.
- **Owner summary** at the top of every report.
- **Command line:** `accountability-harness report LOG`, `verify LOG` and `compare A B`, also runnable as `python -m accountability_harness`.
- Demo scopes are now TOML files in `demo/scopes/`, and there is a new `unapproved` scenario. Sample reports were regenerated.
- Docs updated: `CONTROLS.md` (controls 10 to 13), `THREAT-MODEL.md`, `WHAT-THIS-DOES-NOT-PROVE.md`, `FRAMEWORK-MAPPING.md` (new citations V24 to V27, all to be verified), and the README.
- The package size target was raised to about 1,300 lines.

## 0.6.0 (Milestone 5)

Documentation and release preparation. No code changes to the package beyond the version number.

- New `docs/CONTROLS.md` (control specification), `docs/THREAT-MODEL.md`, `docs/WHAT-THIS-DOES-NOT-PROVE.md` and `docs/FRAMEWORK-MAPPING.md`. The mapping is a draft, and every citation in it is marked to be verified.
- README rewritten.
- MIT license; license and author metadata in `pyproject.toml`; this changelog.
- `experiments/RESULTS.md`: all 50 permissive-run closing summaries read by hand (previously 5).

## 0.5.1 (Milestone 4b)

- The experiments' agent loop records each model reply's stop reason and the closing summary. Its limits were raised to 2,048 output tokens per reply and 15 tool calls per run.
- A permissive-prompt condition: 50 more real-model runs. Results in `experiments/RESULTS.md`.

## 0.5.0 (Milestone 4)

- **Argument rules fail closed.** A rule that cannot be checked counts as broken: a missing argument, a call with no named arguments, or a check that raises. `wrap` fills in default values before the check.
- The duplicated "the tool did not run" wording for blocked calls was removed from report question 2.
- New `experiments/`: a hand-rolled tool-use loop for a real model, a five-variant injection suite with hard caps on runs, tool calls and cost, and `RESULTS.md`. The `anthropic` package is an optional extra, `[experiments]`.
- New demo scenario `replay`, which replays a recorded real-model run offline.
- Tests stay offline. None calls a model.

## 0.4.0 (Milestone 3)

- **Enforce mode.** `Harness(mode="enforce")` blocks out-of-scope calls before they run; they are recorded as blocked, and `ToolCallBlocked` is raised. `wrap` takes `on_block="raise"` or `"return"`.
- Enforce mode in the LangChain adapter, tested for `invoke` and `ainvoke` on `langchain-core` 1.6.12.
- **Argument rules** (`ArgRule`) with the helpers `email_domain_in` and `value_in`.
- The report shows the mode, the argument rules and blocked calls.
- New demo scenarios: `enforce` and `argument`.

## 0.3.0 (Milestone 2)

- **Reversibility declarations.** `Reversibility.reversible`, `.compensable` and `.irreversible`, declared per mutating tool in the `Scope`. They are recorded with each change and used to build report questions 1 and 3.
- Calls that start but never finish are recorded as incomplete. A mutating call that fails or never finishes is recorded with an unknown outcome.
- Multi-line text no longer breaks the report layout.

## 0.2.0 (Milestone 1)

- A framework-neutral `Harness` core (`wrap`, `@harness.tool`, `start_call`, `end_call`, `fail_call`). LangChain moved to an optional adapter, `AccountabilityHandler`.
- Fixes to v0.1:
  - "append-only" wording that overclaimed;
  - errors not counted as violations;
  - a demo inbox with domain-specific flavor.
- A neutral synthetic demo domain (Tallow Lane Events, a fictional events company).
- Configurable truncation. The report warns when the run summary and the log disagree.

## 0.1.0

- The original prototype: a LangChain callback handler that recorded tool calls against a declared scope and rendered a three-question report. Committed as the baseline for Milestone 1.
