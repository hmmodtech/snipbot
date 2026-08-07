"""
Strategy Manager — مدير الاستراتيجيات
يشغّل استراتيجية أو أكثر على نفس الزوج
ويجمع قراراتهم بنظام تصويت
"""

import logging
from strategies import get_strategy, list_strategies

log = logging.getLogger("Strategy-Manager")


class StrategyManager:
    """
    يدير استراتيجيات متعددة
    
    كيف يعمل:
    - تعطيه قائمة استراتيجيات
    - يشغّلها كلها على نفس الزوج
    - يجمع قراراتهم بتصويت موزون
    - يرجع قرار واحد نهائي
    """

    def __init__(self, strategy_names: list = None):
        """
        strategy_names: قائمة أسماء الاستراتيجيات
        مثال: ["TA", "DCA"]
        """
        if strategy_names is None:
            strategy_names = list_strategies()  # كل الاستراتيجيات

        self.strategies = []
        for name in strategy_names:
            try:
                strategy = get_strategy(name)
                self.strategies.append(strategy)
                log.info(f"[Manager]: Loaded strategy — {name}")
            except Exception as e:
                log.error(f"[Manager]: Failed to load {name} — {e}")

        log.info(f"[Manager]: {len(self.strategies)} strategies ready")

    def run(self, df, symbol: str) -> dict:
        """
        يشغّل كل الاستراتيجيات ويجمع النتائج
        """
        if not self.strategies:
            return {
                "symbol": symbol,
                "signal": "HOLD",
                "confidence": 0,
                "reason": "No strategies loaded",
                "details": []
            }

        results    = []
        buy_votes  = 0
        sell_votes = 0
        hold_votes = 0
        total_conf = 0

        for strategy in self.strategies:
            result = strategy.analyze(df, symbol)
            results.append(result)

            sig  = result.get("signal", "HOLD")
            conf = result.get("confidence", 50)
            total_conf += conf

            if sig == "BUY":
                buy_votes  += conf
            elif sig == "SELL":
                sell_votes += conf
            else:
                hold_votes += conf

        # ── نظام التصويت الموزون ──
        avg_confidence = round(total_conf / len(results), 1)
        total_votes    = buy_votes + sell_votes + hold_votes

        buy_pct  = (buy_votes  / total_votes * 100) if total_votes > 0 else 0
        sell_pct = (sell_votes / total_votes * 100) if total_votes > 0 else 0

        # القرار النهائي
        if buy_pct >= 60 and avg_confidence >= 60:
            final_signal = "BUY"
            reason = f"✅ {buy_pct:.0f}% strategies say BUY"
        elif sell_pct >= 60 and avg_confidence >= 60:
            final_signal = "SELL"
            reason = f"📉 {sell_pct:.0f}% strategies say SELL"
        else:
            final_signal = "HOLD"
            reason = f"⏳ Mixed signals — BUY:{buy_pct:.0f}% SELL:{sell_pct:.0f}%"

        final = {
            "symbol":     symbol,
            "signal":     final_signal,
            "confidence": avg_confidence,
            "reason":     reason,
            "buy_pct":    round(buy_pct, 1),
            "sell_pct":   round(sell_pct, 1),
            "strategies_count": len(results),
            "details":    results
        }

        log.info(
            f"[Manager]: {symbol} → {final_signal} "
            f"({avg_confidence}%) | "
            f"BUY:{buy_pct:.0f}% SELL:{sell_pct:.0f}%"
        )
        return final
