# server.py
# AI Trading Middleware – version sécurisée par clé API
# - Protège tous les endpoints avec une clé envoyée en ?api_key=... ou en header Authorization: Bearer <clé>
# - Lit la clé attendue dans la variable d'environnement: QuantConnect_API
# - Relaye les appels vers CryptoMeter (ou autre amont) en lisant:
#     UPSTREAM_BASE_URL, UPSTREAM_API_KEY, UPSTREAM_API_KEY_NAME, UPSTREAM_AUTH_MODE
# - Intègre aussi OpenAI pour générer une analyse rapide via /analyze/
# - Endpoints compatibles OpenAPI: /, /coinlist/, /ticker/, /tickerlist/, /info/, /limits/, /analyze/
# - Réponses JSON homogènes: {"success": "true"|"false", ...}

import os
import time
import json
from typing import Dict, Any, Tuple, Optional

import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ============
# Sécurité API
# ============
EXPECTED_API_KEY = os.getenv("QuantConnect_API")  # NOM EXACT de ta variable Render

def _auth_fail(msg: str, code: int = 401):
    return jsonify({"success": "false", "error": msg}), code

def require_api_key() -> Optional[Tuple[Any, int]]:
    """Vérifie la clé API dans querystring ou header Authorization."""
    if not EXPECTED_API_KEY:
        return _auth_fail("server_missing_api_key_env", 500)

    sent = request.args.get("api_key")
    if not sent:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            sent = auth.replace("Bearer ", "", 1)

    if not sent:
        return _auth_fail("api_key is missing", 401)

    if sent != EXPECTED_API_KEY:
        return _auth_fail("api_key is missing or invalid", 401)

    return None  # OK


# ==========================
# Mini cache (TTL en mémoire)
# ==========================
_cache: Dict[str, Tuple[float, Any]] = {}
CACHE_TTL_SECONDS = 30  # léger cache pour démo

def cache_get(key: str):
    now = time.time()
    v = _cache.get(key)
    if not v:
        return None
    ts, data = v
    if now - ts > CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return data

def cache_put(key: str, data: Any):
    _cache[key] = (time.time(), data)


# ==========================
# Config de l'amont (CryptoMeter)
# ==========================
UP_BASE   = os.getenv("UPSTREAM_BASE_URL", "https://api.cryptometer.io")
UP_KEY    = os.getenv("UPSTREAM_API_KEY", "")
UP_KEYNAM = os.getenv("UPSTREAM_API_KEY_NAME", "api_key")
UP_AUTH   = os.getenv("UPSTREAM_AUTH_MODE", "query")  # "query" ou "bearer"

def upstream_get(path: str, params: Dict[str, Any]):
    """Relais GET vers l'amont avec gestion clé en query ou bearer."""
    if not UP_KEY:
        return _auth_fail("upstream_key_missing", 500)

    url = f"{UP_BASE.rstrip('/')}/{path.lstrip('/')}"
    headers: Dict[str, str] = {}
    q = dict(params)

    if UP_AUTH.lower() == "bearer":
        headers["Authorization"] = f"Bearer {UP_KEY}"
    else:
        q[UP_KEYNAM] = UP_KEY

    try:
        r = requests.get(url, params=q, headers=headers, timeout=12)
        r.raise_for_status()
        return jsonify(r.json())
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 502
        return jsonify({"success": "false", "error": f"upstream_http_{code}"}), 502
    except Exception:
        return jsonify({"success": "false", "error": "upstream_unreachable"}), 502


# ==========================
# Config OpenAI
# ==========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE    = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

def openai_complete(prompt: str) -> Dict[str, Any]:
    """Appel simple à OpenAI pour générer une analyse."""
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "openai_key_missing"}

    url = f"{OPENAI_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": OPENAI_MODEL,
        "messages": [
            {"role": "system", "content": "Tu es un analyste de marché concis. Rédige en français, 6-10 lignes max."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
    }
    try:
        r = requests.post(url, headers=headers, data=json.dumps(body), timeout=20)
        r.raise_for_status()
        j = r.json()
        text = j.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        return {"ok": True, "text": text, "raw": j}
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else 502
        return {"ok": False, "error": f"openai_http_{code}"}
    except Exception:
        return {"ok": False, "error": "openai_unreachable"}


# ==========
# ENDPOINTS
# ==========
@app.get("/")
def ping():
    auth = require_api_key()
    if auth:
        return auth
    return jsonify({"status": "ok", "success": "true"})

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

@app.get("/analyze/")
def analyze_pair():
    auth = require_api_key()
    if auth:
        return auth

    e  = (request.args.get("e") or "").strip().lower()
    mp = (request.args.get("market_pair") or "").strip().upper()
    if not e:
        return jsonify({"success": "false", "error": "param_e_missing"}), 400
    if not mp:
        return jsonify({"success": "false", "error": "market_pair is missing"}), 400

    # 1) Snapshot ticker
    up_resp = upstream_get("/ticker/", {"e": e, "market_pair": mp})
    up_json = (up_resp.get_json(silent=True) or {})
    if up_json.get("success") != "true":
        return jsonify({"success": "false", "error": "upstream_failed", "upstream": up_json}), 502

    rows = up_json.get("data") or []
    snap = rows[0] if rows else {}
    last  = snap.get("last")
    high  = snap.get("high")
    low   = snap.get("low")
    ch1h  = snap.get("change_1h")
    ch24h = snap.get("change_24h")
    ch7d  = snap.get("change_7days")
    vol24 = snap.get("volume_24")

    prompt = (
        f"Donne une lecture rapide du marché pour {mp} sur {e}.\n"
        f"Dernier: {last}, Haut24h: {high}, Bas24h: {low}, "
        f"Var1h: {ch1h}%, Var24h: {ch24h}%, Var7j: {ch7d}%, Volume24h: {vol24}.\n"
        f"Structure en puces: tendance, niveaux clés, momentum, volume, risque, plan d’action prudent."
    )

    ai = openai_complete(prompt)
    if not ai.get("ok"):
        return jsonify({"success": "false", "error": ai.get("error"), "data": snap}), 502

    return jsonify({
        "success": "true",
        "error": "false",
        "pair": mp,
        "exchange": e,
        "analysis": ai.get("text", ""),
        "data": snap
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
