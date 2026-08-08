"""
SnipBot — Hybrid Agent Runner + Status API
-------------------------------------------
Scan loop + Flask HTTP server running concurrently.
GET /status  → آخر نتائج scan لكل pair
GET /health  → health check
"""

import asyncio
import logging
import os
import sys
import time
import threading
from datetime import datetime, timezone
from typing import Optional, List
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-16s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("SnipBot")

from scanner          import Scanner
from strategy_manager import StrategyManager
from notifier         import Notifier

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN    = os.environ.get("TELEGRAM_TOKEN",   "")
CHAT_ID  = os.environ.get("TELEGRAM_CHAT_ID", "")
INTERVAL = int(os.environ.get("SCAN_INTERVAL", "300"))
MIN_CONF = float(os.environ.get("MIN_CONFIDENCE", "65"))
PAIRS    = [p.strip() for p in os.environ.get("PAIRS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT").split(",")]
TF       = os.environ.get("TIMEFRAME", "1h")
PORT     = int(os.environ.get("PORT", "8080"))

CONFIG = {
    "KUCOIN_API_KEY": os.environ.get("KUCOIN_API_KEY", ""),
    "KUCOIN_SECRET":  os.environ.get("KUCOIN_SECRET",  ""),
    "KUCOIN_PASS":    os.environ.get("KUCOIN_PASS",    ""),
    "pairs":    PAIRS,
    "timeframe": TF,
}

# ── Shared state (scan results) ───────────────────────────────────────────────
# Written by scan loop, read by Flask API
scan_state = {
    "last_scan":    None,      # ISO timestamp
    "scan_count":   0,
    "pairs":        {},        # { "BTC/USDT": { action, confidence, reason, strategy } }
    "active_signals": [],      # actionable signals only
    "system": {
        "strategies": ["TA", "DCA"],
        "min_confidence": MIN_CONF,
        "interval_sec":   INTERVAL,
        "timeframe":      TF,
        "pairs":          PAIRS,
    }
}

# ── Flask Status API ──────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)

@app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "scan_count": scan_state["scan_count"],
        "last_scan":  scan_state["last_scan"],
    })

@app.route("/status")
def status():
    return jsonify(scan_state)

@app.route("/api/agents/status")
def agents_status():
    """Same as /status — matches proxy endpoint naming."""
    return jsonify(scan_state)


def run_flask():
    """Run Flask in a background thread."""
    import logging as _log
    _log.getLogger("werkzeug").setLevel(_log.ERROR)
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


# ── Scan Loop ─────────────────────────────────────────────────────────────────
async def run():
    if not TOKEN or not CHAT_ID:
        log.error("⛔ [SnipBot ABORT]: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing.")
        sys.exit(1)

    log.info("🎯 SnipBot Hybrid System starting...")
    log.info(f"Symbols:    {PAIRS}")
    log.info(f"Strategies: ['TA', 'DCA']")
    log.info(f"Interval:   {INTERVAL // 60} min")
    log.info(f"Min conf:   {MIN_CONF:.0f}%")
    log.info(f"Status API: port {PORT}")

    notifier = Notifier(TOKEN, CHAT_ID)
    scanner  = Scanner(CONFIG)

    await notifier.send(
        f"🎯 <b>[SnipBot]</b>: Hybrid Agent System online.\n"
        f"Pairs: {' · '.join(PAIRS)} · TF: {TF}\n"
        f"Scan every {INTERVAL//60} min · Min conf: {MIN_CONF:.0f}%"
    )

    scan_count = 0

    try:
        while True:
            scan_count += 1
            scan_state["scan_count"] = scan_count
            log.info(f"🔎 [Sniper Engine]: Scan #{scan_count} starting...")

            try:
                # Run strategies on all pairs
                pair_results = {}
                active_signals = []

                for pair in PAIRS:
                    df = await scanner.fetch_ohlcv(pair)
                    if df is None:
                        pair_results[pair] = {
                            "action": "NO DATA", "confidence": 0,
                            "reason": "Could not fetch OHLCV", "strategy": "—"
                        }
                        continue

                    signal = scanner.manager.vote(pair, df)

                    if signal:
                        pair_results[pair] = {
                            "action":      signal.action,
                            "confidence":  round(signal.confidence, 1),
                            "reason":      signal.reason,
                            "strategy":    signal.strategy,
                            "entry_price": signal.entry_price,
                            "stop_loss":   signal.stop_loss,
                            "take_profit": signal.take_profit,
                        }
                        if signal.is_actionable(MIN_CONF):
                            active_signals.append(signal)
                    else:
                        pair_results[pair] = {
                            "action": "HOLD", "confidence": 50,
                            "reason": "No consensus", "strategy": "—"
                        }

                # Update shared state
                scan_state["last_scan"]      = datetime.now(timezone.utc).isoformat()
                scan_state["pairs"]          = pair_results
                scan_state["active_signals"] = [
                    {"pair": s.pair, "action": s.action,
                     "confidence": round(s.confidence, 1), "strategy": s.strategy}
                    for s in active_signals
                ]

                # Send Telegram alerts
                for sig in active_signals:
                    if sig.action == "BUY":
                        await notifier.target_acquired(sig)
                    elif sig.action == "SELL":
                        await notifier.sell_signal(sig)

                if not active_signals:
                    log.info(f"◎ [SnipBot Tracking]: No triggers on scan #{scan_count}.")

                if scan_count % 6 == 0:
                    await notifier.scan_summary(
                        len(PAIRS), len(active_signals),
                        [s.pair for s in active_signals]
                    )

            except Exception as e:
                log.error(f"⛔ Scan #{scan_count} error: {e}", exc_info=True)
                await notifier.send(
                    f"⚠️ <b>[SnipBot]</b>: Scan error.\n<code>{str(e)[:200]}</code>"
                )

            log.info(f"◎ Sleeping {INTERVAL}s...")
            await asyncio.sleep(INTERVAL)

    except KeyboardInterrupt:
        await notifier.abort()
    finally:
        await scanner.close()


if __name__ == "__main__":
    # Start Flask in background thread
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    log.info(f"🔎 [Sniper Engine]: Status API started on port {PORT}")

    # Run async scan loop in main thread
    asyncio.run(run())
