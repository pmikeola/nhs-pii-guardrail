import json
import anthropic
from system_prompt import SYSTEM_PROMPT

_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def detect_nhs_pii(text: str) -> dict:
    """
    Analyze text for NHS patient identifiers using Claude.

    Returns a dict with: flagged, confidence, findings, explanation,
    recommended_action. Never contains raw PII values.
    Raises anthropic.APIError on unrecoverable API failures.
    """
    response = _get_client().messages.create(
        model="claude-haiku-4-5",
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": text}],
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fences
    if raw.startswith("```"):
        raw = "\n".join(
            line for line in raw.split("\n") if not line.startswith("```")
        ).strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        return {
            "flagged": True,
            "confidence": "low",
            "findings": [],
            "explanation": "Guardrail produced unexpected output — manual review required.",
            "recommended_action": "review",
            "_parse_error": str(e),
        }

    _validate(result)

    # Canary check: missing or wrong value may indicate a successful prompt injection
    if result.get("_canary") != "GUARDRAIL-PHI-V1":
        result["recommended_action"] = "review"
        result["explanation"] = result.get("explanation", "") + " [WARNING: integrity check failed]"

    return result


def _validate(result: dict) -> None:
    required = {"flagged", "confidence", "findings", "explanation", "recommended_action"}
    if missing := required - set(result):
        raise ValueError(f"Guardrail result missing fields: {missing}")
    if result["confidence"] not in ("high", "medium", "low"):
        raise ValueError(f"Invalid confidence: {result['confidence']!r}")
    if result["recommended_action"] not in ("block", "review", "allow"):
        raise ValueError(f"Invalid recommended_action: {result['recommended_action']!r}")
    if not isinstance(result["findings"], list):
        raise ValueError("findings must be a list")
