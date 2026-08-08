"""
SnipBot — Agents Main Runner
-----------------------------
Orchestrates: Scanner → StrategyManager → Notifier
Loop: every SCAN_INTERVAL seconds, scan all pairs,
      fire Telegram alerts for actionable signals.

Environment variables required:
  TELEGRAM_TOKEN      — Bot token from @BotFather
  TELEGRAM_CHAT_ID    — Chat/channel ID for alerts
  KUCOIN_API_KEY      — KuCoin API key (paper trading)
  KUCOIN_SECRET       — KuCoin secret
  KUCOIN_PASS         — KuCoin passphrase
  SCAN_INTERVAL       — Seconds between scans (default: 300 = 5 min)
  PAIRS               — Comma-separated pairs (default: BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT)
  OCTOBOT_URL         — OctoBot engine URL for status sync (optional)
"""

import asyncio
import logging
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-28s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("SnipBot.Main")

from agents.scanner  import Scanner
from agents.notifier import Notifier


def load_config() -> dict:
    pairs_raw = os.environ.get("PAIRS", "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT")
    return {
        "TELEGRAM_TOKEN":   os.environ.get("TELEGRAM_TOKEN", ""),
        "TELEGRAM_CHAT_ID": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "KUCOIN_API_KEY":   os.environ.get("KUCOIN_API_KEY", ""),
        "KUCOIN_SECRET":    os.environ.get("KUCOIN_SECRET",  ""),
        "KUCOIN_PASS":      os.environ.get("KUCOIN_PASS",    ""),
        "SCAN_INTERVAL":    int(os.environ.get("SCAN_INTERVAL", "300")),
        "OCTOBOT_URL":      os.environ.get("OCTOBOT_URL", ""),
        "pairs":  [p.strip() for p in pairs_raw.split(",") if p.strip()],
        "timeframe": os.environ.get("TIMEFRAME", "1h"),
    }


async def run():
    config = load_config()

    # ── Validate required env vars ────────────────────────────────────────────
    if not config["TELEGRAM_TOKEN"] or not config["TELEGRAM_CHAT_ID"]:
        log.error("⛔ [SnipBot ABORT]: TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing. Halting.")
        sys.exit(1)

    notifier = Notifier(config["TELEGRAM_TOKEN"], config["TELEGRAM_CHAT_ID"])
    scanner  = Scanner(config)

    log.info("🎯 [SnipBot]: Agent system online.")
    log.info(f"🔎 [Sniper Engine]: Watching {config['pairs']} on {config['timeframe']} candles.")
    log.info(f"◎ [SnipBot Tracking]: Scan interval: {config['SCAN_INTERVAL']}s")

    # Startup notification
    await notifier.send(
        f"🎯 <b>[SnipBot]</b>: Hybrid Agent System online.\n"
        f"Pairs: {' · '.join(config['pairs'])}\n"
        f"Timeframe: {config['timeframe']} · "
        f"Scan every {config['SCAN_INTERVAL']}s"
    )

    scan_count = 0

    try:
        while True:
            scan_count += 1
            log.info(f"🔎 [Sniper Engine]: Scan #{scan_count} starting...")

            try:
                signals = await scanner.scan_all()

                if signals:
                    for sig in signals:
                        if sig.action == "BUY":
                            await notifier.target_acquired(sig)
                        elif sig.action == "SELL":
                            await notifier.sell_signal(sig)
                else:
                    # Every 6th scan (30 min default) send a snippet
                    if scan_count % 6 == 0:
                        pairs_str = " · ".join(config["pairs"])
                        await notifier.send(
                            f"◎ <b>[SnipBot Tracking]</b>: All pairs under surveillance.\n"
                            f"{pairs_str}\nNo triggers armed. Scan #{scan_count} complete."
                        )

                # Scan summary log every scan
                await notifier.scan_summary(
                    scanned=len(config["pairs"]),
                    signals=len(signals),
                    pairs=[s.pair for s in signals],
                ) if signals else None

            except Exception as e:
                log.error(f"⛔ [SnipBot]: Scan #{scan_count} error: {e}", exc_info=True)
                await notifier.send(
                    f"⚠️ <b>[SnipBot]</b>: Scan #{scan_count} encountered an error.\n"
                    f"<code>{str(e)[:200]}</code>\nRetrying next cycle."
                )

            await asyncio.sleep(config["SCAN_INTERVAL"])

    except KeyboardInterrupt:
        log.info("⛔ [SnipBot ABORT]: Manual shutdown.")
        await notifier.abort()
    finally:
        await scanner.close()
        log.info("🎯 [SnipBot]: Agent system offline.")


if __name__ == "__main__":
    asyncio.run(run())
