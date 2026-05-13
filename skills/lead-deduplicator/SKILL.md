---
name: lead-deduplicator
description: >
  Check whether leads already exist in the CEO Assistant database before adding them, to prevent
  duplicate outreach. Use this skill whenever new leads need to be validated against existing
  records, when the user asks "is this lead already in the database?", "check for duplicates",
  "have we contacted this person before?", or "filter out leads we already have". Always trigger
  this skill as a gate before sheets-lead-sync appends new leads. Also use when the user provides
  a batch of leads and wants to know which ones are net-new vs already tracked.
---

# Lead Deduplicator Skill

Cross-checks incoming leads against the existing Google Sheets lead database to prevent
duplicate entries and repeated outreach to the same contacts.

---

## Deduplication Logic

Leads are considered duplicates if ANY of the following match an existing row:

| Priority | Match Field | Notes |
|----------|------------|-------|
| 1st | **Email** (column F) | Exact match — strongest signal |
| 2nd | **Contact Name + Municipality** (columns D + B) | Both must match |
| 3rd | **Phone** (column G) | If email not available |

A lead passes deduplication if none of the above match any existing row.

---

## Workflow

### Step 1 — Load Existing Records
Fetch current data from Google Sheets:
- Pull columns B (Municipality), D (Contact Name), F (Email), G (Phone)
- Build an in-memory lookup set for fast comparison

### Step 2 — Check Each Incoming Lead
For each new lead:
1. Check email → if match found: **DUPLICATE**
2. Check name + municipality → if both match: **DUPLICATE**
3. Check phone (if email missing) → if match found: **DUPLICATE**
4. If no match: **NEW — pass through**

### Step 3 — Report Results

```
🔍 Deduplication Check Complete

✅ New (pass): [N] leads
⚠️  Duplicates (skip): [N] leads

Duplicates found:
| Name | Municipality | Email | Existing Status | First Found |
|------|-------------|-------|-----------------|-------------|
| ...  | ...         | ...   | Sent            | 2026-03-01  |

New leads cleared for sync:
| Name | Municipality | Email |
|------|-------------|-------|
| ...  | ...         | ...   |
```

### Step 4 — Pass Clean List Downstream
Return the deduplicated list of new leads for `sheets-lead-sync` to append.

---

## Edge Cases

| Situation | Behaviour |
|-----------|-----------|
| Email missing from new lead | Fall back to Name + Municipality check |
| Email missing from existing record | Skip email check, use Name + Municipality |
| Name slightly different (e.g. accent) | Flag as potential duplicate, let CEO decide |
| Same municipality, different contact | Allow — treat as new lead |
| Phone-only match (no email or name) | Flag as possible duplicate, don't auto-skip |

---

## MCP / Data Source

Uses Google Sheets MCP to fetch existing records:
- **Sheet**: CEO Assistant Lead Database
- **Tab**: Leads (or configured tab name)
- **Columns read**: B, D, F, G (Municipality, Name, Email, Phone)

If Google Sheets is not connected:
- Ask user to paste existing email list manually
- Or skip deduplication and flag: "Deduplication skipped — Sheets not connected"

---

## Example Interactions

**"Check if these 5 leads are already in our database"**
→ Loads sheet, runs checks, returns pass/fail per lead

**"We found 3 new leads — make sure they're not duplicates before saving"**
→ Runs dedup, passes 3 or fewer clean leads to sheets-lead-sync

**"Have we ever contacted the mayor of Uherské Hradiště?"**
→ Searches existing records for Municipality = "Uherské Hradiště", returns match or "not found"
