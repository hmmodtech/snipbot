"""
SnipBot Hybrid System — Main Runner
يدمج OctoBot + freqtrade logic + SnipBot
"""

import os
import time
import logging
from datetime import datetime

from scanner          import Scanner
from strategy_manager import StrategyManager
from notifier         import Notifier

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-16s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("SnipBot")

# ── إعدادات من Environment Variables ──
SYMBOLS = os.getenv(
    "SYMBOLS",
    "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT"
).split(",")

ACTIVE_STRATEGIES = os.getenv(
    "STRATEGIES",
    "TA,DCA"
).split(",")

SCAN_INTERVAL  = int(os.getenv("SCAN_INTERVAL_MIN", "15")) * 60
MIN_CONFIDENCE = int(os.getenv("MIN_CONFIDENCE", "65"))
SUMMARY_EVERY  = int(os.getenv("SUMMARY_EVERY_N_SCANS", "4"))


def main():
    log.info("🎯 SnipBot Hybrid System starting...")
    log.info(f"Symbols:    {SYMBOLS}")
    log.info(f"Strategies: {ACTIVE_STRATEGIES}")
    log.info(f"Interval:   {SCAN_INTERVAL//60} min")
    log.info(f"Min conf:   {MIN_CONFIDENCE}%")

    # ── تهيئة المكونات ──
    scanner  = Scanner()
    manager  = StrategyManager(strategy_names=ACTIVE_STRATEGIES)
    notifier = Notifier()

    # رسالة البدء
    notifier.send_startup(SYMBOLS, ACTIVE_STRATEGIES)

    scan_count = 0

    while True:
        scan_count += 1
        log.info(f"{'='*50}")
        log.info(f"Scan #{scan_count} — {datetime.utcnow().strftime('%H:%M:%S UTC')}")

        # ── جلب بيانات كل الأزواج ──
        all_data = scanner.fetch_all(SYMBOLS, timeframe="1h", limit=100)

        all_results = []

        # ── تحليل كل زوج ──
        for symbol in SYMBOLS:
            df = all_data.get(symbol)
            if df is None:
                log.warning(f"No data for {symbol} — skipping")
                continue

            # تشغيل الاستراتيجيات
            result = manager.run(df, symbol)
            all_results.append(result)

            # إرسال إشعار لو الإشارة قوية
            notifier.notify_signal(result, min_confidence=MIN_CONFIDENCE)

            time.sleep(2)

        # ── ملخص دوري كل N scans ──
        if scan_count % SUMMARY_EVERY == 0:
            log.info("Sending periodic summary...")
            notifier.send_summary(all_results)

        log.info(f"Scan #{scan_count} complete — next in {SCAN_INTERVAL//60} min")
        time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
