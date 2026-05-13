---
name: sheets-lead-sync
description: >
  Sync lead data to Google Sheets — append new leads, check for duplicates, and update lead status.
  Use this skill whenever the user wants to save leads to a spreadsheet, update a lead's status
  (New / Reviewed / Sent / Replied / Closed), check if a lead already exists in the database, or
  maintain the live CEO Assistant lead database. Triggers include: "save leads to Sheets",
  "add these leads to the spreadsheet", "update the status of this lead", "check if this email
  is already in the database", "sync to Google Sheets", or any workflow where structured lead data
  needs to be written to or read from Google Sheets. Always use after lead-researcher or
  gmail-lead-drafter completes if Sheets sync is part of the workflow.
---

# Sheets Lead Sync Skill

Manages the CEO Assistant lead database in Google Sheets — appending new leads, deduplicating,
and keeping statuses up to date.

---

## Google Sheets Schema

The target spreadsheet uses this column layout (in order):

| Column | Header | Type | Notes |
|--------|--------|------|-------|
| A | Date Found | Date | ISO format: YYYY-MM-DD |
| B | Municipality | Text | Name of city, town, or public body |
| C | Region | Text | Kraj name (e.g. Zlínský, Jihomoravský) |
| D | Contact Name | Text | Full name of decision-maker |
| E | Role / Title | Text | e.g. Starosta, IT ředitel |
| F | Email | Text | Primary contact email |
| G | Phone | Text | Phone number if available |
| H | Source URL | URL | Where the lead was discovered |
| I | Language | Text | CZ or EN |
| J | Email Draft | Text | Full text of outreach email draft |
| K | Status | Text | New / Reviewed / Sent / Replied / Closed |
| L | CEO Notes | Text | Free-text notes by CEO |

---

## Operations

### 1. Append New Leads

For each new lead:
1. Check column F (Email) for duplicates — skip if email already exists
2. If no email, check columns B+D (Municipality + Name) for duplicates
3. If unique, append a new row with:
   - Date Found = today's date
   - Status = `New`
   - All available fields populated
   - Empty fields left blank (never fill with "N/A" or placeholders)

### 2. Duplicate Check

Before appending, query existing data:
```
- Search column F for exact email match
- If email is blank, search columns B AND D for matching municipality + name combo
- If match found: skip and flag as duplicate in report
- If no match: proceed with append
```

### 3. Update Lead Status

When user requests a status update:
- Find row by email or contact name
- Update column K (Status) to new value
- Optionally update column L (CEO Notes) if notes provided

Valid status values: `New` | `Reviewed` | `Sent` | `Replied` | `Closed`

### 4. Read / List Leads

On request, fetch and display leads filtered by:
- Status (e.g. all `New` leads)
- Region (e.g. all Zlínský kraj leads)
- Date range (e.g. this week's leads)

---

## MCP Integration

Use Google Sheets via available MCP or API tools.

**If Google Sheets MCP is connected**, use it to:
- Read existing rows for deduplication
- Append new rows
- Update specific cells

**If not connected**, inform user:
> "Google Sheets isn't connected. Enable it in the Tools menu, or I can export leads as a CSV/XLSX file you can paste in manually."

Fall back to generating a downloadable XLSX using the `xlsx` skill.

---

## Workflow

### Step 1 — Identify Target Sheet
Ask once (or reuse from context):
- Google Sheets URL or Sheet ID
- Sheet/tab name (default: `Leads`)

### Step 2 — Read Existing Data
Fetch column F (emails) and optionally B+D for deduplication reference.

### Step 3 — Process Each Lead
For each lead in input:
1. Run duplicate check
2. If new → build row array in correct column order
3. Append row to sheet

### Step 4 — Report Results
```
📊 Google Sheets Sync Complete

✅ Added: [N] new leads
⏭️ Skipped: [N] duplicates
❌ Errors: [N] (if any)

New leads added:
| Name | Municipality | Email | Status |
|------|-------------|-------|--------|
| ...  | ...         | ...   | New    |
```

---

## Error Handling

- **Duplicate found**: Skip silently, include in skip count
- **Missing email AND name**: Skip lead, flag in report
- **Sheet not found**: Ask user to verify Sheet ID/URL and tab name
- **API error**: Report error, offer CSV fallback

---

## Example Interactions

**"Save these leads to the spreadsheet"**
→ Reads leads from context, deduplicates, appends to Sheets, reports summary

**"Mark the lead for Luhačovice as Sent"**
→ Finds row by municipality/name, updates Status to `Sent`

**"Show me all New leads from this week"**
→ Fetches sheet data, filters by Status=New and Date Found this week, displays table
