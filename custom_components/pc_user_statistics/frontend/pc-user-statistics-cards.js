// PC User Statistics – Custom Lovelace Cards
// Version: 2.5.0
// Cards:
//   custom:pc-user-statistics-user-card   – compact single-user card (mobile)
//   custom:pc-user-statistics-tablet-card – all-users overview (tablet/desktop)
// Last Updated: March 2, 2026

// ─────────────────────────────────────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────────────────────────────────────

const DOMAIN  = "pc_user_statistics";
const COLORS  = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6"];

function fmtTime(s) {
  if (!s || s < 0) return "0t 0m";
  return `${Math.floor(s / 3600)}t ${Math.floor((s % 3600) / 60)}m`;
}
function fmtEnergy(k) { return k ? k.toFixed(3).replace(".",",")+"\u00a0kWh" : "0,000\u00a0kWh"; }
function fmtCost(d)   { return d ? d.toFixed(2).replace(".",",")+"\u00a0kr"  : "0,00\u00a0kr";  }

// User color is ALWAYS based on index in tracked_users list.
// Falls back to hash only if user is not found (should not happen).
function userColor(name, trackedUsers) {
  if (trackedUsers && trackedUsers.length) {
    const idx = trackedUsers.indexOf((name || "").toLowerCase());
    if (idx >= 0) return COLORS[idx % COLORS.length];
  }
  // Fallback: hash (consistent with old behaviour if trackedUsers unavailable)
  const n = name || "";
  let h = 0;
  for (const c of n) h = c.charCodeAt(0) + h * 31;
  return COLORS[Math.abs(h) % COLORS.length];
}

