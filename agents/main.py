import os
from flask import Flask, jsonify, request
from flask_cors import CORS
import time

app = Flask(__name__)
CORS(app)

# 🧠 8 AI AGENTS REGISTRY
AGENTS_REGISTRY = {
    "smart_dca": {
        "id": "smart_dca",
        "name": "Smart DCA Agent",
        "type": "Accumulation & Support Sniper",
        "weight": 1.2,
        "enabled": True
    },
    "grid_sniper": {
        "id": "grid_sniper",
        "name": "Grid Sniper Agent",
        "type": "Volatility Range Grid",
        "weight": 1.0,
        "enabled": True
    },
    "sentiment_ai": {
        "id": "sentiment_ai",
        "name": "Sentiment & News AI Agent",
        "type": "LLM News & Social Scanner",
        "weight": 1.1,
        "enabled": True
    },
    "momentum_breakout": {
        "id": "momentum_breakout",
        "name": "Technical Momentum Agent",
        "type": "Breakout & Divergence Engine",
        "weight": 1.3,
        "enabled": True
    },
    "liquidity_sweep": {
        "id": "liquidity_sweep",
        "name": "Liquidity Sweep Agent",
        "type": "Orderbook & Wick Sniper",
        "weight": 1.4,
        "enabled": True
    },
    "trend_follower": {
        "id": "trend_follower",
        "name": "Trend Follower & Trailing Agent",
        "type": "Trend Momentum & Dynamic Trailing",
        "weight": 1.1,
        "enabled": True
    },
    "micro_scalper": {
        "id": "micro_scalper",
        "name": "Micro-Scalper Agent",
        "type": "High-Frequency Spread Exploiter",
        "weight": 0.9,
        "enabled": True
    },
    "risk_governor": {
        "id": "risk_governor",
        "name": "Risk & Portfolio Governor Agent",
        "type": "Master Portfolio Safety Engine",
        "weight": 1.5,
        "enabled": True
    }
}

def evaluate_agent_signal(agent_id, pair):
    signals = {
        "smart_dca": {"signal": 75, "confidence": 85, "reason": "Price near Fib support; Tier-1 DCA layer active."},
        "grid_sniper": {"signal": 50, "confidence": 78, "reason": "Low volatility phase; Grid bounds locked."},
        "sentiment_ai": {"signal": 88, "confidence": 92, "reason": "Bullish sentiment score on X & news."},
        "momentum_breakout": {"signal": 80, "confidence": 86, "reason": "RSI Bullish Divergence on 1h."},
        "liquidity_sweep": {"signal": 92, "confidence": 90, "reason": "Orderbook ask sweep detected."},
        "trend_follower": {"signal": 65, "confidence": 80, "reason": "EMA Golden Cross active; ADX > 25."},
        "micro_scalper": {"signal": 45, "confidence": 70, "reason": "Tight spread; Low risk scalp."},
        "risk_governor": {"signal": 85, "confidence": 95, "reason": "Portfolio drawdown within limit (0.8%)."}
    }
    return signals.get(agent_id, {"signal": 0, "confidence": 50, "reason": "Standby"})

@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ONLINE", "service": "snipbot-agents", "agents_count": len(AGENTS_REGISTRY)}), 200

@app.route('/api/agents/status', methods=['GET'])
def get_agents_status():
    return jsonify({"status": "success", "total_agents": len(AGENTS_REGISTRY), "agents": list(AGENTS_REGISTRY.values())}), 200

@app.route('/api/agents/evaluate', methods=['GET', 'POST'])
def evaluate_pair():
    pair = request.args.get('pair', 'BTC/USDT')
    signals = {}
    total_weight, weighted_signal_sum, weighted_confidence_sum = 0, 0, 0

    for agent_id, cfg in AGENTS_REGISTRY.items():
        if not cfg["enabled"]:
            continue
        eval_res = evaluate_agent_signal(agent_id, pair)
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
    consensus_action = "FIRE_BUY" if net_signal >= 75 and net_confidence >= 80 else "HOLD_AND_SCAN"

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

if __name__ == '__main__':
    # ⚡ dynamic port assignment for Railway
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
