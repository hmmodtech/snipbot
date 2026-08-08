"""
SnipBot API Proxy — v3 Fixed
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import os
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("SnipBot-Proxy")

OCTOBOT_URL = os.getenv("OCTOBOT_URL", "https://snipbot-y.up.railway.app")
PORT        = int(os.getenv("PORT", 8080))

# ── Agent Radar Store ──
_agents_store = {
    "timestamp":  None,
    "signals":    [],
    "strategies": [],
    "symbols":    []
}


def get_trades():
    try:
        r = requests.get(f"{OCTOBOT_URL}/api/trades", timeout=8)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
        return []
    except Exception as e:
        log.error(f"[Proxy] trades error: {e}")
        return []


def get_orders():
    try:
        r = requests.get(f"{OCTOBOT_URL}/api/orders", timeout=8)
        if r.status_code == 200:
            data = r.json()
            return data if isinstance(data, list) else []
        return []
    except Exception as e:
        log.error(f"[Proxy] orders error: {e}")
        return []


@app.route("/health")
def health():
    trades = get_trades()
    octobot_live = trades is not None
    return jsonify({
        "proxy":       "online",
        "octobot":     "connected" if octobot_live else "disconnected",
        "octobot_url": OCTOBOT_URL,
        "timestamp":   datetime.utcnow().isoformat()
    })


@app.route("/api/portfolio")
def portfolio():
    """بيانات المحفظة"""
    try:
        trades_list = get_trades()
        orders_list = get_orders()

        buy_trades  = [t for t in trades_list if "BUY"  in str(t.get("type", ""))]
        sell_trades = [t for t in trades_list if "SELL" in str(t.get("type", ""))]

        total_bought = sum(float(t.get("cost", 0)) for t in buy_trades)
        total_sold   = sum(float(t.get("cost", 0)) for t in sell_trades)
        pnl          = round(total_sold - total_bought, 4)

        locked = sum(float(o.get("cost", 0)) for o in orders_list)
        locked = round(locked, 2)

        # رأس المال الأساسي $10,000
        BASE_CAPITAL = 10000.0
        net_spent    = round(total_bought - total_sold, 2)
        free_usdt    = round(BASE_CAPITAL - net_spent - locked, 2)

        return jsonify({
            "source":                "live",
            "total_portfolio_value": BASE_CAPITAL,
            "free_usdt":             max(free_usdt, 0),
            "locked_usdt":           locked,
            "currency":              "USDT",
            "total_trades":          len(trades_list),
            "buy_trades":            len(buy_trades),
            "sell_trades":           len(sell_trades),
            "open_orders":           len(orders_list),
            "realized_pnl":          pnl,
            "exchange":              "kucoin",
            "mode":                  "simulated"
        })
    except Exception as e:
        log.error(f"[Proxy] portfolio error: {e}")
        return jsonify({
            "source":                "fallback",
            "total_portfolio_value": 10000.0,
            "free_usdt":             10000.0,
            "locked_usdt":           0.0,
            "currency":              "USDT",
            "realized_pnl":          0,
            "mode":                  "simulated"
        })


@app.route("/api/trades")
def trades():
    """الصفقات المنجزة"""
    try:
        data = get_trades()
        # ترتيب من الأحدث
        sorted_trades = sorted(
            data,
            key=lambda x: x.get("time", 0),
            reverse=True
        )
        return jsonify({
            "source": "live",
            "count":  len(sorted_trades),
            "trades": sorted_trades
        })
    except Exception as e:
        log.error(f"[Proxy] trades error: {e}")
        return jsonify({"source": "error", "count": 0, "trades": []})


@app.route("/api/orders")
def orders():
    """الأوامر المفتوحة"""
    try:
        data = get_orders()
        return jsonify({
            "source": "live",
            "count":  len(data),
            "orders": data
        })
    except Exception as e:
        log.error(f"[Proxy] orders error: {e}")
        return jsonify({"source": "error", "count": 0, "orders": []})


@app.route("/api/summary")
def summary():
    """ملخص شامل"""
    try:
        trades_list = get_trades()
        orders_list = get_orders()

        buy_trades  = [t for t in trades_list if "BUY"  in str(t.get("type", ""))]
        sell_trades = [t for t in trades_list if "SELL" in str(t.get("type", ""))]
        pnl         = sum(float(t.get("cost", 0)) for t in sell_trades) - \
                      sum(float(t.get("cost", 0)) for t in buy_trades)

        last_trade = {}
        if trades_list:
            st = sorted(trades_list, key=lambda x: x.get("time", 0), reverse=True)
            last_trade = st[0]

        return jsonify({
            "source": "live",
            "portfolio": {
                "total":      10000.0,
                "free_usdt":  10000.0,
                "pnl":        round(pnl, 4),
                "pnl_pct":    round((pnl / 10000) * 100, 3)
            },
            "activity": {
                "total_trades": len(trades_list),
                "buy_count":    len(buy_trades),
                "sell_count":   len(sell_trades),
                "open_orders":  len(orders_list)
            },
            "last_trade": {
                "symbol": last_trade.get("symbol", "—"),
                "type":   last_trade.get("type",   "—"),
                "price":  last_trade.get("price",  0),
                "date":   last_trade.get("date",   "—")
            },
            "engine": {
                "status":   "online",
                "exchange": "KuCoin",
                "mode":     "Paper Trading",
                "strategy": "Smart DCA"
            }
        })
    except Exception as e:
        log.error(f"[Proxy] summary error: {e}")
        return jsonify({"source": "error"})


@app.route("/api/agents/update", methods=["POST"])
def agents_update():
    global _agents_store
    try:
        data = request.get_json()
        if data:
            _agents_store = data
            return jsonify({"status": "ok"})
        return jsonify({"status": "empty"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/agents/status")
def agents_status():
    if _agents_store["timestamp"] is None:
        return jsonify({
            "source":    "waiting",
            "timestamp": None,
            "agents": [
                {"name": "TA Analyst",  "action": "SCANNING", "confidence": 0},
                {"name": "Smart DCA+",  "action": "SCANNING", "confidence": 0}
            ],
            "signals": []
        })
    return jsonify({
        "source":    "live",
        "timestamp": _agents_store.get("timestamp"),
        "agents":    _agents_store.get("strategies", []),
        "signals":   _agents_store.get("signals", [])
    })


# ── /status للـ Agents service ──
@app.route("/status")
def status():
    return jsonify({
        "proxy":   "online",
        "octobot": OCTOBOT_URL,
        "time":    datetime.utcnow().isoformat()
    })


if __name__ == "__main__":
    log.info(f"[SnipBot Proxy]: Starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
