 # server.py
# AI Trading Middleware – version sécurisée par clé API
# - Protège tous les endpoints avec une clé envoyée en ?api_key=... ou en header Authorization: Bearer <clé>
# - Lit la clé attendue dans la variable d'environnement: QuantConnect_API
# - Fournit des endpoints compatibles avec ton schéma OpenAPI: /, /coinlist/, /ticker/, /tickerlist/, /info/
# - Réponses JSON homogènes: {"success": "true"|"false", ...}

import os
import time
from typing import Dict, Any, Tuple, Optional
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
    """
    Vérifie la clé API dans:
      - ?api_key=... (querystring), OU
      - Authorization: Bearer <clé> (header).
    """
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


# ================
# MOCK / FALLBACKS
# ================
# NOTE: En attendant la connexion “live” aux providers en amont,
# on sert des données de démonstration conformes aux formats attendus.
# On branchera l’amont (CryptoMeter, etc.) plus tard si besoin.

MOCK_COINLIST = {
    "binance": [
        {"market_pair": "BTCUSDT", "pair": "BTC-USDT"},
        {"market_pair": "ETHUSDT", "pair": "ETH-USDT"},
        {"market_pair": "BNBUSDT", "pair": "BNB-USDT"},
    ]
}

def demo_orderbook(symbol: str):
    # Snapshot d’orderbook minimal pour démo
    return {
        "data": [{
            "symbol": symbol,
            "bids": 415.37,
            "asks": 519.01
        }],
        "success": "true",
        "error": "false"
    }


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
        return jsonify({"data": cached, "success": "true", "error": "false"})

    data = MOCK_COINLIST.get(e)
    if not data:
        # Exchange pas dans la démo -> message explicite
        return jsonify({"success": "false", "error": f"exchange_not_supported_demo:{e}"}), 404

    cache_put(cache_key, data)
    return jsonify({"data": data, "success": "true", "error": "false"})

@app.get("/ticker/")
def get_ticker():
    auth = require_api_key()
    if auth: 
        return auth

    e = (request.args.get("e") or "").strip().lower()
    mp = (request.args.get("market_pair") or "").strip().upper()

    if not e:
        return jsonify({"success": "false", "error": "param_e_missing"}), 400
    if not mp:
        return jsonify({"success": "false", "error": "market_pair is missing"}), 400

    # Démo simple
    return jsonify(demo_orderbook(mp))

@app.get("/tickerlist/")
def get_tickerlist():
    auth = require_api_key()
    if auth: 
        return auth

    e = (request.args.get("e") or "").strip().lower()
    if not e:
        return jsonify({"success": "false", "error": "param_e_missing"}), 400

    # Démo: retourne 3 tickers “orderbook” pour l’exchange demandé
    symbols = [x["market_pair"] for x in MOCK_COINLIST.get(e, [])]
    if not symbols:
        return jsonify({"success": "false", "error": f"exchange_not_supported_demo:{e}"}), 404

    data = [demo_orderbook(sym)["data"][0] for sym in symbols]
    return jsonify({"data": data, "success": "true", "error": "false"})

@app.get("/info/")
def get_api_usage_info():
    auth = require_api_key()
    if auth: 
        return auth

    # Démo: renvoie juste l’état de la variable d’environnement
    return jsonify({
        "success": "true",
        "error": "false",
        "env_ok": bool(EXPECTED_API_KEY),
        "env_var": "QuantConnect_API"
    })


if __name__ == "__main__":
    # Pour lancement local éventuel: python server.py
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
