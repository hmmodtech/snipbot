"""
SnipBot — Strategy Manager
---------------------------
Weighted vote across all registered strategies.
"""

import logging
from typing import Optional
import pandas as pd

from strategies.ta_strategy  import TAStrategy
from strategies.dca_strategy import DCAStrategy
from strategies.base_strategy import Signal

log = logging.getLogger("SnipBot.StrategyManager")

REGISTRY = {
    "TA":  TAStrategy,
    "DCA": DCAStrategy,
}


class StrategyManager:

    MIN_CONFIDENCE = 62.0
    MIN_AGREEMENT  = 0.55

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.strategies = [cls(self.config) for cls in REGISTRY.values()]
        log.info(
            f"🎯 [SnipBot]: StrategyManager armed — "
            f"{len(self.strategies)} strategies: {[s.name for s in self.strategies]}"
        )

    def vote(self, pair: str, df: pd.DataFrame) -> Optional[Signal]:
        signals = []
        for strategy in self.strategies:
            try:
                sig = strategy.analyze(pair, df)
                signals.append((sig, strategy))
                log.debug(f"◎ [{strategy.name}] → {sig.action} {sig.confidence:.1f}%")
            except Exception as e:
                log.warning(f"⚠ [{strategy.name}] error on {pair}: {e}")

        if not signals:
            return None

        total_weight  = sum(s.weight for _, s in signals)
        buy_w = sell_w = buy_conf = sell_conf = 0.0

        for sig, strat in signals:
            w = strat.weight
            if sig.action == "BUY":
                buy_w    += w
                buy_conf += sig.confidence * w
            elif sig.action == "SELL":
                sell_w    += w
                sell_conf += sig.confidence * w

        buy_agree  = buy_w  / total_weight
        sell_agree = sell_w / total_weight
        buy_avg    = (buy_conf  / buy_w)  if buy_w  > 0 else 0.0
        sell_avg   = (sell_conf / sell_w) if sell_w > 0 else 0.0

        log.info(
            f"🔎 [Sniper Engine]: {pair} → "
            f"BUY {buy_agree*100:.0f}%/{buy_avg:.0f}% | "
            f"SELL {sell_agree*100:.0f}%/{sell_avg:.0f}%"
        )

        if buy_agree >= self.MIN_AGREEMENT and buy_avg >= self.MIN_CONFIDENCE and buy_avg > sell_avg:
            best = max((s for s, _ in signals if s.action == "BUY"), key=lambda s: s.confidence)
            return Signal(
                pair=pair, action="BUY", confidence=buy_avg,
                strategy="Consensus",
                reason=f"CONSENSUS BUY [{buy_agree*100:.0f}% agree]",
                entry_price=best.entry_price,
                stop_loss=best.stop_loss,
                take_profit=best.take_profit,
            )

        if sell_agree >= self.MIN_AGREEMENT and sell_avg >= self.MIN_CONFIDENCE and sell_avg > buy_avg:
            best = max((s for s, _ in signals if s.action == "SELL"), key=lambda s: s.confidence)
            return Signal(
                pair=pair, action="SELL", confidence=sell_avg,
                strategy="Consensus",
                reason=f"CONSENSUS SELL [{sell_agree*100:.0f}% agree]",
                entry_price=best.entry_price,
            )

        return None

    def status(self) -> dict:
        return {
            "strategies": [{"name": s.name, "weight": s.weight} for s in self.strategies],
            "min_confidence": self.MIN_CONFIDENCE,
            "min_agreement":  self.MIN_AGREEMENT,
        }
