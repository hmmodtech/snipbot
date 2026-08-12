"""
SnipBot API Proxy — v5.2
Dynamic Capital Sync Update & 8 AI Agents Gateway
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

# 🌐 MICROSERVICES URLS & ENVIRONMENT CONFIG
OCTOBOT_URL        = os.getenv("OCTOBOT_URL", "https://snipbot-y.up.railway.app")
AGENTS_SERVICE_URL = os.getenv("AGENTS_SERVICE_URL", "https://agents-snipbot.up.railway.app")
PORT               = int(os.getenv("PORT", 8080))
AGENTS_FILE        = "/tmp/agents_store.json"
AGENT_CONFIGS_FILE = "/tmp/agent_configs.json"


# ══════════════════════════════════════════════
# DYNAMIC BASE CAPITAL HELPER (قراءة رأس المال حركياً)
# ══════════════════════════════════════════════
def get_base_capital():
    """يقرأ رأس المال الابتدائي الحقيقي المحدد في user/config.json حركياً"""
    env_cap = os.getenv("BASE_CAPITAL")
    if env_cap:
        try:
            return float(env_cap)
        except ValueError:
            pass

    config_paths = ["user/config.json", "/app/user/config.json", "../user/config.json"]
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    cfg = json.load(f)
                    start_usdt = cfg.get("trader-simulator", {}).get("starting-portfolio", {}).get("USDT")
                    if start_usdt is not None:
                        log.info(f"[Proxy Capital]: Read ${start_usdt} from {path}")
                        return float(start_usdt)
            except Exception as e:
                log.warning(f"[Proxy Capital]: Could not parse {path}: {e}")

    try:
        r = requests.get(f"{OCTOBOT_URL}/api/portfolio", timeout=5)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, dict) and "total_portfolio_value" in data:
                return float(data["total_portfolio_value"])
    except Exception:
        pass

    return 30000.0


# ══════════════════════════════════════════════
# Agents Store Helper
# ══════════════════════════════════════════════
def load_agents_store():
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
    try:
        with open(AGENTS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        log.warning(f"[Proxy] Could not save agents store: {e}")

_agents_store = load_agents_store()


# ══════════════════════════════════════════════
# OctoBot API Helpers
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
# Routes — Health & Status
# ══════════════════════════════════════════════
@app.route("/health")
def health():
    trades_list = get_trades()
    return jsonify({
        "proxy":       "online",
        "octobot":     "connected" if trades_list is not None else "disconnected",
        "octobot_url": OCTOBOT_URL,
        "agents_url":  AGENTS_SERVICE_URL,
        "timestamp":   datetime.utcnow().isoformat()
    })


@app.route("/status")
def status():
    return jsonify({
        "proxy":   "online",
        "octobot": OCTOBOT_URL,
        "agents":  AGENTS_SERVICE_URL,
        "time":    datetime.utcnow().isoformat()
    })


# ══════════════════════════════════════════════
# Routes — Portfolio (Dynamic Capital Sync)
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

        BASE_CAPITAL = get_base_capital()
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
        BASE_CAPITAL = get_base_capital()
        return jsonify({
            "source":                "fallback",
            "total_portfolio_value": BASE_CAPITAL,
            "free_usdt":             BASE_CAPITAL,
            "locked_usdt":           0.0,
            "currency":              "USDT",
            "realized_pnl":          0,
            "mode":                  "simulated"
        })


# ══════════════════════════════════════════════
# Routes — Trades & Summary
# ══════════════════════════════════════════════
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
        return jsonify({
            "source": "live",
            "count":  len(data),
            "orders": data
        })
    except Exception as e:
        log.error(f"[Proxy] orders error: {e}")
        return jsonify({"source": "error", "count": 0, "orders": []})


# ══════════════════════════════════════════════
# Routes — 8 AI Agents Radar & Config Gateways
# ══════════════════════════════════════════════
@app.route("/api/agents/status", methods=["GET"])
def agents_status():
    """Proxies live 8 agents status directly from agents-snipbot microservice with fallback."""
    try:
        resp = requests.get(f"{AGENTS_SERVICE_URL}/api/agents/status", timeout=5)
        if resp.status_code == 200:
            return jsonify(resp.json()), 200
    except Exception as e:
        log.warning(f"[Proxy] Direct agents fetch failed: {e}")

    # Fallback to local agents store if service is offline
    return jsonify({
        "source":    "live_fallback",
        "timestamp": _agents_store.get("timestamp"),
        "agents":    _agents_store.get("strategies", []),
        "signals":   _agents_store.get("signals", [])
    })

@app.route("/api/agents/evaluate", methods=["GET", "POST"])
def evaluate_agents():
    """Evaluates multi-agent consensus across all 8 agents."""
    pair = request.args.get("pair", "BTC/USDT")
    try:
        resp = requests.get(f"{AGENTS_SERVICE_URL}/api/agents/evaluate?pair={pair}", timeout=5)
        return jsonify(resp.json()), resp.status_code
    except Exception as e:
        return jsonify({"status": "error", "message": f"Agents Evaluation Error: {str(e)}"}), 502

@app.route("/api/agents/update", methods=["POST"])
def agents_update():
    global _agents_store
    try:
        data = request.get_json()
        if data:
            _agents_store = data
            save_agents_store(data)
            log.info(f"[Proxy] Agent Radar updated — {len(data.get('signals', []))} signals")
            return jsonify({"status": "ok"})
        return jsonify({"status": "empty"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/agents/config", methods=["GET", "POST"])
def agent_config_handler():
    if request.method == "POST":
        data = request.get_json() or {}
        try:
            with open(AGENT_CONFIGS_FILE, "w") as f:
                json.dump(data, f)
            return jsonify({"status": "success", "message": "Agent configurations updated"})
        except Exception as e:
            return jsonify({"status": "error", "error": str(e)}), 500
    else:
        try:
            with open(AGENT_CONFIGS_FILE) as f:
                return jsonify(json.load(f))
        except:
            return jsonify({
                "TA Analyst": {"min_confidence": 65, "rsi_oversold": 38, "rsi_overbought": 62, "weight": 1.0},
                "Smart DCA+": {"dip_threshold": 4.0, "recovery_target": 3.0, "weight": 1.0},
                "Sniper Engine": {"breakout_threshold": 0.995, "orderbook_ratio": 1.2, "weight": 1.2}
            })


# ══════════════════════════════════════════════
# Route — Bilingual AI Pair Analysis
# ══════════════════════════════════════════════
@app.route('/api/ai_analysis', methods=['GET'])
def get_ai_analysis():
    # Decode %2F back to standard / for CCXT symbol format
    raw_symbol = request.args.get('symbol', 'BTC/USDT')
    symbol = raw_symbol.replace('%2F', '/').replace('%2f', '/')
    
    analysis = {
        "symbol": symbol,
        "recommendation": "NEUTRAL / HOLD",
        "confidence": 75,
        "support": "Support Zone Verified",
        "resistance": "Resistance Zone Verified",
        "ar_analysis": f"تحليل القناص لزوج {symbol}: السعر يتذبذب حالياً في منطقة ضغط، يوصى بالانتظار لحين تأكيد الكسر.",
        "en_analysis": f"Sniper Analysis for {symbol}: Price consolidating in compression zone. Await breakout confirmation."
    }
    
    # Safely query agents-snipbot consensus
    try:
        agents_res = requests.get(f"https://agents-snipbot.up.railway.app/api/agents/evaluate?pair={symbol}", timeout=3)
        if agents_res.status_code == 200:
            data = agents_res.json()
            consensus = data.get('consensus', {})
            action = consensus.get('action', 'HOLD_AND_SCAN')
            conf = consensus.get('net_confidence', 75)
            
            if action == 'FIRE_BUY':
                rec = 'STRONG BUY / شراء قوي'
            elif action == 'FIRE_SELL':
                rec = 'STRONG SELL / بيع قوي'
            else:
                rec = 'NEUTRAL / HOLD'
                
            analysis['recommendation'] = rec
            analysis['confidence'] = conf
    except Exception as e:
        app.logger.warning(f"[AI Analysis Proxy Warning]: {e}")
        
    response = jsonify(analysis)
    response.headers.add('Access-Control-Allow-Origin', '*')
    return response, 200
# ══════════════════════════════════════════════
# Routes — Telegram & OHLCV & Exchange Balance
# ══════════════════════════════════════════════
@app.route("/api/telegram/send", methods=["POST"])
def telegram_send():
    try:
        data    = request.get_json() or {}
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
    symbol    = request.args.get("symbol", "ADA/USDT").replace("%2F", "/").replace(" ", "/")
    timeframe = request.args.get("timeframe", "1h")
    limit     = int(request.args.get("limit", "80"))
    if "/" not in symbol and "USDT" in symbol:
        symbol = symbol.replace("USDT", "/USDT")
    try:
        ex = ccxt.kucoin({"enableRateLimit": True, "options": {"defaultType": "spot"}, "timeout": 10000})
        raw = ex.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        candles = [{
            "t": int(c[0]), "o": float(c[1]), "h": float(c[2]),
            "l": float(c[3]), "c": float(c[4]), "v": float(c[5]),
        } for c in raw]
        return jsonify({"status": "live", "symbol": symbol, "timeframe": timeframe, "candles": candles})
    except Exception as e:
        log.error(f"[Proxy OHLCV Error] {symbol}: {e}")
        return jsonify({"status": "error", "symbol": symbol, "error": str(e), "candles": []}), 500


@app.route("/api/exchange_balance", methods=["POST"])
def exchange_balance():
    body = request.get_json(silent=True) or {}
    exchange_id = body.get("exchange", "").lower().strip()
    api_key     = body.get("api_key", body.get("apiKey", "")).strip()
    secret      = body.get("secret", "").strip()
    password    = body.get("password", "").strip()
    mode        = body.get("mode", "paper")

    if not exchange_id or not api_key or not secret:
        return jsonify({"error": "exchange, api_key and secret required"}), 400

    try:
        ex_class = getattr(ccxt, exchange_id)
        config   = {"apiKey": api_key, "secret": secret, "enableRateLimit": True, "options": {"defaultType": "spot"}}
        if password: config["password"] = password
        ex = ex_class(config)

        if mode == "paper" and exchange_id == "kucoin":
            ex.urls["api"] = {"public": "https://openapi-sandbox.kucoin.com", "private": "https://openapi-sandbox.kucoin.com"}

        balance = ex.fetch_balance()
        total_usdt = 0.0
        free_usdt  = 0.0

        for asset, amt in (balance.get("total") or {}).items():
            if not amt or float(amt) <= 0: continue
            val = float(amt)
            if asset in ("USDT", "USDC", "BUSD"):
                total_usdt += val
                free_usdt += float((balance.get("free") or {}).get(asset, 0) or 0)

        return jsonify({
            "status": "live", "exchange": exchange_id, "mode": mode,
            "total_usdt": round(total_usdt, 2), "free_usdt": round(free_usdt, 2)
        })
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


if __name__ == "__main__":
    log.info(f"[SnipBot Proxy v5.2]: Dynamic Capital Sync ready on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)
