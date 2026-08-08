"""
SnipBot — Multi-Pair Scanner
-----------------------------
Fetches OHLCV candles from KuCoin via ccxt (paper trading safe).
Passes data to StrategyManager for each pair.
Returns list of actionable Signals.
"""

import logging
import asyncio
from typing import List, Optional
import pandas as pd
import ccxt.async_support as ccxt

from strategy_manager import StrategyManager
from .strategies.base_strategy import Signal

log = logging.getLogger("SnipBot.Scanner")


PAIRS = [
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
]

TIMEFRAME   = "1h"
CANDLE_LIMIT = 200   # enough for all indicators


class Scanner:

    def __init__(self, config: dict):
        self.config  = config
        self.manager = StrategyManager(config)
        self.pairs   = config.get("pairs", PAIRS)
        self.timeframe = config.get("timeframe", TIMEFRAME)

        self.exchange = ccxt.kucoin({
            "apiKey":    config.get("KUCOIN_API_KEY", ""),
            "secret":    config.get("KUCOIN_SECRET",  ""),
            "password":  config.get("KUCOIN_PASS",    ""),
            "enableRateLimit": True,
            # Paper trading: use sandbox if available
            "options": {"defaultType": "spot"},
        })

    async def fetch_ohlcv(self, pair: str) -> Optional[pd.DataFrame]:
        """Fetch OHLCV candles for one pair."""
        try:
            raw = await self.exchange.fetch_ohlcv(
                pair, self.timeframe, limit=CANDLE_LIMIT
            )
            if not raw or len(raw) < 50:
                log.warning(f"[Scanner] Too few candles for {pair}: {len(raw) if raw else 0}")
                return None

            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            df = df.astype(float)
            return df

        except ccxt.NetworkError as e:
            log.error(f"[Scanner] Network error on {pair}: {e}")
            return None
        except ccxt.ExchangeError as e:
            log.error(f"[Scanner] Exchange error on {pair}: {e}")
            return None
        except Exception as e:
            log.error(f"[Scanner] Unexpected error on {pair}: {e}")
            return None

    async def scan_pair(self, pair: str) -> Optional[Signal]:
        """Fetch candles + run strategy vote for one pair."""
        df = await self.fetch_ohlcv(pair)
        if df is None:
            return None

        signal = self.manager.vote(pair, df)
        if signal and signal.is_actionable():
            log.info(
                f"🎯 [SnipBot]: Target acquired on {pair}. "
                f"Price at ${df['close'].iloc[-1]:.2f}. "
                f"Action: {signal.action} @ {signal.confidence:.1f}% confidence. "
                f"Trigger armed."
            )
        else:
            log.info(f"◎ [SnipBot Tracking]: {pair} under surveillance — awaiting breakout confirmation.")

        return signal

    async def scan_all(self) -> List[Signal]:
        """Scan all pairs concurrently. Returns actionable signals only."""
        tasks = [self.scan_pair(pair) for pair in self.pairs]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        actionable = [
            sig for sig in results
            if sig is not None and sig.is_actionable()
        ]

        log.info(
            f"🔎 [Sniper Engine]: Scan complete — "
            f"{len(self.pairs)} pairs scanned · "
            f"{len(actionable)} actionable signals found."
        )
        return actionable

    async def close(self):
        await self.exchange.close()
