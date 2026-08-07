"""
TA Strategy — التحليل الفني
مستلهم من freqtrade's SampleStrategy
يستخدم: RSI + EMA + Bollinger Bands + MACD
"""

import pandas as pd
import pandas_ta as ta
import logging
from .base_strategy import BaseStrategy

log = logging.getLogger("TA-Strategy")


class TAStrategy(BaseStrategy):
    """
    استراتيجية التحليل الفني الكاملة
    
    منطق الشراء (مستلهم من freqtrade):
    ✅ RSI < 35 (مبالغ في البيع)
    ✅ السعر تحت Bollinger Band السفلي
    ✅ EMA9 > EMA21 (اتجاه صاعد)
    ✅ MACD يتقاطع للأعلى
    
    منطق البيع:
    ❌ RSI > 65 (مبالغ في الشراء)
    ❌ السعر فوق Bollinger Band العلوي
    ❌ EMA9 < EMA21 (اتجاه هابط)
    """

    NAME = "TA Strategy"
    VERSION = "1.0"
    TIMEFRAME = "1h"
    CANDLES_NEEDED = 50

    # معاملات RSI
    RSI_BUY_THRESHOLD  = 35
    RSI_SELL_THRESHOLD = 65
    RSI_PERIOD         = 14

    # معاملات EMA
    EMA_FAST = 9
    EMA_SLOW = 21

    # معاملات Bollinger Bands
    BB_PERIOD = 20
    BB_STD    = 2.0

    def analyze(self, df: pd.DataFrame, symbol: str) -> dict:
        """التحليل الفني الكامل"""

        if not self.validate_df(df):
            return self._empty_result(symbol, "Insufficient data")

        try:
            # ── حساب المؤشرات ──
            # RSI
            df["rsi"] = ta.rsi(df["close"], length=self.RSI_PERIOD)

            # EMA
            df["ema_fast"] = ta.ema(df["close"], length=self.EMA_FAST)
            df["ema_slow"] = ta.ema(df["close"], length=self.EMA_SLOW)

            # Bollinger Bands
            bb = ta.bbands(df["close"], length=self.BB_PERIOD, std=self.BB_STD)
            df["bb_upper"] = bb[f"BBU_{self.BB_PERIOD}_{self.BB_STD}"]
            df["bb_lower"] = bb[f"BBL_{self.BB_PERIOD}_{self.BB_STD}"]
            df["bb_mid"]   = bb[f"BBM_{self.BB_PERIOD}_{self.BB_STD}"]

            # MACD
            macd = ta.macd(df["close"])
            df["macd"]        = macd["MACD_12_26_9"]
            df["macd_signal"] = macd["MACDs_12_26_9"]
            df["macd_hist"]   = macd["MACDh_12_26_9"]

            # ── آخر قيم ──
            last       = df.iloc[-1]
            prev       = df.iloc[-2]

            rsi        = round(last["rsi"], 2)
            ema_fast   = round(last["ema_fast"], 4)
            ema_slow   = round(last["ema_slow"], 4)
            price      = round(last["close"], 4)
            bb_upper   = round(last["bb_upper"], 4)
            bb_lower   = round(last["bb_lower"], 4)
            macd_val   = round(last["macd"], 4)
            macd_sig   = round(last["macd_signal"], 4)
            macd_cross = (
                last["macd"] > last["macd_signal"] and
                prev["macd"] <= prev["macd_signal"]
            )

            # ── منطق القرار (مستلهم من freqtrade) ──
            buy_signals  = []
            sell_signals = []
            confidence   = 50

            # RSI
            if rsi < self.RSI_BUY_THRESHOLD:
                buy_signals.append(f"RSI oversold ({rsi})")
                confidence += 20
            elif rsi > self.RSI_SELL_THRESHOLD:
                sell_signals.append(f"RSI overbought ({rsi})")
                confidence -= 20

            # EMA Trend
            if ema_fast > ema_slow:
                buy_signals.append(f"EMA bullish ({ema_fast:.0f}>{ema_slow:.0f})")
                confidence += 15
            else:
                sell_signals.append(f"EMA bearish ({ema_fast:.0f}<{ema_slow:.0f})")
                confidence -= 15

            # Bollinger Bands
            if price < bb_lower:
                buy_signals.append("Price below BB lower")
                confidence += 15
            elif price > bb_upper:
                sell_signals.append("Price above BB upper")
                confidence -= 15

            # MACD Crossover
            if macd_cross:
                buy_signals.append("MACD bullish crossover")
                confidence += 10
            elif macd_val < macd_sig:
                sell_signals.append("MACD bearish")
                confidence -= 10

            # ── القرار النهائي ──
            confidence = max(0, min(100, confidence))

            if confidence >= 65 and len(buy_signals) >= 2:
                signal = "BUY"
                reason = " | ".join(buy_signals)
            elif confidence <= 35 and len(sell_signals) >= 2:
                signal = "SELL"
                reason = " | ".join(sell_signals)
            else:
                signal = "HOLD"
                reason = "No clear consensus"

            result = {
                "strategy": self.NAME,
                "symbol":   symbol,
                "signal":   signal,
                "confidence": confidence,
                "reason":   reason,
                "indicators": {
                    "rsi":       rsi,
                    "ema_fast":  ema_fast,
                    "ema_slow":  ema_slow,
                    "bb_upper":  bb_upper,
                    "bb_lower":  bb_lower,
                    "price":     price,
                    "macd":      macd_val,
                    "macd_sig":  macd_sig,
                    "macd_cross": macd_cross
                }
            }

            log.info(
                f"[TA Strategy]: {symbol} → {signal} "
                f"({confidence}%) | RSI:{rsi} | "
                f"EMA:{ema_fast:.0f}/{ema_slow:.0f}"
            )
            return result

        except Exception as e:
            log.error(f"[TA Strategy]: Analysis failed — {e}")
            return self._empty_result(symbol, str(e))

    def _empty_result(self, symbol, reason):
        return {
            "strategy":   self.NAME,
            "symbol":     symbol,
            "signal":     "HOLD",
            "confidence": 0,
            "reason":     reason,
            "indicators": {}
        }
