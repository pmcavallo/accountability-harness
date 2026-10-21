# Control Specification

This document describes each control the Agent Accountability Harness implements, as of version 0.7.0. For each control it states the risk addressed, whether the control is detective (it records and flags) or preventive (it stops something before it happens), how it is tested, and what it does not cover. Every statement is backed by the code in `src/accountability_harness/`, a test in `tests/`, or a result in `experiments/RESULTS.md`. All demo, test and experiment data is synthetic.

Terms used below:

- A **call** is one tool call that goes through the harness: through `Harness.wrap` or `@harness.tool`, through the LangChain adapter (`AccountabilityHandler`), or through the three integration methods `start_call`, `end_call` and `fail_call`.
- A **violation** is a call that fails the scope check.
- The **demo scenarios** are in `demo/inbox_triage.py`: `clean`, `violation`, `mutation`, `enforce`, `argument` (each in observe or enforce mode) and `replay`.

## Summary

| # | Control | Type | Where |
|---|---|---|---|
| 1 | Declared scope (tool names) | Detective; preventive in enforce mode | `Scope.allowed_tools`, `Scope.check` |
| 2 | Mutations allowed or not | Detective; preventive in enforce mode | `Scope.mutations_allowed`, `Scope.check` |
| 3 | Argument rules (fail closed) | Detective; preventive in enforce mode | `ArgRule`, `Scope.check` |
| 4 | Reversibility declarations | Detective (documentation and reporting) | `Reversibility`, `Scope.mutating_tools` |
| 5 | Observe mode | Detective | `Harness(mode="observe")` |
| 6 | Enforce mode | Preventive | `Harness(mode="enforce")`, `ToolCallBlocked` |
| 7 | Audit log | Detective (record) | `AuditLog` |
| 8 | Report | Detective (review) | `render_report` |
| 9 | Incomplete-call recording | Detective | `Harness.finalize` |
| 10 | Governed scope (scope files, governance fields, fingerprint, findings) | Detective (documentation and reporting) | `load_scope`, `Scope` governance fields, `governance.findings` |
| 11 | Change comparison | Detective (review across runs) | `compare`, `accountability-harness compare` |
| 12 | Hash-chained audit log | Detective (tamper evidence) | `AuditLog`, `verify`, `accountability-harness verify` |
| 13 | Owner summary | Detective (review) | the top of `render_report` |

Controls 1 to 3 are the scope check. They run in this order and a call is reported with the first reason that applies: tool not in scope, then mutation not allowed, then argument rules. Whether a failed check is only flagged or also blocked depends on the mode (controls 5 and 6).

---

## 1. Declared scope (tool names)

**What it does.** Before the run, the developer lists the tools the agent may call (`Scope.allowed_tools`). Every call to a tool not on the list fails the check with the reason "tool '<name>' is not in the declared scope". The scope, including its name and description, is written to the audit log before any call is recorded and is shown in question 1 of the report.

**Risk addressed.** An agent calls a tool it was never meant to use, for example because instructions planted in its input asked it to.

**Type.** Detective in observe mode; preventive in enforce mode.

**How it is tested.**

- `test_core.py`: `test_tool_not_in_scope_is_flagged`, `test_out_of_scope_error_counts_as_violation`
- `test_enforce.py`: `test_observe_mode_flags_but_runs` and `test_enforce_mode_blocks_and_never_runs` (the "not in scope" path)
- `test_langchain_adapter.py`: `test_out_of_scope_flagged`, `test_enforce_blocks_before_the_tool_runs`
- Demo scenarios: `violation` (flagged; the email is sent) and `enforce` (blocked; the sent-mail list stays empty); `test_demo.py::test_same_story_both_ways`

**What it does not cover.**

- It sees only calls that go through the harness. A tool the agent can reach some other way is invisible to it.
- It checks tool names, not what a tool does. A tool on the list that does more than its name suggests is in scope.
- `allowed_data_sources` is recorded and shown in the report but **never checked**. The harness cannot see which data a tool reads.

