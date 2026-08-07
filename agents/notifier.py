"""
Notifier — نظام الإشعارات
Telegram + Dashboard بشخصية القناص
"""

import requests
import logging
import os
from datetime import datetime

log = logging.getLogger("Notifier")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
CHAT_ID        = os.getenv("CHAT_ID", "")
PROXY_URL      = os.getenv("PROXY_URL", "")


class Notifier:

    def send_telegram(self, message: str) -> bool:
        """إرسال رسالة Telegram"""
        if not TELEGRAM_TOKEN or not CHAT_ID:
            log.warning("[Notifier]: Telegram not configured")
            return False
        try:
            url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            resp = requests.post(url, data={
                "chat_id":    CHAT_ID,
                "text":       message,
                "parse_mode": "HTML"
            }, timeout=10)
            success = resp.status_code == 200
            if success:
                log.info("[Notifier]: Telegram sent ✅")
            return success
        except Exception as e:
            log.error(f"[Notifier]: Telegram failed — {e}")
            return False

    def format_signal(self, result: dict) -> str:
        """تنسيق رسالة الإشارة بشخصية القناص"""
        signal  = result.get("signal", "HOLD")
        symbol  = result.get("symbol", "—")
        conf    = result.get("confidence", 0)
        reason  = result.get("reason", "—")
        buy_pct = result.get("buy_pct", 0)
        sel_pct = result.get("sell_pct", 0)
        now     = datetime.utcnow().strftime("%H:%M UTC")

        emoji_map = {
            "BUY":  "🎯",
            "SELL": "⚡",
            "HOLD": "◎"
        }
        action_map = {
            "BUY":  "TARGET ACQUIRED",
            "SELL": "EXIT SIGNAL",
            "HOLD": "STANDBY"
        }

        emoji  = emoji_map.get(signal, "◎")
        action = action_map.get(signal, "STANDBY")

        # تفاصيل كل استراتيجية
        details_text = ""
        for d in result.get("details", []):
            s_name = d.get("strategy", "—")
            s_sig  = d.get("signal", "—")
            s_conf = d.get("confidence", 0)
            details_text += f"\n  • {s_name}: {s_sig} ({s_conf}%)"

        msg = (
            f"{emoji} <b>[SnipBot]: {action}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Target:</b> {symbol}\n"
            f"📊 <b>Signal:</b> {signal}\n"
            f"💯 <b>Confidence:</b> {conf:.0f}%\n"
            f"🗳 <b>Votes:</b> BUY {buy_pct:.0f}% | SELL {sel_pct:.0f}%\n"
            f"⏰ <b>Time:</b> {now}\n"
            f"\n<b>📡 Strategy Radar:</b>{details_text}\n"
            f"\n<b>📋 Reason:</b>\n{reason}\n"
            f"\n<i>◎ [SnipBot]: Precision Trading OS</i>"
        )
        return msg

    def notify_signal(self, result: dict, min_confidence: int = 65):
        """
        يرسل إشعار فقط لو الإشارة قوية
        """
        signal = result.get("signal", "HOLD")
        conf   = result.get("confidence", 0)

        if signal == "HOLD":
            return  # لا نرسل HOLD

        if conf < min_confidence:
            log.info(
                f"[Notifier]: Signal skipped — "
                f"confidence {conf}% < {min_confidence}%"
            )
            return

        msg = self.format_signal(result)
        self.send_telegram(msg)

    def send_startup(self, symbols: list, strategies: list):
        """رسالة بدء التشغيل"""
        msg = (
            "🎯 <b>[SnipBot]: System Online</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📡 <b>Strategies:</b> {' | '.join(strategies)}\n"
            f"🎯 <b>Targets:</b> {' | '.join(symbols)}\n"
            "⚡ <b>Mode:</b> Paper Trading\n"
            "◎ Precision Trading OS — Armed & Ready"
        )
        self.send_telegram(msg)

    def send_summary(self, all_results: list):
        """ملخص دوري لكل الأزواج"""
        now  = datetime.utcnow().strftime("%H:%M UTC")
        lines = [f"📊 <b>[SnipBot Market Scan]</b> — {now}\n━━━━━━━━━━━━━━━━━━━━"]

        for r in all_results:
            symbol = r.get("symbol", "—")
            signal = r.get("signal", "HOLD")
            conf   = r.get("confidence", 0)
            emoji  = "🎯" if signal == "BUY" else "⚡" if signal == "SELL" else "◎"
            lines.append(f"{emoji} {symbol}: <b>{signal}</b> ({conf:.0f}%)")

        lines.append("\n<i>◎ [SnipBot]: Precision Trading OS</i>")
        self.send_telegram("\n".join(lines))
