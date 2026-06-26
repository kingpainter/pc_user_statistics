// PC User Statistics Panel
// Version: 3.2.0 — Vanilla JS (no imports)
// Last Updated: June 26, 2026
//
// Changes in 3.2.0:
//   FIX 1: watt-entity læses fra this._config?.watt_entity i stedet for hardcodet
//           entity ID — watt-ringen opdateres korrekt når entity ændres via config.
//   FIX 2: Admin health-grid viser nu flush_timer_active (grøn/rød Flush-timer metric).
//           statusBar inkluderer timer-status i allOk-beregning og statusLabel.
//   FIX 3: Sticky Gem-knap i Config-tab — position:sticky bottom:0 så knappen
//           altid er synlig uden at scrolle til bunden af den lange formular.
//   FIX 4: Historik-tab skeleton loader — spinner + animerede placeholder-bars
//           i stedet for en tom tom tekst-linje.
//   FIX 5: Live idle-state viser nu hvem der ledte måneden i stedet for
//           den kryptiske "data tilgængeligt i Statistik"-tekst.
//   FIX 6: Donut vises øverst i Statistik-tab på mobil (via .statistik-donut-mobile)
//           — .statistik-right skjules, donut-mobile vises. Desktop uændret.
//   FIX 7: Notifikationer-tab: 24px margin-top på Premade regler-sektionen
//           giver tydeligt visuelt skel fra devices-sektionen.
//
// Changes in 3.1.0:
//   NEW: Manual correction form on Admin tab — "Manuel korrektion".
//        Lets the user add a one-off time/energy/cost entry for a missed
//        session (e.g. files were overwritten mid-session and live tracking
//        never registered it). Calls pc_user_statistics/add_manual_entry,
//        which writes a source=manual InfluxDB point and reloads monthly
//        totals immediately.
//
// Changes in 2.9.0 — UI/UX improvements:
//   FIX: Tab labels always visible on desktop — only hidden on mobile (<600px)
//   FIX: Live-tab gauge layout — gauges now in proper 3-col flex alongside session stats
//   FIX: "unavailable" gauges skipped silently — show "—" without the word "unavailable"
//   FIX: Statistik-tab users with 0 data still show card (not skipped)
//   FIX: Watt-ring color-coded: green <100W, orange 100-250W, red >250W
//   FIX: Statistik-tab 2-col layout now stack-aware — donut moves below on narrow screens
//   NEW: LIVE badge on active user's monthly card on Statistik-tab
//   NEW: Idle-state on Live-tab when no session active — "PC klar" with dim styling
//   NEW: Pulse animation on session-time stat when session is active
//   NEW: Today marker (vertical line) on History bar chart
//   NEW: Total sum footer on Leaderboard ("Samlet: Xt Ym · X,XX kr")
//   NEW: "Sidst sendt" timestamp on each notification rule card
//   NEW: Health-metric cards include a one-line explanation tooltip/sub-label
//   NEW: Statistik-tab month total footer row with combined sum

class PcUserStatisticsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass        = null;
    this._tab         = "live";
    this._history     = null;
    this._histMetric  = "time";
    this._stats       = null;
    this._system      = null;
    this._health      = null;
    this._notif       = null;
    this._savingRule  = null;
    this._editingRule = null;
    this._showCreate  = false;
    this._newRule     = this._emptyRule();
    this._interval    = null;
    this._watt        = null;
    this._gaugeStates = { gauge1:null, gauge2:null, gauge3:null, gauge4:null, gauge5:null };
    this._errCount    = 0;
    this._isDark      = false;
    this._config      = null;
    this._configSaving= false;
    this._configState = null;
    this._forceRender = false;
    this._tabOrder    = this._loadTabOrder();
    this._dragSrc     = null;
    this._haUsers     = [];
    this._fs          = null;  // Microsoft Family Safety data
    this._manualSaving= false; // Admin tab: manual correction in progress
    this._manualMsg   = null;  // Admin tab: manual correction result banner
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    this._isDark = h.themes?.darkMode ?? (window.matchMedia?.("(prefers-color-scheme:dark)").matches ?? false);
    if (first) this._load();
    const wattEntity = this._config?.watt_entity || "sensor.gamer_pc_power_monitor_current_consumption";
    const st = h.states?.[wattEntity];
    const raw = st ? parseFloat(st.state) : null;
    this._watt = raw && !isNaN(raw) ? raw : null;
    this._updateGaugeStates();
    if (this._tab === "live") this._updateBarsInPlace();
    this._updateWattDisplay();
  }

  connectedCallback() {
    this._render();
    this._interval = setInterval(() => {
      if (this._errCount > 3) { clearInterval(this._interval); return; }
      if (document.visibilityState === "visible") this._loadForTab();
    }, 30000);
  }

  disconnectedCallback() { clearInterval(this._interval); }

  _updateWattDisplay() {
    const el = this.shadowRoot?.querySelector(".watt-value");
    if (!el) return;
    el.textContent = this._watt != null ? this._watt.toFixed(0)+"W" : "—";
    const ring = this.shadowRoot?.querySelector(".watt-ring");
    if (!ring) return;
    const w = this._watt || 0;
    ring.style.opacity = w > 5 ? "1" : "0.35";
    const color = w > 250 ? "#ef4444" : w > 100 ? "#f59e0b" : "#10b981";
    ring.style.borderColor = w > 5 ? color : "var(--div)";
    const valEl = this.shadowRoot?.querySelector(".watt-value");
    if (valEl) valEl.style.color = w > 5 ? color : "var(--sub)";
  }

  _updateGaugeStates() {
    if (!this._hass || !this._config) return;
    const cfg = this._config;
    [1,2,3,4,5].forEach(n => {
      const key = `gauge${n}`;
      const entity = cfg[`${key}_entity`];
      if (entity) {
        const s = this._hass.states?.[entity];
        this._gaugeStates[key] = s ? s.state : null;
      } else {
        this._gaugeStates[key] = null;
      }
    });
  }

  // ── Data loading ──────────────────────────────────────────────

  async _load() {
    if (!this._hass) return;
    try {
      const [stats, system, notif, config, fs] = await Promise.all([
        this._hass.callWS({ type: "pc_user_statistics/get_stats" }),
        this._hass.callWS({ type: "pc_user_statistics/get_system" }),
        this._hass.callWS({ type: "pc_user_statistics/get_notifications" }),
        this._hass.callWS({ type: "pc_user_statistics/get_config" }),
        this._hass.callWS({ type: "pc_user_statistics/get_family_safety" }).catch(()=>null),
      ]);
      this._stats  = stats;
      this._system = system;
      this._notif  = notif;
      if (config) this._config = config;
      if (fs) this._fs = fs;
      this._errCount = 0;
    } catch(e) { this._errCount++; console.error("PC Stats load error:", e); }
    this._updateGaugeStates();
    this._render();
  }

  async _loadForTab() {
    if (!this._hass) return;
    try {
      const tab = this._tab;
      if (tab === "live" || tab === "statistik") {
        const [stats, fs] = await Promise.all([
          this._hass.callWS({ type: "pc_user_statistics/get_stats" }),
          this._hass.callWS({ type: "pc_user_statistics/get_family_safety" }).catch(()=>null),
        ]);
        this._stats = stats;
        if (fs) this._fs = fs;
      } else if (tab === "notifications") {
        const [stats, notif] = await Promise.all([
          this._hass.callWS({ type: "pc_user_statistics/get_stats" }),
          this._hass.callWS({ type: "pc_user_statistics/get_notifications" }),
        ]);
        this._stats = stats; this._notif = notif;
      } else if (tab === "admin") {
        const [stats, system, health] = await Promise.all([
          this._hass.callWS({ type: "pc_user_statistics/get_stats" }),
          this._hass.callWS({ type: "pc_user_statistics/get_system" }),
          this._hass.callWS({ type: "pc_user_statistics/get_health" }),
        ]);
        this._stats = stats; this._system = system; this._health = health;
      }
      this._errCount = 0;
    } catch(e) { this._errCount++; console.error("PC Stats poll error:", e); }
    this._render();
  }

  async _loadHistory() {
    if (!this._hass) return;
    try {
      this._history = await this._hass.callWS({ type: "pc_user_statistics/get_history", days: 30 });
    } catch(e) {
      this._history = { days:[], users:[], series:{} };
    }
    this._render();
  }

  // ── Formatters ────────────────────────────────────────────────
  _fmtTime(s)   { if (!s || s < 0) return "0t 0m"; return `${Math.floor(s/3600)}t ${Math.floor((s%3600)/60)}m`; }
  _fmtEnergy(k) { return k ? k.toFixed(3).replace(".",",")+" kWh" : "0,000 kWh"; }
  _fmtCost(d)   { return d ? d.toFixed(2).replace(".",",")+" kr"  : "0,00 kr"; }
  _fmtAge(s)    {
    if (s == null) return "aldrig";
    if (s < 60)   return `${s}s siden`;
    if (s < 3600) return `${Math.floor(s/60)}m siden`;
    return `${Math.floor(s/3600)}t ${Math.floor((s%3600)/60)}m siden`;
  }
  _fmtTs(ts) {
    if (!ts) return null;
    const d = new Date(ts * 1000);
    const now = new Date();
    const diffM = Math.round((now - d) / 60000);
    if (diffM < 1)   return "lige nu";
    if (diffM < 60)  return `${diffM}m siden`;
    if (diffM < 1440) return `${Math.floor(diffM/60)}t siden`;
    return d.toLocaleDateString("da-DK", { day:"numeric", month:"short" });
  }
  _userColor(n) {
    const cols = ["#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1"];
    const users = this._stats?.tracked_users ?? [];
    const idx = users.indexOf((n||"").toLowerCase());
    if (idx >= 0) return cols[idx % cols.length];
    let h = 0; for (const c of n||"") h = c.charCodeAt(0)+h*31;
    return cols[Math.abs(h)%cols.length];
  }
  _triggerLabel(type, val) {
    if (type==="session_minutes") return `Efter ${val} min spiltid`;
    if (type==="session_cost")    return `Når session koster ${val} kr`;
    if (type==="idle_minutes")    return `PC inaktiv i ${val} min`;
    return type;
  }
  _emptyRule() {
    return { id:"", name:"", icon:"🔔", trigger_type:"session_minutes",
      trigger_value:60, title:"🔔 {user} — besked", message:"Du har spillet i {time}.",
      repeat:false, repeat_interval:60, enabled:false, user_targets:[], is_custom:true };
  }
  _esc(s) {
    return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
  }

  // ── Notification actions ──────────────────────────────────────
  async _toggleRule(ruleId) {
    const rule = this._notif.rules[ruleId];
    const updated = { ...rule, enabled: !rule.enabled };
    try {
      await this._hass.callWS({ type:"pc_user_statistics/save_notification", rule_id:ruleId, config:updated });
      this._notif.rules[ruleId] = updated;
    } catch(e) { console.error(e); }
    this._render();
  }

  async _saveRule(ruleId, config) {
    this._savingRule = ruleId; this._render();
    try {
      await this._hass.callWS({ type:"pc_user_statistics/save_notification", rule_id:ruleId, config });
      this._notif.rules[ruleId] = config;
      if (ruleId === (this._newRule.id||"new")) { this._showCreate = false; this._newRule = this._emptyRule(); }
      this._editingRule = null;
    } catch(e) { console.error(e); }
    this._savingRule = null; this._render();
  }

  async _deleteRule(ruleId) {
    if (!confirm("Slet denne regel?")) return;
    try {
      await this._hass.callWS({ type:"pc_user_statistics/delete_notification", rule_id:ruleId });
      delete this._notif.rules[ruleId];
    } catch(e) { alert("Kan ikke slette premade regler"); }
    this._render();
  }

  async _testRule(ruleId) {
    const user = (this._stats?.tracked_users||[])[0]||"flemming";
    try {
      await this._hass.callWS({ type:"pc_user_statistics/test_notification", rule_id:ruleId, user });
      const btn = this.shadowRoot.querySelector(`[data-test="${ruleId}"]`);
      if (btn) { btn.textContent="✅ Sendt!"; setTimeout(()=>{ btn.textContent="📨 Test"; },2000); }
    } catch(e) { console.error(e); }
  }

  async _saveDevices(devices) {
    try {
      await this._hass.callWS({ type:"pc_user_statistics/save_devices", devices });
      this._notif.devices = devices;
    } catch(e) { console.error(e); }
    this._render();
  }

  // ── Manual correction (Admin tab) ───────────────────────────────
  async _saveManualEntry() {
    const root = this.shadowRoot;
    const user   = root.getElementById("manual-user")?.value;
    const date   = root.getElementById("manual-date")?.value;
    const timeMin = parseFloat(root.getElementById("manual-time")?.value);
    const energy  = parseFloat(root.getElementById("manual-energy")?.value) || 0;
    const cost    = parseFloat(root.getElementById("manual-cost")?.value) || 0;

    if (!user || !date || !timeMin || timeMin <= 0) {
      this._manualMsg = { ok:false, text:"Udfyld bruger, dato og tid (minutter) f\u00f8r du gemmer." };
      this._render();
      return;
    }

    this._manualSaving = true; this._manualMsg = null; this._render();
    try {
      await this._hass.callWS({
        type: "pc_user_statistics/add_manual_entry",
        user, date,
        time_minutes: timeMin,
        energy_kwh: energy,
        cost_dkk: cost,
      });
      this._manualMsg = { ok:true, text:`\u2705 Korrektion tilf\u00f8jet: ${user}, ${date}, ${timeMin} min.` };
      // Refresh stats so the updated monthly total shows immediately
      try { this._stats = await this._hass.callWS({ type:"pc_user_statistics/get_stats" }); } catch(e) {}
    } catch(e) {
      this._manualMsg = { ok:false, text:`\u274c Fejl: ${e.message||e}` };
    }
    this._manualSaving = false; this._render();
  }

  // ── Tab order ─────────────────────────────────────────────────
  static get ALL_TABS() {
    return [
      {id:"live",          label:"Live",           icon:"🎮"},
      {id:"statistik",     label:"Statistik",      icon:"📊"},
      {id:"notifications", label:"Notifikationer", icon:"🔔"},
      {id:"history",       label:"Historik",       icon:"📈"},
      {id:"config",        label:"Konfiguration",  icon:"🔧"},
      {id:"admin",         label:"Admin",          icon:"⚙️"},
    ];
  }

  _loadTabOrder() {
    try {
      const saved = localStorage.getItem("pc_stats_tab_order");
      if (saved) {
        const ids = JSON.parse(saved);
        const allIds = PcUserStatisticsPanel.ALL_TABS.map(t=>t.id);
        const valid = ids.filter(id=>allIds.includes(id));
        allIds.forEach(id=>{ if (!valid.includes(id)) valid.push(id); });
        return valid;
      }
    } catch(e) {}
    return PcUserStatisticsPanel.ALL_TABS.map(t=>t.id);
  }

  _saveTabOrder(order) {
    try { localStorage.setItem("pc_stats_tab_order", JSON.stringify(order)); } catch(e) {}
    this._tabOrder = order;
  }

  _orderedTabs() {
    const all = PcUserStatisticsPanel.ALL_TABS;
    return this._tabOrder.map(id=>all.find(t=>t.id===id)).filter(Boolean);
  }

  // ── Config ────────────────────────────────────────────────────
  async _loadConfig() {
    if (!this._hass) return;
    try { this._config = await this._hass.callWS({ type:"pc_user_statistics/get_config" }); }
    catch(e) { this._config = {}; }
    // If get_config didn't return family_safety_mappings (old code in RAM),
    // try fetching it from get_family_safety which has the mappings in response
    if (this._config && !this._config.family_safety_mappings) {
      try {
        const fs = await this._hass.callWS({ type:"pc_user_statistics/get_family_safety" });
        if (fs?.mappings) this._config.family_safety_mappings = fs.mappings;
      } catch(e) { /* not yet available */ }
    }
    this._updateGaugeStates(); this._render();
  }

  async _loadHaUsers() {
    try {
      const result = await this._hass.callWS({ type:"config/auth/list" });
      this._haUsers = (result||[]).map(u=>({ id:u.id, name:u.name }));
      this._render();
    } catch(e) {}
  }

  // ── Gauge helper ──────────────────────────────────────────────
  _gaugeDisplay(key, cfg) {
    const rawVal = this._gaugeStates[key];
    const maxStr = cfg[`${key}_max`];
    const label  = (cfg[`${key}_label`]||"").toLowerCase();
    // Skip unavailable/unknown states
    if (rawVal === null || rawVal === undefined || rawVal === "unavailable" || rawVal === "unknown") {
      return { pct:0, display:"—", label:cfg[`${key}_label`]||"", unavailable:true };
    }
    const num = parseFloat(rawVal);
    if (isNaN(num)) return { pct:0, display:"—", label:cfg[`${key}_label`]||"", unavailable:true };
    if (maxStr && parseFloat(maxStr) > 0) {
      const max = parseFloat(maxStr);
      const pct = Math.min(Math.round(num/max*100), 100);
      return { pct, display:pct+"%", label:cfg[`${key}_label`]||"", unavailable:false };
    }
    if (num >= 0 && num <= 100) {
      const suffix = label.includes("temp") ? "°C" : (label.includes("%") ? "%" : "");
      return { pct:num, display:num.toFixed(0)+suffix, label:cfg[`${key}_label`]||"", unavailable:false };
    }
    const unit = label.match(/mhz|ghz|rpm|mb|gb/i)?.[0]?.toUpperCase()||"";
    return { pct:50, display:num.toFixed(0)+(unit?" "+unit:""), label:cfg[`${key}_label`]||"", unavailable:false };
  }

  _updateBarsInPlace() {
    if (!this._config) return;
    const cfg = this._config;
    [1,2,3,4,5].forEach(n=>{
      const key = `gauge${n}`;
      if (!cfg[`${key}_entity`]) return;
      const g = this._gaugeDisplay(key, cfg);
      const bar = this.shadowRoot?.querySelector(`.gauge-bar-fill[data-gauge="${key}"]`);
      const val = this.shadowRoot?.querySelector(`.gauge-val[data-gauge="${key}"]`);
      if (bar) bar.style.width = g.pct+"%";
      if (val) val.textContent = g.display;
    });
  }

  // ── CSS ───────────────────────────────────────────────────────
  _css() { return `
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
    *, *::before, *::after { box-sizing:border-box; }
    :host {
      display:block; height:100%;
      font-family:'DM Sans', var(--paper-font-body1_-_font-family, sans-serif);
      --accent:#8b5cf6; --accent2:#6366f1; --accent-glow:rgba(139,92,246,0.15);
      --bg:var(--primary-background-color,#0f1923);
      --bg2:var(--secondary-background-color,#1a2535);
      --bg3:#243044;
      --text:var(--primary-text-color,#e2e8f0);
      --sub:var(--secondary-text-color,#94a3b8);
      --div:var(--divider-color,rgba(148,163,184,0.12));
      --green:#10b981; --orange:#f59e0b; --red:#ef4444;
      --card-radius:16px;
    }
    .panel { display:flex; flex-direction:column; height:100%; background:var(--bg); color:var(--text); }
    .panel-topbar { flex-shrink:0; padding:16px 24px 0; background:var(--bg); border-bottom:1px solid var(--div); }
    .panel-scroll  { flex:1; min-height:0; overflow-y:auto; overflow-x:hidden; padding:20px 24px 48px; }

    /* Header */
    .header { display:flex; align-items:center; gap:12px; margin-bottom:12px; }
    .header-icon { width:40px; height:40px; background:linear-gradient(135deg,var(--accent),var(--accent2));
      border-radius:12px; display:flex; align-items:center; justify-content:center; font-size:20px; flex-shrink:0; }
    .header-title { font-size:17px; font-weight:700; color:var(--text); flex:1; }
    .header-sub { font-size:12px; color:var(--sub); font-weight:400; display:block; margin-top:1px; }
    .refresh-btn { padding:6px 12px; border:1px solid var(--div); border-radius:8px;
      background:transparent; color:var(--sub); font-size:12px; cursor:pointer; transition:all .15s; }
    .refresh-btn:hover { border-color:var(--accent); color:var(--accent); }
    .watt-ring { width:36px; height:36px; border-radius:50%; border:2px solid var(--div);
      display:flex; align-items:center; justify-content:center; flex-shrink:0; transition:border-color .4s, opacity .3s; }
    .watt-value { font-size:10px; font-weight:700; color:var(--sub); font-family:'DM Mono',monospace; transition:color .4s; }

    /* Tabs — labels always visible, only hidden on mobile */
    .tab-bar { display:flex; gap:2px; overflow-x:auto; padding-bottom:1px; }
    .tab-bar::-webkit-scrollbar { display:none; }
    .tab { padding:7px 12px; border-radius:8px 8px 0 0; font-size:13px; font-weight:500;
      cursor:pointer; color:var(--sub); background:transparent; border:none;
      white-space:nowrap; transition:all .15s; border-bottom:2px solid transparent;
      display:flex; align-items:center; gap:5px; }
    .tab:hover { color:var(--text); background:var(--bg3); }
    .tab.active { color:var(--accent); border-bottom:2px solid var(--accent); font-weight:600; }
    .tab .tab-label { font-size:12px; }

    /* Section titles */
    .section-title { font-size:11px; font-weight:700; color:var(--sub); text-transform:uppercase;
      letter-spacing:.08em; margin:0 0 10px 2px; }
    .section-title-row { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }

    /* Cards */
    .card  { background:var(--bg2); border-radius:var(--card-radius); border:1px solid var(--div); padding:16px; transition:border-color .2s; }
    .card2 { background:var(--bg3); border-radius:12px; border:1px solid var(--div); padding:14px; }

    /* Live tab */
    .live-idle { display:flex; flex-direction:column; align-items:center; justify-content:center;
      padding:40px 20px; gap:12px; }
    .live-idle-icon { font-size:48px; opacity:.35; }
    .live-idle-text { font-size:15px; color:var(--sub); font-weight:500; }
    .live-idle-sub  { font-size:12px; color:var(--sub); opacity:.7; }
    .live-card { background:var(--bg2); border-radius:var(--card-radius); border:1px solid var(--div);
      padding:20px; display:flex; gap:16px; flex-wrap:wrap; margin-bottom:16px; }
    .live-left  { display:flex; flex-direction:column; gap:10px; flex:0 0 auto; min-width:180px; }
    .live-bars  { flex:1; min-width:140px; display:flex; flex-direction:column; gap:8px; justify-content:center; }
    .live-right { display:flex; align-items:center; justify-content:center; flex:0 0 auto; }
    .live-stat  { display:flex; align-items:center; gap:12px; padding:10px 12px;
      background:var(--bg3); border-radius:10px; border:1px solid var(--div); }
    .live-stat.active { border-color:var(--accent); background:rgba(139,92,246,.06); }
    .live-stat-icon { font-size:18px; flex-shrink:0; }
    .live-stat-val  { font-size:16px; font-weight:700; font-family:'DM Mono',monospace; flex:1; }
    .live-stat-lbl  { font-size:11px; color:var(--sub); }
    .live-stat.active .live-stat-val { position:relative; }
    @keyframes spin { to { transform: rotate(360deg); } }
    @keyframes pulse-dot { 0%,100%{opacity:1} 50%{opacity:.3} }
    .loading-spinner { display:inline-block; width:18px; height:18px; border:2px solid var(--div);
      border-top-color:var(--accent); border-radius:50%; animation:spin .7s linear infinite;
      flex-shrink:0; }
    .pulse-dot { display:inline-block; width:6px; height:6px; background:var(--accent);
      border-radius:50%; margin-left:6px; vertical-align:middle;
      animation:pulse-dot 1.6s ease-in-out infinite; }
    .gauge-row { display:flex; flex-direction:column; gap:3px; }
    .gauge-head { display:flex; justify-content:space-between; font-size:12px; }
    .gauge-label { color:var(--sub); font-weight:500; }
    .gauge-val   { font-weight:700; color:var(--text); font-family:'DM Mono',monospace; font-size:12px; }
    .gauge-bar-bg   { height:5px; background:var(--div); border-radius:3px; overflow:hidden; }
    .gauge-bar-fill { height:100%; border-radius:3px; background:var(--accent); transition:width .4s cubic-bezier(.4,0,.2,1); }
    .gauge-na { opacity:.45; }

    /* Donut */
    .donut-container { display:flex; flex-direction:column; align-items:center; gap:8px; }
    .donut-legend  { display:flex; flex-direction:column; gap:4px; }
    .legend-row    { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--sub); }
    .legend-dot    { width:8px; height:8px; border-radius:50%; flex-shrink:0; }
    .legend-name   { text-transform:capitalize; }

    /* Statistik */
    .statistik-layout { display:grid; grid-template-columns:1fr 260px; gap:20px; }
    .statistik-donut-mobile { display:none; }
    .user-monthly-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:10px; margin-bottom:10px; }
    .user-month-card { background:var(--bg2); border-radius:12px; border:1px solid var(--div); padding:14px; position:relative; }
    .user-month-card.is-active { border-color:var(--accent); background:rgba(139,92,246,.04); }
    .user-month-header { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
    .user-month-name  { font-size:14px; font-weight:600; text-transform:capitalize; flex:1; }
    .user-month-stats { display:flex; flex-direction:column; gap:5px; }
    .user-stat       { display:flex; justify-content:space-between; font-size:13px; }
    .user-stat-label { color:var(--sub); }
    .user-stat-value { font-weight:600; font-family:'DM Mono',monospace; }
    .monthly-footer  { display:flex; justify-content:flex-end; align-items:center; gap:16px;
      padding:10px 14px; background:var(--bg3); border-radius:10px; margin-bottom:16px;
      font-size:13px; border:1px solid var(--div); }
    .monthly-footer-label { color:var(--sub); font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; margin-right:auto; }
    .monthly-footer-val   { font-weight:700; font-family:'DM Mono',monospace; }
    .loading-banner { display:flex; align-items:center; gap:10px; padding:12px 16px;
      background:rgba(139,92,246,.08); border:1px solid rgba(139,92,246,.2); border-radius:10px;
      font-size:13px; color:var(--accent); margin-bottom:14px; }

    /* Avatar */
    .avatar { width:36px; height:36px; border-radius:50%; display:flex; align-items:center;
      justify-content:center; font-size:16px; font-weight:700; color:white; flex-shrink:0; }
    .avatar.large { width:48px; height:48px; font-size:22px; }

    /* Leaderboard */
    .leaderboard { display:flex; flex-direction:column; gap:8px; margin-bottom:12px; }
    .lb-row { display:flex; align-items:center; gap:10px; background:var(--bg2);
      border-radius:12px; padding:12px 14px; border:1px solid var(--div); }
    .lb-row.lb-first { border-color:rgba(139,92,246,.35); background:linear-gradient(135deg,rgba(139,92,246,.07),var(--bg2)); }
    .lb-rank   { font-size:20px; width:28px; text-align:center; flex-shrink:0; }
    .lb-avatar { width:32px; height:32px; border-radius:50%; display:flex; align-items:center;
      justify-content:center; font-size:14px; font-weight:700; color:white; flex-shrink:0; }
    .lb-info   { flex:1; min-width:0; }
    .lb-name   { font-size:13px; font-weight:600; text-transform:capitalize; margin-bottom:5px; }
    .lb-bar-bg { height:5px; background:var(--div); border-radius:3px; overflow:hidden; }
    .lb-bar-fill { height:100%; border-radius:3px; transition:width .6s cubic-bezier(.4,0,.2,1); }
    .lb-stats  { text-align:right; }
    .lb-time   { font-size:14px; font-weight:700; font-family:'DM Mono',monospace; }
    .lb-cost   { font-size:11px; color:var(--sub); margin-top:1px; }
    .lb-total  { display:flex; justify-content:flex-end; gap:16px; font-size:12px; color:var(--sub);
      padding:6px 14px; border-top:1px solid var(--div); }
    .lb-total strong { color:var(--text); font-family:'DM Mono',monospace; }

    /* Active user */
    .active-user-card { display:flex; align-items:center; gap:14px;
      background:rgba(139,92,246,.06); border:2px solid var(--accent);
      border-radius:14px; padding:16px; margin-bottom:8px; }
    .active-user-info { flex:1; }
    .active-user-name { font-size:16px; font-weight:700; text-transform:capitalize; }
    .active-user-meta { font-size:12px; color:var(--sub); margin-top:3px; }
    .live-badge { background:var(--accent); color:white; font-size:10px; font-weight:700;
      padding:3px 8px; border-radius:20px; letter-spacing:.5px; }
    .live-badge.small { font-size:9px; padding:2px 6px; }
    .offline-badge { font-size:11px; color:var(--sub); }
    .users-list { display:flex; flex-direction:column; gap:8px; }
    .user-row { display:flex; align-items:center; gap:12px; background:var(--bg2);
      border-radius:12px; padding:12px 16px; border:1px solid var(--div); }
    .user-row.is-active { border-color:var(--accent); }
    .user-row-info { flex:1; }
    .user-row-name    { font-weight:600; text-transform:capitalize; }
    .user-row-mapping { font-size:12px; color:var(--sub); margin-top:2px; }

    /* Notifications */
    .device-section { display:flex; flex-direction:column; gap:6px; margin-bottom:8px; }
    .device-row  { display:flex; align-items:center; gap:10px; background:var(--bg2);
      border-radius:10px; padding:10px 14px; cursor:pointer; border:1px solid var(--div); }
    .device-name { flex:1; font-weight:500; }
    .device-service { font-size:11px; color:var(--sub); }
    .device-hint { margin-top:10px; font-size:12px; color:var(--green); }
    .device-hint.warn { color:var(--orange); }
    .rules-list { display:flex; flex-direction:column; gap:10px; margin-bottom:8px; }
    .rule-card { background:var(--bg2); border-radius:12px; padding:14px 16px;
      border:1px solid var(--div); transition:border-color .2s; }
    .rule-card.active { border-color:var(--accent); background:rgba(139,92,246,.04); }
    .rule-top     { display:flex; align-items:center; gap:12px; }
    .rule-icon    { font-size:22px; flex-shrink:0; }
    .rule-info    { flex:1; }
    .rule-name    { font-weight:600; font-size:14px; }
    .rule-trigger { font-size:12px; color:var(--sub); margin-top:2px; }
    .rule-last-sent { font-size:11px; color:var(--sub); margin-top:3px; opacity:.7; }
    .rule-preview { margin-top:12px; padding:10px 12px; background:var(--bg3);
      border-radius:8px; border-left:3px solid var(--accent); }
    .rule-msg-title { font-size:13px; font-weight:600; }
    .rule-msg-body  { font-size:12px; color:var(--sub); margin-top:3px; }
    .rule-meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
    .badge { font-size:11px; padding:3px 8px; border-radius:20px; background:var(--div); color:var(--sub); }
    .badge.repeat { background:rgba(99,102,241,.15); color:#818cf8; }
    .badge.once   { background:rgba(16,185,129,.15); color:var(--green); }
    .badge.users  { background:rgba(245,158,11,.15); color:#b45309; }
    .rule-actions { display:flex; gap:8px; margin-top:12px; }
    .test-btn { padding:6px 14px; border:none; border-radius:8px; background:var(--accent);
      color:white; font-size:12px; cursor:pointer; font-weight:600; }
    .test-btn:disabled { opacity:.5; cursor:not-allowed; }
    .edit-rule-btn { padding:6px 14px; border:1px solid var(--div); border-radius:8px;
      background:transparent; color:var(--sub); font-size:12px; font-weight:600; cursor:pointer; }
    .edit-rule-btn:hover { border-color:var(--accent); color:var(--accent); }
    .del-btn { padding:6px 14px; border:none; border-radius:8px;
      background:rgba(239,68,68,.15); color:var(--red); font-size:12px; cursor:pointer; font-weight:600; }
    .inline-edit { margin-top:14px; padding-top:14px; border-top:1px solid var(--div); }
    .toggle { position:relative; display:inline-flex; align-items:center; cursor:pointer; flex-shrink:0; }
    .toggle input { opacity:0; width:0; height:0; position:absolute; }
    .toggle-slider { width:42px; height:24px; background:var(--div); border-radius:12px;
      transition:background .2s; position:relative; }
    .toggle-slider::after { content:""; position:absolute; left:3px; top:3px;
      width:18px; height:18px; border-radius:50%; background:white;
      transition:transform .2s; box-shadow:0 1px 3px rgba(0,0,0,.2); }
    .toggle input:checked + .toggle-slider { background:var(--accent); }
    .toggle input:checked + .toggle-slider::after { transform:translateX(18px); }
    .create-form, .edit-form, .create-form-inner { padding-top:12px; }
    .form-row { display:flex; align-items:center; gap:12px; margin-bottom:10px; }
    .form-row label { font-size:12px; font-weight:600; color:var(--sub); min-width:100px; flex-shrink:0; }
    .form-row input[type=text], .form-row input[type=number], .form-row select {
      flex:1; padding:8px 10px; border:1px solid var(--div); border-radius:8px;
      background:var(--bg3); color:var(--text); font-size:13px; }
    .form-row input:focus, .form-row select:focus { outline:none; border-color:var(--accent); }
    .user-checkboxes { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
    .user-check { display:flex; align-items:center; gap:4px; font-size:13px; cursor:pointer; }
    .form-hint { font-size:11px; color:var(--sub); margin-left:4px; }
    .form-actions { display:flex; gap:8px; margin-top:14px; }

    /* Admin / Health */
    .health-status-bar { display:flex; align-items:center; gap:10px; padding:12px 16px;
      border-radius:10px; margin-bottom:16px; font-size:13px; font-weight:600; }
    .health-status-bar.ok   { background:rgba(16,185,129,.08); border:1px solid rgba(16,185,129,.2); color:var(--green); }
    .health-status-bar.warn { background:rgba(245,158,11,.08); border:1px solid rgba(245,158,11,.2); color:var(--orange); }
    .health-status-bar.err  { background:rgba(239,68,68,.08); border:1px solid rgba(239,68,68,.2); color:var(--red); }
    .health-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:10px; margin-bottom:16px; }
    .health-metric { background:var(--bg2); border-radius:12px; border:1px solid var(--div); padding:14px; }
    .health-metric.ok   { border-color:rgba(16,185,129,.3); }
    .health-metric.warn { border-color:rgba(245,158,11,.3); }
    .health-metric.err  { border-color:rgba(239,68,68,.3); }
    .health-metric-icon { font-size:18px; margin-bottom:6px; }
    .health-metric-val  { font-size:16px; font-weight:700; font-family:'DM Mono',monospace; margin-bottom:2px; }
    .health-metric-lbl  { font-size:11px; color:var(--sub); margin-bottom:3px; }
    .health-metric-desc { font-size:10px; color:var(--sub); opacity:.65; line-height:1.4; }
    .admin-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:10px; margin-bottom:4px; }
    .admin-card { background:var(--bg2); border-radius:10px; border:1px solid var(--div); padding:14px; }
    .admin-card-label { font-size:11px; color:var(--sub); text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }
    .admin-card-value { font-size:13px; font-weight:600; word-break:break-all; font-family:'DM Mono',monospace; }
    .buffer-card { background:var(--bg2); border-radius:12px; border:1px solid var(--div); padding:16px; margin-bottom:4px; }
    .buffer-header { display:flex; justify-content:space-between; font-size:14px; margin-bottom:10px; }
    .buffer-bar-bg   { height:8px; background:var(--div); border-radius:4px; overflow:hidden; }
    .buffer-bar-fill { height:100%; border-radius:4px; transition:width .4s ease; }
    .buffer-hint { font-size:12px; margin-top:8px; color:var(--sub); }
    .mapping-table  { background:var(--bg2); border-radius:12px; overflow:hidden; border:1px solid var(--div); }
    .mapping-header { display:grid; grid-template-columns:1fr 1fr; padding:10px 14px;
      font-size:11px; font-weight:600; text-transform:uppercase; color:var(--sub);
      border-bottom:1px solid var(--div); letter-spacing:.05em; }
    .mapping-row { display:grid; grid-template-columns:1fr 1fr; padding:10px 14px;
      font-size:13px; border-bottom:1px solid var(--div); font-family:'DM Mono',monospace; }
    .mapping-row:last-child { border-bottom:none; }
    .admin-hint { margin-top:16px; padding:12px 16px; background:rgba(139,92,246,.05);
      border-left:3px solid var(--accent); border-radius:0 8px 8px 0;
      font-size:13px; color:var(--sub); line-height:1.5; }

    /* Tab sorter */
    .tab-sorter { display:flex; flex-direction:column; gap:6px; margin-bottom:12px; }
    .tab-sort-item { display:flex; align-items:center; gap:12px; background:var(--bg2);
      border-radius:10px; padding:11px 14px; cursor:grab; border:1px solid var(--div);
      transition:border-color .15s; user-select:none; }
    .tab-sort-item:hover { border-color:var(--accent); }
    .tab-sort-item.dragging  { opacity:.4; cursor:grabbing; }
    .tab-sort-item.drag-over { border-color:var(--accent); background:rgba(139,92,246,.07); }
    .drag-handle    { font-size:18px; color:var(--sub); cursor:grab; flex-shrink:0; }
    .tab-sort-icon  { font-size:20px; flex-shrink:0; }
    .tab-sort-label { font-size:14px; font-weight:500; flex:1; }
    .reset-tabs-btn { padding:6px 14px; border:1px solid var(--div); border-radius:8px;
      background:transparent; color:var(--sub); font-size:12px; cursor:pointer; margin-bottom:4px; }
    .reset-tabs-btn:hover { border-color:var(--accent); color:var(--accent); }

    /* Config */
    .cfg-hint       { font-size:12px; color:var(--sub); margin-bottom:14px; line-height:1.5; }
    .cfg-hint-small { font-size:11px; color:var(--sub); margin-top:3px; display:block; }
    .cfg-grid   { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:14px; }
    .cfg-grid-3 { grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); }
    .cfg-field  { display:flex; flex-direction:column; gap:4px; }
    .cfg-label  { font-size:12px; font-weight:600; color:var(--sub); text-transform:uppercase; letter-spacing:.5px; }
    .cfg-input  { width:100%; padding:9px 12px; border:1px solid var(--div); border-radius:8px;
      background:var(--bg3); color:var(--text); font-size:13px; transition:border-color .15s; }
    .cfg-input:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 3px rgba(139,92,246,.12); }
    .cfg-optional { font-size:10px; font-weight:400; color:var(--sub); text-transform:none; letter-spacing:0; }
    .select-wrap  { position:relative; }
    .select-caret { position:absolute; right:12px; top:50%; transform:translateY(-50%); pointer-events:none; color:var(--sub); font-size:11px; }
    .cfg-select   { appearance:none; -webkit-appearance:none; cursor:pointer; padding-right:28px; }
    .cfg-select option { background:var(--bg3); color:var(--text); }
    .user-mappings-list { display:flex; flex-direction:column; gap:8px; margin-bottom:16px; }
    .user-mapping-row { display:flex; align-items:flex-end; gap:10px; background:var(--bg2);
      border-radius:10px; padding:12px 14px; border:1px solid var(--div); }
    .mapping-col  { flex:1; display:flex; flex-direction:column; gap:4px; }
    .mapping-arrow { font-size:18px; color:var(--sub); padding-bottom:8px; flex-shrink:0; }
    .remove-row-btn { padding:6px 10px; border:none; border-radius:6px;
      background:rgba(239,68,68,.15); color:var(--red); cursor:pointer; font-size:13px;
      flex-shrink:0; align-self:flex-end; margin-bottom:1px; }
    .cfg-save-row { display:flex; gap:10px; margin:20px 0 16px; }
    .cfg-save-row.sticky { position:sticky; bottom:0; z-index:10;
      background:var(--bg); padding:12px 0 12px; margin:0;
      border-top:1px solid var(--div); }
    .cfg-save-btn { min-width:220px; }
    .cfg-banner { padding:12px 16px; border-radius:10px; font-size:13px; font-weight:500; margin-bottom:16px; }
    .cfg-banner.success { background:rgba(16,185,129,.1); color:#059669; border:1px solid rgba(16,185,129,.25); }
    .cfg-banner.error   { background:rgba(239,68,68,.1);  color:#dc2626; border:1px solid rgba(239,68,68,.25); }
    .cfg-info-box   { background:rgba(139,92,246,.05); border:1px solid rgba(139,92,246,.18); border-radius:10px; padding:14px 16px; }
    .cfg-info-title { font-size:13px; font-weight:600; margin-bottom:6px; }
    .cfg-info-body  { font-size:12px; color:var(--sub); line-height:1.6; }

    /* History */
    .hist-toolbar { display:flex; align-items:center; justify-content:space-between; margin-bottom:16px; flex-wrap:wrap; gap:10px; }
    .metric-selector { display:flex; gap:6px; }
    .metric-btn { padding:6px 14px; border:1px solid var(--div); border-radius:20px;
      background:transparent; color:var(--sub); font-size:13px; cursor:pointer; }
    .metric-btn.active { background:var(--accent); color:white; border-color:var(--accent); font-weight:600; }
    .reload-hist-btn { padding:6px 14px; border:1px solid var(--div); border-radius:8px;
      background:transparent; color:var(--sub); font-size:13px; cursor:pointer; }
    .bar-chart-wrap { background:var(--bg2); border-radius:12px; border:1px solid var(--div);
      padding:16px; overflow-x:auto; margin-bottom:16px; }
    .bar-chart-svg { width:100%; min-width:300px; height:auto; display:block; }
    .bar-legend { flex-direction:row; flex-wrap:wrap; gap:12px; margin-top:10px; }
    .month-totals { display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr)); gap:10px; margin-bottom:16px; }
    .month-total-card { background:var(--bg2); border-radius:10px; border:1px solid var(--div); padding:12px; }
    .month-total-name { font-size:11px; color:var(--sub); text-transform:capitalize; margin-bottom:4px; font-weight:600; }
    .month-total-val  { font-size:16px; font-weight:700; font-family:'DM Mono',monospace; }
    .week-cards { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
    .week-user-card { display:flex; align-items:center; gap:10px; background:var(--bg2);
      border-radius:10px; border:1px solid var(--div); padding:12px 14px; flex:1; min-width:120px; }
    .week-user-info { flex:1; }
    .week-user-name { font-size:12px; color:var(--sub); text-transform:capitalize; }
    .week-user-val  { font-size:16px; font-weight:700; font-family:'DM Mono',monospace; }
    .day-table  { width:100%; border-collapse:collapse; font-size:13px; }
    .day-table th { text-align:left; padding:8px 10px; font-size:11px; font-weight:600;
      text-transform:uppercase; letter-spacing:.05em; color:var(--sub); border-bottom:2px solid var(--div); }
    .day-table td { padding:7px 10px; border-bottom:1px solid var(--div); }
    .day-label   { color:var(--sub); white-space:nowrap; width:100px; }
    .day-table tr.today td { background:rgba(139,92,246,.06); }
    .day-bar-bg   { height:5px; background:var(--div); border-radius:3px; overflow:hidden; margin-bottom:3px; }
    .day-bar-fill { height:100%; border-radius:3px; }
    .day-val { font-size:12px; font-weight:600; font-family:'DM Mono',monospace; }
    .empty-state { text-align:center; color:var(--sub); padding:40px 20px; font-size:14px; }
    .empty-state.small { padding:16px; font-size:13px; }

    /* Buttons */
    .save-btn { padding:9px 20px; border:none; border-radius:8px;
      background:linear-gradient(135deg,var(--accent),var(--accent2));
      color:white; font-size:13px; font-weight:600; cursor:pointer; transition:opacity .15s; }
    .save-btn:hover { opacity:.88; }
    .save-btn:disabled { opacity:.5; cursor:not-allowed; }
    .cancel-btn { padding:9px 16px; border:1px solid var(--div); border-radius:8px;
      background:transparent; color:var(--sub); font-size:13px; cursor:pointer; }
    .cancel-btn:hover { border-color:var(--accent); color:var(--accent); }
    .add-btn { padding:6px 14px; border:1px solid var(--accent); border-radius:8px;
      background:transparent; color:var(--accent); font-size:12px; font-weight:600; cursor:pointer; }
    .add-btn:hover { background:rgba(139,92,246,.1); }


    /* Microsoft Family Safety */
    .fs-section { margin-top:20px; }
    .fs-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); gap:10px; margin-bottom:8px; }
    .fs-card { background:var(--bg2); border-radius:12px; border:1px solid var(--div); padding:14px; position:relative; overflow:hidden; }
    .fs-card::before { content:""; position:absolute; top:0; left:0; right:0; height:3px;
      background:linear-gradient(90deg,#0078d4,#50e6ff); }
    .fs-card-header { display:flex; align-items:center; gap:10px; margin-bottom:10px; }
    .fs-card-name { font-size:14px; font-weight:600; text-transform:capitalize; flex:1; }
    .fs-ms-logo { font-size:18px; flex-shrink:0; }
    .fs-stat-row { display:flex; justify-content:space-between; align-items:center; font-size:13px; margin-bottom:6px; }
    .fs-stat-label { color:var(--sub); }
    .fs-stat-value { font-weight:600; font-family:'DM Mono',monospace; }
    .fs-screen-compare { margin-top:8px; padding:8px 10px;
      background:var(--bg3); border-radius:8px; }
    .fs-compare-label { font-size:11px; color:var(--sub); margin-bottom:4px; font-weight:600; text-transform:uppercase; letter-spacing:.05em; }
    .fs-compare-bars { display:flex; flex-direction:column; gap:4px; }
    .fs-bar-row { display:flex; align-items:center; gap:8px; font-size:11px; }
    .fs-bar-label { width:60px; color:var(--sub); flex-shrink:0; }
    .fs-bar-bg { flex:1; height:6px; background:var(--div); border-radius:3px; overflow:hidden; }
    .fs-bar-fill { height:100%; border-radius:3px; transition:width .5s cubic-bezier(.4,0,.2,1); }
    .fs-bar-val { width:55px; text-align:right; font-weight:600; font-family:'DM Mono',monospace; flex-shrink:0; }
    .fs-badge-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
    .fs-badge { display:inline-flex; align-items:center; gap:3px; padding:2px 8px;
      border-radius:12px; font-size:11px; font-weight:500; }
    .fs-badge.balance { background:rgba(16,185,129,.12); color:var(--green); }
    .fs-badge.devices { background:rgba(139,92,246,.12); color:var(--accent); }
    .fs-badge.pending { background:rgba(245,158,11,.18); color:var(--orange); }
    .fs-badge.pending-zero { background:var(--div); color:var(--sub); }
    .fs-ms-hint { font-size:11px; color:var(--sub); margin-top:6px; opacity:.7; }
    .fs-not-configured { padding:16px; background:var(--bg2); border-radius:10px;
      border:1px dashed var(--div); font-size:13px; color:var(--sub); text-align:center; }
    /* Family Safety config rows */
    .fs-mapping-list { display:flex; flex-direction:column; gap:8px; margin-bottom:16px; }
    .fs-mapping-row { display:flex; align-items:flex-end; gap:10px;
      background:var(--bg2); border-radius:10px; padding:12px 14px; border:1px solid var(--div); }
    .fs-mapping-col { flex:1; display:flex; flex-direction:column; gap:4px; }

    /* Mobile */
    @media (max-width:600px) {
      .panel-topbar { padding:12px 16px 0; }
      .panel-scroll { padding:12px 16px 32px; }
      .statistik-layout { grid-template-columns:1fr; }
      .statistik-right { display:none; }
      .statistik-donut-mobile { display:flex; flex-direction:column; align-items:center; gap:8px; margin-bottom:16px; }
      .live-card { flex-direction:column; }
      .tab .tab-label { display:none; }
      .health-grid { grid-template-columns:1fr 1fr; }
      .monthly-footer { flex-wrap:wrap; gap:8px; }
    }
  `; }

  // ── Header ────────────────────────────────────────────────────
  _headerHTML() {
    const cu = this._stats?.current_user;
    const sub = cu ? `${cu.charAt(0).toUpperCase()+cu.slice(1)} spiller nu` : "Ingen aktiv session";
    return `
      <div class="header">
        <div class="header-icon">🎮</div>
        <div style="flex:1">
          <div class="header-title">PC User Statistics</div>
          <span class="header-sub">${this._esc(sub)}</span>
        </div>
        <div class="watt-ring">
          <span class="watt-value">${this._watt != null ? this._watt.toFixed(0)+"W" : "—"}</span>
        </div>
        <button class="refresh-btn" id="refresh-btn">↺</button>
      </div>`;
  }

  // ── Tabs — labels always visible on desktop ───────────────────
  _tabsHTML() {
    return `<div class="tab-bar">${this._orderedTabs().map(t =>
      `<button class="tab${this._tab===t.id?" active":""}" data-tab="${t.id}">
        <span>${t.icon}</span><span class="tab-label">${t.label}</span>
      </button>`).join("")}</div>`;
  }

  // ── Donut SVG ─────────────────────────────────────────────────
  _donutSVG(users, monthly) {
    const COLORS = ["#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1"];
    const total = users.reduce((s,u)=>s+(monthly[u]?.time||0),0);
    if (!total) return `<svg width="120" height="120" viewBox="0 0 120 120">
      <circle cx="60" cy="60" r="48" fill="none" stroke="var(--div)" stroke-width="12"/>
      <text x="60" y="65" text-anchor="middle" font-size="12" fill="var(--sub)" font-family="DM Sans,sans-serif">Ingen data</text></svg>`;
    const R=48, CX=60, CY=60, sw=12, C=2*Math.PI*R;
    let offset=0;
    const arcs=users.map((u,i)=>{
      const frac=(monthly[u]?.time||0)/total, dash=frac*C;
      const arc=`<circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="${COLORS[i%COLORS.length]}" stroke-width="${sw}"
        stroke-dasharray="${dash.toFixed(2)} ${(C-dash).toFixed(2)}"
        stroke-dashoffset="${(-offset*C).toFixed(2)}" transform="rotate(-90 ${CX} ${CY})"/>`;
      offset+=frac; return arc;
    }).join("");
    const topUser=[...users].sort((a,b)=>(monthly[b]?.time||0)-(monthly[a]?.time||0))[0];
    const topPct=Math.round((monthly[topUser]?.time||0)/total*100);
    const legend=users.map((u,i)=>
      `<div class="legend-row"><span class="legend-dot" style="background:${COLORS[i%COLORS.length]}"></span>
       <span class="legend-name">${u}</span></div>`).join("");
    return `
      <svg width="120" height="120" viewBox="0 0 120 120">
        <circle cx="${CX}" cy="${CY}" r="${R}" fill="none" stroke="var(--div)" stroke-width="${sw}"/>
        ${arcs}
        <text x="${CX}" y="${CY-8}" text-anchor="middle" font-size="22" font-weight="700" fill="var(--text)" font-family="DM Mono,monospace">${topPct}%</text>
        <text x="${CX}" y="${CY+12}" text-anchor="middle" font-size="11" fill="var(--sub)" font-family="DM Sans,sans-serif">${topUser}</text>
      </svg>
      <div class="donut-legend">${legend}</div>`;
  }

  // ── Gauge bars ────────────────────────────────────────────────
  _barsHTML() {
    if (!this._config) return "";
    const cfg=this._config;
    const COLORS=["#8b5cf6","#6366f1","#10b981","#f59e0b","#06b6d4"];
    let html="";
    [1,2,3,4,5].forEach((n,i)=>{
      const key=`gauge${n}`;
      if (!cfg[`${key}_entity`]) return;
      const g=this._gaugeDisplay(key,cfg);
      const col=COLORS[i];
      html+=`<div class="gauge-row${g.unavailable?" gauge-na":""}">
        <div class="gauge-head">
          <span class="gauge-label">${this._esc(g.label)}</span>
          <span class="gauge-val" data-gauge="${key}">${this._esc(g.display)}</span>
        </div>
        <div class="gauge-bar-bg">
          <div class="gauge-bar-fill" data-gauge="${key}" style="width:${g.unavailable?0:g.pct}%;background:${col}"></div>
        </div>
      </div>`;
    });
    return html;
  }

  // ── Live tab ──────────────────────────────────────────────────
  _liveHTML() {
    const s=this._stats;
    if (!s) return `<div class="empty-state">Indlæser...</div>`;
    const users=s.tracked_users||[], monthly=s.monthly||{};
    const rawCU=s.current_user;
    const cu=rawCU&&typeof rawCU==="object"?(rawCU.name??rawCU.id??String(rawCU)):(rawCU||null);
    const sd={...s, current_user:cu};
    const barsHTML=this._barsHTML();
    const hasBars=barsHTML.trim()!=="";

    // Idle state when no active session
    if (!cu) {
      return `
        <div class="live-idle">
          <div class="live-idle-icon">💤</div>
          <div class="live-idle-text">PC er klar — ingen aktiv session</div>
          <div class="live-idle-sub">${(()=>{
            const totals=Object.values(this._stats?.monthly||{});
            const anyData=totals.some(m=>m.time>0);
            if (!anyData) return "Ingen sessioner denne måned endnu";
            const lastUser=Object.entries(this._stats?.monthly||{})
              .sort((a,b)=>(b[1].time||0)-(a[1].time||0))[0];
            return lastUser
              ?`${lastUser[0].charAt(0).toUpperCase()+lastUser[0].slice(1)} ledte med ${this._fmtTime(lastUser[1].time)} denne måned`
              :"Se Statistik-tab for månedsoversigt";
          })()}</div>
        </div>
        ${hasBars ? `
          <div class="section-title" style="margin-top:8px">PC Status</div>
          <div class="card" style="display:flex;flex-direction:column;gap:8px;padding:16px">${barsHTML}</div>` : ""}`;
    }

    return `
      <div class="section-title">Live Session</div>
      <div class="live-card">
        <div class="live-left">
          <div class="live-stat active">
            <div class="live-stat-icon">⏱️</div>
            <div class="live-stat-val">${this._fmtTime(sd.acc_time)}<span class="pulse-dot"></span></div>
            <div class="live-stat-lbl">Sessionstid</div>
          </div>
          <div class="live-stat">
            <div class="live-stat-icon">⚡</div>
            <div class="live-stat-val">${this._fmtEnergy(sd.acc_energy)}</div>
            <div class="live-stat-lbl">Sessionsenergi</div>
          </div>
          <div class="live-stat">
            <div class="live-stat-icon">💰</div>
            <div class="live-stat-val">${this._fmtCost(sd.acc_cost)}</div>
            <div class="live-stat-lbl">Sessionspris</div>
          </div>
        </div>
        ${hasBars ? `<div class="live-bars">${barsHTML}</div>` : ""}
        <div class="live-right">
          <div class="donut-container">${this._donutSVG(users, monthly)}</div>
        </div>
      </div>`;
  }

  // ── Statistik tab ─────────────────────────────────────────────
  _statistikHTML() {
    const s=this._stats;
    if (!s) return `<div class="empty-state">Indlæser...</div>`;
    const users=s.tracked_users||[], monthly=s.monthly||{};
    const cu=s.current_user;

    const loadingBanner=!s.monthly_loaded
      ?`<div class="loading-banner">⏳ Monthly data indlæses fra InfluxDB... Tallene er foreløbige.</div>`:""

    // Always show all users — even with 0 data
    const userCards=users.map(u=>{
      const d=monthly[u]||{};
      const col=this._userColor(u);
      const isActive=cu===u;
      return `
        <div class="user-month-card${isActive?" is-active":""}">
          <div class="user-month-header">
            <div class="avatar" style="background:${col}">${u[0].toUpperCase()}</div>
            <div class="user-month-name">${this._esc(u)}</div>
            ${isActive?`<span class="live-badge small">LIVE</span>`:""}
          </div>
          <div class="user-month-stats">
            <div class="user-stat"><span class="user-stat-label">Tid</span><span class="user-stat-value">${this._fmtTime(d.time)}</span></div>
            <div class="user-stat"><span class="user-stat-label">Energi</span><span class="user-stat-value">${this._fmtEnergy(d.energy)}</span></div>
            <div class="user-stat"><span class="user-stat-label">Pris</span><span class="user-stat-value">${this._fmtCost(d.cost)}</span></div>
          </div>
        </div>`;
    }).join("");

    // Combined totals footer
    const totTime=users.reduce((s,u)=>s+(monthly[u]?.time||0),0);
    const totCost=users.reduce((s,u)=>s+(monthly[u]?.cost||0),0);
    const totEnergy=users.reduce((s,u)=>s+(monthly[u]?.energy||0),0);
    const footer=`
      <div class="monthly-footer">
        <span class="monthly-footer-label">Samlet denne måned</span>
        <span class="monthly-footer-val">${this._fmtTime(totTime)}</span>
        <span class="monthly-footer-val" style="color:var(--sub)">${this._fmtEnergy(totEnergy)}</span>
        <span class="monthly-footer-val" style="color:var(--orange)">${this._fmtCost(totCost)}</span>
      </div>`;

    return `
      ${loadingBanner}
      <div class="statistik-donut-mobile">
        <div class="section-title" style="margin:0 0 8px">Fordeling</div>
        ${this._donutSVG(users, monthly)}
      </div>
      <div class="statistik-layout">
        <div class="statistik-left">
          <div class="section-title">Månedlige totaler</div>
          <div class="user-monthly-grid">${userCards}</div>
          ${footer}
          <div class="section-title">🏆 Leaderboard</div>
          ${this._leaderboardHTML(users, monthly)}
          <div class="section-title" style="margin-top:20px">🪟 Microsoft Family Safety</div>
          ${this._familySafetyHTML()}
        </div>
        <div class="statistik-right">
          <div class="section-title">Fordeling</div>
          <div class="donut-container">${this._donutSVG(users, monthly)}</div>
        </div>
      </div>`;
  }

  // ── Leaderboard with total footer ─────────────────────────────

  // ── Microsoft Family Safety ───────────────────────────────────
  _familySafetyHTML() {
    const fs = this._fs;
    const cfg = this._config;
    const fsMap = cfg?.family_safety_mappings || {};
    if (!fs || Object.keys(fsMap).length === 0) {
      return `<div class="fs-not-configured">
        🪟 Microsoft Family Safety ikke konfigureret endnu.<br>
        <span style="font-size:11px">Tilføj entity-prefix per bruger under Konfiguration → Family Safety.</span>
      </div>`;
    }
    const users = this._stats?.tracked_users || [];
    const monthly = this._stats?.monthly || {};
    const COLORS = ["#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1"];
    const cards = users.map((u, idx) => {
      const fsData = fs.users?.[u];
      if (!fsData) return "";
      const col = COLORS[idx % COLORS.length];
      const msMin = fsData.screen_time_min ?? 0;
      const msSecs = msMin * 60;
      const pcSecs = monthly[u]?.time || 0;
      const maxSecs = Math.max(msSecs, pcSecs, 1);
      const msPct = Math.round(msSecs / maxSecs * 100);
      const pcPct = Math.round(pcSecs / maxSecs * 100);
      const compareBlock = `
        <div class="fs-screen-compare">
          <div class="fs-compare-label">Skærmtid i dag</div>
          <div class="fs-compare-bars">
            <div class="fs-bar-row">
              <span class="fs-bar-label" style="color:#0078d4">🪟 MS</span>
              <div class="fs-bar-bg"><div class="fs-bar-fill" style="width:${msPct}%;background:#0078d4"></div></div>
              <span class="fs-bar-val">${this._fmtTime(msSecs)}</span>
            </div>
            <div class="fs-bar-row">
              <span class="fs-bar-label" style="color:${col}">🎮 PC</span>
              <div class="fs-bar-bg"><div class="fs-bar-fill" style="width:${pcPct}%;background:${col}"></div></div>
              <span class="fs-bar-val">${this._fmtTime(pcSecs)}</span>
            </div>
          </div>
        </div>`;
      const balDkk = fsData.balance_dkk;
      const balBadge = balDkk != null ? `<span class="fs-badge balance">💳 ${balDkk.toFixed(2).replace(".",",")} kr</span>` : "";
      const devBadge = fsData.device_count != null ? `<span class="fs-badge devices">📱 ${fsData.device_count} enheder</span>` : "";
      const pendCount = fsData.pending_count ?? 0;
      const pendBadge = `<span class="fs-badge ${pendCount > 0 ? "pending" : "pending-zero"}">🎁 ${pendCount} ønske${pendCount !== 1 ? "r" : ""}</span>`;
      const dateHint = fsData.screen_time_date ? `<div class="fs-ms-hint">Data for ${fsData.screen_time_date}</div>` : "";
      return `
        <div class="fs-card">
          <div class="fs-card-header">
            <div class="avatar" style="background:${col}">${u[0].toUpperCase()}</div>
            <div class="fs-card-name">${this._esc(u)}</div>
            <span class="fs-ms-logo">🪟</span>
          </div>
          ${compareBlock}
          <div class="fs-badge-row">${balBadge}${devBadge}${pendBadge}</div>
          ${dateHint}
        </div>`;
    }).filter(Boolean).join("");
    if (!cards) return `<div class="fs-not-configured">Ingen brugere med Family Safety konfigureret endnu.</div>`;
    return `<div class="fs-grid">${cards}</div>`;
  }

  _leaderboardHTML(users, monthly) {
    const COLORS=["#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1"];
    const MEDALS=["🥇","🥈","🥉"];
    const ranked=[...users]
      .map(u=>({ u, time:monthly[u]?.time||0, cost:monthly[u]?.cost||0 }))
      .sort((a,b)=>b.time-a.time);
    if (ranked.every(r=>r.time===0))
      return `<div class="empty-state small">Ingen data denne måned endnu</div>`;
    const maxTime=ranked[0].time||1;
    const rows=ranked.map((r,i)=>{
      const pct=r.time/maxTime*100;
      const color=COLORS[users.indexOf(r.u)%COLORS.length];
      const medal=MEDALS[i]||`#${i+1}`;
      return `
        <div class="lb-row${i===0?" lb-first":""}">
          <div class="lb-rank">${medal}</div>
          <div class="lb-avatar" style="background:${color}">${r.u[0].toUpperCase()}</div>
          <div class="lb-info">
            <div class="lb-name">${this._esc(r.u)}</div>
            <div class="lb-bar-bg"><div class="lb-bar-fill" style="width:${pct.toFixed(1)}%;background:${color}"></div></div>
          </div>
          <div class="lb-stats">
            <div class="lb-time">${this._fmtTime(r.time)}</div>
            <div class="lb-cost">${this._fmtCost(r.cost)}</div>
          </div>
        </div>`;
    }).join("");
    const totTime=ranked.reduce((s,r)=>s+r.time,0);
    const totCost=ranked.reduce((s,r)=>s+r.cost,0);
    return `<div class="leaderboard">${rows}</div>
      <div class="lb-total">
        <span>Samlet</span>
        <strong>${this._fmtTime(totTime)}</strong>
        <strong style="color:var(--orange)">${this._fmtCost(totCost)}</strong>
      </div>`;
  }

  // ── Notifications ─────────────────────────────────────────────
  _notificationsHTML() {
    const nd=this._notif;
    if (!nd) return `<div class="empty-state">Indlæser...</div>`;
    const rules=nd.rules||{}, devices=nd.devices||[], available=nd.available_devices||[];
    const users=this._stats?.tracked_users||[];
    const premadeIds=["pause_reminder","long_session","cost_limit","idle_pc"];
    const devRows=available.length===0
      ?`<div class="empty-state small">Ingen HA Companion apps fundet.</div>`
      :available.map(d=>`
          <label class="device-row">
            <input type="checkbox" class="dev-check" value="${this._esc(d.service)}" ${devices.includes(d.service)?"checked":""}>
            <span class="device-name">📱 ${this._esc(d.name)}</span>
            <span class="device-service">${this._esc(d.service)}</span>
          </label>`).join("")+
        (devices.length>0
          ?`<div class="device-hint">✅ ${devices.length} enhed${devices.length>1?"er":""} konfigureret</div>`
          :`<div class="device-hint warn">⚠️ Vælg mindst én enhed</div>`);
    const premade=premadeIds.filter(id=>rules[id]).map(id=>this._ruleCardHTML(id,rules[id],users,false));
    const custom=Object.entries(rules).filter(([id])=>!premadeIds.includes(id))
                       .map(([id,r])=>this._ruleCardHTML(id,r,users,true));
    const createBtn=`<button class="add-btn show-create-btn">${this._showCreate?"✕ Luk":"+ Ny regel"}</button>`;
    const createForm=this._showCreate?`<div class="create-form">${this._ruleFormHTML(null,users)}</div>`:"";
    return `
      <div class="section-title">📱 Modtagerenheder</div>
      <div class="device-section">${devRows}</div>
      <div class="section-title" style="margin-top:24px">⭐ Premade regler</div>
      <div class="rules-list">${premade.join("")}</div>
      <div class="section-title-row">
        <span class="section-title" style="margin:0">✏️ Egne regler</span>
        ${createBtn}
      </div>
      ${createForm}
      <div class="rules-list">
        ${custom.length===0&&!this._showCreate
          ?`<div class="empty-state small">Ingen egne regler endnu</div>`
          :custom.join("")}
      </div>`;
  }

  _ruleCardHTML(ruleId, rule, users, canDelete) {
    const active=rule.enabled, editing=this._editingRule===ruleId;
    const chk=active?"checked":"", editLbl=editing?"✕ Luk":"✏️ Rediger";

    // Last sent info — from last_sent in notif store (best-effort: show if available)
    const lastSentData=this._notif?.last_sent||{};
    const relevantUsers=(rule.user_targets?.length>0?rule.user_targets:users);
    const latestSent=relevantUsers.reduce((best,u)=>{
      const ts=lastSentData[`${ruleId}_${u}`]||0;
      return ts>best?ts:best;
    },0);
    const lastSentStr=latestSent>0?`Sidst sendt: ${this._fmtTs(latestSent)}`:"Ikke sendt endnu";

    const preview=active?`
      <div class="rule-preview">
        <div class="rule-msg-title">${this._esc(rule.title)}</div>
        <div class="rule-msg-body">${this._esc(rule.message)}</div>
      </div>
      <div class="rule-meta">
        <span class="badge ${rule.repeat?"repeat":"once"}">${rule.repeat?`Gentages hvert ${rule.repeat_interval} min`:"Én gang per session"}</span>
        <span class="badge users">${rule.user_targets?.length>0?rule.user_targets.join(", "):"Alle brugere"}</span>
      </div>
      <div class="rule-actions">
        <button class="test-btn" data-rule="${ruleId}" data-test="${ruleId}" ${!this._notif?.devices?.length?"disabled":""}>📨 Test</button>
        <button class="edit-btn edit-rule-btn" data-rule="${ruleId}">${editLbl}</button>
        ${canDelete?`<button class="del-btn" data-rule="${ruleId}">🗑️ Slet</button>`:""}
      </div>
      ${editing?`<div class="inline-edit">${this._ruleFormHTML(ruleId,users)}</div>`:""}
    `:"";

    return `
      <div class="rule-card${active?" active":""}">
        <div class="rule-top">
          <div class="rule-icon">${rule.icon||"🔔"}</div>
          <div class="rule-info">
            <div class="rule-name">${this._esc(rule.name)}</div>
            <div class="rule-trigger">${this._triggerLabel(rule.trigger_type,rule.trigger_value)}</div>
            <div class="rule-last-sent">${lastSentStr}</div>
          </div>
          <label class="toggle">
            <input type="checkbox" class="rule-toggle" data-rule="${ruleId}" ${chk}>
            <span class="toggle-slider"></span>
          </label>
        </div>
        ${preview}
      </div>`;
  }

  _ruleFormHTML(editRuleId, users) {
    const r=editRuleId?{...this._notif.rules[editRuleId],id:editRuleId}:this._newRule;
    const isEdit=!!editRuleId;
    const isPremade=isEdit&&["pause_reminder","long_session","cost_limit","idle_pc"].includes(editRuleId);
    const cls=isEdit?"edit-form":"create-form-inner";
    const saveCls=isEdit?"save-edit-btn":"save-new-btn";
    const canCls=isEdit?"cancel-edit-btn":"cancel-new-btn";
    const saveLbl=this._savingRule?"💾 Gemmer...":(isEdit?"💾 Gem ændringer":"💾 Gem regel");
    const userChecks=users.map(u=>`
      <label class="user-check">
        <input type="checkbox" class="f-user" value="${u}" ${r.user_targets?.includes(u)?"checked":""}>${this._esc(u)}
      </label>`).join("");
    const triggerFields=isPremade?`
      <div class="form-row">
        <label>Trigger-værdi</label>
        <input class="f-tval" type="number" value="${r.trigger_value}" min="1">
        <input type="hidden" class="f-ttype" value="${r.trigger_type}">
        <input type="hidden" class="f-icon" value="${r.icon}">
      </div>`:`
      <div class="form-row">
        <label>Ikon</label>
        <input class="f-icon" type="text" value="${this._esc(r.icon)}" style="width:60px">
      </div>
      <div class="form-row">
        <label>Trigger</label>
        <select class="f-ttype">
          <option value="session_minutes" ${r.trigger_type==="session_minutes"?"selected":""}>Spilletid (min)</option>
          <option value="session_cost"    ${r.trigger_type==="session_cost"?"selected":""}>Sessionspris (kr)</option>
          <option value="idle_minutes"    ${r.trigger_type==="idle_minutes"?"selected":""}>PC inaktiv (min)</option>
        </select>
      </div>
      <div class="form-row">
        <label>Værdi</label>
        <input class="f-tval" type="number" value="${r.trigger_value}" min="1">
      </div>`;
    return `
      <div class="${cls}">
        ${!isPremade?`
        <div class="form-row">
          <label>Navn</label>
          <input class="f-name" type="text" value="${this._esc(r.name)}" placeholder="Min regel">
        </div>`:`<input type="hidden" class="f-name" value="${this._esc(r.name)}">`}
        ${triggerFields}
        <div class="form-row"><label>Titel</label><input class="f-title" type="text" value="${this._esc(r.title)}" placeholder="{user}, {time}, {cost}"></div>
        <div class="form-row"><label>Besked</label><input class="f-msg" type="text" value="${this._esc(r.message)}" placeholder="{user}, {time}, {cost}"></div>
        <div class="form-row"><label>Gentag?</label><label class="toggle"><input class="f-repeat" type="checkbox" ${r.repeat?"checked":""}><span class="toggle-slider"></span></label></div>
        <div class="form-row"><label>Interval (min)</label><input class="f-interval" type="number" value="${r.repeat_interval}" min="5"></div>
        <div class="form-row"><label>Brugere</label><div class="user-checkboxes">${userChecks}<span class="form-hint">Tom = alle</span></div></div>
        <div class="form-actions">
          <button class="${saveCls} save-btn" ${this._savingRule?"disabled":""}>${saveLbl}</button>
          <button class="${canCls} cancel-btn">Annuller</button>
        </div>
      </div>`;
  }

  // ── History tab — with today marker ──────────────────────────
  _historyHTML() {
    if (!this._history) return `
      <div class="loading-banner" style="flex-direction:column;align-items:flex-start;gap:12px">
        <div style="display:flex;align-items:center;gap:10px">
          <div class="loading-spinner"></div>
          <span>Indlæser historik fra InfluxDB...</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:8px;width:100%">
          ${["85%","60%","75%","45%","90%"].map(w=>`
          <div style="height:8px;background:var(--bg3);border-radius:4px;width:${w};opacity:.5"></div>`).join("")}
        </div>
      </div>`;
    const { days, users, series }=this._history;
    const m=this._histMetric;
    const metricBtns=[["time","⏱️ Tid"],["energy","⚡ Energi"],["cost","💰 Pris"]]
      .map(([id,label])=>`<button class="metric-btn${m===id?" active":""}" data-metric="${id}">${label}</button>`).join("");
    const COLORS=["#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1"];
    const fmtV=v=>m==="time"?this._fmtTime(v):m==="energy"?this._fmtEnergy(v):this._fmtCost(v);
    const monthTotals=users.map((u,i)=>{
      const tot=days.reduce((acc,d)=>acc+(series[u]?.[d]?.[m]||0),0);
      return `<div class="month-total-card" style="border-top:3px solid ${COLORS[i%COLORS.length]}">
        <div class="month-total-name">${u}</div>
        <div class="month-total-val" style="color:${COLORS[i%COLORS.length]}">${fmtV(tot)}</div>
      </div>`;
    }).join("");
    return `
      <div class="hist-toolbar">
        <div class="metric-selector">${metricBtns}</div>
        <button class="reload-hist-btn">🔄 Opdater</button>
      </div>
      <div class="section-title">Månedstotaler</div>
      <div class="month-totals">${monthTotals}</div>
      <div class="section-title">Daglig fordeling — seneste 30 dage</div>
      <div class="bar-chart-wrap">${this._barChartSVG(days, users, series, m)}</div>
      <div class="section-title">Seneste 7 dage</div>
      ${this._weekSummaryHTML(days, users, series, m)}`;
  }

  _barChartSVG(days, users, series, metric) {
    if (!days.length) return `<div class="empty-state small">Ingen historik data endnu</div>`;
    const COLORS=["#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1"];
    const W=680, H=200, PL=48, PR=12, PT=12, PB=36;
    const cW=W-PL-PR, cH=H-PT-PB;
    const showDays=days.slice(-30);
    const barGW=cW/showDays.length;
    const barW=Math.max(Math.min(barGW/users.length-2,18),3);
    let maxVal=0;
    for (const day of showDays) for (const u of users) { const v=series[u]?.[day]?.[metric]||0; if (v>maxVal) maxVal=v; }
    if (!maxVal) return `<div class="empty-state small">Ingen data for valgt periode</div>`;
    const scale=v=>cH-(v/maxVal)*cH;
    const fmtY=v=>metric==="time"?(v>=3600?(v/3600).toFixed(1)+"t":Math.round(v/60)+"m"):metric==="energy"?v.toFixed(2)+"kWh":v.toFixed(1)+"kr";
    const yLabels=[0,.25,.5,.75,1].map(f=>{
      const val=f*maxVal, y=PT+scale(val);
      return `<text x="${PL-4}" y="${y+4}" text-anchor="end" font-size="9" fill="var(--sub)">${fmtY(val)}</text>
              <line x1="${PL}" y1="${y}" x2="${W-PR}" y2="${y}" stroke="var(--div)" stroke-width="1"/>`;
    }).join("");

    // Today marker
    const todayStr=new Date().toISOString().slice(0,10);
    const todayIdx=showDays.indexOf(todayStr);
    const todayLine=todayIdx>=0?`<line x1="${(PL+todayIdx*barGW+barGW/2).toFixed(1)}" y1="${PT}" x2="${(PL+todayIdx*barGW+barGW/2).toFixed(1)}" y2="${PT+cH}"
      stroke="var(--accent)" stroke-width="1.5" stroke-dasharray="3,3" opacity="0.7"/>
      <text x="${(PL+todayIdx*barGW+barGW/2).toFixed(1)}" y="${PT-2}" text-anchor="middle" font-size="8" fill="var(--accent)">i dag</text>`:"";

    const bars=showDays.map((day,di)=>{
      const gX=PL+di*barGW;
      const dayBars=users.map((u,ui)=>{
        const val=series[u]?.[day]?.[metric]||0, bH=(val/maxVal)*cH;
        const x=gX+(barGW-users.length*(barW+2))/2+ui*(barW+2), y=PT+cH-bH;
        return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW}" height="${bH.toFixed(1)}"
          fill="${COLORS[ui%COLORS.length]}" rx="2" opacity="${day===todayStr?"1":"0.85"}">
          <title>${u}: ${fmtY(val)}</title></rect>`;
      }).join("");
      const step=showDays.length>20?5:showDays.length>10?3:1;
      const xLabel=di%step===0?`<text x="${(gX+barGW/2).toFixed(1)}" y="${H-4}"
        text-anchor="middle" font-size="9" fill="${day===todayStr?"var(--accent)":"var(--sub)"}">${day.slice(5)}</text>`:"";
      return dayBars+xLabel;
    }).join("");

    const legend=users.map((u,i)=>
      `<div class="legend-row"><span class="legend-dot" style="background:${COLORS[i%COLORS.length]}"></span><span class="legend-name">${u}</span></div>`
    ).join("");
    return `<svg viewBox="0 0 ${W} ${H}" class="bar-chart-svg" preserveAspectRatio="xMidYMid meet">
      ${yLabels}${todayLine}${bars}</svg>
      <div class="donut-legend bar-legend">${legend}</div>`;
  }

  _weekSummaryHTML(days, users, series, metric) {
    const last7=days.slice(-7);
    if (!last7.length) return "";
    const fmtV=v=>metric==="time"?this._fmtTime(v):metric==="energy"?this._fmtEnergy(v):this._fmtCost(v);
    const COLORS=["#8b5cf6","#f59e0b","#10b981","#ef4444","#6366f1"];
    const todayStr=new Date().toISOString().slice(0,10);
    const totals=users.map((u,i)=>{
      const tot=last7.reduce((acc,d)=>acc+(series[u]?.[d]?.[metric]||0),0);
      return `<div class="week-user-card">
        <div class="avatar" style="background:${COLORS[i%COLORS.length]}">${u[0].toUpperCase()}</div>
        <div class="week-user-info">
          <div class="week-user-name">${u}</div>
          <div class="week-user-val">${fmtV(tot)}</div>
        </div></div>`;
    }).join("");
    const dayFmt=d=>{
      const dt=new Date(d+"T12:00:00Z");
      return dt.toLocaleDateString("da-DK",{weekday:"short",day:"numeric",month:"numeric"});
    };
    const rows=last7.map(d=>{
      const isToday=d===todayStr;
      const cells=users.map((u,i)=>{
        const v=series[u]?.[d]?.[metric]||0;
        const barPct=Math.round((v/(Math.max(...users.map(u2=>series[u2]?.[d]?.[metric]||0))||1))*100);
        return `<td><div class="day-bar-bg"><div class="day-bar-fill" style="width:${barPct}%;background:${COLORS[i%COLORS.length]}"></div></div>
          <div class="day-val">${fmtV(v)}</div></td>`;
      }).join("");
      return `<tr${isToday?' class="today"':''}><td class="day-label">${dayFmt(d)}${isToday?' <span style="color:var(--accent);font-size:10px">↑</span>':""}</td>${cells}</tr>`;
    }).join("");
    const headers=users.map(u=>`<th>${u}</th>`).join("");
    return `<div class="week-cards">${totals}</div>
      <table class="day-table"><thead><tr><th>Dag</th>${headers}</tr></thead><tbody>${rows}</tbody></table>`;
  }

  // ── Config tab ────────────────────────────────────────────────
  _configHTML() {
    if (!this._config) return '<div class="empty-state">Indlæser konfiguration...</div>';
    const cfg=this._config;
    const rawMappings=cfg.user_mappings||{};
    const mappings=Object.entries(rawMappings).map(([k,v])=>({
      sensorState:k, userId:typeof v==="object"?(v.user_id||""):(v||""), haUser:typeof v==="object"?(v.ha_user||""):"",
    }));
    while (mappings.length<3) mappings.push({sensorState:"",userId:"",haUser:""});
    const haUserOptions=[
      `<option value="">— Vælg HA-bruger (valgfri) —</option>`,
      ...this._haUsers.map(u=>`<option value="${this._esc(u.id)}">${this._esc(u.name)}</option>`),
    ].join("");
    const mappingRows=mappings.map(({sensorState,userId,haUser},i)=>{
      const opts=haUserOptions.replace(`value="${this._esc(haUser)}"`,`value="${this._esc(haUser)}" selected`);
      return `
      <div class="user-mapping-row">
        <div class="mapping-col"><label class="cfg-label">Sensor-tilstand</label>
          <input class="cfg-sensor-state cfg-input" type="text" value="${this._esc(sensorState)}" placeholder="f.eks. konge"></div>
        <div class="mapping-arrow">→</div>
        <div class="mapping-col"><label class="cfg-label">Bruger-ID</label>
          <input class="cfg-user-id cfg-input" type="text" value="${this._esc(userId)}" placeholder="f.eks. flemming"></div>
        <div class="mapping-arrow">→</div>
        <div class="mapping-col"><label class="cfg-label">HA Mobil-bruger <span class="cfg-optional">(valgfri)</span></label>
          <div class="select-wrap"><select class="cfg-ha-user cfg-input cfg-select" data-idx="${i}">${opts}</select><span class="select-caret">▾</span></div></div>
        <button class="remove-row-btn" data-idx="${i}">✕</button>
      </div>`;
    }).join("");
    const statusBanner=this._configState==="saved"
      ?'<div class="cfg-banner success">✅ Gemt! Home Assistant genindlæser integrationen...</div>'
      :this._configState==="error"?'<div class="cfg-banner error">❌ Fejl ved gemning. Tjek HA-loggen.</div>':"";
    return `
      ${statusBanner}
      <div class="section-title">🔌 Sensor Entity IDs</div>
      <div class="cfg-hint">Disse entity IDs skal matche dine HA sensorer.</div>
      <div class="cfg-grid">
        <div class="cfg-field"><label class="cfg-label">👤 Bruger-sensor</label>
          <input class="cfg-user-entity cfg-input" type="text" value="${this._esc(cfg.user_entity||'')}" placeholder="sensor.din_bruger_sensor">
          <span class="cfg-hint-small">Sensor der viser hvem der er logget ind</span></div>
        <div class="cfg-field"><label class="cfg-label">⚡ Watt-sensor</label>
          <input class="cfg-watt-entity cfg-input" type="text" value="${this._esc(cfg.watt_entity||'')}" placeholder="sensor.pc_strømforbrug">
          <span class="cfg-hint-small">PC'ens samlede strømforbrug i watt</span></div>
        <div class="cfg-field"><label class="cfg-label">🔌 Måler-sensor</label>
          <input class="cfg-device-power-entity cfg-input" type="text" value="${this._esc(cfg.device_power_entity||'')}" placeholder="sensor.maaler_forbrug">
          <span class="cfg-hint-small">Målerens eget forbrug (trækkes fra watt)</span></div>
        <div class="cfg-field"><label class="cfg-label">💰 Pris-sensor</label>
          <input class="cfg-price-entity cfg-input" type="text" value="${this._esc(cfg.price_entity||'')}" placeholder="sensor.energi_pris">
          <span class="cfg-hint-small">Aktuel elpris i kr/kWh</span></div>
      </div>
      <div class="section-title" style="margin-top:24px">📊 Live Gauge-sensorer <span style="font-size:11px;font-weight:400;opacity:.6">(valgfri)</span></div>
      <div class="cfg-hint">Vises som søjler i Live Session.</div>
      ${[
        {n:1,icon:"🔵",placeholder:"sensor.flemming_gamer_satellite_cpuload",       ex:"CPU",      maxph:"100"},
        {n:2,icon:"🟠",placeholder:"sensor.flemming_gamer_satellite_gpuload",       ex:"GPU",      maxph:"100"},
        {n:3,icon:"🟢",placeholder:"sensor.flemming_gamer_satellite_memoryusage",   ex:"RAM",      maxph:"100"},
        {n:4,icon:"🟣",placeholder:"sensor.flemming_gamer_satellite_gputemperature",ex:"GPU temp", maxph:""},
        {n:5,icon:"🔵",placeholder:"sensor.flemmings_gamer_pc_currentclockspeed",  ex:"Speed MHz",maxph:"5200"},
      ].map(({n,icon,placeholder,ex,maxph})=>`
      <div class="cfg-grid cfg-grid-3" style="margin-top:${n===1?'0':'8px'}">
        <div class="cfg-field"><label class="cfg-label">${icon} Gauge ${n} — Sensor</label>
          <input class="cfg-gauge${n}-entity cfg-input" type="text" value="${this._esc(cfg[`gauge${n}_entity`]||'')}" placeholder="${placeholder}"></div>
        <div class="cfg-field"><label class="cfg-label">${icon} Gauge ${n} — Etiket</label>
          <input class="cfg-gauge${n}-label cfg-input" type="text" value="${this._esc(cfg[`gauge${n}_label`]||'')}" placeholder="${ex}"></div>
        <div class="cfg-field"><label class="cfg-label">${icon} Gauge ${n} — Max <span class="cfg-optional">(valgfri)</span></label>
          <input class="cfg-gauge${n}-max cfg-input" type="number" min="0" step="any" value="${this._esc(cfg[`gauge${n}_max`]||'')}" placeholder="${maxph}"></div>
      </div>`).join("")}
      <div class="section-title-row" style="margin-top:24px">
        <span class="section-title" style="margin:0">👥 Bruger-mappings</span>
        <button class="add-btn add-mapping-btn">+ Tilføj bruger</button>
      </div>
      <div class="user-mappings-list">${mappingRows}</div>
      <div class="section-title" style="margin-top:24px">🪟 Microsoft Family Safety <span style="font-size:11px;font-weight:400;opacity:.6">(valgfri)</span></div>
      <div class="cfg-hint">Link hver bruger til deres Microsoft Family Safety entity-prefix. Giver adgang til skærmtid, saldo og ønsker direkte i panelet.</div>
      <div class="fs-mapping-list" id="fs-mapping-list">
        ${(()=>{
          const fsMap = cfg.family_safety_mappings || {};
          const trackedUsers = cfg.tracked_users || [];
          return trackedUsers.map(u => {
            const prefix = fsMap[u] || "";
            return `
              <div class="fs-mapping-row">
                <div class="fs-mapping-col">
                  <label class="cfg-label">👤 Bruger</label>
                  <input class="cfg-input" type="text" value="${this._esc(u)}" disabled style="opacity:.6">
                </div>
                <div class="mapping-arrow">→</div>
                <div class="fs-mapping-col">
                  <label class="cfg-label">Entity prefix</label>
                  <input class="cfg-fs-prefix cfg-input" type="text"
                    data-user="${this._esc(u)}"
                    value="${this._esc(prefix)}"
                    placeholder="f.eks. sebastian_hansen_family_safety_sebastian">
                  <span class="cfg-hint-small">Prefix foran _screen_time, _balance osv. (uden sensor. og uden suffixet)</span>
                </div>
              </div>`;
          }).join("");
        })()}
      </div>
      <div class="section-title" style="margin-top:24px">🗂️ Tab-rækkefølge</div>
      <div class="cfg-hint">Træk og slip tabs for at ændre rækkefølgen.</div>
      <div class="tab-sorter" id="tab-sorter">
        ${this._orderedTabs().map((t,i)=>`
          <div class="tab-sort-item" draggable="true" data-idx="${i}" data-id="${t.id}">
            <span class="drag-handle">⠿</span><span class="tab-sort-icon">${t.icon}</span>
            <span class="tab-sort-label">${t.label}</span>
          </div>`).join("")}
      </div>
      <button class="reset-tabs-btn">↺ Nulstil rækkefølge</button>
      <div class="section-title" style="margin-top:24px">💾 Gem konfiguration</div>
      <div class="cfg-save-row sticky">
        <button class="cfg-save-btn save-btn" ${this._configSaving?"disabled":""}>
          ${this._configSaving?"💾 Gemmer og genindlæser...":"💾 Gem konfiguration"}
        </button>
        <button class="cfg-cancel-btn cancel-btn" ${this._configSaving?"disabled":""}>Annuller</button>
      </div>
      <div class="cfg-info-box">
        <div class="cfg-info-title">ℹ️ Hvad sker der når du gemmer?</div>
        <div class="cfg-info-body">Home Assistant opdaterer konfigurationen og genindlæser integrationen automatisk. Dine historiske data i InfluxDB påvirkes ikke.</div>
      </div>`;
  }

  // ── Admin / Health ────────────────────────────────────────────
  _adminHTML() {
    const sys=this._system, h=this._health;
    if (!sys) return `<div class="empty-state">Indlæser...</div>`;
    const bufOk=(h?.buffer_size??0)===0;
    const monthlyOk=h?.monthly_loaded!==false;
    const flushOk=h?.last_flush_age_s==null||h.last_flush_age_s<120;
    const timerOk=h?.flush_timer_active!==false;
    const influxOk=(h?.write_age_s!=null&&h.write_age_s<300)||!h?.acc_time;
    const snapshotOk=h?.snapshot_age_s==null||h.snapshot_age_s<300;
    const allOk=bufOk&&monthlyOk&&flushOk&&timerOk;
    const statusClass=allOk?"ok":(!bufOk||!monthlyOk||!timerOk)?"err":"warn";
    const statusIcon=allOk?"✅":(!bufOk||!monthlyOk||!timerOk)?"❌":"⚠️";
    const statusLabel=allOk?"Alt OK — systemet kører normalt":!monthlyOk?"Monthly data ikke indlæst":!timerOk?"Flush-timer inaktiv — session-data risikerer tab":`${h?.buffer_size} writes i buffer`;

    const metrics=[
      { icon:h?.current_user?"🎮":"💤", val:h?.current_user?h.current_user.charAt(0).toUpperCase()+h.current_user.slice(1):"Ingen",
        lbl:"Aktiv bruger", desc:"Hvem der spiller lige nu", cls:"ok" },
      { icon:monthlyOk?"✅":"⏳", val:monthlyOk?"Indlæst":"Afventer…",
        lbl:"Monthly data", desc:"Måneds-totaler fra InfluxDB", cls:monthlyOk?"ok":"warn" },
      { icon:bufOk?"✅":"⚠️", val:`${h?.buffer_size??0} / ${h?.buffer_max??100}`,
        lbl:"Write buffer", desc:"Fejlede InfluxDB writes der venter på retry", cls:bufOk?"ok":"err" },
      { icon:flushOk?"✅":"⚠️", val:this._fmtAge(h?.last_flush_age_s),
        lbl:"Session flush", desc:"Periodisk snapshot til disk (hvert 60s)", cls:flushOk?"ok":"warn" },
      { icon:timerOk?"✅":"❌", val:timerOk?`Aktiv (${h?.flush_interval_s??60}s)`:"INAKTIV",
        lbl:"Flush-timer", desc:"Backup-timer kører i baggrunden", cls:timerOk?"ok":"err" },
      { icon:influxOk?"✅":"⏳", val:this._fmtAge(h?.write_age_s),
        lbl:"Seneste InfluxDB write", desc:"Hvornår data sidst blev skrevet", cls:influxOk?"ok":"warn" },
      { icon:snapshotOk?"✅":"⚠️", val:this._fmtAge(h?.snapshot_age_s),
        lbl:"Snapshot-alder", desc:"Alder på det gemte session-snapshot", cls:snapshotOk?"ok":"warn" },
    ];

    const metricsHTML=metrics.map(m=>`
      <div class="health-metric ${m.cls}">
        <div class="health-metric-icon">${m.icon}</div>
        <div class="health-metric-val">${this._esc(m.val)}</div>
        <div class="health-metric-lbl">${m.lbl}</div>
        <div class="health-metric-desc">${m.desc}</div>
      </div>`).join("");

    const bufPct=Math.round((h?.buffer_size??0)/(h?.buffer_max??100)*100);
    const bufColor=bufPct>75?"var(--red)":bufPct>40?"var(--orange)":"var(--green)";
    const cards=[
      ["Version", sys.version],
      ["InfluxDB", `${sys.influxdb_host}:${sys.influxdb_port}`],
      ["Database", sys.influxdb_database],
      ["Brugere",  (sys.tracked_users||[]).join(", ")],
    ].map(([l,v])=>`<div class="admin-card"><div class="admin-card-label">${l}</div><div class="admin-card-value">${this._esc(v)}</div></div>`).join("");
    const mapRows=Object.entries(sys.user_map||{}).map(([k,v])=>
      `<div class="mapping-row"><code>${this._esc(k)}</code><span>${this._esc(v)}</span></div>`).join("");

    return `
      <div class="health-status-bar ${statusClass}">${statusIcon} ${statusLabel}</div>
      <div class="section-title">System Health</div>
      <div class="health-grid">${metricsHTML}</div>
      <div class="section-title">Write Buffer</div>
      <div class="buffer-card">
        <div class="buffer-header"><span>Bufferede writes</span><span style="color:${bufColor};font-weight:600">${h?.buffer_size??0} / ${h?.buffer_max??100}</span></div>
        <div class="buffer-bar-bg"><div class="buffer-bar-fill" style="width:${bufPct}%;background:${bufColor}"></div></div>
        <div class="buffer-hint">${(h?.buffer_size??0)===0
          ?`<span style="color:var(--green)">✅ Ingen fejlede writes</span>`
          :`<span style="color:var(--orange)">⚠️ ${h.buffer_size} punkter venter på retry</span>`}</div>
      </div>
      <div class="section-title">System info</div>
      <div class="admin-grid">${cards}</div>
      <div class="section-title">Bruger mappings</div>
      <div class="mapping-table">
        <div class="mapping-header"><span>Sensor tilstand</span><span>Bruger ID</span></div>
        ${mapRows}
      </div>
      <div class="section-title">Manuel korrektion</div>
      <div class="card" style="display:flex;flex-direction:column;gap:10px;padding:16px">
        <div class="form-row">
          <label>Bruger</label>
          <select id="manual-user">
            ${(sys.tracked_users||[]).map(u=>`<option value="${this._esc(u)}">${this._esc(u.charAt(0).toUpperCase()+u.slice(1))}</option>`).join("")}
          </select>
        </div>
        <div class="form-row">
          <label>Dato</label>
          <input type="date" id="manual-date" value="${new Date().toISOString().slice(0,10)}">
        </div>
        <div class="form-row">
          <label>Tid (min)</label>
          <input type="number" id="manual-time" min="1" step="1" placeholder="f.eks. 450">
          <span class="form-hint">7,5 timer = 450 min</span>
        </div>
        <div class="form-row">
          <label>Energi (kWh)</label>
          <input type="number" id="manual-energy" min="0" step="0.001" placeholder="0">
          <span class="form-hint">Valgfri</span>
        </div>
        <div class="form-row">
          <label>Pris (kr)</label>
          <input type="number" id="manual-cost" min="0" step="0.01" placeholder="0">
          <span class="form-hint">Valgfri</span>
        </div>
        <div class="form-actions">
          <button class="save-btn" id="manual-save-btn" ${this._manualSaving?"disabled":""}>
            ${this._manualSaving?"\ud83d\udcbe Gemmer...":"\ud83d\udcbe Tilf\u00f8j korrektion"}
          </button>
        </div>
        ${this._manualMsg?`<div class="cfg-banner ${this._manualMsg.ok?"success":"error"}">${this._esc(this._manualMsg.text)}</div>`:""}
      </div>
      <div class="admin-hint">Brug kun til sj\u00e6ldne tilf\u00e6lde hvor en session ikke blev registreret automatisk (f.eks. filer overskrevet midt i en session). Tilf\u00f8jer et ekstra punkt til InfluxDB tagget <code>source=manual</code> og opdaterer m\u00e5nedstotalerne med det samme.</div>
      <div class="admin-hint">Rediger under <strong>Indstillinger → Enheder & tjenester → PC User Statistics → Konfigurer</strong></div>`;
  }

  // ── Render ────────────────────────────────────────────────────
  _render() {
    if (this._tab==="config"&&!this._forceRender) {
      const active=this.shadowRoot?.activeElement;
      if (active&&(active.tagName==="INPUT"||active.tagName==="SELECT"||active.tagName==="TEXTAREA")) return;
    }
    this._forceRender=false;
    let content="";
    if      (this._tab==="live")          content=this._liveHTML();
    else if (this._tab==="statistik")     content=this._statistikHTML();
    else if (this._tab==="notifications") content=this._notificationsHTML();
    else if (this._tab==="history")       content=this._historyHTML();
    else if (this._tab==="config")        content=this._configHTML();
    else if (this._tab==="admin")         content=this._adminHTML();
    // First render: build full shadow DOM including style and panel structure.
    // Subsequent renders: update only the scrollable content area so scroll
    // position is preserved and the topbar/style nodes are not recreated.
    const existing = this.shadowRoot.querySelector(".panel-scroll");
    if (!existing) {
      this.shadowRoot.innerHTML=`
        <style>${this._css()}</style>
        <div class="panel">
          <div class="panel-topbar">
            ${this._headerHTML()}
            ${this._tabsHTML()}
          </div>
          <div class="panel-scroll">${content}</div>
        </div>`;
    } else {
      // Preserve scroll position across data refreshes
      const scrollEl = existing;
      const savedScroll = scrollEl.scrollTop;
      // Rebuild topbar in-place (tab highlight may change)
      const topbar = this.shadowRoot.querySelector(".panel-topbar");
      if (topbar) topbar.innerHTML = this._headerHTML() + this._tabsHTML();
      scrollEl.innerHTML = content;
      scrollEl.scrollTop = savedScroll;
    }
    this._bind();
  }

  // ── Event binding ─────────────────────────────────────────────
  _bind() {
    const root=this.shadowRoot;

    root.querySelectorAll(".tab").forEach(el=>{
      el.addEventListener("click",()=>{
        this._tab=el.dataset.tab; this._render();
        if (el.dataset.tab==="history"&&!this._history) this._loadHistory();
        if (el.dataset.tab==="config"&&!this._config)   this._loadConfig();
        if (el.dataset.tab==="config"&&!this._haUsers.length) this._loadHaUsers();
        if (el.dataset.tab==="admin") this._loadForTab();
      });
    });

    root.getElementById("refresh-btn")?.addEventListener("click",()=>{
      this._stats=null; this._system=null; this._health=null; this._notif=null;
      this._render(); this._load();
    });

    root.querySelectorAll(".metric-btn").forEach(el=>{
      el.addEventListener("click",()=>{ this._histMetric=el.dataset.metric; this._render(); });
    });
    root.querySelector(".reload-hist-btn")?.addEventListener("click",()=>{
      this._history=null; this._render(); this._loadHistory();
    });

    root.querySelectorAll(".rule-toggle").forEach(el=>{
      el.addEventListener("change",()=>this._toggleRule(el.dataset.rule));
    });
    root.querySelectorAll("[data-test]").forEach(el=>{
      el.addEventListener("click",()=>this._testRule(el.dataset.test));
    });
    root.querySelectorAll(".edit-btn").forEach(el=>{
      el.addEventListener("click",()=>{
        const rid=el.dataset.rule;
        this._editingRule=this._editingRule===rid?null:rid; this._render();
      });
    });
    root.querySelectorAll(".del-btn").forEach(el=>{
      el.addEventListener("click",()=>this._deleteRule(el.dataset.rule));
    });
    root.querySelector(".show-create-btn")?.addEventListener("click",()=>{
      this._showCreate=!this._showCreate; this._render();
    });
    root.querySelector(".save-new-btn")?.addEventListener("click",()=>{
      const f=root.querySelector(".create-form-inner"); if (!f) return;
      const cfg=this._collectRuleForm(f);
      if (!cfg.id) cfg.id="custom_"+Date.now();
      this._saveRule(cfg.id,cfg);
    });
    root.querySelector(".cancel-new-btn")?.addEventListener("click",()=>{
      this._showCreate=false; this._newRule=this._emptyRule(); this._render();
    });
    root.querySelectorAll(".save-edit-btn").forEach(el=>{
      el.addEventListener("click",()=>{
        const f=el.closest(".edit-form"); if (!f) return;
        const rid=this._editingRule, cfg=this._collectRuleForm(f); cfg.id=rid;
        this._saveRule(rid,cfg);
      });
    });
    root.querySelectorAll(".cancel-edit-btn").forEach(el=>{
      el.addEventListener("click",()=>{ this._editingRule=null; this._render(); });
    });
    root.querySelectorAll(".dev-check").forEach(el=>{
      el.addEventListener("change",()=>{
        const checked=[...root.querySelectorAll(".dev-check:checked")].map(c=>c.value);
        this._saveDevices(checked);
      });
    });

    // Manual correction (Admin tab)
    root.getElementById("manual-save-btn")?.addEventListener("click",()=>{
      this._saveManualEntry();
    });

    // Config save
    root.querySelector(".cfg-save-btn")?.addEventListener("click",async()=>{
      this._configSaving=true; this._forceRender=true; this._render();
      try {
        // Save main config first (family_safety_mappings excluded — sent separately)
        const payload=this._collectConfigPayload();
        const { family_safety_mappings: fsMappings, ...configPayload } = payload;
        await this._hass.callWS({ type:"pc_user_statistics/save_config", ...configPayload });
        // Save Family Safety mappings via dedicated command (bypasses voluptuous arbitrary-key restriction)
        await this._hass.callWS({ type:"pc_user_statistics/save_family_safety", family_safety_mappings: fsMappings });
        // Keep local config in sync so fields stay filled after re-render
        if (this._config) this._config = { ...this._config, family_safety_mappings: fsMappings };
        this._configState="saved";
      } catch(e) { console.error(e); this._configState="error"; }
      this._configSaving=false; this._forceRender=true; this._render();
      if (this._configState==="saved") setTimeout(()=>{ this._configState=null; this._forceRender=true; this._render(); },4000);
    });
    root.querySelector(".cfg-cancel-btn")?.addEventListener("click",()=>{
      this._configState=null; this._forceRender=true; this._render();
    });
    root.querySelector(".add-mapping-btn")?.addEventListener("click",()=>{
      if (!this._config) return;
      const cur=this._config.user_mappings||{};
      this._config={...this._config, user_mappings:{...cur,"":" "}};
      this._forceRender=true; this._render();
    });
    root.querySelectorAll(".remove-row-btn").forEach(el=>{
      el.addEventListener("click",()=>{
        const idx=parseInt(el.dataset.idx);
        const rows=root.querySelectorAll(".user-mapping-row");
        const entries=[...rows].map(r=>({
          sensorState:r.querySelector(".cfg-sensor-state")?.value||"",
          userId:r.querySelector(".cfg-user-id")?.value||"",
          haUser:r.querySelector(".cfg-ha-user")?.value||"",
        })).filter((_,i)=>i!==idx);
        const newMap={};
        entries.forEach(e=>{ if (e.sensorState) newMap[e.sensorState]=e.haUser?{user_id:e.userId,ha_user:e.haUser}:e.userId; });
        if (!this._config) return;
        this._config={...this._config, user_mappings:newMap};
        this._forceRender=true; this._render();
      });
    });

    // Tab drag & drop
    const sorter=root.getElementById("tab-sorter");
    if (sorter) {
      sorter.querySelectorAll(".tab-sort-item").forEach(item=>{
        item.addEventListener("dragstart",e=>{ this._dragSrc=parseInt(item.dataset.idx); item.classList.add("dragging"); e.dataTransfer.effectAllowed="move"; });
        item.addEventListener("dragend",()=>item.classList.remove("dragging"));
        item.addEventListener("dragover",e=>{ e.preventDefault(); item.classList.add("drag-over"); });
        item.addEventListener("dragleave",()=>item.classList.remove("drag-over"));
        item.addEventListener("drop",e=>{
          e.preventDefault(); item.classList.remove("drag-over");
          const dst=parseInt(item.dataset.idx);
          if (this._dragSrc===null||this._dragSrc===dst) return;
          const newOrder=[...this._tabOrder];
          const [moved]=newOrder.splice(this._dragSrc,1);
          newOrder.splice(dst,0,moved);
          this._saveTabOrder(newOrder); this._render();
        });
      });
    }
    root.querySelector(".reset-tabs-btn")?.addEventListener("click",()=>{
      this._saveTabOrder(PcUserStatisticsPanel.ALL_TABS.map(t=>t.id)); this._render();
    });
  }

  _collectRuleForm(f) {
    const targets=[...(f.querySelectorAll(".f-user:checked")||[])].map(c=>c.value);
    return {
      name:f.querySelector(".f-name")?.value||"",
      icon:f.querySelector(".f-icon")?.value||"🔔",
      trigger_type:f.querySelector(".f-ttype")?.value||"session_minutes",
      trigger_value:parseFloat(f.querySelector(".f-tval")?.value||"60"),
      title:f.querySelector(".f-title")?.value||"",
      message:f.querySelector(".f-msg")?.value||"",
      repeat:f.querySelector(".f-repeat")?.checked??false,
      repeat_interval:parseInt(f.querySelector(".f-interval")?.value||"60"),
      enabled:true, user_targets:targets, is_custom:true,
    };
  }

  _collectConfigPayload() {
    const root=this.shadowRoot;
    const rows=root.querySelectorAll(".user-mapping-row");
    const userMappings={};
    rows.forEach(r=>{
      const state=r.querySelector(".cfg-sensor-state")?.value?.trim()||"";
      const userId=r.querySelector(".cfg-user-id")?.value?.trim()||"";
      const haUser=r.querySelector(".cfg-ha-user")?.value?.trim()||"";
      if (state&&userId) userMappings[state]=haUser?{user_id:userId,ha_user:haUser}:userId;
    });
    const trackedUsers=Object.values(userMappings).map(v=>typeof v==="object"?v.user_id:v).filter(Boolean);
    // Collect Family Safety prefix mappings inline — avoids a separate WS call
    const fsMappings={};
    root.querySelectorAll(".cfg-fs-prefix").forEach(el=>{
      const user=el.dataset.user;
      const prefix=el.value?.trim()||"";
      // Only include non-empty prefixes — empty means "leave existing value alone"
      if (user && prefix) fsMappings[user]=prefix;
    });
    // Merge with existing mappings so untouched users aren't cleared
    const existingFs = (this._config?.family_safety_mappings) || {};
    const mergedFs = { ...existingFs, ...fsMappings };
    const payload={ user_mappings:userMappings, tracked_users:trackedUsers,
      user_entity:root.querySelector(".cfg-user-entity")?.value?.trim()||"",
      watt_entity:root.querySelector(".cfg-watt-entity")?.value?.trim()||"",
      device_power_entity:root.querySelector(".cfg-device-power-entity")?.value?.trim()||"",
      price_entity:root.querySelector(".cfg-price-entity")?.value?.trim()||"" };
    [1,2,3,4,5].forEach(n=>{
      payload[`gauge${n}_entity`]=root.querySelector(`.cfg-gauge${n}-entity`)?.value?.trim()||"";
      payload[`gauge${n}_label`] =root.querySelector(`.cfg-gauge${n}-label`)?.value?.trim()||"";
      payload[`gauge${n}_max`]   =root.querySelector(`.cfg-gauge${n}-max`)?.value?.trim()||"";
    });
    payload.family_safety_mappings = mergedFs;
    return payload;
  }
}

if (!customElements.get("pc-user-statistics-panel")) {
  customElements.define("pc-user-statistics-panel", PcUserStatisticsPanel);
}