## 2. Mutations allowed or not

**What it does.** The scope names the tools that change something outside the agent (`Scope.mutating_tools`) and says whether this run may change anything at all (`Scope.mutations_allowed`). If changes are not allowed, a call to a mutating tool fails the check even when the tool is in scope: "tool '<name>' mutates external state, but this run does not allow mutations". Tool permission and change permission are separate switches. Every completed call to a mutating tool writes a mutation entry to the log.

**Risk addressed.** An agent that should only read and summarize (a review-only run) makes a change anyway, using a tool it is otherwise allowed to have.

**Type.** Detective in observe mode; preventive in enforce mode.

**How it is tested.**

- `test_core.py`: `test_mutation_not_allowed_is_flagged`, `test_mutation_allowed_is_recorded_without_violation`
- `test_enforce.py`: the "mutation not allowed" path in `test_observe_mode_flags_but_runs` and `test_enforce_mode_blocks_and_never_runs`
- `test_langchain_adapter.py`: `test_mutation_not_allowed_flagged`, `test_mutation_recorded`
- Demo scenario: `mutation`

**What it does not cover.**

- Whether a tool mutates is declared by the developer. A mutating tool left off `mutating_tools` is treated as read-only and writes no mutation entry.

## 3. Argument rules (fail closed)

**What it does.** An `ArgRule` constrains one argument of one tool, for example "email may only go to tallowlane.example addresses" (`email_domain_in`) or a fixed list of values (`value_in`). Any function that takes the value and returns True or False can be a check.

A call that breaks a rule fails the scope check with the rule's description as the reason. Rules fail closed. A rule that cannot be checked counts as broken:

- the call leaves out the argument;
- the call has no named arguments (for example, a LangChain tool invoked with a bare string);
- the check function raises.

Through `wrap`, the function's default values are filled in before the check, so a default is checked like any other value. Rules are written to the log with the scope (tool, argument, description, and the check: a built-in helper by name and values, such as `email_domain_in('tallowlane.example')`, or "custom Python check") and listed in question 1.

`email_domain_in` compares the exact domain after the last `@`. Every address in a comma-separated string or a list must pass. Subdomains fail unless listed, and a bare domain or an empty entry fails.

**Risk addressed.** An allowed tool pointed at the wrong place: an email tool that may send internally is used to send to an outside address.

**Type.** Detective in observe mode; preventive in enforce mode.

**How it is tested.**

- `test_enforce.py`:
  - `test_email_domain_in` (11 cases, including a lookalike domain, a mixed list and a bare domain)
  - `test_value_in`, `test_a_check_that_raises_fails_the_rule`, `test_rule_only_applies_to_its_tool`
  - `test_a_rule_that_cannot_be_checked_fails` (missing argument, empty dict, `None`, bare string, positional tuple)
  - `test_missing_argument_is_a_violation_in_observe_mode`, `test_missing_argument_is_blocked_in_enforce_mode`
  - `test_a_default_value_is_checked_like_any_other`, `test_an_allowed_default_passes`
  - `test_rules_are_written_to_the_log_and_listed_in_question_1`
  - the "argument rule failed" path in both mode tests
- `test_langchain_adapter.py`: `test_enforce_applies_argument_rules`, `test_bare_string_call_fails_argument_rules`
- `test_suite.py::test_measure_enforce_run_with_a_mixed_recipient_list`: an internal-plus-outside recipient list is blocked
- Demo scenarios: `argument` and `argument enforce`

**What it does not cover.**

- **The LangChain path does not fill in default values.** The adapter sees only the input LangChain passes, not the function. A LangChain call that omits a rule's argument fails the rule even if the function's default would pass. That errs on the side of failing, so the adapter fails closed slightly more often than `wrap`.
- **No opt-out from failing closed.** A rule on an optional argument flags or blocks every call that leaves it out.
- Rules see argument values only. They cannot check what the tool does with them, or content the agent assembles elsewhere.
- Through `wrap`, a call whose arguments do not match the function's signature is recorded with positional and keyword arguments separated, so a rule finds no named argument and fails closed. This follows from the code; no test covers it with a rule.
- There is no policy language. Rules are plain Python functions. Larger policies belong in an existing policy engine.

