"""
Base Strategy — القالب الأساسي
كل استراتيجية جديدة ترث من هذا الكلاس
مستلهم من freqtrade's IStrategy interface
"""

from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """
    القالب الأساسي لكل استراتيجية في SnipBot
    مستلهم من freqtrade IStrategy
    
    لإضافة استراتيجية جديدة:
    1. أنشئ ملف جديد في strategies/
    2. اورث من BaseStrategy
    3. طبّق analyze() و get_signal()
    """

    # اسم الاستراتيجية — كل استراتيجية تحدد اسمها
    NAME = "Base"
    VERSION = "1.0"

    # إعدادات افتراضية — تقدر تغيرها في كل استراتيجية
    TIMEFRAME = "1h"       # الإطار الزمني
    CANDLES_NEEDED = 100   # عدد الشمعات المطلوبة للتحليل

    @abstractmethod
    def analyze(self, df: pd.DataFrame, symbol: str) -> dict:
        """
        التحليل الرئيسي — كل استراتيجية تطبق هذا
        
        المدخلات:
            df: DataFrame يحتوي OHLCV data
            symbol: زوج التداول مثل BTC/USDT
            
        المخرجات:
            dict يحتوي:
                signal: BUY / SELL / HOLD
                confidence: 0-100
                reason: سبب القرار
                indicators: قيم المؤشرات
        """
        pass

    def validate_df(self, df: pd.DataFrame) -> bool:
        """التحقق من صحة البيانات قبل التحليل"""
        if df is None or df.empty:
            return False
        if len(df) < self.CANDLES_NEEDED:
            return False
        required = ["open", "high", "low", "close", "volume"]
        return all(col in df.columns for col in required)

    def get_info(self) -> dict:
        """معلومات الاستراتيجية"""
        return {
            "name": self.NAME,
            "version": self.VERSION,
            "timeframe": self.TIMEFRAME,
            "candles_needed": self.CANDLES_NEEDED
        }
