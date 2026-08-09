"""
SnipBot — Hybrid Agent Runner
------------------------------
Scan loop + sends results to Proxy /api/agents/update
so the Dashboard Agent Radar shows live data.
"""

import asyncio
import logging
import os
import sys
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

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
PROXY_URL= os.environ.get("PROXY_URL", "https://snipbot-proxy.up.railway.app")

CONFIG = {
    "KUCOIN_API_KEY": os.environ.get("KUCOIN_API_KEY", ""),
    "KUCOIN_SECRET":  os.environ.get("KUCOIN_SECRET",  ""),
    "KUCOIN_PASS":    os.environ.get("KUCOIN_PASS",    ""),
    "pairs":    PAIRS,
    "timeframe": TF,
}


def push_to_proxy(agents_data: dict):
    """
    Send scan results to Proxy /api/agents/update
    so Dashboard Agent Radar shows live data.
    """
    try:
        r = requests.post(
            f"{PROXY_URL}/api/agents/update",
            json=agents_data,
            timeout=5,
        )
        if r.status_code == 200:
            log.info("🔎 [Proxy]: Agent Radar updated successfully")
        else:
            log.warning(f"[Proxy]: agents/update returned {r.status_code}")
    except Exception as e:
        log.warning(f"[Proxy]: Could not push agent update — {e}")


async def run():
    if not TOKEN or not CHAT_ID:
        log.error("⛔ [SnipBot ABORT]: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing.")
        sys.exit(1)

    log.info("🎯 SnipBot Hybrid System starting...")
    log.info(f"Symbols:    {PAIRS}")
    log.info(f"Strategies: ['TA', 'DCA']")
    log.info(f"Interval:   {INTERVAL // 60} min")
    log.info(f"Min conf:   {MIN_CONF:.0f}%")
    log.info(f"Proxy:      {PROXY_URL}")

    notifier = Notifier(TOKEN, CHAT_ID)
    scanner  = Scanner(CONFIG)
    manager  = StrategyManager(config=CONFIG)

    await notifier.send(
        f"🎯 <b>[SnipBot]</b>: Hybrid Agent System online.\n"
        f"Pairs: {' · '.join(PAIRS)} · TF: {TF}\n"
        f"Scan every {INTERVAL//60} min · Min conf: {MIN_CONF:.0f}%"
    )

    scan_count = 0

    try:
        while True:
            scan_count += 1
            log.info(f"🔎 [Sniper Engine]: Scan #{scan_count} starting...")

            agent_results = []
            active_signals = []

            try:
                for pair in PAIRS:
                    df = await scanner.fetch_ohlcv(pair)
                    if df is None:
                        log.info(f"◎ [Scanner]: No data for {pair}")
                        agent_results.append({
                            "name":       "TA Analyst",
                            "action":     "NO DATA",
                            "confidence": 0,
                            "reason":     f"Could not fetch OHLCV for {pair}",
                            "pair":       pair,
                        })
                        continue

                    # Run TA strategy vote
                    signal = manager.vote(pair, df)

                    if signal:
                        agent_results.append({
                            "name":       signal.strategy,
                            "action":     signal.action,
                            "confidence": round(signal.confidence, 1),
                            "reason":     signal.reason[:100],
                            "pair":       pair,
                        })
                        if signal.is_actionable(MIN_CONF):
                            active_signals.append(signal)
                            log.info(f"🎯 {pair} → {signal.action} {signal.confidence:.1f}%")
                    else:
                        agent_results.append({
                            "name":       "Consensus",
                            "action":     "HOLD",
                            "confidence": 50,
                            "reason":     f"{pair}: No consensus between strategies",
                            "pair":       pair,
                        })
                        log.info(f"◎ [SnipBot Tracking]: {pair} — awaiting breakout.")

                # Push results to Proxy → Dashboard
                push_to_proxy({
                    "timestamp":  datetime.now(timezone.utc).isoformat(),
                    "scan_count": scan_count,
                    "strategies": agent_results,
                    "signals":    [
                        {"pair": s.pair, "action": s.action,
                         "confidence": round(s.confidence, 1)}
                        for s in active_signals
                    ],
                    "symbols": PAIRS,
                })

                # Send Telegram alerts
                for sig in active_signals:
                    if sig.action == "BUY":
                        await notifier.target_acquired(sig)
                    elif sig.action == "SELL":
                        await notifier.sell_signal(sig)

                if not active_signals:
                    log.info(f"◎ No triggers on scan #{scan_count}.")

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
    asyncio.run(run())