## 4. Reversibility declarations

**What it does.** For each mutating tool, the scope can declare how its change can be undone, before the run:

- `Reversibility.reversible(how, window)`: undone directly, for example delete a draft;
- `Reversibility.compensable(how, window)`: not undone, but offset by a separate action;
- `Reversibility.irreversible(how)`: nothing restores the prior state; `how` says what can still be done.

A mutating tool can also be left undeclared (`None`). An unknown kind or an empty `how` is rejected.

The declarations are written to the log with the scope before any call. Every mutation entry carries the tool's declaration and an outcome: `completed`, or `unknown` when the call raised or never finished. Question 1 lists every mutating tool with its declaration, worst first. Question 3 groups the run's changes as irreversible, compensable, reversible, and "no reversibility declared", in that order.

**Risk addressed.** After a run, nobody knows which changes can still be undone, how, or for how long. Writing it down before the run also exposes tools nobody planned the undo for.

**Type.** Detective: documentation and reporting. It does not prevent anything and does not undo anything.

**How it is tested.**

- `test_reversibility.py` (19 tests): the kinds and the checks on them, the set and mapping forms, declarations in the log before the run, mutation entries with their declaration, failed and incomplete mutations with an unknown outcome, question 1 and question 3 wording and ordering, summary counts.
- Demo scenario `clean`: `add_client_contact` is deliberately undeclared and appears under "No reversibility declared".
- `experiments/RESULTS.md`: in the 100 real-model runs, every mutating call was recorded with its declared reversibility. Milestone 5 checked this against the audit logs: 54 calendar holds and 275 drafts, all declared reversible; 8 drafts with outcome `unknown` after the tool raised.

**What it does not cover.**

- **The harness never undoes anything.** It records how a change can be undone.
- A declaration is the developer's claim. The harness does not check that the undo method works or that the window is accurate.
- Blocked calls write no mutation entry. In question 3 they are listed separately, as "Blocked before they ran (nothing changed)".

## 5. Observe mode

**What it does.** The default. Every call is recorded. A call that fails the scope check is marked as a violation with its reason, and **the tool still runs**. The report header says "observe (records and flags out-of-scope calls; does not block them)".

**Risk addressed.** Lack of visibility. It is also the safe way to introduce a scope: see what would be flagged before blocking anything.

**Type.** Detective.

**How it is tested.**

- `test_enforce.py`: `test_observe_mode_flags_but_runs` (all three failure paths), `test_report_shows_mode`, `test_report_without_mode_in_log_reads_as_observe`
- `test_langchain_adapter.py::test_observe_handler_does_not_raise_or_block`
- `test_agent_loop.py::test_observe_mode_lets_the_outside_send_run`
- Demo scenarios: `violation` and `argument` (the outside email is actually sent, into a list in the script)

**What it does not cover.**

- It does not stop anything. A flagged irreversible call, such as sending an email, has already happened by the time anyone reads the report.

## 6. Enforce mode

**What it does.** A call that fails the scope check is blocked before the tool runs.

- `start_call` records the call with status `blocked` and the result "BLOCKED: the tool did not run". The call counts as a violation and as blocked, and `start_call` raises `ToolCallBlocked(tool, reason)`, so no integration runs the tool by accident.
- `wrap` and `@harness.tool` take `on_block="raise"` (the default) or `on_block="return"`. With `"return"`, the wrapped function hands back the text "blocked: <reason>", for an agent loop that reads tool results as text.
- The LangChain adapter sets LangChain's `raise_error` flag in enforce mode, so `ToolCallBlocked` raised in `on_tool_start` propagates out of `invoke()` before the tool body runs.

**Risk addressed.** An out-of-scope call, especially an irreversible one, completes before anyone can review it.

**Type.** Preventive.

