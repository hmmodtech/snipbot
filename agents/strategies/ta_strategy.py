"""
SnipBot — Technical Analysis Strategy
--------------------------------------
Indicators: RSI · EMA9/21 · MACD · Bollinger Bands
Library: ta==0.11.0 (replaces pandas-ta — Python 3.11 compatible)

Signal logic:
  BUY  if RSI oversold + EMA bullish cross + MACD bullish + price near BB lower
  SELL if RSI overbought + EMA bearish cross + MACD bearish + price near BB upper
  HOLD otherwise
"""

import pandas as pd
import ta.momentum
import ta.trend
import ta.volatility

from .base_strategy import BaseStrategy, Signal


class TAStrategy(BaseStrategy):

    name = "TA Analyst"
    weight = 1.0   # 20% weight in 5-strategy vote (manager normalizes)

    # ── Tunable thresholds ──────────────────────────────────────────────────
    RSI_OVERSOLD   = 38
    RSI_OVERBOUGHT = 62
    EMA_FAST       = 9
    EMA_SLOW       = 21
    MACD_FAST      = 12
    MACD_SLOW      = 26
    MACD_SIGNAL    = 9
    BB_WINDOW      = 20
    BB_STD         = 2.0
    MIN_ROWS       = 50    # need 50 candles for MACD(26) to be stable

    def analyze(self, pair: str, df: pd.DataFrame) -> Signal:
        if not self._validate_df(df, self.MIN_ROWS):
            return self.hold(pair, "Insufficient data for TA analysis")

        closes = df["close"]
        highs  = df["high"]
        lows   = df["low"]

        # ── RSI ──────────────────────────────────────────────────────────────
        rsi_series = ta.momentum.RSIIndicator(closes, window=14).rsi()
        rsi = rsi_series.iloc[-1]

        # ── EMA cross ────────────────────────────────────────────────────────
        ema_fast = ta.trend.EMAIndicator(closes, window=self.EMA_FAST).ema_indicator()
        ema_slow = ta.trend.EMAIndicator(closes, window=self.EMA_SLOW).ema_indicator()
        ema_cross_bull = (
            ema_fast.iloc[-1] > ema_slow.iloc[-1] and
            ema_fast.iloc[-2] <= ema_slow.iloc[-2]
        )
        ema_cross_bear = (
            ema_fast.iloc[-1] < ema_slow.iloc[-1] and
            ema_fast.iloc[-2] >= ema_slow.iloc[-2]
        )
        ema_bull = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        ema_bear = ema_fast.iloc[-1] < ema_slow.iloc[-1]

        # ── MACD ─────────────────────────────────────────────────────────────
        macd_obj    = ta.trend.MACD(
            closes,
            window_fast=self.MACD_FAST,
            window_slow=self.MACD_SLOW,
            window_sign=self.MACD_SIGNAL,
        )
        macd_line   = macd_obj.macd()
        signal_line = macd_obj.macd_signal()
        macd_bull   = macd_line.iloc[-1] > signal_line.iloc[-1]
        macd_bear   = macd_line.iloc[-1] < signal_line.iloc[-1]
        macd_cross_bull = (
            macd_line.iloc[-1] > signal_line.iloc[-1] and
            macd_line.iloc[-2] <= signal_line.iloc[-2]
        )
        macd_cross_bear = (
            macd_line.iloc[-1] < signal_line.iloc[-1] and
            macd_line.iloc[-2] >= signal_line.iloc[-2]
        )

        # ── Bollinger Bands ───────────────────────────────────────────────────
        bb = ta.volatility.BollingerBands(
            closes, window=self.BB_WINDOW, window_dev=self.BB_STD
        )
        bb_upper = bb.bollinger_hband().iloc[-1]
        bb_lower = bb.bollinger_lband().iloc[-1]
        bb_mid   = bb.bollinger_mavg().iloc[-1]
        price    = closes.iloc[-1]

        near_lower = price <= bb_lower * 1.01   # within 1% of lower band
        near_upper = price >= bb_upper * 0.99   # within 1% of upper band

        # ── Scoring (0–4 bullish signals, 0–4 bearish) ───────────────────────
        bull_score = sum([
            rsi < self.RSI_OVERSOLD,
            ema_bull,
            macd_bull,
            near_lower,
        ])
        bear_score = sum([
            rsi > self.RSI_OVERBOUGHT,
            ema_bear,
            macd_bear,
            near_upper,
        ])

        # Cross signals add bonus weight
        cross_bonus = 20.0
        bull_bonus = (ema_cross_bull or macd_cross_bull) * cross_bonus
        bear_bonus = (ema_cross_bear or macd_cross_bear) * cross_bonus

        # Confidence: 40 base + 15 per signal + cross bonus
        bull_conf = 40.0 + bull_score * 15.0 + bull_bonus
        bear_conf = 40.0 + bear_score * 15.0 + bear_bonus

        # ── Decision ─────────────────────────────────────────────────────────
        if bull_conf > bear_conf and bull_score >= 2:
            sl = price * 0.97      # 3% stop loss
            tp = price * 1.06      # 6% take profit
            reason = (
                f"RSI={rsi:.1f} (oversold={rsi < self.RSI_OVERSOLD}) · "
                f"EMA9>{ema_fast.iloc[-1]:.2f} EMA21>{ema_slow.iloc[-1]:.2f} "
                f"({'CROSS ▲' if ema_cross_bull else 'BULL'}) · "
                f"MACD {'CROSS ▲' if macd_cross_bull else 'BULL' if macd_bull else 'BEAR'} · "
                f"BB: price near lower={near_lower}"
            )
            return Signal(
                pair=pair, action="BUY", confidence=min(bull_conf, 95.0),
                strategy=self.name, reason=reason,
                entry_price=price, stop_loss=sl, take_profit=tp,
            )

        if bear_conf > bull_conf and bear_score >= 2:
            sl = price * 1.03
            tp = price * 0.94
            reason = (
                f"RSI={rsi:.1f} (overbought={rsi > self.RSI_OVERBOUGHT}) · "
                f"EMA9<EMA21 "
                f"({'CROSS ▼' if ema_cross_bear else 'BEAR'}) · "
                f"MACD {'CROSS ▼' if macd_cross_bear else 'BEAR' if macd_bear else 'BULL'} · "
                f"BB: price near upper={near_upper}"
            )
            return Signal(
                pair=pair, action="SELL", confidence=min(bear_conf, 95.0),
                strategy=self.name, reason=reason,
                entry_price=price, stop_loss=sl, take_profit=tp,
            )

        return self.hold(
            pair,
            f"RSI={rsi:.1f} · bull_score={bull_score}/4 · bear_score={bear_score}/4 · no clear edge"
        )
