import os

# ---------------------------------------------------------------------------
# Everything is read from environment variables (safer for hosting — your
# token never sits in plain text in your code or on GitHub).
#
# ON RAILWAY: go to your project -> Variables tab -> add each of these:
#   BOT_TOKEN
#   ADMIN_TELEGRAM_ID
#   CHAPA_SECRET_KEY
#   WEBAPP_URL              (the public https URL of this service — see README)
#   DB_PATH                 (optional, e.g. /data/fpl_contest.db with a volume)
#   ENTRY_FEE_BIRR          (optional, defaults to 100)
# ---------------------------------------------------------------------------

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError(
        "BOT_TOKEN is not set. Add it as an environment variable "
        "(Railway: Project -> Variables -> BOT_TOKEN)."
    )

_admin_id = os.environ.get("ADMIN_TELEGRAM_ID")
if not _admin_id:
    raise ValueError(
        "ADMIN_TELEGRAM_ID is not set. Add it as an environment variable "
        "(Railway: Project -> Variables -> ADMIN_TELEGRAM_ID)."
    )
ADMIN_TELEGRAM_ID = int(_admin_id)

ENTRY_FEE_BIRR = int(os.environ.get("ENTRY_FEE_BIRR", "100"))

PAYMENT_INSTRUCTIONS = os.environ.get(
    "PAYMENT_INSTRUCTIONS",
    "Send 100 birr via Telebirr to 09XXXXXXXX (Your Name)\n"
    "or bank transfer to Account: XXXXXXXXXX, Bank Name, Your Name.\n"
    "Then copy the transaction ID/reference from the confirmation SMS.",
)

# ---------------------------------------------------------------------------
# Chapa payment gateway — enables fully automatic payment verification.
# Sign up free at https://dashboard.chapa.co, then go to Settings -> API Keys
# to get your secret key. Use the TEST key while trying things out (starts
# with CHASECK_TEST-), then switch to the LIVE key once ready for real money.
# ---------------------------------------------------------------------------
CHAPA_SECRET_KEY = os.environ.get("CHAPA_SECRET_KEY")
if not CHAPA_SECRET_KEY:
    raise ValueError(
        "CHAPA_SECRET_KEY is not set. Add it as an environment variable "
        "(Railway: Project -> Variables -> CHAPA_SECRET_KEY). Get it free "
        "at https://dashboard.chapa.co"
    )

# Where Chapa sends the user back after paying — doesn't need to be a real
# website, this is fine as a default since the app checks payment status
# itself rather than relying on this page.
CHAPA_RETURN_URL = os.environ.get("CHAPA_RETURN_URL", "https://t.me/share")

# How often (in seconds) the bot checks Chapa for payment confirmations.
PAYMENT_CHECK_INTERVAL_SECONDS = int(os.environ.get("PAYMENT_CHECK_INTERVAL_SECONDS", "30"))

# ---------------------------------------------------------------------------
# Mini App settings
# ---------------------------------------------------------------------------
# Public HTTPS address of this service, e.g. https://etfpl-production.up.railway.app
# Telegram requires HTTPS. Leave empty to skip the menu button / "Open app" buttons.
WEBAPP_URL = os.environ.get("WEBAPP_URL", "").rstrip("/")

# DEV_MODE=1 lets you open the app in a normal browser with ?dev=<any number>
# (no Telegram needed). NEVER enable this on the live server.
DEV_MODE = os.environ.get("DEV_MODE", "0") == "1"

# Set RUN_BOT=0 to run only the website/API (handy for UI work).
RUN_BOT = os.environ.get("RUN_BOT", "1") == "1"
