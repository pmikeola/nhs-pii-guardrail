# Health PHI Guardrail — Blue Team Guide

This repository contains an LLM-based security guardrail that detects protected health information (PHI) in text — including data that has been encoded or obfuscated to evade detection. It is aligned with HIPAA privacy requirements.

PHI types detected: Social Security Numbers (SSNs), Medical Record Numbers (MRNs), Dates of Birth, Health Plan / Insurance IDs, Diagnosis codes (ICD), Prescription details, Lab results, and combinations of the above.

A red team will send payloads to the live API trying to sneak PHI through. Your job is to harden the guardrail so it catches everything they throw at it.

---

## What's in this repository

| File | What it does | Can you edit it? |
|---|---|---|
| `system_prompt.py` | Instructions given to the AI — the guardrail's brain | **Yes — this is your main tool** |
| `guardrail.py` | Sends text to Claude and parses the response | Yes, with care |
| `api.py` | The web API the red team calls | Yes, with care |
| `requirements.txt` | Python package list | Yes if you add dependencies |
| `.env.example` | Template for secret keys (never commit `.env`) | No |

**Start with `system_prompt.py`.** Most hardening work happens there. Only touch `guardrail.py` or `api.py` if you want to add defenses outside the AI (rate limiting, input pre-processing, etc.).

---

## How the guardrail works

Every time the red team sends a request, this happens:

1. Their text lands at `POST /evaluate` in `api.py`
2. `guardrail.py` sends it to Claude with the instructions from `system_prompt.py`
3. Claude returns a full internal verdict including findings and encoding details
4. `api.py` logs the full verdict server-side, then strips `findings` before returning a trimmed response to the red team

The red team **wins** if they get `"recommended_action": "allow"` for a payload containing real PHI, or if they can trick the AI into revealing its instructions.

### What the red team sees

```json
{
  "flagged": true,
  "confidence": "high",
  "recommended_action": "block"
}
```

### What the full internal verdict looks like (visible in logs only)

```json
{
  "flagged": true,
  "confidence": "high",
  "findings": [
    {
      "type": "COMBINED_PHI",
      "encoding_detected": "base64",
      "notes": "SSN and DOB detected after base64 decoding, accompanied by a patient name."
    }
  ],
  "explanation": "A combined PHI record was detected containing an SSN, date of birth, and patient name.",
  "recommended_action": "block",
  "_canary": "GUARDRAIL-PHI-V1"
}
```

The `findings` array is your primary diagnostic tool. Each entry tells you the `type` of PHI detected, the `encoding_detected` (e.g. `base64`, `hex`, `none`), and human-readable `notes`. Use this when reviewing red team logs to understand exactly what the guardrail caught and how.

---

## How to make changes

You have two options: editing directly on GitHub (easiest) or using Git on your computer (more powerful).

### Option A — Edit on GitHub (no setup required)

This works for quick changes to `system_prompt.py`.

1. Go to the repository on GitHub
2. Click on `system_prompt.py`
3. Click the pencil icon (Edit this file) in the top right
4. Make your changes
5. Scroll down, write a short description of what you changed (e.g. "Add ROT13 detection instruction"), and click **Commit changes**
6. The live API will redeploy automatically within about 30 seconds

### Option B — Use Git on your computer (recommended for bigger changes)

**First-time setup** (do this once):

1. Install Git: https://git-scm.com/downloads
2. Open a terminal (Terminal on Mac, Command Prompt or PowerShell on Windows)
3. Clone the repository (replace the URL with your actual repo URL):
   ```bash
   git clone https://github.com/your-org/health-phi-guardrail.git
   cd health-phi-guardrail
   ```

**Every time you want to make a change:**

1. Pull the latest version from GitHub first:
   ```bash
   git pull
   ```
2. Open `system_prompt.py` in any text editor and make your changes
3. Save the file, then tell Git to package your changes:
   ```bash
   git add system_prompt.py
   git commit -m "Describe what you changed here"
   git push
   ```
4. The live API redeploys automatically — check the Railway dashboard to confirm

---

## Hardening the system prompt

Open `system_prompt.py`. The `SYSTEM_PROMPT` string is what the AI reads before analyzing any input. Changing it changes how the AI behaves.

### What to look for in the logs

Download the attack log CSV from your instructor. Each row is one red team request. Look for:
- Rows where `recommended_action` is `allow` or `review` but the `input_preview` looks suspicious
- Rows where `flagged` is `False` — those are the red team's wins
- Unusual `input_length` values (very long inputs, or empty inputs)

### Ideas for hardening

**1. Add new obfuscation examples**
The system prompt already lists base64, hex, ROT13, etc. After reviewing red team attacks, add new encoding schemes you observe to the `OBFUSCATION DECODING` section.

**2. Tighten injection resistance**
If the red team is trying specific injection phrases ("pretend you are", "[SYSTEM]", etc.), add those exact patterns to the `ABSOLUTE RULES` section.

**3. Change the canary value**
The system prompt instructs the AI to include `"_canary": "GUARDRAIL-PHI-V1"` in every response. `guardrail.py` checks for this — a missing or wrong canary triggers a forced `review`. After each round, change the canary string in **both** `system_prompt.py` and `guardrail.py` so the red team can't hardcode it.

In `system_prompt.py`, find and update:
```
"_canary": "GUARDRAIL-PHI-V1"
```

In `guardrail.py`, find and update the check:
```python
if result.get("_canary") != "GUARDRAIL-PHI-V1":
```

**4. Add non-AI defenses in `api.py`**
You are not limited to the system prompt. In `api.py` you can add:
- **Input length limits** — reject inputs over N characters before they reach the AI
- **Rate limiting per team key** — limit requests per minute
- **Pre-screening** — run a fast regex pass to immediately block obvious SSNs or MRNs before the AI call

**5. Bump the version**
Every push that changes the guardrail must increment the version in `version.py`. The format is `v<major>.<minor>` — the sequence is `v1.0` → `v1.1` → `v1.2`. The app will refuse to start if the format is wrong.

**6. Things to avoid**
- Do not remove the `_canary` check from `guardrail.py` — it is a safety net
- Do not commit your `.env` file — it contains secret keys
- Do not change the JSON output structure that `guardrail.py` expects, or it will break

---

## Checking if your changes are live

1. Go to the Railway dashboard (your instructor will share the link)
2. Look for a green "Deployed" badge — if it is still deploying, wait 30 seconds and refresh
3. Test with a known payload:

```bash
curl -X POST https://health-phi-guardrail-production.up.railway.app/evaluate \
  -H "X-API-Key: your-team-key" \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient John Doe, SSN 123-45-6789, diagnosed with E11.9"}'
```

This should return `"flagged": true` and `"recommended_action": "block"`. If it does, your changes deployed correctly.

---

## Downloading the attack log (instructors only)

```bash
curl -o logs.csv https://health-phi-guardrail-production.up.railway.app/logs \
  -H "X-API-Key: your-admin-key"
```
