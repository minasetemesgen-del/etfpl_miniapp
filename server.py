@app.get("/api/home")
def home(user: dict = Depends(current_user)):
    tid = user["id"]
    me = core.get_user(tid)
    window = core.get_entry_window()
    live_gw = core.get_live_gameweek()

    is_admin_user = (tid == ADMIN_TELEGRAM_ID)

    out = {
        "user": {
            "id": tid,
            "name": _display_name(user),
            "first_name": user.get("first_name"),
            "is_admin": is_admin_user,
        },
        "fee": ENTRY_FEE_BIRR,
        "prize_percent": int(core.PRIZE_SHARE * 100),
        "registered": bool(me),
        "team": {"id": me["team_id"], "name": me["team_name"]} if me else None,
        "entry": None,
        "live": None,
        "unread": core.unread_count(tid),
    }

    if window:
        gw = window["gameweek"]
        entry = core.get_entry(tid, gw)
        n = core.count_paid_entries(gw)
        pot_amount = n * ENTRY_FEE_BIRR
        out["entry"] = {
            "gameweek": gw,
            "deadline": _iso(window["deadline"]),
            "paid": bool(entry and entry["paid"]),
            "pending": bool(entry and not entry["paid"]),
            "entrants": n,
            "pot": pot_amount if is_admin_user else 0,
            "prize": 0, # Kept as a number so .toLocaleString() never crashes
        }

    if live_gw:
        board = core.contest_leaderboard(live_gw)
        mine = next((r for r in board if r["telegram_id"] == tid), None)
        out["live"] = {
            "gameweek": live_gw,
            "entrants": len(board),
            "entered": bool(mine),
            "rank": mine["rank"] if mine else None,
            "points": mine["points"] if mine else None,
        }
    return out


@app.get("/api/leaderboard")
def leaderboard(user: dict = Depends(current_user)):
    gw = core.get_live_gameweek()
    board = core.contest_leaderboard(gw) if gw else []
    tid = user["id"]
    is_admin_user = (tid == ADMIN_TELEGRAM_ID)

    top = [
        {
            "rank": r["rank"],
            "name": r["username"],
            "team_name": r["team_name"],
            "points": r["points"],
            "is_me": r["telegram_id"] == tid,
        }
        for r in board[:10]
    ]
    mine = next((r for r in board if r["telegram_id"] == tid), None)
    me = None
    if mine and mine["rank"] > 10:
        me = {
            "rank": mine["rank"],
            "name": mine["username"],
            "team_name": mine["team_name"],
            "points": mine["points"],
            "is_me": True,
        }
    pot = len(board) * ENTRY_FEE_BIRR
    return {
        "gameweek": gw,
        "entrants": len(board),
        "top": top,
        "me": me,
        "pot": pot if is_admin_user else 0, # Kept as a number
        "prize": 0,                         # Kept as a number
    }
