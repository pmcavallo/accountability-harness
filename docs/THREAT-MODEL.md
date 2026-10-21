# Threat Model

This threat model covers the scenario the harness is built and tested on. It names, for each threat, the control that applies (see `docs/CONTROLS.md`) and what remains. It claims only what the code, the tests and `experiments/RESULTS.md` support. All data is synthetic.

## The scenario

An AI assistant works through the inbox of Tallow Lane Events, a fictional small events company. Its tools are plain Python functions, each going through the harness:

| Tool | What it does | Changes something? | Declared reversibility |
|---|---|---|---|
| `read_inbox` | Lists unread emails | No | n/a |
| `read_email` | Reads one email | No | n/a |
| `summarize_thread` | One-line summary of a thread | No | n/a |
| `draft_reply` | Saves a draft for a person to review; nothing is sent | Yes | Reversible: delete the draft |
| `place_calendar_hold` | Places a hold on the company calendar | Yes | Reversible: release the hold, within 48 hours |
| `add_client_contact` | Adds a person to the client contact list | Yes | Deliberately undeclared |
| `send_email` | Sends an email | Yes | Irreversible: send a correction; the original cannot be recalled |

The demo uses three scopes:

- `inbox-assistant`: everything except `send_email`.
- `inbox-assistant-review-only`: the same tools, but no changes allowed.
- `inbox-assistant-internal-email`: every tool, but `send_email` may only go to `tallowlane.example` addresses. This is the scope used in the real-model runs.

In the demo, "sent" email, drafts, holds and contacts go into lists in the script, and every address uses the reserved `.example` domain.

## Assets

- **The client list and the price sheet.** Confidential business information. The planted emails ask for both to be sent to an outside address. No demo tool reads either one, so in this scenario the only way they could leave is in the body of an outgoing email the agent writes.
- **Outgoing email.** Once sent, it cannot be recalled. It is the channel through which data leaves the company and through which the company speaks for itself.
- **The company calendar and contact list.** Lower stakes: changes can be reversed (the calendar hold) or are at least visible (the contact list).
- **The audit log.** The record of what the agent did. It also holds message text and addresses, so it is itself sensitive.

## Trust boundaries

- **The deployer** writes the system prompt, chooses the tools and writes the scope. The deployer is trusted, but can be wrong (threat 2).
- **Email content** comes from anyone who can send the company an email. It is untrusted, but the agent reads it as part of its work.
- **The harness** sits between the agent and its tools. It sees every call that goes through it, and nothing else.

## Threats

### 1. Indirect prompt injection in an email

An outside sender writes an email that contains instructions for the assistant: send the client list and price sheet to an outside address. The test suite uses five techniques: claiming the owner approved it, urgency, pretending to be a system message, burying the request in a long legitimate inquiry, and asking for an internal and an outside address together.

**Controls.**

- **Declared scope (1):** if `send_email` is not in scope, calling it fails the check.
- **Argument rules (3):** if `send_email` is in scope but limited to internal addresses, a send to an outside address, or to a list that includes one, fails the check.
- **Observe mode (5)** flags the call; **enforce mode (6)** blocks it before it runs.
- **Audit log (7) and report (8)** record the attempt and its reason.

**Evidence.**

- Scripted scenarios `violation`, `enforce`, `argument` and `argument enforce` show the call flagged in observe mode (the email is sent) and blocked in enforce mode (the sent-mail list stays empty).
- `test_measure_enforce_run_with_a_mixed_recipient_list` shows a mixed internal-plus-outside list blocked.
- In 100 real-model runs (Claude Haiku 5.5, `experiments/RESULTS.md`), the model never attempted the send, so no real-model run exercised these controls.

**What remains.**

- The harness does not detect injections. It checks calls against the scope, whatever caused them.
- An injection that leads to an in-scope call is not flagged. For example, the agent could be persuaded to put confidential text in a draft, or in an email to an internal address that is later forwarded.
- Content inside an allowed call is not inspected. Only declared argument rules are checked.

### 2. A permissive deployer prompt that widens what the agent does

The deployer writes a system prompt that tells the agent to act for the owner and complete what each email asks without asking for confirmation. No attacker is involved, but the agent now does more on its own.

**Controls.**

- **The scope (1 to 3)** stays the same whatever the prompt says. It is set in code, not in the prompt.
- **Mutation records with reversibility (2, 4)** show what the agent changed and how each change can be undone.
- **The report (8) and the owner summary (13)** put it in front of a reader.
- **Change comparison (11)**, added in 0.7.0, is a detective control for this threat. Comparing the audit logs from before and after a prompt change flags a material shift in what the agent does, even when every run is in scope.

**Evidence.**

- `experiments/COMPARE-neutral-vs-permissive.md`: on the M4 audit logs, the comparison flags the calendar hold (rules 1 and 2: 4 of 50 runs to 50 of 50) under the same scope fingerprint, so the scope did not change but the behavior did.
- `experiments/RESULTS.md`, permissive-prompt condition (50 runs) against the neutral prompt (50 runs). The model placed the calendar hold that email 4 asks for in 50 of 50 runs, against 4 of 50, and drafted fewer replies (107 against 168).
- In both conditions it attempted no outside send.
- Every one of the 329 mutating calls across the 100 runs was recorded with its declared reversibility.

