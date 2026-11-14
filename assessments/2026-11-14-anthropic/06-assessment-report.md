## 6. Assessment report (§5, Module C scope)

### Assessor independence disclosure
- This assessment was prepared with tooling that runs on the assessed provider, and the assessor's own systems depend on that provider. Included unprompted.

### Recommendation (REQUIRED, one line — stands even if the decision memo slips)
- **Conditional go** to pilot, subject to: (1) the POC in §5 clearing its pre-registered go threshold on redacted tickets, and (2) a written zero-retention arrangement with the vendor and a completed privacy impact assessment before any live ticket data is processed. Continuing condition: a standing release-notes and status watch, with any behavior-affecting change reopening validation under §4.3, because the inventoried models cannot be pinned to dated snapshots. Ruled by Paulo, Sat Nov 14, 2026.

### Findings, ordered by severity
1. **The intake's hard guarantee cannot be satisfied from public documentation.** The published retention default is stated two ways (gap G12), zero-retention terms are not published and are arranged per organization through the sales team (gap G9), and flagged content may be retained up to 2 years and classification scores up to 7 years under any arrangement (retention documentation; §2 row 2, §4 fit row 2). It closes only in contracting, and it gates the pilot (§5).
2. **No documented availability commitment stands behind a live incident record.** No uptime SLA, service-credit schedule, or support response-time commitment appears in any source opened (gaps G3, G7), while the vendor's own status record shows two API-affecting incidents in the assessment week, including a partial API outage of about two and a half hours on Nov 13, 2026 (status page snapshots, Nov 13-14, 2026; §2 row 6). This is the chain's weakest link; the score is 2.
3. **The inventoried models cannot be pinned, and behavior changes arrive without advance notice.** The current generation ships under floating version-number IDs; dated snapshots exist only for older generations (deprecations and release-notes pages; §2 row 1). No opened source states an advance-notice period for behavior-affecting changes (gap G8). The compensating control is procedural: release-notes monitoring with §4.3 revalidation, written into the POC plan (§5) and the recommendation's continuing condition.
4. **Exit is cheap to execute and hard to document.** The customer owns its inputs and outputs (Commercial Terms, Section B) and the design holds no vendor-side state, so switching is a re-pointing exercise; but no export mechanism for prompts, outputs, or audit logs is established (gap G6), no post-termination deletion certification is documented, and the terms' termination notice period was not established (gap G5) (§2 row 5).
5. **Vendor-level finding (different product, labeled as such): a privacy defect in the vendor's coding product was customer-detected, and the fix's completeness is contested on the vendor's own tracker.** Event A (§3) remains open. It evidences the vendor's detection and disclosure behavior; it does not score against the API's posture.
6. **Two evidence surfaces could not be read at all.** The vendor's Trust Center, including its sub-processor list, returned no extractable content (gap G1), and no security certification claims (SOC 2, ISO 27001) appear in any readable primary source (gap G2). Both attach to the Legal/Privacy handoff (§4); neither blocks the POC, which runs on redacted data.

### Change events since previous assessment
- First assessment; no previous assessment exists. Baseline established Sat Nov 14, 2026. Two change events were worked as case studies in §3: a model retirement, closed by evidence, and a vendor-level product incident, still open.

### Residual-risk statement
- Not tested: model behavior on the customer's ticket corpus (the §5 POC exists to test it and has not run); the DPA's contents (gap G5); the Trust Center and sub-processor list (gap G1); zero-retention terms as they would appear in a signed arrangement (gap G9). Resting on vendor self-description: every evaluation result behind Dimension 3 (the system cards and the Transparency Hub are the vendor's own publications), and the incident accounts behind Dimension 6 (the vendor's status page). Not examined: partner-operated platforms (Amazon Bedrock, Google-managed), the vendor's consumer and coding products as products in their own right (touched only as vendor-level evidence in Event A, §3), and the vendor's internal security controls beyond published claims.

### Sign-off
- Assessor: Paulo Cavallo · System owner: Support Operations (intake role) · Date: Sat Nov 14, 2026 · Review-by: Dec 14, 2026