function esc(s) {
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function isDarkMode(hass) {
  return hass?.themes?.darkMode ?? (window.matchMedia?.("(prefers-color-scheme:dark)").matches ?? false);
}

function cssVars() {
  // Use HA theme CSS custom properties directly — works with ANY active HA theme.
  // Shadow DOM inherits custom properties from :root automatically.
  return `
    --bg:  var(--card-background-color, #1f2937);
    --bg2: var(--secondary-background-color, #374151);
    --text: var(--primary-text-color, #f9fafb);
    --sub: var(--secondary-text-color, #9ca3af);
    --div: var(--divider-color, #374151);
  `;
}

// ─────────────────────────────────────────────────────────────────────────────
// pc-user-statistics-user-card
// Shows live session + monthly stats for ONE configured user.
// Config:
//   user: "flemming"   (required – must match tracked_users)
//   title: "Min PC"    (optional)
// ─────────────────────────────────────────────────────────────────────────────

class PcUserStatisticsUserCard extends HTMLElement {

  // Called by Lovelace to get a stub config for the card picker
  static getStubConfig() {
    return { user: "flemming" };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass    = null;
    this._stats   = null;
    this._config  = {};
    this._interval = null;
    this._errCount = 0;
  }

  setConfig(config) {
    if (!config.user) throw new Error("pc-user-statistics-user-card: 'user' is required");
    this._config = config;
    this._render();
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._load();
  }

  connectedCallback() {
    this._interval = setInterval(() => {
      if (this._errCount > 5) { clearInterval(this._interval); return; }
      if (document.visibilityState === "visible") this._load();
    }, 30000);
  }

  disconnectedCallback() {
    clearInterval(this._interval);
  }

  async _load() {
    if (!this._hass) return;
    try {
      this._stats = await this._hass.callWS({ type: `${DOMAIN}/get_stats` });
      this._errCount = 0;
    } catch (e) {
      this._errCount++;
      console.error("PcUserCard load error:", e);
    }
    this._render();
  }

  _donutSVG(users, monthly) {
    const totals = users.map(u => (monthly[u]?.time ?? 0));
    const total  = totals.reduce((a, b) => a + b, 0);
    if (!total) return `
      <svg viewBox="0 0 80 80" class="donut-svg">
        <circle cx="40" cy="40" r="28" fill="none" stroke="var(--div)" stroke-width="12"/>
      </svg>
      <div class="donut-center"><div class="donut-no-data">—</div></div>`;

    const C = 2 * Math.PI * 28;
    let offset = 0;
    const segs = users.map((u, i) => {
      const pct  = totals[i] / total;
      const dash = pct * C;
      const gap  = C - dash;
      const seg  = { dash, gap, color: COLORS[i % COLORS.length], offset };
      offset += dash;
      return seg;
    });

    const thisIdx = users.indexOf(this._config.user?.toLowerCase() ?? "");
    const topColor = thisIdx >= 0 ? COLORS[thisIdx % COLORS.length] : COLORS[0];
    const thisPct  = thisIdx >= 0 && total ? Math.round((totals[thisIdx] / total) * 100) : 0;

    const circles = segs.map(s => `
      <circle cx="40" cy="40" r="28" fill="none"
        stroke="${s.color}" stroke-width="12"
        stroke-dasharray="${s.dash} ${s.gap}"
        stroke-dashoffset="${-s.offset}"
        transform="rotate(-90 40 40)"/>`).join("");

    const legend = users.map((u, i) => {
      const c = COLORS[i % COLORS.length];
      // convert hex to rgba for background tint
      const r = parseInt(c.slice(1,3),16), g = parseInt(c.slice(3,5),16), b = parseInt(c.slice(5,7),16);
      return `<span class="donut-init" style="color:${c};background:rgba(${r},${g},${b},0.18)" title="${esc(u)}">${u[0].toUpperCase()}</span>`;
    }).join("");

    return `
      <div class="donut-ring">
        <svg viewBox="0 0 80 80" class="donut-svg">${circles}</svg>
        <div class="donut-center">
          <div class="donut-pct" style="color:${topColor}">${thisPct}%</div>
        </div>
      </div>
      <div class="donut-initials">${legend}</div>`;
  }

  _leaderboardHTML(users, monthly) {
    const medals = ["🥇","🥈","🥉"];
    const sorted = [...users].sort((a, b) => (monthly[b]?.time ?? 0) - (monthly[a]?.time ?? 0));
    const maxTime = monthly[sorted[0]]?.time ?? 0;

    return sorted.map((u, i) => {
      const d      = monthly[u] ?? {};
      const color  = userColor(u, users);
      const pct    = maxTime > 0 ? Math.round((d.time ?? 0) / maxTime * 100) : 0;
      const isThis = u === (this._config.user?.toLowerCase() ?? "");
      const r = parseInt(color.slice(1,3),16), g = parseInt(color.slice(3,5),16), b = parseInt(color.slice(5,7),16);
      return `
        <div class="lb-row ${isThis ? "lb-active" : ""}" style="${isThis ? `--user-color:${color}` : ""}">
          <div class="lb-medal">${medals[i] ?? ""}</div>
          <div class="lb-avatar" style="background:${color}">${u[0].toUpperCase()}</div>
          <div class="lb-name">
            ${esc(u)}
            <div class="lb-bar-bg"><div class="lb-bar-fill" style="width:${pct}%;background:${color}"></div></div>
          </div>
          <div class="lb-stats">
            <div class="lb-time">${fmtTime(d.time)}</div>
            <div class="lb-cost">${fmtCost(d.cost)}</div>
          </div>
        </div>`;
    }).join("");
  }

  _render() {
    const dark    = isDarkMode(this._hass);
    const s       = this._stats;
    const user    = this._config.user?.toLowerCase() ?? "";
    const title   = this._config.title ?? user.charAt(0).toUpperCase() + user.slice(1);
    const color   = userColor(user, s?.tracked_users ?? []);
    const initial = user ? user[0].toUpperCase() : "?";

    const isActive    = s?.current_user === user;
    const monthly     = s?.monthly?.[user] ?? {};
    const users       = s?.tracked_users ?? [];
    const allMonthly  = s?.monthly ?? {};
    const sessionTime = isActive ? (s?.acc_time   ?? 0) : 0;
    const sessionEng  = isActive ? (s?.acc_energy ?? 0) : 0;
    const sessionCost = isActive ? (s?.acc_cost   ?? 0) : 0;

    const activeBadge = isActive
      ? `<span class="badge-live">● LIVE</span>`
      : `<span class="badge-idle">Inaktiv</span>`;

    const donutHTML = users.length
      ? `<div class="donut-corner">${this._donutSVG(users, allMonthly)}</div>`
      : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          ${cssVars()}
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        .card {
          background: var(--bg);
          border-radius: 16px;
          padding: 16px;
          color: var(--text);
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.15));
        }
        .header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 14px;
        }
        .avatar {
          width: 44px; height: 44px;
          border-radius: 50%;
          background: ${color};
          display: flex; align-items: center; justify-content: center;
          font-size: 20px; font-weight: 700; color: #fff;
          flex-shrink: 0;
        }
        .header-info { flex: 1; min-width: 0; }
        .user-name {
          font-size: 16px; font-weight: 700;
          text-transform: capitalize;
          white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .badge-live  { font-size: 11px; font-weight: 700; color: #10b981; letter-spacing: .5px; }
        .badge-idle  { font-size: 11px; color: var(--sub); }

        .divider { height: 1px; background: var(--div); margin: 10px 0; }

        .section-label {
          font-size: 10px; font-weight: 600; text-transform: uppercase;
          letter-spacing: 1px; color: var(--sub); margin-bottom: 8px;
        }

        .stat-row {
          display: flex; gap: 8px; margin-bottom: 10px;
        }
        .stat-box {
          flex: 1; background: var(--bg2); border-radius: 10px;
          padding: 10px 8px; text-align: center;
        }
        .stat-box.active { border: 1px solid ${color}44; }
        .stat-icon { font-size: 18px; margin-bottom: 4px; }
        .stat-val  { font-size: 15px; font-weight: 700; line-height: 1.1; }
        .stat-lbl  { font-size: 10px; color: var(--sub); margin-top: 3px; }

        .monthly-grid {
          display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px;
        }
        .m-box {
          background: var(--bg2); border-radius: 10px;
          padding: 8px 6px; text-align: center;
        }
        .m-val { font-size: 13px; font-weight: 700; }
        .m-lbl { font-size: 10px; color: var(--sub); margin-top: 2px; }

        .error { color: var(--sub); font-size: 13px; padding: 8px 0; }

        /* ── Corner donut ── */
        .header { position: relative; }
        .header-info { padding-right: 90px; }
        .donut-corner {
          position: absolute; top: 0; right: 0;
          display: flex; flex-direction: row; align-items: center; gap: 6px;
        }
        .donut-ring { position: relative; flex-shrink: 0; }
        .donut-svg  { width: 80px; height: 80px; display: block; }
        .donut-center {
          position: absolute; top: 50%; left: 50%;
          transform: translate(-50%, -50%);
          text-align: center;
        }
        .donut-pct     { font-size: 14px; font-weight: 800; line-height: 1; }
        .donut-no-data { font-size: 10px; color: var(--sub); }

        /* ── Leaderboard ── */
        .lb-row {
          display: flex; align-items: center; gap: 10px;
          padding: 8px 10px; border-radius: 10px;
          margin-bottom: 6px;
          background: var(--bg2);
        }
        .lb-row.lb-active {
          border: 1px solid var(--user-color, #6366f1);
          background: var(--bg2);
        }
        .lb-medal { font-size: 18px; width: 24px; text-align: center; flex-shrink: 0; }
        .lb-avatar {
          width: 30px; height: 30px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: 13px; font-weight: 700; color: #fff; flex-shrink: 0;
        }
        .lb-name { flex: 1; font-size: 13px; font-weight: 600; text-transform: capitalize; }
        .lb-stats { text-align: right; }
        .lb-time { font-size: 13px; font-weight: 700; }
        .lb-cost { font-size: 10px; color: var(--sub); }
        .lb-bar-bg {
          height: 3px; background: var(--div); border-radius: 2px;
          margin-top: 4px; overflow: hidden;
        }
        .lb-bar-fill { height: 100%; border-radius: 2px; transition: width .4s; }

        .donut-initials {
          display: flex; flex-direction: column; justify-content: center; gap: 4px;
        }
        .donut-init {
          font-size: 11px; font-weight: 800;
          width: 18px; height: 18px; border-radius: 50%;
          background: transparent; /* set inline via JS */
          display: flex; align-items: center; justify-content: center;
          line-height: 1;
        }
      </style>
      <ha-card>
        <div class="card">
          <div class="header">
            <div class="avatar">${initial}</div>
            <div class="header-info">
              <div class="user-name">${esc(title)}</div>
              ${s ? activeBadge : '<span class="badge-idle">Indlæser…</span>'}
            </div>
            ${donutHTML}
          </div>

          ${!s ? '<div class="error">Henter data…</div>' : `
            <div class="section-label">Session</div>
            <div class="stat-row">
              <div class="stat-box ${isActive ? "active" : ""}">
                <div class="stat-icon">⏱️</div>
                <div class="stat-val">${fmtTime(sessionTime)}</div>
                <div class="stat-lbl">Tid</div>
              </div>
              <div class="stat-box ${isActive ? "active" : ""}">
                <div class="stat-icon">⚡</div>
                <div class="stat-val">${fmtEnergy(sessionEng)}</div>
                <div class="stat-lbl">Energi</div>
              </div>
              <div class="stat-box ${isActive ? "active" : ""}">
                <div class="stat-icon">💰</div>
                <div class="stat-val">${fmtCost(sessionCost)}</div>
                <div class="stat-lbl">Pris</div>
              </div>
            </div>

            <div class="divider"></div>

            <div class="section-label">Denne måned</div>
            <div class="monthly-grid">
              <div class="m-box">
                <div class="m-val">${fmtTime(monthly.time)}</div>
                <div class="m-lbl">Tid</div>
              </div>
              <div class="m-box">
                <div class="m-val">${fmtEnergy(monthly.energy)}</div>
                <div class="m-lbl">Energi</div>
              </div>
              <div class="m-box">
                <div class="m-val">${fmtCost(monthly.cost)}</div>
                <div class="m-lbl">Pris</div>
              </div>
            </div>

            <div class="divider"></div>

            <div class="section-label">🏆 Leaderboard</div>
            ${this._leaderboardHTML(users, allMonthly)}
          `}
        </div>
      </ha-card>`;
  }

  // Required by Lovelace – returns card height in rows
  getCardSize() { return 4; }
}

if (!customElements.get("pc-user-statistics-user-card")) {
  customElements.define("pc-user-statistics-user-card", PcUserStatisticsUserCard);
}


// ─────────────────────────────────────────────────────────────────────────────
// pc-user-statistics-tablet-card
// Shows live session + monthly overview for ALL tracked users side by side.
// Config:
//   title: "PC Overblik"  (optional)
// ─────────────────────────────────────────────────────────────────────────────

class PcUserStatisticsTabletCard extends HTMLElement {

  static getStubConfig() {
    return { title: "PC Overblik" };
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass       = null;
    this._stats      = null;
    this._config     = {};
    this._gaugeConfig = null; // loaded once from get_config
    this._interval   = null;
    this._errCount   = 0;
  }

  setConfig(config) {
    this._config = config ?? {};
    this._render();
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    if (first) this._loadAll();
    this._updateWatt(h);
    this._updateBars(h);
  }

  async _loadAll() {
    if (!this._hass) return;
    try {
      const [stats, cfg] = await Promise.all([
        this._hass.callWS({ type: `${DOMAIN}/get_stats` }),
        this._hass.callWS({ type: `${DOMAIN}/get_config` }),
      ]);
      this._stats = stats;
      this._gaugeConfig = cfg;
      this._errCount = 0;
    } catch (e) {
      this._errCount++;
      console.error("PcTabletCard load error:", e);
    }
    this._render();
  }

  connectedCallback() {
    this._interval = setInterval(() => {
      if (this._errCount > 5) { clearInterval(this._interval); return; }
      if (document.visibilityState === "visible") this._loadStats();
    }, 30000);
  }

  disconnectedCallback() {
    clearInterval(this._interval);
  }

  // Polling: only refresh stats (gauge config is static, loaded once)
  async _loadStats() {
    if (!this._hass) return;
    try {
      this._stats = await this._hass.callWS({ type: `${DOMAIN}/get_stats` });
      this._errCount = 0;
    } catch (e) {
      this._errCount++;
      console.error("PcTabletCard load error:", e);
    }
    this._render();
  }

  _updateWatt(h) {
    const el = this.shadowRoot?.querySelector(".live-watt");
    if (!el) return;
    const st  = h.states?.["sensor.gamer_pc_power_monitor_current_consumption"];
    const raw = st ? parseFloat(st.state) : null;
    el.textContent = raw && !isNaN(raw) ? raw.toFixed(0) + " W" : "—";
  }

  _updateBars(h) {
    const gc = this._gaugeConfig;
    if (!gc || !this.shadowRoot) return;
    const GAUGE_COLORS = ["#6366f1","#f59e0b","#10b981","#8b5cf6","#06b6d4"];
    [1,2,3,4,5].forEach(n => {
      const entity = gc[`gauge${n}_entity`];
      if (!entity) return;
      const st  = h.states?.[entity];
      const raw = st ? parseFloat(st.state) : null;
      const val = raw != null && !isNaN(raw) ? raw : null;
      const pct = val != null ? Math.min(Math.max(val, 0), 100) : 0;
      const color  = GAUGE_COLORS[(n-1) % GAUGE_COLORS.length];
      const danger = pct > 90 ? "#ef4444" : pct > 70 ? "#f59e0b" : color;
      const dv = val != null ? (Number.isInteger(val) ? val+"%" : val.toFixed(1)) : "—";
      const valEl  = this.shadowRoot.querySelector(`.bar-val-${n}`);
      const fillEl = this.shadowRoot.querySelector(`.bar-fill-${n}`);
      if (valEl)  { valEl.textContent = dv; valEl.style.color = danger; }
      if (fillEl) { fillEl.style.height = pct + "%"; fillEl.style.background = danger; }
    });
  }

  _donutSVG(users, monthly) {
    const totals = users.map(u => (monthly[u]?.time ?? 0));
    const total  = totals.reduce((a, b) => a + b, 0);
    if (!total) {
      return `
        <svg viewBox="0 0 120 120" class="donut-svg">
          <circle cx="60" cy="60" r="44" fill="none" stroke="var(--div)" stroke-width="18"/>
        </svg>
        <div class="donut-center"><div class="donut-no-data">Ingen data</div></div>`;
    }

    const C = 2 * Math.PI * 44;
    let offset = 0;
    const segs = users.map((u, i) => {
      const pct  = totals[i] / total;
      const dash = pct * C;
      const gap  = C - dash;
      const seg  = { u, pct, dash, gap, color: COLORS[i % COLORS.length], offset };
      offset += dash;
      return seg;
    });

    const topIdx  = totals.indexOf(Math.max(...totals));
    const topUser = users[topIdx] ?? "";
    const topPct  = total ? Math.round((totals[topIdx] / total) * 100) : 0;

    const circles = segs.map(s => `
      <circle cx="60" cy="60" r="44" fill="none"
        stroke="${s.color}" stroke-width="18"
        stroke-dasharray="${s.dash} ${s.gap}"
        stroke-dashoffset="${-s.offset}"
        transform="rotate(-90 60 60)"/>`).join("");

    const legend = users.map((u, i) => {
      const pct = total ? Math.round((totals[i] / total) * 100) : 0;
      return `<div class="legend-row">
        <span class="legend-dot" style="background:${COLORS[i % COLORS.length]}"></span>
        <span class="legend-name">${esc(u)}</span>
        <span class="legend-pct">${pct}%</span>
      </div>`;
    }).join("");

    return `
      <div class="donut-ring">
        <svg viewBox="0 0 120 120" class="donut-svg">${circles}</svg>
        <div class="donut-center">
          <div class="donut-top-user" style="color:${COLORS[topIdx % COLORS.length]}">${esc(topUser)}</div>
          <div class="donut-top-pct">${topPct}%</div>
        </div>
      </div>
      <div class="donut-legend">${legend}</div>`;
  }

  _render() {
    const dark    = isDarkMode(this._hass);
    const s       = this._stats;
    const title   = this._config.title ?? "PC Overblik";
    const users   = s?.tracked_users ?? [];
    const monthly = s?.monthly ?? {};

    // Right column: donut → live session → gauge bars (stacked vertically)
    const gc = this._gaugeConfig || {};
    const GAUGE_COLORS = ["#6366f1","#f59e0b","#10b981","#8b5cf6","#06b6d4"];

    const gaugeBars = [1,2,3,4,5].map(n => {
      const entity = gc[`gauge${n}_entity`];
      const label  = gc[`gauge${n}_label`] || `G${n}`;
      if (!entity) return "";
      const st    = this._hass?.states?.[entity];
      const raw   = st ? parseFloat(st.state) : null;
      const val   = raw != null && !isNaN(raw) ? raw : null;
      const pct   = val != null ? Math.min(Math.max(val, 0), 100) : 0;
      const color = GAUGE_COLORS[(n-1) % GAUGE_COLORS.length];
      const danger = pct > 90 ? "#ef4444" : pct > 70 ? "#f59e0b" : color;
      const dv    = val != null ? (Number.isInteger(val) ? val+"%" : val.toFixed(1)) : "—";
      return `<div class="bar-col">
        <div class="bar-val bar-val-${n}" style="color:${danger}">${dv}</div>
        <div class="bar-track">
          <div class="bar-fill bar-fill-${n}" style="height:${pct}%;background:${danger}"></div>
        </div>
        <div class="bar-label">${esc(label)}</div>
      </div>`;
    }).join("");
    const hasGauges = gaugeBars.trim().length > 0;

    // Live session block (compact, no background — sits between donut and gauges)
    const liveBlock = (() => {
      if (!s) return "";
      if (s.current_user) {
        const col = userColor(s.current_user, users);
        return `<div class="live-block" style="--live-color:${col}">
          <div class="live-user-row">
            <div class="lp-avatar" style="background:${col}">${s.current_user[0].toUpperCase()}</div>
            <div class="lp-info">
              <div class="lp-name">${esc(s.current_user)}</div>
              <div class="lp-badge">● LIVE</div>
            </div>
          </div>
          <div class="lp-stats">
            <div class="lp-stat"><span class="lp-val">${fmtTime(s.acc_time)}</span><span class="lp-lbl">Tid</span></div>
            <div class="lp-stat"><span class="lp-val">${fmtEnergy(s.acc_energy)}</span><span class="lp-lbl">Energi</span></div>
            <div class="lp-stat"><span class="lp-val">${fmtCost(s.acc_cost)}</span><span class="lp-lbl">Pris</span></div>
            <div class="lp-stat"><span class="lp-val live-watt">— W</span><span class="lp-lbl">Watt</span></div>
          </div>
        </div>`;
      } else {
        return `<div class="live-idle">Ingen aktiv session</div>`;
      }
    })();

    // Monthly user cards
    const userCardsHTML = users.map(u => {
      const d     = monthly[u] ?? {};
      const color = userColor(u, users);
      const isAct = s?.current_user === u;
      return `
        <div class="user-card ${isAct ? "user-card-active" : ""}" style="${isAct ? `border-color:${color}` : ""}">
          <div class="user-card-header">
            <div class="avatar sm" style="background:${color}">${u[0].toUpperCase()}</div>
            <div class="user-card-name">${esc(u)}</div>
            ${isAct ? `<span class="live-dot" style="color:${color}">●</span>` : ""}
          </div>
          <div class="user-stats">
            <div class="u-row"><span class="u-lbl">Tid</span><span class="u-val">${fmtTime(d.time)}</span></div>
            <div class="u-row"><span class="u-lbl">Energi</span><span class="u-val">${fmtEnergy(d.energy)}</span></div>
            <div class="u-row"><span class="u-lbl">Pris</span><span class="u-val">${fmtCost(d.cost)}</span></div>
          </div>
        </div>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          ${cssVars()}
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        .card {
          background: var(--bg);
          border-radius: 16px;
          padding: 16px 20px;
          color: var(--text);
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.15));
        }
        .card-title {
          font-size: 14px; font-weight: 700;
          text-transform: uppercase; letter-spacing: 1px;
          color: var(--sub); margin-bottom: 12px;
        }

        /* ── Two-column layout ── */
        .main-row {
          display: flex; gap: 14px; align-items: flex-start;
        }
        .left-col  { display: flex; flex-direction: column; gap: 10px; flex: 1; min-width: 0; }
        .right-col {
          display: flex; flex-direction: column; gap: 10px;
          flex-shrink: 0; width: 150px;
        }

        /* ── Monthly user cards ── */
        .user-card {
          background: var(--bg2); border-radius: 12px;
          padding: 12px; border: 1px solid transparent;
          transition: border-color .2s;
        }
        .user-card-active { border-width: 1px; border-style: solid; }
        .user-card-header {
          display: flex; align-items: center; gap: 8px; margin-bottom: 8px;
        }
        .user-card-name { font-size: 13px; font-weight: 700; text-transform: capitalize; flex: 1; }
        .live-dot { font-size: 10px; }
        .u-row {
          display: flex; justify-content: space-between; align-items: center;
          padding: 3px 0; border-bottom: 1px solid var(--div); font-size: 12px;
        }
        .u-row:last-child { border-bottom: none; }
        .u-lbl { color: var(--sub); }
        .u-val  { font-weight: 600; }

        /* ── Donut (top of right col) ── */
        .donut-wrap {
          display: flex; flex-direction: column; align-items: center; gap: 8px;
        }
        .donut-ring { position: relative; }
        .donut-svg  { width: 120px; height: 120px; display: block; }
        .donut-center {
          position: absolute; top: 50%; left: 50%;
          transform: translate(-50%,-50%); text-align: center; width: 70px;
        }
        .donut-top-user { font-size: 12px; font-weight: 700; text-transform: capitalize; white-space: nowrap; }
        .donut-top-pct  { font-size: 18px; font-weight: 800; color: var(--text); line-height: 1.1; }
        .donut-no-data  { font-size: 11px; color: var(--sub); }
        .donut-legend   { width: 100%; display: flex; flex-direction: column; gap: 4px; }
        .legend-row     { display: flex; align-items: center; gap: 6px; font-size: 11px; }
        .legend-dot     { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
        .legend-name    { flex: 1; text-transform: capitalize; }
        .legend-pct     { color: var(--sub); }

        /* ── Live session block (middle of right col) ── */
        .live-block {
          background: var(--bg2); border-radius: 10px;
          padding: 10px; border: 1px solid var(--live-color, transparent);
          display: flex; flex-direction: column; gap: 8px;
        }
        .live-user-row { display: flex; align-items: center; gap: 8px; }
        .lp-avatar {
          width: 26px; height: 26px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: 12px; font-weight: 700; color: #fff; flex-shrink: 0;
        }
        .lp-info { min-width: 0; }
        .lp-name  { font-size: 12px; font-weight: 700; text-transform: capitalize;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .lp-badge { font-size: 9px; color: #10b981; font-weight: 700; }
        .lp-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
        .lp-stat  { display: flex; flex-direction: column; gap: 1px; }
        .lp-val   { font-size: 11px; font-weight: 700; white-space: nowrap; }
        .lp-lbl   { font-size: 9px; color: var(--sub); text-transform: uppercase; letter-spacing: .3px; }
        .live-idle { font-size: 11px; color: var(--sub); text-align: center; padding: 4px 0; }

        /* ── Gauge bars (bottom of right col) ── */
        .gauge-bars {
          display: flex; gap: 6px; align-items: flex-end; height: 80px;
        }
        .bar-col {
          display: flex; flex-direction: column; align-items: center;
          gap: 2px; flex: 1; height: 100%;
        }
        .bar-val   { font-size: 9px; font-weight: 700; white-space: nowrap; min-height: 12px; line-height: 1; }
        .bar-track {
          flex: 1; width: 100%; background: rgba(255,255,255,0.08);
          border-radius: 4px; overflow: hidden;
          display: flex; flex-direction: column; justify-content: flex-end;
        }
        .bar-fill  { width: 100%; border-radius: 4px; transition: height .5s cubic-bezier(.4,0,.2,1); min-height: 2px; }
        .bar-label { font-size: 8px; color: var(--sub); text-transform: uppercase; letter-spacing: .3px; white-space: nowrap; }

        /* ── Avatar ── */
        .avatar    { width: 36px; height: 36px; border-radius: 50%;
                     display: flex; align-items: center; justify-content: center;
                     font-size: 16px; font-weight: 700; color: #fff; flex-shrink: 0; }
        .avatar.sm { width: 28px; height: 28px; font-size: 12px; }

        .section-label {
          font-size: 10px; font-weight: 600; text-transform: uppercase;
          letter-spacing: 1px; color: var(--sub); margin-bottom: 8px;
        }
        .loading { color: var(--sub); font-size: 13px; padding: 8px 0; }
      </style>
      <ha-card>
        <div class="card">
          <div class="card-title">${esc(title)}</div>
          <div class="section-label">Månedlige totaler</div>
          <div class="main-row">

            <div class="left-col">
              ${userCardsHTML || '<div class="loading">Ingen brugere</div>'}
            </div>

            <div class="right-col">
              ${s && users.length ? `<div class="donut-wrap">${this._donutSVG(users, monthly)}</div>` : ""}
              ${liveBlock}
              ${hasGauges ? `<div class="gauge-bars">${gaugeBars}</div>` : ""}
            </div>

          </div>
        </div>
      </ha-card>`;

    // Set live watt after render
    if (this._hass) this._updateWatt(this._hass);
  }

  getCardSize() { return 5; }
}

if (!customElements.get("pc-user-statistics-tablet-card")) {
  customElements.define("pc-user-statistics-tablet-card", PcUserStatisticsTabletCard);
}


// ─────────────────────────────────────────────────────────────────────────────
// Register cards in the Lovelace card picker
// ─────────────────────────────────────────────────────────────────────────────

window.customCards = window.customCards || [];

if (!window.customCards.find((c) => c.type === "pc-user-statistics-user-card")) {
  window.customCards.push({
    type:        "pc-user-statistics-user-card",
    name:        "PC User Statistics – Bruger",
    description: "Kompakt kort til én bruger – live session og månedlige tal (mobil-optimeret)",
    preview:     true,
    documentationURL: "https://github.com/kingpainter/pc_user_statistics",
  });
}

if (!window.customCards.find((c) => c.type === "pc-user-statistics-tablet-card")) {
  window.customCards.push({
    type:        "pc-user-statistics-tablet-card",
    name:        "PC User Statistics – Overblik",
    description: "Alle brugere side om side med live session og månedlige totaler (tablet/desktop)",
    preview:     true,
    documentationURL: "https://github.com/kingpainter/pc_user_statistics",
  });
}
