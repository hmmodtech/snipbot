"""
SnipBot — Smart DCA+ Strategy
-------------------------------
Logic: Buy on dips relative to moving average.
       Scale in when price drops X% from recent high.
       Exit when price recovers Y% above average cost.

Inspired by OctoBot Smart DCA tentacle.
"""

import pandas as pd
import ta.trend
import ta.momentum

from base_strategy import BaseStrategy, Signal


class DCAStrategy(BaseStrategy):

    name = "Smart DCA+"
    weight = 1.0

    # ── Config ───────────────────────────────────────────────────────────────
    DIP_THRESHOLD   = 0.04   # buy when price is 4% below MA
    RECOVERY_TARGET = 0.03   # sell when price is 3% above MA
    MA_WINDOW       = 50     # 50-period moving average baseline
    RSI_FLOOR       = 25     # don't buy if RSI this low (potential crash)
    MIN_ROWS        = 55

    def analyze(self, pair: str, df: pd.DataFrame) -> Signal:
        if not self._validate_df(df, self.MIN_ROWS):
            return self.hold(pair, "Insufficient data for DCA analysis")

        closes = df["close"]
        price  = closes.iloc[-1]

        # ── Baseline MA ───────────────────────────────────────────────────────
        ma = ta.trend.SMAIndicator(closes, window=self.MA_WINDOW).sma_indicator()
        ma_now = ma.iloc[-1]

        if pd.isna(ma_now):
            return self.hold(pair, "MA not yet calculable")

        # ── RSI filter (avoid catching falling knives) ────────────────────────
        rsi = ta.momentum.RSIIndicator(closes, window=14).rsi().iloc[-1]

        # ── Price vs MA ───────────────────────────────────────────────────────
        pct_from_ma = (price - ma_now) / ma_now   # negative = below MA

        # ── Recent high (20-period) ────────────────────────────────────────────
        recent_high = closes.iloc[-20:].max()
        pct_from_high = (price - recent_high) / recent_high  # negative = dip

        # ── EMA trend filter: only buy in uptrend ────────────────────────────
        ema200 = ta.trend.EMAIndicator(closes, window=min(200, len(closes)//2)).ema_indicator()
        uptrend = price > ema200.iloc[-1] if not pd.isna(ema200.iloc[-1]) else True

        # ── DCA BUY condition ─────────────────────────────────────────────────
        # Price dipped below MA by threshold AND RSI not in crash AND uptrend
        dip_buy = (
            pct_from_ma <= -self.DIP_THRESHOLD and
            rsi > self.RSI_FLOOR and
            uptrend
        )

        # ── DCA SELL condition ────────────────────────────────────────────────
        # Price recovered above MA by recovery target
        recovery_sell = pct_from_ma >= self.RECOVERY_TARGET

        if dip_buy:
            # Confidence scales with dip depth (deeper dip = more confident DCA buy)
            dip_pct = abs(pct_from_ma) * 100
            confidence = min(55.0 + dip_pct * 5, 88.0)
            sl = price * (1 - self.DIP_THRESHOLD)
            tp = ma_now * (1 + self.RECOVERY_TARGET)

            return Signal(
                pair=pair,
                action="BUY",
                confidence=confidence,
                strategy=self.name,
                reason=(
                    f"DCA dip entry: price {pct_from_ma*100:.1f}% below MA{self.MA_WINDOW} "
                    f"(MA=${ma_now:.2f}) · RSI={rsi:.1f} · uptrend={uptrend} · "
                    f"high-dip={pct_from_high*100:.1f}%"
                ),
                entry_price=price,
                stop_loss=sl,
                take_profit=tp,
            )

        if recovery_sell:
            confidence = min(55.0 + pct_from_ma * 100 * 3, 82.0)
            return Signal(
                pair=pair,
                action="SELL",
                confidence=confidence,
                strategy=self.name,
                reason=(
                    f"DCA recovery exit: price {pct_from_ma*100:.1f}% above MA{self.MA_WINDOW} "
                    f"(MA=${ma_now:.2f}) · RSI={rsi:.1f}"
                ),
                entry_price=price,
            )

        return self.hold(
            pair,
            f"DCA standby: price {pct_from_ma*100:+.1f}% vs MA · "
            f"need <-{self.DIP_THRESHOLD*100:.0f}% to enter · RSI={rsi:.1f}"
        )
