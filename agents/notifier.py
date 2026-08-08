"""
SnipBot — Telegram Notifier
-----------------------------
Sends sniper-personality alerts to Telegram channel/chat.
Uses python-telegram-bot v20 (async).
All message formats follow SNIPBOT_INSTRUCTIONS.md mandatory format.
"""

import logging
import asyncio
from typing import Optional
from telegram import Bot
from telegram.error import TelegramError

from strategies.base_strategy import Signal

log = logging.getLogger("SnipBot.Notifier")


class Notifier:

    def __init__(self, token: str, chat_id: str):
        if not token or not chat_id:
            raise ValueError("TELEGRAM_TOKEN and TELEGRAM_CHAT_ID are required")
        self.bot     = Bot(token=token)
        self.chat_id = chat_id

    async def send(self, text: str) -> bool:
        """Send raw message to Telegram."""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode="HTML",
            )
            return True
        except TelegramError as e:
            log.error(f"[Notifier] Telegram send failed: {e}")
            return False

    # ── Mandatory SnipBot message formats ─────────────────────────────────────

    async def target_acquired(self, signal: Signal) -> bool:
        """🎯 Target acquired alert — BUY signal."""
        price_str = f"${signal.entry_price:,.2f}" if signal.entry_price else "market"
        sl_str    = f"${signal.stop_loss:,.2f}"   if signal.stop_loss   else "—"
        tp_str    = f"${signal.take_profit:,.2f}" if signal.take_profit else "—"

        msg = (
            f"🎯 <b>[SnipBot]</b>: Target acquired on <b>{signal.pair}</b>.\n"
            f"Price at major support. Liquidity scan complete. Trigger armed.\n\n"
            f"<b>Entry:</b> {price_str}\n"
            f"<b>Stop Loss:</b> {sl_str}\n"
            f"<b>Take Profit:</b> {tp_str}\n"
            f"<b>Confidence:</b> {signal.confidence:.1f}%\n"
            f"<b>Agent:</b> {signal.strategy}\n\n"
            f"<i>{signal.reason[:120]}</i>"
        )
        return await self.send(msg)

    async def execution_fired(self, signal: Signal, side: str, price: float) -> bool:
        """⚡ Execution alert — order fired."""
        msg = (
            f"⚡ <b>[SnipBot Execution]</b>: "
            f"<b>{signal.pair}</b> {side} fired @ <b>${price:,.2f}</b>.\n"
            f"Agent: {signal.strategy}. "
            f"Confidence: {signal.confidence:.1f}%."
        )
        return await self.send(msg)

    async def abort(self) -> bool:
        """⛔ Emergency abort alert."""
        msg = (
            "⛔ <b>[SnipBot ABORT]</b>: Emergency halt executed. "
            "All triggers suspended."
        )
        return await self.send(msg)

    async def tracking(self, pair: str) -> bool:
        """◎ Surveillance alert — no trigger yet."""
        msg = (
            f"◎ <b>[SnipBot Tracking]</b>: <b>{pair}</b> under surveillance "
            f"— awaiting breakout confirmation."
        )
        return await self.send(msg)

    async def scan_summary(self, scanned: int, signals: int, pairs: list) -> bool:
        """🔎 Scan complete summary."""
        pairs_str = " · ".join(pairs) if pairs else "none"
        msg = (
            f"🔎 <b>[Sniper Engine]</b>: Order book scan complete.\n"
            f"Pairs scanned: <b>{scanned}</b> · "
            f"Signals found: <b>{signals}</b>\n"
            f"Active: {pairs_str}"
        )
        return await self.send(msg)

    async def market_snippet(self, sector: str, momentum: str, timeframe: str) -> bool:
        """📊 Market snippet alert."""
        msg = (
            f"📊 <b>[SnipBot Market Snippet]</b>: "
            f"{sector} showing <b>{momentum}</b> over last {timeframe}."
        )
        return await self.send(msg)

    async def sell_signal(self, signal: Signal) -> bool:
        """🎯 SELL/exit signal alert."""
        price_str = f"${signal.entry_price:,.2f}" if signal.entry_price else "market"
        msg = (
            f"🎯 <b>[SnipBot]</b>: Exit trigger on <b>{signal.pair}</b>.\n"
            f"Price: {price_str} · "
            f"Confidence: {signal.confidence:.1f}% · "
            f"Agent: {signal.strategy}\n\n"
            f"<i>{signal.reason[:120]}</i>"
        )
        return await self.send(msg)
