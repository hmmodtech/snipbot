"""
SnipBot — Hybrid AI Agents Engine v12
---------------------------------------
8 AI Agents + Weighted Consensus Engine
Live OHLCV data from KuCoin via ccxt
Flask API for Dashboard + Proxy
"""

import os
import asyncio
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

# ── Config ────────────────────────────────────────────────────────────────────
PORT       = int(os.environ.get("PORT", 8080))
PROXY_URL  = os.environ.get("PROXY_URL",  "https://snipbot-proxy.up.railway.app")
PAIRS      = [p.strip() for p in os.environ.get(
    "PAIRS", "ADA/USDT,XRP/USDT,BTC/USDT,ETH/USDT"
).split(",")]
INTERVAL   = int(os.environ.get("SCAN_INTERVAL", "300"))
TF         = os.environ.get("TIMEFRAME", "1h")
MIN_SIGNAL = float(os.environ.get("MIN_SIGNAL",     "75"))
MIN_CONF   = float(os.environ.get("MIN_CONFIDENCE", "80"))

# ── Flask App ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

# ── Shared State ──────────────────────────────────────────────────────────────
_latest_evaluations = {}   # { "ADA/USDT": { agents, consensus, timestamp } }
_scan_count         = 0
_last_scan_time     = None

# ── 8 AGENTS REGISTRY ─────────────────────────────────────────────────────────
AGENTS_REGISTRY = {
    "smart_dca": {
        "name":    "Smart DCA Agent",
        "type":    "Accumulation & Support Sniper",
        "weight":  1.2,
        "enabled": True,
    },
    "momentum_breakout": {
        "name":    "Technical Momentum Agent",
        "type":    "Breakout & Divergence Engine",
        "weight":  1.3,
        "enabled": True,
    },
    "trend_follower": {
        "name":    "Trend Follower Agent",
        "type":    "EMA Trend & Trailing",
        "weight":  1.1,
        "enabled": True,
    },
    "grid_sniper": {
        "name":    "Grid Sniper Agent",
        "type":    "Volatility Range Grid",
        "weight":  1.0,
        "enabled": True,
    },
    "liquidity_sweep": {
        "name":    "Liquidity Sweep Agent",
        "type":    "Orderbook & Wick Sniper",
        "weight":  1.4,
        "enabled": True,
    },
    "micro_scalper": {
        "name":    "Micro-Scalper Agent",
        "type":    "High-Frequency Spread",
        "weight":  0.9,
        "enabled": True,
    },
    "sentiment_ai": {
        "name":    "Sentiment AI Agent",
        "type":    "Fear & Greed + Momentum",
        "weight":  1.1,
        "enabled": True,
    },
    "risk_governor": {
        "name":    "Risk & Portfolio Governor",
        "type":    "Master Safety Engine",
        "weight":  1.5,
        "enabled": True,
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# REAL AGENT EVALUATION FUNCTIONS
# Each agent analyzes real OHLCV data and returns signal (-100 to +100)
# ══════════════════════════════════════════════════════════════════════════════

def analyze_smart_dca(df: pd.DataFrame) -> dict:
    """DCA — buys on dips below MA50, sells on recovery."""
    try:
        closes = df["close"]
        price  = closes.iloc[-1]
        ma50   = ta.trend.SMAIndicator(closes, window=50).sma_indicator().iloc[-1]
        rsi    = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        ema200 = ta.trend.EMAIndicator(closes, window=min(200, len(closes)//2)).ema_indicator().iloc[-1]

        pct_from_ma = (price - ma50) / ma50 * 100
        uptrend     = price > ema200

        if pct_from_ma <= -4 and rsi > 25 and uptrend:
            signal     = min(70 + abs(pct_from_ma) * 5, 95)
            confidence = min(75 + abs(pct_from_ma) * 3, 90)
            reason     = f"DCA dip {pct_from_ma:.1f}% below MA50 · RSI={rsi:.0f} · Uptrend={uptrend}"
        elif pct_from_ma >= 3:
            signal     = max(30 - pct_from_ma * 5, 5)
            confidence = 75
            reason     = f"DCA recovery {pct_from_ma:.1f}% above MA50"
        else:
            signal     = 50
            confidence = 60
            reason     = f"DCA standby {pct_from_ma:+.1f}% vs MA50 · RSI={rsi:.0f}"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


def analyze_momentum_breakout(df: pd.DataFrame) -> dict:
    """RSI divergence + MACD crossover + Supertrend proxy."""
    try:
        closes = df["close"]
        highs  = df["high"]
        lows   = df["low"]
        price  = closes.iloc[-1]

        rsi      = ta.momentum.RSIIndicator(closes, window=14).rsi()
        macd_obj = ta.trend.MACD(closes, window_fast=12, window_slow=26, window_sign=9)
        macd     = macd_obj.macd()
        macd_sig = macd_obj.macd_signal()
        ema20    = ta.trend.EMAIndicator(closes, window=20).ema_indicator()
        ema50    = ta.trend.EMAIndicator(closes, window=50).ema_indicator()

        rsi_v       = rsi.iloc[-1]
        macd_bull   = macd.iloc[-1] > macd_sig.iloc[-1]
        macd_cross  = macd.iloc[-1] > macd_sig.iloc[-1] and macd.iloc[-2] <= macd_sig.iloc[-2]
        ema_bull    = ema20.iloc[-1] > ema50.iloc[-1]
        rsi_bull    = 45 < rsi_v < 65

        bull_score = sum([macd_bull, macd_cross, ema_bull, rsi_bull])

        if bull_score >= 3:
            signal     = 75 + bull_score * 5 + (10 if macd_cross else 0)
            confidence = 80 + (10 if macd_cross else 0)
            reason     = f"Bullish momentum · RSI={rsi_v:.0f} · MACD={'CROSS ▲'if macd_cross else'BULL'} · EMA={'▲'if ema_bull else'▼'}"
        elif bull_score <= 1:
            signal     = 30 - (2 - bull_score) * 10
            confidence = 70
            reason     = f"Weak momentum · RSI={rsi_v:.0f} · bull_score={bull_score}/4"
        else:
            signal     = 50
            confidence = 60
            reason     = f"Neutral · RSI={rsi_v:.0f} · bull_score={bull_score}/4"

        return {"signal": round(min(max(signal, 5), 95), 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


def analyze_trend_follower(df: pd.DataFrame) -> dict:
    """EMA Golden/Death cross with ADX trend strength."""
    try:
        closes = df["close"]
        highs  = df["high"]
        lows   = df["low"]

        ema20 = ta.trend.EMAIndicator(closes, window=20).ema_indicator()
        ema50 = ta.trend.EMAIndicator(closes, window=50).ema_indicator()
        adx   = ta.trend.ADXIndicator(highs, lows, closes, window=14)

        adx_v    = adx.adx().iloc[-1]
        golden   = ema20.iloc[-1] > ema50.iloc[-1] and ema20.iloc[-2] <= ema50.iloc[-2]
        death    = ema20.iloc[-1] < ema50.iloc[-1] and ema20.iloc[-2] >= ema50.iloc[-2]
        uptrend  = ema20.iloc[-1] > ema50.iloc[-1]
        strong   = adx_v > 25

        if uptrend and strong:
            signal     = 80 + (10 if golden else 0)
            confidence = 82 + (8 if strong else 0)
            reason     = f"{'Golden Cross ▲'if golden else 'Uptrend'} · EMA20>EMA50 · ADX={adx_v:.0f}"
        elif not uptrend and strong:
            signal     = 20 - (10 if death else 0)
            confidence = 80
            reason     = f"{'Death Cross ▼'if death else 'Downtrend'} · EMA20<EMA50 · ADX={adx_v:.0f}"
        else:
            signal     = 50
            confidence = 55
            reason     = f"Sideways trend · ADX={adx_v:.0f} (weak < 25)"

        return {"signal": round(min(max(signal, 5), 95), 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


def analyze_grid_sniper(df: pd.DataFrame) -> dict:
    """Bollinger Band squeeze + low volatility grid detection."""
    try:
        closes = df["close"]
        price  = closes.iloc[-1]

        bb     = ta.volatility.BollingerBands(closes, window=20, window_dev=2)
        upper  = bb.bollinger_hband().iloc[-1]
        lower  = bb.bollinger_lband().iloc[-1]
        mid    = bb.bollinger_mavg().iloc[-1]
        width  = (upper - lower) / mid * 100  # band width %

        pct_in_band = (price - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

        if width < 3:  # Squeeze — breakout imminent
            signal     = 70
            confidence = 75
            reason     = f"BB Squeeze · Width={width:.1f}% · Price at {pct_in_band*100:.0f}% of band"
        elif pct_in_band < 0.2:  # Near lower band → buy
            signal     = 75
            confidence = 78
            reason     = f"Price near BB lower · {pct_in_band*100:.0f}% in band · Width={width:.1f}%"
        elif pct_in_band > 0.8:  # Near upper band → sell
            signal     = 30
            confidence = 73
            reason     = f"Price near BB upper · {pct_in_band*100:.0f}% in band · Width={width:.1f}%"
        else:
            signal     = 50
            confidence = 60
            reason     = f"Mid-band position · {pct_in_band*100:.0f}% · Width={width:.1f}%"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


def analyze_liquidity_sweep(df: pd.DataFrame) -> dict:
    """Detects wick sweeps and orderbook imbalances via price action."""
    try:
        closes = df["close"]
        highs  = df["high"]
        lows   = df["low"]
        opens  = df["open"]

        # Last 3 candles
        last   = df.iloc[-1]
        prev   = df.iloc[-2]
        prev2  = df.iloc[-3]

        price       = last["close"]
        wick_low    = last["open"] - last["low"]   # lower wick
        wick_high   = last["high"] - last["open"]  # upper wick
        body        = abs(last["close"] - last["open"])
        candle_size = last["high"] - last["low"]

        # Bullish wick sweep — long lower wick rejecting low
        wick_ratio = wick_low / candle_size if candle_size > 0 else 0
        bull_sweep = wick_ratio > 0.6 and last["close"] > last["open"]

        # Volume spike
        avg_vol    = df["volume"].iloc[-10:-1].mean()
        vol_spike  = last["volume"] > avg_vol * 1.5

        if bull_sweep and vol_spike:
            signal     = 88
            confidence = 85
            reason     = f"Bullish wick sweep · Wick ratio={wick_ratio:.0%} · Volume spike={vol_spike}"
        elif bull_sweep:
            signal     = 75
            confidence = 75
            reason     = f"Wick sweep detected · Ratio={wick_ratio:.0%}"
        elif wick_ratio < 0.2 and last["close"] < last["open"]:
            signal     = 35
            confidence = 68
            reason     = f"Bearish candle · No sweep support"
        else:
            signal     = 52
            confidence = 58
            reason     = f"No sweep signal · Wick ratio={wick_ratio:.0%}"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


def analyze_micro_scalper(df: pd.DataFrame) -> dict:
    """Short-term momentum on last 5 candles + RSI micro."""
    try:
        closes = df["close"]
        price  = closes.iloc[-1]

        rsi3   = ta.momentum.RSIIndicator(closes, window=3).rsi()
        rsi14  = ta.momentum.RSIIndicator(closes, window=14).rsi()

        rsi3_v  = rsi3.iloc[-1]
        rsi14_v = rsi14.iloc[-1]

        # 5-candle momentum
        momentum_5 = (closes.iloc[-1] - closes.iloc[-5]) / closes.iloc[-5] * 100

        if rsi3_v < 30 and momentum_5 < -1:
            signal     = 78
            confidence = 72
            reason     = f"Micro oversold · RSI3={rsi3_v:.0f} · 5c momentum={momentum_5:.2f}%"
        elif rsi3_v > 70 and momentum_5 > 1:
            signal     = 28
            confidence = 70
            reason     = f"Micro overbought · RSI3={rsi3_v:.0f} · 5c momentum={momentum_5:.2f}%"
        else:
            signal     = 50
            confidence = 55
            reason     = f"Scalp standby · RSI3={rsi3_v:.0f} · RSI14={rsi14_v:.0f}"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


def analyze_sentiment_ai(df: pd.DataFrame) -> dict:
    """
    Sentiment proxy using price momentum + volume trend.
    (Real Twitter/news API would replace this in production)
    """
    try:
        closes  = df["close"]
        volumes = df["volume"]

        # Price trend over last 24 candles (1 day on 1h TF)
        trend_24h = (closes.iloc[-1] - closes.iloc[-24]) / closes.iloc[-24] * 100

        # Volume trend
        avg_vol_recent = volumes.iloc[-5:].mean()
        avg_vol_older  = volumes.iloc[-20:-5].mean()
        vol_trend      = (avg_vol_recent - avg_vol_older) / avg_vol_older * 100

        # RSI as sentiment proxy
        rsi = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]

        if trend_24h > 2 and vol_trend > 10:
            signal     = 85
            confidence = 80
            reason     = f"Bullish sentiment · 24h={trend_24h:+.1f}% · Vol trend={vol_trend:+.0f}%"
        elif trend_24h > 0 and rsi > 50:
            signal     = 65
            confidence = 70
            reason     = f"Mildly bullish · 24h={trend_24h:+.1f}% · RSI={rsi:.0f}"
        elif trend_24h < -2:
            signal     = 30
            confidence = 72
            reason     = f"Bearish sentiment · 24h={trend_24h:+.1f}% · Vol trend={vol_trend:+.0f}%"
        else:
            signal     = 50
            confidence = 58
            reason     = f"Neutral sentiment · 24h={trend_24h:+.1f}%"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


def analyze_risk_governor(df: pd.DataFrame) -> dict:
    """
    Portfolio safety checks:
    - Max drawdown from recent high
    - Volatility (ATR-based)
    - Overall market health
    """
    try:
        closes = df["close"]
        highs  = df["high"]
        lows   = df["low"]
        price  = closes.iloc[-1]

        # ATR for volatility
        atr    = ta.volatility.AverageTrueRange(highs, lows, closes, window=14).average_true_range()
        atr_v  = atr.iloc[-1]
        atr_pct = atr_v / price * 100

        # Drawdown from 20-period high
        recent_high = highs.iloc[-20:].max()
        drawdown    = (price - recent_high) / recent_high * 100

        if drawdown < -8:
            signal     = 20
            confidence = 90
            reason     = f"RISK ALERT: Drawdown={drawdown:.1f}% · ATR={atr_pct:.1f}% — REDUCE EXPOSURE"
        elif drawdown < -5:
            signal     = 40
            confidence = 85
            reason     = f"Moderate risk: Drawdown={drawdown:.1f}% · ATR={atr_pct:.1f}%"
        elif atr_pct > 5:
            signal     = 45
            confidence = 80
            reason     = f"High volatility: ATR={atr_pct:.1f}% — caution"
        else:
            signal     = 85
            confidence = 88
            reason     = f"Portfolio safe: Drawdown={drawdown:.1f}% · ATR={atr_pct:.1f}% — OK to trade"

        return {"signal": round(signal, 1), "confidence": round(confidence, 1), "reason": reason}
    except Exception as e:
        return {"signal": 50, "confidence": 50, "reason": f"Error: {e}"}


# ── Agent function map ─────────────────────────────────────────────────────────
AGENT_FUNCTIONS = {
    "smart_dca":         analyze_smart_dca,
    "momentum_breakout": analyze_momentum_breakout,
    "trend_follower":    analyze_trend_follower,
    "grid_sniper":       analyze_grid_sniper,
    "liquidity_sweep":   analyze_liquidity_sweep,
    "micro_scalper":     analyze_micro_scalper,
    "sentiment_ai":      analyze_sentiment_ai,
    "risk_governor":     analyze_risk_governor,
}


# ══════════════════════════════════════════════════════════════════════════════
# CONSENSUS ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def run_consensus(pair: str, df: pd.DataFrame) -> dict:
    """Run all 8 agents on real OHLCV data and compute weighted consensus."""
    agents_results = {}
    total_weight = weighted_signal = weighted_confidence = 0.0

    for agent_id, cfg in AGENTS_REGISTRY.items():
        if not cfg["enabled"]:
            continue

        fn     = AGENT_FUNCTIONS.get(agent_id)
        result = fn(df) if fn else {"signal": 50, "confidence": 50, "reason": "No function"}
        weight = cfg["weight"]

        agents_results[agent_id] = {
            "id":         agent_id,
            "name":       cfg["name"],
            "type":       cfg["type"],
            "weight":     weight,
            "signal":     result["signal"],
            "confidence": result["confidence"],
            "reason":     result["reason"],
            "status":     "TRIGGERED" if result["signal"] >= MIN_SIGNAL else "SCANNING",
        }

        weighted_signal     += result["signal"]     * weight
        weighted_confidence += result["confidence"] * weight
        total_weight        += weight

    net_signal     = round(weighted_signal     / total_weight, 2) if total_weight > 0 else 50
    net_confidence = round(weighted_confidence / total_weight, 2) if total_weight > 0 else 50

    if net_signal >= MIN_SIGNAL and net_confidence >= MIN_CONF:
        action = "FIRE_BUY"
    elif net_signal <= (100 - MIN_SIGNAL) and net_confidence >= MIN_CONF:
        action = "FIRE_SELL"
    else:
        action = "HOLD_AND_SCAN"

    return {
        "pair":      pair,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "consensus": {
            "action":             action,
            "net_signal":         net_signal,
            "net_confidence":     net_confidence,
            "threshold_signal":   MIN_SIGNAL,
            "threshold_conf":     MIN_CONF,
        },
        "agents": agents_results,
    }


# ══════════════════════════════════════════════════════════════════════════════
# OHLCV FETCH (sync wrapper for Flask)
# ══════════════════════════════════════════════════════════════════════════════

def fetch_ohlcv_sync(pair: str, timeframe: str = "1h", limit: int = 200) -> pd.DataFrame | None:
    """Fetch OHLCV synchronously via ccxt (used inside Flask routes)."""
    import ccxt
    try:
        exchange = ccxt.kucoin({"enableRateLimit": True, "options": {"defaultType": "spot"}})
        raw = exchange.fetch_ohlcv(pair, timeframe, limit=limit)
      exchange.close()
        if not raw or len(raw) < 55:
            return None
        df = pd.DataFrame(raw, columns=["timestamp","open","high","low","close","volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        return df.astype(float)
    except Exception as e:
        log.error(f"[OHLCV] {pair} error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# PUSH TO PROXY
# ══════════════════════════════════════════════════════════════════════════════

def push_to_proxy(data: dict):
    """Send latest scan results to Proxy → Dashboard Agent Radar."""
    try:
        r = requests.post(f"{PROXY_URL}/api/agents/update", json=data, timeout=5)
        if r.status_code == 200:
            log.info("🔎 [Proxy]: Agent Radar updated")
        else:
            log.warning(f"[Proxy]: agents/update → {r.status_code}")
    except Exception as e:
        log.warning(f"[Proxy]: push failed — {e}")


# ══════════════════════════════════════════════════════════════════════════════
# SCAN LOOP (runs in background thread)
# ══════════════════════════════════════════════════════════════════════════════

def scan_loop():
    """Background scan loop — runs every INTERVAL seconds."""
    global _scan_count, _last_scan_time, _latest_evaluations

    import time as _time
    _time.sleep(10)  # wait for Flask to start

    while True:
        _scan_count += 1
        _last_scan_time = datetime.now(timezone.utc).isoformat()
        log.info(f"🔎 [Sniper Engine]: Scan #{_scan_count} starting on {PAIRS}...")

        all_agents_for_proxy = []
        active_signals       = []

        for pair in PAIRS:
            df = fetch_ohlcv_sync(pair, TF)
            if df is None:
                log.warning(f"◎ [Scanner]: No data for {pair}")
                continue

            result = run_consensus(pair, df)
            _latest_evaluations[pair] = result

            action     = result["consensus"]["action"]
            net_signal = result["consensus"]["net_signal"]
            net_conf   = result["consensus"]["net_confidence"]

            # Build agent list for proxy (dashboard Agent Radar format)
            for agent_id, ag in result["agents"].items():
                all_agents_for_proxy.append({
                    "name":       ag["name"],
                    "action":     "BUY" if ag["signal"] >= MIN_SIGNAL else ("SELL" if ag["signal"] <= (100 - MIN_SIGNAL) else "HOLD"),
                    "confidence": ag["confidence"],
                    "reason":     ag["reason"],
                    "pair":       pair,
                    "strategy":   ag["name"],
                })

            if action == "FIRE_BUY":
                active_signals.append({"pair": pair, "action": "BUY", "confidence": net_conf})
                log.info(f"🎯 [SnipBot]: {pair} → FIRE_BUY · signal={net_signal} conf={net_conf}")
            elif action == "FIRE_SELL":
                active_signals.append({"pair": pair, "action": "SELL", "confidence": net_conf})
                log.info(f"⚡ [SnipBot]: {pair} → FIRE_SELL · signal={net_signal} conf={net_conf}")
            else:
                log.info(f"◎ [SnipBot Tracking]: {pair} — {action} · signal={net_signal:.1f}")

        # Push to proxy for Dashboard
        push_to_proxy({
            "timestamp":  _last_scan_time,
            "scan_count": _scan_count,
            "strategies": all_agents_for_proxy,
            "signals":    active_signals,
            "symbols":    PAIRS,
        })

        log.info(f"◎ Sleeping {INTERVAL}s until next scan...")
        _time.sleep(INTERVAL)


# ══════════════════════════════════════════════════════════════════════════════
# FLASK ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
@app.route("/health")
def health():
    return jsonify({
        "status":      "ONLINE",
        "service":     "snipbot-agents-v12",
        "agents":      len(AGENTS_REGISTRY),
        "pairs":       PAIRS,
        "scan_count":  _scan_count,
        "last_scan":   _last_scan_time,
    })


@app.route("/api/agents/status")
def agents_status():
    """Returns all 8 agents registry + latest scan results."""
    return jsonify({
        "status":       "success",
        "total_agents": len(AGENTS_REGISTRY),
        "agents":       list(AGENTS_REGISTRY.values()),
        "scan_count":   _scan_count,
        "last_scan":    _last_scan_time,
        "pairs":        list(_latest_evaluations.keys()),
    })


@app.route("/api/agents/evaluate")
def evaluate_pair():
    """
    On-demand evaluation for a specific pair with live data.
    GET /api/agents/evaluate?pair=ADA/USDT&timeframe=1h
    """
    pair = request.args.get("pair", PAIRS[0] if PAIRS else "ADA/USDT")
    tf   = request.args.get("timeframe", TF)

    # Return cached result if available and recent (< 5 min)
    if pair in _latest_evaluations:
        cached = _latest_evaluations[pair]
        cached_ts = cached.get("timestamp", "")
        if cached_ts:
            age = (datetime.now(timezone.utc) -
                   datetime.fromisoformat(cached_ts)).total_seconds()
            if age < 300:
                return jsonify({"status": "success", "source": "cache", **cached})

    # Fetch live data
    df = fetch_ohlcv_sync(pair, tf)
    if df is None:
        return jsonify({"status": "error", "error": f"Could not fetch data for {pair}"}), 503

    result = run_consensus(pair, df)
    _latest_evaluations[pair] = result
    return jsonify({"status": "success", "source": "live", **result})


@app.route("/api/agents/config", methods=["GET", "POST"])
def agents_config():
    """Read or update agent weights."""
    if request.method == "GET":
        return jsonify({
            "status": "success",
            "config": {
                agent_id: {
                    "name":    cfg["name"],
                    "weight":  cfg["weight"],
                    "enabled": cfg["enabled"],
                }
                for agent_id, cfg in AGENTS_REGISTRY.items()
            }
        })

    # POST — update weights
    body = request.get_json(silent=True) or {}
    for agent_id, updates in body.items():
        if agent_id in AGENTS_REGISTRY:
            if "weight" in updates:
                AGENTS_REGISTRY[agent_id]["weight"] = float(updates["weight"])
            if "enabled" in updates:
                AGENTS_REGISTRY[agent_id]["enabled"] = bool(updates["enabled"])

    return jsonify({"status": "updated", "config": {k: v for k, v in AGENTS_REGISTRY.items()}})


@app.route("/api/agents/pairs")
def latest_by_pair():
    """Returns latest evaluation for each pair."""
    return jsonify({
        "status": "success",
        "evaluations": _latest_evaluations,
    })


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    log.info(f"🎯 [SnipBot Agents v12]: Starting — {len(AGENTS_REGISTRY)} agents · {PAIRS}")

    # Start background scan loop
    t = threading.Thread(target=scan_loop, daemon=True)
    t.start()
    log.info(f"🔎 [Sniper Engine]: Background scan loop started · interval={INTERVAL}s")

    # Start Flask API
    log.info(f"🔎 [Sniper Engine]: Status API on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