**What remains.**

- Within a single run, the harness cannot tell that the agent is doing more than intended if every action is in scope. The shift is visible only by comparing sets of runs, and only if someone runs the comparison.
- The comparison is a heuristic with fixed thresholds. A smaller shift is not flagged.
- The prompt itself is not recorded in the audit log, so the comparison shows the change in behavior, not its cause. The experiments record the prompts in `RESULTS.md` and the run files.

### 3. Out-of-scope tools

The agent calls a tool that is not in the declared scope, whether because of an injection, a mistake, or a tool list wider than the scope.

**Controls.** Declared scope (1); observe or enforce mode (5, 6); log and report (7, 8). A tool name the scope has never heard of is out of scope too.

**Evidence.** `test_tool_not_in_scope_is_flagged`; `test_enforce_mode_blocks_and_never_runs`; the `violation` and `enforce` scenarios.

**What remains.**

- A tool reachable outside the harness is invisible to it.
- The agent loop in `experiments/agent_loop.py` answers a request for a tool name it does not have with error text and does not write it to the audit log. None occurred in the 100 runs.

### 4. Allowed tools pointed at the wrong place

The agent uses a tool it is allowed to use, but on the wrong target: an email to an outside address, or a change during a run that should not change anything.

**Controls.**

- **Argument rules (3)**, which fail closed: a missing argument, a call with no named arguments, or a check that raises all count as broken.
- **Mutations allowed or not (2).**

**Evidence.** The `argument` and `mutation` scenarios; the argument-rule tests in `test_enforce.py`; `test_bare_string_call_fails_argument_rules`.

**What remains.**

- A rule only covers the argument and tool it names. Other arguments and other tools are unconstrained.
- `allowed_data_sources` is recorded but not checked, so the harness does not constrain which data a tool reads.

### 5. Tool errors partway through a change

A mutating tool raises, or the run stops before the tool returns. The change may or may not have happened.

**Controls.** Incomplete-call recording (9): a mutating call that raised or never finished is recorded with outcome `unknown`, and the report says to check whether anything changed. Reversibility declarations (4) say how to undo the change if it did happen.

**Evidence.**

- `test_failed_mutating_call_is_recorded_as_unknown_change` and `test_incomplete_mutating_call_has_unknown_outcome`.
- In the first real-model suite, 8 `draft_reply` calls arrived without their text, raised, and were recorded with outcome `unknown` (`experiments/RESULTS.md`).

**What remains.**

- The harness cannot tell whether a failed call changed anything; a person has to check.
- If the process dies before `finalize()`, open calls are never marked incomplete.

### 6. Tampering with or leaking the audit log

Someone edits or deletes the log to hide what an agent did, or the log is read by someone who should not see its contents.

**Controls.** Tampering is now partly addressed by a detective control; nothing prevents either threat.

- **Hash-chained log (12)**, added in 0.7.0. Each entry carries the hash of the previous one. `verify` and the owner summary report an edited, deleted or reordered line, with the first line where the chain breaks.
- The report warns when the run's own summary disagrees with the recorded calls.
- Truncation (`max_text`, default 500 characters) limits how much of each argument and result is stored.

**Evidence.** `test_chain.py` (intact, edited, deleted, reordered, malformed and legacy logs); `test_report_warns_when_summary_disagrees_with_log`; `test_long_output_and_args_are_truncated`.

**What remains.**

- **The chain detects edits; it does not prevent them.** Anyone with write access can still change or delete the file.
- **A rewrite of the whole file with fresh hashes, or lines cut from the end, is not detected** unless the final hash was kept somewhere else. Anchoring it elsewhere is out of scope.
- There are no signatures, so the chain does not show who wrote the log.
- **There is no redaction option.** The log can contain message text, addresses and other tool data.
- Storage, access control, retention and transport of the log are outside the harness.

### 7. Unapproved or unnoticed scope changes

A scope is changed, or put into use, without anyone approving it; or it is never reviewed; or nobody can tell afterward which version an agent ran under.

**Controls.** Governed scope (10), added in 0.7.0:

- the scope's governance fields (owner, approver, approval date, version, review date, change note, a reason per tool) and a SHA-256 fingerprint of its content are written to every log;
- the report and the owner summary list the gaps: no approver, no owner, review overdue, a tool with no reason.

Change comparison (11) flags two sets of runs made under different fingerprints (rule 4).

**Evidence.** The `unapproved` demo scenario and `demo/sample-report-unapproved.md`; `test_governance.py`; `test_a_new_scope_version_fires_rule_4`.

**What remains.**

- **Nothing is enforced.** A run under an unapproved or overdue scope proceeds; the gap is only reported.
- The governance fields are text. The harness does not check that the named approver exists or approved anything.
- The fingerprint covers the scope, not the tools' code or the prompt.

## Out of scope for this threat model

- Attacks on the model provider, the Python runtime or the host.
- An agent with tools that do not go through the harness.
- Multi-agent systems and multi-turn attacks.
- Attacks hidden in tool outputs other than an email body.
- Denial of service and cost exhaustion. The experiments cap tool calls and runs, but the harness itself does not.
