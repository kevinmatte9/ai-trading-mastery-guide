import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Config ---
BASE_URL = "https://api.cryptometer.io"   # endpoint officiel CryptoMeter
API_KEY = os.getenv("API_KEY")            # ta clé est stockée sur Render (Env var)

# Sécurité : on refuse de démarrer si la clé manque (utile en local)
if not API_KEY:
    print("WARNING: Missing API_KEY environment variable. Set it on Render.")

# Utilitaire : propage la requête vers CryptoMeter en ajoutant api_key
def forward_to_cm(path):
    try:
        # On reprend tous les query params de l'appel entrant…
        params = dict(request.args)

        # …et on force la clé requise par CryptoMeter
        params["api_key"] = API_KEY

        # Appel côté CryptoMeter
        url = f"{BASE_URL}{path}"
        resp = requests.get(url, params=params, timeout=20)

        # Renvoie la réponse telle quelle (status + JSON)
        return (jsonify(resp.json()), resp.status_code)
    except requests.exceptions.Timeout:
        return jsonify({"success": False, "message": "Upstream timeout"}), 504
    except Exception as e:
        return jsonify({"success": False, "message": f"Proxy error: {str(e)}"}), 500


# --- Health / Info ---
@app.get("/")
def root():
    return jsonify({"status": "ok", "success": True})

@app.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@app.get("/info/")
def info():
    # point d’info de CryptoMeter (utilise aussi la clé)
    return forward_to_cm("/info/")


# --- Endpoints exposés à ton Custom GPT ---
# (on mappe chaque route de ton schéma OpenAPI vers le proxy)

@app.get("/coinlist/")
def coinlist():
    return forward_to_cm("/coinlist/")

@app.get("/cryptocurrency-info/")
def cryptocurrency_info():
    return forward_to_cm("/cryptocurrency-info/")

@app.get("/coininfo/")
def coininfo():
    return forward_to_cm("/coininfo/")

@app.get("/tickerlist/")
def tickerlist():
    return forward_to_cm("/tickerlist/")

@app.get("/ticker/")
def ticker():
    return forward_to_cm("/ticker/")

@app.get("/trend-indicator-v3/")
def trend_indicator_v3():
    return forward_to_cm("/trend-indicator-v3/")

@app.get("/forex-rates/")
def forex_rates():
    return forward_to_cm("/forex-rates/")

@app.get("/ai-screener/")
def ai_screener():
    return forward_to_cm("/ai-screener/")

@app.get("/ai-screener-analysis/")
def ai_screener_analysis():
    return forward_to_cm("/ai-screener-analysis/")

@app.get("/ls-ratio/")
def ls_ratio():
    return forward_to_cm("/ls-ratio/")

@app.get("/liquidation-data-v2/")
def liquidation_data_v2():
    return forward_to_cm("/liquidation-data-v2/")

@app.get("/bitmex-liquidation/")
def bitmex_liquidation():
    return forward_to_cm("/bitmex-liquidation/")

@app.get("/rapid-movements/")
def rapid_movements():
    return forward_to_cm("/rapid-movements/")

@app.get("/24h-trade-volume-v2/")
def trade_volume_24h_v2():
    return forward_to_cm("/24h-trade-volume-v2/")

@app.get("/open-interest/")
def open_interest():
    return forward_to_cm("/open-interest/")

@app.get("/volume-flow/")
def volume_flow():
    return forward_to_cm("/volume-flow/")

@app.get("/liquidity-lens/")
def liquidity_lens():
    return forward_to_cm("/liquidity-lens/")

@app.get("/merged-orderbook/")
def merged_orderbook():
    return forward_to_cm("/merged-orderbook/")

@app.get("/large-trades-activity/")
def large_trades_activity():
    return forward_to_cm("/large-trades-activity/")

@app.get("/merged-trade-volume/")
def merged_trade_volume():
    return forward_to_cm("/merged-trade-volume/")
