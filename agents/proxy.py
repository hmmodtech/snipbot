"""
SnipBot — Multi-Exchange Proxy
مستقل تماماً عن OctoBot
يدعم: KuCoin, Binance, Bybit (قابل للتوسع)
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os, json, time, hmac, hashlib, base64, requests
from datetime import datetime
from database import db_init, db_save_trade, db_get_trades, db_get_pnl, db_get_portfolio

app = Flask(__name__)
CORS(app)

# ══════════════════════════════════════════
# EXCHANGE REGISTRY — يُحمَّل من ENV أو Dashboard
# ══════════════════════════════════════════

def get_exchange_config(exchange_id):
    """يجيب إعدادات المنصة من environment variables"""
    ex = exchange_id.upper()
    return {
        'api_key':    os.environ.get(f'{ex}_API_KEY',    ''),
        'secret':     os.environ.get(f'{ex}_API_SECRET', ''),
        'passphrase': os.environ.get(f'{ex}_PASSPHRASE', ''),
        'mode':       os.environ.get(f'{ex}_MODE',       'paper'),
        'enabled':    os.environ.get(f'{ex}_ENABLED',    'false').lower() == 'true',
    }

def get_all_exchanges():
    """يرجع كل المنصات المضافة"""
    supported = ['KUCOIN', 'BINANCE', 'BYBIT', 'OKX', 'BITGET']
    result = []
    for ex in supported:
        cfg = get_exchange_config(ex)
        if cfg['enabled'] or cfg['api_key']:
            result.append({'id': ex.lower(), 'name': ex, **cfg})
    return result

# ══════════════════════════════════════════
# KUCOIN
# ══════════════════════════════════════════

class KuCoin:
    BASE = 'https://api.kucoin.com'

    def __init__(self, api_key, secret, passphrase):
        self.api_key    = api_key
        self.secret     = secret
        self.passphrase = passphrase

    def _headers(self, method, path, body=''):
        ts  = str(int(time.time() * 1000))
        msg = ts + method.upper() + path + (body or '')
        sig = base64.b64encode(hmac.new(
            self.secret.encode(), msg.encode(), hashlib.sha256
        ).digest()).decode()
        pp  = base64.b64encode(hmac.new(
            self.secret.encode(), self.passphrase.encode(), hashlib.sha256
        ).digest()).decode()
        return {
            'KC-API-KEY':        self.api_key,
            'KC-API-SIGN':       sig,
            'KC-API-TIMESTAMP':  ts,
            'KC-API-PASSPHRASE': pp,
            'KC-API-KEY-VERSION':'2',
            'Content-Type':      'application/json',
        }

    def get_balance(self):
        path = '/api/v1/accounts?type=trade'
        r = requests.get(self.BASE + path, headers=self._headers('GET', path), timeout=10)
        data = r.json()
        if data.get('code') != '200000':
            return None
        accounts = data.get('data', [])
        balances = {}
        for acc in accounts:
            currency = acc['currency']
            available = float(acc['available'])
            if available > 0:
                balances[currency] = available
        return balances

    def place_order(self, symbol, side, amount_usdt, price=None):
        """paper mode أو real mode"""
        cfg = get_exchange_config('kucoin')
        if cfg['mode'] == 'paper':
            return self._paper_order(symbol, side, amount_usdt, price)
        path = '/api/v1/orders'
        kucoin_symbol = symbol.replace('/', '-')
        body = json.dumps({
            'clientOid': f'snipbot_{int(time.time()*1000)}',
            'side':      side.lower(),
            'symbol':    kucoin_symbol,
            'type':      'market' if not price else 'limit',
            'funds':     str(amount_usdt) if side.upper() == 'BUY' else None,
            'size':      None,
            'price':     str(price) if price else None,
        })
        r = requests.post(self.BASE + path, headers=self._headers('POST', path, body), data=body, timeout=10)
        return r.json()

    def _paper_order(self, symbol, side, amount_usdt, price):
        """تنفيذ ورقي محلي"""
        trade = {
            'exchange':    'kucoin',
            'symbol':      symbol,
            'side':        side.upper(),
            'amount_usdt': amount_usdt,
            'price':       price or get_price(symbol, 'kucoin'),
            'mode':        'paper',
            'timestamp':   datetime.now().isoformat(),
            'status':      'filled',
        }
        db_save_trade(trade)
        return {'status': 'paper_filled', 'trade': trade}

    def get_ohlcv(self, symbol, timeframe='15min', limit=80):
        tf_map = {'1m':'1min','5m':'5min','15m':'15min','1h':'1hour','4h':'4hour','1d':'1day'}
        tf = tf_map.get(timeframe, '15min')
        kucoin_symbol = symbol.replace('/', '-')
        url = f'{self.BASE}/api/v1/market/candles?type={tf}&symbol={kucoin_symbol}'
        r = requests.get(url, timeout=10)
        data = r.json()
        if data.get('code') != '200000':
            return []
        raw = data.get('data', [])[:limit]
        return [{'t': int(c[0])*1000, 'o': float(c[1]), 'c': float(c[2]),
                 'h': float(c[3]), 'l': float(c[4]), 'v': float(c[5])} for c in raw][::-1]

    def get_ticker(self, symbol):
        kucoin_symbol = symbol.replace('/', '-')
        url = f'{self.BASE}/api/v1/market/orderbook/level1?symbol={kucoin_symbol}'
        r = requests.get(url, timeout=5)
        data = r.json()
        if data.get('code') == '200000':
            return {'price': float(data['data']['price']), 'symbol': symbol}
        return None

# ══════════════════════════════════════════
# BINANCE
# ══════════════════════════════════════════

class Binance:
    BASE = 'https://api.binance.com'

    def __init__(self, api_key, secret):
        self.api_key = api_key
        self.secret  = secret

    def _sign(self, params):
        query = '&'.join([f'{k}={v}' for k, v in params.items()])
        sig   = hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        return query + '&signature=' + sig

    def _headers(self):
        return {'X-MBX-APIKEY': self.api_key}

    def get_balance(self):
        ts     = int(time.time() * 1000)
        params = {'timestamp': ts}
        url    = f'{self.BASE}/api/v3/account?{self._sign(params)}'
        r      = requests.get(url, headers=self._headers(), timeout=10)
        data   = r.json()
        if 'balances' not in data:
            return None
        return {b['asset']: float(b['free']) for b in data['balances'] if float(b['free']) > 0}

    def place_order(self, symbol, side, amount_usdt, price=None):
        cfg = get_exchange_config('binance')
        if cfg['mode'] == 'paper':
            return self._paper_order(symbol, side, amount_usdt, price)
        binance_symbol = symbol.replace('/', '')
        ts     = int(time.time() * 1000)
        params = {
            'symbol':    binance_symbol,
            'side':      side.upper(),
            'type':      'MARKET',
            'quoteOrderQty': amount_usdt,
            'timestamp': ts,
        }
        url = f'{self.BASE}/api/v3/order?{self._sign(params)}'
        r   = requests.post(url, headers=self._headers(), timeout=10)
        return r.json()

    def _paper_order(self, symbol, side, amount_usdt, price):
        trade = {
            'exchange':    'binance',
            'symbol':      symbol,
            'side':        side.upper(),
            'amount_usdt': amount_usdt,
            'price':       price or 0,
            'mode':        'paper',
            'timestamp':   datetime.now().isoformat(),
            'status':      'filled',
        }
        db_save_trade(trade)
        return {'status': 'paper_filled', 'trade': trade}

    def get_ohlcv(self, symbol, timeframe='15m', limit=80):
        binance_symbol = symbol.replace('/', '')
        url = f'{self.BASE}/api/v3/klines?symbol={binance_symbol}&interval={timeframe}&limit={limit}'
        r   = requests.get(url, timeout=10)
        raw = r.json()
        if not isinstance(raw, list):
            return []
        return [{'t': c[0], 'o': float(c[1]), 'h': float(c[2]),
                 'l': float(c[3]), 'c': float(c[4]), 'v': float(c[5])} for c in raw]

    def get_ticker(self, symbol):
        binance_symbol = symbol.replace('/', '')
        url = f'{self.BASE}/api/v3/ticker/price?symbol={binance_symbol}'
        r   = requests.get(url, timeout=5)
        data = r.json()
        if 'price' in data:
            return {'price': float(data['price']), 'symbol': symbol}
        return None

# ══════════════════════════════════════════
# BYBIT
# ══════════════════════════════════════════

class Bybit:
    BASE = 'https://api.bybit.com'

    def __init__(self, api_key, secret):
        self.api_key = api_key
        self.secret  = secret

    def _sign(self, params_str):
        return hmac.new(self.secret.encode(), params_str.encode(), hashlib.sha256).hexdigest()

    def get_balance(self):
        ts     = str(int(time.time() * 1000))
        params = f'accountType=UNIFIED'
        sig    = self._sign(ts + self.api_key + '5000' + params)
        headers = {
            'X-BAPI-API-KEY':   self.api_key,
            'X-BAPI-SIGN':      sig,
            'X-BAPI-TIMESTAMP': ts,
            'X-BAPI-RECV-WINDOW': '5000',
        }
        url = f'{self.BASE}/v5/account/wallet-balance?{params}'
        r   = requests.get(url, headers=headers, timeout=10)
        data = r.json()
        if data.get('retCode') != 0:
            return None
        coins = data['result']['list'][0]['coin']
        return {c['coin']: float(c['walletBalance']) for c in coins if float(c['walletBalance']) > 0}

    def place_order(self, symbol, side, amount_usdt, price=None):
        cfg = get_exchange_config('bybit')
        if cfg['mode'] == 'paper':
            trade = {
                'exchange': 'bybit', 'symbol': symbol, 'side': side.upper(),
                'amount_usdt': amount_usdt, 'price': price or 0,
                'mode': 'paper', 'timestamp': datetime.now().isoformat(), 'status': 'filled',
            }
            db_save_trade(trade)
            return {'status': 'paper_filled', 'trade': trade}
        bybit_symbol = symbol.replace('/', '')
        ts  = str(int(time.time() * 1000))
        body = json.dumps({
            'category': 'spot', 'symbol': bybit_symbol,
            'side': side.capitalize(), 'orderType': 'Market',
            'qty': str(amount_usdt), 'marketUnit': 'quoteCoin',
        })
        sig = self._sign(ts + self.api_key + '5000' + body)
        headers = {
            'X-BAPI-API-KEY': self.api_key, 'X-BAPI-SIGN': sig,
            'X-BAPI-TIMESTAMP': ts, 'X-BAPI-RECV-WINDOW': '5000',
            'Content-Type': 'application/json',
        }
        r = requests.post(f'{self.BASE}/v5/order/create', headers=headers, data=body, timeout=10)
        return r.json()

    def get_ohlcv(self, symbol, timeframe='15', limit=80):
        tf_map = {'1m':'1','5m':'5','15m':'15','1h':'60','4h':'240','1d':'D'}
        tf = tf_map.get(timeframe, '15')
        bybit_symbol = symbol.replace('/', '')
        url = f'{self.BASE}/v5/market/kline?category=spot&symbol={bybit_symbol}&interval={tf}&limit={limit}'
        r   = requests.get(url, timeout=10)
        data = r.json()
        if data.get('retCode') != 0:
            return []
        raw = data['result']['list']
        return [{'t': int(c[0]), 'o': float(c[1]), 'h': float(c[2]),
                 'l': float(c[3]), 'c': float(c[4]), 'v': float(c[5])} for c in raw][::-1]

    def get_ticker(self, symbol):
        bybit_symbol = symbol.replace('/', '')
        url = f'{self.BASE}/v5/market/tickers?category=spot&symbol={bybit_symbol}'
        r   = requests.get(url, timeout=5)
        data = r.json()
        if data.get('retCode') == 0:
            price = float(data['result']['list'][0]['lastPrice'])
            return {'price': price, 'symbol': symbol}
        return None

# ══════════════════════════════════════════
# EXCHANGE ROUTER — يختار المنصة تلقائياً
# ══════════════════════════════════════════

def get_exchange_client(exchange_id):
    cfg = get_exchange_config(exchange_id)
    ex  = exchange_id.lower()
    if ex == 'kucoin':
        return KuCoin(cfg['api_key'], cfg['secret'], cfg['passphrase'])
    elif ex == 'binance':
        return Binance(cfg['api_key'], cfg['secret'])
    elif ex == 'bybit':
        return Bybit(cfg['api_key'], cfg['secret'])
    return None

def get_price(symbol, exchange_id='kucoin'):
    """يجيب السعر من أي منصة"""
    try:
        client = get_exchange_client(exchange_id)
        if client:
            ticker = client.get_ticker(symbol)
            if ticker:
                return ticker['price']
    except:
        pass
    # fallback: KuCoin public API
    try:
        kucoin_symbol = symbol.replace('/', '-')
        r = requests.get(f'https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={kucoin_symbol}', timeout=5)
        data = r.json()
        if data.get('code') == '200000':
            return float(data['data']['price'])
    except:
        pass
    return 0

# ══════════════════════════════════════════
# API ROUTES
# ══════════════════════════════════════════

@app.route('/api/exchanges', methods=['GET'])
def api_exchanges():
    """قائمة المنصات المتاحة وحالتها"""
    exchanges = []
    for ex_id in ['kucoin', 'binance', 'bybit', 'okx', 'bitget']:
        cfg = get_exchange_config(ex_id)
        connected = bool(cfg['api_key'])
        balance   = None
        if connected:
            try:
                client  = get_exchange_client(ex_id)
                if client:
                    balance = client.get_balance()
            except:
                pass
        exchanges.append({
            'id':        ex_id,
            'name':      ex_id.upper(),
            'connected': connected,
            'mode':      cfg['mode'],
            'enabled':   cfg['enabled'],
            'balance':   balance,
            'usdt':      balance.get('USDT', 0) if balance else 0,
        })
    return jsonify({'exchanges': exchanges})

@app.route('/api/exchange/connect', methods=['POST'])
def api_exchange_connect():
    """ربط منصة جديدة — يحفظ في environment وقت التشغيل"""
    data     = request.json
    ex_id    = data.get('exchange', '').upper()
    api_key  = data.get('api_key',  '')
    secret   = data.get('secret',   '')
    password = data.get('passphrase','')
    mode     = data.get('mode', 'paper')

    if not ex_id or not api_key or not secret:
        return jsonify({'status': 'error', 'message': 'Missing fields'}), 400

    # اختبار الاتصال
    os.environ[f'{ex_id}_API_KEY']    = api_key
    os.environ[f'{ex_id}_API_SECRET'] = secret
    os.environ[f'{ex_id}_PASSPHRASE'] = password
    os.environ[f'{ex_id}_MODE']       = mode
    os.environ[f'{ex_id}_ENABLED']    = 'true'

    try:
        client  = get_exchange_client(ex_id.lower())
        balance = client.get_balance() if client else None
        usdt    = balance.get('USDT', 0) if balance else 0
        return jsonify({'status': 'connected', 'exchange': ex_id, 'usdt': usdt, 'mode': mode})
    except Exception as e:
        return jsonify({'status': 'auth_error', 'message': str(e)}), 401

@app.route('/api/exchange/disconnect', methods=['POST'])
def api_exchange_disconnect():
    data  = request.json
    ex_id = data.get('exchange', '').upper()
    for key in ['API_KEY', 'API_SECRET', 'PASSPHRASE', 'MODE', 'ENABLED']:
        os.environ.pop(f'{ex_id}_{key}', None)
    return jsonify({'status': 'disconnected', 'exchange': ex_id})

@app.route('/api/balance', methods=['GET'])
def api_balance():
    """رصيد كل المنصات مجمّع"""
    exchange_id = request.args.get('exchange', 'kucoin')
    try:
        client  = get_exchange_client(exchange_id)
        balance = client.get_balance() if client else {}
        usdt    = balance.get('USDT', 0) if balance else 0
        return jsonify({'exchange': exchange_id, 'balance': balance, 'usdt': usdt, 'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/portfolio', methods=['GET'])
def api_portfolio():
    """محفظة مجمّعة من كل المنصات"""
    total_usdt = 0
    breakdown  = []
    for ex_id in ['kucoin', 'binance', 'bybit']:
        cfg = get_exchange_config(ex_id)
        if not cfg['api_key']:
            continue
        try:
            client  = get_exchange_client(ex_id)
            balance = client.get_balance() if client else {}
            usdt    = balance.get('USDT', 0) if balance else 0
            total_usdt += usdt
            breakdown.append({'exchange': ex_id, 'usdt': usdt, 'balance': balance, 'mode': cfg['mode']})
        except:
            pass

    db_port = db_get_portfolio()
    return jsonify({
        'portfolio': {
            'total_capital': total_usdt or db_port.get('total_capital', 0),
            'free_usdt':     total_usdt,
            'mode':          'Mixed' if len(breakdown) > 1 else (breakdown[0]['mode'] if breakdown else 'paper'),
        },
        'breakdown': breakdown,
        'pnl':       db_get_pnl(),
        'activity':  db_port.get('activity', {}),
        'source':    'live' if breakdown else 'db',
    })

@app.route('/api/summary', methods=['GET'])
def api_summary():
    """نفس endpoint القديم — للتوافق مع الداشبورد"""
    port = api_portfolio().get_json()
    trades = db_get_trades(limit=200)

    buy_trades  = [t for t in trades if t.get('side') == 'BUY']
    sell_trades = [t for t in trades if t.get('side') == 'SELL']

    return jsonify({
        'portfolio': port['portfolio'],
        'pnl':       port['pnl'],
        'activity': {
            'total_trades':    len(trades),
            'buy_count':       len(buy_trades),
            'sell_count':      len(sell_trades),
            'open_positions':  len(buy_trades) - len(sell_trades),
            'open_orders':     0,
            'closed_pairs':    len(sell_trades),
        },
        'engine': {
            'exchange': 'Multi-Exchange',
            'mode':     port['portfolio']['mode'],
            'status':   'online',
            'strategy': 'SnipBot Engine',
        },
        'source': 'live',
    })

@app.route('/api/order', methods=['POST'])
def api_order():
    """تنفيذ صفقة على المنصة المختارة"""
    data        = request.json
    symbol      = data.get('symbol',    'BTC/USDT')
    side        = data.get('side',      'BUY')
    amount_usdt = data.get('amount_usdt', 100)
    price       = data.get('price',     None)
    exchange_id = data.get('exchange',  'kucoin')
    source      = data.get('source',    'manual')

    try:
        client = get_exchange_client(exchange_id)
        if not client:
            return jsonify({'status': 'error', 'message': f'{exchange_id} not configured'}), 400
        result = client.place_order(symbol, side, amount_usdt, price)
        return jsonify({'status': 'ok', 'result': result, 'exchange': exchange_id})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/ohlcv', methods=['GET'])
def api_ohlcv():
    """بيانات الشموع من أي منصة"""
    symbol     = request.args.get('symbol',    'ADA/USDT')
    timeframe  = request.args.get('timeframe', '15m')
    limit      = int(request.args.get('limit', 80))
    exchange_id= request.args.get('exchange',  'kucoin')

    # جرب المنصة المطلوبة أولاً، ثم KuCoin كـ fallback
    for ex in [exchange_id, 'kucoin', 'binance']:
        try:
            client  = get_exchange_client(ex)
            if not client:
                continue
            candles = client.get_ohlcv(symbol, timeframe, limit)
            if candles:
                return jsonify({'symbol': symbol, 'exchange': ex, 'candles': candles})
        except:
            continue

    return jsonify({'symbol': symbol, 'candles': [], 'error': 'No data'}), 200

@app.route('/api/trades', methods=['GET'])
def api_trades():
    exchange = request.args.get('exchange', None)
    limit    = int(request.args.get('limit', 100))
    trades   = db_get_trades(limit=limit, exchange=exchange)
    return jsonify({'trades': trades, 'total': len(trades)})

@app.route('/api/telegram/send', methods=['POST'])
def api_telegram():
    data    = request.json
    message = data.get('message', '')
    token   = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID',   '')
    if token and chat_id and message:
        try:
            requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'},
                timeout=5
            )
        except:
            pass
    return jsonify({'status': 'sent'})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'online', 'service': 'SnipBot Multi-Exchange Proxy', 'time': datetime.now().isoformat()})

if __name__ == '__main__':
    db_init()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