**How it is tested.**

- `test_enforce.py`:
  - `test_enforce_mode_blocks_and_never_runs` (all three failure paths; a side-effect list stays empty)
  - `test_enforce_mode_lets_in_scope_calls_run`
  - `test_on_block_return_gives_a_plain_text_refusal`, `test_decorator_accepts_on_block`
  - `test_direct_start_call_raises_in_enforce_mode`, `test_invalid_mode_and_on_block_are_rejected`
  - `test_summary_and_report_agree_with_blocked_calls`, `test_question_3_says_a_blocked_change_changed_nothing`
- `test_langchain_adapter.py`:
  - `test_enforce_blocks_before_the_tool_runs`, run for `invoke` with a dict, `invoke` with a tool-call input and `ainvoke`, each with and without `handle_tool_error`
  - `test_enforce_blocks_an_async_tool`, `test_enforce_lets_in_scope_calls_run`, `test_handler_mode_follows_a_shared_harness`
- `test_agent_loop.py::test_a_blocked_call_comes_back_to_the_model_as_text`
- Demo scenarios: `enforce` and `argument enforce`

**What it does not cover.**

- **Only calls that go through the harness are enforced.**
- Code that catches every exception around `start_call` and runs the tool anyway defeats the block. The docstring says the caller must not run the tool.
- **The LangChain behavior is proven for `langchain-core` 1.6.12 only.** It relies on LangChain's `raise_error` handling, which a future version could change; the tests would catch that. LangChain also prints one warning line per blocked call. How a LangGraph agent loop (for example `ToolNode`) presents the block to a model is untested.
- **No real-model run was blocked.** In 100 runs, Claude Haiku 5.5 never attempted the outside send, so blocking is demonstrated by the scripted scenarios and the tests only (`experiments/RESULTS.md`). How a model reacts to a block is untested.

## 7. Audit log

**What it does.** One JSONL file per run (`audit-<run id>.jsonl` in `log_dir`, default `audit_logs/`). Each event is appended as one JSON line as the run proceeds. The entry types are:

- `run_meta`: agent name, mode;
- `scope`: the full declared scope, including reversibility and rules;
- `action`: one per call, with sequence number, tool, arguments, result, status (`ok`, `error`, `blocked` or `incomplete`), duration, in-scope flag and reason;
- `mutation`: what changed, declared reversibility, outcome, whether permitted;
- `run_end`: counts.

Arguments and results are truncated to `max_text` characters (default 500), with a marker showing the original length.

**Risk addressed.** No record of what an agent did, or a record that cannot be reconciled with the run's own summary.

**Type.** Detective (record).

**How it is tested.**

- `test_core.py`: `test_direct_start_and_end_calls`, `test_long_output_and_args_are_truncated`, `test_wrap_records_positional_and_keyword_args_the_same`, `test_error_is_recorded_and_reraised`
- `test_langchain_adapter.py::test_args_recorded_like_the_core`
- `test_reversibility.py::test_declarations_are_written_to_the_log_before_the_run`
- Throughout the demo and suite tests, which read outcomes from the log

**What it does not cover.**

- **The log is an ordinary file.** The harness only appends, and since 0.7.0 the hash chain (control 12) makes an edit detectable, but nothing prevents anyone with write access from editing or deleting it.
- **The log is sensitive data.** It can contain message text, addresses and other tool arguments and results.
- **There is no redaction option, only truncation.**
- No signing, encryption, rotation, retention or access control. Where the log is stored and who can read it is the deployer's responsibility.
- A process that crashes before `finalize()` leaves a log with no `run_end` entry, and its open calls are never marked incomplete.

## 8. Report

**What it does.** `render_report(log_path)` turns a log into a Markdown report organized around three questions:

1. What was the agent allowed to touch? The scope, tools, data sources, whether changes are allowed, each mutating tool's reversibility, and the argument rules.
2. What did it do? Every call in order, marked OK, VIOLATION or BLOCKED, with arguments, result and duration, plus a list of violations with reasons.
3. How can its actions be undone? The run's changes grouped by reversibility, worst first; changes not permitted by the scope are marked; blocked changes are listed as "nothing changed".

