"""
SnipBot — Hybrid Agent Runner
------------------------------
Orchestrates: Scanner → StrategyManager → Notifier
"""

import logging
import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────
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

# ── Config from env ───────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN",   "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
KUCOIN_API_KEY   = os.environ.get("KUCOIN_API_KEY",   "")
KUCOIN_SECRET    = os.environ.get("KUCOIN_SECRET",    "")
KUCOIN_PASS      = os.environ.get("KUCOIN_PASS",      "")
SCAN_INTERVAL    = int(os.environ.get("SCAN_INTERVAL", "900"))   # 15 min default
MIN_CONFIDENCE   = float(os.environ.get("MIN_CONFIDENCE", "65"))

PAIRS_RAW        = os.environ.get("PAIRS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT")
ACTIVE_PAIRS     = [p.strip() for p in PAIRS_RAW.split(",") if p.strip()]

ACTIVE_STRATEGIES = ["TA", "DCA"]
TIMEFRAME         = os.environ.get("TIMEFRAME", "1h")

CONFIG = {
    "KUCOIN_API_KEY":   KUCOIN_API_KEY,
    "KUCOIN_SECRET":    KUCOIN_SECRET,
    "KUCOIN_PASS":      KUCOIN_PASS,
    "pairs":            ACTIVE_PAIRS,
    "timeframe":        TIMEFRAME,
    "min_confidence":   MIN_CONFIDENCE,
}


def main():
    # ── Validate ──────────────────────────────────────────────────────────────
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.error("⛔ [SnipBot ABORT]: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing.")
        sys.exit(1)

    log.info("🎯 SnipBot Hybrid System starting...")
    log.info(f"Symbols:    {ACTIVE_PAIRS}")
    log.info(f"Strategies: {ACTIVE_STRATEGIES}")
    log.info(f"Interval:   {SCAN_INTERVAL // 60} min")
    log.info(f"Min conf:   {MIN_CONFIDENCE:.0f}%")

    # ── Init components ───────────────────────────────────────────────────────
    notifier = Notifier(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
    scanner  = Scanner(CONFIG)
    manager  = StrategyManager(config=CONFIG)          # ← FIXED: no strategy_names kwarg

    notifier.send_sync(
        f"🎯 <b>[SnipBot]</b>: Hybrid Agent System online.\n"
        f"Pairs: {' · '.join(ACTIVE_PAIRS)}\n"
        f"Timeframe: {TIMEFRAME} · Scan every {SCAN_INTERVAL // 60} min\n"
        f"Min confidence: {MIN_CONFIDENCE:.0f}%"
    )

    scan_count = 0

    # ── Main loop ─────────────────────────────────────────────────────────────
    while True:
        scan_count += 1
        log.info(f"🔎 [Sniper Engine]: Scan #{scan_count} starting...")

        try:
            all_signals = []

            for pair in ACTIVE_PAIRS:
                df = scanner.fetch_ohlcv_sync(pair)
                if df is None:
                    log.warning(f"◎ [Scanner]: No data for {pair} — skipping")
                    continue

                signal = manager.vote(pair, df)

                if signal and signal.is_actionable(MIN_CONFIDENCE):
                    all_signals.append(signal)
                    log.info(
                        f"🎯 [SnipBot]: {pair} → {signal.action} "
                        f"@ {signal.confidence:.1f}% — {signal.reason[:80]}"
                    )
                    if signal.action == "BUY":
                        notifier.send_sync(
                            f"🎯 <b>[SnipBot]</b>: Target acquired on <b>{pair}</b>.\n"
                            f"Entry: ${signal.entry_price:,.2f}\n"
                            f"SL: ${signal.stop_loss:,.2f} · TP: ${signal.take_profit:,.2f}\n"
                            f"Confidence: {signal.confidence:.1f}% · Agent: {signal.strategy}\n"
                            f"<i>{signal.reason[:120]}</i>"
                        )
                    elif signal.action == "SELL":
                        notifier.send_sync(
                            f"⚡ <b>[SnipBot Execution]</b>: {pair} SELL fired "
                            f"@ ${signal.entry_price:,.2f}\n"
                            f"Agent: {signal.strategy} · Confidence: {signal.confidence:.1f}%"
                        )
                else:
                    log.info(f"◎ [SnipBot Tracking]: {pair} — no trigger.")

            # Periodic summary every 6 scans
            if scan_count % 6 == 0:
                notifier.send_sync(
                    f"🔎 <b>[Sniper Engine]</b>: Scan #{scan_count} complete.\n"
                    f"Pairs: {len(ACTIVE_PAIRS)} scanned · "
                    f"Signals: {len(all_signals)} fired\n"
                    f"◎ All pairs under surveillance."
                )

        except Exception as e:
            log.error(f"⛔ [SnipBot]: Scan #{scan_count} error: {e}", exc_info=True)
            notifier.send_sync(
                f"⚠️ <b>[SnipBot]</b>: Scan #{scan_count} error.\n"
                f"<code>{str(e)[:200]}</code>"
            )

        log.info(f"◎ [SnipBot Tracking]: Sleeping {SCAN_INTERVAL}s until next scan...")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
