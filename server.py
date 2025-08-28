from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

API_KEY = "b608Hg1obDdaNeLW4TpF1qL5530pwF7K1vpG9exR"

@app.route("/price")
def get_price():
    symbol = request.args.get("symbol", "ETHUSDT")
    url = f"https://api.cryptometer.io/v1/markets?exchange=binance&symbol={symbol}"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    response = requests.get(url, headers=headers)
    return jsonify(response.json())

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
