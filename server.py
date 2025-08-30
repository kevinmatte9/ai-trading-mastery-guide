# server.py
# Flask middleware extensible pour agréger plusieurs APIs (CryptoMeter, QuantConnect, etc.)

import os
import time
from typing import Any, Dict, Optional, Tuple
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# ==========
# Config
# ==========
CRYPTO_API_KEY = os.getenv("API_KEY")                # <- ta clé CryptoMeter (déjà en place)
QC_API_KEY      = os.getenv("QuantConnect_API") or os.getenv("QC_API_KEY")  # <- ta clé QuantConnect

# Si tu utilises un base URL personnalisé pour QuantConnect plus tard, tu peux le poser ici
QC_BASE_URL = os.getenv("QC_BASE_URL", "").strip()   # optionnel, vide par défaut

# ==========
# Mini cache mémoire (TTL) pour alléger les appels
# ==========
_cache: Dict[str, Tuple[float, Any]] = {}
def cache_get(key: str, ttl_sec: int) -> Optional[Any]:
    now = time.time()
    item = _cache.get(key)
    if not item:
        return None
    ts, data = item
    if now - ts > ttl_sec:
        _cache.pop(key, None)
        return None
    return data

def cache_set(key: str, value: Any) -> None:
    _cache[key] = (time.time(), value)

# ==========
# Utilitaires HTTP
# ==========
def http_get(url: str, params: Dict[str, Any] = None, headers: Dict[str, str] = None, timeout: int = 20):
    try:
        r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
        # On renvoie toujours la réponse brute + code pour gérer proprement côté middleware
        return r.status_code, (r.json() if "application/json" in r.headers.get("Content-Type","") else r.text)
    except requests.RequestException as e:
        return 599, {"error": str(e)}

# ==========
# Providers
# ==========
class CryptoMeterProvider:
    """
    Provider CryptoMeter — proxy simple vers ton compte.
    Les routes ci-dessous restent compatibles avec tes actions existantes:
      - /coinlist/?e=binance
      - /ticker/?e=binance&market_pair=BTCUSDT
      - /tickerlist/?e=binance
      - /info/
    """
    BASE = "https://cryptometer.io"  # le middleware amont peut varier; à ajuster si besoin

    @staticmethod
    def _hdr():
        if not CRYPTO_API_KEY:
            return {}
        # La plupart des API attendent un header Authorization ou X-API-KEY; ajuste si besoin :
        return {"Authorization": f"Bearer {CRYPTO_API_KEY}", "X-API-KEY": CRYPTO_API_KEY}

    @classmethod
    def coinlist(cls, e: str):
        # Exemple d’endpoint amont (à adapter selon ta doc CryptoMeter)
        url = f"{cls.BASE}/coinlist"
        return http_get(url, params={"e": e}, headers=cls._hdr())

    @classmethod
    def ticker(cls, e: str, market_pair: str):
        url = f"{cls.BASE}/ticker"
        return http_get(url, params={"e": e, "market_pair": market_pair}, headers=cls._hdr())

    @classmethod
    def tickerlist(cls, e: str):
        url = f"{cls.BASE}/tickerlist"
        return http_get(url, params={"e": e}, headers=cls._hdr())

    @classmethod
    def info(cls):
        url = f"{cls.BASE}/info"
        return http_get(url, headers=cls._hdr())

