/* ETFPL Mini App Client */

const CURRENT_PRIZE = {
  name: "PS5 Console",
  image: "/prize.png"
};

const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
}

let CURRENT_TAB = "home";
let USER_DATA = null;
let COUNTDOWN_TIMER = null;

const ICONS = {
  home: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>',
  trophy: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/></svg>',
  table: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/></svg>',
  calendar: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="18" height="18" x="3" y="4" rx="2" ry="2"/><line x1="16" x2="16" y1="2" y2="6"/><line x1="8" x2="8" y1="2" y2="6"/><line x1="3" x2="21" y1="10" y2="10"/></svg>',
  shirt: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.38 3.46 16 2a4 4 0 0 1-8 0L3.62 3.46a2 2 0 0 0-1.34 2.23l.58 3.47a1 1 0 0 0 .99.84H6v10a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V10h2.15a1 1 0 0 0 .99-.84l.58-3.47a2 2 0 0 0-1.34-2.23z"/></svg>'
};

function renderIcons() {
  document.querySelectorAll("[data-icon]").forEach(el => {
    const key = el.getAttribute("data-icon");
    if (ICONS[key]) el.innerHTML = ICONS[key];
  });
}

function apiHeaders() {
  const headers = { "Content-Type": "application/json" };
  const initData = tg?.initData;
  if (initData) headers["X-Telegram-Init-Data"] = initData;
  const params = new URLSearchParams(window.location.search);
  const dev = params.get("dev");
  if (dev) headers["X-Dev-User"] = dev;
  return headers;
}

async function api(path, options = {}) {
  const res = await fetch(path, { ...options, headers: { ...apiHeaders(), ...options.headers } });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || "Request failed");
  return data;
}

function showToast(msg) {
  const t = document.getElementById("toast");
  if (!t) return;
  t.textContent = msg;
  t.hidden = false;
  setTimeout(() => (t.hidden = true), 3500);
}

function startCountdown(deadlineStr, el) {
  if (COUNTDOWN_TIMER) clearInterval(COUNTDOWN_TIMER);
  if (!deadlineStr) return;
  const target = new Date(deadlineStr).getTime();
  if (isNaN(target)) return;

  function tick() {
    const now = Date.now();
    const diff = target - now;
    if (diff <= 0) {
      el.textContent = "00:00:00";
      clearInterval(COUNTDOWN_TIMER);
      return;
    }
    const h = Math.floor(diff / (1000 * 60 * 60));
    const m = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    const s = Math.floor((diff % (1000 * 60)) / 1000);
    el.textContent = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  }
  tick();
  COUNTDOWN_TIMER = setInterval(tick, 1000);
}

function formatDeadlineDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
}

