"""
SnipBot Strategy Registry
--------------------------
Add a new strategy: import it here and add to REGISTRY.
StrategyManager loads all strategies from REGISTRY automatically.
"""

from .ta_strategy  import TAStrategy
from .dca_strategy import DCAStrategy

# ── Strategy Registry ────────────────────────────────────────────────────────
# Format: { "name": StrategyClass }
# Weight is defined on the class itself (strategy.weight)
REGISTRY = {
    "TA Analyst":  TAStrategy,
    "Smart DCA+":  DCAStrategy,
}

__all__ = ["TAStrategy", "DCAStrategy", "REGISTRY"]
