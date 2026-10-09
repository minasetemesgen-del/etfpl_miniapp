"""
ETFPL — FPL Weekly Contest Telegram Bot (with Mini App launcher)
-----------------------------------------------------------------
Same commands as before, now built on core.py so the bot and the Mini App
share one database and one set of rules. New: /app opens the Mini App,
and deadline reminders are sent automatically.

Normally this file is started for you by server.py (one service runs both
the website and the bot). To run ONLY the bot: python bot.py
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

import core
from config import (
    ADMIN_TELEGRAM_ID,
    BOT_TOKEN,
    ENTRY_FEE_BIRR,
    PAYMENT_CHECK_INTERVAL_SECONDS,
    WEBAPP_URL,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

EAT = timezone(timedelta(hours=3))  # East Africa Time (Ethiopia)


def fmt_deadline(deadline):
    return deadline.astimezone(EAT).strftime("%a %d %b, %H:%M EAT")


def app_keyboard(label="🚀 Open ETFPL App"):
    if not WEBAPP_URL:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, web_app=WebAppInfo(url=WEBAPP_URL))]])


def is_admin(update: Update) -> bool:
    return update.effective_user.id == ADMIN_TELEGRAM_ID


# ---------------------------------------------------------------------------
# User commands
# ---------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome to the FPL Weekly Contest! 🏆\n\n"
        f"Entry fee: {ENTRY_FEE_BIRR} birr per gameweek. Highest scorer that "
        "gameweek wins the prize.\n\n"
        "Tap the button below for the full app — leaderboard, league table, "
        "fixtures, your team and transfers.\n\n"
        "Or use commands:\n"
        "/register <your_FPL_team_id> - link your FPL team\n"
        "/pay - get your payment link (Telebirr, CBE Birr, or card)\n"
        "/mystatus - check your registration & payment status\n"
        "/leaderboard - see this gameweek's top 10\n"
        "/app - open the Mini App\n\n"
        "Payments confirm automatically within about a minute — no need to "
        "message anyone.",
        reply_markup=app_keyboard(),
    )


async def open_app(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not WEBAPP_URL:
        await update.message.reply_text("The Mini App isn't set up yet — WEBAPP_URL is missing.")
        return
    await update.message.reply_text("Here's the app 👇", reply_markup=app_keyboard())


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Usage: /register <fpl_team_id>\n\n"
            "Find your team ID in the URL when you open 'Points' on the "
            "official FPL site, e.g. .../entry/1234567/event/1 → 1234567 is your ID."
        )
        return
    try:
        team_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("That doesn't look like a valid numeric team ID.")
        return

    try:
        info = await asyncio.to_thread(core.fetch_team_info, team_id)
    except Exception:
        logger.exception("FPL team lookup failed")
        await update.message.reply_text("Couldn't reach the FPL servers just now — please try again in a moment.")
        return
    if info is None:
        await update.message.reply_text("I couldn't find an FPL team with that ID. Please double-check it.")
        return

    user = update.effective_user
    core.register_user(user.id, user.username or user.first_name, team_id, info["name"])
    await update.message.reply_text(
        f"✅ Registered! \"{info['name']}\" (ID {team_id}) is linked.\nNow run /pay to enter this gameweek.",
        reply_markup=app_keyboard(),
    )


async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        result = await asyncio.to_thread(core.start_payment, user.id, user.first_name, user.last_name)
    except core.ContestError as e:
        await update.message.reply_text(e.message)
        return
    except Exception:
        logger.exception("start_payment failed")
        await update.message.reply_text("Sorry, something went wrong — please try again in a moment.")
        return

    await update.message.reply_text(
        f"💰 Entry fee: {ENTRY_FEE_BIRR} birr for Gameweek {result['gameweek']}\n"
        f"⏰ Entries close {fmt_deadline(result['deadline'])}\n\n"
        f"Tap to pay (Telebirr, CBE Birr, or card):\n{result['checkout_url']}\n\n"
        "Once payment completes, you'll be entered automatically within a "
        "minute — no need to do anything else. Check /mystatus anytime."
    )


async def check_pending_payments(context: ContextTypes.DEFAULT_TYPE):
    """Background job: automatically verifies all pending payments with Chapa
    and confirms entries with zero admin involvement."""
    pending = core.db_execute(
        "SELECT telegram_id, gameweek, tx_reference FROM entries WHERE paid=0 AND tx_reference IS NOT NULL",
        fetch=True,
    )
    for telegram_id, gw, tx_ref in pending:
        try:
            if await asyncio.to_thread(core.verify_payment, tx_ref) and core.mark_paid(telegram_id, gw):
                core.add_notification(
                    telegram_id, "payment", "Payment confirmed ✅",
                    f"You're entered in Gameweek {gw}. Good luck!",
                )
                await context.bot.send_message(
                    telegram_id,
                    f"✅ Payment confirmed automatically! You're entered in GW{gw}. Good luck!",
                    reply_markup=app_keyboard("📊 Open app"),
                )
                logger.info(f"Auto-confirmed payment for {telegram_id}, GW{gw}")
        except Exception:
            logger.exception(f"Payment verify failed for tx_ref {tx_ref}")


async def deadline_reminders(context: ContextTypes.DEFAULT_TYPE):
    """Background job: reminds registered users who haven't entered yet, once
    ~24h and once ~3h before the FPL deadline. Users can switch this off in
    the app (🔔 → Deadline reminders)."""
    try:
        window = await asyncio.to_thread(core.get_entry_window)
    except Exception:
        logger.exception("Reminder job: could not read FPL deadline")
        return
    if not window:
        return

    gw = window["gameweek"]
    hours_left = (window["deadline"] - datetime.now(timezone.utc)).total_seconds() / 3600
    kind = 3 if hours_left <= 3 else 24 if hours_left <= 24 else None
    if kind is None:
        return

    label = "less than 3 hours" if kind == 3 else "less than 24 hours"
    title = f"GW{gw} entries close soon"
    body = f"{label.capitalize()} left to enter Gameweek {gw} ({fmt_deadline(window['deadline'])})."
    for telegram_id in core.reminder_targets(gw, kind):
        core.add_notification(telegram_id, "deadline", title, body)
        core.mark_reminded(telegram_id, gw, kind)
        try:
            await context.bot.send_message(
                telegram_id,
                f"⏰ {title}\n{body}\n\nYou can switch these reminders off in the app (🔔).",
                reply_markup=app_keyboard("Enter now"),
            )
        except Exception:
            logger.warning("Could not send reminder to %s", telegram_id)


async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    me = core.get_user(user.id)
    if not me:
        await update.message.reply_text("You haven't registered yet. Use /register <fpl_team_id>.")
        return
    try:
        window = await asyncio.to_thread(core.get_entry_window)
    except Exception:
        await update.message.reply_text("Couldn't reach the FPL servers just now — please try again in a moment.")
        return

    team = f"{me['team_name']} (ID {me['team_id']})" if me["team_name"] else f"ID {me['team_id']}"
    if not window:
        await update.message.reply_text(f"FPL Team: {team}\nNo gameweek is open for entries right now.")
        return

    gw = window["gameweek"]
    entry = core.get_entry(user.id, gw)
    status = "Not entered this gameweek yet — run /pay."
    if entry:
        status = (
            "✅ Payment confirmed, you're entered!"
            if entry["paid"]
            else "⏳ Waiting for payment to complete — check back in a minute after paying."
        )
    await update.message.reply_text(
        f"FPL Team: {team}\nGameweek {gw} (closes {fmt_deadline(window['deadline'])}):\n{status}",
        reply_markup=app_keyboard(),
    )


async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        gw = await asyncio.to_thread(core.get_live_gameweek)
        results = await asyncio.to_thread(core.contest_leaderboard, gw)
    except Exception:
        logger.exception("leaderboard failed")
        await update.message.reply_text("Couldn't reach the FPL servers just now — please try again in a moment.")
        return
    if not results:
        await update.message.reply_text(f"No confirmed entries yet for GW{gw}.")
        return

    lines = [f"📊 Gameweek {gw} — Top 10"]
    for r in results[:10]:
        lines.append(f"{r['rank']}. {r['username']} — {r['points']} pts")
    me = next((r for r in results if r["telegram_id"] == update.effective_user.id), None)
    if me and me["rank"] > 10:
        lines.append(f"…\n{me['rank']}. You — {me['points']} pts")
    await update.message.reply_text("\n".join(lines), reply_markup=app_keyboard("See full leaderboard"))


# ---------------------------------------------------------------------------
# Admin commands
# ---------------------------------------------------------------------------
async def announce_winner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Admins only.")
        return
    try:
        gw = int(context.args[0]) if context.args else await asyncio.to_thread(core.get_live_gameweek)
        results = await asyncio.to_thread(core.contest_leaderboard, gw, 0)  # fresh scores
    except Exception:
        logger.exception("announcewinner failed")
        await update.message.reply_text("Couldn't fetch scores just now — please try again in a moment.")
        return
    if not results:
        await update.message.reply_text(f"No confirmed entries for GW{gw}.")
        return

    winner = results[0]
    total_pot = len(results) * ENTRY_FEE_BIRR
    prize = total_pot * core.PRIZE_SHARE
    # If you've set a prize (e.g. "PlayStation 5") the winner is told that;
    # otherwise they're told the cash amount.
    prize_text = core.get_prize()["text"] or f"{prize:.0f} birr"

    await update.message.reply_text(
        f"🏆 GW{gw} Winner: {winner['username']} with {winner['points']} points!\n"
        f"Pot: {total_pot} birr → 50% cash: {prize:.0f} birr\n"
        f"Prize announced to the winner: {prize_text}"
    )
    await context.bot.send_message(
        winner["telegram_id"],
        f"🎉 Congrats! You won GW{gw} with {winner['points']} points. Prize: {prize_text}!",
    )
    # Everyone who entered also gets it in their in-app notifications.
    for r in results:
        core.add_notification(
            r["telegram_id"], "winner", f"GW{gw} winner: {winner['username']}",
            f"{winner['username']} won with {winner['points']} points. You finished #{r['rank']} with {r['points']}.",
        )


PRIZE_HELP = (
    "🎁 How to change the prize shown in the app:\n\n"
    "• Text only:  /setprize PlayStation 5\n"
    "• Picture + text: send a picture and write the caption  /setprize PlayStation 5\n"
    "  (tip: send it as a File instead of a Photo to keep a transparent PNG sharp)\n"
    "• Remove everything:  /clearprize"
)


def _prize_status():
    p = core.get_prize()
    return f"Now showing: {p['text'] or '(no text)'} · picture: {'yes' if p['has_image'] else 'no'}"


async def set_prize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Admins only.")
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text(f"{PRIZE_HELP}\n\n{_prize_status()}")
        return
    shown = core.set_prize_text(text)
    await update.message.reply_text(f"✅ Prize text updated to: {shown}\n{_prize_status()}")


async def set_prize_picture(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A picture (or image file) whose caption starts with /setprize."""
    if not is_admin(update):
        return
    msg = update.message
    caption = re.sub(r"^/setprize(@\w+)?", "", msg.caption or "").strip()
    try:
        if msg.photo:
            tg_file, mime = await msg.photo[-1].get_file(), "image/jpeg"
        else:
            doc = msg.document
            if doc.file_size and doc.file_size > core.MAX_PRIZE_IMAGE_BYTES:
                raise core.ContestError("too_big", "That picture is too big — please keep it under 5 MB.")
            tg_file, mime = await doc.get_file(), doc.mime_type or "image/png"
        data = bytes(await tg_file.download_as_bytearray())
        core.save_prize_image(data, mime)
    except core.ContestError as e:
        await update.message.reply_text(e.message)
        return
    except Exception:
        logger.exception("Prize picture upload failed")
        await update.message.reply_text("Couldn't save that picture — please try again.")
        return
    if caption:
        core.set_prize_text(caption)
    await update.message.reply_text(f"✅ Prize picture updated.\n{_prize_status()}")


async def clear_prize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        await update.message.reply_text("Admins only.")
        return
    core.clear_prize()
    await update.message.reply_text("🧹 Prize text and picture removed. The app now shows “To be announced”.")


# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------
def build_application():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("app", open_app))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("pay", pay))
    app.add_handler(CommandHandler("mystatus", my_status))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("announcewinner", announce_winner))
    app.add_handler(CommandHandler("setprize", set_prize))
    app.add_handler(CommandHandler("clearprize", clear_prize))
    app.add_handler(
        MessageHandler(
            filters.CaptionRegex(r"^/setprize") & (filters.PHOTO | filters.Document.IMAGE),
            set_prize_picture,
        )
    )

    # Automatically checks Chapa for completed payments in the background —
    # this is what makes confirmation fully automatic, no admin needed.
    app.job_queue.run_repeating(check_pending_payments, interval=PAYMENT_CHECK_INTERVAL_SECONDS, first=10)
    app.job_queue.run_repeating(deadline_reminders, interval=600, first=60)
    return app


def main():
    core.init_db()
    app = build_application()
    logger.info("Bot starting (bot only)...")
    app.run_polling()


if __name__ == "__main__":
    main()
