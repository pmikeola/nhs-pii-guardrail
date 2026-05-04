from __future__ import annotations

import csv
import hashlib
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from guardrail import detect_nhs_pii
from version import GUARDRAIL_VERSION

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="NHS PII Guardrail",
    description="LLM-based NHS patient identifier (PII) detection API — England, Wales, and Isle of Man",
    version="1.0.0",
)


# ── Key loading ────────────────────────────────────────────────────────────────
# Set GUARDRAIL_API_KEYS as a comma-separated list of "teamname:key" pairs.
# Example: GUARDRAIL_API_KEYS=red1:abc123,red2:def456
# Set ADMIN_API_KEY to protect the /logs endpoint (only you need this).

def _parse_api_keys(raw: str) -> dict[str, str]:
    """Returns {key: team_name} from 'team1:key1,team2:key2' string."""
    result = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            team, key = entry.split(":", 1)
            result[key.strip()] = team.strip()
    return result


_raw_keys = os.environ.get("GUARDRAIL_API_KEYS", "")
API_KEYS: dict[str, str] = _parse_api_keys(_raw_keys)
ADMIN_KEY: str = os.environ.get("ADMIN_API_KEY", "")

if not API_KEYS:
    raise RuntimeError(
        f"GUARDRAIL_API_KEYS is not set correctly. "
        f"Raw value read: {_raw_keys!r}. "
        f"Expected format: team1:key1,team2:key2"
    )
if not ADMIN_KEY:
    raise RuntimeError("ADMIN_API_KEY must be set.")

if not re.match(r'^v\d+\.\d+$', GUARDRAIL_VERSION):
    raise RuntimeError(
        f"Invalid GUARDRAIL_VERSION {GUARDRAIL_VERSION!r} in version.py. "
        f"Must be v<major>.<minor> (e.g. v1.0, v1.1)."
    )


# ── Persistent file log ────────────────────────────────────────────────────────
# LOG_DIR defaults to ./data locally; set to /data in Railway (mounted volume).
# The volume persists across redeploys so logs survive blue team pushes.

LOG_FIELDS = [
    "timestamp", "guardrail_version", "team", "ip", "input_hash", "input_length",
    "input_preview", "flagged", "confidence", "recommended_action",
    "findings_count", "error",
]

LOG_DIR = Path(os.environ.get("LOG_DIR", "./data"))
LOG_FILE = LOG_DIR / "requests.csv"
_log_lock = threading.Lock()


def _ensure_log_file() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        with open(LOG_FILE, "w", newline="") as f:
            csv.DictWriter(f, fieldnames=LOG_FIELDS).writeheader()


_ensure_log_file()


# ── Auth ───────────────────────────────────────────────────────────────────────

def require_team_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if x_api_key not in API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key.")
    return x_api_key


def require_admin_key(x_api_key: str = Header(..., alias="X-API-Key")) -> str:
    if x_api_key != ADMIN_KEY:
        raise HTTPException(status_code=401, detail="Invalid admin key.")
    return x_api_key


# ── Models ─────────────────────────────────────────────────────────────────────

class EvaluateRequest(BaseModel):
    text: str


class EvaluateResponse(BaseModel):
    flagged: bool
    confidence: str
    recommended_action: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _input_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _preview(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return repr(text)
    return repr(text[:max_len]) + f"... [{len(text)} chars]"


def _record_request(
    *,
    team: str,
    ip: str,
    input_hash: str,
    input_length: int,
    input_preview: str,
    flagged: bool | None,
    confidence: str | None,
    recommended_action: str | None,
    findings_count: int,
    error: str | None,
) -> None:
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "guardrail_version": GUARDRAIL_VERSION,
        "team": team,
        "ip": ip,
        "input_hash": input_hash,
        "input_length": input_length,
        "input_preview": input_preview,
        "flagged": flagged,
        "confidence": confidence,
        "recommended_action": recommended_action,
        "findings_count": findings_count,
        "error": error,
    }
    with _log_lock:
        with open(LOG_FILE, "a", newline="") as f:
            csv.DictWriter(f, fieldnames=LOG_FIELDS).writerow(row)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(
    body: EvaluateRequest,
    request: Request,
    api_key: str = Depends(require_team_key),
):
    team = API_KEYS[api_key]
    h = _input_hash(body.text)
    ip = request.client.host if request.client else "unknown"
    preview = _preview(body.text)

    log.info("request  | team=%s ip=%s hash=%s length=%d preview=%s", team, ip, h, len(body.text), preview)

    error_str = None
    result = None

    try:
        result = detect_nhs_pii(body.text)
    except anthropic.AuthenticationError:
        log.error("Anthropic auth failed — check ANTHROPIC_API_KEY")
        error_str = "auth_error"
        _record_request(team=team, ip=ip, input_hash=h, input_length=len(body.text),
                        input_preview=preview, flagged=None, confidence=None,
                        recommended_action=None, findings_count=0, error=error_str)
        raise HTTPException(status_code=503, detail="Guardrail service unavailable.")
    except anthropic.RateLimitError:
        log.warning("Anthropic rate limit | team=%s hash=%s", team, h)
        error_str = "rate_limit"
        _record_request(team=team, ip=ip, input_hash=h, input_length=len(body.text),
                        input_preview=preview, flagged=None, confidence=None,
                        recommended_action=None, findings_count=0, error=error_str)
        raise HTTPException(status_code=429, detail="Rate limited. Retry after a moment.")
    except anthropic.APIError as e:
        log.error("Anthropic API error | team=%s hash=%s: %s", team, h, e)
        error_str = f"api_error: {e}"
        _record_request(team=team, ip=ip, input_hash=h, input_length=len(body.text),
                        input_preview=preview, flagged=None, confidence=None,
                        recommended_action=None, findings_count=0, error=error_str)
        raise HTTPException(status_code=503, detail="Guardrail service error.")
    except ValueError as e:
        log.error("Result validation error | team=%s hash=%s: %s", team, h, e)
        error_str = f"validation_error: {e}"
        _record_request(team=team, ip=ip, input_hash=h, input_length=len(body.text),
                        input_preview=preview, flagged=None, confidence=None,
                        recommended_action=None, findings_count=0, error=error_str)
        raise HTTPException(status_code=500, detail="Guardrail output validation failed.")

    log.info(
        "response | team=%s ip=%s hash=%s flagged=%s confidence=%s action=%s",
        team, ip, h, result.get("flagged"), result.get("confidence"), result.get("recommended_action"),
    )

    _record_request(
        team=team,
        ip=ip,
        input_hash=h,
        input_length=len(body.text),
        input_preview=preview,
        flagged=result.get("flagged"),
        confidence=result.get("confidence"),
        recommended_action=result.get("recommended_action"),
        findings_count=len(result.get("findings", [])),
        error=None,
    )

    # Only return the three verdict fields — findings and explanation are stripped
    # to avoid leaking detection signals to the red team.
    # Full internal verdict is preserved in the log file for blue team review.
    return {
        "flagged": result.get("flagged"),
        "confidence": result.get("confidence"),
        "recommended_action": result.get("recommended_action"),
    }


@app.get("/logs")
async def download_logs(_key: str = Depends(require_admin_key)):
    """Download all requests as a CSV. Protected by ADMIN_API_KEY."""
    with _log_lock:
        content = LOG_FILE.read_text() if LOG_FILE.exists() else "No requests recorded yet.\n"

    filename = f"guardrail_logs_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.csv"
    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
