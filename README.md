# ETFPL — Telegram Mini App + Bot

One service runs **the website (Mini App), its API, and the Telegram bot** together,
sharing one database. Users open the app from a button in your bot.

**Screens:** Home (enter & pay) · Top 10 leaderboard · Premier League table ·
Fixtures (any gameweek) · My Team (pitch view) + Transfers · Notifications (🔔)

## Stack (and why)

| Part | Chosen | Alternative |
|---|---|---|
| Backend | **FastAPI (Python)** — reuses your bot code, same SQLite database, one language | Node/Express or Next.js API routes (would mean rewriting the bot logic) |
| Front end | **Plain HTML/CSS/JS** served by the same service — no build step | React/Vite (nicer for a big team, overkill here) |
| Hosting | **Railway, one service** — already your host, free HTTPS (Telegram requires it) | Vercel/Netlify for the website + Railway for the API (two deployments, CORS, more to break) |

## 1. Try it on your computer (no Telegram needed)

```
pip install -r requirements.txt
python dev/test_smoke.py          # self-check of the API
python dev/mock_server.py         # fake data, open http://localhost:8000/?dev=888
```
Other test players: `?dev=777` (brand new), `?dev=889` (ranked outside the Top 10).

## 2. Deploy on Railway

1. Replace your GitHub repo's files with this folder's contents and push.
2. **Add a Volume** (Railway → your service → Settings → Volumes) mounted at `/data`.
   Without it, Railway wipes your database on every redeploy — all users and payments lost.
3. In **Variables**, set:
   - `BOT_TOKEN`, `ADMIN_TELEGRAM_ID`, `CHAPA_SECRET_KEY` (as before)
   - `DB_PATH` = `/data/fpl_contest.db`
   - `WEBAPP_URL` = your public address (next step), e.g. `https://etfpl-production.up.railway.app`
4. Settings → Networking → **Generate Domain**, copy it into `WEBAPP_URL`, redeploy.
5. Logs should show `Bot started` and `Menu button set to https://...`.
6. Open your bot in Telegram → send `/start` → tap **Open ETFPL App**. The blue menu
   button next to the message box also opens it.

Optional: in @BotFather send `/newapp` to get a shareable `t.me/yourbot/app` link.

**Moving your existing database?** Upload your old `fpl_contest.db` into the volume as
`/data/fpl_contest.db`. The new tables/columns are added automatically.

## What's new for players

- `/app` command and "Open ETFPL App" buttons in the bot
- Registration now **checks the team exists on FPL** and stores the team name
- Paying inside the app confirms the moment Chapa says yes
- ⏰ Deadline reminders ~24h and ~3h before entries close (for people who haven't entered);
  each person can switch them off in the app (🔔 → Deadline reminders)
- `/leaderboard` in the bot now shows the Top 10 too

## Important notes

- **Never set `DEV_MODE=1` on the live server** — it lets anyone pretend to be any user.
  The live app only trusts Telegram's signed login data.
- Run **either** `server.py` (website + bot) **or** `python bot.py` (bot only) — never both
  with the same token, or Telegram rejects the second one.
- **Entries now open for the *upcoming* gameweek.** The old code used FPL's "current"
  gameweek, whose deadline has already passed, so `/pay` would have said "closed" during
  the season. Entries/payment → next gameweek; leaderboard/winner → the gameweek being played.
- Player photos and club badges load from the Premier League's image servers. If they
  ever change addresses, a placeholder silhouette/shield shows instead — update the two
  URL lists at the top of `static/app.js`.
- Before taking real money, check Ethiopia's rules on cash-prize contests (as in your original README).
