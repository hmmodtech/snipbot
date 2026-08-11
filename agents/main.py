"""
====================================================================
🎯 SnipBot AI Agents Microservice v2.0 - Multi-Agent Engine (8 Agents)
Railway Service: snipbot-agents.up.railway.app
====================================================================
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import time
import random

app = Flask(__name__)
CORS(app)

# ------------------------------------------------------------------
# 🧠 8 AI AGENTS CONFIGURATION & WEIGHT MATRIX
# ------------------------------------------------------------------
AGENTS_REGISTRY = {
    "smart_dca": {
        "id": "smart_dca",
        "name": "Smart DCA Agent",
        "type": "Accumulation & Support Sniper",
        "weight": 1.2,
        "enabled": True,
        "description": "Dynamic Dollar-Cost Averaging based on Fib levels & support zones."
    },
    "grid_sniper": {
        "id": "grid_sniper",
        "name": "Grid Sniper Agent",
        "type": "Volatility Range Grid",
        "weight": 1.0,
        "enabled": True,
        "description": "Adaptive ATR-driven grid bounds for side-ways markets."
    },
    "sentiment_ai": {
        "id": "sentiment_ai",
        "name": "Sentiment & News AI Agent",
        "type": "LLM News & Social Scanner",
        "weight": 1.1,
        "enabled": True,
        "description": "Scans Twitter/X, CryptoPanic & Panic index using NLP LLM."
    },
    "momentum_breakout": {
        "id": "momentum_breakout",
        "name": "Technical Momentum Agent",
        "type": "Breakout & Divergence Engine",
        "weight": 1.3,
        "enabled": True,
        "description": "Multi-indicator consensus (RSI, MACD, Supertrend, Volume)."
    },
    "liquidity_sweep": {
        "id": "liquidity_sweep",
        "name": "Liquidity Sweep Agent",
        "type": "Orderbook & Wick Sniper",
        "weight": 1.4,
        "enabled": True,
        "description": "Detects orderbook imbalances, ask sweeps, and high-leverage liquidation pools."
    },
    "trend_follower": {
        "id": "trend_follower",
        "name": "Trend Follower & Trailing Agent",
        "type": "Trend Momentum & Dynamic Trailing",
        "weight": 1.1,
        "enabled": True,
        "description": "EMA Golden Cross & ADX trend filter with AI-managed dynamic stop loss."
    },
    "micro_scalper": {
        "id": "micro_scalper",
        "name": "Micro-Scalper Agent",
        "type": "High-Frequency Spread Exploiter",
        "weight": 0.9,
        "enabled": True,
        "description": "Captures micro spreads on 1m/5m orderbook liquidity gaps."
    },
    "risk_governor": {
        "id": "risk_governor",
        "name": "Risk & Portfolio Governor Agent",
        "type": "Master Portfolio Safety Engine",
        "weight": 1.5,
        "enabled": True,
        "description": "Master Governor: Enforces drawdown limits, exposure controls & capital allocation."
    }
}

# ------------------------------------------------------------------
# 🎯 AGENT SIGNAL EVALUATION LOGIC
# ------------------------------------------------------------------
def evaluate_agent_signal(agent_id, pair, market_data):
    """
    Evaluates individual agent logic and produces signal score (-100 to +100)
    and confidence score (0 to 100%).
    """
    # Sample analytical dynamic logic (Expandable per agent)
    if agent_id == "smart_dca":
        return {"signal": 75, "confidence": 85, "reason": "Price sitting on major 0.618 Fib support; Tier-1 DCA layer active."}
    elif agent_id == "grid_sniper":
        return {"signal": 50, "confidence": 78, "reason": "Low volatility ATR phase detected; Grid bounds set [-$250, +$450]."}
    elif agent_id == "sentiment_ai":
        return {"signal": 88, "confidence": 92, "reason": "Bullish sentiment score 0.84 on X & news feeds."}
    elif agent_id == "momentum_breakout":
        return {"signal": 80, "confidence": 86, "reason": "RSI Bullish Divergence on 1h + MACD bullish crossover."}
    elif agent_id == "liquidity_sweep":
        return {"signal": 92, "confidence": 90, "reason": "Orderbook ask sweep detected; Liquidation wick tapped."}
    elif agent_id == "trend_follower":
        return {"signal": 65, "confidence": 80, "reason": "EMA 20/50 Golden Cross active; ADX > 25 (Strong trend)."}
    elif agent_id == "micro_scalper":
        return {"signal": 45, "confidence": 70, "reason": "Tight spread detected; Low risk scalp trigger."}
    elif agent_id == "risk_governor":
        return {"signal": 85, "confidence": 95, "reason": "Current portfolio drawdown 0.8% (Limit: 3.5%). Allocation approved."}
    
    return {"signal": 0, "confidence": 50, "reason": "Neutral standby."}

# ------------------------------------------------------------------
# 📊 API ENDPOINTS
# ------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ONLINE",
        "service": "snipbot-agents",
        "agents_count": len(AGENTS_REGISTRY),
        "timestamp": time.time()
    }), 200

@app.route('/api/agents/status', methods=['GET'])
def get_agents_status():
    """Returns status and configuration of all 8 AI Agents."""
    return jsonify({
        "status": "success",
        "total_agents": len(AGENTS_REGISTRY),
        "agents": list(AGENTS_REGISTRY.values())
    }), 200

@app.route('/api/agents/evaluate', methods=['GET', 'POST'])
def evaluate_pair():
    """
    Evaluates market data across all 8 AI Agents and calculates Weighted Consensus.
    """
    pair = request.args.get('pair', 'BTC/USDT')
    
    signals = {}
    total_weight = 0
    weighted_signal_sum = 0
    weighted_confidence_sum = 0

    for agent_id, cfg in AGENTS_REGISTRY.items():
        if not cfg["enabled"]:
            continue

        eval_res = evaluate_agent_signal(agent_id, pair, {})
        weight = cfg["weight"]

        signals[agent_id] = {
            "id": agent_id,
            "name": cfg["name"],
            "type": cfg["type"],
            "weight": weight,
            "signal": eval_res["signal"],
            "confidence": eval_res["confidence"],
            "reason": eval_res["reason"],
            "status": "TRIGGERED" if eval_res["signal"] >= 70 else "SCANNING"
        }

        weighted_signal_sum += eval_res["signal"] * weight
        weighted_confidence_sum += eval_res["confidence"] * weight
        total_weight += weight

    net_signal = round(weighted_signal_sum / total_weight, 2) if total_weight > 0 else 0
    net_confidence = round(weighted_confidence_sum / total_weight, 2) if total_weight > 0 else 0

    # Decision Matrix Thresholds
    if net_signal >= 75 and net_confidence >= 80:
        consensus_action = "FIRE_BUY"
    elif net_signal <= -75 and net_confidence >= 80:
        consensus_action = "FIRE_SELL"
    else:
        consensus_action = "HOLD_AND_SCAN"

    return jsonify({
        "status": "success",
        "pair": pair,
        "consensus": {
            "action": consensus_action,
            "net_signal": net_signal,
            "net_confidence": net_confidence,
            "threshold_required": 75,
            "timestamp": time.time()
        },
        "agents_evaluations": signals
    }), 200

@app.route('/api/agents/config', methods=['POST'])
def update_config():
    """Allows dynamic adjustment of agent weights and activation state."""
    data = request.json or {}
    agent_id = data.get('agent_id')
    if agent_id in AGENTS_REGISTRY:
        if 'weight' in data:
            AGENTS_REGISTRY[agent_id]['weight'] = float(data['weight'])
        if 'enabled' in data:
            AGENTS_REGISTRY[agent_id]['enabled'] = bool(data['enabled'])
        return jsonify({"status": "updated", "agent": AGENTS_REGISTRY[agent_id]}), 200
    return jsonify({"status": "error", "message": "Agent not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
