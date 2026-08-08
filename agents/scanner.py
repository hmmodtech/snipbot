"""
SnipBot — Multi-Pair Scanner
-----------------------------
Fetches OHLCV from KuCoin via ccxt async.
"""

import logging
import asyncio
from typing import List, Optional
import pandas as pd
import ccxt.async_support as ccxt

from strategy_manager import StrategyManager
from strategies.base_strategy import Signal

log = logging.getLogger("Scanner")

CANDLE_LIMIT = 200


class Scanner:

    def __init__(self, config: dict):
        self.config    = config
        self.pairs     = config.get("pairs", ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"])
        self.timeframe = config.get("timeframe", "1h")
        self.manager   = StrategyManager(config)

        self.exchange = ccxt.kucoin({
            "apiKey":   config.get("KUCOIN_API_KEY", ""),
            "secret":   config.get("KUCOIN_SECRET",  ""),
            "password": config.get("KUCOIN_PASS",    ""),
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        log.info("[Scanner]: KuCoin connection ready")

    async def fetch_ohlcv(self, pair: str) -> Optional[pd.DataFrame]:
        try:
            raw = await self.exchange.fetch_ohlcv(pair, self.timeframe, limit=CANDLE_LIMIT)
            if not raw or len(raw) < 50:
                return None
            df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df.set_index("timestamp", inplace=True)
            return df.astype(float)
        except Exception as e:
            log.error(f"[Scanner] {pair} fetch error: {e}")
            return None

    async def scan_pair(self, pair: str) -> Optional[Signal]:
        df = await self.fetch_ohlcv(pair)
        if df is None:
            return None
        signal = self.manager.vote(pair, df)
        if signal and signal.is_actionable():
            log.info(f"🎯 [SnipBot]: Target acquired on {pair} — {signal.action} {signal.confidence:.1f}%")
        else:
            log.info(f"◎ [SnipBot Tracking]: {pair} — awaiting breakout confirmation.")
        return signal

    async def scan_all(self) -> List[Signal]:
        tasks   = [self.scan_pair(p) for p in self.pairs]
        results = await asyncio.gather(*tasks)
        return [s for s in results if s is not None and s.is_actionable()]

    async def close(self):
        await self.exchange.close()
