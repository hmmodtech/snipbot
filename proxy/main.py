"""
SnipBot API Proxy — v4
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import ccxt
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
    try:
        trades_list = get_trades()
        orders_list = get_orders()

        buy_trades  = [t for t in trades_list if "BUY"  in str(t.get("type", ""))]
        sell_trades = [t for t in trades_list if "SELL" in str(t.get("type", ""))]

        total_bought = sum(float(t.get("cost", 0)) for t in buy_trades)
        total_sold   = sum(float(t.get("cost", 0)) for t in sell_trades)
        pnl          = round(total_sold - total_bought, 4)

        locked    = round(sum(float(o.get("cost", 0)) for o in orders_list), 2)
        BASE_CAPITAL = 10000.0
        net_spent = round(total_bought - total_sold, 2)
        free_usdt = round(BASE_CAPITAL - net_spent - locked, 2)

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
    try:
        data = get_trades()
        sorted_trades = sorted(data, key=lambda x: x.get("time", 0), reverse=True)
        return jsonify({"source": "live", "count": len(sorted_trades), "trades": sorted_trades})
    except Exception as e:
        log.error(f"[Proxy] trades error: {e}")
        return jsonify({"source": "error", "count": 0, "trades": []})


@app.route("/api/orders")
def orders():
    try:
        data = get_orders()
        return jsonify({"source": "live", "count": len(data), "orders": data})
    except Exception as e:
        log.error(f"[Proxy] orders error: {e}")
        return jsonify({"source": "error", "count": 0, "orders": []})


@app.route("/api/summary")
def summary():
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
                "total":     10000.0,
                "free_usdt": 10000.0,
                "pnl":       round(pnl, 4),
                "pnl_pct":   round((pnl / 10000) * 100, 3)
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


@app.route("/status")
def status():
    return jsonify({
        "proxy":   "online",
        "octobot": OCTOBOT_URL,
        "time":    datetime.utcnow().isoformat()
    })


@app.route("/api/telegram/send", methods=["POST"])
def telegram_send():
    try:
        data    = request.get_json()
        message = data.get("message", "")
        token   = os.getenv("TELEGRAM_TOKEN", "")
        chat_id = os.getenv("CHAT_ID", "")
        if not token or not chat_id:
            return jsonify({"status": "no_token"}), 200
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            timeout=8
        )
        return jsonify({"status": "sent", "ok": r.status_code == 200})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


# ══════════════════════════════════════════════════════════════════
# NEW: Multi-Exchange Balance
# POST /api/exchange_balance
# Body: { exchange, api_key, secret, password, mode }
# ══════════════════════════════════════════════════════════════════
@app.route("/api/exchange_balance", methods=["POST"])
def exchange_balance():
    body = request.get_json(silent=True) or {}

    exchange_id = body.get("exchange", "").lower().strip()
    api_key     = body.get("api_key",  body.get("apiKey", "")).strip()
    secret      = body.get("secret",   "").strip()
    password    = body.get("password", "").strip()
    mode        = body.get("mode",     "paper")

    if not exchange_id:
        return jsonify({"error": "exchange field required"}), 400
    if not api_key or not secret:
        return jsonify({"error": "api_key and secret required"}), 400

    SUPPORTED = ["kucoin", "binance", "bybit", "okx",
                 "kraken", "bitget", "gateio"]
    if exchange_id not in SUPPORTED:
        return jsonify({"error": f"'{exchange_id}' not supported"}), 400

    try:
        # Build ccxt instance
        ex_class = getattr(ccxt, exchange_id)
        config   = {
            "apiKey":          api_key,
            "secret":          secret,
            "enableRateLimit": True,
            "options":         {"defaultType": "spot"},
        }
        if password:
            config["password"] = password

        ex = ex_class(config)

        # Enable sandbox for paper mode
        if mode == "paper":
            try:
                ex.set_sandbox_mode(True)
            except Exception:
                pass

        # Fetch balance
        balance      = ex.fetch_balance()
        total_usdt   = 0.0
        free_usdt    = 0.0
        active_pairs = []

        for asset, amt in (balance.get("total") or {}).items():
            if not amt or float(amt) <= 0:
                continue
            val = float(amt)
            if asset in ("USDT", "USDC", "BUSD", "TUSD"):
                total_usdt += val
                free_usdt  += float((balance.get("free") or {}).get(asset, 0) or 0)
            else:
                try:
                    ticker = ex.fetch_ticker(f"{asset}/USDT")
                    price  = float(ticker.get("last") or 0)
                    worth  = val * price
                    total_usdt += worth
                    if worth > 1:
                        active_pairs.append(f"{asset}/USDT")
                except Exception:
                    pass

        # PnL from open positions (futures/margin)
        pnl = 0.0
        try:
            for pos in (ex.fetch_positions() or []):
                pnl += float(pos.get("unrealizedPnl") or 0)
                if float(pos.get("contracts") or 0) > 0:
                    sym = pos.get("symbol", "")
                    if sym and sym not in active_pairs:
                        active_pairs.append(sym)
        except Exception:
            pass

        log.info(f"🔎 [Proxy]: {exchange_id} balance — ${total_usdt:.0f} USDT ({mode})")

        return jsonify({
            "status":       "live",
            "exchange":     exchange_id,
            "mode":         mode,
            "total_usdt":   round(total_usdt, 2),
            "free_usdt":    round(free_usdt,  2),
            "used_usdt":    round(total_usdt - free_usdt, 2),
            "active_pairs": active_pairs[:5],
            "pnl":          round(pnl, 2),
        })

    except ccxt.AuthenticationError:
        log.warning(f"[Proxy] Auth error — {exchange_id}")
        return jsonify({
            "status":   "auth_error",
            "error":    "Authentication failed — check API key and secret",
            "exchange": exchange_id,
        }), 401

    except ccxt.NetworkError as e:
        return jsonify({"status": "network_error", "error": str(e)}), 503

    except ccxt.ExchangeError as e:
        return jsonify({"status": "exchange_error", "error": str(e)}), 502

    except Exception as e:
        log.error(f"[Proxy] exchange_balance error: {e}", exc_info=True)
        return jsonify({"status": "error", "error": str(e)[:200]}), 500


if __name__ == "__main__":
    log.info(f"[SnipBot Proxy]: Starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
