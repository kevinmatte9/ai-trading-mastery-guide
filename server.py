# server.py
import os, requests
from flask import Flask, request, jsonify

app = Flask(__name__)

CRYPTOMETER_API = "https://api.cryptometer.io"
API_KEY = os.getenv("CRYPTOMETER_API_KEY")  # définie sur Render

@app.get("/")
def index():
    return jsonify({
        "success": True,
        "message": "Middleware up. Use /health or /cm/<endpoint>. Examples: /cm/info/ | /cm/open-interest/?exchange=bybit&market_pair=btcusdt"
    })

@app.get("/health")
def health():
    return jsonify({"success": True, "status": "ok"})

def _cm_headers():
    if not API_KEY:
        return None, jsonify({"success": False, "error": "Missing CRYPTOMETER_API_KEY"}), 500
    return {"Authorization": f"Bearer {API_KEY}"}, None, None

@app.get("/cm/<path:endpoint>")
def cm_proxy(endpoint):
    headers, err_resp, status = _cm_headers()
    if err_resp: return err_resp, status

    url = f"{CRYPTOMETER_API}/{endpoint.lstrip('/')}"
    if not url.endswith("/"):
        url += "/"

    try:
        r = requests.get(url, params=request.args, headers=headers, timeout=20)
        return (r.json(), r.status_code)
    except requests.RequestException as e:
        return jsonify({"success": False, "error": str(e)}), 502
