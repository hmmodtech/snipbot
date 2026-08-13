"""
SnipBot — Hybrid AI Agents Engine v12.3 FINAL
-----------------------------------------------
8 Real AI Agents + Weighted Consensus Engine
KuCoin -> Binance automatic failover
Flask API for Dashboard + Proxy
"""

import os
import logging
import time
import threading
import requests
from datetime import datetime, timezone
from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
import ta.momentum
import ta.trend
import ta.volatility

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("SnipBot.Agents")

PORT       = int(os.environ.get("PORT", 8080))
PROXY_URL  = os.environ.get("PROXY_URL",  "https://snipbot-proxy.up.railway.app")
PAIRS      = [p.strip() for p in os.environ.get("PAIRS", "ADA/USDT,XRP/USDT,BTC/USDT,ETH/USDT").split(",")]
INTERVAL   = int(os.environ.get("SCAN_INTERVAL", "300"))
TF         = os.environ.get("TIMEFRAME", "1h")
MIN_SIGNAL = float(os.environ.get("MIN_SIGNAL", "75"))
MIN_CONF   = float(os.environ.get("MIN_CONFIDENCE", "80"))

app = Flask(__name__)
CORS(app)

_latest_evaluations = {}
_scan_count         = 0
_last_scan_time     = None

AGENTS_REGISTRY = {
    "smart_dca":         {"name": "Smart DCA Agent",             "type": "Accumulation & Support Sniper",    "weight": 1.2, "enabled": True},
    "momentum_breakout": {"name": "Technical Momentum Agent",    "type": "Breakout & Divergence Engine",     "weight": 1.3, "enabled": True},
    "trend_follower":    {"name": "Trend Follower Agent",        "type": "EMA Trend & Trailing",             "weight": 1.1, "enabled": True},
    "grid_sniper":       {"name": "Grid Sniper Agent",           "type": "Volatility Range Grid",            "weight": 1.0, "enabled": True},
    "liquidity_sweep":   {"name": "Liquidity Sweep Agent",       "type": "Orderbook & Wick Sniper",          "weight": 1.4, "enabled": True},
    "micro_scalper":     {"name": "Micro-Scalper Agent",         "type": "High-Frequency Spread",            "weight": 0.9, "enabled": True},
    "sentiment_ai":      {"name": "Sentiment AI Agent",          "type": "Fear & Greed + Momentum",          "weight": 1.1, "enabled": True},
    "risk_governor":     {"name": "Risk & Portfolio Governor",   "type": "Master Safety Engine",             "weight": 1.5, "enabled": True},
}

# ══ REAL AGENT ANALYSIS FUNCTIONS ══════════════════════════════════════════════

