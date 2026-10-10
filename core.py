"""
Shared logic used by BOTH the Telegram bot and the Mini App API:
database, FPL API access (with caching), Chapa payments, notifications and
the contest leaderboard. Keeping it in one place means the bot and the app
can never disagree about who is entered or who is winning.
"""

import logging
import os
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests

from config import CHAPA_RETURN_URL, CHAPA_SECRET_KEY, ENTRY_FEE_BIRR

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "fpl_contest.db")
PRIZE_SHARE = 0.5  # winner gets 50% of the pot

FPL_API = "https://fantasy.premierleague.com/api"
CHAPA_INITIALIZE_URL = "https://api.chapa.co/v1/transaction/initialize"
CHAPA_VERIFY_URL = "https://api.chapa.co/v1/transaction/verify/{tx_ref}"

HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "Mozilla/5.0 (compatible; ETFPL-MiniApp/1.0)"})


class ContestError(Exception):
    """A problem the user should be told about in plain words."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def _connect():
    return sqlite3.connect(DB_PATH, timeout=15)


def init_db():
    folder = os.path.dirname(DB_PATH)
    if folder:
        os.makedirs(folder, exist_ok=True)
    conn = _connect()
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute(
        """CREATE TABLE IF NOT EXISTS users (
            telegram_id INTEGER PRIMARY KEY,
            username TEXT,
            fpl_team_id INTEGER
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS entries (
            telegram_id INTEGER,
            gameweek INTEGER,
            paid INTEGER DEFAULT 0,
            tx_reference TEXT,
            PRIMARY KEY (telegram_id, gameweek)
        )"""
    )
    # Added for the Mini App — safe to run on an existing database.
    try:
        c.execute("ALTER TABLE users ADD COLUMN team_name TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    c.execute(
        """CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL,
            kind TEXT,
            title TEXT,
            body TEXT,
            created_at INTEGER,
            is_read INTEGER DEFAULT 0
        )"""
    )
    c.execute("CREATE INDEX IF NOT EXISTS idx_notif_user ON notifications (telegram_id, id)")
    c.execute(
        """CREATE TABLE IF NOT EXISTS settings (
            telegram_id INTEGER PRIMARY KEY,
            notify_deadline INTEGER DEFAULT 1
        )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS reminders_sent (
            telegram_id INTEGER,
            gameweek INTEGER,
            kind INTEGER,
            PRIMARY KEY (telegram_id, gameweek, kind)
        )"""
    )
    conn.commit()
    conn.close()


def db_execute(query, params=(), fetch=False, fetchone=False):
    conn = _connect()
    try:
        c = conn.cursor()
        c.execute(query, params)
        result = None
        if fetchone:
            result = c.fetchone()
        elif fetch:
            result = c.fetchall()
        conn.commit()
        return result
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# FPL API (cached so many users don't hammer the official servers)
# ---------------------------------------------------------------------------
_cache = {}
_cache_lock = threading.Lock()


def fpl_get(path, ttl=60):
    """GET a path on the FPL API. Results are cached for `ttl` seconds, and if
    FPL is briefly down we serve the last good copy instead of failing."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(path)
    if hit and now - hit[0] < ttl:
        return hit[1]
    try:
        resp = HTTP.get(f"{FPL_API}/{path}", timeout=12)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        if hit:
            logger.warning("FPL request failed for %s, serving stale copy", path)
            return hit[1]
        raise
    with _cache_lock:
        _cache[path] = (now, data)
    return data


def bootstrap():
    return fpl_get("bootstrap-static/", 60)


def parse_deadline(value):
    # FPL gives ISO 8601 UTC, e.g. "2026-10-17T10:00:00Z"
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def get_live_gameweek():
    """The gameweek whose scores are being played / were just played
    (FPL's 'current' event). Used for leaderboards and winners."""
    events = bootstrap()["events"]
    for event in events:
        if event["is_current"]:
            return event["id"]
    for event in events:
        if event["is_next"]:
            return event["id"]
    return None


def get_entry_window():
    """The gameweek that is OPEN for entries right now: the first one whose
    FPL deadline is still in the future. Returns {"gameweek", "deadline"} or
    None if the season is over.

    Entries close at FPL's own deadline — the moment squads lock — so nobody
    can watch live scores and only pay once they know they're winning."""
    now = datetime.now(timezone.utc)
    for event in bootstrap()["events"]:
        deadline = parse_deadline(event["deadline_time"])
        if deadline > now:
            return {"gameweek": event["id"], "deadline": deadline}
    return None


def _history_score(team_id, gameweek):
    """Official score from FPL's history. Only filled in once a gameweek has finished."""
    try:
        data = fpl_get(f"entry/{team_id}/history/", 60)
    except Exception:
        return None
    for row in data.get("current", []):
        if row["event"] == gameweek:
            return row["points"]
    return None


def _live_score(team_id, gameweek):
    """Running score while a gameweek is being played: each starter's live
    points x multiplier (captain), with automatic substitutions applied.
    Returns None if FPL has no picks/live data yet."""
    try:
        live = fpl_get(f"event/{gameweek}/live/", 45)
        picks = fpl_get(f"entry/{team_id}/event/{gameweek}/picks/", 45)
    except Exception:
        return None
    pts = {e["id"]: e["stats"]["total_points"] for e in live.get("elements", [])}
    chip = picks.get("active_chip")
    weights = {}
    for p in picks["picks"]:
        if p["position"] <= 11:
            weights[p["element"]] = p["multiplier"]
        elif chip == "bboost":
            weights[p["element"]] = 1
    for sub in picks.get("automatic_subs") or []:
        weights.pop(sub["element_out"], None)
        weights[sub["element_in"]] = 1
    return sum(pts.get(el, 0) * w for el, w in weights.items())


def get_gameweek_score(team_id, gameweek):
    """A team's points for a gameweek (live while it's being played, official
    once finished), or None if unavailable."""
    try:
        event = next((e for e in bootstrap()["events"] if e["id"] == gameweek), None)
    except Exception:
        event = None
    if event and not event.get("finished"):
        score = _live_score(team_id, gameweek)
        if score is not None:
            return score
    return _history_score(team_id, gameweek)


_lb_cache = {}
_lb_lock = threading.Lock()


def contest_leaderboard(gameweek, ttl=45):
    """Everyone with a confirmed entry for `gameweek`, ranked by FPL points.
    Ties share a rank. Cached briefly because scores come from the FPL API."""
    now = time.time()
    with _lb_lock:
        hit = _lb_cache.get(gameweek)
    if ttl and hit and now - hit[0] < ttl:
        return hit[1]

    rows = db_execute(
        "SELECT u.telegram_id, u.username, u.fpl_team_id, u.team_name FROM entries e "
        "JOIN users u ON u.telegram_id = e.telegram_id WHERE e.gameweek=? AND e.paid=1",
        (gameweek,),
        fetch=True,
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        scores = list(pool.map(lambda r: get_gameweek_score(r[2], gameweek), rows))

    results = []
    for (tid, username, team_id, team_name), score in zip(rows, scores):
        results.append(
            {
                "telegram_id": tid,
                "username": username or "Player",
                "team_id": team_id,
                "team_name": team_name,
                "points": score if score is not None else 0,
            }
        )
    results.sort(key=lambda r: (-r["points"], r["username"].lower()))
    for i, r in enumerate(results):
        r["rank"] = results[i - 1]["rank"] if i and results[i - 1]["points"] == r["points"] else i + 1

    with _lb_lock:
        _lb_cache[gameweek] = (now, results)
    return results
