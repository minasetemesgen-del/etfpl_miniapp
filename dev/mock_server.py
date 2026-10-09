"""
Run the Mini App on your own computer WITHOUT Telegram, the real FPL servers
or Chapa. Everything is fake data, so you can click through every screen.

    pip install -r requirements.txt
    python dev/mock_server.py
    open http://localhost:8000/?dev=888      (a registered player)
    open http://localhost:8000/?dev=777      (a brand-new player)
    open http://localhost:8000/?dev=889      (a player ranked outside the Top 10)

This file is for testing only — never deploy it.
"""

import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- fake settings (set BEFORE importing the app) --------------------------
os.environ.setdefault("BOT_TOKEN", "123456:TEST-TOKEN")
os.environ.setdefault("ADMIN_TELEGRAM_ID", "1")
os.environ.setdefault("CHAPA_SECRET_KEY", "CHASECK_TEST-fake")
os.environ.setdefault("DEV_MODE", "1")
os.environ.setdefault("RUN_BOT", "0")
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(), "mock.db"))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

import core  # noqa: E402
import fpl_views  # noqa: E402

NOW = datetime.now(timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"
CURRENT_GW = 7

TEAM_NAMES = [
    ("Arsenal", "ARS", 3), ("Aston Villa", "AVL", 7), ("Bournemouth", "BOU", 91), ("Brentford", "BRE", 94),
    ("Brighton", "BHA", 36), ("Chelsea", "CHE", 8), ("Crystal Palace", "CRY", 31), ("Everton", "EVE", 11),
    ("Fulham", "FUL", 54), ("Leeds", "LEE", 2), ("Liverpool", "LIV", 14), ("Man City", "MCI", 43),
    ("Man Utd", "MUN", 1), ("Newcastle", "NEW", 4), ("Nott'm Forest", "NFO", 17), ("Spurs", "TOT", 6),
    ("Sunderland", "SUN", 56), ("West Ham", "WHU", 21), ("Wolves", "WOL", 39), ("Burnley", "BUR", 90),
]
SYL = ["ka", "ro", "ma", "len", "do", "vi", "sa", "tur", "bel", "ni", "mo", "ar", "gus", "ten", "ber", "ko", "li", "san"]


def _rng(*seed):
    return random.Random("-".join(map(str, seed)))


# --- teams, players ---------------------------------------------------------
TEAMS = [{"id": i + 1, "name": n, "short_name": s, "code": c} for i, (n, s, c) in enumerate(TEAM_NAMES)]

ELEMENTS = []
for pid in range(1, 151):
    r = _rng("el", pid)
    etype = 1 if pid <= 20 else 2 if pid <= 70 else 3 if pid <= 120 else 4
    name = (r.choice(SYL) + r.choice(SYL) + r.choice(["", "o", "ez", "son"])).capitalize()
    ELEMENTS.append({
        "id": pid, "web_name": name, "element_type": etype, "team": r.randint(1, 20), "code": 100000 + pid,
        "now_cost": r.randint(40, 135), "event_points": r.choice([0, 1, 2, 2, 3, 5, 6, 8, 9, 12]),
        "status": r.choice(["a"] * 12 + ["d", "i"]), "news": "Knock - 75% chance of playing",
        "transfers_in_event": r.randint(1000, 600000), "transfers_out_event": r.randint(1000, 500000),
    })

# --- events (gameweeks) -------------------------------------------------------
GW8_DEADLINE = NOW + timedelta(days=2, hours=4)
EVENTS = []
for gw in range(1, 39):
    deadline = GW8_DEADLINE + timedelta(days=7 * (gw - 8))
    EVENTS.append({
        "id": gw, "deadline_time": deadline.strftime(ISO),
        "is_current": gw == CURRENT_GW, "is_next": gw == CURRENT_GW + 1, "is_previous": gw == CURRENT_GW - 1,
        "finished": gw < CURRENT_GW,
    })

# --- fixtures (round robin) -----------------------------------------------------
FIXTURES = []
ids = list(range(1, 21))
fid = 1
for gw in range(1, 39):
    rnd = (gw - 1) % 19
    rot = ids[1:]
    rot = rot[-rnd:] + rot[:-rnd] if rnd else rot
    order = [ids[0]] + rot
    pairs = [(order[i], order[19 - i]) for i in range(10)]
    if gw > 19:
        pairs = [(b, a) for a, b in pairs]
    day0 = datetime.strptime(EVENTS[gw - 1]["deadline_time"], ISO).replace(tzinfo=timezone.utc) + timedelta(days=1)
    for k, (h, a) in enumerate(pairs):
        r = _rng("fx", gw, h, a)
        ko = day0 + timedelta(hours=[0, 2.5, 5, 24, 26, 28.5, 48, 50, 51, 72][k])
        finished = gw < CURRENT_GW or (gw == CURRENT_GW and k < 9)
        live = gw == CURRENT_GW and k == 9
        FIXTURES.append({
            "id": fid, "event": gw, "kickoff_time": ko.strftime(ISO), "team_h": h, "team_a": a,
            "team_h_score": r.choice([0, 1, 1, 2, 2, 3, 4]) if finished or live else None,
            "team_a_score": r.choice([0, 0, 1, 1, 2, 3]) if finished or live else None,
            "finished": finished, "finished_provisional": finished, "started": finished or live,
            "minutes": 90 if finished else 63 if live else 0,
        })
        fid += 1


def _squad(team_id):
    r = _rng("squad", team_id)
    form = r.choice([(3, 4, 3), (4, 4, 2), (3, 5, 2), (4, 3, 3)])
    gks = r.sample(range(1, 21), 2)
    defs = r.sample(range(21, 71), 5)
    mids = r.sample(range(71, 121), 5)
    fwds = r.sample(range(121, 151), 3)
    xi = [gks[0]] + defs[: form[0]] + mids[: form[1]] + fwds[: form[2]]
    bench = [gks[1]] + defs[form[0]:] + mids[form[1]:] + fwds[form[2]:]
    xi, bench = xi[:11], bench[:4]
    cap = xi[-1]
    vice = xi[-2]
    picks = [
        {"element": e, "position": i + 1, "multiplier": 2 if e == cap else 1 if i < 11 else 0,
         "is_captain": e == cap, "is_vice_captain": e == vice}
        for i, e in enumerate(xi + bench)
    ]
    return picks


def _not_found():
    resp = requests.Response()
    resp.status_code = 404
    return requests.HTTPError("404 Not Found", response=resp)


def fake_fpl_get(path, ttl=60):
    path = path.strip("/")
    if path == "bootstrap-static":
        return {"events": EVENTS, "teams": TEAMS, "elements": ELEMENTS}
    if path == "fixtures":
        return FIXTURES
    parts = path.split("/")
    if parts[0] == "entry":
        tid = int(parts[1])
        if tid == 999:
            raise _not_found()
        if len(parts) == 2:
            return {"name": f"Team {tid}", "player_first_name": "Dev", "player_last_name": f"Manager{tid}"}
        if parts[2] == "history":
            cur = []
            for gw in range(1, CURRENT_GW + 1):
                pts = _rng("pts", tid, gw).randint(38, 96)
                if tid == 2000 and gw == CURRENT_GW:
                    pts = 31  # makes player 889 rank outside the Top 10
                cur.append({"event": gw, "points": pts})
            return {"current": cur}
        if parts[2] == "event":
            return {
                "picks": _squad(tid), "active_chip": None,
                "entry_history": {"points": _rng("pts", tid, int(parts[3])).randint(38, 96), "total_points": 412,
                                  "rank": 1_284_331, "value": 1012, "bank": 13, "event_transfers": 1,
                                  "event_transfers_cost": 4, "points_on_bench": 7},
            }
        if parts[2] == "transfers":
            r = _rng("tr", tid)
            out = []
            for gw in (3, 3, 5, 7):
                out.append({"event": gw, "time": NOW.strftime(ISO), "element_in": r.randint(71, 150),
                            "element_in_cost": r.randint(55, 120), "element_out": r.randint(21, 120),
                            "element_out_cost": r.randint(50, 115)})
            return out
    raise _not_found()


core.fpl_get = fake_fpl_get
fpl_views.fpl_get = fake_fpl_get

# --- fake payments --------------------------------------------------------------
core.create_payment_link = lambda tx_ref, amount, fn, ln, tid: "https://checkout.chapa.co/checkout/payment/mock-" + tx_ref
core.verify_payment = lambda tx_ref: True  # every payment "succeeds" instantly


# --- seed the database --------------------------------------------------------------
def seed():
    core.init_db()
    names = ["Abebe", "Selam", "Dawit", "Hanna", "Yonas", "Mekdes", "Biruk", "Rediet", "Nahom", "Lidya", "Kaleb", "Tigist"]
    for i, n in enumerate(names):
        tid = 100 + i
        core.register_user(tid, n, 1000 + i, f"{n} FC")
        for gw in (CURRENT_GW, CURRENT_GW + 1):
            core.db_execute("INSERT OR REPLACE INTO entries VALUES (?, ?, 1, ?)", (tid, gw, f"seed{tid}{gw}"))
    # 888: registered, entered this live GW, has not paid for the next one yet
    core.register_user(888, "dev888", 1888, "Addis Rovers")
    core.db_execute("INSERT OR REPLACE INTO entries VALUES (888, ?, 1, 'seed888')", (CURRENT_GW,))
    # 889: ranks outside the Top 10
    core.register_user(889, "dev889", 2000, "Late Bloomers")
    core.db_execute("INSERT OR REPLACE INTO entries VALUES (889, ?, 1, 'seed889')", (CURRENT_GW,))
    core.add_notification(888, "payment", "Payment confirmed ✅", f"You're entered in Gameweek {CURRENT_GW}. Good luck!")
    core.add_notification(888, "deadline", f"GW{CURRENT_GW + 1} entries close soon", "Less than 24 hours left to enter.")
    core.add_notification(888, "winner", f"GW{CURRENT_GW - 1} winner: Selam", "Selam won with 91 points. You finished #4.")


if __name__ == "__main__":
    import uvicorn

    seed()
    import server

    print("\n  Mock ETFPL running →  http://localhost:8000/?dev=888\n")
    uvicorn.run(server.app, host="127.0.0.1", port=8000, log_level="warning")
