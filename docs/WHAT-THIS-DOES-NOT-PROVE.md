# What This Does Not Prove

The harness and its experiments are evidence of a small set of controls, built and tested honestly. They are not evidence of more than that. Read this before citing anything from this project.

**One model, one synthetic scenario, small n.** The real-model results come from Claude Haiku 5.5 on one fictional inbox, with five hand-written injection emails and two system prompts: 100 runs, on one date. They say nothing reliable about other models, other tasks, stronger attacks, or rare failures. Zero attempts in 100 runs does not mean the true rate is zero.

**A live demo run is one run.** The app's local live mode shows the harness around one real model on one run, with one of two prompts. Whatever that run does, it is not evidence about other models, other prompts or other runs of the same model.

**No real-model run exercised flagging or blocking.** The model never attempted the outside send, under either prompt. So the 100 real runs show what the model did, and that the harness recorded and classified it. They do not show the harness catching or stopping a real model.

**Flag and block behavior is shown by scripted scenarios and tests.** The `violation`, `mutation`, `enforce`, `argument` and `argument enforce` demo scenarios, and the offline test suite, show that out-of-scope calls are flagged in observe mode and never run in enforce mode. These are scripted calls, not a model choosing to make them.

**The audit log is tamper-evident, not tamper-proof.** Since 0.7.0 each entry is hash-chained to the one before, so an edited, deleted or reordered line is detected. Nothing stops anyone with write access from changing the file, and a rewrite of the whole file with fresh hashes, or lines cut from the end, goes undetected unless the final hash was stored somewhere else. That anchoring is out of scope. The chain has no signatures, so it does not show who wrote the log.

**The harness does not undo anything.** It records how each change can be undone, as declared before the run. It does not check that the declared undo works, and it never performs it.

**Enforcement only covers calls that go through the harness.** A tool the agent can reach any other way is neither recorded nor blocked. Code that catches the block and runs the tool anyway defeats it.

**A scope is only as good as the person who writes it.** The harness checks calls against the declared tools, change permission and argument rules. If a dangerous tool is allowed, or a rule is too loose, or a mutating tool is not declared as one, the harness reports the run as in scope. "OK" in the report means "passed the declared checks", not "safe" or "correct".

**An approved scope is a recorded claim, not a verified approval.** The owner, approver, dates and reasons in a scope file are text. The harness reports when they are missing or a review is overdue; it does not check that any of them is true, and it never stops a run because of them.

**The change comparison is a heuristic.** Its five rules and thresholds were chosen for this project. It flags differences in counts between two sets of runs; it does not explain them, test their significance, or see differences in arguments or content. A change below its thresholds is not flagged. The one real comparison in this repository (`experiments/COMPARE-neutral-vs-permissive.md`) covers one model, one scenario and two prompts.

**It does not detect prompt injection.** It checks what the agent does, not why. An injection that leads only to in-scope actions passes unflagged.

**It does not check data access.** `allowed_data_sources` is recorded and reported but never checked.

**It is not a compliance claim.** `docs/FRAMEWORK-MAPPING.md` shows which framework clauses the controls relate to. It is illustrative; its citations were checked against the primary sources on 2026-10-21. Using this harness does not make a system compliant with any framework or law.
