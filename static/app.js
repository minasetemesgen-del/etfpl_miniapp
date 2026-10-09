async function loadLeaderboard() {
  const view = document.getElementById("view");
  view.innerHTML = '<div class="loader">Loading...</div>';

  try {
    const data = await api("/api/leaderboard");
    let rowsHtml = "";

    if (!data.top || data.top.length === 0) {
      rowsHtml = '<div class="empty-state">No confirmed entries yet this gameweek.</div>';
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
        <span class="sub">${data.entrants} managers entered</span>
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
    view.innerHTML = `<div class="error-box">${err.message}</div>`;
  }
}
