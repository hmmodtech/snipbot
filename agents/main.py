"""
SnipBot — Hybrid Agent Runner
------------------------------
Orchestrates: Scanner → StrategyManager → Notifier
Pure async loop — compatible with scanner.py and notifier.py.
"""

import asyncio
import logging
import os
import sys
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
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SCAN_INTERVAL    = int(os.environ.get("SCAN_INTERVAL", "900"))
MIN_CONFIDENCE   = float(os.environ.get("MIN_CONFIDENCE", "65"))
PAIRS_RAW        = os.environ.get("PAIRS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT")
ACTIVE_PAIRS     = [p.strip() for p in PAIRS_RAW.split(",") if p.strip()]
TIMEFRAME        = os.environ.get("TIMEFRAME", "1h")

CONFIG = {
    "KUCOIN_API_KEY": os.environ.get("KUCOIN_API_KEY", ""),
    "KUCOIN_SECRET":  os.environ.get("KUCOIN_SECRET",  ""),
    "KUCOIN_PASS":    os.environ.get("KUCOIN_PASS",    ""),
    "pairs":          ACTIVE_PAIRS,
    "timeframe":      TIMEFRAME,
}


async def run():
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("⛔ [SnipBot ABORT]: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing.")
        sys.exit(1)

    log.info("🎯 SnipBot Hybrid System starting...")
    log.info(f"Symbols:    {ACTIVE_PAIRS}")
    log.info(f"Strategies: ['TA', 'DCA']")
    log.info(f"Interval:   {SCAN_INTERVAL // 60} min")
    log.info(f"Min conf:   {MIN_CONFIDENCE:.0f}%")

    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    scanner  = Scanner(CONFIG)
    manager  = StrategyManager(config=CONFIG)

    await notifier.send(
        f"🎯 <b>[SnipBot]</b>: Hybrid Agent System online.\n"
        f"Pairs: {' · '.join(ACTIVE_PAIRS)}\n"
        f"Timeframe: {TIMEFRAME} · Scan every {SCAN_INTERVAL // 60} min"
    )

    scan_count = 0

    try:
        while True:
            scan_count += 1
            log.info(f"🔎 [Sniper Engine]: Scan #{scan_count} starting...")
            all_signals = []

            try:
                signals = await scanner.scan_all()

                for sig in signals:
                    if not sig.is_actionable(MIN_CONFIDENCE):
                        continue
                    all_signals.append(sig)

                    if sig.action == "BUY":
                        await notifier.target_acquired(sig)
                    elif sig.action == "SELL":
                        await notifier.sell_signal(sig)

                if not all_signals:
                    log.info(f"◎ [SnipBot Tracking]: No triggers on scan #{scan_count}.")

                if scan_count % 6 == 0:
                    await notifier.scan_summary(
                        scanned=len(ACTIVE_PAIRS),
                        signals=len(all_signals),
                        pairs=[s.pair for s in all_signals],
                    )

            except Exception as e:
                log.error(f"⛔ Scan #{scan_count} error: {e}", exc_info=True)
                await notifier.send(
                    f"⚠️ <b>[SnipBot]</b>: Scan #{scan_count} error.\n"
                    f"<code>{str(e)[:200]}</code>"
                )

            log.info(f"◎ Sleeping {SCAN_INTERVAL}s...")
            await asyncio.sleep(SCAN_INTERVAL)

    except KeyboardInterrupt:
        log.info("⛔ [SnipBot ABORT]: Manual shutdown.")
        await notifier.abort()
    finally:
        await scanner.close()
        log.info("🎯 [SnipBot]: Agent system offline.")


if __name__ == "__main__":
    asyncio.run(run())
