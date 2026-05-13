---
name: lead-researcher
description: >
  Research contact leads by industry and location. Use this skill whenever the user wants to find
  contacts, leads, decision-makers, or key officers for businesses, municipalities, or organizations
  in a given area or sector. Triggers include: "find leads in X city", "research contacts for Y
  industry", "get me the mayor and contact info for towns in Z region", "find decision makers in X
  field", "who runs the municipality in Y", or any request to look up email/phone for local officials,
  business owners, or organizational leads. Always use this skill when the user provides an
  industry + location combination and wants structured contact output.
---

# Lead Researcher Skill

Finds key contacts (decision-makers, mayors, officers, executives) for a batch of organizations or
municipalities given an industry/sector and location, then outputs structured contact data.

---

## Input Template

The user provides some combination of:
- **Industry / sector**: e.g. "municipal governments", "dental clinics", "construction firms", "NGOs"
- **Location**: e.g. "Zlín Region, Czech Republic", "Bavaria, Germany", "Chicago suburbs"
- **Batch size**: 2–10 targets (default: 5 if not specified)
- **Optional focus**: specific role to find (e.g. "mayor", "CEO", "procurement officer"); if not given, infer the most relevant decision-maker for the sector

---

## Research Workflow

### Step 1 — Identify Targets
Search for organizations/entities matching the industry + location.
- Query pattern: `"[industry] [location]"`, `"[sector] companies [city/region]"`, `"municipalities in [region]"`
- Collect 2–10 target names + their official websites if available
- Prefer authoritative sources: official websites, government portals, LinkedIn, local business directories

### Step 2 — Find Decision-Maker per Target
For each target, search for the key contact person:
- For **municipalities**: search `"mayor [city name]"`, `"starosta [město]"` (Czech), or equivalent in local language
- For **businesses**: search `"CEO [company]"`, `"director [company]"`, `"[company] leadership team"`
- For **NGOs/institutions**: search `"[organization] director"`, `"[organization] contact officer"`
- Use `web_fetch` on official websites to find "About", "Contact", "Leadership", or "Team" pages directly

### Step 3 — Find Email & Phone
For each target + contact person:
1. Check official website contact page (`web_fetch` on `/contact`, `/about`, `/kontakt`)
2. Search `"[person name] [organization] email"` or `"[organization] contact email"`
3. Search `"[organization] phone"` or `"[organization] telefon"` for local language variants
4. If direct email not found, note the general contact email (e.g. info@...) as fallback
5. Mark fields as `Not found` if genuinely unavailable — never invent or guess contact details

### Step 4 — Compile & Output

Present results as a clean markdown table with these columns:

| # | Organization | Location | Key Contact | Role | Email | Phone | Source |
|---|---|---|---|---|---|---|---|

Then below the table, add a **Notes** section flagging:
- Any contacts where only a general email was found (not personal)
- Any targets where no contact info could be verified
- Suggestions for manual follow-up (e.g. LinkedIn profile link if found)

---

## Output Guidelines

- Always include a **Source** column with the URL where contact info was verified
- Use local language variants in searches when location is non-English (Czech, German, etc.)
- If fewer than requested leads are found with verified info, explain why and suggest refining the query
- Offer to export at the end: *"Would you like this exported to a spreadsheet (CSV/XLSX) or saved to Google Docs?"*
- Never fabricate emails, phone numbers, or names — accuracy over completeness

---

## 🔁 Pipeline Continuation — Auto Email Drafting

**After completing the lead table, always proceed automatically to the next step without asking the user.**

If the `gmail-lead-drafter` skill is available AND Gmail is connected:
1. State clearly: *"Research complete. Proceeding to create Gmail drafts for each lead…"*
2. Immediately apply the `gmail-lead-drafter` skill to the leads just found
3. Create one Gmail draft per lead — do not stop to ask for confirmation
4. Finish by showing the draft summary table (contact, org, email, draft status)

This means a prompt like *"Find mayors in Prague region"* should result in **both** a lead table **and** Gmail drafts being created in a single uninterrupted workflow.

Only skip auto-drafting if:
- Gmail MCP is not connected (mention this to the user)
- The user has explicitly said they only want research, not drafts

---

## Example Interaction

**User:** Find me 5 mayors with contact info in the Zlín Region, Czech Republic

**Claude:**
1. Searches for municipalities in Zlín Region
2. Fetches official municipal websites for each
3. Finds mayor name + contact details from each site
4. Returns table + notes + offer to export

---

## Exporting to Google Docs

When the user requests a Google Docs export:

1. **Check for Google Drive MCP tool** — if a Google Drive tool is connected (e.g. `gdrive_create_document`, `google_drive`, or similar), use it to create a new Google Doc with the results.

2. **Format for Google Docs**:
   - Title: `Lead Research — [Industry] — [Location] — [Date]`
   - Include the full table formatted as a plain text table or use the tool's native table support
   - Add the Notes section below the table
   - Add a footer: *Generated by Lead Researcher skill on [date]*

3. **If no Google Drive tool is connected**:
   - Inform the user: *"Google Drive isn't connected. You can enable it in the Tools menu, or I can export to CSV/XLSX instead."*
   - Offer XLSX as the fallback (use the xlsx skill)

4. **Sharing**: After creating the doc, return the Google Docs link to the user so they can open or share it directly.

---

## Tips for Better Results

- Czech municipal sites often list contacts at `/kontakt` or `/samosprava/starosta`
- German municipal sites often at `/gemeinde/buergermeister`
- LinkedIn can supplement when official sites lack personal emails
- For businesses, Firmy.cz (CZ), Handelsregister (DE), or Companies House (UK) are useful directories
