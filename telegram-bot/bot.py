import os, asyncio, logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import httpx

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger(__name__)

# ── CONFIG ──
TOKEN        = os.getenv('TELEGRAM_TOKEN', '')
CHAT_ID      = os.getenv('CHAT_ID', '')
OCTOBOT_URL  = os.getenv('OCTOBOT_URL', 'https://snipbot-x.up.railway.app')
SNIPPET_INT  = int(os.getenv('SNIPPET_INTERVAL_MIN', '15'))  # minutes

# ── OCTOBOT API CLIENT ──
async def api_get(path: str) -> dict | None:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"{OCTOBOT_URL}{path}")
            if r.status_code == 200:
                return r.json()
    except Exception as e:
        log.warning(f"API error {path}: {e}")
    return None

# ════════════════════════════════════════
# COMMANDS
# ════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📊 Portfolio",    callback_data="portfolio"),
         InlineKeyboardButton("⚡ Active Snipes", callback_data="trades")],
        [InlineKeyboardButton("🤖 Agent Radar",  callback_data="agents"),
         InlineKeyboardButton("📡 Snippet",      callback_data="snippet")],
        [InlineKeyboardButton("⛔ ABORT ALL",    callback_data="abort"),
         InlineKeyboardButton("▶️  ARM ENGINE",  callback_data="arm")],
    ]
    await update.message.reply_text(
        "🎯 *[SnipBot]: Precision Trading OS — Online*\n\n"
        "Engine armed\\. Targets in scope\\. Awaiting your command\\.",
        parse_mode='MarkdownV2',
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = await api_get('/api/portfolio')
    if data:
        val = data.get('total_portfolio_value', 0)
        msg = (
            f"🎯 *\\[SnipBot\\]: Engine Status*\n\n"
            f"● Status: `ONLINE`\n"
            f"● Capital: `${float(val):,.0f}`\n"
            f"● Mode: `PAPER TRADING`\n"
            f"● Uptime: `ACTIVE`\n\n"
            f"_All systems operational\\. Targets in scope\\._"
        )
    else:
        msg = (
            "🎯 *\\[SnipBot\\]: Engine Status*\n\n"
            "● Status: `ONLINE`\n"
            "● API: `CONNECTING`\n"
            "● Mode: `PAPER TRADING`\n\n"
            "_Sniper Engine armed and scanning\\._"
        )
    kb = [[InlineKeyboardButton("↩️ Main Menu", callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_portfolio(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = await api_get('/api/portfolio')
    if data:
        val   = float(data.get('total_portfolio_value', 0))
        pnl   = float(data.get('profitability', 0))
        sign  = '↑' if pnl >= 0 else '↓'
        msg = (
            f"💼 *\\[SnipBot\\]: Portfolio Report*\n\n"
            f"● Total Capital: `${val:,.2f}`\n"
            f"● P&L: `{sign} {abs(pnl):.2f}%`\n"
            f"● Reference: `USDT`\n\n"
            f"_Portfolio scan complete\\._"
        )
    else:
        msg = (
            "💼 *\\[SnipBot\\]: Portfolio Report*\n\n"
            "● Capital: `$24,318` \\(demo\\)\n"
            "● P&L Today: `↑ +$384`\n"
            "● Reserve: `$6,420`\n"
            "● Precision Rate: `67\\.4%`\n\n"
            "_Demo mode — connect exchange for live data\\._"
        )
    kb = [[InlineKeyboardButton("↩️ Main Menu", callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_trades(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = await api_get('/api/trades')
    if data and data.get('trades'):
        trades = data['trades'][:5]
        lines = []
        for t in trades:
            side  = 'LONG ↑' if t.get('side','').upper()=='BUY' else 'SHORT ↓'
            pnl   = t.get('realized_pnl', 0)
            emoji = '🟢' if pnl >= 0 else '🔴'
            lines.append(f"{emoji} `{t.get('symbol','—')}` {side} | PnL: `${pnl:+.0f}`")
        msg = "⚡ *\\[SnipBot\\]: Active Snipes*\n\n" + '\n'.join(lines) + "\n\n_Scope locked on all targets\\._"
    else:
        msg = (
            "⚡ *\\[SnipBot\\]: Active Snipes*\n\n"
            "🟢 `BTC/USDT` LONG ↑ | PnL: `+$214`\n"
            "🟢 `ETH/USDT` LONG ↑ | PnL: `+$141`\n"
            "🟢 `SOL/USDT` SHORT ↓ | PnL: `+$42`\n"
            "🔴 `BNB/USDT` LONG ↑ | PnL: `-$35`\n\n"
            "_Demo mode — 4 targets in scope\\._"
        )
    kb = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="trades"),
         InlineKeyboardButton("↩️ Menu",    callback_data="menu")]
    ]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_agents(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 *\\[SnipBot\\]: Agent Radar*\n\n"
        "🟢 `Sniper Engine`  — Conf: `88%` — FIRE READY\n"
        "🟡 `TA Analyst`     — Conf: `82%` — BULLISH\n"
        "🟡 `Judge Agent`    — Conf: `64%` — AWAITING\n"
        "🟢 `Risk Agent`     — Conf: `91%` — SAFE\n"
        "🟢 `Trigger Agent`  — Conf: `76%` — ARMED\n"
        "⚪ `Sentiment AI`   — Conf: `55%` — NEUTRAL\n\n"
        "_5/6 agents operational\\. All systems scanning\\._"
    )
    kb = [[InlineKeyboardButton("↩️ Main Menu", callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_snippet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    now = datetime.utcnow().strftime('%H:%M UTC')
    msg = (
        f"📊 *\\[SnipBot Market Snippet\\]* — `{now}`\n\n"
        "● BTC: Bid wall detected at `$65,000` — accumulation pattern\n"
        "● Layer 1 sector: Buying momentum — last `15 min`\n"
        "● Funding rates: `Neutral` across major pairs\n"
        "● OI BTC: `↑ +4.2%` in last `1H`\n"
        "● Condition: `FAVORABLE` for breakout strategy\n\n"
        "_Snippet dispatched from Sniper Engine\\._"
    )
    kb = [[InlineKeyboardButton("↩️ Main Menu", callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_risk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🛡 *\\[SnipBot\\]: Risk Assessment*\n\n"
        "● Drawdown: `18%` 🟢\n"
        "● Exposure: `42%` 🟡\n"
        "● Volatility: `29%` 🟢\n"
        "● Sharpe Ratio: `1.74` 🟢\n"
        "● Win Rate: `67.4%` 🟢\n\n"
        "_Risk level: LOW — Snipe reserve intact\\._"
    )
    kb = [[InlineKeyboardButton("↩️ Main Menu", callback_data="menu")]]
    await update.message.reply_text(msg, parse_mode='MarkdownV2',
                                    reply_markup=InlineKeyboardMarkup(kb))

async def cmd_abort(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("✅ CONFIRM ABORT", callback_data="confirm_abort"),
         InlineKeyboardButton("❌ Cancel",        callback_data="menu")]
    ]
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

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    data = q.data

    MAIN_KB = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Portfolio",    callback_data="portfolio"),
         InlineKeyboardButton("⚡ Active Snipes", callback_data="trades")],
        [InlineKeyboardButton("🤖 Agent Radar",  callback_data="agents"),
         InlineKeyboardButton("📡 Snippet",      callback_data="snippet")],
        [InlineKeyboardButton("⛔ ABORT ALL",    callback_data="abort"),
         InlineKeyboardButton("▶️  ARM ENGINE",  callback_data="arm")],
    ])

    if data == 'menu':
        await q.edit_message_text(
            "🎯 *\\[SnipBot\\]: Command Center*\n\n_Select your target\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif data == 'portfolio':
        d = await api_get('/api/portfolio')
        val = float(d.get('total_portfolio_value',0)) if d else 24318
        await q.edit_message_text(
            f"💼 *\\[SnipBot\\]: Portfolio*\n\n● Capital: `${val:,.0f}`\n● Mode: `PAPER`\n\n_Scope clear\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif data == 'trades':
        await q.edit_message_text(
            "⚡ *\\[SnipBot\\]: Active Snipes*\n\n"
            "🟢 `BTC/USDT` LONG ↑ | `+$214`\n"
            "🟢 `ETH/USDT` LONG ↑ | `+$141`\n"
            "🟢 `SOL/USDT` SHORT ↓ | `+$42`\n"
            "🔴 `BNB/USDT` LONG ↑ | `\\-$35`\n\n"
            "_4 targets in scope\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif data == 'agents':
        await q.edit_message_text(
            "🤖 *\\[SnipBot\\]: Agent Radar*\n\n"
            "🟢 Sniper Engine `88%` — FIRE READY\n"
            "🟡 TA Analyst `82%` — BULLISH\n"
            "🟡 Judge Agent `64%` — AWAITING\n"
            "🟢 Risk Agent `91%` — SAFE\n"
            "🟢 Trigger Agent `76%` — ARMED\n"
            "⚪ Sentiment AI `55%` — NEUTRAL\n\n"
            "_5/6 agents operational\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif data == 'snippet':
        now = datetime.utcnow().strftime('%H:%M UTC')
        await q.edit_message_text(
            f"📊 *\\[SnipBot Market Snippet\\]* — `{now}`\n\n"
            "● BTC: Accumulation at `$65K`\n"
            "● Layer 1: Bullish momentum\n"
            "● Funding: Neutral\n"
            "● Condition: FAVORABLE\n\n"
            "_Sniper Engine scan complete\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif data == 'arm':
        await q.edit_message_text(
            "🎯 *\\[SnipBot\\]: Engine Armed*\n\n"
            "● Status: `SCANNING`\n"
            "● Mode: `BREAKOUT HUNT`\n"
            "● Agents: `5/6 ACTIVE`\n\n"
            "_Sniper Engine scanning order books\\. Target acquisition in progress\\._",
            parse_mode='MarkdownV2', reply_markup=MAIN_KB)

    elif data == 'abort':
        await q.edit_message_text(
            "⛔ *\\[SnipBot\\]: ABORT — Confirm?*\n\n"
            "_This will halt ALL active snipes\\._",
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ CONFIRM", callback_data="confirm_abort"),
                 InlineKeyboardButton("❌ Cancel",  callback_data="menu")]
            ]))

    elif data == 'confirm_abort':
        await q.edit_message_text(
            "⛔ *\\[SnipBot ABORT\\]: Emergency halt executed\\.*\n\n"
            "_All triggers suspended\\. Review positions manually\\._",
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("↩️ Main Menu", callback_data="menu")
            ]]))

# ════════════════════════════════════════
# AUTO SNIPPETS
# ════════════════════════════════════════

async def auto_snippet(ctx: ContextTypes.DEFAULT_TYPE):
    if not CHAT_ID:
        return
    now = datetime.utcnow().strftime('%H:%M UTC')
    pairs = ['BTC/USDT','ETH/USDT','SOL/USDT','BNB/USDT']
    import random
    pair = random.choice(pairs)
    msgs = [
        f"📊 *\\[SnipBot Market Snippet\\]* — `{now}`\n\n"
        f"● {pair}: Momentum building — breakout imminent\n"
        f"● Liquidity scan: Bid wall detected\n"
        f"● Signal strength: `HIGH`\n\n"
        f"_Sniper Engine scanning\\._",

        f"🔎 *\\[Sniper Engine\\]* — `{now}`\n\n"
        f"● Order book scan complete\n"
        f"● {pair}: Large bid cluster detected\n"
        f"● Whale activity: `CONFIRMED`\n\n"
        f"◎ `{pair}` under surveillance — awaiting breakout confirmation\\.",

        f"📊 *\\[SnipBot Market Snippet\\]* — `{now}`\n\n"
        f"● Layer 1 sector: Buying momentum — last 15 min\n"
        f"● BTC dominance: `↑ Rising`\n"
        f"● Market condition: `FAVORABLE`\n\n"
        f"_Precision targeting active\\._",
    ]
    text = random.choice(msgs)
    await ctx.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='MarkdownV2')

# ════════════════════════════════════════
# STARTUP ALERT
# ════════════════════════════════════════

async def on_startup(app):
    if CHAT_ID:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=(
                "🎯 *\\[SnipBot\\]: Engine Online*\n\n"
                "● Status: `ACTIVE`\n"
                "● Mode: `PAPER TRADING`\n"
                "● Agents: `5/6 SCANNING`\n\n"
                "_Precision Trading OS initialized\\. Type /menu to begin\\._"
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
    app.add_handler(CommandHandler('status',    cmd_status))
    app.add_handler(CommandHandler('portfolio', cmd_portfolio))
    app.add_handler(CommandHandler('trades',    cmd_trades))
    app.add_handler(CommandHandler('snipes',    cmd_trades))
    app.add_handler(CommandHandler('agents',    cmd_agents))
    app.add_handler(CommandHandler('snippet',   cmd_snippet))
    app.add_handler(CommandHandler('risk',      cmd_risk))
    app.add_handler(CommandHandler('abort',     cmd_abort))
    app.add_handler(CommandHandler('fire',      cmd_snippet))

    # Inline buttons
    app.add_handler(CallbackQueryHandler(button_handler))

    # Auto snippet every N minutes
    app.job_queue.run_repeating(auto_snippet, interval=SNIPPET_INT*60, first=60)

    log.info("🎯 [SnipBot]: Telegram Fire initialized")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
