import csv
import hashlib
import io
import logging
import os
import threading
from datetime import datetime, timezone

import anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from guardrail import detect_cardholder_data

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(
    title="Cardholder Data Guardrail",
    description="LLM-based PCI DSS cardholder data detection API",
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


API_KEYS: dict[str, str] = _parse_api_keys(os.environ.get("GUARDRAIL_API_KEYS", ""))
ADMIN_KEY: str = os.environ.get("ADMIN_API_KEY", "")

if not API_KEYS:
    raise RuntimeError(
        "GUARDRAIL_API_KEYS must be set. Format: team1:key1,team2:key2"
    )
if not ADMIN_KEY:
    raise RuntimeError("ADMIN_API_KEY must be set.")


# ── In-memory request log ──────────────────────────────────────────────────────
# Stored in memory — resets on each deploy. Good enough for round-based exercises.
# For persistence across deploys, swap _request_log for a SQLite file or Railway volume.

_log_lock = threading.Lock()
_request_log: list[dict] = []


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


class Finding(BaseModel):
    type: str
    encoding_detected: str
    notes: str


class EvaluateResponse(BaseModel):
    flagged: bool
    confidence: str
    findings: list[Finding]
    explanation: str
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
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
        _request_log.append(entry)


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
        result = detect_cardholder_data(body.text)
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

    return result


@app.get("/logs")
async def download_logs(_key: str = Depends(require_admin_key)):
    """Download all requests as a CSV. Protected by ADMIN_API_KEY."""
    with _log_lock:
        snapshot = list(_request_log)

    output = io.StringIO()
    if snapshot:
        writer = csv.DictWriter(output, fieldnames=snapshot[0].keys())
        writer.writeheader()
        writer.writerows(snapshot)
    else:
        output.write("No requests recorded yet.\n")

    output.seek(0)
    filename = f"guardrail_logs_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
