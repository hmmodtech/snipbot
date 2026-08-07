"""
SnipBot — Base Strategy
-----------------------
Abstract base class for all SnipBot trading strategies.
Every strategy returns a standardized Signal object.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    """Standardized trading signal returned by every strategy."""
    pair: str                        # e.g. "BTC/USDT"
    action: str                      # "BUY" | "SELL" | "HOLD"
    confidence: float                # 0.0 – 100.0
    strategy: str                    # strategy name
    reason: str                      # human-readable reasoning
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    def is_actionable(self, min_confidence: float = 60.0) -> bool:
        return self.action in ("BUY", "SELL") and self.confidence >= min_confidence

    def to_dict(self) -> dict:
        return {
            "pair": self.pair,
            "action": self.action,
            "confidence": self.confidence,
            "strategy": self.strategy,
            "reason": self.reason,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
        }


class BaseStrategy(ABC):
    """
    Abstract base. All strategies inherit from this.
    Implement `analyze(pair, df)` and return a Signal.
    """

    name: str = "BaseStrategy"
    weight: float = 1.0          # voting weight in StrategyManager

    def __init__(self, config: dict = None):
        self.config = config or {}

    @abstractmethod
    def analyze(self, pair: str, df: pd.DataFrame) -> Signal:
        """
        Analyze OHLCV DataFrame and return a Signal.

        df columns expected: open, high, low, close, volume
        df index: DatetimeIndex, sorted ascending
        """
        ...

    def hold(self, pair: str, reason: str) -> Signal:
        """Convenience — return a HOLD signal."""
        return Signal(
            pair=pair,
            action="HOLD",
            confidence=50.0,
            strategy=self.name,
            reason=reason,
        )

    def _validate_df(self, df: pd.DataFrame, min_rows: int = 30) -> bool:
        """Check DataFrame has enough rows and required columns."""
        required = {"open", "high", "low", "close", "volume"}
        if df is None or df.empty:
            return False
        if len(df) < min_rows:
            return False
        if not required.issubset(set(df.columns)):
            return False
        return True
