# Framework Mapping

Citations checked against primary sources on 2026-10-21.

**This mapping is illustrative, not a compliance claim.** It shows which parts of three widely used frameworks the harness's controls relate to, to help a reader place the controls. "Relates to" means the control produces evidence or behavior relevant to the clause. It does not mean the control satisfies the clause, and using the harness does not make any system compliant with any framework or law. Several of the EU AI Act provisions cited here apply only to systems classified as high-risk under that Act, and those requirements apply only from the postponed dates given in V14 (2 December 2027 for Annex III systems, 2 August 2028 for Annex I systems). Whether a given deployment is high-risk is a separate question that this project does not answer. The controls themselves are described in `docs/CONTROLS.md`, and their limits in `docs/WHAT-THIS-DOES-NOT-PROVE.md`.

**Sources.** NIST AI RMF 1.0 and NIST AI 600-1, from NIST's publication pages. The EU AI Act wording was read per the European Commission's consolidated text, as reproduced on the Commission's AI Act Service Desk as at 27 July 2026; the number and entry into force of the amending Regulation (EU) 2026/1744 were checked on EUR-Lex. OWASP entries were read on the OWASP GenAI Security Project pages. Each citation's URL is given with it.

## Citations

Each citation has an ID used in the mapping tables. V13 was removed after verification: no suggested action in NIST AI 600-1 covers limiting the permissions or access of a tool-connected system, and V21 and V22 cover that point. V23 is not a framework citation. It is a packaging fact (setuptools 77.0.0 is the first release to accept a plain SPDX string for `license`, and it deprecates the table form), verified the same day and applied in `pyproject.toml` by keeping the table form of `license` with `setuptools>=61`. Source: https://raw.githubusercontent.com/pypa/setuptools/main/NEWS.rst

### NIST AI Risk Management Framework (AI RMF 1.0)

Source for V1 to V9 and V24 to V26: https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=936225

| ID | Identifier | Paraphrase |
|---|---|---|
| V1 | AI RMF 1.0, GOVERN 1 (category); GOVERN 1.4 | GOVERN 1: policies, processes, procedures and practices for mapping, measuring and managing AI risk are in place, transparent and implemented effectively. GOVERN 1.4: the risk management process and its outcomes are established through transparent policies, procedures and other controls based on organizational risk priorities. |
| V2 | AI RMF 1.0, GOVERN 2.1 | Roles and responsibilities and lines of communication related to mapping, measuring and managing AI risks are documented and clear (accountability is the theme of the GOVERN 2 category). |
| V3 | AI RMF 1.0, MAP 1.1; MAP 2.1 | MAP 1.1: intended purposes, uses, context-specific laws and norms, and deployment settings are understood and documented. MAP 2.1: the specific tasks and methods the system uses to support them are defined. |
| V4 | AI RMF 1.0, MAP 2.2 (see also MAP 3.5) | The system's knowledge limits and how its output may be used and overseen by humans are documented. |
| V5 | AI RMF 1.0, MEASURE 2.4 | The functionality and behavior of the AI system and its components are monitored when in production. |
| V6 | AI RMF 1.0, MEASURE 2.1; MEASURE 2.5 | MEASURE 2.1: test sets, metrics and details of the tools used during test, evaluation, verification and validation are documented. MEASURE 2.5: limits of generalizability beyond the conditions the system was developed under are documented. |
| V7 | AI RMF 1.0, MANAGE 2.4 | Mechanisms with assigned responsibilities are in place to supersede, disengage or deactivate AI systems whose performance or outcomes are inconsistent with intended use. |
| V8 | AI RMF 1.0, MANAGE 4.3 (with MANAGE 4.1; category MANAGE 4) | Incidents and errors are communicated to relevant AI actors, and processes for tracking, responding to and recovering from them are followed and documented. |
| V9 | AI RMF 1.0, section 3.4, "Accountable and Transparent" | The trustworthiness characteristic on accountability and transparency. |
| V24 | AI RMF 1.0, GOVERN 1.5 | Ongoing monitoring and periodic review of the risk management process and its outcomes are planned, with organizational roles and responsibilities clearly defined, including how often reviews happen. |
| V25 | AI RMF 1.0, GOVERN 1.6 | Mechanisms are in place to inventory AI systems, resourced according to organizational risk priorities. |
| V26 | AI RMF 1.0, MANAGE 4.1 | Post-deployment monitoring plans are implemented, including mechanisms for capturing and evaluating input from users and other relevant AI actors, appeal and override, decommissioning, incident response, recovery and change management. |