The report states the mode. If the counts in the run's summary disagree with the recorded calls, it ends with a warning. Multi-line text goes in fenced blocks so it cannot break the layout. The report is built only from the log, so the same log always gives the same report apart from what the log itself records (run id, timestamps, durations).

**Risk addressed.** Records that a non-engineer cannot read. The person accountable for an agent cannot answer basic questions about a run.

**Type.** Detective (review).

**How it is tested.**

- `test_core.py`: `test_three_questions_present`, `test_summary_and_report_agree_on_mixed_run`, `test_report_warns_when_summary_disagrees_with_log`
- `test_enforce.py::test_report_warns_when_blocked_count_disagrees`
- The question 1 and question 3 tests in `test_reversibility.py`
- `test_reversibility.py`: `test_multiline_demo_output_does_not_break_the_list`, `test_text_containing_a_fence_gets_a_longer_fence`
- `test_demo.py::test_core_and_adapter_reports_match`: the core and the adapter give the same report for every scenario and mode
- `test_demo.py::test_replay_is_deterministic_and_matches_the_sample`

**What it does not cover.**

- The report is only as complete and as honest as the log. An edited log produces a report of the edited log.
- It reports truncated arguments and results, not full ones.
- It does not judge whether an in-scope action was wise. "OK" means "passed the declared checks", not "correct".

## 9. Incomplete-call recording

**What it does.** At `finalize()`, any call that started but never ended or failed is recorded as an action with status `incomplete` and the result "INCOMPLETE: no result or error was recorded". It counts as a violation if it was out of scope. If the tool is mutating, it also writes a mutation entry with outcome `unknown`, because a change cannot be ruled out. A mutating call that raised is handled the same way at the time it fails (outcome `unknown`).

**Risk addressed.** A call that crashed partway through a change silently disappears from the record.

**Type.** Detective.

**How it is tested.**

- `test_reversibility.py`: `test_incomplete_in_scope_call`, `test_incomplete_out_of_scope_call_is_a_violation`, `test_incomplete_mutating_call_has_unknown_outcome`, `test_failed_mutation_keeps_unknown_outcome_and_declaration`
- `test_core.py::test_failed_mutating_call_is_recorded_as_unknown_change`

**What it does not cover.**

- It runs only if `finalize()` is called. If the process dies first, nothing marks the open calls.
- "Unknown" means the harness cannot tell. Someone has to check the outside system.

## 10. Governed scope

**What it does.** A scope can be written as a TOML file and loaded with `load_scope(path)`. Python-built scopes keep working. Either way, the scope can carry governance fields, all plain text:

- `owner`, `approver`, `approved_on`, `version`, `review_by` and `change_note`;
- a one-line `rationale` per allowed tool.

A file declares reversibility and argument rules too. Argument rules in a file can use only the built-in helpers by name (`email_domain_in`, `value_in`); a file that names anything else is rejected, and custom checks stay in Python.

When a run starts, the log records the full scope, including the governance fields, and a SHA-256 fingerprint of its canonical content. Any change to the scope, including its version or approver, gives a different fingerprint. The report shows the fingerprint and the governance fields in question 1, and lists governance findings in plain language:

- no approver;
- no owner;
- review date passed on the day of the run;
- a tool allowed without a rationale.

Findings are not errors: the run proceeds. A log from an older version says it did not record governance fields.

**Risk addressed.** An agent runs under a scope nobody approved, nobody owns, or nobody has reviewed in time, or a tool is allowed with no recorded reason. Afterward, nobody can say which version of the scope the agent ran under.

**Type.** Detective (documentation and reporting). Nothing is enforced: a run under an unapproved scope proceeds.

**How it is tested.**

