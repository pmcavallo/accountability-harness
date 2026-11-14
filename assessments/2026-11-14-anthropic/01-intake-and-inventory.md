## 0. Business request (fictional intake)

> The customer support team wants an AI assistant that reads incoming support tickets, summarizes each one, and drafts a reply for a human agent to approve before anything is sent. Volume is roughly 2,000 tickets a day. Tickets routinely contain customer names, email addresses, and order details. The team needs drafts good enough that agents edit rather than rewrite, a cost per ticket the support budget can carry, and a hard guarantee that ticket content is neither retained beyond the task nor used for training.

[Confirmed by Paulo at Block 1, Sat Nov 14, 2026, as written; he kept the brief unchanged because it is built on the role's job description. Everything below is judged against this brief.]

**Needs extracted from the brief:** (1) draft quality: edit-not-rewrite; (2) ticket content contains personal data: retention and training guarantees are gating; (3) approve-before-send control; (4) ~2,000 tickets/day volume; (5) cost per ticket must fit a support budget.

## 1. Inventory artifact (§4.1)

### Model entries

Model assignment decided by Paulo at Block 1, Sat Nov 14, 2026: two entries. Haiku 5.5 carries the high-volume summarization leg; Sonnet 5.5 carries the reply-drafting leg, where the edit-not-rewrite quality bar and the customer-facing risk sit. Fields that are identical across both entries are stated once in the shared block under the two tables.

**Entry A: summarization leg**

| Field | Entry |
|---|---|
| Provider | Anthropic |
| Model name + pinned version / snapshot date | Claude Haiku 5.5. Current generation is published under undated version-number names (pricing page, accessed Nov 13, 2026); no dated snapshot ID for this model appears on the pages opened. |
| Endpoint + region | Messages API (`/v1/messages`), Anthropic-operated platform. Global routing is the default; US-only inference available via `inference_geo: "us"` at a 1.1x price multiplier (pricing page). |
| Version selection (pinned / floating / provider-default) | Floating at the version number: no dated snapshot exists to pin for the current generation. Recorded as an inventory fact; it is scored under Dimension 1 in Section 2. |

**Entry B: reply-drafting leg**

| Field | Entry |
|---|---|
| Provider | Anthropic |
| Model name + pinned version / snapshot date | Claude Sonnet 5.5 (API string `claude-sonnet-5-5`, the replacement ID named on the deprecations page, accessed Nov 13, 2026). Undated version-number name, as with Entry A. |
| Endpoint + region | Messages API (`/v1/messages`), Anthropic-operated platform; routing as Entry A. |
| Version selection (pinned / floating / provider-default) | Floating at the version number, as Entry A. |

**Shared data-terms and change fields (both entries; sources accessed Fri Nov 13, 2026)**

| Field | Entry |
|---|---|
| Data terms: retention period | Standard arrangement, two unreconciled vendor formulations (gap G12): the retention docs page states conversation content "is not retained by default"; the Privacy Center commercial article states API inputs and outputs are deleted on the backend "within 30 days of receipt or generation." Neither model is a Covered Model (the 30-day-retention list is the Fable and Mythos lines), so the Covered Models exception does not apply to these entries. Zero data retention exists only as an arrangement requested through the sales team, enabled per organization (retention docs page); its terms are gap G9. Exceptions under any arrangement: trust-and-safety-flagged content may be retained up to 2 years; classification scores up to 7 years (Privacy Center article). |
| Data terms: inputs used for training? | No. Commercial Terms, Section B: "Anthropic may not train models on Customer Content from Services." Retention docs page: retained data is "never used for model training without your express permission." |
| Data terms: subprocessors (list location) | Published on the vendor's Trust Center. That site returned no extractable content on Nov 13, 2026, so the list's contents are not verified in this assessment (gap G1). |
| Data terms: residency | `inference_geo: "us"` documented on the pricing page (1.1x multiplier). No contractual residency guarantee established from the sources opened (gap G11). |
| Change-notification channel | Model retirements: email to impacted customers plus documentation, per the deprecations page, with a stated minimum of 60 days' notice for publicly released models. Behavior-affecting changes: recorded in the release notes on their effective dates; no advance-notice period stated (gap G8). Price changes: effective the earlier of 30 days after posting or customer notice (Commercial Terms, Section H.1). |
| Changelog location | Release notes overview, Claude Platform Docs (dated changelog, newest first); lifecycle state and retirement dates on the model deprecations page. |

### Dependency entries
| Component | Version | License | Role in execution path | Permissions held | Provenance / maintainer |
|---|---|---|---|---|---|
| Claude API, Messages API (`/v1/messages`) | API versioned separately from models (current version line includes `2026-10-21`, which removed non-default `temperature`/`top_p`/`top_k` values) | Commercial service, Anthropic Commercial Terms | Sole model dependency for both task legs: every ticket summary and every reply draft is produced through this endpoint | Receives full ticket content, including customer names, email addresses, and order details, on every call | Anthropic |
| Prompt caching (Messages API feature) | n/a | Commercial service feature | Optional in this design; not required by either leg. Recorded because its retention behavior differs from the base call: key/value representations are held in memory for the cache TTL only, and the feature is ZDR-eligible (retention docs page) | Same content as the calls it accelerates | Anthropic |
| Batch API | n/a | Commercial service feature | NOT in the execution path as inventoried. Recorded as an excluded component: it carries a 50% price discount but is not ZDR-eligible and carries 29-day retention (retention docs page). Whether cost pressure reopens this exclusion is a Gate 2 decision (Section 4), not an inventory assumption | Would receive the same ticket content if adopted | Anthropic |
| Customer's ticketing system and agent review UI | Customer's own, outside this assessment's scope | Customer's own | System of record for tickets; hosts the approve-before-send control (a human agent approves every draft before anything is sent). The control lives on the customer's side, not in the vendor's product | Holds the ticket content at rest; the vendor receives content only through the API calls above | The customer's organization |

### Provenance notes
- Single-provider concentration: both legs depend on one vendor and one endpoint. If the Claude API is withdrawn or either model is retired, both legs stop; the deprecations page documents no automatic rerouting of a retired model ID to its named replacement, and requests to a retired model fail, so migration is the customer's work on the vendor's notice clock (stated minimum 60 days for publicly released models).
- API behavior is a dependency of its own: API versions change independently of models (the `2026-10-21` version removed sampling parameters), so the integration code, not only the model choice, sits inside the change-event perimeter of Section 3.
- The approve-before-send control is the customer's component. Nothing in the vendor's documented offering supplies it; if the customer's review UI fails or is bypassed, no vendor-side control in the sources opened prevents a draft from being sent.