### NIST AI 600-1, Generative AI Profile

Source for V10 to V12: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf

| ID | Identifier | Paraphrase |
|---|---|---|
| V10 | NIST AI 600-1 (July 2024) | "Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile". |
| V11 | NIST AI 600-1, "Information Security" risk (section 2.9) | One of the 12 GAI risks; section 2.9 names direct and indirect prompt injection as attacks on GAI systems. |
| V12 | NIST AI 600-1, MG-4.1-002; MG-4.3-002 | MG-4.1-002: establish and evaluate processes for post-deployment monitoring of GAI systems. MG-4.3-002: establish policies and procedures to record and track reported GAI errors, near-misses and negative impacts. |

### EU AI Act

| ID | Identifier | Paraphrase | Source |
|---|---|---|---|
| V14 | Regulation (EU) 2024/1689 (Artificial Intelligence Act); Article 6(1) with Annex I, Article 6(2) with Annex III; Article 113 as amended by Regulation (EU) 2026/1744 | High-risk systems are defined in Article 6 (safety components or products under the Annex I legislation, and the Annex III use cases). As amended by the Digital Omnibus on AI (Regulation (EU) 2026/1744, in force 27 July 2026), the high-risk requirements apply from 2 December 2027 for Annex III systems and 2 August 2028 for Annex I systems, per the Commission's consolidated text. | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-113 ; https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-6 ; https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744 |
| V15 | Article 12(1) | High-risk AI systems must technically allow the automatic recording of events (logs) over the lifetime of the system. | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-12 |
| V16 | Article 26(6) | Deployers keep the automatically generated logs under their control for a period appropriate to the intended purpose, of at least six months, unless other Union or national law provides otherwise. | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-26 |
| V17 | Article 14(4), points (a), (d), (e) | Overseers must be enabled to understand the system's capacities and limits and monitor its operation; to decide not to use it or to disregard, override or reverse its output; and to intervene or interrupt it. | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-14 |
| V18 | Article 11(1); Annex IV | Providers draw up technical documentation before the system is placed on the market or put into service and keep it up to date; Annex IV lists its minimum contents. | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-11 |
| V19 | Article 13 (in particular 13(3)(b)) | High-risk systems must be transparent enough for deployers to interpret their output and come with instructions for use covering, among other things, their characteristics, capabilities and limitations of performance. | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-13 |
| V27 | Article 17 ("Quality management system") | Providers of high-risk AI systems put in place a quality management system documented in written policies, procedures and instructions; as originally adopted, it includes procedures for managing modifications to the system (point (a) of paragraph 1) and record-keeping of relevant documentation (point (k)). The Commission's consolidated text notes that Article 17 has been amended by the Digital Omnibus on AI and that page has not yet been updated, so the point letters refer to the text as originally adopted. | https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-17 |

### OWASP Top 10 for LLM Applications

| ID | Identifier | Paraphrase | Source |
|---|---|---|---|
| V20 | OWASP Top 10 for LLM Applications 2025 | The current edition (entries LLM01:2025 to LLM10:2025). | https://genai.owasp.org/llm-top-10/ |
| V21 | LLM01:2025 Prompt Injection | Covers direct and indirect prompt injection (instructions carried in external content); mitigations include enforcing privilege control and least privilege access, and requiring human approval for high-risk actions. | https://genai.owasp.org/llmrisk/llm01-prompt-injection/ |
| V22 | LLM06:2025 Excessive Agency | Root causes: excessive functionality, excessive permissions and excessive autonomy; mitigations include minimizing extensions, their functionality and permissions, requiring user approval, and complete mediation. | https://genai.owasp.org/llmrisk/llm062025-excessive-agency/ |

