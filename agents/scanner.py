"""
Multi-Pair Scanner — ماسح متعدد الأزواج
يجلب البيانات لكل الأزواج من KuCoin
"""

import ccxt
import pandas as pd
import logging
import time

log = logging.getLogger("Scanner")


class Scanner:
    """
    يجلب بيانات OHLCV لأي عدد من الأزواج
    من KuCoin مباشرة — بدون API keys
    """

    def __init__(self):
        self.exchange = ccxt.kucoin({
            "enableRateLimit": True,  # مهم — يمنع الحظر
        })
        log.info("[Scanner]: KuCoin connection ready")

    def fetch(self, symbol: str, timeframe: str = "1h", limit: int = 100):
        """
        جلب بيانات زوج واحد
        
        المدخلات:
            symbol: مثل BTC/USDT
            timeframe: 1m, 5m, 15m, 1h, 4h, 1d
            limit: عدد الشمعات
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol, timeframe, limit=limit
            )
            df = pd.DataFrame(
                ohlcv,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df.set_index("timestamp")
            log.info(f"[Scanner]: {symbol} — {len(df)} candles fetched")
            return df
        except Exception as e:
            log.error(f"[Scanner]: Failed to fetch {symbol} — {e}")
            return None

    def fetch_all(self, symbols: list, timeframe: str = "1h", limit: int = 100):
        """
        جلب بيانات كل الأزواج
        مع تأخير بسيط بين كل طلب
        """
        results = {}
        for symbol in symbols:
            df = self.fetch(symbol, timeframe, limit)
            if df is not None:
                results[symbol] = df
            time.sleep(1)  # تأخير 1 ثانية — يمنع الحظر من KuCoin
        log.info(f"[Scanner]: Fetched {len(results)}/{len(symbols)} pairs")
        return results