- `test_governance.py`:
  - `test_a_scope_file_loads_every_field`, `test_a_scope_file_cannot_name_a_custom_check`
  - `test_python_built_scopes_still_work_and_custom_checks_are_labeled`, `test_demo_scope_files_load_with_complete_governance`
  - `test_fingerprint_is_written_to_the_log_and_identifies_the_version`, `test_findings_for_each_gap`
  - `test_a_log_from_an_older_version_says_so`, `test_an_unapproved_scope_still_runs_and_the_report_lists_findings`
- Demo scenario `unapproved` and `demo/sample-report-unapproved.md`
- The demo's scopes are TOML files in `demo/scopes/`

**What it does not cover.**

- **The fields are text.** The harness does not check who the owner or approver is, that approval happened, or that the date is true.
- The review check compares dates only on the day of the run. Nothing reminds anyone before a review falls due.
- The fingerprint identifies the content of a scope, not the code of its tools or the system prompt. The same fingerprint with a different prompt is possible, and is what the M4 experiments show.
- Custom Python checks are recorded as "custom Python check". Changing a custom check's code without changing its description does not change the fingerprint.

## 11. Change comparison

**What it does.** `compare(a_dir, b_dir)`, or `accountability-harness compare A B`, reads every audit log in two folders and writes a Markdown comparison. It is built from counts only: tool names, numbers and scope fingerprints, never arguments or results. It reports:

- the number of runs and the mean tool calls per run;
- each tool's share of calls, the runs using it, and its calls per run;
- changes per run by reversibility kind;
- violations, blocked and incomplete calls per run;
- tools used in only one set;
- the scope fingerprints seen in each set.

It flags a **material behavior change** when one of five documented rules fires. The thresholds are constants at the top of `compare.py` and are printed at the top of every comparison:

1. A mutating tool is used in a share of runs that differs by 25 percentage points or more.
2. A mutating tool's calls per run change by 50% or more, and by at least 0.5 calls per run.
3. A tool is used in one set and never in the other.
4. The two sets ran under different scope fingerprints.
5. Violations, blocked calls or incomplete calls per run rise from zero.

**Risk addressed.** A change to a prompt, a model or a scope changes what the agent actually does, and nobody notices because every individual run still looks in scope.

**Type.** Detective (review across runs). It is a heuristic.

**How it is tested.**

- `test_compare.py`:
  - `test_counts_per_run`, `test_the_calendar_hold_shift_fires_rules_1_and_2`
  - `test_no_rule_fires_for_the_same_behavior`, `test_a_small_volume_change_does_not_fire`
  - `test_a_new_scope_version_fires_rule_4`, `test_violations_and_blocks_rising_from_zero_fire_rule_5`
  - `test_output_has_counts_only_and_states_the_rules`, `test_an_empty_folder_is_an_error`
  - `test_the_committed_comparison_has_counts_only`
- `test_cli.py::test_compare`
- `experiments/COMPARE-neutral-vs-permissive.md`: on the M4 audit logs, rules 1 and 2 fire for the calendar hold (4 of 50 runs to 50 of 50) under the same scope fingerprint.

**What it does not cover.**

- **It is a heuristic.** The thresholds were chosen for this project, not derived. A real change below them is not flagged, and a flagged change may be harmless or intended.
- It does not explain a change or name its cause. The logs do not record the system prompt or the model, so a prompt change shows up only as behavior.
- It compares counts, not content. Two runs that call the same tools with very different arguments look the same.
- With small sets, differences can be noise. It reports no significance test.

## 12. Hash-chained audit log

**What it does.** Each log entry carries `prev_hash`, the SHA-256 of the previous entry, and `hash`, the SHA-256 of itself, both over its canonical JSON (sorted keys, no spaces). The first entry chains from a fixed value: 64 zeros (`GENESIS` in `audit.py`).

`verify(log)`, or `accountability-harness verify LOG`, reports one of three results:

- "intact", with the number of entries (exit code 0);
- the first line where the chain breaks (exit code 1);
- "not chained", for a log written before 0.7.0 (exit code 2).

The owner summary states the result.

