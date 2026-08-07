"""
DCA Strategy — Dollar Cost Averaging
تكمّل Smart DCA الحالي في OctoBot
تضيف فلتر ذكي: لا تشتري في هبوط قوي
"""

import pandas as pd
import pandas_ta as ta
import logging
from .base_strategy import BaseStrategy

log = logging.getLogger("DCA-Strategy")


class DCAStrategy(BaseStrategy):
    """
    استراتيجية DCA المحسّنة
    
    الفكرة: OctoBot يشتري بـ DCA
    نحن نضيف فلتر: لا تشتري إذا السوق في هبوط قوي
    
    شروط الشراء:
    ✅ RSI ليس في منطقة هبوط قوي (مش < 20)
    ✅ السعر ليس في downtrend واضح
    ✅ Volume طبيعي (مش انهيار)
    """

    NAME = "Smart DCA+"
    VERSION = "1.0"
    TIMEFRAME = "1h"
    CANDLES_NEEDED = 30

    def analyze(self, df: pd.DataFrame, symbol: str) -> dict:
        """تحليل DCA المحسّن"""

        if not self.validate_df(df):
            return self._empty_result(symbol, "Insufficient data")

        try:
            # RSI للفلتر
            df["rsi"] = ta.rsi(df["close"], length=14)

            # EMA للاتجاه
            df["ema_50"] = ta.ema(df["close"], length=50)

            # Volume المتوسط
            df["vol_ma"] = df["volume"].rolling(20).mean()

            last         = df.iloc[-1]
            rsi          = round(last["rsi"], 2)
            price        = round(last["close"], 4)
            ema_50       = round(last["ema_50"], 4)
            vol_ratio    = last["volume"] / last["vol_ma"] if last["vol_ma"] > 0 else 1

            warnings     = []
            confidence   = 70  # DCA افتراضياً آمن

            # فلتر الانهيار
            if rsi < 20:
                warnings.append(f"Extreme oversold RSI {rsi} — market crash?")
                confidence -= 40

            # فلتر الاتجاه
            if price < ema_50 * 0.95:
                warnings.append("Price 5% below EMA50 — strong downtrend")
                confidence -= 20

            # فلتر Volume الشاذ
            if vol_ratio > 3:
                warnings.append(f"Volume spike {vol_ratio:.1f}x — unusual activity")
                confidence -= 15

            confidence = max(0, min(100, confidence))

            if confidence >= 55:
                signal = "BUY"
                reason = "DCA conditions met — safe to accumulate"
            else:
                signal = "HOLD"
                reason = " | ".join(warnings)

            result = {
                "strategy":   self.NAME,
                "symbol":     symbol,
                "signal":     signal,
                "confidence": confidence,
                "reason":     reason,
                "indicators": {
                    "rsi":       rsi,
                    "ema_50":    ema_50,
                    "price":     price,
                    "vol_ratio": round(vol_ratio, 2)
                }
            }

            log.info(
                f"[DCA Strategy]: {symbol} → {signal} "
                f"({confidence}%) | RSI:{rsi}"
            )
            return result

        except Exception as e:
            log.error(f"[DCA Strategy]: Failed — {e}")
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
