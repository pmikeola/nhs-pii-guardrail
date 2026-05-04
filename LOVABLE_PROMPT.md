# Lovable Build Prompt — NHS PII Guardrail Checker

Copy everything below the line and paste it into Lovable to generate the frontend.

---

Build a clean, professional web app called **NHS PII Checker** that lets users paste text and check whether it contains NHS patient-identifying information.

## What the App Does

The app sends text to a live API and displays whether the text contains patient data. It is used by NHS staff to check text before sharing it.

---

## Pages / Screens

### Single page app with three states:

**State 1 — Ready (default)**
A centered card with:
- NHS logo placeholder (blue square with "NHS" text in white)
- Heading: "NHS PII Checker"
- Subheading: "Paste any text below to check for patient-identifying information"
- A large text area (min 6 rows) with placeholder: "Paste your text here..."
- A blue button labelled "Check Text"
- A small grey note at the bottom: "Text is not stored. Only an anonymised audit log is kept."

**State 2 — Loading**
- Replace the button with a spinner and the text "Checking..."
- Disable the text area while loading

**State 3 — Result**
Show a result card below the text area with:
- A large coloured badge showing the action:
  - 🔴 RED badge with "BLOCK" — if recommended_action is "block"
  - 🟡 AMBER badge with "REVIEW" — if recommended_action is "review"
  - 🟢 GREEN badge with "ALLOW" — if recommended_action is "allow"
- One line of plain English explanation (see copy below)
- A confidence indicator: "Confidence: High / Medium / Low"
- A "Check Another" button that clears the form and resets to State 1

---

## Plain English Result Copy

Use these exact messages based on the result:

| Result | Message |
|---|---|
| block | "⚠️ Patient-identifying information was detected. Do not share this text. Remove or anonymise the data before proceeding." |
| review | "⚡ This text may contain patient information. Please ask your Information Governance lead to review it before sharing." |
| allow | "✅ No patient-identifying information detected. This text appears safe to share." |

---

## API Integration

**Endpoint:**
```
POST https://web-production-b611c.up.railway.app/evaluate
```

**Headers:**
```
X-API-Key: testkey123
Content-Type: application/json
```

**Request body:**
```json
{
  "text": "<whatever the user typed>"
}
```

**Response:**
```json
{
  "flagged": true,
  "confidence": "high",
  "recommended_action": "block"
}
```

Use `recommended_action` to determine the badge colour and message.
Use `confidence` to show the confidence label.

**Error handling:**
- If the API returns an error or times out, show a neutral amber card with: "Unable to check this text right now. Please try again or contact your technical lead."

---

## Design

- **Colour palette:** NHS Blue (#005EB8) as primary, white background, light grey card backgrounds
- **Font:** Clean sans-serif (Inter or system font)
- **Style:** Simple, clinical, trustworthy — no decorative elements
- **Mobile friendly:** Responsive layout that works on phones and tablets
- **No login screen** — the API key is hardcoded in the app

---

## Extra Details

- Show a small footer: "NHS PII Guardrail · Powered by Claude AI"
- Add a subtle info tooltip (?) next to the text area that says: "The tool checks for NHS Numbers, names, dates of birth, postcodes, addresses, and email addresses"
- If the user clicks "Check Text" with an empty text area, show a gentle inline error: "Please enter some text to check"
- The "Check Another" button should scroll back to the top of the page

---

## What NOT to Include

- No user accounts or login
- No history or saved results
- No ability to edit the API key from the UI
- No dark mode toggle
- Keep it simple — one purpose only
