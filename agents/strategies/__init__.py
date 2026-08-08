from strategies.ta_strategy  import TAStrategy
from strategies.dca_strategy import DCAStrategy

REGISTRY = {
    "TA":  TAStrategy,
    "DCA": DCAStrategy,
}

__all__ = ["TAStrategy", "DCAStrategy", "REGISTRY"]