async function loadHome() {
  const view = document.getElementById("view");
  view.innerHTML = '<div class="loader" style="text-align:center;padding:40px;color:#aaa;">Loading...</div>';

  try {
    const data = await api("/api/home");
    USER_DATA = data;

    const bellDot = document.getElementById("bell-dot");
    if (bellDot) {
      bellDot.hidden = !data.unread;
      bellDot.textContent = data.unread || 0;
    }

    const entry = data.entry;
    const isRegistered = data.registered;

    let heroHtml = "";
    if (entry) {
      heroHtml = `
        <div class="hero-card">
          <div class="hero-head">
            <span class="gw-tag">GAMEWEEK ${entry.gameweek} • ENTRIES CLOSE IN</span>
            <div class="timer" id="countdown">--:--:--</div>
            <div class="deadline-sub">Deadline ${formatDeadlineDate(entry.deadline)}</div>
          </div>

          <div class="stats-row">
            <div class="stat">
              <div class="num">${data.fee || 100}</div>
              <div class="lbl">ENTRY (BIRR)</div>
            </div>

            ${data.user && data.user.is_admin ? `
              <div class="stat admin-stat">
                <div class="num">${entry.pot || 0}</div>
                <div class="lbl">POT (BIRR)</div>
              </div>
            ` : ''}

            <div class="stat prize-stat">
              <div class="prize-content">
                <img src="${CURRENT_PRIZE.image}" alt="${CURRENT_PRIZE.name}" class="prize-thumbnail" onerror="this.style.display='none'">
                <div class="num prize-name">${CURRENT_PRIZE.name}</div>
              </div>
              <div class="lbl">PRIZE</div>
            </div>
          </div>

          <div class="action-zone">
            ${
              entry.paid
                ? `<div class="status-pill success">✓ You're in for Gameweek ${entry.gameweek}</div>`
                : entry.pending
                ? `<div class="status-pill warning">⏳ Payment processing...</div>`
                : !isRegistered
                ? `<button class="btn btn-primary" id="btn-go-register">Link FPL Team to Enter</button>`
                : `<button class="btn btn-primary" id="btn-pay">Pay ${data.fee || 100} Birr to Enter</button>`
            }
            <div class="entrants-count">${entry.entrants || 0} players entered so far</div>
          </div>
        </div>
      `;
    } else {
      heroHtml = `
        <div class="hero-card">
          <div class="hero-head">
            <span class="gw-tag">ENTRIES CLOSED</span>
            <div class="timer">--:--:--</div>
            <div class="deadline-sub">Next gameweek opening soon</div>
          </div>
        </div>
      `;
    }

    view.innerHTML = `
      ${heroHtml}

      ${
        !isRegistered
          ? `
          <div class="card register-card">
            <h3>Link Your FPL Team</h3>
            <p class="card-desc">Enter your numeric team ID from fantasy.premierleague.com</p>
            <div class="input-group">
              <input type="number" id="team-id-input" placeholder="e.g. 1234567" />
              <button class="btn btn-secondary" id="btn-save-team">Link</button>
            </div>
          </div>
        `
          : `
          <div class="card team-info-card">
            <div class="team-meta">
              <strong>${data.team?.name || "Your Team"}</strong>
              <small>ID: ${data.team?.id}</small>
            </div>
            <button class="link-btn" id="btn-change-team">Change</button>
          </div>
        `
      }

      <div class="card rules-card">
        <h3>How it works</h3>
        <ul class="steps-list">
          <li>
            <div class="step-num">1</div>
            <div class="step-txt">
              <strong>Link your FPL team</strong>
              <span>One time only.</span>
            </div>
          </li>
          <li>
            <div class="step-num">2</div>
            <div class="step-txt">
              <strong>Pay ${data.fee || 100} birr</strong>
              <span>Telebirr, CBE Birr or card — confirmed automatically.</span>
            </div>
          </li>
          <li>
            <div class="step-num">3</div>
            <div class="step-txt">
              <strong>Highest score wins</strong>
              <span>The best gameweek score wins the prize.</span>
            </div>
          </li>
        </ul>
      </div>
    `;

    if (entry && entry.deadline) {
      const cdEl = document.getElementById("countdown");
      if (cdEl) startCountdown(entry.deadline, cdEl);
    }

    document.getElementById("btn-go-register")?.addEventListener("click", () => {
      document.getElementById("team-id-input")?.focus();
    });

    document.getElementById("btn-save-team")?.addEventListener("click", async () => {
      const input = document.getElementById("team-id-input");
      const val = parseInt(input.value, 10);
      if (!val) return showToast("Enter a valid numeric ID");
      try {
        await api("/api/register", { method: "POST", body: JSON.stringify({ team_id: val }) });
        showToast("Team linked successfully!");
        loadHome();
      } catch (e) {
        showToast(e.message);
      }
    });

    document.getElementById("btn-change-team")?.addEventListener("click", () => {
      const tid = prompt("Enter your new FPL Team ID:");
      if (!tid) return;
      api("/api/register", { method: "POST", body: JSON.stringify({ team_id: parseInt(tid, 10) }) })
        .then(() => {
          showToast("Team updated!");
          loadHome();
        })
        .catch(e => showToast(e.message));
    });

    document.getElementById("btn-pay")?.addEventListener("click", async () => {
      try {
        const res = await api("/api/pay", { method: "POST" });
        if (res.checkout_url) {
          if (tg && tg.openLink) {
            tg.openLink(res.checkout_url);
          } else {
            window.location.href = res.checkout_url;
          }
          let checks = 0;
          const interval = setInterval(async () => {
            checks++;
            const c = await api("/api/pay/check", { method: "POST" });
            if (c.paid) {
              clearInterval(interval);
              showToast("Payment confirmed! You are entered!");
              loadHome();
            }
            if (checks >= 30) clearInterval(interval);
          }, 3000);
        }
      } catch (e) {
        showToast(e.message);
      }
    });
  } catch (err) {
    view.innerHTML = `<div class="error-box" style="padding:20px;text-align:center;color:#ff6b6b;">${err.message}</div>`;
  }
}

async function loadLeaderboard() {
  const view = document.getElementById("view");
  view.innerHTML = '<div class="loader" style="text-align:center;padding:40px;color:#aaa;">Loading...</div>';

  try {
    const data = await api("/api/leaderboard");
    let rowsHtml = "";

    if (!data.top || data.top.length === 0) {
      rowsHtml = '<div class="empty-state" style="padding:20px;text-align:center;">No confirmed entries yet this gameweek.</div>';
    } else {
      rowsHtml = data.top
        .map(
          r => `
          <div class="table-row ${r.is_me ? "highlight" : ""}">
            <div class="rank-badge">${r.rank}</div>
            <div class="user-meta">
              <strong>${r.name}</strong>
              <small>${r.team_name || ""}</small>
            </div>
            <div class="pts">${r.points} pts</div>
          </div>
        `
        )
        .join("");
    }

    view.innerHTML = `
      <div class="page-head">
        <h2>GW${data.gameweek || ""} Leaderboard</h2>
        <span class="sub">${data.entrants || 0} managers entered</span>
        ${
          data.pot && data.pot > 0
            ? `<div class="admin-pot-tag">Total Pot: ${Number(data.pot).toLocaleString()} birr</div>`
            : ""
        }
      </div>
      <div class="card list-card">${rowsHtml}</div>
      ${
        data.me
          ? `
        <div class="my-rank-banner">
          <span>Your Rank: #${data.me.rank}</span>
          <strong>${data.me.points} pts</strong>
        </div>
      `
          : ""
      }
    `;
  } catch (err) {
    view.innerHTML = `<div class="error-box" style="padding:20px;text-align:center;color:#ff6b6b;">${err.message}</div>`;
  }
}

async function loadTable() {
  const view = document.getElementById("view");
  view.innerHTML = '<div class="loader" style="text-align:center;padding:40px;color:#aaa;">Loading table...</div>';
  try {
    const data = await api("/api/table");
    const rows = (data.rows || [])
      .map(
        r => `
        <div class="league-row">
          <span class="pos">${r.pos}</span>
          <span class="team-name">${r.name}</span>
          <span class="num">${r.p}</span>
          <span class="num">${r.gd}</span>
          <span class="num pts-bold">${r.pts}</span>
        </div>
      `
      )
      .join("");

    view.innerHTML = `
      <div class="page-head"><h2>Premier League Table</h2></div>
      <div class="card">
        <div class="league-head">
          <span class="pos">#</span>
          <span class="team-name">Club</span>
          <span class="num">P</span>
          <span class="num">GD</span>
          <span class="num pts-bold">PTS</span>
        </div>
        ${rows}
      </div>
    `;
  } catch (err) {
    view.innerHTML = `<div class="error-box" style="padding:20px;text-align:center;color:#ff6b6b;">${err.message}</div>`;
  }
}

async function loadFixtures() {
  const view = document.getElementById("view");
  view.innerHTML = '<div class="loader" style="text-align:center;padding:40px;color:#aaa;">Loading fixtures...</div>';
  try {
    const data = await api("/api/fixtures");
    const matches = (data.matches || [])
      .map(
        m => `
        <div class="fixture-card">
          <div class="side home">${m.home.short}</div>
          <div class="score-box">
            ${
              m.status === "finished" || m.status === "live"
                ? `<strong>${m.home.score ?? 0} - ${m.away.score ?? 0}</strong>`
                : `<span>vs</span>`
            }
          </div>
          <div class="side away">${m.away.short}</div>
        </div>
      `
      )
      .join("");

    view.innerHTML = `
      <div class="page-head"><h2>Gameweek ${data.gameweek || ""} Fixtures</h2></div>
      <div class="fixtures-grid">${matches}</div>
    `;
  } catch (err) {
    view.innerHTML = `<div class="error-box" style="padding:20px;text-align:center;color:#ff6b6b;">${err.message}</div>`;
  }
}

async function loadTeam() {
  const view = document.getElementById("view");
  view.innerHTML = '<div class="loader" style="text-align:center;padding:40px;color:#aaa;">Loading squad...</div>';
  try {
    const data = await api("/api/my-team");
    if (!data.registered) {
      view.innerHTML = `
        <div class="empty-state" style="padding:40px;text-align:center;">
          <p>You haven't linked your FPL team yet.</p>
          <button class="btn btn-primary" onclick="setTab('home')">Link on Home</button>
        </div>
      `;
      return;
    }

    function renderLine(players) {
      return (players || [])
        .map(
          p => `
          <div class="pitch-player">
            <span class="p-name">${p.name} ${p.captain ? "(C)" : ""}</span>
            <span class="p-pts">${p.shown_points} pts</span>
          </div>
        `
        )
        .join("");
    }

    view.innerHTML = `
      <div class="page-head">
        <h2>${data.team?.name || "My Team"}</h2>
        <span class="sub">GW${data.gameweek} Points: ${data.summary?.points ?? 0}</span>
      </div>
      <div class="pitch">
        <div class="pitch-row">${renderLine(data.lines?.GKP)}</div>
        <div class="pitch-row">${renderLine(data.lines?.DEF)}</div>
        <div class="pitch-row">${renderLine(data.lines?.MID)}</div>
        <div class="pitch-row">${renderLine(data.lines?.FWD)}</div>
      </div>
      <div class="card bench-card">
        <h4>Bench</h4>
        <div class="bench-row">${renderLine(data.bench)}</div>
      </div>
    `;
  } catch (err) {
    view.innerHTML = `<div class="error-box" style="padding:20px;text-align:center;color:#ff6b6b;">${err.message}</div>`;
  }
}

async function openNotifications() {
  const sheet = document.getElementById("sheet");
  const backdrop = document.getElementById("backdrop");
  const body = document.getElementById("sheet-body");
  if (!sheet || !backdrop || !body) return;

  backdrop.hidden = false;
  sheet.hidden = false;
  body.innerHTML = '<div class="loader" style="text-align:center;padding:20px;color:#aaa;">Loading...</div>';

  try {
    const res = await api("/api/notifications");
    api("/api/notifications/read", { method: "POST" });
    const bellDot = document.getElementById("bell-dot");
    if (bellDot) bellDot.hidden = true;

    if (!res.items || res.items.length === 0) {
      body.innerHTML = '<div class="empty-state" style="padding:20px;text-align:center;">No notifications yet.</div>';
      return;
    }

    body.innerHTML = res.items
      .map(
        n => `
        <div class="notif-item">
          <strong>${n.title}</strong>
          <p>${n.body}</p>
        </div>
      `
      )
      .join("");
  } catch (e) {
    body.innerHTML = `<div class="error-box" style="padding:20px;text-align:center;color:#ff6b6b;">${e.message}</div>`;
  }
}

function closeNotifications() {
  const sheet = document.getElementById("sheet");
  const backdrop = document.getElementById("backdrop");
  if (sheet) sheet.hidden = true;
  if (backdrop) backdrop.hidden = true;
}

function setTab(tab) {
  CURRENT_TAB = tab;
  document.querySelectorAll("#tabbar button").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === tab);
  });
  if (tab === "home") loadHome();
  else if (tab === "board") loadLeaderboard();
  else if (tab === "table") loadTable();
  else if (tab === "fixtures") loadFixtures();
  else if (tab === "team") loadTeam();
}

function initApp() {
  renderIcons();
  document.querySelectorAll("#tabbar button").forEach(btn => {
    btn.addEventListener("click", () => setTab(btn.getAttribute("data-tab")));
  });

  document.getElementById("bell")?.addEventListener("click", openNotifications);
  document.getElementById("sheet-close")?.addEventListener("click", closeNotifications);
  document.getElementById("backdrop")?.addEventListener("click", closeNotifications);

  setTab("home");
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}