## Mapping

| Control (`docs/CONTROLS.md`) | Relates to | How it relates | What it does not cover |
|---|---|---|---|
| 1. Declared scope (tool names) | V1, V3, V21, V22 | The permitted tools are written down before the run, and every call is checked against that list. This limits functionality to what was declared. | Calls outside the harness; what a permitted tool actually does; data access (`allowed_data_sources` is not checked) |
| 2. Mutations allowed or not | V3, V22 | A run can be declared read-only, so any change counts as out of scope. This limits autonomy to what the run is for. | Tools the developer fails to declare as mutating |
| 3. Argument rules (fail closed) | V21, V22 | Limits where a permitted tool can act, for example email recipients restricted to an internal domain. A rule that cannot be checked counts as broken. | Arguments and tools without rules; message content; no policy language |
| 4. Reversibility declarations | V4, V8, V9, V18 | How each change can be undone, and for how long, is documented before the run and reported after it, as input to recovery. | The harness never undoes anything and does not test the declared undo |
| 5. Observe mode | V5, V12, V17 | Records and flags out-of-scope calls during operation without stopping them, so a person can monitor the system. | Does not stop anything; an irreversible action has already happened |
| 6. Enforce mode | V7, V17, V21, V22 | Blocks out-of-scope calls before they run, a technical means to stop an action the declared scope does not allow. | Only calls through the harness; can be defeated by integration code that ignores the block; no real-model run was blocked |
| 7. Audit log | V5, V9, V12, V15, V16 | Automatic recording of every call, its result, its scope verdict and each change, in one file per run. | Edits are detectable only through control 12, and not prevented; no redaction; no retention or access control; storage is the deployer's job |
| 8. Report | V2, V9, V17, V19 | Presents each run to a non-engineer as three questions (allowed, done, undoable), so the accountable person can understand and review it. | Only as complete and honest as the log; "OK" means passed the declared checks |
| 9. Incomplete-call recording | V8, V15 | Calls that failed or never finished are recorded, and changes with an unknown outcome are flagged for checking. | Only if `finalize()` runs |
| 10. Governed scope | V1, V2, V18, V24, V25, V27 | The scope is a versioned document with an owner, an approver, an approval date, a review date, a change note and a reason per tool. Every run records which version it ran under (a fingerprint), and the report lists missing approval, missing ownership, overdue review and unexplained tools. | The fields are text and are not verified; nothing is enforced; the fingerprint does not cover tool code or the prompt |
| 11. Change comparison | V5, V12, V26, V27 | Compares what the agent did across two sets of runs, for example before and after a prompt or scope change, and flags material behavior changes by documented rules. | A heuristic over counts with fixed thresholds; it does not explain causes or test significance |
| 12. Hash-chained audit log | V9, V15, V16 | Makes after-the-fact edits, deletions and reordering of log entries detectable, which supports relying on the record later. | Detects, does not prevent; a full rewrite or lines cut from the end go undetected unless the final hash is kept elsewhere; no signatures |
| 13. Owner summary | V2, V9, V17, V19 | Puts the approval status, the review status, the run's changes by reversibility, what needs attention and the log's integrity in front of the accountable person, on one screen. | Summarizes the declared checks only; "nothing needs attention" does not mean safe |
| Experiments and their limits (`experiments/RESULTS.md`, `docs/WHAT-THIS-DOES-NOT-PROVE.md`) | V6, V11, V21 | Evaluation of a real model against five indirect prompt injection techniques, with results and limits documented. | One model, one scenario, 100 runs; no real-model run exercised flagging or blocking |
