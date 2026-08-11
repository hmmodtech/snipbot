import os, asyncio, logging, json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ── CONFIG ──
TOKEN       = os.getenv('TELEGRAM_TOKEN', '')
CHAT_ID     = os.getenv('CHAT_ID', '')
PROXY_URL   = os.getenv('PROXY_URL', 'https://snipbot-proxy.up.railway.app')

# ── TRADE WATCHER STATE ──
# يحفظ IDs الصفقات المعروفة حتى لا يرسل نفس الإشعار مرتين
_known_trade_ids = set()
_known_order_ids = set()
_last_portfolio  = {}

# ════════════════════════════════════════
# API CLIENT — يتصل بالـ Proxy
# ════════════════════════════════════════
async def api_get(path: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{PROXY_URL}{path}")
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        log.warning(f"API error {path}: {e}")
    return None


# ════════════════════════════════════════
# TRADE WATCHER — يراقب الصفقات الحقيقية
# ════════════════════════════════════════
async def watch_trades(ctx: ContextTypes.DEFAULT_TYPE):
    """
    يفحص كل دقيقة:
    1. صفقات جديدة → إشعار فوري
    2. تغيير في Portfolio → إشعار P&L
    """
    global _known_trade_ids, _known_order_ids, _last_portfolio
    if not CHAT_ID:
        return

    try:
        # ── فحص الصفقات الجديدة ──
        trades_data = await api_get('/api/trades')
        if trades_data and trades_data.get('trades'):
            trades = trades_data['trades']
            for t in trades:
                # استخدم time+symbol+type كـ ID فريد
                trade_id = f"{t.get('time','')}-{t.get('symbol','')}-{t.get('type','')}"
                if trade_id and trade_id not in _known_trade_ids:
                    _known_trade_ids.add(trade_id)

                    # لا ترسل للصفقات القديمة عند أول تشغيل
                    if len(_known_trade_ids) <= len(trades):
                        continue

                    is_buy = 'BUY' in str(t.get('type', '')).upper()
                    symbol = t.get('symbol', '—')
                    price  = float(t.get('price', t.get('entry_price', 0)) or 0)
                    cost   = float(t.get('cost', t.get('ref_market_cost', 0)) or 0)
                    date   = t.get('date', datetime.utcnow().strftime('%H:%M'))

                    if is_buy:
                        msg = (
                            f"🎯 *\\[SnipBot\\]: Target Acquired*\n\n"
                            f"● Pair: `{symbol}`\n"
                            f"● Side: `LONG ↑`\n"
                            f"● Entry: `${price:.4f}`\n"
                            f"● Size: `${cost:.2f} USDT`\n"
                            f"● Time: `{date}`\n"
                            f"● Mode: `PAPER TRADING`\n\n"
                            f"_🎯 Trigger armed\\. Position open\\._"
                        )
                    else:
                        msg = (
                            f"⚡ *\\[SnipBot Execution\\]: Position Closed*\n\n"
                            f"● Pair: `{symbol}`\n"
                            f"● Side: `SELL ↓`\n"
                            f"● Exit: `${price:.4f}`\n"
                            f"● Size: `${cost:.2f} USDT`\n"
                            f"● Time: `{date}`\n\n"
                            f"_◎ Position closed by Smart DCA\\._"
                        )

                    await ctx.bot.send_message(
                        chat_id=CHAT_ID, text=msg, parse_mode='MarkdownV2'
                    )
                    log.info(f"[TradeAlert] Sent: {symbol} {'BUY' if is_buy else 'SELL'}")

        # ── فحص Portfolio للتغيير ──
        portfolio = await api_get('/api/portfolio')
        if portfolio:
            pnl     = float(portfolio.get('realized_pnl', 0))
            total   = float(portfolio.get('total_portfolio_value', 10000))
            prev_pnl = float(_last_portfolio.get('realized_pnl', 0))

            # أرسل إشعار فقط إذا تغير الـ P&L بأكثر من $1
            if abs(pnl - prev_pnl) > 1.0 and _last_portfolio:
                diff    = pnl - prev_pnl
                sign    = '↑' if diff >= 0 else '↓'
                color   = '🟢' if diff >= 0 else '🔴'
                pct     = (pnl / total * 100)

                msg = (
                    f"{color} *\\[SnipBot\\]: P\\&L Update*\n\n"
                    f"● Realized P&L: `{'+'if pnl>=0 else ''}${pnl:.4f}`\n"
                    f"● Change: `{sign} ${'+'if diff>=0 else ''}{diff:.4f}`\n"
                    f"● Return: `{pct:.3f}%`\n"
                    f"● Capital: `${total:,.0f} USDT`\n\n"
                    f"_Smart DCA cycle update\\._"
                )
                await ctx.bot.send_message(
                    chat_id=CHAT_ID, text=msg, parse_mode='MarkdownV2'
                )

            _last_portfolio = portfolio

    except Exception as e:
        log.error(f"[TradeWatcher] Error: {e}")


async def watch_orders(ctx: ContextTypes.DEFAULT_TYPE):
    """يراقب الأوامر المفتوحة — يرسل إشعار عند فتح/إغلاق order"""
    global _known_order_ids
    if not CHAT_ID:
        return

    try:
        orders_data = await api_get('/api/orders')
        if not orders_data or not orders_data.get('orders'):
            return

        current_ids = set()
        for o in orders_data['orders']:
            oid = f"{o.get('time','')}-{o.get('symbol','')}-{o.get('price','')}"
            current_ids.add(oid)

            if oid not in _known_order_ids and _known_order_ids:
                symbol = o.get('symbol', '—')
                price  = float(o.get('price', 0) or 0)
                cost   = float(o.get('cost',  0) or 0)
                is_buy = 'BUY' in str(o.get('type', '')).upper()

                msg = (
                    f"◎ *\\[SnipBot Tracking\\]*\n\n"
                    f"● New order placed on `{symbol}`\n"
                    f"● Type: `{'BUY LIMIT' if is_buy else 'SELL LIMIT'}`\n"
                    f"● Price: `${price:.4f}`\n"
                    f"● Size: `${cost:.2f} USDT`\n\n"
                    f"_Awaiting fill\\._"
                )
                await ctx.bot.send_message(
                    chat_id=CHAT_ID, text=msg, parse_mode='MarkdownV2'
                )

        _known_order_ids = current_ids

    except Exception as e:
        log.error(f"[OrderWatcher] Error: {e}")


# ════════════════════════════════════════
# COMMANDS
# ════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 Portfolio",     callback_data="portfolio"),
         InlineKeyboardButton("⚡ Active Snipes",  callback_data="trades")],
        [InlineKeyboardButton("🤖 Agent Radar",   callback_data="agents"),
         InlineKeyboardButton("📈 P&L Report",    callback_data="pnl")],
        [InlineKeyboardButton("⛔ ABORT ALL",     callback_data="abort"),
         InlineKeyboardButton("▶️ ARM ENGINE",    callback_data="arm")],
    ]
    await update.message.reply_text(
        "🎯 *\\[SnipBot\\]: Precision Trading OS*\n\n"
        "● Status: `ACTIVE`\n"
        "● Mode: `PAPER TRADING`\n"
        "● Engine: `ONLINE`\n\n"
        "_Select your command below\\._",
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = await api_get('/api/portfolio')
    if data and data.get('source') != 'error':
        total  = float(data.get('total_portfolio_value', 10000))
        free   = float(data.get('free_usdt', 0))
        locked = float(data.get('locked_usdt', 0))
        pnl    = float(data.get('realized_pnl', 0))
        trades = int(data.get('total_trades', 0))
        buys   = int(data.get('buy_trades', 0))
        sells  = int(data.get('sell_trades', 0))
        sign   = '↑' if pnl >= 0 else '↓'
        pct    = pnl / total * 100

        msg = (
            f"💼 *\\[SnipBot\\]: Portfolio Report*\n\n"
            f"💰 Capital: `${total:,.2f} USDT`\n"
            f"🟡 Free: `${free:,.2f}`\n"
            f"🔒 Locked: `${locked:,.2f}`\n"
            f"{'🟢' if pnl>=0 else '🔴'} P&L: `{sign} ${abs(pnl):.4f}` \\(`{pct:.3f}%`\\)\n\n"
            f"📊 Trades: `{trades}` \\(`{buys}` BUY / `{sells}` SELL\\)\n"
            f"🏦 Exchange: `KuCoin — Paper Trading`\n\n"
            f"_Live data from OctoBot engine\\._"
        )
    else:
        msg = (
            "💼 *\\[SnipBot\\]: Portfolio*\n\n"
            "⚠️ Engine connecting\\.\\.\\.\n"
            "_Try again in a moment\\._"
        )
    kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="portfolio"),
           InlineKeyboardButton("↩️ Menu",    callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = await api_get('/api/trades')
    if data and data.get('trades'):
        trades = data['trades'][:6]
        lines  = []
        for t in trades:
            is_buy = 'BUY' in str(t.get('type', '')).upper()
            symbol = t.get('symbol', '—')
            price  = float(t.get('price', 0) or 0)
            cost   = float(t.get('cost',  0) or 0)
            icon   = '🟢' if is_buy else '🔴'
            side   = 'BUY ↑' if is_buy else 'SELL ↓'
            lines.append(f"{icon} `{symbol}` {side} @ `${price:.4f}` \\| `${cost:.0f}`")

        msg = (
            f"⚡ *\\[SnipBot\\]: Active Snipes*\n\n"
            + '\n'.join(lines) +
            f"\n\n_Total: {data.get('count',0)} trades — Smart DCA running\\._"
        )
    else:
        msg = "⚡ *\\[SnipBot\\]: No trades yet*\n\n_Smart DCA scanning for entries\\._"

    kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="trades"),
           InlineKeyboardButton("↩️ Menu",    callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_pnl(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = await api_get('/api/portfolio')
    if data:
        total  = float(data.get('total_portfolio_value', 10000))
        pnl    = float(data.get('realized_pnl', 0))
        buys   = int(data.get('buy_trades', 0))
        sells  = int(data.get('sell_trades', 0))
        pct    = pnl / total * 100
        icon   = '🟢' if pnl >= 0 else '🔴'

        msg = (
            f"{icon} *\\[SnipBot\\]: P\\&L Report*\n\n"
            f"● Realized P&L: `{'+'if pnl>=0 else ''}${pnl:.4f}`\n"
            f"● Return: `{pct:.3f}%`\n"
            f"● Buy trades: `{buys}`\n"
            f"● Sell trades: `{sells}`\n"
            f"● Capital: `${total:,.0f} USDT`\n\n"
            + (
                "_DCA accumulating — P&L improves as positions close\\._"
                if pnl < 0 else
                "_Profit realized\\. DCA cycle active\\._"
            )
        )
    else:
        msg = "📈 *\\[SnipBot\\]: P&L*\n\n_Loading\\.\\.\\._"

    kb = [[InlineKeyboardButton("↩️ Menu", callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_agents(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = await api_get('/api/agents/status')
    if data and data.get('agents'):
        agents = data['agents']
        cmap   = {'BUY':'🟢','SELL':'🔴','HOLD':'⚪','SCANNING':'🟡','NO DATA':'⚫'}
        lines  = []
        for a in agents:
            icon = cmap.get(a.get('action',''), '⚪')
            name = a.get('name','—')
            conf = float(a.get('confidence', 0))
            act  = a.get('action','—')
            pair = a.get('pair','')
            lines.append(f"{icon} `{name}` — `{conf:.0f}%` — {act}" + (f" on `{pair}`" if pair else ''))

        ts  = data.get('timestamp','')
        src = data.get('source','—')
        msg = (
            f"🤖 *\\[SnipBot\\]: Agent Radar*\n\n"
            + '\n'.join(lines) +
            f"\n\n_Source: {src}_ \\| _Updated: {ts[:16] if ts else '—'}_"
        )
    else:
        msg = (
            "🤖 *\\[SnipBot\\]: Agent Radar*\n\n"
            "🟡 `TA Analyst` — Awaiting scan\n"
            "🟡 `Smart DCA\\+` — Awaiting scan\n\n"
            "_Agents initializing\\._"
        )
    kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="agents"),
           InlineKeyboardButton("↩️ Menu",    callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_abort(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton("✅ CONFIRM ABORT", callback_data="confirm_abort"),
           InlineKeyboardButton("❌ Cancel",        callback_data="menu")]]
    await update.message.reply_text(
        "⛔ *\\[SnipBot\\]: EMERGENCY ABORT*\n\n"
        "This will halt ALL active snipes and freeze the engine\\.\n\n"
        "_Confirm to execute emergency protocol\\._",
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ════════════════════════════════════════
# INLINE CALLBACKS
# ════════════════════════════════════════
MAIN_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📊 Portfolio",    callback_data="portfolio"),
     InlineKeyboardButton("⚡ Active Snipes",callback_data="trades")],
    [InlineKeyboardButton("🤖 Agent Radar", callback_data="agents"),
     InlineKeyboardButton("📈 P&L Report",  callback_data="pnl")],
    [InlineKeyboardButton("⛔ ABORT ALL",   callback_data="abort"),
     InlineKeyboardButton("▶️ ARM ENGINE",  callback_data="arm")],
])

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == 'menu':
        await q.edit_message_text(
            "🎯 *\\[SnipBot\\]: Command Center*\n\n_Select your command\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif q.data == 'portfolio':
        data  = await api_get('/api/portfolio')
        total = float(data.get('total_portfolio_value',10000)) if data else 10000
        pnl   = float(data.get('realized_pnl',0)) if data else 0
        free  = float(data.get('free_usdt',0)) if data else 0
        await q.edit_message_text(
            f"💼 *\\[SnipBot\\]: Portfolio*\n\n"
            f"💰 Capital: `${total:,.2f}`\n"
            f"🟡 Free: `${free:,.2f}`\n"
            f"{'🟢'if pnl>=0 else'🔴'} P&L: `{'+'if pnl>=0 else''}${pnl:.4f}`\n\n"
            f"_KuCoin Paper Trading\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif q.data == 'trades':
        data = await api_get('/api/trades')
        if data and data.get('trades'):
            lines = []
            for t in data['trades'][:5]:
                is_buy = 'BUY' in str(t.get('type','')).upper()
                lines.append(f"{'🟢'if is_buy else'🔴'} `{t.get('symbol','—')}` {'BUY ↑'if is_buy else'SELL ↓'} @ `${float(t.get('price',0) or 0):.4f}`")
            await q.edit_message_text(
                "⚡ *\\[SnipBot\\]: Active Snipes*\n\n" + '\n'.join(lines) + f"\n\n_Total: {data.get('count',0)}_",
                parse_mode='MarkdownV2', reply_markup=MAIN_KB)
        else:
            await q.edit_message_text(
                "⚡ *\\[SnipBot\\]: No trades yet*\n\n_Scanning\\._",
                parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif q.data == 'agents':
        data = await api_get('/api/agents/status')
        if data and data.get('agents'):
            cmap = {'BUY':'🟢','SELL':'🔴','HOLD':'⚪','SCANNING':'🟡'}
            lines = [f"{cmap.get(a.get('action',''),'⚪')} `{a.get('name','—')}` — `{float(a.get('confidence',0)):.0f}%`" for a in data['agents']]
            await q.edit_message_text(
                "🤖 *\\[SnipBot\\]: Agent Radar*\n\n" + '\n'.join(lines) + "\n\n_Live scan data\\._",
                parse_mode='MarkdownV2', reply_markup=MAIN_KB)
        else:
            await q.edit_message_text(
                "🤖 *\\[SnipBot\\]: Agents initializing\\.*",
                parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif q.data == 'pnl':
        data  = await api_get('/api/portfolio')
        pnl   = float(data.get('realized_pnl',0)) if data else 0
        total = float(data.get('total_portfolio_value',10000)) if data else 10000
        await q.edit_message_text(
            f"📈 *\\[SnipBot\\]: P\\&L Report*\n\n"
            f"{'🟢'if pnl>=0 else'🔴'} Realized: `{'+'if pnl>=0 else''}${pnl:.4f}`\n"
            f"● Return: `{pnl/total*100:.3f}%`\n"
            f"● Capital: `${total:,.0f}`\n\n"
            f"_Smart DCA active\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif q.data == 'arm':
        await q.edit_message_text(
            "🎯 *\\[SnipBot\\]: Engine Armed*\n\n"
            "● Status: `SCANNING`\n"
            "● Agents: `ACTIVE`\n\n"
            "_Sniper Engine scanning order books\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif q.data == 'abort':
        await q.edit_message_text(
            "⛔ *\\[SnipBot\\]: ABORT — Confirm?*",
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ CONFIRM", callback_data="confirm_abort"),
                 InlineKeyboardButton("❌ Cancel",  callback_data="menu")]
            ]))

    elif q.data == 'confirm_abort':
        await q.edit_message_text(
            "⛔ *\\[SnipBot ABORT\\]: Emergency halt executed\\.*\n\n"
            "_All triggers suspended\\._",
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Main Menu", callback_data="menu")
            ]]))

# ════════════════════════════════════════
# STARTUP ALERT
# ════════════════════════════════════════
async def on_startup(app):
    global _known_trade_ids, _known_order_ids

    # تحميل الصفقات الموجودة حتى لا يرسل إشعارات عن صفقات قديمة
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{PROXY_URL}/api/trades")
            if r.status_code == 200:
                data = r.json()
                for t in (data.get('trades') or []):
                    tid = f"{t.get('time','')}-{t.get('symbol','')}-{t.get('type','')}"
                    _known_trade_ids.add(tid)
                log.info(f"[Startup] Loaded {len(_known_trade_ids)} existing trades")

            r2 = await c.get(f"{PROXY_URL}/api/orders")
            if r2.status_code == 200:
                data2 = r2.json()
                for o in (data2.get('orders') or []):
                    oid = f"{o.get('time','')}-{o.get('symbol','')}-{o.get('price','')}"
                    _known_order_ids.add(oid)
    except Exception as e:
        log.warning(f"[Startup] Could not preload trades: {e}")

    if CHAT_ID:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                "🎯 *\\[SnipBot\\]: Engine Online*\n\n"
                "● Status: `ACTIVE`\n"
                "● Mode: `PAPER TRADING`\n"
                "● Trade alerts: `ENABLED`\n"
                "● P&L tracking: `ENABLED`\n\n"
                "_Type /menu to begin\\._"
            ),
            parse_mode='MarkdownV2'
        )

# ════════════════════════════════════════
# MAIN
# ════════════════════════════════════════
def main():
    if not TOKEN:
        log.error("TELEGRAM_TOKEN not set"); return

    app = Application.builder().token(TOKEN).post_init(on_startup).build()

    # Commands
    app.add_handler(CommandHandler('start',     cmd_start))
    app.add_handler(CommandHandler('menu',      cmd_start))
    app.add_handler(CommandHandler('portfolio', cmd_portfolio))
    app.add_handler(CommandHandler('trades',    cmd_trades))
    app.add_handler(CommandHandler('snipes',    cmd_trades))
    app.add_handler(CommandHandler('agents',    cmd_agents))
    app.add_handler(CommandHandler('pnl',       cmd_pnl))
    app.add_handler(CommandHandler('abort',     cmd_abort))

    # Inline buttons
    app.add_handler(CallbackQueryHandler(button_handler))

    # ── Trade Watcher — كل 60 ثانية ──
    app.job_queue.run_repeating(watch_trades, interval=60, first=30)
    # ── Order Watcher — كل 2 دقيقة ──
    app.job_queue.run_repeating(watch_orders, interval=120, first=60)

    log.info("🎯 [SnipBot]: Telegram Fire initialized — Trade alerts ACTIVE")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