def analyze_smart_dca(df):
    try:
        closes = df["close"]
        price  = closes.iloc[-1]
        ma50   = ta.trend.SMAIndicator(closes, window=min(50, len(closes)-1)).sma_indicator().iloc[-1]
        rsi    = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        ema200 = ta.trend.EMAIndicator(closes, window=min(200, max(1, len(closes)//2))).ema_indicator().iloc[-1]
        pct    = (price - ma50) / ma50 * 100
        uptrend = price > ema200
        if pct <= -4 and rsi > 25 and uptrend:
            return {"signal": min(70+abs(pct)*5,95), "confidence": min(75+abs(pct)*3,90), "reason": f"DCA dip {pct:.1f}% below MA50 · RSI={rsi:.0f}"}
        elif pct >= 3:
            return {"signal": max(30-pct*5,5), "confidence": 75, "reason": f"DCA recovery {pct:.1f}% above MA50"}
        return {"signal": 50, "confidence": 60, "reason": f"DCA standby {pct:+.1f}% vs MA50 · RSI={rsi:.0f}"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_momentum_breakout(df):
    try:
        closes   = df["close"]
        rsi_v    = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        macd_obj = ta.trend.MACD(closes, window_fast=12, window_slow=26, window_sign=9)
        macd     = macd_obj.macd()
        macd_sig = macd_obj.macd_signal()
        ema20    = ta.trend.EMAIndicator(closes, window=20).ema_indicator()
        ema50    = ta.trend.EMAIndicator(closes, window=min(50,len(closes)-1)).ema_indicator()
        macd_bull  = macd.iloc[-1] > macd_sig.iloc[-1]
        macd_cross = macd.iloc[-1] > macd_sig.iloc[-1] and macd.iloc[-2] <= macd_sig.iloc[-2]
        ema_bull   = ema20.iloc[-1] > ema50.iloc[-1]
        rsi_bull   = 45 < rsi_v < 65
        score = sum([macd_bull, macd_cross, ema_bull, rsi_bull])
        if score >= 3:
            return {"signal": min(75+score*5+(10 if macd_cross else 0),95), "confidence": min(80+(10 if macd_cross else 0),95), "reason": f"Bullish momentum · RSI={rsi_v:.0f} · MACD={'CROSS ▲' if macd_cross else 'BULL'}"}
        elif score <= 1:
            return {"signal": max(30-(2-score)*10,5), "confidence": 70, "reason": f"Weak momentum · RSI={rsi_v:.0f} · score={score}/4"}
        return {"signal": 50, "confidence": 60, "reason": f"Neutral · RSI={rsi_v:.0f} · score={score}/4"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_trend_follower(df):
    try:
        closes = df["close"]; highs = df["high"]; lows = df["low"]
        ema20  = ta.trend.EMAIndicator(closes, window=20).ema_indicator()
        ema50  = ta.trend.EMAIndicator(closes, window=min(50,len(closes)-1)).ema_indicator()
        adx_v  = ta.trend.ADXIndicator(highs, lows, closes, window=14).adx().iloc[-1]
        golden  = ema20.iloc[-1] > ema50.iloc[-1] and ema20.iloc[-2] <= ema50.iloc[-2]
        death   = ema20.iloc[-1] < ema50.iloc[-1] and ema20.iloc[-2] >= ema50.iloc[-2]
        uptrend = ema20.iloc[-1] > ema50.iloc[-1]
        strong  = adx_v > 25
        if uptrend and strong:
            return {"signal": 80+(10 if golden else 0), "confidence": 82+(8 if strong else 0), "reason": f"{'Golden Cross ▲' if golden else 'Uptrend'} · ADX={adx_v:.0f}"}
        elif not uptrend and strong:
            return {"signal": 20-(10 if death else 0), "confidence": 80, "reason": f"{'Death Cross ▼' if death else 'Downtrend'} · ADX={adx_v:.0f}"}
        return {"signal": 50, "confidence": 55, "reason": f"Sideways · ADX={adx_v:.0f} (weak)"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_grid_sniper(df):
    try:
        closes = df["close"]; price = closes.iloc[-1]
        bb = ta.volatility.BollingerBands(closes, window=20, window_dev=2)
        upper = bb.bollinger_hband().iloc[-1]; lower = bb.bollinger_lband().iloc[-1]; mid = bb.bollinger_mavg().iloc[-1]
        width = (upper-lower)/mid*100 if mid > 0 else 0
        pct   = (price-lower)/(upper-lower) if (upper-lower) > 0 else 0.5
        if width < 3:
            return {"signal": 70, "confidence": 75, "reason": f"BB Squeeze · Width={width:.1f}%"}
        elif pct < 0.2:
            return {"signal": 75, "confidence": 78, "reason": f"Near BB lower · {pct*100:.0f}% in band"}
        elif pct > 0.8:
            return {"signal": 30, "confidence": 73, "reason": f"Near BB upper · {pct*100:.0f}% in band"}
        return {"signal": 50, "confidence": 60, "reason": f"Mid-band · {pct*100:.0f}% · Width={width:.1f}%"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_liquidity_sweep(df):
    try:
        last = df.iloc[-1]
        wick_low = last["open"] - last["low"]
        size     = last["high"] - last["low"]
        ratio    = wick_low / size if size > 0 else 0
        bull     = ratio > 0.6 and last["close"] > last["open"]
        avg_vol  = df["volume"].iloc[-10:-1].mean() if len(df) > 10 else df["volume"].mean()
        spike    = last["volume"] > avg_vol * 1.5
        if bull and spike:
            return {"signal": 88, "confidence": 85, "reason": f"Bullish wick sweep · Ratio={ratio:.0%} · Vol spike"}
        elif bull:
            return {"signal": 75, "confidence": 75, "reason": f"Wick sweep · Ratio={ratio:.0%}"}
        elif ratio < 0.2 and last["close"] < last["open"]:
            return {"signal": 35, "confidence": 68, "reason": "Bearish candle · No sweep"}
        return {"signal": 52, "confidence": 58, "reason": f"No sweep · Ratio={ratio:.0%}"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_micro_scalper(df):
    try:
        closes  = df["close"]
        rsi3_v  = ta.momentum.RSIIndicator(closes, window=3).rsi().iloc[-1]
        rsi14_v = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        n       = min(5, len(closes)-1)
        mom5    = (closes.iloc[-1] - closes.iloc[-n]) / closes.iloc[-n] * 100
        if rsi3_v < 30 and mom5 < -1:
            return {"signal": 78, "confidence": 72, "reason": f"Micro oversold · RSI3={rsi3_v:.0f} · mom={mom5:.2f}%"}
        elif rsi3_v > 70 and mom5 > 1:
            return {"signal": 28, "confidence": 70, "reason": f"Micro overbought · RSI3={rsi3_v:.0f} · mom={mom5:.2f}%"}
        return {"signal": 50, "confidence": 55, "reason": f"Scalp standby · RSI3={rsi3_v:.0f} · RSI14={rsi14_v:.0f}"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_sentiment_ai(df):
    try:
        closes  = df["close"]; volumes = df["volume"]
        lb      = min(24, len(closes)-1)
        trend   = (closes.iloc[-1] - closes.iloc[-lb]) / closes.iloc[-lb] * 100
        rv      = volumes.iloc[-5:].mean() if len(volumes) >= 5 else volumes.mean()
        ov      = volumes.iloc[-min(20,len(volumes)):-5].mean() if len(volumes) >= 20 else volumes.mean()
        vol_t   = (rv - ov) / ov * 100 if ov > 0 else 0
        rsi     = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        if trend > 2 and vol_t > 10:
            return {"signal": 85, "confidence": 80, "reason": f"Bullish sentiment · 24h={trend:+.1f}% · Vol={vol_t:+.0f}%"}
        elif trend > 0 and rsi > 50:
            return {"signal": 65, "confidence": 70, "reason": f"Mildly bullish · 24h={trend:+.1f}% · RSI={rsi:.0f}"}
        elif trend < -2:
            return {"signal": 30, "confidence": 72, "reason": f"Bearish sentiment · 24h={trend:+.1f}%"}
        return {"signal": 50, "confidence": 58, "reason": f"Neutral · 24h={trend:+.1f}%"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_risk_governor(df):
    try:
        closes = df["close"]; highs = df["high"]; lows = df["low"]
        price  = closes.iloc[-1]
        atr_v  = ta.volatility.AverageTrueRange(highs, lows, closes, window=14).average_true_range().iloc[-1]
        atr_pct = atr_v / price * 100 if price > 0 else 0
        high20  = highs.iloc[-min(20,len(highs)):].max()
        dd      = (price - high20) / high20 * 100 if high20 > 0 else 0
        if dd < -8:
            return {"signal": 20, "confidence": 90, "reason": f"RISK ALERT: DD={dd:.1f}% · ATR={atr_pct:.1f}% — REDUCE"}
        elif dd < -5:
            return {"signal": 40, "confidence": 85, "reason": f"Moderate risk: DD={dd:.1f}% · ATR={atr_pct:.1f}%"}
        elif atr_pct > 5:
            return {"signal": 45, "confidence": 80, "reason": f"High volatility: ATR={atr_pct:.1f}% — caution"}
        return {"signal": 85, "confidence": 88, "reason": f"Portfolio safe: DD={dd:.1f}% · ATR={atr_pct:.1f}%"}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

AGENT_FUNCTIONS = {
    "smart_dca": analyze_smart_dca, "momentum_breakout": analyze_momentum_breakout,
    "trend_follower": analyze_trend_follower, "grid_sniper": analyze_grid_sniper,
    "liquidity_sweep": analyze_liquidity_sweep, "micro_scalper": analyze_micro_scalper,
    "sentiment_ai": analyze_sentiment_ai, "risk_governor": analyze_risk_governor,
}

# ══ CONSENSUS ENGINE ════════════════════════════════════════════════════════════

def run_consensus(pair, df):
    results = {}
    tw = ws = wc = 0.0
    for aid, cfg in AGENTS_REGISTRY.items():
        if not cfg["enabled"]: continue
        fn = AGENT_FUNCTIONS.get(aid)
        r  = fn(df) if fn else {"signal":50,"confidence":50,"reason":"No fn"}
        w  = cfg["weight"]
        results[aid] = {
            "id": aid, "name": cfg["name"], "type": cfg["type"], "weight": w,
            "signal": r["signal"], "confidence": r["confidence"], "reason": r["reason"],
            "status": "TRIGGERED" if r["signal"] >= MIN_SIGNAL else "SCANNING",
        }
        ws += r["signal"] * w; wc += r["confidence"] * w; tw += w

    ns = round(ws/tw,2) if tw>0 else 50
    nc = round(wc/tw,2) if tw>0 else 50
    action = "FIRE_BUY" if ns>=MIN_SIGNAL and nc>=MIN_CONF else ("FIRE_SELL" if ns<=(100-MIN_SIGNAL) and nc>=MIN_CONF else "HOLD_AND_SCAN")
    return {
        "pair": pair, "timestamp": datetime.now(timezone.utc).isoformat(),
        "consensus": {"action": action, "net_signal": ns, "net_confidence": nc,
                      "threshold_signal": MIN_SIGNAL, "threshold_conf": MIN_CONF},
        "agents": results,
    }

# ══ OHLCV FETCH — KuCoin -> Binance failover ════════════════════════════════════

def fetch_ohlcv_sync(pair, timeframe="1h", limit=200):
    import ccxt
    for exchange_id in ["kucoin", "binance"]:
        try:
            ex  = getattr(ccxt, exchange_id)({"enableRateLimit": True, "options": {"defaultType": "spot"}})
            raw = ex.fetch_ohlcv(pair, timeframe, limit=limit)
            if raw and len(raw) >= 15:
                df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)
                log.info(f"[OHLCV] {pair} fetched from {exchange_id} ({len(df)} candles)")
                return df.astype(float)
        except Exception as e:
            log.warning(f"[OHLCV] {exchange_id} failed for {pair}: {e}")
    return None

# ══ PUSH TO PROXY ═══════════════════════════════════════════════════════════════

def push_to_proxy(data):
    try:
        r = requests.post(f"{PROXY_URL}/api/agents/update", json=data, timeout=5)
        log.info(f"🔎 [Proxy]: Agent Radar updated → {r.status_code}")
    except Exception as e:
        log.warning(f"[Proxy]: push failed — {e}")

# ══ BACKGROUND SCAN LOOP ════════════════════════════════════════════════════════

def scan_loop():
    global _scan_count, _last_scan_time, _latest_evaluations
    time.sleep(5)
    while True:
        _scan_count += 1
        _last_scan_time = datetime.now(timezone.utc).isoformat()
        log.info(f"🔎 [Sniper Engine]: Scan #{_scan_count} on {PAIRS}...")

        proxy_agents = []
        active_sigs  = []

        for pair in PAIRS:
            df = fetch_ohlcv_sync(pair, TF)
            if df is None:
                log.warning(f"◎ [Scanner]: No data for {pair}")
                continue
            result = run_consensus(pair, df)
            _latest_evaluations[pair] = result
            action = result["consensus"]["action"]
            ns     = result["consensus"]["net_signal"]
            nc     = result["consensus"]["net_confidence"]

            for aid, ag in result["agents"].items():
                proxy_agents.append({
                    "name": ag["name"], "pair": pair, "strategy": ag["name"],
                    "action": "BUY" if ag["signal"]>=MIN_SIGNAL else ("SELL" if ag["signal"]<=(100-MIN_SIGNAL) else "HOLD"),
                    "confidence": ag["confidence"], "reason": ag["reason"],
                })

            if action == "FIRE_BUY":
                active_sigs.append({"pair": pair, "action": "BUY", "confidence": nc})
                log.info(f"🎯 [SnipBot]: {pair} FIRE_BUY · ns={ns} nc={nc}")
            elif action == "FIRE_SELL":
                active_sigs.append({"pair": pair, "action": "SELL", "confidence": nc})
                log.info(f"⚡ [SnipBot]: {pair} FIRE_SELL · ns={ns} nc={nc}")
            else:
                log.info(f"◎ [SnipBot Tracking]: {pair} HOLD · ns={ns:.1f}")

        push_to_proxy({"timestamp": _last_scan_time, "scan_count": _scan_count,
                       "strategies": proxy_agents, "signals": active_sigs, "symbols": PAIRS})
        log.info(f"◎ Sleeping {INTERVAL}s...")
        time.sleep(INTERVAL)

# ══ FLASK ROUTES ════════════════════════════════════════════════════════════════

@app.route("/"); @app.route("/health")
def health():
    return jsonify({"status":"ONLINE","service":"snipbot-agents-v12.3",
                    "agents":len(AGENTS_REGISTRY),"pairs":PAIRS,
                    "scan_count":_scan_count,"last_scan":_last_scan_time}), 200

@app.route("/api/agents/status")
def agents_status():
    latest = {}
    if _latest_evaluations:
        first = list(_latest_evaluations.values())[0]
        latest = first.get("agents", {})
    enriched = []
    for aid, cfg in AGENTS_REGISTRY.items():
        ev = latest.get(aid, {})
        sig  = ev.get("signal", 50)
        conf = ev.get("confidence", 75)
        action = "BUY" if sig>=MIN_SIGNAL else ("SELL" if sig<=(100-MIN_SIGNAL) else "HOLD")
        enriched.append({"id":aid,"name":cfg["name"],"type":cfg["type"],"weight":cfg["weight"],
                         "enabled":cfg["enabled"],"status":action,"action":action,
                         "signal":sig,"confidence":conf,"reason":ev.get("reason","Active scanning")})
    return jsonify({"status":"success","total_agents":len(enriched),"agents":enriched,
                    "scan_count":_scan_count,"last_scan":_last_scan_time,
                    "pairs":list(_latest_evaluations.keys())}), 200

@app.route("/api/agents/evaluate")
def evaluate_pair():
    pair = request.args.get("pair", PAIRS[0] if PAIRS else "ADA/USDT")
    tf   = request.args.get("timeframe", TF)
    if pair in _latest_evaluations:
        cached = _latest_evaluations[pair]
        ts = cached.get("timestamp","")
        if ts:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
            if age < 300:
                return jsonify({"status":"success","source":"cache",**cached}), 200
    df = fetch_ohlcv_sync(pair, tf)
    if df is None:
        if _latest_evaluations:
            fb = list(_latest_evaluations.values())[0]
            return jsonify({"status":"success","source":"fallback",**fb}), 200
        return jsonify({"status":"error","error":f"No data for {pair}"}), 503
    result = run_consensus(pair, df)
    _latest_evaluations[pair] = result
    return jsonify({"status":"success","source":"live",**result}), 200

@app.route("/api/agents/config", methods=["GET","POST"])
def agents_config():
    if request.method == "GET":
        return jsonify({"status":"success","config":{
            aid:{"name":cfg["name"],"weight":cfg["weight"],"enabled":cfg["enabled"]}
            for aid,cfg in AGENTS_REGISTRY.items()}}), 200
    body = request.get_json(silent=True) or {}
    for aid, updates in body.items():
        if aid in AGENTS_REGISTRY:
            if "weight"  in updates: AGENTS_REGISTRY[aid]["weight"]  = float(updates["weight"])
            if "enabled" in updates: AGENTS_REGISTRY[aid]["enabled"] = bool(updates["enabled"])
    return jsonify({"status":"updated"}), 200

@app.route("/api/agents/pairs")
def latest_by_pair():
    return jsonify({"status":"success","evaluations":_latest_evaluations}), 200

# ══ MAIN ════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info(f"🎯 [SnipBot Agents v12.3]: {len(AGENTS_REGISTRY)} agents · {PAIRS}")
    threading.Thread(target=scan_loop, daemon=True).start()
    log.info(f"🔎 [Sniper Engine]: Scan loop started · interval={INTERVAL}s · port={PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
