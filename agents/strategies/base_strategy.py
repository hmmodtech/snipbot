from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
import pandas as pd


@dataclass
class Signal:
    pair:        str
    action:      str           # BUY | SELL | HOLD
    confidence:  float         # 0–100
    strategy:    str
    reason:      str
    entry_price: Optional[float] = None
    stop_loss:   Optional[float] = None
    take_profit: Optional[float] = None

    def is_actionable(self, min_confidence: float = 60.0) -> bool:
        return self.action in ("BUY", "SELL") and self.confidence >= min_confidence

    def to_dict(self) -> dict:
        return self.__dict__


class BaseStrategy(ABC):
    name:   str   = "BaseStrategy"
    weight: float = 1.0

    def __init__(self, config: dict = None):
        self.config = config or {}

    @abstractmethod
    def analyze(self, pair: str, df: pd.DataFrame) -> Signal: ...

    def hold(self, pair: str, reason: str) -> Signal:
        return Signal(pair=pair, action="HOLD", confidence=50.0,
                      strategy=self.name, reason=reason)

    def _validate_df(self, df: pd.DataFrame, min_rows: int = 30) -> bool:
        required = {"open", "high", "low", "close", "volume"}
        return (df is not None and not df.empty
                and len(df) >= min_rows
                and required.issubset(df.columns))
