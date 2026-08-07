"""
Strategy Registry — سجل الاستراتيجيات
لإضافة استراتيجية جديدة:
1. أنشئ ملف في strategies/
2. أضفه هنا
"""

from .ta_strategy  import TAStrategy
from .dca_strategy import DCAStrategy

# سجل كل الاستراتيجيات المتاحة
STRATEGIES = {
    "TA":      TAStrategy,
    "DCA":     DCAStrategy,
}

def get_strategy(name: str):
    """جلب استراتيجية بالاسم"""
    cls = STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Strategy '{name}' not found. Available: {list(STRATEGIES.keys())}")
    return cls()

def list_strategies():
    """قائمة كل الاستراتيجيات"""
    return list(STRATEGIES.keys())
