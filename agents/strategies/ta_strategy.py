import pandas as pd
import ta.momentum, ta.trend, ta.volatility

from strategies.base_strategy import BaseStrategy, Signal


class TAStrategy(BaseStrategy):
    name   = "TA"
    weight = 1.0

    RSI_OVERSOLD   = 38
    RSI_OVERBOUGHT = 62
    MIN_ROWS       = 50

    def analyze(self, pair: str, df: pd.DataFrame) -> Signal:
        if not self._validate_df(df, self.MIN_ROWS):
            return self.hold(pair, "Insufficient data")

        closes = df["close"]
        price  = closes.iloc[-1]

        rsi      = ta.momentum.RSIIndicator(closes, window=14).rsi()
        ema_fast = ta.trend.EMAIndicator(closes, window=9).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(closes, window=21).ema_indicator()
        macd_obj = ta.trend.MACD(closes, window_fast=12, window_slow=26, window_sign=9)
        macd     = macd_obj.macd()
        macd_sig = macd_obj.macd_signal()
        bb       = ta.volatility.BollingerBands(closes, window=20, window_dev=2)

        rsi_v    = rsi.iloc[-1]
        ema_bull = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        ema_bear = not ema_bull
        macd_bull = macd.iloc[-1] > macd_sig.iloc[-1]
        near_lower = price <= bb.bollinger_lband().iloc[-1] * 1.01
        near_upper = price >= bb.bollinger_hband().iloc[-1] * 0.99

        bull = sum([rsi_v < self.RSI_OVERSOLD, ema_bull, macd_bull, near_lower])
        bear = sum([rsi_v > self.RSI_OVERBOUGHT, ema_bear, not macd_bull, near_upper])

        if bull >= 2 and bull > bear:
            conf = min(40 + bull * 15, 95)
            return Signal(pair=pair, action="BUY", confidence=conf, strategy=self.name,
                          reason=f"RSI={rsi_v:.1f} bull={bull}/4",
                          entry_price=price, stop_loss=price*0.97, take_profit=price*1.06)

        if bear >= 2 and bear > bull:
            conf = min(40 + bear * 15, 95)
            return Signal(pair=pair, action="SELL", confidence=conf, strategy=self.name,
                          reason=f"RSI={rsi_v:.1f} bear={bear}/4",
                          entry_price=price, stop_loss=price*1.03, take_profit=price*0.94)

        return self.hold(pair, f"RSI={rsi_v:.1f} bull={bull} bear={bear}")
