// PC User Statistics – Custom Lovelace Cards
// Version: 2.6.11
// Cards:
//   custom:pc-user-statistics-user-card   – compact single-user card (mobile)
//   custom:pc-user-statistics-tablet-card – all-users overview (tablet/desktop)
// Last Updated: August 8, 2026
//
// Changes in 2.6.11:
//   FIX: The JS-measured donut sizing from 2.6.9 (_sizeDonut(), based on
//        .right-col.clientWidth) was confirmed on-device to still be
//        landing on the small 180px CSS fallback, even after a genuine full
//        page reload (ruled out caching). Removed the JS measurement
//        entirely -- .donut-ring now sizes itself with the classic
//        "padding-bottom percentage" square trick (width:92%; height:0;
//        padding-bottom:92%), which has been reliable CSS since 2.1 with no
//        aspect-ratio, no calc() unit division, and no JS that can silently
//        fail. svg and the center %/name label are absolutely positioned to
//        fill the resulting box.
//
// Changes in 2.6.10:
//   FIX: _sizeDonut() (2.6.9) capped the ring at 340px, well below what the
//        actual ~570px-wide right column on the tablet allows -- donut
//        looked too small. Cap raised to 460px and the width fraction used
//        from 0.9 to 0.98.
//
// Changes in 2.6.9:
//   FIX: The 2.6.8 attempt to top-align the donut (justify-content:
//        flex-start on .donut-wrap + aspect-ratio:1/max-width:88% on
//        .donut-ring) did not reliably resolve on the tablet's WebView --
//        same class of quirk as the vh/px calc() bug fixed in 2.6.5. Ditched
//        the CSS flex-grow/aspect-ratio approach entirely: .donut-ring now
//        gets an explicit pixel width/height set in JS (_sizeDonut(), based
//        on the actual measured clientWidth of .right-col, capped 120-340px)
//        right after each render and on window resize. .donut-wrap is a
//        plain flex-shrink:0 block at the top of .right-col now, so it
//        naturally sits flush with the top of the left column -- no growth
//        or centering tricks needed.
//   NEW: Donut legend (Flemming/Lukas/Sebastian list) made much larger and
//        more prominent: legend-row font 13px -> 19px + semi-bold, dots
//        8px -> 14px, more row gap, bolder percentage text.
//
// Changes in 2.6.8:
//   NEW: Donut top now aligns with the top of Flemming's card instead of
//        sitting vertically centered in the right column. .donut-wrap
//        switched from justify-content:center to flex-start -- the leftover
//        flex space (donut-ring is width-constrained by the column, so it
//        doesn't consume its full flex-grown height) now collects below the
//        ring+legend instead of being split above/below. Ring also slightly
//        smaller (max-width 100% -> 88%) to feel less dominant next to the
//        left column.
//   NEW: Left column (Flemming/Lukas/Sebastian cards) text sizes increased
//        for readability at tablet-viewing distance: .user-card-name 13px
//        -> 20px, .u-row (Tid/Energi/Pris/Skærm rows) 12px -> 17px + bolder
//        value weight (600 -> 700), .avatar.sm 28px -> 40px.
//
// Changes in 2.6.7:
//   NEW: Right column donut on pc-user-statistics-tablet-card was still a
//        small fixed circle even after the 2.6.6 layout redesign, leaving
//        the right column visually empty/unbalanced next to the now-full-
//        height left column. .donut-wrap is now flex:1 so it consumes all
//        leftover vertical space in .right-col (live-block/gauge-bars below
//        keep their natural compact size); .donut-ring is sized purely via
//        aspect-ratio:1 off its own resolved flex height (capped by
//        max-width:100%), and the SVG fills that box at width/height:100%.
//        No magic pixel numbers -- it's a responsive square that grows or
//        shrinks to fill whatever space is actually available. Also bumped
//        the center %/name text and legend row font sizes to match the now
//        much larger ring.
//
// Changes in 2.6.6:
//   NEW: pc-user-statistics-tablet-card two-column layout redesigned as a
//        70/30 CSS grid split (grid-template-columns: 7fr 3fr) instead of
//        flex:1 + a fixed-width right column. Also: .user-card now uses
//        flex:1 so the 3 monthly user cards evenly share all available
//        vertical space in the left column, and the new .user-stats wrapper
//        uses justify-content:space-evenly so the Tid/Energi/Pris/Skærm rows
//        spread out to fill the taller card instead of clumping at the top.
//        .right-col uses the same space-evenly distribution for donut/live
//        session/gauges. Net effect: the card now genuinely fills all
//        available height on the tablet instead of leaving dead space below
//        a fixed-size content block.
//
// Changes in 2.6.5:
//   FIX: --sm-scale-h never actually scaled on the real tablet -- width
//        adapted (plain flex/%, unrelated to the scale factor) but height
//        stayed flat, leaving dead space below the card. Root cause:
//        calc(100vh / 800px) divides two different CSS units (vh and px)
//        inside calc(), which is not reliably computed the same way across
//        WebViews -- it apparently silently fell back to the property's
//        initial value on the tablet's kiosk browser, even though it looked
//        fine in a desktop browser during development. Replaced with a JS
//        computation (_updateScale(), based on window.innerHeight) pushed
//        onto the host element via style.setProperty("--sm-scale-h", ...),
//        run on connectedCallback/setConfig and kept in sync with a resize
//        listener. This always works regardless of engine calc() quirks.
//
// Changes in 2.6.4:
//   FIX: .right-col kept a fixed width:150px while its contents (.donut-svg,
//        avatars) were scaled up by --sm-scale-h (v2.6.3) for the taller
//        11" tablet. At scale 1.5x the donut grew to 180px but the column
//        stayed 150px wide, so the right column visually overflowed its
//        intended width, squeezing .left-col narrower than intended even
//        though .left-col's own CSS was untouched. .right-col width is now
//        calc(150px * var(--sm-scale-h)) so it scales with its contents.
//
// Changes in 2.6.3:
//   FIX: pc-user-statistics-tablet-card was designed against the old 7"
//        1280x800 Lenovo tablet and left dead space at the bottom on the
//        new 11" Samsung Tab A11+ (1920x1200, same 16:10 ratio). Added a
//        --sm-scale-h height-driven scale factor (clamp(0.8, 100vh/800px,
//        1.8)), same pattern as secure_me_alarm_tab_card.js, and wrapped
//        vertical paddings/gaps/font-sizes/element heights in calc()
//        so the card scales up to fill the taller viewport. Width/column
//        layout untouched -- height only, as requested.
//
// Changes in 2.6.2:
//   FIX: pc-user-statistics-tablet-card was still a little too tall for a 7"
//        tablet panel view — the left column (stacked user cards) overflowed
//        below the visible screen while the right column fit fine. Trimmed
//        vertical padding/gaps in .card, .card-title, .left-col, .user-card,
//        .user-card-header and .u-row to reclaim ~65-70px of height. No
//        layout/structure changes, purely spacing.
//
// Changes in 2.6.1:
//   FIX: pc-user-statistics-tablet-card filled a Lovelace `type: panel` view
//        incorrectly (small centered card instead of full screen on 7" tablet).
//        :host now sets height:100%; ha-card is a 100%-height flex column
//        with overflow:hidden; .card and .main-row use flex:1 + min-height:0
//        so they scale to the panel instead of shrinking/overflowing.
//        (Same pattern as secure_me_alarm_tab_card.js .root container.)
//
// Changes in 2.6.0:
//   NEW: Microsoft Family Safety screen_time shown in both cards
//   NEW: Active avatar glow ring on live session
//   NEW: Monthly stat boxes get icons and accent tint for active user
//   UPX: Leaderboard bars thicker (5px) with smooth width transition

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

