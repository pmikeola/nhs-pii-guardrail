# NHS PII Guardrail — Team Guide

## What Is This Tool?

This tool is an **automatic privacy checker** for NHS patient data.

When you paste or send any piece of text to it, it reads the text and tells you whether it contains **patient-identifying information** — things like NHS Numbers, dates of birth, names combined with medical details, addresses, or email addresses.

Think of it as a security guard that stands at the door and checks every piece of text before it goes somewhere it shouldn't.

---

## Why Do We Need It?

NHS patient data is protected by law. If patient-identifying information is accidentally shared — in an email, a document, a message, or an app — it can cause serious harm to patients and result in significant legal and reputational consequences for your organisation.

This tool helps catch that risk **before** it becomes a problem.

---

## What Does It Check For?

The tool looks for 7 types of NHS patient identifiers:

| # | What It Is | Example |
|---|---|---|
| 1 | **NHS Number** | 485 777 3456 |
| 2 | **Last name** (when combined with other details) | SMITH |
| 3 | **First name** (when combined with other details) | John |
| 4 | **Date of birth** | 08-Feb-2005 |
| 5 | **Postcode** (when combined with other details) | SW1A 1AA |
| 6 | **First line of address** (when combined with postcode) | 12 Baker Street |
| 7 | **Email address** | john.smith@nhs.net |

> **Important:** A name or postcode on its own is not flagged. The tool understands context — it only raises an alert when the combination of details could identify a real patient.

---

## What Does the Result Mean?

Every time you check a piece of text, you get back three things:

### 1. Flagged — Yes or No
- **Yes (true)** — the text contains patient-identifying information
- **No (false)** — the text looks safe

### 2. Confidence — How Sure the Tool Is
- **High** — very confident, act immediately
- **Medium** — likely an issue, worth checking manually
- **Low** — something looks unusual but uncertain

### 3. Recommended Action — What To Do Next
| Action | What It Means | What You Should Do |
|---|---|---|
| **Block** | High risk — patient data detected | Do not share this text. Remove or anonymise the data first. |
| **Review** | Possible risk — human judgement needed | Pass to your information governance lead to review |
| **Allow** | No patient data detected | Safe to proceed |

---

## How To Use It

You do not need to install anything. You just send a request to the tool's web address.

### The Web Address (API URL)
```
https://web-production-b611c.up.railway.app/evaluate
```

### Your Team Access Key
```
testkey123
```
Keep this key private — do not share it publicly.

---

### Option 1 — Using the Browser (Easiest Way)

1. Go to: **https://web-production-b611c.up.railway.app/docs**
2. Click on **POST /evaluate**
3. Click **Try it out**
4. In the box that appears, replace the example text with the text you want to check:
   ```json
   {
     "text": "paste your text here"
   }
   ```
5. Click **Execute**
6. Scroll down to see the result

---

### Option 2 — Using the Terminal (For Technical Users)

Copy and paste this command, replacing the text in quotes with what you want to check:

```bash
curl -X POST https://web-production-b611c.up.railway.app/evaluate \
  -H "X-API-Key: testkey123" \
  -H "Content-Type: application/json" \
  -d '{"text": "your text here"}'
```

---

## Example Results

### Example 1 — Patient data detected (Block)
**Text checked:**
> "Patient: John Smith, NHS: 485 777 3456, DOB: 08-Feb-2005"

**Result:**
```json
{
  "flagged": true,
  "confidence": "high",
  "recommended_action": "block"
}
```
**What to do:** Do not share this text. Remove the NHS Number and date of birth before proceeding.

---

### Example 2 — Safe text (Allow)
**Text checked:**
> "The patient's appointment has been rescheduled to next Monday."

**Result:**
```json
{
  "flagged": false,
  "confidence": "high",
  "recommended_action": "allow"
}
```
**What to do:** Safe to proceed — no patient-identifying information found.

---

### Example 3 — Needs review (Review)
**Text checked:**
> "John Smith, born 08-Feb-2005"

**Result:**
```json
{
  "flagged": true,
  "confidence": "medium",
  "recommended_action": "review"
}
```
**What to do:** Pass to your information governance lead. A name and date of birth together could identify a patient but the tool is not certain.

---

## Quick Reference Card

| If you see... | It means... | Do this... |
|---|---|---|
| `"recommended_action": "block"` | Patient data found — high risk | Stop. Do not share. Anonymise first. |
| `"recommended_action": "review"` | Possible patient data | Ask your IG lead to check |
| `"recommended_action": "allow"` | No patient data found | Safe to proceed |
| `"flagged": true` | Something was detected | Check the action above |
| `"flagged": false` | Nothing detected | Safe to proceed |

---

## Who To Contact

| Question | Contact |
|---|---|
| Something looks wrong with the tool | Your technical lead |
| Not sure if a result means I should share the data | Your Information Governance lead |
| Need a team access key | Your technical lead |
| Want to download the full audit log | Admin only — contact your technical lead |

---

## Summary

- This tool **automatically checks text** for NHS patient identifiers
- It covers **7 types** of identifying information
- Results are **instant** — no waiting
- It gives you a clear **block / review / allow** decision
- It does **not store** the text you send — only a short anonymised log entry is kept for audit purposes
- It works **24/7** — available any time via the web address above