class QuantConnectProvider:
    """
    Squelette QuantConnect.
    - Clé lue dans QuantConnect_API (ou QC_API_KEY).
    - BASE optionnelle dans QC_BASE_URL (sinon laisse vide et utilise des endpoints spécifiques quand tu les décideras).
    Remplis/active les méthodes dont tu as besoin (quote, history, etc.) en fonction des endpoints QC que tu veux appeler.
    """
    @staticmethod
    def _hdr():
        if not QC_API_KEY:
            return {}
        # Exemple générique; adapte selon l’auth QC réelle (Bearer / X-API-KEY / Cookie…)
        return {"Authorization": f"Bearer {QC_API_KEY}", "X-API-KEY": QC_API_KEY}

    @classmethod
    def ready(cls) -> bool:
        return bool(QC_API_KEY and QC_BASE_URL)

    @classmethod
    def ping(cls):
        if not cls.ready():
            return 501, {"error": "QuantConnect non configuré. Renseigne QuantConnect_API et QC_BASE_URL.", "success": False}
        return http_get(f"{QC_BASE_URL}/ping", headers=cls._hdr())

    @classmethod
    def quote(cls, symbol: str):
        if not cls.ready():
            return 501, {"error": "QuantConnect non configuré. Renseigne QuantConnect_API et QC_BASE_URL.", "success": False}
        # Ex. fictif; remplace par l’endpoint QC exact que tu utiliseras
        url = f"{QC_BASE_URL}/data/quote"
        return http_get(url, params={"symbol": symbol}, headers=cls._hdr())

    @classmethod
    def history(cls, symbol: str, resolution: str = "minute", lookback: int = 1440):
        if not cls.ready():
            return 501, {"error": "QuantConnect non configuré. Renseigne QuantConnect_API et QC_BASE_URL.", "success": False}
        # Ex. fictif; remplace par l’endpoint QC exact
        url = f"{QC_BASE_URL}/data/history"
        return http_get(url, params={"symbol": symbol, "resolution": resolution, "lookback": lookback}, headers=cls._hdr())

# ==========
# Routes publiques (stables pour tes actions actuelles)
# ==========
@app.get("/")
def ping():
    return jsonify({"status": "ok", "providers": {
        "cryptometer": bool(CRYPTO_API_KEY),
        "quantconnect_key": bool(QC_API_KEY),
        "quantconnect_ready": QuantConnectProvider.ready()
    }})

@app.get("/coinlist/")
def coinlist():
    e = request.args.get("e", "").strip()
    if not e:
        return jsonify({"success": False, "error": "e (exchange) est requis"}), 400

    cache_key = f"coinlist:{e}"
    cached = cache_get(cache_key, ttl_sec=60)  # 1 minute
    if cached:
        return jsonify({"success": True, "data": cached})

    code, data = CryptoMeterProvider.coinlist(e)
    if code == 200:
        cache_set(cache_key, data)
        return jsonify({"success": True, "data": data})
    return jsonify({"success": False, "error": data}), code

@app.get("/ticker/")
def ticker():
    e = request.args.get("e", "").strip()
    pair = request.args.get("market_pair", "").strip()
    if not e or not pair:
        return jsonify({"success": False, "error": "Paramètres requis: e, market_pair"}), 400
    code, data = CryptoMeterProvider.ticker(e, pair)
    return (jsonify({"success": True, "data": data}), 200) if code == 200 else (jsonify({"success": False, "error": data}), code)

@app.get("/tickerlist/")
def tickerlist():
    e = request.args.get("e", "").strip()
    if not e:
        return jsonify({"success": False, "error": "e (exchange) est requis"}), 400
    code, data = CryptoMeterProvider.tickerlist(e)
    return (jsonify({"success": True, "data": data}), 200) if code == 200 else (jsonify({"success": False, "error": data}), code)

@app.get("/info/")
def info():
    code, data = CryptoMeterProvider.info()
    return (jsonify({"success": True, "data": data}), 200) if code == 200 else (jsonify({"success": False, "error": data}), code)

# ==========
# Pré-routes QuantConnect (tu pourras en créer d’autres très facilement)
# ==========
@app.get("/qc/ping")
def qc_ping():
    code, data = QuantConnectProvider.ping()
    return (jsonify({"success": code == 200, "data" if code == 200 else "error": data}), code)

@app.get("/qc/quote")
def qc_quote():
    symbol = request.args.get("symbol", "").strip().upper()
    if not symbol:
        return jsonify({"success": False, "error": "symbol est requis"}), 400
    code, data = QuantConnectProvider.quote(symbol)
    return (jsonify({"success": code == 200, "data" if code == 200 else "error": data}), code)

@app.get("/qc/history")
def qc_history():
    symbol = request.args.get("symbol", "").strip().upper()
    resolution = request.args.get("resolution", "minute")
    lookback = int(request.args.get("lookback", "1440"))
    if not symbol:
        return jsonify({"success": False, "error": "symbol est requis"}), 400
    code, data = QuantConnectProvider.history(symbol, resolution, lookback)
    return (jsonify({"success": code == 200, "data" if code == 200 else "error": data}), code)

# ==========
# Lancement
# ==========
if __name__ == "__main__":
    # Pour exécution locale; Render utilisera gunicorn via Procfile
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
