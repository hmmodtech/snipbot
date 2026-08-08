import pandas as pd
import ta.trend, ta.momentum

from strategies.base_strategy import BaseStrategy, Signal


class DCAStrategy(BaseStrategy):
    name   = "DCA"
    weight = 1.0

    DIP_THRESHOLD   = 0.04
    RECOVERY_TARGET = 0.03
    MA_WINDOW       = 50
    RSI_FLOOR       = 25
    MIN_ROWS        = 55

    def analyze(self, pair: str, df: pd.DataFrame) -> Signal:
        if not self._validate_df(df, self.MIN_ROWS):
            return self.hold(pair, "Insufficient data")

        closes = df["close"]
        price  = closes.iloc[-1]

        ma    = ta.trend.SMAIndicator(closes, window=self.MA_WINDOW).sma_indicator().iloc[-1]
        rsi   = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]
        ema200 = ta.trend.EMAIndicator(closes, window=min(200, len(closes)//2)).ema_indicator().iloc[-1]

        if pd.isna(ma):
            return self.hold(pair, "MA not ready")

        pct = (price - ma) / ma
        uptrend = price > ema200 if not pd.isna(ema200) else True

        if pct <= -self.DIP_THRESHOLD and rsi > self.RSI_FLOOR and uptrend:
            conf = min(55 + abs(pct) * 500, 88)
            return Signal(pair=pair, action="BUY", confidence=conf, strategy=self.name,
                          reason=f"DCA dip {pct*100:.1f}% below MA · RSI={rsi:.1f}",
                          entry_price=price, stop_loss=price*(1-self.DIP_THRESHOLD),
                          take_profit=ma*(1+self.RECOVERY_TARGET))

        if pct >= self.RECOVERY_TARGET:
            conf = min(55 + pct * 300, 82)
            return Signal(pair=pair, action="SELL", confidence=conf, strategy=self.name,
                          reason=f"DCA recovery {pct*100:.1f}% above MA",
                          entry_price=price)

        return self.hold(pair, f"DCA standby {pct*100:+.1f}% vs MA · RSI={rsi:.1f}")
