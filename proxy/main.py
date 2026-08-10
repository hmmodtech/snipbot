"""
SnipBot API Proxy — v5
التحسينات:
  1. KuCoin Sandbox URL صحيح
  2. Agents Store محفوظ في ملف
  3. ccxt مضمون في الكود
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import ccxt
import os
import json
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("SnipBot-Proxy")

OCTOBOT_URL  = os.getenv("OCTOBOT_URL", "https://snipbot-y.up.railway.app")
PORT         = int(os.getenv("PORT", 8080))
AGENTS_FILE  = "/tmp/agents_store.json"


# ══════════════════════════════════════════════
# التحسين 2 — Agents Store في ملف
# ══════════════════════════════════════════════
def load_agents_store():
    """يحمّل آخر نتائج الـ Agents من الملف عند البدء"""
    try:
        with open(AGENTS_FILE) as f:
            return json.load(f)
    except Exception:
        return {
            "timestamp":  None,
            "signals":    [],
            "strategies": [],
            "symbols":    []
        }

def save_agents_store(data):
    """يحفظ نتائج الـ Agents في الملف"""
    try:
        with open(AGENTS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        log.warning(f"[Proxy] Could not save agents store: {e}")

# تحميل عند البدء
_agents_store = load_agents_store()


# ══════════════════════════════════════════════
# OctoBot Helpers
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
# Routes — Health
# ══════════════════════════════════════════════
@app.route("/health")
def health():
    trades = get_trades()
    return jsonify({
        "proxy":       "online",
        "octobot":     "connected" if trades is not None else "disconnected",
        "octobot_url": OCTOBOT_URL,
        "timestamp":   datetime.utcnow().isoformat()
    })


@app.route("/status")
def status():
    return jsonify({
        "proxy":   "online",
        "octobot": OCTOBOT_URL,
        "time":    datetime.utcnow().isoformat()
    })


# ══════════════════════════════════════════════
# Routes — Portfolio
# ══════════════════════════════════════════════
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
        locked       = round(sum(float(o.get("cost", 0)) for o in orders_list), 2)

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


# ══════════════════════════════════════════════
# Routes — Trades & Orders
# ══════════════════════════════════════════════
@app.route("/api/trades")
def trades():
    try:
        data = get_trades()
        sorted_trades = sorted(
            data, key=lambda x: x.get("time", 0), reverse=True
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
    try:
        trades_list = get_trades()
        orders_list = get_orders()

        buy_trades  = [t for t in trades_list if "BUY"  in str(t.get("type", ""))]
        sell_trades = [t for t in trades_list if "SELL" in str(t.get("type", ""))]
        pnl = (
            sum(float(t.get("cost", 0)) for t in sell_trades) -
            sum(float(t.get("cost", 0)) for t in buy_trades)
        )

        last_trade = {}
        if trades_list:
            last_trade = sorted(
                trades_list, key=lambda x: x.get("time", 0), reverse=True
            )[0]

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


# ══════════════════════════════════════════════
# Routes — Agents
# ══════════════════════════════════════════════
@app.route("/api/agents/update", methods=["POST"])
def agents_update():
    global _agents_store
    try:
        data = request.get_json()
        if data:
            _agents_store = data
            save_agents_store(data)  # ← التحسين 2
            log.info(
                f"[Proxy] Agent Radar updated — "
                f"{len(data.get('signals', []))} signals"
            )
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
                {"name": "TA Analyst", "action": "SCANNING", "confidence": 0,
                 "reason": "Awaiting first scan cycle"},
                {"name": "Smart DCA+", "action": "SCANNING", "confidence": 0,
                 "reason": "Awaiting first scan cycle"}
            ],
            "signals": []
        })
    return jsonify({
        "source":    "live",
        "timestamp": _agents_store.get("timestamp"),
        "agents":    _agents_store.get("strategies", []),
        "signals":   _agents_store.get("signals", [])
    })


# ══════════════════════════════════════════════
# Routes — Telegram
# ══════════════════════════════════════════════
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
            data={
                "chat_id":    chat_id,
                "text":       message,
                "parse_mode": "HTML"
            },
            timeout=8
        )
        return jsonify({"status": "sent", "ok": r.status_code == 200})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)})


# ══════════════════════════════════════════════
# Routes — Exchange Balance
# التحسين 1 — KuCoin Sandbox URL صحيح
# ══════════════════════════════════════════════
@app.route("/api/exchange_balance", methods=["POST"])
def exchange_balance():
    body = request.get_json(silent=True) or {}

    exchange_id = body.get("exchange", "").lower().strip()
    api_key     = body.get("api_key", body.get("apiKey", "")).strip()
    secret      = body.get("secret", "").strip()
    password    = body.get("password", "").strip()
    mode        = body.get("mode", "paper")

    if not exchange_id:
        return jsonify({"error": "exchange field required"}), 400
    if not api_key or not secret:
        return jsonify({"error": "api_key and secret required"}), 400

    SUPPORTED = ["kucoin", "binance", "bybit", "okx",
                 "kraken", "bitget", "gateio"]
    if exchange_id not in SUPPORTED:
        return jsonify({
            "error": f"'{exchange_id}' not supported. "
                     f"Supported: {', '.join(SUPPORTED)}"
        }), 400

    try:
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

        # ── التحسين 1 — KuCoin Sandbox URL الصحيح ──
        if mode == "paper":
            if exchange_id == "kucoin":
                # KuCoin sandbox يحتاج URL مخصص
                ex.urls["api"] = {
                    "public":  "https://openapi-sandbox.kucoin.com",
                    "private": "https://openapi-sandbox.kucoin.com",
                }
                log.info("[Proxy] KuCoin: using sandbox URL")
            else:
                # باقي المنصات تدعم set_sandbox_mode
                try:
                    ex.set_sandbox_mode(True)
                    log.info(f"[Proxy] {exchange_id}: sandbox mode enabled")
                except Exception:
                    log.info(f"[Proxy] {exchange_id}: sandbox not supported")

        # ── جلب الرصيد ──
        balance    = ex.fetch_balance()
        total_usdt = 0.0
        free_usdt  = 0.0
        active_pairs = []

        for asset, amt in (balance.get("total") or {}).items():
            if not amt or float(amt) <= 0:
                continue
            val = float(amt)
            if asset in ("USDT", "USDC", "BUSD", "TUSD"):
                total_usdt += val
                free_usdt  += float(
                    (balance.get("free") or {}).get(asset, 0) or 0
                )
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

        # ── PnL من الـ positions ──
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

        log.info(
            f"🔎 [Proxy]: {exchange_id} — "
            f"${total_usdt:.0f} USDT ({mode})"
        )

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
@app.route("/api/ohlcv")
def ohlcv():
    symbol    = request.args.get("symbol",    "ADA/USDT")
    timeframe = request.args.get("timeframe", "1h")
    limit     = int(request.args.get("limit", "100"))
    try:
        exchange = ccxt.kucoin({
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        exchange.close()
        candles = [{
            "t": c[0], "o": float(c[1]), "h": float(c[2]),
            "l": float(c[3]), "c": float(c[4]), "v": float(c[5]),
        } for c in raw]
        return jsonify({"status": "live", "symbol": symbol,
                        "timeframe": timeframe, "candles": candles})
    except Exception as e:
        log.error(f"[Proxy] OHLCV error: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == "__main__":
    log.info(f"[SnipBot Proxy]: Starting on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
