"""
SnipBot — Strategy Manager
---------------------------
Weighted vote across all registered strategies.
Final decision requires MIN_CONFIDENCE and MIN_AGREEMENT.

Vote system:
  Each strategy returns BUY / SELL / HOLD with a confidence score.
  Weighted score = confidence × strategy.weight
  If total weighted score for BUY >= threshold → FIRE BUY
  Same for SELL.
"""

import logging
from typing import Optional
import pandas as pd

from .strategies import REGISTRY
from .strategies.base_strategy import Signal

log = logging.getLogger("SnipBot.StrategyManager")


class StrategyManager:

    MIN_CONFIDENCE  = 62.0   # weighted avg confidence to act
    MIN_AGREEMENT   = 0.55   # 55% of total weight must agree

    def __init__(self, config: dict = None):
        self.config = config or {}
        # Instantiate all registered strategies
        self.strategies = [cls(config) for cls in REGISTRY.values()]
        log.info(
            f"🎯 [SnipBot]: StrategyManager armed — "
            f"{len(self.strategies)} strategies loaded: "
            f"{[s.name for s in self.strategies]}"
        )

    def vote(self, pair: str, df: pd.DataFrame) -> Optional[Signal]:
        """
        Run all strategies on the same OHLCV data, collect votes,
        return final Signal or None if no consensus.
        """
        signals = []
        for strategy in self.strategies:
            try:
                sig = strategy.analyze(pair, df)
                signals.append(sig)
                log.debug(
                    f"◎ [Agent Radar]: {strategy.name} → "
                    f"{sig.action} {sig.confidence:.1f}% — {sig.reason[:60]}"
                )
            except Exception as e:
                log.warning(f"⚠ [{strategy.name}] error on {pair}: {e}")

        if not signals:
            return None

        # ── Weighted tally ────────────────────────────────────────────────────
        total_weight = sum(s.weight for s in self.strategies)
        buy_weight  = 0.0
        sell_weight = 0.0
        buy_conf_sum  = 0.0
        sell_conf_sum = 0.0

        for sig, strat in zip(signals, self.strategies):
            w = strat.weight
            if sig.action == "BUY":
                buy_weight    += w
                buy_conf_sum  += sig.confidence * w
            elif sig.action == "SELL":
                sell_weight   += w
                sell_conf_sum += sig.confidence * w

        buy_agree  = buy_weight  / total_weight   # 0.0–1.0
        sell_agree = sell_weight / total_weight

        buy_conf_avg  = (buy_conf_sum  / buy_weight)  if buy_weight  > 0 else 0.0
        sell_conf_avg = (sell_conf_sum / sell_weight) if sell_weight > 0 else 0.0

        log.info(
            f"🔎 [Sniper Engine]: {pair} vote → "
            f"BUY {buy_agree*100:.0f}% agree @ {buy_conf_avg:.1f}% conf | "
            f"SELL {sell_agree*100:.0f}% agree @ {sell_conf_avg:.1f}% conf"
        )

        # ── Decision ─────────────────────────────────────────────────────────
        if (buy_agree >= self.MIN_AGREEMENT and
                buy_conf_avg >= self.MIN_CONFIDENCE and
                buy_conf_avg > sell_conf_avg):

            # Synthesize final BUY signal
            best = max(
                (s for s in signals if s.action == "BUY"),
                key=lambda s: s.confidence,
            )
            reasons = " | ".join(
                f"{s.strategy}:{s.confidence:.0f}%"
                for s in signals if s.action == "BUY"
            )
            return Signal(
                pair=pair,
                action="BUY",
                confidence=buy_conf_avg,
                strategy="StrategyManager",
                reason=f"CONSENSUS BUY [{buy_agree*100:.0f}% agree] — {reasons}",
                entry_price=best.entry_price,
                stop_loss=best.stop_loss,
                take_profit=best.take_profit,
            )

        if (sell_agree >= self.MIN_AGREEMENT and
                sell_conf_avg >= self.MIN_CONFIDENCE and
                sell_conf_avg > buy_conf_avg):

            best = max(
                (s for s in signals if s.action == "SELL"),
                key=lambda s: s.confidence,
            )
            reasons = " | ".join(
                f"{s.strategy}:{s.confidence:.0f}%"
                for s in signals if s.action == "SELL"
            )
            return Signal(
                pair=pair,
                action="SELL",
                confidence=sell_conf_avg,
                strategy="StrategyManager",
                reason=f"CONSENSUS SELL [{sell_agree*100:.0f}% agree] — {reasons}",
                entry_price=best.entry_price,
                stop_loss=best.stop_loss,
                take_profit=best.take_profit,
            )

        # No consensus
        hold_reason = (
            f"No consensus on {pair} — "
            f"BUY {buy_agree*100:.0f}%/{buy_conf_avg:.0f}% · "
            f"SELL {sell_agree*100:.0f}%/{sell_conf_avg:.0f}% · "
            f"need >{self.MIN_AGREEMENT*100:.0f}% agree & >{self.MIN_CONFIDENCE:.0f}% conf"
        )
        log.info(f"◎ [SnipBot Tracking]: {pair} — {hold_reason}")
        return None

    def status(self) -> dict:
        """Return agent status for dashboard Agent Radar panel."""
        return {
            "strategies": [
                {"name": s.name, "weight": s.weight}
                for s in self.strategies
            ],
            "min_confidence": self.MIN_CONFIDENCE,
            "min_agreement":  self.MIN_AGREEMENT,
        }
