import json
import time
import urllib.error
import urllib.request
from typing import Optional
from fastapi import HTTPException

from app.core import config

_ENGINES = {"OLLAMA": "ollama", "WEB_API": "cloud", "CLOUD": "cloud", "GEMINI": "cloud"}


def _call(url: str, body: Optional[dict], headers: dict) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json", **headers})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=config.AI_TIMEOUT) as res:
                return json.loads(res.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503) and attempt < 2:  # busy or rate limited: wait and try again
                time.sleep(2 * (attempt + 1))
                continue
            try:
                detail = exc.read().decode(errors="replace")[:300]
            except Exception:
                detail = ""
            raise HTTPException(status_code=502, detail=f"AI engine returned HTTP {exc.code}: {detail}")
        except (urllib.error.URLError, TimeoutError):
            raise HTTPException(status_code=503, detail="AI engine is not reachable")
        except ValueError:
            raise HTTPException(status_code=502, detail="AI engine returned an unreadable answer")

def list_ollama_models() -> list:
    raw = _call(f"{config.OLLAMA_URL.rstrip('/')}/api/tags", None, {})
    return sorted(m["name"] for m in raw.get("models", []) if "name" in m)


def _clean_json(text: str):
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`").strip()
        if t.lower().startswith("json"):
            t = t[4:].strip()
    return json.loads(t)


def generate_json(prompt: str, engine: Optional[str] = None, model: Optional[str] = None) -> tuple:
    """engine is OLLAMA or WEB_API (empty = server default). Returns (answer, engine, model_name)."""
    chosen = _ENGINES.get((engine or config.AI_ENGINE or "").upper())
    if chosen == "ollama":
        used = model or config.OLLAMA_MODEL
        raw = _call(f"{config.OLLAMA_URL.rstrip('/')}/api/generate",
                    {"model": used, "prompt": prompt, "stream": False, "format": "json"}, {})
        answer = raw.get("response", "")
    elif chosen == "cloud":
        if not config.WEB_API_KEY:
            raise HTTPException(status_code=503, detail="Cloud AI is not configured (WEB_API_KEY is empty in the AIDAA .env)")
        used = (model or config.WEB_API_MODEL).strip()
        body: dict = {"model": used,
                      "messages": [{"role": "user", "content": prompt}],
                      "response_format": {"type": "json_object"},
                      "stream": False}
        if config.WEB_API_THINKING:  # DeepSeek thinking toggle; omitted entirely for other providers
            body["thinking"] = {"type": config.WEB_API_THINKING}
        raw = _call(f"{config.WEB_API_BASE_URL}/chat/completions", body,
                    {"Authorization": f"Bearer {config.WEB_API_KEY}"})
        choices = raw.get("choices") or []
        if not choices:
            err = raw.get("error") or raw
            raise HTTPException(status_code=502, detail=f"Cloud AI returned no answer ({err})")
        answer = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not answer:
            raise HTTPException(status_code=502, detail=f"Cloud AI returned an empty answer ({choices[0].get('finish_reason')})")
    else:
        raise HTTPException(status_code=503, detail="AI_ENGINE must be OLLAMA or WEB_API")
    try:
        return _clean_json(answer), chosen, used
    except ValueError:
        raise HTTPException(status_code=502, detail="AI engine did not return valid JSON, try again")