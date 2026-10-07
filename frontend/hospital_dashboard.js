/**
 * LifeLine — Hospital Dashboard JS
 * Polls /api/hospital/dashboard every 10 seconds.
 * Shows live patient requests, driver assignments, ambulance statuses.
 */

const POLL_MS = 3000; // 10 seconds

const state = {
  ambulances:    [],
  requests:      [],
  active:        [],
  hospitals:     [],
  stats:         {},
  alerts:        [],
  trend:         [],
  statusSummary: {},
  map:           null,
  markers:       [],
};

let pollTimer = null;

/* ══════════════════════════════════════════════
   BOOT
══════════════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  initMap();
  fetchAll();
  pollTimer = setInterval(fetchAll, POLL_MS);
});

/* ══════════════════════════════════════════════
   FETCH
══════════════════════════════════════════════ */
async function fetchAll() {
  try {
    const res = await fetch('/api/hospital/dashboard');
    if (!res.ok) return;
    const d = await res.json();

    state.ambulances    = d.ambulances      || [];
    state.requests      = d.requests        || [];
    state.active        = d.active_requests || [];
    state.hospitals     = d.hospitals       || [];
    state.stats         = d.stats           || {};
    state.alerts        = d.alerts          || [];
    state.trend         = d.emergency_trend || [];
    state.statusSummary = d.status_summary  || {};

    renderKPIs();
    renderActiveRequests();
    renderAlerts();
    renderMap();
    renderTrend();
    renderDonut();
    renderAmbulanceTable();
    markUpdated();
  } catch(e) {
    console.error('dashboard fetch error', e);
  }
}

function markUpdated() {
  const el = document.getElementById('last-updated');
  if (el) el.textContent = 'Updated ' + new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit', second:'2-digit' });
  const cd = document.getElementById('cd-label');
  if (cd) cd.textContent = 'Live · auto-refresh every 10s';
}

/* ══════════════════════════════════════════════
   KPIs
══════════════════════════════════════════════ */
function renderKPIs() {
  const s = state.stats;
  set('total-ambulances',   s.total_ambulances    ?? '—');
  set('active-ambulances',  s.active_ambulances   ?? '—');
  set('emergency-requests', s.emergency_requests  ?? '—');
  const rt = s.average_response_time || 0;
  set('response-time', rt ? Math.round(rt) + ' min' : '—');
}

