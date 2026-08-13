"""
SnipBot — Master Quantitative AI Strategy Engine v12.3 (Merged Edition)
------------------------------------------------------------------------
- Real 8 Quantitative Indicator Agents (pandas + ta)
- Automatic KuCoin -> Binance Exchange Failover
- Background Scan Loop (300s) + Push to Proxy Gateway
- Dynamic Weight & Threshold Config Management (/api/agents/config)
"""

import os
import time
import logging
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

# ── Config ────────────────────────────────────────────────────────────────────
PORT       = int(os.environ.get("PORT", 8080))
PROXY_URL  = os.environ.get("PROXY_URL", "https://snipbot-proxy.up.railway.app")
PAIRS      = [p.strip() for p in os.environ.get("PAIRS", "ADA/USDT,XRP/USDT,BTC/USDT,ETH/USDT").split(",")]
INTERVAL   = int(os.environ.get("SCAN_INTERVAL", "300"))
TF         = os.environ.get("TIMEFRAME", "1h")
MIN_SIGNAL = float(os.environ.get("MIN_SIGNAL", "75"))
MIN_CONF   = float(os.environ.get("MIN_CONFIDENCE", "80"))

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

_latest_evaluations = {}
_scan_count         = 0
_last_scan_time     = None

# ── 8 AGENTS REGISTRY ─────────────────────────────────────────────────────────
AGENTS_REGISTRY = {
    "smart_dca": {
        "name": "Smart DCA Agent",
        "type": "Accumulation & Support Sniper",
        "weight": 1.2,
        "enabled": True,
    },
    "momentum_breakout": {
        "name": "Technical Momentum Agent",
        "type": "Breakout & Divergence Engine",
        "weight": 1.3,
        "enabled": True,
    },
    "trend_follower": {
        "name": "Trend Follower Agent",
        "type": "EMA Trend & Trailing",
        "weight": 1.1,
        "enabled": True,
    },
    "grid_sniper": {
        "name": "Grid Sniper Agent",
        "type": "Volatility Range Grid",
        "weight": 1.0,
        "enabled": True,
    },
    "liquidity_sweep": {
        "name": "Liquidity Sweep Agent",
        "type": "Orderbook & Wick Sniper",
        "weight": 1.4,
        "enabled": True,
    },
    "micro_scalper": {
        "name": "Micro-Scalper Agent",
        "type": "High-Frequency Spread",
        "weight": 0.9,
        "enabled": True,
    },
    "sentiment_ai": {
        "name": "Sentiment AI Agent",
        "type": "Fear & Greed + Momentum",
        "weight": 1.1,
        "enabled": True,
    },
    "risk_governor": {
        "name": "Risk & Portfolio Governor",
        "type": "Master Safety Engine",
        "weight": 1.5,
        "enabled": True,
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# REAL QUANTITATIVE EVALUATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def analyze_smart_dca(df: pd.DataFrame) -> dict:
    try:
        closes = df["close"]
        price = closes.iloc[-1]
        ma50 = ta.trend.SMAIndicator(closes, window=min(50, len(closes)-1)).sma_indicator().iloc[-1]
        rsi = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        ema200 = ta.trend.EMAIndicator(closes, window=min(200, max(1, len(closes)//2))).ema_indicator().iloc[-1]

        pct_from_ma = (price - ma50) / ma50 * 100
        uptrend = price > ema200

        if pct_from_ma <= -4 and rsi > 25 and uptrend:
            signal = min(70 + abs(pct_from_ma) * 5, 95)
            confidence = min(75 + abs(pct_from_ma) * 3, 90)
            reason = f"DCA dip {pct_from_ma:.1f}% vs MA50 · RSI={rsi:.0f}"
        elif pct_from_ma >= 3:
            signal = max(30 - pct_from_ma * 5, 5)
            confidence = 75
            reason = f"DCA recovery {pct_from_ma:.1f}% above MA50"
        else:
            signal = 50
            confidence = 60
            reason = f"DCA standby {pct_from_ma:+.1f}% vs MA50 · RSI={rsi:.0f}"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_momentum_breakout(df: pd.DataFrame) -> dict:
    try:
        closes = df["close"]
        rsi = ta.momentum.RSIIndicator(closes, window=14).rsi()
        macd_obj = ta.trend.MACD(closes, window_fast=12, window_slow=26, window_sign=9)
        macd = macd_obj.macd()
        macd_sig = macd_obj.macd_signal()
        ema20 = ta.trend.EMAIndicator(closes, window=20).ema_indicator()
        ema50 = ta.trend.EMAIndicator(closes, window=min(50, len(closes)-1)).ema_indicator()

        rsi_v = rsi.iloc[-1]
        macd_bull = macd.iloc[-1] > macd_sig.iloc[-1]
        macd_cross = macd.iloc[-1] > macd_sig.iloc[-1] and macd.iloc[-2] <= macd_sig.iloc[-2]
        ema_bull = ema20.iloc[-1] > ema50.iloc[-1]
        rsi_bull = 45 < rsi_v < 65

        bull_score = sum([macd_bull, macd_cross, ema_bull, rsi_bull])

        if bull_score >= 3:
            signal = 75 + bull_score * 5 + (10 if macd_cross else 0)
            confidence = 80 + (10 if macd_cross else 0)
            reason = f"Bullish momentum · RSI={rsi_v:.0f} · MACD={'CROSS ▲' if macd_cross else 'BULL'}"
        elif bull_score <= 1:
            signal = 30 - (2 - bull_score) * 10
            confidence = 70
            reason = f"Weak momentum · RSI={rsi_v:.0f} · bull_score={bull_score}/4"
        else:
            signal = 50
            confidence = 60
            reason = f"Neutral · RSI={rsi_v:.0f} · bull_score={bull_score}/4"

        return {"signal": round(min(max(signal, 5), 95), 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_trend_follower(df: pd.DataFrame) -> dict:
    try:
        closes = df["close"]
        highs = df["high"]
        lows = df["low"]

        ema20 = ta.trend.EMAIndicator(closes, window=20).ema_indicator()
        ema50 = ta.trend.EMAIndicator(closes, window=min(50, len(closes)-1)).ema_indicator()
        adx = ta.trend.ADXIndicator(highs, lows, closes, window=14)

        adx_v = adx.adx().iloc[-1]
        golden = ema20.iloc[-1] > ema50.iloc[-1] and ema20.iloc[-2] <= ema50.iloc[-2]
        death = ema20.iloc[-1] < ema50.iloc[-1] and ema20.iloc[-2] >= ema50.iloc[-2]
        uptrend = ema20.iloc[-1] > ema50.iloc[-1]
        strong = adx_v > 25

        if uptrend and strong:
            signal = 80 + (10 if golden else 0)
            confidence = 82 + (8 if strong else 0)
            reason = f"{'Golden Cross ▲' if golden else 'Uptrend'} · EMA20>EMA50 · ADX={adx_v:.0f}"
        elif not uptrend and strong:
            signal = 20 - (10 if death else 0)
            confidence = 80
            reason = f"{'Death Cross ▼' if death else 'Downtrend'} · EMA20<EMA50 · ADX={adx_v:.0f}"
        else:
            signal = 50
            confidence = 55
            reason = f"Sideways trend · ADX={adx_v:.0f} (weak < 25)"

        return {"signal": round(min(max(signal, 5), 95), 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_grid_sniper(df: pd.DataFrame) -> dict:
    try:
        closes = df["close"]
        price = closes.iloc[-1]

        bb = ta.volatility.BollingerBands(closes, window=20, window_dev=2)
        upper = bb.bollinger_hband().iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        mid = bb.bollinger_mavg().iloc[-1]
        width = (upper - lower) / mid * 100 if mid > 0 else 0
        pct_in_band = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

        if width < 3:
            signal = 70
            confidence = 75
            reason = f"BB Squeeze · Width={width:.1f}% · Price at {pct_in_band*100:.0f}%"
        elif pct_in_band < 0.2:
            signal = 75
            confidence = 78
            reason = f"Price near BB lower · {pct_in_band*100:.0f}% in band"
        elif pct_in_band > 0.8:
            signal = 30
            confidence = 73
            reason = f"Price near BB upper · {pct_in_band*100:.0f}% in band"
        else:
            signal = 50
            confidence = 60
            reason = f"Mid-band position · Width={width:.1f}%"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_liquidity_sweep(df: pd.DataFrame) -> dict:
    try:
        last = df.iloc[-1]
        wick_low = last["open"] - last["low"]
        candle_size = last["high"] - last["low"]
        wick_ratio = wick_low / candle_size if candle_size > 0 else 0
        bull_sweep = wick_ratio > 0.6 and last["close"] > last["open"]

        avg_vol = df["volume"].iloc[-10:-1].mean() if len(df) > 10 else df["volume"].mean()
        vol_spike = last["volume"] > avg_vol * 1.5

        if bull_sweep and vol_spike:
            signal = 88
            confidence = 85
            reason = f"Bullish wick sweep · Ratio={wick_ratio:.0%} · Vol spike"
        elif bull_sweep:
            signal = 75
            confidence = 75
            reason = f"Wick sweep detected · Ratio={wick_ratio:.0%}"
        else:
            signal = 52
            confidence = 58
            reason = f"No sweep signal · Wick ratio={wick_ratio:.0%}"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_micro_scalper(df: pd.DataFrame) -> dict:
    try:
        closes = df["close"]
        rsi3 = ta.momentum.RSIIndicator(closes, window=3).rsi().iloc[-1]
        rsi14 = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        momentum_5 = (closes.iloc[-1] - closes.iloc[-min(5, len(closes)-1)]) / closes.iloc[-min(5, len(closes)-1)] * 100

        if rsi3 < 30 and momentum_5 < -1:
            signal = 78
            confidence = 72
            reason = f"Micro oversold · RSI3={rsi3:.0f} · Momentum={momentum_5:.2f}%"
        elif rsi3 > 70 and momentum_5 > 1:
            signal = 28
            confidence = 70
            reason = f"Micro overbought · RSI3={rsi3:.0f} · Momentum={momentum_5:.2f}%"
        else:
            signal = 50
            confidence = 55
            reason = f"Scalp standby · RSI3={rsi3:.0f} · RSI14={rsi14:.0f}"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_sentiment_ai(df: pd.DataFrame) -> dict:
    try:
        closes = df["close"]
        volumes = df["volume"]
        lookback = min(24, len(closes)-1)
        trend_24h = (closes.iloc[-1] - closes.iloc[-lookback]) / closes.iloc[-lookback] * 100

        avg_vol_recent = volumes.iloc[-5:].mean() if len(volumes) >= 5 else volumes.mean()
        avg_vol_older = volumes.iloc[-min(20, len(volumes)):-5].mean() if len(volumes) >= 20 else volumes.mean()
        vol_trend = (avg_vol_recent - avg_vol_older) / avg_vol_older * 100 if avg_vol_older > 0 else 0

        rsi = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]

        if trend_24h > 2 and vol_trend > 10:
            signal = 85
            confidence = 80
            reason = f"Bullish sentiment · 24h={trend_24h:+.1f}% · Vol={vol_trend:+.0f}%"
        elif trend_24h > 0 and rsi > 50:
            signal = 65
            confidence = 70
            reason = f"Mildly bullish · 24h={trend_24h:+.1f}% · RSI={rsi:.0f}"
        else:
            signal = 50
            confidence = 58
            reason = f"Neutral sentiment · 24h={trend_24h:+.1f}%"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

def analyze_risk_governor(df: pd.DataFrame) -> dict:
    try:
        closes = df["close"]
        highs = df["high"]
        lows = df["low"]
        price = closes.iloc[-1]

        atr = ta.volatility.AverageTrueRange(highs, lows, closes, window=14).average_true_range().iloc[-1]
        atr_pct = atr / price * 100 if price > 0 else 0
        recent_high = highs.iloc[-min(20, len(highs)):].max()
        drawdown = (price - recent_high) / recent_high * 100 if recent_high > 0 else 0

        if drawdown < -8:
            signal = 20
            confidence = 90
            reason = f"RISK ALERT: Drawdown={drawdown:.1f}% · ATR={atr_pct:.1f}%"
        elif atr_pct > 5:
            signal = 45
            confidence = 80
            reason = f"High volatility: ATR={atr_pct:.1f}% — caution"
        else:
            signal = 85
            confidence = 88
            reason = f"Portfolio safe: Drawdown={drawdown:.1f}% · ATR={atr_pct:.1f}%"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}

AGENT_FUNCTIONS = {
    "smart_dca": analyze_smart_dca,
    "momentum_breakout": analyze_momentum_breakout,
    "trend_follower": analyze_trend_follower,
    "grid_sniper": analyze_grid_sniper,
    "liquidity_sweep": analyze_liquidity_sweep,
    "micro_scalper": analyze_micro_scalper,
    "sentiment_ai": analyze_sentiment_ai,
    "risk_governor": analyze_risk_governor,
}

def run_consensus(pair: str, df: pd.DataFrame) -> dict:
    agents_results = {}
    total_weight = weighted_signal = weighted_confidence = 0.0

    for agent_id, cfg in AGENTS_REGISTRY.items():
        if not cfg["enabled"]:
            continue

        fn = AGENT_FUNCTIONS.get(agent_id)
        result = fn(df) if fn else {"signal": 50, "confidence": 50, "reason": "No function"}
        weight = cfg["weight"]

        agents_results[agent_id] = {
            "id": agent_id,
            "name": cfg["name"],
            "type": cfg["type"],
            "weight": weight,
            "signal": result["signal"],
            "confidence": result["confidence"],
            "reason": result["reason"],
            "status": "TRIGGERED" if result["signal"] >= MIN_SIGNAL else "SCANNING",
        }

        weighted_signal += result["signal"] * weight
        weighted_confidence += result["confidence"] * weight
        total_weight += weight

    net_signal = round(weighted_signal / total_weight, 2) if total_weight > 0 else 50
    net_confidence = round(weighted_confidence / total_weight, 2) if total_weight > 0 else 50

    if net_signal >= MIN_SIGNAL and net_confidence >= MIN_CONF:
        action = "FIRE_BUY"
    elif net_signal <= (100 - MIN_SIGNAL) and net_confidence >= MIN_CONF:
        action = "FIRE_SELL"
    else:
        action = "HOLD_AND_SCAN"

    return {
        "pair": pair,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "consensus": {
            "action": action,
            "net_signal": net_signal,
            "net_confidence": net_confidence,
            "threshold_signal": MIN_SIGNAL,
            "threshold_conf": MIN_CONF,
        },
        "agents": agents_results,
    }

def fetch_ohlcv_sync(pair: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame | None:
    """Fetch OHLCV synchronously via CCXT with KuCoin -> Binance automatic failover."""
    import ccxt
    
    # 1. Primary Attempt: KuCoin
    try:
        exchange = ccxt.kucoin({"enableRateLimit": True, "options": {"defaultType": "spot"}})
        raw = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
        if raw and len(raw) >= 15:
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df.astype(float)
    except Exception as e:
        log.warning(f"[OHLCV KuCoin] {pair} failed: {e}. Trying Binance fallback...")

    # 2. Secondary Failover Attempt: Binance
    try:
        exchange = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "spot"}})
        raw = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
        if raw and len(raw) >= 15:
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df.astype(float)
    except Exception as e:
        log.error(f"[OHLCV Binance Fallback] {pair} failed: {e}")

    return None

def push_to_proxy(data: dict):
    try:
        r = requests.post(f"{PROXY_URL}/api/agents/update", json=data, timeout=5)
        if r.status_code == 200:
            log.info("🔎 [Proxy]: Agent Radar updated successfully")
    except Exception as e:
        log.warning(f"[Proxy]: Push failed — {e}")

def scan_loop():
    global _scan_count, _last_scan_time, _latest_evaluations
    import time as _time
    _time.sleep(5)

    while True:
        _scan_count += 1
        _last_scan_time = datetime.now(timezone.utc).isoformat()
        log.info(f"🔎 [Sniper Engine]: Scan #{_scan_count} starting on {PAIRS}...")

        all_agents_for_proxy = []
        active_signals = []

        for pair in PAIRS:
            df = fetch_ohlcv_sync(pair, TF)
            if df is None:
                log.warning(f"◎ [Scanner]: No data available for {pair}")
                continue

            result = run_consensus(pair, df)
            _latest_evaluations[pair] = result

            action = result["consensus"]["action"]
            net_signal = result["consensus"]["net_signal"]
            net_conf = result["consensus"]["net_confidence"]

            for agent_id, ag in result["agents"].items():
                all_agents_for_proxy.append({
                    "name": ag["name"],
                    "action": "BUY" if ag["signal"] >= MIN_SIGNAL else ("SELL" if ag["signal"] <= (100 - MIN_SIGNAL) else "HOLD"),
                    "confidence": ag["confidence"],
                    "reason": ag["reason"],
                    "pair": pair,
                    "strategy": ag["name"],
                })

            if action == "FIRE_BUY":
                active_signals.append({"pair": pair, "action": "BUY", "confidence": net_conf})
                log.info(f"🎯 [SnipBot]: {pair} → FIRE_BUY · signal={net_signal} conf={net_conf}")
            elif action == "FIRE_SELL":
                active_signals.append({"pair": pair, "action": "SELL", "confidence": net_conf})
                log.info(f"⚡ [SnipBot]: {pair} → FIRE_SELL · signal={net_signal} conf={net_conf}")

        push_to_proxy({
            "timestamp": _last_scan_time,
            "scan_count": _scan_count,
            "strategies": all_agents_for_proxy,
            "signals": active_signals,
            "symbols": PAIRS,
        })

        log.info(f"◎ Sleeping {INTERVAL}s until next scan...")
        _time.sleep(INTERVAL)

# ── Flask API Routes ──────────────────────────────────────────────────────────

@app.route("/")
@app.route("/health")
def health():
    return jsonify({
        "status": "ONLINE",
        "service": "snipbot-agents-v12.3",
        "agents": len(AGENTS_REGISTRY),
        "pairs": PAIRS,
        "scan_count": _scan_count,
        "last_scan": _last_scan_time,
    }), 200

@app.route("/api/agents/status")
def agents_status():
    return jsonify({
        "status": "success",
        "total_agents": len(AGENTS_REGISTRY),
        "agents": list(AGENTS_REGISTRY.values()),
        "scan_count": _scan_count,
        "last_scan": _last_scan_time,
        "pairs": list(_latest_evaluations.keys()),
    }), 200

@app.route("/api/agents/evaluate")
def evaluate_pair():
    pair = request.args.get("pair", PAIRS[0] if PAIRS else "ADA/USDT")
    tf = request.args.get("timeframe", TF)

    if pair in _latest_evaluations:
        cached = _latest_evaluations[pair]
        cached_ts = cached.get("timestamp", "")
        if cached_ts:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(cached_ts)).total_seconds()
            if age < 300:
                return jsonify({"status": "success", "source": "cache", **cached}), 200

    df = fetch_ohlcv_sync(pair, tf)
    if df is None:
        if _latest_evaluations:
            fallback_key = list(_latest_evaluations.keys())[0]
            return jsonify({"status": "success", "source": "fallback_cache", **_latest_evaluations[fallback_key]}), 200
        return jsonify({"status": "success", "source": "empty", "evaluations": {}, "agents": AGENTS_REGISTRY}), 200

    result = run_consensus(pair, df)
    _latest_evaluations[pair] = result
    return jsonify({"status": "success", "source": "live", **result}), 200

@app.route("/api/agents/config", methods=["GET", "POST"])
def agents_config():
    if request.method == "GET":
        return jsonify({
            "status": "success",
            "config": {
                agent_id: {
                    "name": cfg["name"],
                    "weight": cfg["weight"],
                    "enabled": cfg["enabled"],
                }
                for agent_id, cfg in AGENTS_REGISTRY.items()
            }
        }), 200

    body = request.get_json(silent=True) or {}
    for agent_id, updates in body.items():
        if agent_id in AGENTS_REGISTRY:
            if "weight" in updates:
                AGENTS_REGISTRY[agent_id]["weight"] = float(updates["weight"])
            if "enabled" in updates:
                AGENTS_REGISTRY[agent_id]["enabled"] = bool(updates["enabled"])

    return jsonify({"status": "updated", "config": {k: v for k, v in AGENTS_REGISTRY.items()}}), 200

@app.route("/api/agents/pairs")
def latest_by_pair():
    return jsonify({"status": "success", "evaluations": _latest_evaluations}), 200

if __name__ == "__main__":
    log.info(f"🎯 [SnipBot Agents v12.3]: Starting Master Merged Engine — {len(AGENTS_REGISTRY)} agents · {PAIRS}")
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