**Risk addressed.** Someone edits the log after the run to hide or change what an agent did.

**Type.** Detective (tamper evidence). It does not prevent anything.

**How it is tested.**

- `test_chain.py`:
  - `test_intact_chain`, `test_an_edited_line_breaks_the_chain_at_that_line`
  - `test_a_deleted_line_breaks_the_chain_at_the_next_line`, `test_reordered_lines_break_the_chain`
  - `test_a_line_that_is_no_longer_json_breaks_the_chain`, `test_an_unchained_legacy_log_reports_not_chained`
  - `test_what_the_chain_cannot_detect_is_stated`
- `test_cli.py::test_verify_exit_codes`

**What it does not cover.**

- **It detects edits after the fact; it does not prevent them.**
- **Someone who rewrites the whole file and recomputes every hash defeats it,** unless the final hash was stored somewhere else beforehand. Lines cut from the end also leave a valid, shorter chain. The report says both.
- **Anchoring the final hash elsewhere** (a separate store, a signature, a timestamping service) **is out of scope.**
- There are no keys or signatures. The chain shows the file is internally consistent, not who wrote it.

## 13. Owner summary

**What it does.** Every report opens with a short section for the accountable owner, not the engineer, that fits on one screen:

- who owns and approved the scope, and its version;
- whether the scope is due for review or overdue;
- this run's changes, grouped irreversible first, with tool names;
- what needs attention: blocked actions, actions flagged as outside the scope, changes with no undo plan, and the number of governance findings;
- whether the log's hash chain verified;
- the command to re-create the report from the log.

**Risk addressed.** The person accountable for an agent gets a report written for engineers and cannot tell, quickly, whether anything needs their attention.

**Type.** Detective (review).

**How it is tested.**

- `test_owner_summary.py`:
  - `test_the_summary_comes_first_and_fits_one_screen`, `test_changes_are_grouped_irreversible_first`
  - `test_approval_review_and_attention`, `test_missing_approval_overdue_review_blocked_and_flagged`
  - `test_chain_status_and_how_to_recreate`
- All sample reports in `demo/`

**What it does not cover.**

- It summarizes the log and the declarations. "Nothing needs your attention" means nothing failed the declared checks, not that the run was safe.
- "Fits on one screen" is tested as at most eight lines; a long list of tool names can still make a line long.

---

## Integration support, as implemented

| Path | Sync tools | Async tools |
|---|---|---|
| `Harness.wrap` and `@harness.tool` | Supported and tested | **Not supported.** `wrap` calls the function directly and does not await it. Untested. |
| LangChain adapter (`AccountabilityHandler`) | Supported and tested, `invoke` with dict and tool-call inputs | Blocking in enforce mode is tested for `ainvoke` on a sync tool and on an async tool. Recording a completed async call is not covered by a test. |
| `start_call` / `end_call` / `fail_call` | Usable from any code; tested directly | Usable from async code, since the methods themselves are synchronous; not tested from async code |

The core package needs no third-party dependencies and Python 3.11 or later (for `tomllib`). It is tested to run with LangChain unavailable (`test_no_langchain.py`). The command line runs as `accountability-harness` once installed, or as `python -m accountability_harness`.

## Known limits in one list

- `allowed_data_sources` is recorded, not checked.
- The audit log is tamper-evident, not tamper-proof: a rewrite of the whole file with fresh hashes, or lines cut from the end, is not detected unless the final hash is kept elsewhere. It has no redaction option and holds sensitive data.
- The harness never undoes anything.
- Enforcement covers only calls that go through the harness.
- The LangChain path does not apply default values before argument rules.
- `wrap` does not support async functions.
- Enforce mode through LangChain is proven for `langchain-core` 1.6.12 only.
- No real-model run has exercised flagging or blocking (`experiments/RESULTS.md`).
- A scope, a reversibility declaration and a rule are only as good as the person who writes them. The governance fields are text: the harness does not check who the owner or approver really is.
- The change comparison is a heuristic over counts. It flags differences; it does not explain them.