function set(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

/* ══════════════════════════════════════════════
   ACTIVE REQUESTS  (the most important section)
══════════════════════════════════════════════ */
function renderActiveRequests() {
  // Find or create the active-requests panel in the scroll area
  let panel = document.getElementById('active-requests-panel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'active-requests-panel';
    panel.className = 'panel';
    panel.style.cssText = 'margin-bottom:20px;';
    panel.innerHTML = `
      <div class="panel-hdr" style="margin-bottom:14px">
        <h3 style="display:flex;align-items:center;gap:8px">
          <span style="display:inline-block;width:8px;height:8px;background:#C62828;border-radius:50%;animation:blink 1.4s infinite"></span>
          Live Emergency Requests
        </h3>
        <span id="req-count" style="font-size:12px;color:#9CA3AF;font-weight:600"></span>
      </div>
      <div id="req-list"></div>`;
    // Insert before the ambulance table
    const tbl = document.getElementById('ambulance-table');
    if (tbl) {
      const wrap = tbl.closest('.panel');
      if (wrap) wrap.before(panel);
    } else {
      document.querySelector('.scroll')?.prepend(panel);
    }
  }

  const list = document.getElementById('req-list');
  const countEl = document.getElementById('req-count');
  if (!list) return;

  const active = state.active;
  if (countEl) countEl.textContent = active.length ? `${active.length} active` : 'No active requests';

  if (!active.length) {
    list.innerHTML = `
      <div style="text-align:center;padding:28px 16px;color:#9CA3AF;font-size:13px;font-family:sans-serif">
        <div style="font-size:32px;margin-bottom:8px">✅</div>
        No active emergency requests right now
      </div>`;
    return;
  }

  const STATUS_COLOR = {
    pending:  { bg:'#FEF3C7', color:'#B45309', label:'Pending' },
    active:   { bg:'#FFEBEE', color:'#C62828', label:'Active'  },
    accepted: { bg:'#E6F4EC', color:'#1B7A3E', label:'Accepted'},
    en_route: { bg:'#EFF6FF', color:'#1D4ED8', label:'En Route'},
    picked_up:{ bg:'#F3E8FF', color:'#6D28D9', label:'Picked Up'},
    completed:{ bg:'#E6F4EC', color:'#1B7A3E', label:'Completed'},
  };

  list.innerHTML = active.map(r => {
    const p  = r.patient || {};
    const st = STATUS_COLOR[r.status] || { bg:'#F3F4F6', color:'#374151', label: r.status };
    const ai = r.ambulance_info;
    const hosp = r.hospital_name || '—';
    return `
      <div style="
        background:#F8F9FB; border:1.5px solid #E4E7EC;
        border-radius:12px; padding:14px 16px; margin-bottom:10px;
        font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
      ">
        <!-- header row -->
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
          <div style="display:flex;align-items:center;gap:10px">
            <div style="font-size:13px;font-weight:800;color:#0D1B2A">${r.id}</div>
            <span style="
              background:${st.bg};color:${st.color};
              border-radius:20px;padding:3px 10px;
              font-size:11px;font-weight:700;
            ">${st.label}</span>
            ${r.status === 'pending' ? '<span style="background:#FEF3C7;color:#B45309;border-radius:20px;padding:3px 10px;font-size:11px;font-weight:700;animation:pulse-badge 1s infinite">⏳ Awaiting Driver</span>' : ''}
          </div>
          <div style="font-size:11px;color:#9CA3AF">${timeAgo(r.timestamp)}</div>
        </div>

        <!-- patient + driver columns -->
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
          <!-- patient -->
          <div style="background:#fff;border-radius:9px;padding:10px 12px;border:1px solid #E4E7EC">
            <div style="font-size:10px;font-weight:700;color:#C62828;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px">Patient</div>
            <div style="font-size:13px;font-weight:700;color:#0D1B2A;margin-bottom:2px">${p.name || p.full_name || '—'}</div>
            <div style="font-size:12px;color:#6B7280">${[p.age, p.gender].filter(Boolean).join(', ') || '—'} · ${p.blood_group || '—'}</div>
            <div style="font-size:12px;color:#6B7280;margin-top:3px">📱 ${p.mobile || p.id || '—'}</div>
            <div style="margin-top:6px;display:inline-block;background:#FFEBEE;color:#C62828;border-radius:6px;padding:2px 8px;font-size:11px;font-weight:700">
              🚨 ${p.emergency_type || '—'}
            </div>
          </div>

          <!-- driver / ambulance -->
          <div style="background:#fff;border-radius:9px;padding:10px 12px;border:1px solid #E4E7EC">
            <div style="font-size:10px;font-weight:700;color:#1B7A3E;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px">
              ${ai ? 'Driver / Ambulance' : 'No Driver Assigned Yet'}
            </div>
            ${ai ? `
              <div style="font-size:13px;font-weight:700;color:#0D1B2A;margin-bottom:2px">${ai.driver_name || '—'}</div>
              <div style="font-size:12px;color:#6B7280">${ai.vehicle_type || '—'}</div>
              <div style="font-size:12px;color:#6B7280;margin-top:3px">🚑 ${ai.id}</div>
              <div style="font-size:12px;color:#6B7280;margin-top:2px">🏥 ${hosp}</div>
            ` : `
              <div style="font-size:12px;color:#9CA3AF;margin-top:4px">Waiting for a driver to accept this request…</div>
              <div style="font-size:12px;color:#6B7280;margin-top:6px">🏥 Nearest: ${hosp}</div>
            `}
          </div>
        </div>
      </div>`;
  }).join('');
}

/* ══════════════════════════════════════════════
   ALERTS
══════════════════════════════════════════════ */
function renderAlerts() {
  const list = document.getElementById('alerts-list');
  if (!list) return;

  if (!state.alerts.length) {
    list.innerHTML = `<div class="alert-row">
      <span class="alert-ico">🟢</span>
      <div><div class="alert-title">All systems normal</div>
      <div class="alert-time">No active alerts</div></div></div>`;
    return;
  }

  list.innerHTML = state.alerts.slice(0, 6).map(a => `
    <div class="alert-row">
      <span class="alert-ico">${a.icon || '🟡'}</span>
      <div>
        <div class="alert-title">${a.message || 'Alert'}</div>
        <div class="alert-time">${timeAgo(a.timestamp)}</div>
      </div>
    </div>`).join('');
}

/* ══════════════════════════════════════════════
   MAP
══════════════════════════════════════════════ */
function initMap() {
  state.map = L.map('map', { attributionControl: false, zoomControl: true })
    .setView([13.1, 77.6], 11);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19 }).addTo(state.map);
}

