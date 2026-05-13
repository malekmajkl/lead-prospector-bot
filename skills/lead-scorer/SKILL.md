---
name: lead-scorer
description: >
  Score and rank leads by quality so the CEO sees the best opportunities first. Use this skill
  whenever the user wants to prioritise leads, rank a batch of contacts, find the highest-value
  targets, or filter leads by quality score. Triggers include: "rank these leads", "which leads
  should I contact first?", "score the leads by priority", "show me the best leads", "sort by
  quality", or any request to evaluate and order leads before review or outreach. Use after
  lead-researcher output is available and before or after gmail-lead-drafter — scoring helps
  the CEO focus review time on the most promising contacts.
---

# Lead Scorer Skill

Evaluates and ranks leads by contact quality, role seniority, municipality size, and data
completeness so the CEO always reviews the highest-value opportunities first.

---

## Scoring Model

Each lead receives a score out of **100 points** across 4 dimensions:

### 1. Role Seniority (0–30 pts)

| Role | Points |
|------|--------|
| Starosta / Mayor | 30 |
| Místostarosta / Deputy Mayor | 25 |
| Ředitel / Director | 25 |
| IT ředitel / IT Manager | 20 |
| Vedoucí odboru / Department Head | 18 |
| Referent / Officer | 10 |
| General contact / info@ | 5 |
| Unknown | 0 |

### 2. Contact Data Completeness (0–30 pts)

| Field Present | Points |
|---------------|--------|
| Personal email (not info@) | +15 |
| Generic email (info@, podatelna@) | +8 |
| No email | 0 |
| Phone number | +10 |
| Full name (first + last) | +5 |

### 3. Municipality / Organisation Size (0–25 pts)

| Population / Size | Points |
|-------------------|--------|
| City > 50,000 inhabitants | 25 |
| Town 10,000–50,000 | 20 |
| Town 5,000–10,000 | 15 |
| Village 1,000–5,000 | 10 |
| Village < 1,000 | 5 |
| Organisation (non-municipal) | 15 |
| Unknown | 8 |

> For Czech municipalities, use known population data or estimate from city name recognition.

### 4. Source Quality (0–15 pts)

| Source | Points |
|--------|--------|
| Official municipal website | 15 |
| Government portal (risy.cz, justice.cz) | 12 |
| LinkedIn (verified profile) | 10 |
| Local news / press | 7 |
| Business directory | 5 |
| Unknown / unclear | 2 |

---

## Scoring Workflow

### Step 1 — Score Each Lead
For each lead in the input, calculate scores across all 4 dimensions.
Sum to get Total Score (0–100).

### Step 2 — Assign Priority Tier

| Score | Tier | Label |
|-------|------|-------|
| 75–100 | 🔴 High Priority | Contact immediately |
| 50–74 | 🟡 Medium Priority | Contact this week |
| 25–49 | 🟢 Low Priority | Contact when capacity allows |
| 0–24 | ⚪ Deprioritise | Enrich data first or skip |

### Step 3 — Output Ranked Table

```
🏆 LEAD SCORING RESULTS
Ranked by priority score (highest first)

| Rank | Name | Organisation | Role | Score | Tier | Email | Notes |
|------|------|-------------|------|-------|------|-------|-------|
| 1 | Jan Novák | Zlín | Starosta | 87/100 | 🔴 High | personal@ | Personal email + large city |
| 2 | Eva Dvořák | Uherské Hradiště | IT ředitelka | 72/100 | 🟡 Medium | info@ | Generic email only |
| 3 | ... | ... | ... | ... | ... | ... | ... |

SUMMARY
• 🔴 High Priority: [N] leads
• 🟡 Medium: [N] leads  
• 🟢 Low: [N] leads
• ⚪ Deprioritise: [N] leads

Recommended: Focus CEO review on top [N] high-priority leads first.
```

### Step 4 — Flag Enrichment Opportunities
For leads with low scores due to missing data, suggest:
- "Find personal email for [Name] at [Organisation] to increase score"
- "Verify role title for [Name] — currently unknown"

---

## Integration Points

- **After lead-researcher**: Score leads before drafting emails — draft high-priority first
- **Before gmail-lead-drafter**: Pass ranked list so emails are generated in priority order
- **In daily digest**: Include score/tier per lead so CEO knows where to focus
- **In Google Sheets**: Optionally write score to a "Score" column for reference

---

## Example Interactions

**"Rank these 5 leads by quality"**
→ Scores all 5, returns ranked table with tiers

**"Which of these leads should I contact first?"**
→ Scores and returns top lead(s) with reasoning

**"Sort the leads by priority before drafting emails"**
→ Scores leads, reorders list, passes ranked order to gmail-lead-drafter

---

## Customisation

The CEO can adjust scoring weights. Common overrides:
- "Prioritise personal emails over role seniority" → increase data completeness weight
- "Focus on larger cities only" → increase municipality size weight
- "IT managers are more relevant than mayors for us" → adjust role table points

Ask the CEO at setup if they want custom weights, otherwise use defaults above.