function fmtScreenTime(min) {
  if (min == null || min < 0) return null;
  if (min === 0) return "0m";
  const h = Math.floor(min / 60);
  const m = min % 60;
  return h > 0 ? `${h}t ${m}m` : `${m}m`;
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
    this._fs      = null;
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
      const [stats, fs] = await Promise.all([
        this._hass.callWS({ type: `${DOMAIN}/get_stats` }),
        this._hass.callWS({ type: `${DOMAIN}/get_family_safety` }).catch(() => null),
      ]);
      this._stats = stats;
      if (fs) this._fs = fs;
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

    // Microsoft Family Safety screen_time for this user
    const fsUser  = this._fs?.users?.[user];
    const fsMin   = fsUser?.screen_time_min ?? null;
    const fsFmt   = fmtScreenTime(fsMin);

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
        .avatar-glow { box-shadow: 0 0 0 3px var(--glow-color, transparent), 0 0 12px 2px var(--glow-color, transparent); transition: box-shadow .4s; }
        .ms-row { display:flex; align-items:center; gap:6px; margin-top:6px; padding:6px 8px; background:rgba(139,92,246,0.10); border-radius:8px; border-left:3px solid #8b5cf6; }
        .ms-label { font-size:10px; color:#8b5cf6; font-weight:600; text-transform:uppercase; letter-spacing:.5px; flex:1; }
        .ms-val   { font-size:13px; font-weight:700; color:#8b5cf6; }

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
        .m-icon { font-size: 16px; margin-bottom: 2px; }
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
          height: 5px; background: var(--div); border-radius: 3px;
          margin-top: 5px; overflow: hidden;
        }
        .lb-bar-fill { height: 100%; border-radius: 3px; transition: width .6s cubic-bezier(.4,0,.2,1); }

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
            <div class="avatar ${isActive ? 'avatar-glow' : ''}" style="--glow-color:${isActive ? color+'99' : 'transparent'}">${initial}</div>
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
            ${fsFmt ? `
            <div class="ms-row">
              <span class="ms-label">🖥️ Skærm tid i dag</span>
              <span class="ms-val">${fsFmt}</span>
            </div>` : ""}
            <div style="display:none"><!-- ms-placeholder-end -->
            </div>

            <div class="divider"></div>

            <div class="section-label">Denne måned</div>
            <div class="monthly-grid">
              <div class="m-box" style="${isActive ? `border:1px solid ${color}33;background:${color}11` : ''}">
                <div class="m-icon">⏱️</div>
                <div class="m-val">${fmtTime(monthly.time)}</div>
                <div class="m-lbl">Tid</div>
              </div>
              <div class="m-box" style="${isActive ? `border:1px solid ${color}33;background:${color}11` : ''}">
                <div class="m-icon">⚡</div>
                <div class="m-val">${fmtEnergy(monthly.energy)}</div>
                <div class="m-lbl">Energi</div>
              </div>
              <div class="m-box" style="${isActive ? `border:1px solid ${color}33;background:${color}11` : ''}">
                <div class="m-icon">💰</div>
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
    this._fs         = null;
    this._config     = {};
    this._gaugeConfig = null; // loaded once from get_config
    this._interval   = null;
    this._errCount   = 0;
  }

  setConfig(config) {
    this._config = config ?? {};
    this._updateScale();
    this._render();
  }

  // v2.6.5: CSS calc(100vh / 800px) — dividing a vh unit by a px unit inside
  // calc() — is not reliably supported across WebViews (notably older
  // Android WebView engines used by kiosk browsers like Fully Kiosk). The
  // custom property silently fell back to its initial value there, so
  // --sm-scale-h never actually scaled up on the tablet even though it
  // worked fine in a desktop browser. Computed in JS instead and pushed as
  // an inline custom property on the host element — always works.
  _updateScale() {
    const h = window.innerHeight || 800;
    const scale = Math.min(1.8, Math.max(0.8, h / 800));
    this.style.setProperty("--sm-scale-h", scale.toFixed(4));
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
      const [stats, cfg, fs] = await Promise.all([
        this._hass.callWS({ type: `${DOMAIN}/get_stats` }),
        this._hass.callWS({ type: `${DOMAIN}/get_config` }),
        this._hass.callWS({ type: `${DOMAIN}/get_family_safety` }).catch(() => null),
      ]);
      this._stats = stats;
      this._gaugeConfig = cfg;
      if (fs) this._fs = fs;
      this._errCount = 0;
    } catch (e) {
      this._errCount++;
      console.error("PcTabletCard load error:", e);
    }
    this._render();
  }

  connectedCallback() {
    this._updateScale();
    this._resizeHandler = () => this._updateScale();
    window.addEventListener("resize", this._resizeHandler);
    this._interval = setInterval(() => {
      if (this._errCount > 5) { clearInterval(this._interval); return; }
      if (document.visibilityState === "visible") this._loadStats();
    }, 30000);
  }

  disconnectedCallback() {
    clearInterval(this._interval);
    if (this._resizeHandler) window.removeEventListener("resize", this._resizeHandler);
  }

  // Polling: refresh stats + family safety (gauge config is static, loaded once)
  async _loadStats() {
    if (!this._hass) return;
    try {
      const [stats, fs] = await Promise.all([
        this._hass.callWS({ type: `${DOMAIN}/get_stats` }),
        this._hass.callWS({ type: `${DOMAIN}/get_family_safety` }).catch(() => null),
      ]);
      this._stats = stats;
      if (fs) this._fs = fs;
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
      const d      = monthly[u] ?? {};
      const color  = userColor(u, users);
      const isAct  = s?.current_user === u;
      const fsMin  = this._fs?.users?.[u]?.screen_time_min ?? null;
      const fsFmt  = fmtScreenTime(fsMin);
      const glowStyle = isAct ? `box-shadow:0 0 0 2px ${color}99,0 0 10px 1px ${color}66` : "";
      return `
        <div class="user-card ${isAct ? "user-card-active" : ""}" style="${isAct ? `border-color:${color}` : ""}">
          <div class="user-card-header">
            <div class="avatar sm" style="background:${color};${glowStyle}">${u[0].toUpperCase()}</div>
            <div class="user-card-name">${esc(u)}</div>
            ${isAct ? `<span class="live-dot" style="color:${color}">●</span>` : ""}
          </div>
          <div class="user-stats">
            <div class="u-row"><span class="u-lbl">⏱️ Tid</span><span class="u-val">${fmtTime(d.time)}</span></div>
            <div class="u-row"><span class="u-lbl">⚡ Energi</span><span class="u-val">${fmtEnergy(d.energy)}</span></div>
            <div class="u-row"><span class="u-lbl">💰 Pris</span><span class="u-val">${fmtCost(d.cost)}</span></div>
            ${fsFmt ? `<div class="u-row u-ms"><span class="u-lbl" style="color:#8b5cf6">🖥️ Skærm</span><span class="u-val" style="color:#8b5cf6">${fsFmt}</span></div>` : ""}
          </div>
        </div>`;
    }).join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          height: 100%;
          /* v2.6.5: fallback only — actual value is set at runtime via
             this.style.setProperty() in _updateScale() (JS), because
             calc(100vh / 800px) below (kept as a comment for history) does
             not reliably compute in all WebViews:
             OLD: --sm-scale-h: clamp(0.8, calc(100vh / 800px), 1.8); */
          --sm-scale-h: 1;
          ${cssVars()}
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
        }
        ha-card {
          width: 100%;
          height: 100%;
          min-height: 0;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .card {
          flex: 1;
          min-height: 0;
          display: flex;
          flex-direction: column;
          background: var(--bg);
          border-radius: 16px;
          padding: calc(12px * var(--sm-scale-h)) 20px;
          color: var(--text);
          box-shadow: var(--ha-card-box-shadow, 0 2px 8px rgba(0,0,0,.15));
          overflow: auto;
        }
        .card-title {
          font-size: calc(14px * var(--sm-scale-h)); font-weight: 700;
          text-transform: uppercase; letter-spacing: 1px;
          color: var(--sub); margin-bottom: calc(8px * var(--sm-scale-h));
          flex-shrink: 0;
        }

        /* ── Two-column layout ── */
        /* v2.6.6: 70/30 split via CSS grid (fr units), replacing the old
           flex:1 + fixed-width right column. fr units auto-adjust to any
           tablet width and correctly account for the gap, so both columns
           always keep their intended ratio. Grid's default align-items:
           stretch also makes both columns take the full row height, which
           combined with flex:1 on .user-card + justify-content:space-evenly
           below is what makes the card fill all available height instead of
           leaving dead space at the bottom. */
        .main-row {
          display: grid;
          grid-template-columns: 7fr 3fr;
          gap: 14px;
          flex: 1;
          min-height: 0;
        }
        .left-col  {
          display: flex; flex-direction: column; gap: calc(6px * var(--sm-scale-h));
          min-width: 0; min-height: 0;
        }
        .right-col {
          display: flex; flex-direction: column; gap: calc(10px * var(--sm-scale-h));
          min-width: 0; min-height: 0;
        }

        /* ── Monthly user cards ── */
        /* v2.6.6: flex:1 makes the 3 user-cards evenly share whatever height
           .left-col has available (instead of sizing purely by content).
           .user-stats below then gets justify-content:space-evenly so the
           rows spread out to fill the taller card instead of clumping at
           the top with blank space underneath. */
        .user-card {
          flex: 1;
          display: flex; flex-direction: column;
          background: var(--bg2); border-radius: 12px;
          padding: calc(9px * var(--sm-scale-h)) 16px; border: 1px solid transparent;
          transition: border-color .2s;
        }
        .user-card-active { border-width: 1px; border-style: solid; }
        .user-card-header {
          display: flex; align-items: center; gap: 10px; margin-bottom: calc(6px * var(--sm-scale-h));
          flex-shrink: 0;
        }
        .user-card-name { font-size: calc(20px * var(--sm-scale-h)); font-weight: 700; text-transform: capitalize; flex: 1; }
        .live-dot { font-size: 10px; }
        .user-stats {
          flex: 1;
          display: flex; flex-direction: column;
          justify-content: space-evenly;
          min-height: 0;
        }
        .u-row {
          display: flex; justify-content: space-between; align-items: center;
          padding: calc(2px * var(--sm-scale-h)) 0; border-bottom: 1px solid var(--div); font-size: calc(17px * var(--sm-scale-h));
        }
        .u-row:last-child { border-bottom: none; }
        .u-ms { background: rgba(139,92,246,0.07); border-radius: 4px; padding-left: 3px; margin-top: 2px; }
        .u-lbl { color: var(--sub); }
        .u-val  { font-weight: 700; }

        /* ── Donut (top of right col) ── */
        /* v2.6.11: JS-measured sizing (_sizeDonut(), 2.6.9) turned out to be
           just as unreliable on this tablet's WebView as the earlier
           aspect-ratio/calc(vh/px) attempts — whatever the reason, it kept
           landing back on the 180px CSS fallback. Replaced with the classic
           "padding-bottom percentage" square trick instead: a block's
           padding-bottom percentage is always resolved against its parent's
           WIDTH regardless of axis, which has been reliable CSS since 2.1 —
           no aspect-ratio, no calc() unit division, no JS measurement, no
           moving parts to silently fail. .donut-ring becomes a 92%-wide,
           92%-tall (via padding-bottom) square purely from CSS; svg and the
           center label are absolutely positioned to fill that box. */
        .donut-wrap {
          display: flex; flex-direction: column; align-items: center;
          gap: calc(8px * var(--sm-scale-h));
          flex-shrink: 0; width: 100%;
        }
        .donut-ring {
          position: relative;
          flex-shrink: 0;
          width: 92%;
          height: 0;
          padding-bottom: 92%;
        }
        .donut-svg  { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: block; }
        .donut-center {
          position: absolute; top: 50%; left: 50%;
          transform: translate(-50%,-50%); text-align: center; width: 60%;
        }
        .donut-top-user { font-size: calc(20px * var(--sm-scale-h)); font-weight: 700; text-transform: capitalize; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .donut-top-pct  { font-size: calc(34px * var(--sm-scale-h)); font-weight: 800; color: var(--text); line-height: 1.1; }
        .donut-no-data  { font-size: 11px; color: var(--sub); }
        .donut-legend   { width: 100%; display: flex; flex-direction: column; gap: calc(9px * var(--sm-scale-h)); margin-top: calc(4px * var(--sm-scale-h)); }
        .legend-row     { display: flex; align-items: center; gap: 10px; font-size: calc(19px * var(--sm-scale-h)); font-weight: 600; }
        .legend-dot     { width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }
        .legend-name    { flex: 1; text-transform: capitalize; color: var(--text); }
        .legend-pct     { color: var(--sub); font-weight: 700; }

        /* ── Live session block (middle of right col) ── */
        .live-block {
          background: var(--bg2); border-radius: 10px;
          padding: calc(10px * var(--sm-scale-h)); border: 1px solid var(--live-color, transparent);
          display: flex; flex-direction: column; gap: calc(8px * var(--sm-scale-h));
        }
        .live-user-row { display: flex; align-items: center; gap: 8px; }
        .lp-avatar {
          width: calc(26px * var(--sm-scale-h)); height: calc(26px * var(--sm-scale-h)); border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: calc(12px * var(--sm-scale-h)); font-weight: 700; color: #fff; flex-shrink: 0;
        }
        .lp-info { min-width: 0; }
        .lp-name  { font-size: calc(12px * var(--sm-scale-h)); font-weight: 700; text-transform: capitalize;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .lp-badge { font-size: 9px; color: #10b981; font-weight: 700; }
        .lp-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
        .lp-stat  { display: flex; flex-direction: column; gap: 1px; }
        .lp-val   { font-size: calc(11px * var(--sm-scale-h)); font-weight: 700; white-space: nowrap; }
        .lp-lbl   { font-size: 9px; color: var(--sub); text-transform: uppercase; letter-spacing: .3px; }
        .live-idle { font-size: 11px; color: var(--sub); text-align: center; padding: 4px 0; }

        /* ── Gauge bars (bottom of right col) ── */
        .gauge-bars {
          display: flex; gap: 6px; align-items: flex-end; height: calc(80px * var(--sm-scale-h));
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
        .avatar    { width: calc(36px * var(--sm-scale-h)); height: calc(36px * var(--sm-scale-h)); border-radius: 50%;
                     display: flex; align-items: center; justify-content: center;
                     font-size: calc(16px * var(--sm-scale-h)); font-weight: 700; color: #fff; flex-shrink: 0; }
        .avatar.sm { width: calc(40px * var(--sm-scale-h)); height: calc(40px * var(--sm-scale-h)); font-size: calc(18px * var(--sm-scale-h)); }

        .section-label {
          font-size: calc(10px * var(--sm-scale-h)); font-weight: 600; text-transform: uppercase;
          letter-spacing: 1px; color: var(--sub); margin-bottom: calc(6px * var(--sm-scale-h));
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
