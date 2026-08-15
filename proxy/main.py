"""
SnipBot API Proxy — v5 FIXED
P&L calculation corrected
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

OCTOBOT_URL       = os.getenv("OCTOBOT_URL", "https://snipbot-y.up.railway.app")
AGENTS_SERVICE_URL= os.getenv("AGENTS_SERVICE_URL", "https://agents-snipbot.up.railway.app")
PORT              = int(os.getenv("PORT", 8080))

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


def compute_pnl(trades_list):
    """
    Correct P&L calculation:
    Only count closed pairs (1 BUY matched with 1 SELL).
    Unrealized (open BUY without matching SELL) are excluded.
    """
    buy_trades  = [t for t in trades_list if "BUY"  in str(t.get("type", "")).upper()]
    sell_trades = [t for t in trades_list if "SELL" in str(t.get("type", "")).upper()]

    # Sort by time to match correctly
    buy_trades  = sorted(buy_trades,  key=lambda x: x.get("time", 0))
    sell_trades = sorted(sell_trades, key=lambda x: x.get("time", 0))

    # Only count closed pairs
    closed_count = min(len(buy_trades), len(sell_trades))

    total_bought = sum(float(t.get("cost", t.get("ref_market_cost", 0)) or 0)
                       for t in buy_trades[:closed_count])
    total_sold   = sum(float(t.get("cost", t.get("ref_market_cost", 0)) or 0)
                       for t in sell_trades[:closed_count])

    realized_pnl = round(total_sold - total_bought, 4)

    return {
        "realized_pnl":  realized_pnl,
        "buy_trades":    len(buy_trades),
        "sell_trades":   len(sell_trades),
        "closed_pairs":  closed_count,
        "open_positions": len(buy_trades) - closed_count,
        "total_trades":  len(trades_list),
    }


@app.route("/health")
def health():
    trades = get_trades()
    return jsonify({
        "proxy":       "online",
        "octobot":     "connected" if trades is not None else "disconnected",
        "octobot_url": OCTOBOT_URL,
        "timestamp":   datetime.utcnow().isoformat()
    })


@app.route("/api/portfolio")
def portfolio():
    try:
        trades_list = get_trades()
        orders_list = get_orders()

        pnl_data = compute_pnl(trades_list)

        locked = round(sum(
            float(o.get("cost", o.get("ref_market_cost", 0)) or 0)
            for o in orders_list
        ), 2)

        BASE_CAPITAL = 30000.0
        free_usdt = round(max(BASE_CAPITAL - locked, 0), 2)

        return jsonify({
            "source":                "live",
            "total_portfolio_value": BASE_CAPITAL,
            "free_usdt":             free_usdt,
            "locked_usdt":           locked,
            "currency":              "USDT",
            "total_trades":          pnl_data["total_trades"],
            "buy_trades":            pnl_data["buy_trades"],
            "sell_trades":           pnl_data["sell_trades"],
            "closed_pairs":          pnl_data["closed_pairs"],
            "open_positions":        pnl_data["open_positions"],
            "open_orders":           len(orders_list),
            "realized_pnl":          pnl_data["realized_pnl"],
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
        pnl_data    = compute_pnl(trades_list)

        last_trade = {}
        if trades_list:
            st = sorted(trades_list, key=lambda x: x.get("time", 0), reverse=True)
            last_trade = st[0]

        return jsonify({
            "source": "live",
            "portfolio": {
                "total":          10000.0,
                "free_usdt":      max(10000.0 - sum(float(o.get("cost",0) or 0) for o in orders_list), 0),
                "pnl":            pnl_data["realized_pnl"],
                "pnl_pct":        round((pnl_data["realized_pnl"] / 10000) * 100, 3)
            },
            "activity": {
                "total_trades":   pnl_data["total_trades"],
                "buy_count":      pnl_data["buy_trades"],
                "sell_count":     pnl_data["sell_trades"],
                "closed_pairs":   pnl_data["closed_pairs"],
                "open_positions": pnl_data["open_positions"],
                "open_orders":    len(orders_list)
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
    # Try agents service first
    try:
        r = requests.get(f"{AGENTS_SERVICE_URL}/api/agents/status", timeout=5)
        if r.status_code == 200:
            return jsonify(r.json())
    except Exception:
        pass

    # Fallback to local store
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


@app.route("/api/agents/evaluate")
def agents_evaluate():
    pair = request.args.get("pair", "BTC/USDT")
    tf   = request.args.get("timeframe", "1h")
    try:
        r = requests.get(
            f"{AGENTS_SERVICE_URL}/api/agents/evaluate",
            params={"pair": pair, "timeframe": tf},
            timeout=10
        )
        if r.status_code == 200:
            return jsonify(r.json())
    except Exception as e:
        log.warning(f"[Proxy] agents/evaluate fallback: {e}")
    return jsonify({"status": "error", "error": "Agents service unavailable"}), 503


@app.route("/status")
def status():
    return jsonify({
        "proxy":   "online",
        "octobot": OCTOBOT_URL,
        "agents":  AGENTS_SERVICE_URL,
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


@app.route("/api/ohlcv")
def ohlcv():
    symbol    = request.args.get("symbol", "ADA/USDT")
    timeframe = request.args.get("timeframe", "1h")
    limit     = int(request.args.get("limit", "100"))
    for exchange_id in ["kucoin", "binance"]:
        try:
            ex  = getattr(ccxt, exchange_id)({"enableRateLimit": True})
            raw = ex.fetch_ohlcv(symbol, timeframe, limit=limit)
            if raw and len(raw) > 0:
                candles = [{"t":c[0],"o":float(c[1]),"h":float(c[2]),
                            "l":float(c[3]),"c":float(c[4]),"v":float(c[5])} for c in raw]
                return jsonify({"status":"live","symbol":symbol,"timeframe":timeframe,"candles":candles})
        except Exception as e:
            log.warning(f"[OHLCV] {exchange_id} failed: {e}")
    return jsonify({"status": "error", "error": "No data"}), 500


@app.route("/api/exchange_balance", methods=["POST"])
def exchange_balance():
    body        = request.get_json(silent=True) or {}
    exchange_id = body.get("exchange", "").lower().strip()
    api_key     = body.get("api_key", body.get("apiKey", "")).strip()
    secret      = body.get("secret", "").strip()
    password    = body.get("password", "").strip()
    mode        = body.get("mode", "paper")

    if not exchange_id or not api_key or not secret:
        return jsonify({"error": "exchange, api_key and secret required"}), 400

    try:
        ex_class = getattr(ccxt, exchange_id)
        config   = {"apiKey": api_key, "secret": secret, "enableRateLimit": True}
        if password:
            config["password"] = password
        ex = ex_class(config)
        if mode == "paper":
            try: ex.set_sandbox_mode(True)
            except: pass

        balance      = ex.fetch_balance()
        total_usdt   = 0.0
        free_usdt    = 0.0
        active_pairs = []

        for asset, amt in (balance.get("total") or {}).items():
            if not amt or float(amt) <= 0:
                continue
            val = float(amt)
            if asset in ("USDT","USDC","BUSD","TUSD"):
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
                except: pass

        pnl = 0.0
        try:
            for pos in (ex.fetch_positions() or []):
                pnl += float(pos.get("unrealizedPnl") or 0)
        except: pass

        return jsonify({
            "status":       "live",
            "exchange":     exchange_id,
            "mode":         mode,
            "total_usdt":   round(total_usdt, 2),
            "free_usdt":    round(free_usdt, 2),
            "used_usdt":    round(total_usdt - free_usdt, 2),
            "active_pairs": active_pairs[:5],
            "pnl":          round(pnl, 2),
        })

    except ccxt.AuthenticationError:
        return jsonify({"status":"auth_error","error":"Authentication failed"}), 401
    except ccxt.NetworkError as e:
        return jsonify({"status":"network_error","error":str(e)}), 503
    except Exception as e:
        return jsonify({"status":"error","error":str(e)[:200]}), 500

@app.route("/api/agents/evaluate")
def agents_evaluate():
    """
    يمرر طلب التحليل للـ Agents service
    ويرجع النتيجة للـ Dashboard
    """
    pair = request.args.get("pair", "BTC/USDT")
    
    AGENTS_URL = os.getenv("AGENTS_SERVICE_URL", "https://agents-snipbot.up.railway.app")

    try:
        # يحاول يجيب من الـ Agents مباشرة
        r = requests.get(
            f"{AGENTS_URL}/api/agents/evaluate",
            params={"pair": pair},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            data["source"] = "live"
            data["pair"]   = pair
            return jsonify(data)

    except Exception as e:
        log.warning(f"[Proxy] Agents service unreachable: {e}")

    # Fallback — يجيب من الـ store المحفوظ
    signals = _agents_store.get("signals", [])
    pair_signals = [
        s for s in signals
        if s.get("pair") == pair or s.get("symbol") == pair
    ]

    if pair_signals:
        latest = pair_signals[-1]
        return jsonify({
            "source":     "cached",
            "pair":       pair,
            "action":     latest.get("action", "HOLD"),
            "confidence": latest.get("confidence", 0),
            "reason":     latest.get("reason", "—"),
        })

    # لو ما في بيانات خالص
    return jsonify({
        "source":     "waiting",
        "pair":       pair,
        "action":     "SCANNING",
        "confidence": 0,
        "reason":     f"No analysis yet for {pair}"
    })

if __name__ == "__main__":
    log.info(f"[SnipBot Proxy v5]: Starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
