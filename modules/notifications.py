import json
import logging
import threading
import urllib.request
from datetime import datetime, timezone
from modules.config import get_config

def send_telegram_alert(message, parse_mode="HTML"):
    try:
        cfg = get_config()
        tg = cfg.get("notifications", {}).get("telegram", {})
        if not tg.get("enabled"):
            return False, "Telegram notifications disabled in settings"
        bot_token = tg.get("bot_token", "").strip()
        chat_id = tg.get("chat_id", "").strip()
        if not bot_token or not chat_id:
            return False, "Telegram Bot Token or Chat ID not configured"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200, "Sent"
    except Exception as e:
        logging.error(f"Telegram notification error: {e}")
        return False, str(e)

def send_discord_alert(title, description, fields=None, color=0x10B981):
    try:
        cfg = get_config()
        dc = cfg.get("notifications", {}).get("discord", {})
        if not dc.get("enabled"):
            return False, "Discord notifications disabled in settings"
        webhook_url = dc.get("webhook_url", "").strip()
        if not webhook_url:
            return False, "Discord Webhook URL not configured"

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": "NF-Sawava Suite Ultra • Alert System"}
        }
        if fields:
            embed["fields"] = fields

        payload = json.dumps({
            "username": "NF-Sawava Notifier",
            "embeds": [embed]
        }).encode("utf-8")

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "NF-Sawava-Notifier/2.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status in (200, 204), "Sent"
    except Exception as e:
        logging.error(f"Discord notification error: {e}")
        return False, str(e)

def dispatch_live_notification(*args, **kwargs):
    if len(args) == 1 and isinstance(args[0], dict):
        d = args[0]
        service = kwargs.get("service") or d.get("service") or "Unknown"
        email = d.get("email") or d.get("user") or d.get("account") or "-"
        plan = d.get("plan") or d.get("product") or d.get("status_text") or "-"
        country = d.get("country") or "-"
        route = d.get("route") or "Direct"
    elif len(args) >= 2 and isinstance(args[0], dict):
        d = args[0]
        service = args[2] if len(args) > 2 else (kwargs.get("service") or d.get("service") or "Unknown")
        email = d.get("email") or d.get("user") or "-"
        plan = d.get("plan") or d.get("product") or "-"
        country = d.get("country") or "-"
        route = d.get("route") or "Direct"
    else:
        service = args[0] if len(args) > 0 else kwargs.get("service", "Unknown")
        email = args[1] if len(args) > 1 else kwargs.get("email", "-")
        plan = args[2] if len(args) > 2 else kwargs.get("plan", "-")
        country = args[3] if len(args) > 3 else kwargs.get("country", "-")
        route = args[4] if len(args) > 4 else kwargs.get("route", "Direct")

    def _run():
        try:
            cfg = get_config()
            notifs = cfg.get("notifications", {})
            tg = notifs.get("telegram", {})
            dc = notifs.get("discord", {})

            if not (tg.get("enabled") and tg.get("notify_on_live", True)) and not (dc.get("enabled") and dc.get("notify_on_live", True)):
                return

            masked_email = email
            if email and "@" in email:
                u, d = email.split("@", 1)
                masked_u = (u[:2] + "****" + u[-1:]) if len(u) > 3 else (u[:1] + "***")
                masked_email = f"{masked_u}@{d}"

            is_4k = bool(plan and ("4K" in plan or "Ultra" in plan or "Premium" in plan))
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. Telegram
            if tg.get("enabled") and tg.get("notify_on_live", True):
                badge = "🎬 <b>[ULTRA HD 4K HIT!]</b>" if is_4k else "🎉 <b>[LIVE ACCOUNT HIT!]</b>"
                msg = (
                    f"{badge}\n\n"
                    f"• <b>Layanan:</b> {service.upper()}\n"
                    f"• <b>Email:</b> <code>{masked_email}</code>\n"
                    f"• <b>Plan:</b> {plan or '-'}\n"
                    f"• <b>Negara:</b> {country or '-'}\n"
                    f"• <b>Route:</b> {route or 'Direct'}\n"
                    f"• <b>Waktu:</b> {now_str}"
                )
                send_telegram_alert(msg)

            # 2. Discord
            if dc.get("enabled") and dc.get("notify_on_live", True):
                color = 0xE50914 if is_4k else 0x10B981
                title = f"🎬 [4K HIT] {service.upper()} Account Live!" if is_4k else f"🎉 {service.upper()} Account Live!"
                fields = [
                    {"name": "Service", "value": service.upper(), "inline": True},
                    {"name": "Plan", "value": plan or "Active", "inline": True},
                    {"name": "Country", "value": country or "-", "inline": True},
                    {"name": "Email", "value": f"`{masked_email}`", "inline": True},
                    {"name": "Route", "value": route or "Direct", "inline": True},
                    {"name": "Checked At", "value": now_str, "inline": True}
                ]
                send_discord_alert(title, "Akun berstatus LIVE berhasil ditemukan oleh NF-Sawava Suite.", fields=fields, color=color)
        except Exception as e:
            logging.error(f"Error in dispatch_live_notification: {e}")

    threading.Thread(target=_run, daemon=True).start()

def dispatch_bulk_notification(summary):
    def _run():
        try:
            cfg = get_config()
            notifs = cfg.get("notifications", {})
            tg = notifs.get("telegram", {})
            dc = notifs.get("discord", {})

            if not (tg.get("enabled") and tg.get("notify_on_bulk_finish", True)) and not (dc.get("enabled") and dc.get("notify_on_bulk_finish", True)):
                return

            total = summary.get("total", 0)
            live = summary.get("live", 0)
            four_k = summary.get("four_k", 0)
            hold = summary.get("hold", 0)
            dead = summary.get("dead", 0)
            dur = summary.get("duration", "-")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 1. Telegram
            if tg.get("enabled") and tg.get("notify_on_bulk_finish", True):
                msg = (
                    f"🏁 <b>[NF-Sawava] Bulk Check Selesai!</b>\n\n"
                    f"• <b>Total Diperiksa:</b> {total} akun\n"
                    f"• <b>✅ LIVE:</b> {live} (🎬 4K: {four_k})\n"
                    f"• <b>⏸ HOLD:</b> {hold}\n"
                    f"• <b>💀 DEAD:</b> {dead}\n"
                    f"• <b>Durasi:</b> {dur}\n"
                    f"• <b>Waktu:</b> {now_str}"
                )
                send_telegram_alert(msg)

            # 2. Discord
            if dc.get("enabled") and dc.get("notify_on_bulk_finish", True):
                fields = [
                    {"name": "Total Checked", "value": str(total), "inline": True},
                    {"name": "✅ LIVE", "value": f"{live} (🎬 {four_k} 4K)", "inline": True},
                    {"name": "⏸ HOLD", "value": str(hold), "inline": True},
                    {"name": "💀 DEAD", "value": str(dead), "inline": True},
                    {"name": "Duration", "value": str(dur), "inline": True},
                    {"name": "Finished At", "value": now_str, "inline": True}
                ]
                send_discord_alert(
                    "🏁 [Bulk Check Selesai]",
                    "Proses pengecekan massal telah selesai dijalankan.",
                    fields=fields,
                    color=0x3B82F6
                )
        except Exception as e:
            logging.error(f"Error in dispatch_bulk_notification: {e}")

    threading.Thread(target=_run, daemon=True).start()
