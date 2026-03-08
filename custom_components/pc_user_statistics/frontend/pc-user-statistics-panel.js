// PC User Statistics Panel
// Version: 2.5.0 — Vanilla JS (no imports)
// Last Updated: March 2, 2026
//
// Fixes in 2.5.0:
//   - FIX: TypeError: Assignment to constant variable in _statisticsHTML()
//          const s was reassigned — now uses let sd (separate normalized copy)
//   - FIX: CustomElementRegistry: name "pc-user-statistics-panel" already used
//          Added customElements.get() guard before define()

class PcUserStatisticsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass       = null;
    this._tab        = "live";
    this._history    = null;
    this._histMetric = "time"; // time | energy | cost
    this._stats      = null;
    this._system     = null;
    this._notif      = null;
    this._savingRule = null;
    this._editingRule= null;
    this._showCreate = false;
    this._newRule    = this._emptyRule();
    this._interval     = null;
    this._wattInterval = null;
    this._watt         = null;   // live watts from HA state
    this._gaugeStates  = { gauge1: null, gauge2: null, gauge3: null, gauge4: null, gauge5: null }; // live gauge values
    this._errCount     = 0;
    this._isDark       = false;
    this._config       = null;
    this._configSaving = false;
    this._configDirty  = false;
    this._configState  = null; // null | 'saved' | 'error'
    this._forceRender  = false;
    this._tabOrder     = this._loadTabOrder();
    this._dragSrc      = null; // index being dragged
    this._haUsers      = [];   // [{id, name}] fra config/auth/list
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    // Detect dark mode from HA theme
    this._isDark = h.themes?.darkMode ?? (window.matchMedia?.("(prefers-color-scheme:dark)").matches ?? false);
    if (first) this._load();
    // Update live watt from HA state (no extra WS call)
    const wattEntity = "sensor.gamer_pc_power_monitor_current_consumption";
    const st = h.states?.[wattEntity];
    const raw = st ? parseFloat(st.state) : null;
    this._watt = raw && !isNaN(raw) ? raw : null;
    // Update live gauge states from HA (no extra WS call)
    this._updateGaugeStates();
    // Update bars in-place if live tab is showing
    if (this._tab === "live") this._updateBarsInPlace();
    // Only re-render header+watt area to avoid full flash
    this._updateWattDisplay();
  }

  connectedCallback() {
    this._render();
    this._interval = setInterval(() => {
      if (this._errCount > 3) { clearInterval(this._interval); return; }
      if (document.visibilityState === "visible") this._loadForTab();
    }, 30000);
  }

  disconnectedCallback() {
    clearInterval(this._interval);
  }

  _updateWattDisplay() {
    const el = this.shadowRoot?.querySelector(".watt-value");
    if (!el) return;
    el.textContent = this._watt != null ? this._watt.toFixed(0)+"W" : "—";
    const ring = this.shadowRoot?.querySelector(".watt-ring");
    if (ring) ring.style.opacity = this._watt > 20 ? "1" : "0.3";
  }

  _updateGaugeStates() {
    if (!this._hass || !this._config) return;
    const cfg = this._config;
    [1, 2, 3, 4, 5].forEach(n => {
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

  // Full load — used on first connect and manual refresh button
  async _load() {
    if (!this._hass) return;
    try {
      const [stats, system, notif, config] = await Promise.all([
        this._hass.callWS({ type: "pc_user_statistics/get_stats" }),
        this._hass.callWS({ type: "pc_user_statistics/get_system" }),
        this._hass.callWS({ type: "pc_user_statistics/get_notifications" }),
        this._hass.callWS({ type: "pc_user_statistics/get_config" }),
      ]);
      this._stats  = stats;
      this._system = system;
      this._notif  = notif;
      if (config) this._config = config;
      this._errCount = 0;
    } catch (e) {
      this._errCount++;
      console.error("PC Stats load error:", e);
    }
    this._updateGaugeStates();
    this._render();
  }

  // Smart poll — only fetches what the active tab actually needs.
  // History and config are static; no need to re-fetch on every tick.
  async _loadForTab() {
    if (!this._hass) return;
    try {
      const tab = this._tab;
      if (tab === "live" || tab === "statistik") {
        this._stats = await this._hass.callWS({ type: "pc_user_statistics/get_stats" });
      } else if (tab === "notifications") {
        const [stats, notif] = await Promise.all([
          this._hass.callWS({ type: "pc_user_statistics/get_stats" }),
          this._hass.callWS({ type: "pc_user_statistics/get_notifications" }),
        ]);
        this._stats = stats;
        this._notif = notif;
      } else if (tab === "admin") {
        const [stats, system] = await Promise.all([
          this._hass.callWS({ type: "pc_user_statistics/get_stats" }),
          this._hass.callWS({ type: "pc_user_statistics/get_system" }),
        ]);
        this._stats  = stats;
        this._system = system;
      }
      // history + config: never auto-refresh
      this._errCount = 0;
    } catch (e) {
      this._errCount++;
      console.error("PC Stats poll error:", e);
    }
    this._render();
  }

  async _loadHistory() {
    if (!this._hass) return;
    try {
      this._history = await this._hass.callWS({ type: "pc_user_statistics/get_history", days: 30 });
    } catch(e) {
      console.error("History load error:", e);
      this._history = { days: [], users: [], series: {} };
    }
    this._render();
  }

  // ── Formatters ────────────────────────────────────────────────
  _fmtTime(s) {
    if (!s || s < 0) return "0t 0m";
    return `${Math.floor(s/3600)}t ${Math.floor((s%3600)/60)}m`;
  }
  _fmtEnergy(k) { return k ? k.toFixed(3).replace(".",",")+" kWh" : "0,000 kWh"; }
  _fmtCost(d)   { return d ? d.toFixed(2).replace(".",",")+" kr"  : "0,00 kr"; }
  _userColor(n) {
    const cols = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6"];
    const users = this._stats?.tracked_users ?? [];
    const idx = users.indexOf((n || "").toLowerCase());
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
    this._savingRule = ruleId;
    this._render();
    try {
      await this._hass.callWS({ type:"pc_user_statistics/save_notification", rule_id:ruleId, config });
      this._notif.rules[ruleId] = config;
      if (ruleId === (this._newRule.id||"new")) {
        this._showCreate = false;
        this._newRule    = this._emptyRule();
      }
      this._editingRule = null;
    } catch(e) { console.error(e); }
    this._savingRule = null;
    this._render();
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

  // ── Tab order persistence ─────────────────────────────────────
  static get ALL_TABS() {
    return [
      {id:"live",          label:"Live",            icon:"🎮"},
      {id:"statistik",     label:"Statistik",       icon:"📊"},
      {id:"notifications", label:"Notifikationer",  icon:"🔔"},
      {id:"history",       label:"Historik",        icon:"📈"},
      {id:"config",        label:"Konfiguration",   icon:"🔧"},
      {id:"admin",         label:"Admin",           icon:"⚙️"},
    ];
  }

  _loadTabOrder() {
    try {
      const saved = localStorage.getItem("pc_stats_tab_order");
      if (saved) {
        const ids = JSON.parse(saved);
        const allIds = PcUserStatisticsPanel.ALL_TABS.map(t => t.id);
        const valid = ids.filter(id => allIds.includes(id));
        allIds.forEach(id => { if (!valid.includes(id)) valid.push(id); });
        return valid;
      }
    } catch(e) {}
    return PcUserStatisticsPanel.ALL_TABS.map(t => t.id);
  }

  _saveTabOrder(order) {
    try { localStorage.setItem("pc_stats_tab_order", JSON.stringify(order)); } catch(e) {}
    this._tabOrder = order;
  }

  _orderedTabs() {
    const all = PcUserStatisticsPanel.ALL_TABS;
    return this._tabOrder
      .map(id => all.find(t => t.id === id))
      .filter(Boolean);
  }

  // ── Config load/save ──────────────────────────────────────────
  async _loadConfig() {
    if (!this._hass) return;
    try {
      this._config = await this._hass.callWS({ type: "pc_user_statistics/get_config" });
    } catch(e) {
      console.error("Config load error:", e);
      this._config = {};
    }
    // Now that config is loaded, update gauge states from current hass.states
    this._updateGaugeStates();
    this._render();
  }

  async _loadHaUsers() {
    try {
      const result = await this._hass.callWS({ type: "config/auth/list" });
      this._haUsers = (result || []).map(u => ({ id: u.id, name: u.name }));
      this._render();
    } catch (e) {
      console.warn("[PC Stats] Kunne ikke hente HA brugere:", e);
    }
  }

  async _saveConfig() {
    if (!this._hass || this._configSaving) return;
    const root = this.shadowRoot;

    const getVal = cls => root.querySelector(cls)?.value?.trim() || "";
    const payload = {
      user_entity:         getVal(".cfg-user-entity"),
      watt_entity:         getVal(".cfg-watt-entity"),
      device_power_entity: getVal(".cfg-device-power-entity"),
      price_entity:        getVal(".cfg-price-entity"),
      gauge1_entity:       getVal(".cfg-gauge1-entity"),
      gauge1_label:        getVal(".cfg-gauge1-label"),
      gauge2_entity:       getVal(".cfg-gauge2-entity"),
      gauge2_label:        getVal(".cfg-gauge2-label"),
      gauge3_entity:       getVal(".cfg-gauge3-entity"),
      gauge3_label:        getVal(".cfg-gauge3-label"),
      gauge4_entity:       getVal(".cfg-gauge4-entity"),
      gauge4_label:        getVal(".cfg-gauge4-label"),
      gauge5_entity:       getVal(".cfg-gauge5-entity"),
      gauge5_label:        getVal(".cfg-gauge5-label"),
      user_mappings: {},
      tracked_users: [],
    };

    const rows = root.querySelectorAll(".user-mapping-row");
    let valid = true;
    rows.forEach(row => {
      const sensorState = row.querySelector(".cfg-sensor-state")?.value?.trim();
      const userId      = row.querySelector(".cfg-user-id")?.value?.trim().toLowerCase();
      const haUser      = row.querySelector(".cfg-ha-user")?.value?.trim() || "";
      if (sensorState && userId) {
        payload.user_mappings[sensorState] = haUser
          ? { user_id: userId, ha_user: haUser }
          : userId;
        if (!payload.tracked_users.includes(userId))
          payload.tracked_users.push(userId);
      } else if (sensorState || userId) {
        valid = false;
      }
    });

    if (!valid) { alert("Alle bruger-rækker skal have både sensor-tilstand og bruger-ID"); return; }
    if (!payload.tracked_users.length) { alert("Mindst én bruger skal konfigureres"); return; }

    this._configSaving = true;
    this._configState  = null;
    this._forceRender  = true;
    this._render();

    try {
      await this._hass.callWS({ type: "pc_user_statistics/save_config", ...payload });
      this._configState  = "saved";
      this._configSaving = false;
      // Reload config from server so ha_user dict values are preserved correctly
      await this._loadConfig();
      this._forceRender = true;
      this._render();
    } catch(e) {
      console.error("Save config error:", e);
      this._configState  = "error";
      this._configSaving = false;
      this._forceRender  = true;
      this._render();
    }
  }

  // ── Live Gauge (circular, valgfri sensor) ─────────────────────
  _barsHTML() {
    // Renders configured gauge sensors as vertical bar columns (card-style).
    // Always visible when configured — values updated in-place via _updateGaugeStates().
    const cfg = this._config || {};
    const BAR_COLORS = ["#6366f1","#f59e0b","#10b981","#8b5cf6","#06b6d4"];
    const bars = [1,2,3,4,5].map(n => {
      const entity = cfg[`gauge${n}_entity`];
      if (!entity) return "";
      const label = cfg[`gauge${n}_label`] || `G${n}`;
      const raw   = this._gaugeStates?.[`gauge${n}`];
      const val   = raw !== null && raw !== undefined && raw !== "unavailable" && raw !== "unknown"
        ? parseFloat(raw) : null;
      const pct   = val !== null && !isNaN(val) ? Math.min(Math.max(val, 0), 100) : 0;
      const color = BAR_COLORS[(n-1) % BAR_COLORS.length];
      const danger = pct > 90 ? "#ef4444" : pct > 70 ? "#f59e0b" : color;
      const dv    = val !== null && !isNaN(val)
        ? (Number.isInteger(val) ? val+"%" : val.toFixed(1))
        : "—";
      return `<div class="bar-col">
        <div class="bar-val bar-val-${n}" style="color:${danger}">${dv}</div>
        <div class="bar-track">
          <div class="bar-fill bar-fill-${n}" style="height:${pct}%;background:${danger}"></div>
        </div>
        <div class="bar-label">${this._esc(label)}</div>
      </div>`;
    }).join("");
    return bars;
  }

  _updateBarsInPlace() {
    // Update bar values and fills in-place without re-rendering the full panel.
    const cfg = this._config || {};
    const BAR_COLORS = ["#6366f1","#f59e0b","#10b981","#8b5cf6","#06b6d4"];
    [1,2,3,4,5].forEach(n => {
      const entity = cfg[`gauge${n}_entity`];
      if (!entity) return;
      const raw  = this._gaugeStates?.[`gauge${n}`];
      const val  = raw !== null && raw !== undefined && raw !== "unavailable" && raw !== "unknown"
        ? parseFloat(raw) : null;
      const pct  = val !== null && !isNaN(val) ? Math.min(Math.max(val, 0), 100) : 0;
      const color = BAR_COLORS[(n-1) % BAR_COLORS.length];
      const danger = pct > 90 ? "#ef4444" : pct > 70 ? "#f59e0b" : color;
      const dv   = val !== null && !isNaN(val)
        ? (Number.isInteger(val) ? val+"%" : val.toFixed(1))
        : "—";
      const valEl  = this.shadowRoot?.querySelector(`.bar-val-${n}`);
      const fillEl = this.shadowRoot?.querySelector(`.bar-fill-${n}`);
      if (valEl)  { valEl.textContent = dv; valEl.style.color = danger; }
      if (fillEl) { fillEl.style.height = pct + "%"; fillEl.style.background = danger; }
    });
  }

  // ── SVG Donut ─────────────────────────────────────────────────
  _donutSVG(users, monthly) {
    const COLORS = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6"];
    const vals   = users.map(u => monthly[u]?.time||0);
    const total  = vals.reduce((a,b)=>a+b,0);
    if (total===0) return `
      <svg viewBox="0 0 120 120" class="donut-svg">
        <circle cx="60" cy="60" r="44" fill="none" stroke="var(--divider)" stroke-width="18"/>
      </svg>
      <div class="donut-center"><div class="donut-center-label">Ingen data</div></div>`;

    const R=44, circ=2*Math.PI*R, startOff=circ/4;
    let offset=0;
    const segs = users.map((u,i)=>{
      const pct=vals[i]/total, dash=pct*circ, gap=circ-dash;
      const s={u,pct,dash,gap,color:COLORS[i%COLORS.length],offset};
      offset+=dash; return s;
    });

    const topIdx = vals.indexOf(Math.max(...vals));
    const topUser = users[topIdx], topPct = Math.round(vals[topIdx]/total*100);

    const circles = segs.map(s=>`
      <circle cx="60" cy="60" r="44" fill="none"
        stroke="${s.color}" stroke-width="18"
        stroke-dasharray="${s.dash} ${s.gap}"
        stroke-dashoffset="${startOff - s.offset}"
        stroke-linecap="butt"/>`).join("");

    const legend = segs.map(s=>`
      <div class="legend-row">
        <span class="legend-dot" style="background:${s.color}"></span>
        <span class="legend-name">${this._esc(s.u)}</span>
        <span class="legend-pct">${Math.round(s.pct*100)}%</span>
      </div>`).join("");

    return `
      <div class="donut-ring">
        <svg viewBox="0 0 120 120" class="donut-svg">${circles}</svg>
        <div class="donut-center">
          <div class="donut-top-user" style="color:${COLORS[topIdx%COLORS.length]}">${this._esc(topUser)}</div>
          <div class="donut-top-pct">${topPct}%</div>
        </div>
      </div>
      <div class="donut-legend">${legend}</div>`;
  }

  // ── HTML builders ─────────────────────────────────────────────
  _tabsHTML() {
    return this._orderedTabs().map(t=>`
      <button class="tab${this._tab===t.id?" active":""}" data-tab="${t.id}">
        <span class="tab-icon">${t.icon}</span>
        <span class="tab-label">${t.label}</span>
      </button>`).join("");
  }

  _headerHTML() {
    const rawUser = this._stats?.current_user;
    const user    = rawUser && typeof rawUser === "object" ? (rawUser.name ?? rawUser.id ?? String(rawUser)) : (rawUser || null);
    const isLive  = !!user;
    const wattTxt = this._watt != null ? this._watt.toFixed(0)+"W" : "—";
    const wattPct = this._watt != null ? Math.min(this._watt / 600, 1) : 0;
    const wattDeg = Math.round(wattPct * 180);
    const r = 28, cx = 34, cy = 34;
    const toRad = d => d * Math.PI / 180;
    const arcX  = cx + r * Math.cos(toRad(180 + wattDeg));
    const arcY  = cy + r * Math.sin(toRad(180 + wattDeg));
    const large = wattDeg > 180 ? 1 : 0;
    const wattColor = wattPct > 0.75 ? "#ef4444" : wattPct > 0.4 ? "#f59e0b" : "#4ade80";

    const pulseIcon = isLive
      ? '<div class="pulse-ring-wrap"><div class="pulse-ring watt-ring"></div><div class="pulse-ring pulse-ring-2"></div><span class="icon">🎮</span></div>'
      : '<span class="icon">🎮</span>';

    const subtitle = isLive
      ? '<span class="live-dot"></span> ' + this._esc(user) + ' spiller nu'
      : 'Ingen aktiv session';

    const arcPath = wattDeg > 2
      ? '<path d="M6,34 A' + r + ',' + r + ' 0 ' + large + ',1 ' + arcX.toFixed(1) + ',' + arcY.toFixed(1) + '" fill="none" stroke="' + wattColor + '" stroke-width="5" stroke-linecap="round"/>'
      : '';

    const wattGauge = isLive
      ? '<div class="watt-gauge" title="Live strømforbrug">'
        + '<svg viewBox="0 0 68 40" class="gauge-svg">'
        + '<path d="M6,34 A' + r + ',' + r + ' 0 0,1 62,34" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="5" stroke-linecap="round"/>'
        + arcPath
        + '</svg>'
        + '<div class="watt-center"><span class="watt-value">' + wattTxt + '</span></div>'
        + '</div>'
      : '';

    return '<div class="header' + (isLive ? ' header-live' : '') + '">'
      + '<div class="header-left">'
      + '<button class="menu-btn" title="Menu"><svg viewBox="0 0 24 24"><path d="M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z"/></svg></button>'
      + '<div class="header-title">'
      + pulseIcon
      + '<div><div class="title">PC Statistik</div><div class="subtitle">' + subtitle + '</div></div>'
      + '</div>'
      + '</div>'
      + '<div class="header-right">'
      + wattGauge
      + '<button class="refresh-btn" title="Opdater"><svg viewBox="0 0 24 24"><path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/></svg></button>'
      + '</div>'
      + '</div>';
  }

  // ── FIX: Was reassigning const s → now uses let sd (normalized copy) ──────
  _liveHTML() {
    const s = this._stats;
    if (!s) return `<div class="empty-state">Indlæser...</div>`;
    const users = s.tracked_users||[];
    const monthly = s.monthly||{};

    // Normalize current_user — coordinator may return an object in edge cases
    const rawCU = s.current_user;
    const cu = rawCU && typeof rawCU === "object" ? (rawCU.name ?? rawCU.id ?? String(rawCU)) : (rawCU || null);
    // FIX: use a new let variable instead of reassigning const s
    const sd = { ...s, current_user: cu };

    const sessionActive = sd.current_user ? "active" : "";

    // Build bar columns (always shown when configured)
    const barsHTML = this._barsHTML();
    const hasBars = barsHTML.trim() !== "";

    const userCards = users.map(u => {
      const d = monthly[u]||{};
      const col = this._userColor(u);
      return `
        <div class="user-month-card">
          <div class="user-month-header">
            <div class="avatar" style="background:${col}">${u[0].toUpperCase()}</div>
            <div class="user-month-name">${this._esc(u)}</div>
          </div>
          <div class="user-month-stats">
            <div class="user-stat"><span class="user-stat-label">Tid</span><span class="user-stat-value">${this._fmtTime(d.time)}</span></div>
            <div class="user-stat"><span class="user-stat-label">Energi</span><span class="user-stat-value">${this._fmtEnergy(d.energy)}</span></div>
            <div class="user-stat"><span class="user-stat-label">Pris</span><span class="user-stat-value">${this._fmtCost(d.cost)}</span></div>
          </div>
        </div>`;
    }).join("");

    return `
      <div class="section-title">Live Session</div>
      <div class="live-card">

        <div class="live-left">
          <div class="live-stat ${sessionActive}">
            <div class="live-stat-icon">⏱️</div>
            <div class="live-stat-val">${this._fmtTime(sd.acc_time)}</div>
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

  _statistikHTML() {
    const s = this._stats;
    if (!s) return `<div class="empty-state">Indlæser...</div>`;
    const users   = s.tracked_users||[];
    const monthly = s.monthly||{};

    const userCards = users.map(u => {
      const d = monthly[u]||{};
      const col = this._userColor(u);
      return `
        <div class="user-month-card">
          <div class="user-month-header">
            <div class="avatar" style="background:${col}">${u[0].toUpperCase()}</div>
            <div class="user-month-name">${this._esc(u)}</div>
          </div>
          <div class="user-month-stats">
            <div class="user-stat"><span class="user-stat-label">Tid</span><span class="user-stat-value">${this._fmtTime(d.time)}</span></div>
            <div class="user-stat"><span class="user-stat-label">Energi</span><span class="user-stat-value">${this._fmtEnergy(d.energy)}</span></div>
            <div class="user-stat"><span class="user-stat-label">Pris</span><span class="user-stat-value">${this._fmtCost(d.cost)}</span></div>
          </div>
        </div>`;
    }).join("");

    return `
      <div class="statistik-layout">
        <div class="statistik-left">
          <div class="section-title">Månedlige totaler</div>
          <div class="user-monthly-grid">${userCards}</div>
          <div class="section-title" style="margin-top:20px">🏆 Leaderboard</div>
          ${this._leaderboardHTML(users, monthly)}
        </div>
        <div class="statistik-right">
          <div class="section-title">Fordeling</div>
          <div class="donut-container">${this._donutSVG(users, monthly)}</div>
        </div>
      </div>`;
  }

  _usersHTML() {
    const s = this._stats;
    if (!s) return `<div class="empty-state">Indlæser...</div>`;
    const users = s.tracked_users||[];
    const inv   = Object.fromEntries(Object.entries(s.user_map||{}).map(([k,v])=>[v,k]));

    const activeCard = s.current_user ?
      `<div class="active-user-card">
        <div class="avatar large" style="background:${this._userColor(s.current_user)}">${s.current_user[0].toUpperCase()}</div>
        <div class="active-user-info">
          <div class="active-user-name">${this._esc(s.current_user)}</div>
          <div class="active-user-meta">Spiller i ${this._fmtTime(s.acc_time)}</div>
          <div class="active-user-meta">${this._fmtEnergy(s.acc_energy)} · ${this._fmtCost(s.acc_cost)}</div>
        </div>
        <div class="live-badge">LIVE</div>
      </div>` : `<div class="empty-state">Ingen aktiv bruger</div>`;

    const rows = users.map(u => `
      <div class="user-row${s.current_user===u?" is-active":""}">
        <div class="avatar" style="background:${this._userColor(u)}">${u[0].toUpperCase()}</div>
        <div class="user-row-info">
          <div class="user-row-name">${this._esc(u)}</div>
          <div class="user-row-mapping">Sensor: <code>${this._esc(inv[u]||"?")}</code></div>
        </div>
        ${s.current_user===u
          ? `<span class="live-badge small">LIVE</span>`
          : `<span class="offline-badge">Offline</span>`}
      </div>`).join("");

    return `
      <div class="section-title">Aktiv session</div>
      ${activeCard}
      <div class="section-title">Alle brugere</div>
      <div class="users-list">${rows}</div>`;
  }

  _notificationsHTML() {
    const nd = this._notif;
    if (!nd) return `<div class="empty-state">Indlæser...</div>`;
    const rules     = nd.rules||{};
    const devices   = nd.devices||[];
    const available = nd.available_devices||[];
    const users     = this._stats?.tracked_users||[];
    const premadeIds= ["pause_reminder","long_session","cost_limit","idle_pc"];

    const devRows = available.length===0
      ? `<div class="empty-state small">Ingen HA Companion apps fundet. Installer Home Assistant-appen på din mobil.</div>`
      : available.map(d=>`
          <label class="device-row">
            <input type="checkbox" class="dev-check" value="${this._esc(d.service)}" ${devices.includes(d.service)?"checked":""}>
            <span class="device-name">📱 ${this._esc(d.name)}</span>
            <span class="device-service">${this._esc(d.service)}</span>
          </label>`).join("") +
        (devices.length>0
          ? `<div class="device-hint">✅ ${devices.length} enhed${devices.length>1?"er":""} konfigureret</div>`
          : `<div class="device-hint warn">⚠️ Vælg mindst én enhed</div>`);

    const premade = premadeIds.filter(id=>rules[id]).map(id=>this._ruleCardHTML(id, rules[id], users, false));
    const custom  = Object.entries(rules).filter(([id])=>!premadeIds.includes(id))
                          .map(([id,r])=>this._ruleCardHTML(id,r,users,true));

    const createBtn = `<button class="add-btn show-create-btn">${this._showCreate?"✕ Luk":"+ Ny regel"}</button>`;
    const createForm = this._showCreate ? `<div class="create-form">${this._ruleFormHTML(null, users)}</div>` : "";

    return `
      <div class="section-title">📱 Modtagerenheder</div>
      <div class="device-section">${devRows}</div>

      <div class="section-title">⭐ Premade regler</div>
      <div class="rules-list">${premade.join("")}</div>

      <div class="section-title-row">
        <span class="section-title" style="margin:0">✏️ Egne regler</span>
        ${createBtn}
      </div>
      ${createForm}
      <div class="rules-list">
        ${custom.length===0&&!this._showCreate
          ? `<div class="empty-state small">Ingen egne regler endnu</div>`
          : custom.join("")}
      </div>`;
  }

  _ruleCardHTML(ruleId, rule, users, canDelete) {
    const active  = rule.enabled;
    const editing = this._editingRule === ruleId;
    const chk     = active ? "checked" : "";
    const editLbl = editing ? "✕ Luk" : "✏️ Rediger";

    const preview = active ? `
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
      ${editing ? `<div class="inline-edit">${this._ruleFormHTML(ruleId, users)}</div>` : ""}
    ` : "";

    return `
      <div class="rule-card${active?" active":""}">
        <div class="rule-top">
          <div class="rule-icon">${rule.icon||"🔔"}</div>
          <div class="rule-info">
            <div class="rule-name">${this._esc(rule.name)}</div>
            <div class="rule-trigger">${this._triggerLabel(rule.trigger_type, rule.trigger_value)}</div>
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
    const r       = editRuleId ? { ...this._notif.rules[editRuleId], id:editRuleId } : this._newRule;
    const isEdit  = !!editRuleId;
    const isPremade = isEdit && ["pause_reminder","long_session","cost_limit","idle_pc"].includes(editRuleId);
    const cls     = isEdit ? "edit-form" : "create-form-inner";
    const saveCls = isEdit ? "save-edit-btn" : "save-new-btn";
    const canCls  = isEdit ? "cancel-edit-btn" : "cancel-new-btn";
    const saveLbl = this._savingRule ? "💾 Gemmer..." : (isEdit ? "💾 Gem ændringer" : "💾 Gem regel");

    const userChecks = users.map(u=>`
      <label class="user-check">
        <input type="checkbox" class="f-user" value="${u}" ${r.user_targets?.includes(u)?"checked":""}>
        ${this._esc(u)}
      </label>`).join("");

    const triggerFields = isPremade ? `
      <div class="form-row">
        <label>Trigger-værdi</label>
        <input class="f-tval" type="number" value="${r.trigger_value}" min="1">
        <input type="hidden" class="f-ttype" value="${r.trigger_type}">
        <input type="hidden" class="f-icon" value="${r.icon}">
      </div>` : `
      <div class="form-row">
        <label>Ikon</label>
        <input class="f-icon" type="text" value="${this._esc(r.icon)}" style="width:60px">
      </div>
      <div class="form-row">
        <label>Trigger</label>
        <select class="f-ttype">
          <option value="session_minutes" ${r.trigger_type==="session_minutes"?"selected":""}>Spilletid (min)</option>
          <option value="session_cost"    ${r.trigger_type==="session_cost"   ?"selected":""}>Sessionspris (kr)</option>
          <option value="idle_minutes"    ${r.trigger_type==="idle_minutes"   ?"selected":""}>PC inaktiv (min)</option>
        </select>
      </div>
      <div class="form-row">
        <label>Værdi</label>
        <input class="f-tval" type="number" value="${r.trigger_value}" min="1">
      </div>`;

    return `
      <div class="${cls}">
        ${!isPremade ? `
        <div class="form-row">
          <label>Navn</label>
          <input class="f-name" type="text" value="${this._esc(r.name)}" placeholder="Min regel">
        </div>` : `<input type="hidden" class="f-name" value="${this._esc(r.name)}">`}
        ${triggerFields}
        <div class="form-row">
          <label>Titel</label>
          <input class="f-title" type="text" value="${this._esc(r.title)}" placeholder="{user}, {time}, {cost}">
        </div>
        <div class="form-row">
          <label>Besked</label>
          <input class="f-msg" type="text" value="${this._esc(r.message)}" placeholder="{user}, {time}, {cost}">
        </div>
        <div class="form-row">
          <label>Gentag?</label>
          <label class="toggle">
            <input class="f-repeat" type="checkbox" ${r.repeat?"checked":""}><span class="toggle-slider"></span>
          </label>
        </div>
        <div class="form-row">
          <label>Interval (min)</label>
          <input class="f-interval" type="number" value="${r.repeat_interval}" min="5">
        </div>
        <div class="form-row">
          <label>Brugere</label>
          <div class="user-checkboxes">${userChecks}<span class="form-hint">Tom = alle</span></div>
        </div>
        <div class="form-actions">
          <button class="${saveCls} save-btn" ${this._savingRule?"disabled":""}>${saveLbl}</button>
          <button class="${canCls} cancel-btn">Annuller</button>
        </div>
      </div>`;
  }

  // ── Leaderboard ───────────────────────────────────────────────
  _leaderboardHTML(users, monthly) {
    const COLORS  = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6"];
    const MEDALS  = ["🥇","🥈","🥉"];
    const ranked  = [...users]
      .map(u => ({ u, time: monthly[u]?.time||0, cost: monthly[u]?.cost||0, energy: monthly[u]?.energy||0 }))
      .sort((a,b) => b.time - a.time);

    if (ranked.every(r => r.time === 0))
      return `<div class="empty-state small">Ingen data denne måned endnu</div>`;

    const maxTime = ranked[0].time || 1;

    const rows = ranked.map((r, i) => {
      const pct   = r.time / maxTime * 100;
      const color = COLORS[users.indexOf(r.u) % COLORS.length];
      const medal = MEDALS[i] || `#${i+1}`;
      return `
        <div class="lb-row${i===0?" lb-first":""}">
          <div class="lb-rank">${medal}</div>
          <div class="lb-avatar" style="background:${color}">${r.u[0].toUpperCase()}</div>
          <div class="lb-info">
            <div class="lb-name">${this._esc(r.u)}</div>
            <div class="lb-bar-bg">
              <div class="lb-bar-fill" style="width:${pct.toFixed(1)}%;background:${color}"></div>
            </div>
          </div>
          <div class="lb-stats">
            <div class="lb-time">${this._fmtTime(r.time)}</div>
            <div class="lb-cost">${this._fmtCost(r.cost)}</div>
          </div>
        </div>`;
    }).join("");

    return `<div class="leaderboard">${rows}</div>`;
  }

  // ── History tab ────────────────────────────────────────────────
  _historyHTML() {
    if (!this._history) {
      return `<div class="empty-state">Indlæser historik fra InfluxDB...</div>`;
    }

    const { days, users, series } = this._history;
    const m = this._histMetric;

    const metricBtns = [
      ["time",   "⏱️ Tid"],
      ["energy", "⚡ Energi"],
      ["cost",   "💰 Pris"],
    ].map(([id, label]) =>
      `<button class="metric-btn${m===id?" active":""}" data-metric="${id}">${label}</button>`
    ).join("");

    return `
      <div class="hist-toolbar">
        <div class="metric-selector">${metricBtns}</div>
        <button class="reload-hist-btn">🔄 Opdater</button>
      </div>

      <div class="section-title">Daglig fordeling — seneste 30 dage</div>
      <div class="bar-chart-wrap">
        ${this._barChartSVG(days, users, series, m)}
      </div>

      <div class="section-title">Seneste 7 dage</div>
      ${this._weekSummaryHTML(days, users, series, m)}
    `;
  }

  // ── Bar chart SVG ─────────────────────────────────────────────
  _barChartSVG(days, users, series, metric) {
    if (!days.length) return `<div class="empty-state small">Ingen historik data endnu</div>`;

    const COLORS = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6"];
    const W = 680, H = 200, PAD_L = 48, PAD_R = 12, PAD_T = 12, PAD_B = 36;
    const chartW = W - PAD_L - PAD_R;
    const chartH = H - PAD_T - PAD_B;

    const showDays = days.slice(-30);
    const barGroupW = chartW / showDays.length;
    const barW = Math.max(Math.min(barGroupW / users.length - 2, 18), 3);

    let maxVal = 0;
    for (const day of showDays) {
      for (const u of users) {
        const v = series[u]?.[day]?.[metric] || 0;
        if (v > maxVal) maxVal = v;
      }
    }
    if (maxVal === 0) return `<div class="empty-state small">Ingen data for valgt periode</div>`;

    const scale = v => chartH - (v / maxVal) * chartH;
    const fmtY  = v => {
      if (metric === "time")   return v >= 3600 ? (v/3600).toFixed(1)+"t" : Math.round(v/60)+"m";
      if (metric === "energy") return v.toFixed(2)+"kWh";
      return v.toFixed(1)+"kr";
    };

    const yLabels = [0,.25,.5,.75,1].map(f => {
      const val = f * maxVal;
      const y   = PAD_T + scale(val);
      return `<text x="${PAD_L - 4}" y="${y + 4}" text-anchor="end" font-size="9" fill="var(--secondary-text-color)">${fmtY(val)}</text>
              <line x1="${PAD_L}" y1="${y}" x2="${W - PAD_R}" y2="${y}" stroke="var(--divider)" stroke-width="1"/>`;
    }).join("");

    const bars = showDays.map((day, di) => {
      const groupX = PAD_L + di * barGroupW;
      const dayBars = users.map((u, ui) => {
        const val  = series[u]?.[day]?.[metric] || 0;
        const barH = (val / maxVal) * chartH;
        const x    = groupX + (barGroupW - users.length * (barW + 2)) / 2 + ui * (barW + 2);
        const y    = PAD_T + chartH - barH;
        const col  = COLORS[ui % COLORS.length];
        return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW}" height="${barH.toFixed(1)}"
                  fill="${col}" rx="2" opacity="0.85">
                  <title>${u}: ${fmtY(val)}</title>
                </rect>`;
      }).join("");

      const step   = showDays.length > 20 ? 5 : showDays.length > 10 ? 3 : 1;
      const xLabel = di % step === 0
        ? `<text x="${(groupX + barGroupW/2).toFixed(1)}" y="${H - 4}"
             text-anchor="middle" font-size="9" fill="var(--secondary-text-color)">${day.slice(5)}</text>`
        : "";

      return dayBars + xLabel;
    }).join("");

    const legend = users.map((u,i) =>
      `<div class="legend-row"><span class="legend-dot" style="background:${COLORS[i%COLORS.length]}"></span><span class="legend-name">${u}</span></div>`
    ).join("");

    return `
      <svg viewBox="0 0 ${W} ${H}" class="bar-chart-svg" preserveAspectRatio="xMidYMid meet">
        ${yLabels}
        ${bars}
      </svg>
      <div class="donut-legend bar-legend">${legend}</div>`;
  }

  // ── Week summary table ─────────────────────────────────────────
  _weekSummaryHTML(days, users, series, metric) {
    const last7 = days.slice(-7);
    if (!last7.length) return "";

    const fmtV = (v) => {
      if (metric === "time")   return this._fmtTime(v);
      if (metric === "energy") return this._fmtEnergy(v);
      return this._fmtCost(v);
    };

    const COLORS = ["#6366f1","#f59e0b","#10b981","#ef4444","#8b5cf6"];

    const totals = users.map((u,i) => {
      const tot = last7.reduce((acc, d) => acc + (series[u]?.[d]?.[metric]||0), 0);
      return `
        <div class="week-user-card">
          <div class="avatar" style="background:${COLORS[i%COLORS.length]}">${u[0].toUpperCase()}</div>
          <div class="week-user-info">
            <div class="week-user-name">${u}</div>
            <div class="week-user-val">${fmtV(tot)}</div>
          </div>
        </div>`;
    }).join("");

    const dayFmt = d => {
      const dt = new Date(d+"T12:00:00Z");
      return dt.toLocaleDateString("da-DK", { weekday:"short", day:"numeric", month:"numeric" });
    };

    const rows = last7.map(d => {
      const cells = users.map((u,i) => {
        const v = series[u]?.[d]?.[metric]||0;
        const barPct = Math.round((v / (Math.max(...users.map(u2 => series[u2]?.[d]?.[metric]||0))||1)) * 100);
        return `<td>
          <div class="day-bar-bg"><div class="day-bar-fill" style="width:${barPct}%;background:${COLORS[i%COLORS.length]}"></div></div>
          <div class="day-val">${fmtV(v)}</div>
        </td>`;
      }).join("");
      return `<tr><td class="day-label">${dayFmt(d)}</td>${cells}</tr>`;
    }).join("");

    const headers = users.map(u => `<th>${u}</th>`).join("");

    return `
      <div class="week-cards">${totals}</div>
      <table class="day-table">
        <thead><tr><th>Dag</th>${headers}</tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ── Config tab HTML ───────────────────────────────────────────
  _configHTML() {
    if (!this._config) return '<div class="empty-state">Indlæser konfiguration...</div>';
    const cfg = this._config;

    const rawMappings = cfg.user_mappings || {};
    const mappings = Object.entries(rawMappings).map(([k, v]) => ({
      sensorState: k,
      userId:  typeof v === "object" ? (v.user_id || "") : (v || ""),
      haUser:  typeof v === "object" ? (v.ha_user  || "") : "",
    }));
    while (mappings.length < 3) mappings.push({ sensorState: "", userId: "", haUser: "" });

    const haUserOptions = [
      `<option value="">— Vælg HA-bruger (valgfri) —</option>`,
      ...this._haUsers.map(u =>
        `<option value="${this._esc(u.id)}">{NAME}</option>`.replace("{NAME}", this._esc(u.name))
      ),
    ].join("");

    const mappingRows = mappings.map(({ sensorState, userId, haUser }, i) => {
      const opts = haUserOptions.replace(
        `value="${this._esc(haUser)}"`,
        `value="${this._esc(haUser)}" selected`
      );
      return `
      <div class="user-mapping-row">
        <div class="mapping-col">
          <label class="cfg-label">Sensor-tilstand</label>
          <input class="cfg-sensor-state cfg-input" type="text"
            value="${this._esc(sensorState)}" placeholder="f.eks. konge">
        </div>
        <div class="mapping-arrow">→</div>
        <div class="mapping-col">
          <label class="cfg-label">Bruger-ID</label>
          <input class="cfg-user-id cfg-input" type="text"
            value="${this._esc(userId)}" placeholder="f.eks. flemming">
        </div>
        <div class="mapping-arrow">→</div>
        <div class="mapping-col">
          <label class="cfg-label">HA Mobil-bruger <span class="cfg-optional">(valgfri)</span></label>
          <div class="select-wrap">
            <select class="cfg-ha-user cfg-input cfg-select" data-idx="${i}">
              ${opts}
            </select>
            <span class="select-caret">▾</span>
          </div>
        </div>
        <button class="remove-row-btn" data-idx="${i}">✕</button>
      </div>`;
    }).join("");

    const statusBanner = this._configState === "saved"
      ? '<div class="cfg-banner success">✅ Gemt! Home Assistant genindlæser integrationen...</div>'
      : this._configState === "error"
      ? '<div class="cfg-banner error">❌ Fejl ved gemning. Tjek HA-loggen.</div>'
      : "";

    return `
      ${statusBanner}

      <div class="section-title">🔌 Sensor Entity IDs</div>
      <div class="cfg-hint">Disse entity IDs skal matche dine HA sensorer. Find dem under <strong>Indstillinger → Enheder & tjenester</strong>.</div>
      <div class="cfg-grid">
        <div class="cfg-field">
          <label class="cfg-label">👤 Bruger-sensor</label>
          <input class="cfg-user-entity cfg-input" type="text"
            value="${this._esc(cfg.user_entity || '')}"
            placeholder="sensor.din_bruger_sensor">
          <span class="cfg-hint-small">Sensor der viser hvem der er logget ind (f.eks. "konge", "lukas")</span>
        </div>
        <div class="cfg-field">
          <label class="cfg-label">⚡ Watt-sensor</label>
          <input class="cfg-watt-entity cfg-input" type="text"
            value="${this._esc(cfg.watt_entity || '')}"
            placeholder="sensor.pc_strømforbrug">
          <span class="cfg-hint-small">PC'ens samlede strømforbrug i watt</span>
        </div>
        <div class="cfg-field">
          <label class="cfg-label">🔌 Måler-sensor</label>
          <input class="cfg-device-power-entity cfg-input" type="text"
            value="${this._esc(cfg.device_power_entity || '')}"
            placeholder="sensor.maaler_forbrug">
          <span class="cfg-hint-small">Målerens eget forbrug (trækkes fra watt-sensoren)</span>
        </div>
        <div class="cfg-field">
          <label class="cfg-label">💰 Pris-sensor</label>
          <input class="cfg-price-entity cfg-input" type="text"
            value="${this._esc(cfg.price_entity || '')}"
            placeholder="sensor.energi_pris">
          <span class="cfg-hint-small">Aktuel elpris i kr/kWh</span>
        </div>
      </div>

      <div class="section-title" style="margin-top:24px">📊 Live Gauge-sensorer <span style="font-size:11px;font-weight:400;opacity:.6">(valgfri)</span></div>
      <div class="cfg-hint">Vises som runde gauges i Live Session-sektionen. Kun synlige hvis konfigureret. Brug f.eks. CPU%, GPU%, temperatur, volt, amps.</div>
      ${[
        { n:1, icon:"🔵", placeholder:"sensor.flemming_gamer_satellite_cpuload",      ex:"cpu"  },
        { n:2, icon:"🟠", placeholder:"sensor.flemming_gamer_satellite_gpuload",      ex:"gpu"  },
        { n:3, icon:"🟢", placeholder:"sensor.flemming_gamer_satellite_memoryusage",  ex:"ram"  },
        { n:4, icon:"🟣", placeholder:"sensor.flemming_gamer_satellite_gputemperature", ex:"gpu °C" },
        { n:5, icon:"🔵", placeholder:"sensor.flemmings_gamer_pc_currentclockspeed", ex:"mhz"  },
      ].map(({ n, icon, placeholder, ex }) => `
      <div class="cfg-grid" style="margin-top:${n===1?'0':'8px'}">
        <div class="cfg-field">
          <label class="cfg-label">${icon} Gauge ${n} — Sensor</label>
          <input class="cfg-gauge${n}-entity cfg-input" type="text"
            value="${this._esc(cfg[`gauge${n}_entity`] || '')}"
            placeholder="${placeholder}">
          <span class="cfg-hint-small">Efterlad tom for at skjule gauge ${n}</span>
        </div>
        <div class="cfg-field">
          <label class="cfg-label">${icon} Gauge ${n} — Etiket</label>
          <input class="cfg-gauge${n}-label cfg-input" type="text"
            value="${this._esc(cfg[`gauge${n}_label`] || '')}"
            placeholder="${ex}">
          <span class="cfg-hint-small">Tekst vist i midten (f.eks. "${ex}")</span>
        </div>
      </div>`).join("")}

      <div class="section-title-row" style="margin-top:24px">
        <span class="section-title" style="margin:0">👥 Bruger-mappings</span>
        <button class="add-btn add-mapping-btn">+ Tilføj bruger</button>
      </div>
      <div class="cfg-hint" style="margin-bottom:12px">
        Sensor-tilstand er den tekst din bruger-sensor returnerer. Bruger-ID er det navn du bruger i statistikken.
      </div>
      <div class="user-mappings-list">
        ${mappingRows}
      </div>

      <div class="section-title" style="margin-top:24px">🗂️ Tab-rækkefølge</div>
      <div class="cfg-hint">Træk og slip tabs for at ændre rækkefølgen. Ændringen gemmes straks.</div>
      <div class="tab-sorter" id="tab-sorter">
        ${this._orderedTabs().map((t, i) => `
          <div class="tab-sort-item" draggable="true" data-idx="${i}" data-id="${t.id}">
            <span class="drag-handle">⠿</span>
            <span class="tab-sort-icon">${t.icon}</span>
            <span class="tab-sort-label">${t.label}</span>
          </div>`).join("")}
      </div>
      <button class="reset-tabs-btn">↺ Nulstil rækkefølge</button>

      <div class="section-title" style="margin-top:24px">💾 Gem konfiguration</div>
      <div class="cfg-save-row">
        <button class="cfg-save-btn save-btn" ${this._configSaving ? "disabled" : ""}>
          ${this._configSaving ? "💾 Gemmer og genindlæser..." : "💾 Gem konfiguration"}
        </button>
        <button class="cfg-cancel-btn cancel-btn" ${this._configSaving ? "disabled" : ""}>
          Annuller
        </button>
      </div>

      <div class="cfg-info-box">
        <div class="cfg-info-title">ℹ️ Hvad sker der når du gemmer?</div>
        <div class="cfg-info-body">
          Home Assistant opdaterer konfigurationen og genindlæser integrationen automatisk.
          Dine historiske data i InfluxDB påvirkes ikke.
          Sensorer vil kortvarigt vise "Utilgængelig" mens integrationen genstartes.
        </div>
      </div>`;
  }

  // ── Admin tab HTML ────────────────────────────────────────────
  _adminHTML() {
    const sys = this._system;
    if (!sys) return `<div class="empty-state">Indlæser...</div>`;

    // ── Write buffer ───────────────────────────────────────────
    const bufPct   = Math.round(sys.buffer_size / sys.buffer_max * 100);
    const bufColor = bufPct > 75 ? "#ef4444" : bufPct > 40 ? "#f59e0b" : "#10b981";

    // ── System health indicators ───────────────────────────────
    const monthlyOk = sys.monthly_loaded === true;
    const bufOk     = sys.buffer_size === 0;
    const writeOk   = sys.last_write && sys.last_write !== "aldrig";

    // Overall health: all green = ok, any red = warning
    const allOk = monthlyOk && bufOk;
    const healthColor  = allOk ? "#10b981" : "#f59e0b";
    const healthIcon   = allOk ? "✅" : "⚠️";
    const healthLabel  = allOk ? "Alt OK" : "Kræver opmærksomhed";

    const healthRows = [
      {
        icon: monthlyOk ? "✅" : "⏳",
        label: "Monthly data",
        value: monthlyOk ? "Indlæst" : "Afventer InfluxDB…",
        ok: monthlyOk,
      },
      {
        icon: bufOk ? "✅" : "⚠️",
        label: "Write buffer",
        value: bufOk ? "Tom" : `${sys.buffer_size} punkter venter`,
        ok: bufOk,
      },
      {
        icon: writeOk ? "✅" : "⏳",
        label: "Seneste write",
        value: sys.last_write || "aldrig",
        ok: writeOk,
      },
      {
        icon: "👤",
        label: "Aktiv bruger",
        value: sys.current_user ? sys.current_user.charAt(0).toUpperCase() + sys.current_user.slice(1) : "Ingen",
        ok: true,
      },
    ].map(r => `
      <div class="health-row">
        <span class="health-icon">${r.icon}</span>
        <span class="health-label">${r.label}</span>
        <span class="health-value" style="color:${r.ok ? "var(--text)" : "#f59e0b"}">${this._esc(r.value)}</span>
      </div>`).join("");

    // ── Info cards ─────────────────────────────────────────────
    const cards = [
      ["Version",      sys.version],
      ["InfluxDB host", `${sys.influxdb_host}:${sys.influxdb_port}`],
      ["Database",     sys.influxdb_database],
      ["Brugere",      (sys.tracked_users || []).join(", ")],
    ].map(([l, v]) => `
      <div class="admin-card">
        <div class="admin-card-label">${l}</div>
        <div class="admin-card-value">${this._esc(v)}</div>
      </div>`).join("");

    const mapRows = Object.entries(sys.user_map || {}).map(([k, v]) => `
      <div class="mapping-row"><code>${this._esc(k)}</code><span>${this._esc(v)}</span></div>`).join("");

    return `
      <div class="section-title">
        System Health
        <span class="health-badge" style="background:${healthColor}22;color:${healthColor};border:1px solid ${healthColor}44">
          ${healthIcon} ${healthLabel}
        </span>
      </div>
      <div class="health-card">
        ${healthRows}
      </div>

      <div class="section-title">System info</div>
      <div class="admin-grid">${cards}</div>

      <div class="section-title">Write Buffer</div>
      <div class="buffer-card">
        <div class="buffer-header">
          <span>Bufferede writes</span>
          <span style="color:${bufColor};font-weight:600">${sys.buffer_size} / ${sys.buffer_max}</span>
        </div>
        <div class="buffer-bar-bg"><div class="buffer-bar-fill" style="width:${bufPct}%;background:${bufColor}"></div></div>
        <div class="buffer-hint">${sys.buffer_size === 0
          ? `<span style="color:#10b981">✅ Ingen fejlede writes</span>`
          : `<span style="color:#f59e0b">⚠️ ${sys.buffer_size} punkter venter</span>`}</div>
      </div>

      <div class="section-title">Bruger mappings</div>
      <div class="mapping-table">
        <div class="mapping-header"><span>Sensor tilstand</span><span>Bruger ID</span></div>
        ${mapRows}
      </div>
      <div class="admin-hint">Rediger under <strong>Indstillinger → Enheder & tjenester → PC User Statistics → Konfigurer</strong></div>`;
  }

  // ── Main render ───────────────────────────────────────────────
  _render() {
    // Don't rebuild the config tab DOM while the user is typing in an input/select —
    // it would destroy focus and discard unsaved keystrokes.
    // Exception: _forceRender is set when the user explicitly triggers a save/action.
    if (this._tab === "config" && !this._forceRender) {
      const active = this.shadowRoot?.activeElement;
      if (active && (active.tagName === "INPUT" || active.tagName === "SELECT" || active.tagName === "TEXTAREA")) {
        return;
      }
    }
    this._forceRender = false;

    let content = "";
    if      (this._tab==="live")          content = this._liveHTML();
    else if (this._tab==="statistik")     content = this._statistikHTML();
    else if (this._tab==="notifications") content = this._notificationsHTML();
    else if (this._tab==="history")       content = this._historyHTML();
    else if (this._tab==="config")        content = this._configHTML();
    else if (this._tab==="admin")         content = this._adminHTML();

    this.shadowRoot.innerHTML = `
      <style>${this._css()}</style>
      <div class="panel">
        ${this._headerHTML()}
        <div class="tabs">${this._tabsHTML()}</div>
        <div class="tab-content">${content}</div>
      </div>`;

    this._bind();
  }

  // ── Event delegation ──────────────────────────────────────────
  _bind() {
    const root = this.shadowRoot;

    // Tabs
    root.querySelectorAll(".tab").forEach(el => {
      el.addEventListener("click", () => {
        this._tab = el.dataset.tab;
        this._render();
        if (el.dataset.tab === "history" && !this._history) this._loadHistory();
        if (el.dataset.tab === "config"  && !this._config)  this._loadConfig();
        if (el.dataset.tab === "config"  && !this._haUsers.length) this._loadHaUsers();
      });
    });

    // Refresh
    root.querySelector(".refresh-btn")?.addEventListener("click", () => this._load());

    // Hamburger
    root.querySelector(".menu-btn")?.addEventListener("click", () => {
      this.dispatchEvent(new Event("hass-toggle-menu",{bubbles:true,composed:true}));
    });

    if (this._tab === "config" && this._config) {
      root.querySelector(".cfg-save-btn")?.addEventListener("click", () => this._saveConfig());
      root.querySelector(".cfg-cancel-btn")?.addEventListener("click", () => {
        this._config = null; this._configState = null; this._loadConfig();
      });

      const sorter = root.querySelector("#tab-sorter");
      if (sorter) {
        let dragIdx = null;
        sorter.querySelectorAll(".tab-sort-item").forEach(el => {
          el.addEventListener("dragstart", e => {
            dragIdx = parseInt(el.dataset.idx);
            el.classList.add("dragging");
            e.dataTransfer.effectAllowed = "move";
          });
          el.addEventListener("dragend", () => {
            el.classList.remove("dragging");
            sorter.querySelectorAll(".tab-sort-item").forEach(x => x.classList.remove("drag-over"));
          });
          el.addEventListener("dragover", e => {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            sorter.querySelectorAll(".tab-sort-item").forEach(x => x.classList.remove("drag-over"));
            el.classList.add("drag-over");
          });
          el.addEventListener("drop", e => {
            e.preventDefault();
            const targetIdx = parseInt(el.dataset.idx);
            if (dragIdx === null || dragIdx === targetIdx) return;
            const newOrder = [...this._tabOrder];
            const [moved]  = newOrder.splice(dragIdx, 1);
            newOrder.splice(targetIdx, 0, moved);
            this._saveTabOrder(newOrder);
            this._render();
          });
        });
      }

      root.querySelector(".reset-tabs-btn")?.addEventListener("click", () => {
        this._saveTabOrder(PcUserStatisticsPanel.ALL_TABS.map(t => t.id));
        this._render();
      });

      root.querySelector(".add-mapping-btn")?.addEventListener("click", () => {
        const updated = { ...this._config.user_mappings };
        updated[""] = { user_id: "", ha_user: "" };
        this._config = { ...this._config, user_mappings: updated };
        this._render();
      });
      root.querySelectorAll(".remove-row-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          const idx     = parseInt(btn.dataset.idx);
          const entries = Object.entries(this._config.user_mappings || {});
          entries.splice(idx, 1);
          this._config = { ...this._config, user_mappings: Object.fromEntries(entries) };
          this._render();
        });
      });
    }

    if (this._tab === "history") {
      root.querySelectorAll(".metric-btn").forEach(el => {
        el.addEventListener("click", () => { this._histMetric = el.dataset.metric; this._render(); });
      });
      root.querySelector(".reload-hist-btn")?.addEventListener("click", () => {
        this._history = null; this._render(); this._loadHistory();
      });
    }

    if (this._tab === "notifications" && this._notif) {
      root.querySelectorAll(".dev-check").forEach(el => {
        el.addEventListener("change", () => {
          const devs = [...root.querySelectorAll(".dev-check")]
            .filter(c=>c.checked).map(c=>c.value);
          this._saveDevices(devs);
        });
      });

      root.querySelectorAll(".rule-toggle").forEach(el => {
        el.addEventListener("change", () => this._toggleRule(el.dataset.rule));
      });

      root.querySelectorAll(".edit-btn").forEach(el => {
        el.addEventListener("click", () => {
          const id = el.dataset.rule;
          if (this._editingRule === id) {
            this._editingRule = null;
          } else {
            this._editingRule = id;
            this._newRule = { ...this._notif.rules[id], id };
          }
          this._render();
        });
      });

      root.querySelectorAll(".test-btn").forEach(el => {
        el.addEventListener("click", () => this._testRule(el.dataset.rule));
      });

      root.querySelectorAll(".del-btn").forEach(el => {
        el.addEventListener("click", () => this._deleteRule(el.dataset.rule));
      });

      root.querySelector(".save-edit-btn")?.addEventListener("click", () => {
        const r = this._collectForm("edit-form");
        if (r) this._saveRule(this._editingRule, { ...this._notif.rules[this._editingRule], ...r });
      });
      root.querySelector(".cancel-edit-btn")?.addEventListener("click", () => {
        this._editingRule = null; this._render();
      });

      root.querySelector(".show-create-btn")?.addEventListener("click", () => {
        this._showCreate = !this._showCreate;
        this._editingRule = null;
        this._render();
      });
      root.querySelector(".save-new-btn")?.addEventListener("click", () => {
        const r = this._collectForm("create-form");
        if (!r) return;
        const id = `custom_${Date.now()}`;
        this._saveRule(id, { ...r, id, enabled:false, is_custom:true });
      });
      root.querySelector(".cancel-new-btn")?.addEventListener("click", () => {
        this._showCreate = false; this._newRule = this._emptyRule(); this._render();
      });
    }
  }

  _collectForm(formClass) {
    const root = this.shadowRoot;
    const f = root.querySelector(`.${formClass}`);
    if (!f) return null;
    const name = f.querySelector(".f-name")?.value?.trim();
    if (!name) { alert("Giv reglen et navn"); return null; }
    const targets = [...f.querySelectorAll(".f-user:checked")].map(el=>el.value);
    return {
      name,
      icon:             f.querySelector(".f-icon")?.value || "🔔",
      trigger_type:     f.querySelector(".f-ttype")?.value || "session_minutes",
      trigger_value:    parseFloat(f.querySelector(".f-tval")?.value) || 60,
      title:            f.querySelector(".f-title")?.value || "",
      message:          f.querySelector(".f-msg")?.value || "",
      repeat:           f.querySelector(".f-repeat")?.checked || false,
      repeat_interval:  parseFloat(f.querySelector(".f-interval")?.value) || 60,
      user_targets:     targets,
    };
  }

  // ── CSS ───────────────────────────────────────────────────────
  _css() {
    return `
    :host {
      display: block;
      --accent:   var(--primary-color, #6366f1);
      --text:     var(--primary-text-color, #1f2937);
      --subtext:  var(--secondary-text-color, #6b7280);
      --card:     var(--card-background-color, #ffffff);
      --card2:    var(--secondary-background-color, #f3f4f6);
      --divider:  var(--divider-color, #e5e7eb);
      font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
      font-size: 14px;
      color: var(--text);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }

    /* ── Panel layout ── */
    .panel { display:flex; flex-direction:column; height:100%; min-height:0; }
    .tab-content { flex:1; overflow-y:auto; padding:16px; }

    /* ── Header ── */
    .header { display:flex; align-items:center; justify-content:space-between;
      padding:14px 16px; background:var(--card2); border-bottom:1px solid var(--divider);
      gap:12px; transition:background .3s; }
    .header-live { background:linear-gradient(135deg,#6366f1 0%,#8b5cf6 100%); color:white; }
    .header-live .title, .header-live .subtitle { color:white; }
    .header-live .subtext { color:rgba(255,255,255,0.8); }
    .header-left { display:flex; align-items:center; gap:10px; flex:1; min-width:0; }
    .header-right { display:flex; align-items:center; gap:8px; flex-shrink:0; }
    .header-title { display:flex; align-items:center; gap:10px; min-width:0; }
    .title    { font-size:16px; font-weight:700; white-space:nowrap; }
    .subtitle { font-size:12px; color:var(--subtext); display:flex; align-items:center; gap:5px; }
    .header-live .subtitle { color:rgba(255,255,255,0.85); }

    /* ── Live dot ── */
    .live-dot { display:inline-block; width:7px; height:7px; border-radius:50%;
      background:#4ade80; box-shadow:0 0 6px #4ade80; animation:blink 1.4s infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

    /* ── Pulse ring ── */
    .pulse-ring-wrap { position:relative; display:inline-flex; align-items:center; justify-content:center; }
    .pulse-ring { position:absolute; width:36px; height:36px; border-radius:50%;
      border:2px solid rgba(255,255,255,0.5); animation:sonar 2s ease-out infinite; }
    .pulse-ring-2 { animation-delay:1s; }
    @keyframes sonar { 0%{transform:scale(1);opacity:0.8} 100%{transform:scale(2.2);opacity:0} }
    .icon { font-size:24px; position:relative; z-index:1; }

    /* ── Watt gauge ── */
    .watt-gauge { display:flex; flex-direction:column; align-items:center; position:relative; }
    .gauge-svg { width:68px; height:40px; }
    .watt-center { position:absolute; bottom:0; left:50%; transform:translateX(-50%); text-align:center; }
    .watt-value { font-size:11px; font-weight:700; color:white; white-space:nowrap; }

    /* ── Buttons ── */
    .refresh-btn, .menu-btn { background:rgba(255,255,255,0.15); border:none; border-radius:8px;
      width:36px; height:36px; cursor:pointer; display:flex; align-items:center; justify-content:center;
      color:white; transition:background .15s; }
    .refresh-btn:hover, .menu-btn:hover { background:rgba(255,255,255,0.25); }
    .refresh-btn svg, .menu-btn svg { width:20px; height:20px; fill:currentColor; }
    .header:not(.header-live) .refresh-btn, .header:not(.header-live) .menu-btn {
      background:var(--card); color:var(--subtext); border:1px solid var(--divider); }

    .save-btn { padding:10px 20px; background:var(--accent); color:white;
      border:none; border-radius:10px; font-size:14px; font-weight:600; cursor:pointer;
      transition:opacity .15s; }
    .save-btn:hover { opacity:.88; }
    .save-btn:disabled { opacity:.5; cursor:not-allowed; }
    .cancel-btn { padding:10px 20px; background:transparent; color:var(--subtext);
      border:1px solid var(--divider); border-radius:10px; font-size:14px; cursor:pointer; }
    .add-btn { padding:6px 14px; background:var(--accent); color:white;
      border:none; border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; }

    /* ── Tabs ── */
    .tabs { display:flex; overflow-x:auto; border-bottom:1px solid var(--divider);
      background:var(--card); scrollbar-width:none; justify-content:center; }
    .tabs::-webkit-scrollbar { display:none; }
    .tab { display:flex; flex-direction:column; align-items:center; gap:5px;
      padding:14px 20px; border:none; background:transparent; cursor:pointer;
      color:var(--subtext); font-size:11px; border-bottom:2px solid transparent;
      transition:color .15s, border-color .15s; white-space:nowrap; flex-shrink:0; }
    .tab:hover { color:var(--accent); }
    .tab.active { color:var(--accent); border-bottom-color:var(--accent); font-weight:600; }
    .tab-icon { font-size:30px; }
    .tab-label { font-size:10px; }
    @media (max-width:600px) { .tab-label { display:none; } .tab { padding:12px 14px; } }

    /* ── Section titles ── */
    .section-title { font-size:11px; font-weight:700; text-transform:uppercase;
      letter-spacing:.8px; color:var(--subtext); margin:20px 0 10px; }
    .section-title:first-child { margin-top:0; }
    .section-title-row { display:flex; align-items:center; justify-content:space-between; margin:20px 0 10px; }

    /* ── Avatar ── */
    .avatar { width:36px; height:36px; border-radius:50%; display:flex; align-items:center;
      justify-content:center; font-weight:700; font-size:15px; color:white; flex-shrink:0; }
    .avatar.large { width:48px; height:48px; font-size:20px; }

    /* ── Stat grid ── */
    /* ── Live card ── */
    .live-card {
      display:flex; align-items:center; gap:0;
      background:var(--card2); border-radius:16px;
      padding:16px 20px; flex-wrap:wrap;
    }
    .live-left {
      display:flex; flex-direction:column; gap:14px;
      min-width:140px; flex-shrink:0;
      border-right:1px solid rgba(255,255,255,0.07); padding-right:20px; margin-right:4px;
    }
    .live-stat { display:flex; align-items:center; gap:10px; }
    .live-stat.active .live-stat-val { color:var(--accent); }
    .live-stat-icon { font-size:18px; width:24px; text-align:center; }
    .live-stat-val  { font-size:16px; font-weight:700; white-space:nowrap; }
    .live-stat-lbl  { font-size:10px; color:var(--subtext); white-space:nowrap; }
    .live-bars {
      display:flex; gap:8px; align-items:flex-end;
      flex:1; padding:0 8px; height:100px; min-width:0;
    }
    .bar-col {
      display:flex; flex-direction:column; align-items:center;
      gap:3px; flex:1; height:100%;
    }
    .bar-val   { font-size:11px; font-weight:700; white-space:nowrap; min-height:14px; line-height:1; }
    .bar-track {
      flex:1; width:100%; background:rgba(255,255,255,0.08);
      border-radius:5px; overflow:hidden;
      display:flex; flex-direction:column; justify-content:flex-end;
    }
    .bar-fill  { width:100%; border-radius:5px; transition:height .5s cubic-bezier(.4,0,.2,1); min-height:3px; }
    .bar-label { font-size:9px; color:var(--subtext); text-transform:uppercase; letter-spacing:.4px; white-space:nowrap; }
    .live-right {
      flex-shrink:0; margin-left:auto;
      border-left:1px solid rgba(255,255,255,0.07); padding-left:20px;
    }

    /* ── Monthly / Statistik tab ── */
    .statistik-layout { display:flex; gap:24px; align-items:flex-start; flex-wrap:wrap; }
    .statistik-left   { flex:1; min-width:0; }
    .statistik-right  { flex-shrink:0; width:220px; }
    .user-monthly-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; }
    .user-month-card { background:var(--card2); border-radius:12px; padding:16px; }
    .user-month-header { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
    .user-month-name { font-weight:600; text-transform:capitalize; }
    .user-month-stats { display:flex; flex-direction:column; gap:8px; }
    .user-stat { display:flex; justify-content:space-between; font-size:13px; }
    .user-stat-label { color:var(--subtext); }
    .user-stat-value { font-weight:600; }

    /* ── Donut ── */
    .donut-container { width:160px; display:flex; flex-direction:column; align-items:center; gap:10px; position:relative; }
    .donut-ring { position:relative; }
    .donut-svg { width:140px; height:140px; display:block; }
    .donut-center { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); text-align:center; width:80px; }
    .donut-top-user { font-size:12px; font-weight:700; text-transform:capitalize; }
    .donut-top-pct  { font-size:18px; font-weight:800; }
    .donut-center-label { font-size:11px; color:var(--subtext); }
    .donut-legend { display:flex; flex-direction:column; gap:6px; width:100%; }
    .legend-row { display:flex; align-items:center; gap:6px; font-size:12px; }
    .legend-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
    .legend-name { flex:1; text-transform:capitalize; }
    .legend-pct { color:var(--subtext); font-size:11px; }

    /* ── Leaderboard ── */
    .leaderboard { display:flex; flex-direction:column; gap:8px; }
    .lb-row { display:flex; align-items:center; gap:12px;
      background:var(--card2); border-radius:12px; padding:12px 16px;
      border:2px solid transparent; }
    .lb-first { border-color:color-mix(in srgb,#f59e0b 60%,transparent);
      background:color-mix(in srgb,#f59e0b 6%,var(--card2)); }
    .lb-rank { font-size:20px; text-align:center; }
    .lb-avatar { width:36px; height:36px; border-radius:50%; display:flex; align-items:center;
      justify-content:center; font-weight:700; font-size:15px; color:white; }
    .lb-info { flex:1; min-width:0; }
    .lb-name { font-size:13px; font-weight:600; text-transform:capitalize; margin-bottom:5px; color:var(--text); }
    .lb-bar-bg { height:6px; background:var(--divider); border-radius:3px; overflow:hidden; }
    .lb-bar-fill { height:100%; border-radius:3px; transition:width 0.6s cubic-bezier(.4,0,.2,1); }
    .lb-stats { text-align:right; }
    .lb-time { font-size:14px; font-weight:700; color:var(--text); }
    .lb-cost { font-size:11px; color:var(--subtext); margin-top:1px; }

    /* ── Users tab ── */
    .active-user-card { display:flex; align-items:center; gap:14px;
      background:color-mix(in srgb,var(--accent) 8%,var(--card2));
      border:2px solid var(--accent); border-radius:14px; padding:16px; margin-bottom:8px; }
    .active-user-info { flex:1; }
    .active-user-name { font-size:16px; font-weight:700; text-transform:capitalize; }
    .active-user-meta { font-size:12px; color:var(--subtext); margin-top:3px; }
    .live-badge { background:var(--accent); color:white; font-size:10px; font-weight:700;
      padding:3px 8px; border-radius:20px; letter-spacing:.5px; }
    .live-badge.small { font-size:9px; padding:2px 6px; }
    .offline-badge { font-size:11px; color:var(--subtext); }
    .users-list { display:flex; flex-direction:column; gap:8px; }
    .user-row { display:flex; align-items:center; gap:12px;
      background:var(--card2); border-radius:12px; padding:12px 16px; }
    .user-row.is-active { border:2px solid var(--accent); }
    .user-row-info { flex:1; }
    .user-row-name { font-weight:600; text-transform:capitalize; }
    .user-row-mapping { font-size:12px; color:var(--subtext); margin-top:2px; }

    /* ── Notifications ── */
    .device-section { display:flex; flex-direction:column; gap:6px; margin-bottom:8px; }
    .device-row { display:flex; align-items:center; gap:10px;
      background:var(--card2); border-radius:10px; padding:10px 14px; cursor:pointer; }
    .device-name { flex:1; font-weight:500; }
    .device-service { font-size:11px; color:var(--subtext); }
    .device-hint { margin-top:10px; font-size:12px; color:#10b981; }
    .device-hint.warn { color:#f59e0b; }
    .rules-list { display:flex; flex-direction:column; gap:10px; margin-bottom:8px; }
    .rule-card { background:var(--card2); border-radius:12px;
      padding:14px 16px; border:2px solid transparent; transition:border-color .2s; }
    .rule-card.active { border-color:var(--accent);
      background:color-mix(in srgb,var(--accent) 5%,var(--secondary-background-color,#f3f4f6)); }
    .rule-top { display:flex; align-items:center; gap:12px; }
    .rule-icon { font-size:22px; flex-shrink:0; }
    .rule-info { flex:1; }
    .rule-name { font-weight:600; font-size:14px; }
    .rule-trigger { font-size:12px; color:var(--subtext); margin-top:2px; }
    .rule-preview { margin-top:12px; padding:10px 12px; background:var(--card);
      border-radius:8px; border-left:3px solid var(--accent); }
    .rule-msg-title { font-size:13px; font-weight:600; }
    .rule-msg-body  { font-size:12px; color:var(--subtext); margin-top:3px; }
    .rule-meta { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
    .badge { font-size:11px; padding:3px 8px; border-radius:20px;
      background:var(--divider); color:var(--subtext); }
    .badge.repeat { background:color-mix(in srgb,#6366f1 15%,transparent); color:#6366f1; }
    .badge.once   { background:color-mix(in srgb,#10b981 15%,transparent); color:#10b981; }
    .badge.users  { background:color-mix(in srgb,#f59e0b 15%,transparent); color:#b45309; }
    .rule-actions { display:flex; gap:8px; margin-top:12px; }
    .test-btn { padding:6px 14px; border:none; border-radius:8px;
      background:var(--accent); color:white; font-size:12px; cursor:pointer; font-weight:600; }
    .test-btn:disabled { opacity:.5; cursor:not-allowed; }
    .edit-rule-btn { padding:6px 14px; border:1px solid var(--divider);
      border-radius:8px; background:transparent; color:var(--subtext); font-size:12px; font-weight:600; cursor:pointer; }
    .edit-rule-btn:hover { border-color:var(--accent); color:var(--accent); }
    .del-btn { padding:6px 14px; border:none; border-radius:8px;
      background:color-mix(in srgb,#ef4444 15%,transparent); color:#ef4444; font-size:12px; cursor:pointer; font-weight:600; }
    .inline-edit { margin-top:14px; padding-top:14px; border-top:1px solid var(--divider); }

    /* ── Toggle ── */
    .toggle { position:relative; display:inline-flex; align-items:center; cursor:pointer; flex-shrink:0; }
    .toggle input { opacity:0; width:0; height:0; position:absolute; }
    .toggle-slider { width:42px; height:24px; background:var(--divider); border-radius:12px;
      transition:background .2s; position:relative; }
    .toggle-slider::after { content:""; position:absolute; left:3px; top:3px;
      width:18px; height:18px; border-radius:50%; background:white;
      transition:transform .2s; box-shadow:0 1px 3px rgba(0,0,0,.2); }
    .toggle input:checked + .toggle-slider { background:var(--accent); }
    .toggle input:checked + .toggle-slider::after { transform:translateX(18px); }

    /* ── Notification form ── */
    .create-form, .edit-form, .create-form-inner { padding-top:12px; }
    .form-row { display:flex; align-items:center; gap:12px; margin-bottom:10px; }
    .form-row label { font-size:12px; font-weight:600; color:var(--subtext); min-width:100px; flex-shrink:0; }
    .form-row input[type=text], .form-row input[type=number], .form-row select {
      flex:1; padding:8px 10px; border:1px solid var(--divider); border-radius:8px;
      background:var(--card); color:var(--text); font-size:13px; }
    .form-row input:focus, .form-row select:focus { outline:none; border-color:var(--accent); }
    .user-checkboxes { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
    .user-check { display:flex; align-items:center; gap:4px; font-size:13px; cursor:pointer; }
    .form-hint { font-size:11px; color:var(--subtext); margin-left:4px; }
    .form-actions { display:flex; gap:8px; margin-top:14px; }

    /* ── Admin ── */
    .admin-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:10px; margin-bottom:4px; }
    .admin-card { background:var(--card2); border-radius:10px; padding:14px; }
    .admin-card-label { font-size:11px; color:var(--subtext); text-transform:uppercase; letter-spacing:.5px; margin-bottom:4px; }
    .admin-card-value { font-size:14px; font-weight:600; word-break:break-all; }
    .health-badge { display:inline-flex; align-items:center; gap:4px; font-size:11px; font-weight:600;
      padding:2px 8px; border-radius:20px; margin-left:8px; vertical-align:middle; }
    .health-card { background:var(--card2); border-radius:12px; overflow:hidden; margin-bottom:4px; }
    .health-row { display:grid; grid-template-columns:24px 1fr auto; align-items:center;
      gap:8px; padding:11px 14px; border-bottom:1px solid var(--divider); font-size:13px; }
    .health-row:last-child { border-bottom:none; }
    .health-icon { font-size:14px; text-align:center; }
    .health-label { color:var(--subtext); }
    .health-value { font-weight:600; text-align:right; }
    .buffer-card { background:var(--card2); border-radius:12px; padding:16px; margin-bottom:4px; }
    .buffer-header { display:flex; justify-content:space-between; font-size:14px; margin-bottom:10px; }
    .buffer-bar-bg { height:8px; background:var(--divider); border-radius:4px; overflow:hidden; }
    .buffer-bar-fill { height:100%; border-radius:4px; transition:width .4s ease; }
    .buffer-hint { font-size:12px; margin-top:8px; }
    .mapping-table { background:var(--card2); border-radius:12px; overflow:hidden; }
    .mapping-header { display:grid; grid-template-columns:1fr 1fr; padding:10px 14px;
      font-size:11px; font-weight:600; text-transform:uppercase; color:var(--subtext);
      border-bottom:1px solid var(--divider); }
    .mapping-row { display:grid; grid-template-columns:1fr 1fr; padding:10px 14px;
      font-size:13px; border-bottom:1px solid var(--divider); }
    .mapping-row:last-child { border-bottom:none; }
    .admin-hint { margin-top:20px; padding:12px 16px;
      background:color-mix(in srgb,var(--accent) 6%,var(--card-background-color,#fff));
      border-left:3px solid var(--accent); border-radius:0 8px 8px 0;
      font-size:13px; color:var(--subtext); line-height:1.5; }

    /* ── Tab sorter ── */
    .tab-sorter { display:flex; flex-direction:column; gap:6px; margin-bottom:12px; }
    .tab-sort-item { display:flex; align-items:center; gap:12px;
      background:var(--card2); border-radius:10px; padding:11px 14px; cursor:grab;
      border:2px solid transparent; transition:background .15s, border-color .15s, transform .15s, box-shadow .15s;
      user-select:none; }
    .tab-sort-item:hover { border-color:var(--accent); }
    .tab-sort-item.dragging { opacity:0.45; cursor:grabbing; transform:scale(1.02);
      box-shadow:0 8px 24px rgba(0,0,0,0.18); }
    .tab-sort-item.drag-over { border-color:var(--accent);
      background:color-mix(in srgb,var(--accent) 10%,var(--card2)); transform:translateY(-2px); }
    .drag-handle { font-size:18px; color:var(--subtext); cursor:grab; flex-shrink:0; }
    .tab-sort-icon  { font-size:20px; flex-shrink:0; }
    .tab-sort-label { font-size:14px; font-weight:500; color:var(--text); flex:1; }
    .reset-tabs-btn { padding:6px 14px; border:1px solid var(--divider); border-radius:8px;
      background:transparent; color:var(--subtext); font-size:12px; cursor:pointer; margin-bottom:4px; }
    .reset-tabs-btn:hover { border-color:var(--accent); color:var(--accent); }

    /* ── Config tab ── */
    .cfg-hint { font-size:12px; color:var(--subtext); margin-bottom:14px; line-height:1.5; }
    .cfg-hint-small { font-size:11px; color:var(--subtext); margin-top:3px; display:block; }
    .cfg-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:14px; }
    .cfg-field { display:flex; flex-direction:column; gap:4px; }
    .cfg-label { font-size:12px; font-weight:600; color:var(--subtext);
      text-transform:uppercase; letter-spacing:.5px; }
    .cfg-input { width:100%; padding:9px 12px;
      border:1px solid var(--divider); border-radius:8px;
      background:var(--card); color:var(--text); font-size:13px;
      transition:border-color .15s, box-shadow .15s; }
    .cfg-input:focus { outline:none; border-color:var(--accent);
      box-shadow:0 0 0 3px color-mix(in srgb,var(--accent) 15%,transparent); }
    .cfg-optional { font-size:10px; font-weight:400; color:var(--subtext); text-transform:none; letter-spacing:0; }
    .select-wrap { position:relative; }
    .select-caret { position:absolute; right:12px; top:50%; transform:translateY(-50%); pointer-events:none; color:var(--subtext); font-size:11px; }
    .cfg-select { appearance:none; -webkit-appearance:none; cursor:pointer; padding-right:28px; }
    .cfg-select option { background:var(--card2,#1e2029); color:var(--text,#e8eaf6); }
    .user-mappings-list { display:flex; flex-direction:column; gap:8px; margin-bottom:16px; }
    .user-mapping-row { display:flex; align-items:flex-end; gap:10px;
      background:var(--card2); border-radius:10px; padding:12px 14px; }
    .mapping-col { flex:1; display:flex; flex-direction:column; gap:4px; }
    .mapping-arrow { font-size:18px; color:var(--subtext); padding-bottom:8px; flex-shrink:0; }
    .remove-row-btn { padding:6px 10px; border:none; border-radius:6px;
      background:color-mix(in srgb,#ef4444 15%,transparent);
      color:#ef4444; cursor:pointer; font-size:13px; flex-shrink:0; align-self:flex-end; margin-bottom:1px; }
    .remove-row-btn:hover { background:color-mix(in srgb,#ef4444 25%,transparent); }
    .cfg-save-row { display:flex; gap:10px; margin:20px 0 16px; }
    .cfg-save-btn { min-width:220px; }
    .cfg-banner { padding:12px 16px; border-radius:10px; font-size:13px; font-weight:500; margin-bottom:16px; }
    .cfg-banner.success { background:color-mix(in srgb,#10b981 12%,var(--card));
      color:#059669; border:1px solid color-mix(in srgb,#10b981 30%,transparent); }
    .cfg-banner.error   { background:color-mix(in srgb,#ef4444 12%,var(--card));
      color:#dc2626; border:1px solid color-mix(in srgb,#ef4444 30%,transparent); }
    .cfg-info-box { background:color-mix(in srgb,var(--accent) 6%,var(--card));
      border:1px solid color-mix(in srgb,var(--accent) 20%,transparent);
      border-radius:10px; padding:14px 16px; }
    .cfg-info-title { font-size:13px; font-weight:600; margin-bottom:6px; color:var(--text); }
    .cfg-info-body  { font-size:12px; color:var(--subtext); line-height:1.6; }

    /* ── History tab ── */
    .hist-toolbar { display:flex; align-items:center; justify-content:space-between;
      margin-bottom:16px; flex-wrap:wrap; gap:10px; }
    .metric-selector { display:flex; gap:6px; }
    .metric-btn { padding:6px 14px; border:1px solid var(--divider); border-radius:20px;
      background:transparent; color:var(--subtext); font-size:13px; cursor:pointer; }
    .metric-btn.active { background:var(--accent); color:white;
      border-color:var(--accent); font-weight:600; }
    .reload-hist-btn { padding:6px 14px; border:1px solid var(--divider);
      border-radius:8px; background:transparent; color:var(--subtext); font-size:13px; cursor:pointer; }
    .bar-chart-wrap { background:var(--card2); border-radius:12px; padding:16px; overflow-x:auto; }
    .bar-chart-svg { width:100%; min-width:300px; height:auto; display:block; }
    .bar-legend { flex-direction:row; flex-wrap:wrap; gap:12px; margin-top:10px; }
    .week-cards { display:flex; gap:10px; flex-wrap:wrap; margin-bottom:14px; }
    .week-user-card { display:flex; align-items:center; gap:10px;
      background:var(--card2); border-radius:10px; padding:12px 14px; flex:1; min-width:120px; }
    .week-user-info { flex:1; }
    .week-user-name { font-size:12px; color:var(--subtext); text-transform:capitalize; }
    .week-user-val  { font-size:16px; font-weight:700; }
    .day-table { width:100%; border-collapse:collapse; font-size:13px; }
    .day-table th { text-align:left; padding:8px 10px; font-size:11px; font-weight:600;
      text-transform:uppercase; letter-spacing:.5px; color:var(--subtext);
      border-bottom:2px solid var(--divider); }
    .day-table td { padding:7px 10px; border-bottom:1px solid var(--divider-color,#f3f4f6); }
    .day-label { color:var(--subtext); white-space:nowrap; width:100px; }
    .day-bar-bg { height:6px; background:var(--divider); border-radius:3px; overflow:hidden; margin-bottom:3px; }
    .day-bar-fill { height:100%; border-radius:3px; }
    .day-val { font-size:12px; font-weight:600; }

    /* ── Misc ── */
    .empty-state { text-align:center; color:var(--subtext); padding:40px 20px; font-size:14px; }
    .empty-state.small { padding:16px; font-size:13px; }
  `; }
}

// ── FIX: Guard against double-registration on HA navigate/reload ──────────────
// Without this guard, HA re-executes the JS file on panel re-entry, causing:
// "Failed to execute 'define' on 'CustomElementRegistry': name already used"
if (!customElements.get("pc-user-statistics-panel")) {
  customElements.define("pc-user-statistics-panel", PcUserStatisticsPanel);
}
