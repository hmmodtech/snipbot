"""
SnipBot — Local Database
SQLite لحفظ الصفقات والـ P&L بشكل مستقل
"""

import sqlite3, json, os
from datetime import datetime

DB_PATH = os.environ.get('DB_PATH', '/data/snipbot.db')

def db_init():
    """إنشاء قاعدة البيانات عند التشغيل"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS trades (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        exchange    TEXT    NOT NULL,
        symbol      TEXT    NOT NULL,
        side        TEXT    NOT NULL,
        amount_usdt REAL    DEFAULT 0,
        price       REAL    DEFAULT 0,
        quantity    REAL    DEFAULT 0,
        fee         REAL    DEFAULT 0,
        mode        TEXT    DEFAULT 'paper',
        status      TEXT    DEFAULT 'filled',
        source      TEXT    DEFAULT 'engine',
        timestamp   TEXT    NOT NULL,
        raw         TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    NOT NULL,
        exchange    TEXT,
        total_usdt  REAL,
        balances    TEXT
    )''')

    conn.commit()
    conn.close()

def db_save_trade(trade: dict):
    """حفظ صفقة جديدة"""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    price    = float(trade.get('price', 0) or 0)
    amount   = float(trade.get('amount_usdt', 0) or 0)
    quantity = (amount / price) if price > 0 else 0
    c.execute('''INSERT INTO trades
        (exchange, symbol, side, amount_usdt, price, quantity, fee, mode, status, source, timestamp, raw)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''', (
        trade.get('exchange',    'unknown'),
        trade.get('symbol',      ''),
        trade.get('side',        '').upper(),
        amount,
        price,
        quantity,
        amount * 0.001,  # 0.1% fee estimate
        trade.get('mode',        'paper'),
        trade.get('status',      'filled'),
        trade.get('source',      'engine'),
        trade.get('timestamp',   datetime.now().isoformat()),
        json.dumps(trade),
    ))
    conn.commit()
    conn.close()

def db_get_trades(limit=100, exchange=None, symbol=None):
    """جلب الصفقات مع فلتر اختياري"""
    conn  = sqlite3.connect(DB_PATH)
    c     = conn.cursor()
    query = 'SELECT * FROM trades WHERE 1=1'
    params= []
    if exchange:
        query  += ' AND exchange=?'
        params.append(exchange)
    if symbol:
        query  += ' AND symbol=?'
        params.append(symbol)
    query += ' ORDER BY timestamp DESC LIMIT ?'
    params.append(limit)
    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    cols = ['id','exchange','symbol','side','amount_usdt','price','quantity','fee','mode','status','source','timestamp','raw']
    return [dict(zip(cols, row)) for row in rows]

def db_get_pnl():
    """حساب P&L من الصفقات المغلقة"""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()

    # جلب كل الصفقات مجمعة بالزوج
    c.execute('SELECT symbol, side, amount_usdt, price, quantity, fee FROM trades WHERE status="filled"')
    rows = c.fetchall()
    conn.close()

    # حساب P&L لكل زوج
    positions = {}
    realized_pnl = 0.0
    total_fees   = 0.0

    for symbol, side, amount_usdt, price, quantity, fee in rows:
        total_fees += fee
        if symbol not in positions:
            positions[symbol] = {'qty': 0, 'avg_price': 0, 'cost': 0}

        pos = positions[symbol]
        if side == 'BUY':
            new_qty       = pos['qty'] + quantity
            pos['cost']   = pos['cost'] + amount_usdt
            pos['avg_price'] = pos['cost'] / new_qty if new_qty > 0 else 0
            pos['qty']    = new_qty
        elif side == 'SELL' and pos['qty'] > 0:
            sell_qty     = min(quantity, pos['qty'])
            buy_cost     = pos['avg_price'] * sell_qty
            sell_revenue = price * sell_qty
            realized_pnl += sell_revenue - buy_cost - fee
            pos['qty']   -= sell_qty
            pos['cost']   = pos['avg_price'] * pos['qty']

    return {
        'net_realized_pnl': round(realized_pnl, 4),
        'total_fees':       round(total_fees, 4),
        'open_positions':   {k: v for k, v in positions.items() if v['qty'] > 0},
    }

def db_get_portfolio():
    """ملخص المحفظة من DB"""
    trades  = db_get_trades(limit=1000)
    buys    = [t for t in trades if t['side'] == 'BUY']
    sells   = [t for t in trades if t['side'] == 'SELL']
    pnl     = db_get_pnl()

    return {
        'total_capital': 0,  # يُحدَّث من المنصات الحية
        'activity': {
            'total_trades':   len(trades),
            'buy_count':      len(buys),
            'sell_count':     len(sells),
            'open_positions': len(pnl['open_positions']),
            'open_orders':    0,
            'closed_pairs':   len(sells),
        },
        'pnl': pnl,
    }

def db_save_portfolio_snapshot(exchange, total_usdt, balances):
    """حفظ snapshot للمحفظة"""
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute('INSERT INTO portfolio_snapshots (timestamp, exchange, total_usdt, balances) VALUES (?,?,?,?)',
              (datetime.now().isoformat(), exchange, total_usdt, json.dumps(balances)))
    conn.commit()
    conn.close()
