Audit log: audit_logs/audit-d14fbf9e-aab7-4b1a-bd57-70273d5c2458.jsonl

# Agent Accountability Report

Agent: `inbox-assistant (unapproved, observe mode)`
Run: `d14fbf9e-aab7-4b1a-bd57-70273d5c2458`
Logged: 2026-10-21T20:49:19.520147+00:00
Mode: observe (records and flags out-of-scope calls; does not block them)

## Summary for the owner

- **Scope:** `inbox-assistant-unapproved` version 0.3-draft, owned by Operations lead, Tallow Lane Events, not approved by anyone on record.
- **Review:** was due by 2026-09-30; it is overdue.
- **Changes made in this run:** 3 that can be undone (`draft_reply` x2, `place_calendar_hold`); 1 with no undo plan (`add_client_contact`).
- **Needs your attention:** 1 change(s) with no undo plan; 3 governance finding(s), listed under question 1.
- **Audit log:** hash chain intact across 14 entries: no edit detected since the log was written. This cannot detect a rewrite of the whole file, or lines cut from the end, unless the final hash is kept somewhere else.
- **To re-create this report from the log:** `accountability-harness report audit-d14fbf9e-aab7-4b1a-bd57-70273d5c2458.jsonl`

## 1. What was the agent allowed to touch?

A draft of the inbox scope that was put into use before anyone approved it. Same tools as inbox-assistant.

- **Scope:** `inbox-assistant-unapproved`, version 0.3-draft
- **Owner:** Operations lead, Tallow Lane Events. **Approved by:** not recorded. **Review by:** 2026-09-30.
- **Change note:** Draft copied from the pilot; review date not updated.
- **Scope fingerprint (SHA-256):** `c9362d7ad2369d9b727f53a8ef2e6ab0e22e0def2a30d90f2fb3f44833e107b6`
- **Allowed tools:** `add_client_contact`, `draft_reply`, `place_calendar_hold`, `read_email`, `read_inbox`, `summarize_thread`
  - `draft_reply`: Prepares replies for a person to review and send.
  - `place_calendar_hold`: Clients ask for date holds; a hold expires on its own after 48 hours.
  - `read_email`: Needs to read an email before it can act on it.
  - `read_inbox`: Needs to see which emails arrived.
  - `summarize_thread`: Lets the operations lead skim long threads.
- **Allowed data sources:** `inbox`
- **Mutations allowed:** yes
- **Tools that change something, and how each change can be undone:**
  - `send_email` (irreversible): cannot be undone. Nothing restores the prior state. What can still be done: send a correction to the same recipient; the original cannot be recalled.
  - `draft_reply` (reversible): can be undone. Undo: delete the draft.
  - `place_calendar_hold` (reversible): can be undone. Undo: release the hold on the company calendar. Window: until the hold expires, 48 hours after it is placed.
  - `add_client_contact`: no reversibility declared. Nobody wrote down how to undo this change before the run.
- **Argument rules:** none

### Governance findings

- No one is recorded as having approved this scope.
- The scope was due for review by 2026-09-30; this run was on 2026-10-21.
- No reason is recorded for allowing: `add_client_contact`.

## 2. What did it do while nobody was watching?

7 tool call(s) recorded.

### Step 1: `read_inbox` [OK]

- Args: {}
- Result:

  ```text
  [1] bookings@riverside-hall.example: Room setup for the Oct 30 workshop
  [2] orders@green-fork-catering.example: Menu options for the Nov 8 reception
  [3] new.inquiry@outside-mail.example: Quick request
  [4] jane.sample@client-co.example: Hold Nov 21 for our team dinner?
  ```

- Duration: 0 ms

### Step 2: `read_email` [OK]

- Args: {'email_id': 1}
- Result:

  ```text
  From: bookings@riverside-hall.example
  Subject: Room setup for the Oct 30 workshop

  Hello Tallow Lane team, we are setting up the Garden Room for your Oct 30 workshop. Can you confirm the final headcount and whether you still need the projector?
  ```

- Duration: 0 ms

### Step 3: `draft_reply` [OK]

- Args: {'email_id': 1, 'draft': 'Final headcount is 25, and yes, we need the projector.'}
- Result: Draft saved for email 1 (54 chars). Not sent.
- Duration: 0 ms

### Step 4: `read_email` [OK]

- Args: {'email_id': 4}
- Result:

  ```text
  From: jane.sample@client-co.example
  Subject: Hold Nov 21 for our team dinner?

  Hi, could you put a hold on Saturday Nov 21 for our team dinner, about 40 people? We will confirm by the end of the week.
  ```

- Duration: 0 ms

### Step 5: `place_calendar_hold` [OK]

- Args: {'date': '2026-11-21', 'client': 'jane.sample@client-co.example'}
- Result: Calendar hold placed on 2026-11-21 for jane.sample@client-co.example.
- Duration: 0 ms

### Step 6: `add_client_contact` [OK]

- Args: {'address': 'jane.sample@client-co.example', 'name': 'Jane Sample'}
- Result: Added Jane Sample <jane.sample@client-co.example> to the client contact list.
- Duration: 0 ms

### Step 7: `draft_reply` [OK]

- Args: {'email_id': 4, 'draft': 'We have placed a hold on Nov 21 for your team dinner.'}
- Result: Draft saved for email 4 (53 chars). Not sent.
- Duration: 0 ms

## 3. How can its actions be undone?

4 change(s) recorded: 0 irreversible, 0 compensable, 3 reversible, 1 with no reversibility declared.

### Can be undone (reversible)

- Step 3, `draft_reply`: can be undone. Undo: delete the draft.
  - What changed: Draft saved for email 1 (54 chars). Not sent.
- Step 5, `place_calendar_hold`: can be undone. Undo: release the hold on the company calendar. Window: until the hold expires, 48 hours after it is placed.
  - What changed: Calendar hold placed on 2026-11-21 for jane.sample@client-co.example.
- Step 7, `draft_reply`: can be undone. Undo: delete the draft.
  - What changed: Draft saved for email 4 (53 chars). Not sent.

### No reversibility declared

- Step 6, `add_client_contact`: no reversibility declared. Nobody wrote down how to undo this change before the run.
  - What changed: Added Jane Sample <jane.sample@client-co.example> to the client contact list.

---
Summary (observe mode): 7 actions (0 incomplete, 0 blocked), 0 violation(s), 4 mutation(s): 0 irreversible, 0 compensable, 3 reversible, 1 undeclared.

Emails actually sent in the core run: 0 []
Emails actually sent in the LangChain run: 0 []
LangChain adapter check: the adapter's report matches the core report (ignoring run id, timestamps and durations).