function renderMap() {
  if (!state.map) return;
  state.markers.forEach(m => state.map.removeLayer(m));
  state.markers = [];

  state.ambulances.forEach(a => {
    const lat   = +a.latitude  || 13.1;
    const lon   = +a.longitude || 77.6;
    const color = a.status === 'enroute' ? '#C62828' : a.status === 'maintenance' ? '#B45309' : '#1B7A3E';
    const m = L.circleMarker([lat, lon], {
      radius:9, fillColor:color, color:'#fff', weight:2, fillOpacity:.9
    }).bindPopup(`<b>${a.id}</b><br>${a.driver_name||a.driver||'—'}<br>${a.status}`);
    m.addTo(state.map);
    state.markers.push(m);
  });

  state.hospitals.forEach(h => {
    const m = L.marker([+h.latitude||13.1, +h.longitude||77.6], {
      icon: L.divIcon({ className:'', html:'<div style="font-size:20px;line-height:1">🏥</div>', iconSize:[24,24] })
    }).bindPopup(`<b>${h.name}</b><br>Beds: ${h.beds??'N/A'}`);
    m.addTo(state.map);
    state.markers.push(m);
  });

  // Show active patient locations
  state.active.forEach(r => {
    const p = r.patient;
    if (!p?.latitude) return;
    const m = L.circleMarker([+p.latitude, +p.longitude], {
      radius:7, fillColor:'#C62828', color:'#fff', weight:2, fillOpacity:.8
    }).bindPopup(`<b>${p.name||'Patient'}</b><br>${p.emergency_type||'—'}<br>${r.status}`);
    m.addTo(state.map);
    state.markers.push(m);
  });
}

/* ══════════════════════════════════════════════
   TREND CHART
══════════════════════════════════════════════ */
function renderTrend() {
  const svg = document.getElementById('trend-chart');
  if (!svg || !state.trend.length) return;
  svg.innerHTML = '';

  const data = state.trend;
  const W=560, H=200, px=36, py=24;
  const cW=W-2*px, cH=H-2*py;
  const maxV = Math.max(...data.map(d=>d.count||0), 1);

  svg.innerHTML = `<defs><linearGradient id="tg" x1="0%" y1="0%" x2="0%" y2="100%">
    <stop offset="0%" stop-color="#C62828" stop-opacity=".18"/>
    <stop offset="100%" stop-color="#C62828" stop-opacity="0"/>
  </linearGradient></defs>`;

  const g = svgEl('g'); g.setAttribute('transform',`translate(${px},${py})`);

  [0.25,0.5,0.75,1].forEach(f => {
    const y = cH*(1-f);
    const l = svgEl('line');
    l.setAttribute('x1',0); l.setAttribute('y1',y);
    l.setAttribute('x2',cW); l.setAttribute('y2',y);
    l.setAttribute('stroke','#E4E7EC'); l.setAttribute('stroke-width','1');
    g.appendChild(l);
  });

  const pts = data.map((d,i)=>[
    data.length>1?(i/(data.length-1))*cW:cW/2,
    cH-((d.count||0)/maxV)*cH
  ]);

  if (pts.length>1) {
    const fd=`M${pts[0][0]} ${pts[0][1]} `+pts.slice(1).map(p=>`L${p[0]} ${p[1]}`).join(' ')+` L${pts[pts.length-1][0]} ${cH} L${pts[0][0]} ${cH}Z`;
    const fp=svgEl('path'); fp.setAttribute('d',fd); fp.setAttribute('fill','url(#tg)'); g.appendChild(fp);
    const ld=`M${pts[0][0]} ${pts[0][1]} `+pts.slice(1).map(p=>`L${p[0]} ${p[1]}`).join(' ');
    const lp=svgEl('path'); lp.setAttribute('d',ld); lp.setAttribute('stroke','#C62828');
    lp.setAttribute('stroke-width','2.5'); lp.setAttribute('fill','none'); lp.setAttribute('stroke-linecap','round');
    g.appendChild(lp);
  }

  pts.forEach(([x,y],i)=>{
    const c=svgEl('circle'); c.setAttribute('cx',x); c.setAttribute('cy',y);
    c.setAttribute('r','4'); c.setAttribute('fill','#C62828');
    c.setAttribute('stroke','#fff'); c.setAttribute('stroke-width','2');
    g.appendChild(c);
    const t=svgEl('text'); t.setAttribute('x',x); t.setAttribute('y',cH+16);
    t.setAttribute('text-anchor','middle'); t.setAttribute('font-size','9');
    t.setAttribute('fill','#9CA3AF'); t.setAttribute('font-family','sans-serif');
    t.textContent=data[i].label||'';
    g.appendChild(t);
  });
  svg.appendChild(g);
}

