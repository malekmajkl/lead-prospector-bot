---
name: gmail-lead-drafter
description: >
  Draft and save personalised cold-outreach Gmail drafts from lead-researcher output. ALWAYS trigger
  this skill automatically immediately after the lead-researcher skill completes — do not wait for the
  user to ask. If a user says "find mayors in X region" or any lead research request, this skill runs
  as the automatic second step the moment research finishes. Triggers include: lead-researcher output
  appearing in context, "create drafts for these leads", "draft emails from the lead table", "save
  outreach emails to Gmail", "generate cold email drafts for the CEO to review", or any workflow that
  follows lead data with email drafting. Also use when the user asks to re-draft, update, or regenerate
  existing lead email drafts. Always use this skill when lead data (contact name, role, email,
  municipality) is in context and email drafting is the next step — even if the user did not explicitly
  ask for drafts.
---

# Gmail Lead Drafter Skill

Takes structured lead data (from lead-researcher or manually provided) and generates personalised
Czech or English cold-outreach emails, then saves them as Gmail drafts for CEO review.

---

## Input

Accepts lead data in any of these formats:
- Output table from the `lead-researcher` skill (markdown table)
- Manually provided contact details (name, role, organisation, email, language)
- A mix of both

Minimum required per lead: **Contact Name**, **Organisation/Municipality**, **Email**, **Role**

---

## Language Detection

| Condition | Email Language |
|---|---|
| Contact is in Czech Republic + no English indicator | **Czech (default)** |
| Contact name/org signals English context | **English** |
| User explicitly specifies language | Use specified language |

Always default to **Czech** for all Czech municipal contacts.

---

## Email Template Structure

Each email is generated dynamically but follows this structure:

### Czech Template
```
Předmět: [Personalizovaný předmět — hodnota pro obec/organizaci]

Vážený/á pane/paní [Příjmení],

[Odstavec 1 — krátké představení odesílatele a společnosti]

[Odstavec 2 — konkrétní hodnota pro municipality/veřejný sektor]

[Výzva k akci — návrh krátkého úvodního hovoru nebo schůzky]

S pozdravem,
[Jméno CEO]
[Titul], [Název společnosti]
[Email] | [Telefon]
```

### English Template
```
Subject: [Personalised subject — value proposition for the organisation]

Dear [Title] [Last Name],

[Paragraph 1 — brief intro of sender and company]

[Paragraph 2 — specific value for municipalities / public sector]

[Call to action — request a short intro call or meeting]

Best regards,
[CEO Name]
[Title], [Company Name]
[Email] | [Phone]
```

---

## Drafting Workflow

### Step 1 — Load Sender Profile
Extract or ask for:
- CEO full name
- Title / position
- Company name
- Contact email
- Phone number
If these were provided earlier in the conversation, reuse them without asking again.

### Step 2 — Load Company Pitch
Extract from conversation context or ask:
- What product/service is being pitched?
- Key benefit for municipalities specifically
- Any approved template text from the CEO

### Step 3 — Generate Email Per Lead
For each lead:
1. Detect language (CZ/EN) based on location and context
2. Address contact by name and role in the appropriate language
3. Reference their specific municipality/organisation by name
4. Personalise body §1 with company intro
5. Personalise body §2 with value relevant to their role (e.g. Starosta vs IT Manager)
6. Write clear CTA — request a 20-minute intro call
7. Add CEO signature block

### Step 4 — Save to Gmail Drafts
Use the Gmail MCP tool to save each email as a draft:

```javascript
// MCP call pattern for saving Gmail draft
{
  tool: "gmail",
  action: "create_draft",
  to: "[lead email]",
  subject: "[generated subject]",
  body: "[generated email body]"
}
```

**Gmail MCP server**: `https://gmailmcp.googleapis.com/mcp/v1`

If Gmail MCP is not connected:
- Inform user: "Gmail isn't connected. Enable it in the Tools menu, or I can output the emails as text for manual copying."
- Fall back to displaying emails as formatted text blocks

### Step 5 — Confirm & Report
After saving all drafts, report:
```
✅ Gmail Drafts Created: [N] emails saved

| Lead | Organisation | Email | Subject | Language |
|------|-------------|-------|---------|----------|
| ...  | ...         | ...   | ...     | CZ/EN    |

📬 Drafts are ready for CEO review in Gmail → Drafts folder.
```

---

## Role-Based Personalisation

Adjust tone and value proposition based on contact role:

| Role | Focus of Body §2 |
|---|---|
| Starosta / Mayor | Civic impact, local development, community benefit |
| IT Manager / IT ředitel | Technical efficiency, integration, modernisation |
| Procurement / Nákup | Cost savings, compliance, vendor reliability |
| Director / Ředitel | Strategic value, ROI, partnerships |
| General contact | Broad public sector value |

---

## Error Handling

- **Missing email**: Skip lead, flag in report as "No email — draft skipped"
- **Missing name**: Use role + organisation as salutation (e.g. "Vážený starostо obce Luhačovice")
- **Gmail API error**: Display draft as text fallback, note the error
- **Ambiguous language**: Default to Czech, note assumption in report

---

## Example Interaction

**Context**: lead-researcher just returned 5 mayors in Zlínský kraj

**Claude automatically:**
1. Detects lead data in context
2. Checks for CEO sender profile (asks if not found)
3. Generates 5 personalised Czech emails
4. Saves 5 drafts to Gmail via MCP
5. Returns confirmation table

---

## Tips

- Keep emails under 200 words — Czech municipal contacts prefer brevity
- Use formal address: "Vážený pane starosto" (mayor), "Vážená paní ředitelko" (female director)
- Avoid superlatives and marketing language — public sector prefers factual, professional tone
- Always personalise the subject line with the municipality name
- For English emails, use "Dear Mr/Ms [Last Name]" format
