# server.py
# Middleware unique: CryptoMeter (proxy) + OpenAI text (/gen)
# Auth requise: ?api_key=<clé> OU Authorization: Bearer <clé>
# ENV requis sur Render:
#   QuantConnect_API                -> clé d'accès à TON middleware
#   UPSTREAM_BASE_URL               -> https://api.cryptometer.io
#   UPSTREAM_API_KEY                -> ta clé CryptoMeter
#   UPSTREAM_API_KEY_NAME           -> api_key   (ou ce que CryptoMeter exige)
#   UPSTREAM_AUTH_MODE              -> query     (ou 'bearer')
#   OPENAI_API_KEY                  -> ta clé OpenAI
#   OPENAI_BASE_URL                 -> https://api.openai.com
#   OPENAI_MODEL                    -> gpt-4o-mini (ou autre modèle)

import os
import time
from typing import Dict, Any, Tuple, Optional

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ============
# Sécurité API
# ============
EXPECTED_API_KEY = os.getenv("QuantConnect_API")  # NOM EXACT sur Render

def _auth_fail(msg: str, code: int = 401):
    return jsonify({"success": "false", "error": msg}), code

def require_api_key() -> Optional[Tuple[Any, int]]:
    """Vérifie ?api_key=... ou Authorization: Bearer <clé>."""
    if not EXPECTED_API_KEY:
        return _auth_fail("server_missing_api_key_env", 500)

    sent = request.args.get("api_key")
    if not sent:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            sent = auth[7:]

    if not sent:
        return _auth_fail("api_key is missing", 401)
    if sent != EXPECTED_API_KEY:
        return _auth_fail("api_key is missing or invalid", 401)
    return None  # OK

# ============
# Mini cache
# ============
_cache: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 30

def cache_get(key: str):
    v = _cache.get(key)
    if not v:
        return None
    ts, data = v
    if time.time() - ts > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return data

def cache_put(key: str, data: Any):
    _cache[key] = (time.time(), data)

# ==========================
# Config amont CryptoMeter
# ==========================
UP_BASE   = os.getenv("UPSTREAM_BASE_URL", "https://api.cryptometer.io")
UP_KEY    = os.getenv("UPSTREAM_API_KEY", "")
UP_KEYNAM = os.getenv("UPSTREAM_API_KEY_NAME", "api_key")
UP_AUTH   = os.getenv("UPSTREAM_AUTH_MODE", "query")  # "query" ou "bearer"

def upstream_get(path: str, params: Dict[str, Any]):
    """Relais GET vers l'amont (clé en query ou bearer)."""
    if not UP_KEY:
        return _auth_fail("upstream_key_missing", 500)

    url = f"{UP_BASE.rstrip('/')}/{path.lstrip('/')}"
    headers: Dict[str, str] = {}
    q = dict(params)

    if UP_AUTH.lower() == "bearer":
        headers["Authorization"] = f"Bearer {UP_KEY}"
    else:
        q[UP_KEYNAM] = UP_KEY  # par défaut: ?api_key=

    try:
        r = requests.get(url, params=q, headers=headers, timeout=15)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 502
        return jsonify({"success": "false", "error": f"upstream_http_{code}"}), 502
    except Exception:
        return jsonify({"success": "false", "error": "upstream_unreachable"}), 502

# ==========================
# Config OpenAI (texte)
# ==========================
OA_KEY   = os.getenv("OPENAI_API_KEY", "")
OA_BASE  = os.getenv("OPENAI_BASE_URL", "https://api.openai.com")
OA_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

def openai_generate(prompt: str, style: str = ""):
    """Appel simple à OpenAI Chat Completions."""
    if not OA_KEY:
        return _auth_fail("openai_key_missing", 500)

    url = f"{OA_BASE.rstrip('/')}/v1/chat/completions"
    sys_msg = "You are a helpful trading assistant. Write concise, clear French."
    if style:
        sys_msg += f" Adopt this style/tone: {style}"

    payload = {
        "model": OA_MODEL,
        "messages": [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.4,
        "max_tokens": 800
    }
    headers = {
        "Authorization": f"Bearer {OA_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        return jsonify({"success": "true", "error": "false", "text": text})
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 502
        return jsonify({"success": "false", "error": f"openai_http_{code}"}), 502
    except Exception:
        return jsonify({"success": "false", "error": "openai_unreachable"}), 502

# ==========
# ENDPOINTS
# ==========
@app.get("/")
def ping():
    auth = require_api_key()
    if auth:
        return auth
    return jsonify({"status": "ok", "message": "Server is running"})

@app.get("/coinlist/")
def get_coinlist():
    auth = require_api_key()
    if auth:
        return auth

    e = (request.args.get("e") or "").strip().lower()
    if not e:
        return jsonify({"success": "false", "error": "param_e_missing"}), 400

    cache_key = f"coinlist:{e}"
    cached = cache_get(cache_key)
    if cached:
        return jsonify(cached)

    resp = upstream_get("/coinlist/", {"e": e})
    try:
        data = resp.get_json(silent=True) or {}
        if data.get("success") == "true":
            cache_put(cache_key, data)
    except Exception:
        pass
    return resp

@app.get("/ticker/")
def get_ticker():
    auth = require_api_key()
    if auth:
        return auth

    e  = (request.args.get("e") or "").strip().lower()
    mp = (request.args.get("market_pair") or "").strip().upper()
    if not e:
        return jsonify({"success": "false", "error": "param_e_missing"}), 400
    if not mp:
        return jsonify({"success": "false", "error": "market_pair is missing"}), 400
    return upstream_get("/ticker/", {"e": e, "market_pair": mp})

@app.get("/tickerlist/")
def get_tickerlist():
    auth = require_api_key()
    if auth:
        return auth

    e = (request.args.get("e") or "").strip().lower()
    if not e:
        return jsonify({"success": "false", "error": "param_e_missing"}), 400
    return upstream_get("/tickerlist/", {"e": e})

@app.get("/info/")
def get_api_usage_info():
    auth = require_api_key()
    if auth:
        return auth

    return jsonify({
        "success": "true",
        "error": "false",
        "env_ok": bool(EXPECTED_API_KEY),
        "env_var": "QuantConnect_API",
        "upstream": {
            "base_url": UP_BASE,
            "auth_mode": UP_AUTH,
            "key_name": UP_KEYNAM,
            "has_key": bool(UP_KEY)
        }
    })

@app.get("/limits/")
def get_limits():
    auth = require_api_key()
    if auth:
        return auth
    return upstream_get("/limits/", {})

@app.post("/gen/")
def gen_text():
    """Génère du texte via OpenAI. Body: { "prompt": "...", "style": "optionnel" }"""
    auth = require_api_key()
    if auth:
        return auth

    body = request.get_json(silent=True) or {}
    prompt = (body.get("prompt") or "").strip()
    style  = (body.get("style") or "").strip()
    if not prompt:
        return jsonify({"success": "false", "error": "prompt_missing"}), 400
    return openai_generate(prompt, style)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