/* ══════════════════════════════════════════════
   DONUT
══════════════════════════════════════════════ */
function renderDonut() {
  const svg = document.getElementById('status-chart');
  if (!svg) return;
  svg.innerHTML='';
  const { available=0, enroute=0, maintenance=0 } = state.statusSummary;
  const total = available+enroute+maintenance||1;
  const segs = [
    {v:available,  color:'#1B7A3E', id:'pct-available'},
    {v:enroute,    color:'#C62828', id:'pct-busy'},
    {v:maintenance,color:'#B45309', id:'pct-idle'},
  ];
  let angle=-90;
  segs.forEach(s=>{
    if(!s.v)return;
    const span=(s.v/total)*360;
    svg.appendChild(donutArc(100,100,72,22,angle,angle+span,s.color));
    angle+=span;
    const el=document.getElementById(s.id);
    if(el) el.textContent=((s.v/total)*100).toFixed(1)+'%';
  });
  // centre
  const t=svgEl('text'); t.setAttribute('x','100'); t.setAttribute('y','107');
  t.setAttribute('text-anchor','middle'); t.setAttribute('font-family','sans-serif');
  t.setAttribute('font-size','22'); t.setAttribute('font-weight','900'); t.setAttribute('fill','#0D1B2A');
  t.textContent=available+enroute+maintenance;
  svg.appendChild(t);
}

function donutArc(cx,cy,r,thick,a1,a2,color){
  const rad=d=>d*Math.PI/180;
  const s=rad(a1),e=rad(a2);
  const x1=cx+r*Math.cos(s),y1=cy+r*Math.sin(s);
  const x2=cx+r*Math.cos(e),y2=cy+r*Math.sin(e);
  const x3=cx+(r-thick)*Math.cos(e),y3=cy+(r-thick)*Math.sin(e);
  const x4=cx+(r-thick)*Math.cos(s),y4=cy+(r-thick)*Math.sin(s);
  const lg=a2-a1>180?1:0;
  const p=svgEl('path');
  p.setAttribute('d',`M${x1} ${y1} A${r} ${r} 0 ${lg} 1 ${x2} ${y2} L${x3} ${y3} A${r-thick} ${r-thick} 0 ${lg} 0 ${x4} ${y4}Z`);
  p.setAttribute('fill',color);
  return p;
}

/* ══════════════════════════════════════════════
   AMBULANCE TABLE
══════════════════════════════════════════════ */
function renderAmbulanceTable() {
  const tbody = document.getElementById('ambulance-table');
  if (!tbody) return;
  if (!state.ambulances.length) {
    tbody.innerHTML='<tr><td colspan="5" class="empty">No ambulances found</td></tr>';
    return;
  }
  tbody.innerHTML = state.ambulances.map(a=>{
    const st  = a.status||'available';
    const bc  = st==='enroute'?'busy':st==='maintenance'?'idle':'ok';
    const lbl = st==='enroute'?'En Route':st.charAt(0).toUpperCase()+st.slice(1);
    const loc = a.latitude?`${(+a.latitude).toFixed(4)}, ${(+a.longitude).toFixed(4)}`:'—';
    return `<tr>
      <td><strong>${a.id||'—'}</strong></td>
      <td>${a.driver_name||a.driver||'Unassigned'}</td>
      <td>${a.vehicle_type||'—'}</td>
      <td><span class="badge ${bc}">${lbl}</span></td>
      <td style="color:#9CA3AF;font-size:12px">${loc}</td>
    </tr>`;
  }).join('');
}

/* ══════════════════════════════════════════════
   UTILS
══════════════════════════════════════════════ */
function svgEl(tag){ return document.createElementNS('http://www.w3.org/2000/svg',tag); }

function timeAgo(ts){
  if(!ts) return 'Just now';
  const d=Math.floor((Date.now()-new Date(ts))/1000);
  if(d<60) return 'Just now';
  if(d<3600) return Math.floor(d/60)+' min ago';
  if(d<86400) return Math.floor(d/3600)+' hr ago';
  return Math.floor(d/86400)+' day ago';
}

/* ══════════════════════════════════════════════
   PULSE ANIMATION FOR PENDING BADGE
══════════════════════════════════════════════ */
const _s = document.createElement('style');
_s.textContent = `
  @keyframes pulse-badge { 0%,100%{opacity:1} 50%{opacity:.5} }
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.2}}
`;
document.head.appendChild(_s);
