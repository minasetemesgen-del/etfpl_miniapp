"""
Quick self-check of the API using fake FPL data:   python dev/test_smoke.py
Covers Telegram sign-in validation, registration, payment, and every screen's data.
"""

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mock_server as mock  # noqa: E402  (sets env + patches FPL/Chapa)

mock.seed()

import logging  # noqa: E402

logging.disable(logging.INFO)  # keep the test output readable

from fastapi.testclient import TestClient  # noqa: E402

import core  # noqa: E402
import server  # noqa: E402

TOKEN = mock.os.environ["BOT_TOKEN"]


def sign(user_id, auth_date=None, token=TOKEN):
    user = json.dumps({"id": user_id, "first_name": "Test", "username": f"user{user_id}"}, separators=(",", ":"))
    fields = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAH", "user": user}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


passed = 0


def check(name, cond):
    global passed
    if not cond:
        print(f"  FAIL  {name}")
        sys.exit(1)
    passed += 1
    print(f"  ok    {name}")


with TestClient(server.app) as client:
    H = lambda uid: {"X-Telegram-Init-Data": sign(uid)}  # noqa: E731

    print("Telegram sign-in")
    check("no header → 401", client.get("/api/home").status_code == 401)
    check("valid signature → 200", client.get("/api/home", headers=H(777)).status_code == 200)
    bad = sign(777).replace("user=", "user=%7B%7D&x=")  # tampered payload
    check("tampered data → 401", client.get("/api/home", headers={"X-Telegram-Init-Data": bad}).status_code == 401)
    check("wrong bot token → 401", client.get("/api/home", headers={"X-Telegram-Init-Data": sign(777, token="1:OTHER")}).status_code == 401)
    check("expired (2 days old) → 401", client.get("/api/home", headers={"X-Telegram-Init-Data": sign(777, auth_date=int(time.time()) - 2 * 86400)}).status_code == 401)
    server.DEV_MODE = False
    check("dev header ignored when DEV_MODE off", client.get("/api/home", headers={"X-Dev-User": "777"}).status_code == 401)
    server.DEV_MODE = True
    check("dev header works when DEV_MODE on", client.get("/api/home", headers={"X-Dev-User": "777"}).status_code == 200)

    print("Registration & payment (new player 777)")
    home = client.get("/api/home", headers=H(777)).json()
    check("starts unregistered", home["registered"] is False)
    check("entry window is GW8", home["entry"]["gameweek"] == 8 and not home["entry"]["paid"])
    r = client.post("/api/pay", headers=H(777))
    check("pay before registering → 400", r.status_code == 400)
    r = client.post("/api/register", headers=H(777), json={"team_id": 999})
    check("unknown FPL team → 400 with message", r.status_code == 400 and "couldn't find" in r.json()["detail"])
    r = client.post("/api/register", headers=H(777), json={"team_id": 5555})
    check("register ok, team name stored", r.status_code == 200 and r.json()["team"]["name"] == "Team 5555")
    r = client.post("/api/pay", headers=H(777))
    check("pay returns checkout link for GW8", r.status_code == 200 and r.json()["gameweek"] == 8 and r.json()["checkout_url"].startswith("https://"))
    home = client.get("/api/home", headers=H(777)).json()
    check("pending after link created", home["entry"]["pending"] and not home["entry"]["paid"])
    r = client.post("/api/pay/check", headers=H(777)).json()
    check("payment confirmed on check", r["paid"] is True and r["confirmed"] == [8])
    home = client.get("/api/home", headers=H(777)).json()
    check("home shows paid, pot grows", home["entry"]["paid"] and home["entry"]["entrants"] == 13)
    r = client.post("/api/pay", headers=H(777))
    check("paying twice is refused", r.status_code == 400 and r.json()["code"] == "already_paid")
    check("confirming again does not double-notify", client.post("/api/pay/check", headers=H(777)).json()["confirmed"] == [])

    print("Notifications")
    n = client.get("/api/notifications", headers=H(777)).json()
    check("payment notification created once", len(n["items"]) == 1 and n["unread"] == 1)
    client.post("/api/notifications/read", headers=H(777))
    check("mark read", client.get("/api/notifications", headers=H(777)).json()["unread"] == 0)
    client.post("/api/settings", headers=H(777), json={"notify_deadline": False})
    check("reminder toggle saved", client.get("/api/notifications", headers=H(777)).json()["settings"]["notify_deadline"] is False)
    check("opted-out user gets no reminder", 777 not in core.reminder_targets(8, 24))
    check("registered unpaid user gets reminder", 888 in core.reminder_targets(8, 24))

    print("Top 10 leaderboard")
    lb = client.get("/api/leaderboard", headers=H(889)).json()
    check("shows exactly 10 rows", len(lb["top"]) == 10 and lb["entrants"] == 14)
    check("ranks are descending by points", [r["points"] for r in lb["top"]] == sorted([r["points"] for r in lb["top"]], reverse=True))
    check("player outside Top 10 gets own row", lb["me"] is not None and lb["me"]["rank"] > 10)
    check("leaderboard shows prize text", lb["prize"]["text"] == "PlayStation 5")

    print("Pot & payout are admin-only")
    for uid in (777, 888, 889):
        raw = client.get("/api/home", headers=H(uid)).text + client.get("/api/leaderboard", headers=H(uid)).text
        check(f"player {uid}: no pot/payout anywhere in responses", '"pot"' not in raw and '"payout"' not in raw and '"admin":{' not in raw)
    check("non-admin home has no admin block", "admin" not in client.get("/api/home", headers=H(888)).json())
    check("non-admin leaderboard admin is null", client.get("/api/leaderboard", headers=H(888)).json()["admin"] is None)
    ADMIN = 1  # ADMIN_TELEGRAM_ID in mock_server
    ah = client.get("/api/home", headers=H(ADMIN)).json()
    check("admin home sees pot + 50% payout", ah["is_admin"] and ah["admin"]["pot"] == ah["admin"]["players"] * 100 and ah["admin"]["payout"] == round(ah["admin"]["pot"] * 0.5))
    al = client.get("/api/leaderboard", headers=H(ADMIN)).json()
    check("admin leaderboard sees pot + payout", al["admin"]["pot"] == al["entrants"] * 100 and al["admin"]["percent"] == 50)

    print("Prize picture + text")
    check("home carries the prize", client.get("/api/home", headers=H(777)).json()["prize"]["text"] == "PlayStation 5")
    img = client.get("/api/prize-image")
    check("prize picture is served as PNG", img.status_code == 200 and img.headers["content-type"] == "image/png" and img.content[:4] == b"\x89PNG")
    v1 = client.get("/api/home", headers=H(777)).json()["prize"]["version"]
    core.set_prize_text("  PS4   Pro  ")
    p = client.get("/api/home", headers=H(777)).json()["prize"]
    check("text edit is cleaned up and busts the picture cache", p["text"] == "PS4 Pro" and p["version"] != v1 and p["has_image"])
    core.set_prize_text("x" * 300)
    check("prize text is capped at 80 characters", len(core.get_prize()["text"]) == 80)
    try:
        core.save_prize_image(b"hello", "application/pdf")
        check("non-image rejected", False)
    except core.ContestError:
        check("non-image rejected", True)
    try:
        core.save_prize_image(b"0" * (core.MAX_PRIZE_IMAGE_BYTES + 1), "image/png")
        check("oversized picture rejected", False)
    except core.ContestError:
        check("oversized picture rejected", True)
    core.clear_prize()
    cleared = client.get("/api/home", headers=H(777)).json()["prize"]
    check("clearing removes text and picture", cleared["text"] == "" and not cleared["has_image"] and client.get("/api/prize-image").status_code == 404)
    core.set_prize_text("PlayStation 5")  # restore for the checks below

    print("Premier League data")
    table = client.get("/api/table", headers=H(777)).json()["rows"]
    check("20 clubs, positions 1..20", [r["pos"] for r in table] == list(range(1, 21)))
    check("sorted by points", [r["pts"] for r in table] == sorted([r["pts"] for r in table], reverse=True))
    check("points = 3W + D, GD = GF - GA", all(r["pts"] == 3 * r["w"] + r["d"] and r["gd"] == r["gf"] - r["ga"] for r in table))
    # GW1-6 fully played + 9 of 10 GW7 matches finished (one is still live and not counted)
    check("live match isn't counted in the table", sorted(r["p"] for r in table).count(6) == 2 and all(r["p"] in (6, 7) for r in table))
    fx = client.get("/api/fixtures", headers=H(777)).json()
    check("fixtures default to current GW7 with 10 matches", fx["gameweek"] == 7 and len(fx["matches"]) == 10 and fx["total"] == 38)
    check("one live match", sum(m["status"] == "live" for m in fx["matches"]) == 1)
    check("fixtures for GW9 are all scheduled", all(m["status"] == "scheduled" for m in client.get("/api/fixtures?gw=9", headers=H(777)).json()["matches"]))
    check("out-of-range GW is clamped", client.get("/api/fixtures?gw=99", headers=H(777)).json()["gameweek"] == 38)

    print("My team & transfers")
    check("unregistered has no team", client.get("/api/my-team", headers=H(12345)).json()["registered"] is False)
    team = client.get("/api/my-team", headers=H(888)).json()
    sizes = {k: len(v) for k, v in team["lines"].items()}
    check("11 starters + 4 bench", sum(sizes.values()) == 11 and sizes["GKP"] == 1 and len(team["bench"]) == 4)
    caps = [p for line in team["lines"].values() for p in line if p["captain"]]
    check("exactly one captain, points doubled", len(caps) == 1 and caps[0]["shown_points"] == caps[0]["points"] * 2)
    tr = client.get("/api/transfers", headers=H(888)).json()
    check("transfers list + trending", len(tr["mine"]) == 4 and len(tr["trending"]["in"]) == 6 and len(tr["trending"]["out"]) == 6)
    tr0 = client.get("/api/transfers", headers=H(12345)).json()
    check("unregistered still sees trending", tr0["registered"] is False and tr0["mine"] == [] and len(tr0["trending"]["in"]) == 6)

    print("Website files")
    for path in ("/", "/app.js", "/style.css", "/health"):
        check(f"GET {path}", client.get(path).status_code == 200)

print(f"\nAll {passed} checks passed.")
