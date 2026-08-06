import ccxt
import pandas as pd

class SniperEngine:
    """
    وكيل 1: Sniper Engine
    يراقب السيولة ويرصد Breakouts
    """
    
    def __init__(self, exchange_id='kucoin', api_key='', api_secret='', passphrase=''):
        self.exchange = getattr(ccxt, exchange_id)({
            'apiKey': api_key,
            'secret': api_secret,
            'password': passphrase,
        })
        self.name = "Sniper Engine"
        self.confidence = 0
        self.signal = "HOLD"

    def scan_orderbook(self, symbol='BNB/USDT'):
        """مراقبة دفتر الأوامر"""
        try:
            ob = self.exchange.fetch_order_book(symbol, limit=20)
            bids = sum([b[1] for b in ob['bids']])
            asks = sum([a[1] for a in ob['asks']])
            ratio = bids / asks if asks > 0 else 1
            return ratio
        except:
            return 1.0

    def scan_breakout(self, symbol='BNB/USDT', timeframe='1h'):
        """رصد الاختراقات السعرية"""
        try:
            candles = self.exchange.fetch_ohlcv(symbol, timeframe, limit=50)
            df = pd.DataFrame(candles, columns=['time','open','high','low','close','volume'])
            
            # آخر 20 شمعة
            recent_high = df['high'].tail(20).max()
            current_price = df['close'].iloc[-1]
            
            # اختراق للأعلى
            if current_price >= recent_high * 0.995:
                return True, current_price
            return False, current_price
        except:
            return False, 0

    def analyze(self, symbol='BNB/USDT'):
        """التحليل الكامل وإرجاع الإشارة"""
        ratio = self.scan_orderbook(symbol)
        breakout, price = self.scan_breakout(symbol)
        
        # حساب الثقة
        if breakout and ratio > 1.2:
            self.confidence = 88
            self.signal = "BUY"
        elif ratio < 0.8:
            self.confidence = 75
            self.signal = "SELL"
        else:
            self.confidence = 45
            self.signal = "HOLD"
            
        return {
            "agent": self.name,
            "symbol": symbol,
            "signal": self.signal,
            "confidence": self.confidence,
            "orderbook_ratio": round(ratio, 2),
            "breakout": breakout,
            "price": price
        }


if __name__ == "__main__":
    agent = SniperEngine()
    result = agent.analyze('BNB/USDT')
    print(f"🎯 [Sniper Engine]: {result['symbol']} → {result['signal']} | Conf: {result['confidence']}%")
