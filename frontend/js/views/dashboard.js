import { api } from "../api.js";
import { icon } from "../icons.js";
import { $, countUp, enter, esc, timeAgo, PRIORITY_LABEL, WO_LABEL } from "../ui.js";

const KPIS = [
  { id: "waiting", label: "Patients waiting", icon: "users", tone: "" },
  { id: "serving", label: "In consultation now", icon: "pulse", tone: "blue" },
  { id: "open", label: "Open medicine orders", icon: "package", tone: "amber" },
  { id: "critical", label: "Critical, not yet received", icon: "alert", tone: "alert" },
];

// One heartbeat, drawn twice across the hero
const ECG = "M0 60 H180 l15 0 l10 -10 l10 10 H300 l12 8 l14 -50 l16 80 l12 -38 H520 l15 0 l10 -10 l10 10 H700 l12 8 l14 -50 l16 80 l12 -38 H1000";

let el, lastDepts, lastOrders;

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

function tile(d) {
  const shown = Math.min(d.waiting, 12);
  const dots = Array.from({ length: shown }, (_, i) => `<i style="--i:${i}"></i>`).join("");
  const more = d.waiting > shown ? `<small>+${d.waiting - shown}</small>` : "";
  return `
    <a class="dept ${d.now_serving ? "live" : ""} ${enter(`dept-${d.code}-${d.now_serving}`)}" href="#/staff/${d.code}">
      <header><h3>${esc(d.name)}</h3><span class="chip chip-soft">${d.waiting} waiting</span></header>
      <div class="serving"><span class="muted">${d.now_serving ? "Now serving" : "Doctor free"}</span>
        <strong class="token-big">${d.now_serving ?? "None"}</strong></div>
      <div class="dots">${dots}${more}</div>
    </a>`;
}

function recentRow(o) {
  return `
    <li class="${enter(`recent-${o.id}-${o.status}`)}">
      <span class="pdot p-${o.priority}" title="${PRIORITY_LABEL[o.priority]} priority"></span>
      <div class="who"><strong>${esc(o.medicine_name)}</strong><span class="muted">${o.quantity_needed.toLocaleString()} needed</span></div>
      <span class="chip s-${o.status}">${WO_LABEL[o.status]}</span>
      <span class="muted">${timeAgo(o.created_at)}</span>
    </li>`;
}

export default {
  title: "Overview",
  subtitle: "Patient flow and medicine availability, updated every few seconds.",

  async mount(root) {
    el = root;
    lastDepts = lastOrders = "";
    el.innerHTML = `
      <section class="hero">
        <h2>${greeting()}. <span id="hero-line">Checking the wards...</span></h2>
        <p>See who is waiting, who is with a doctor, and which medicines need action.</p>
        <svg class="ecg" viewBox="0 0 1000 84" preserveAspectRatio="none" aria-hidden="true">
          <path class="track" d="${ECG}" transform="translate(0 10)"/>
          <path class="pulse" pathLength="1000" d="${ECG}" transform="translate(0 10)"/>
        </svg>
      </section>
      <section class="kpis">
        ${KPIS.map((k) => `
          <article class="card kpi">
            <span class="kpi-icon ${k.tone}">${icon[k.icon]}</span>
            <div><div class="kpi-num" id="kpi-${k.id}">0</div><div class="kpi-label">${k.label}</div></div>
          </article>`).join("")}
      </section>
      <div class="section-head"><h2>Department queues</h2><a class="btn ghost small" href="#/staff">Open OPD staff desk</a></div>
      <div class="dept-grid" id="depts"></div>
      <div class="section-head"><h2>Latest medicine orders</h2><a class="btn ghost small" href="#/stock">Open stock board</a></div>
      <section class="card"><ul class="recent" id="recent"></ul></section>`;
    await this.refresh();
  },

  async refresh() {
    const root = el;
    const [depts, orders] = await Promise.all([api.departments(), api.workOrders()]);
    if (root !== el) return; // user navigated away

    const waiting = depts.reduce((n, d) => n + d.waiting, 0);
    const serving = depts.filter((d) => d.now_serving).length;
    const open = orders.filter((o) => o.status !== "completed");
    const critical = open.filter((o) => o.priority === "critical" && o.status !== "received");

    countUp($("#kpi-waiting", el), waiting);
    countUp($("#kpi-serving", el), serving);
    countUp($("#kpi-open", el), open.length);
    countUp($("#kpi-critical", el), critical.length);
    $("#hero-line", el).textContent =
      `${waiting} ${waiting === 1 ? "patient is" : "patients are"} waiting and ${critical.length} critical medicine ${critical.length === 1 ? "order needs" : "orders need"} attention.`;

    const deptSig = JSON.stringify(depts);
    if (deptSig !== lastDepts) {
      lastDepts = deptSig;
      $("#depts", el).innerHTML = depts.map(tile).join("");
    }
    const latest = orders.slice(0, 5);
    const orderSig = JSON.stringify(latest);
    if (orderSig !== lastOrders) {
      lastOrders = orderSig;
      $("#recent", el).innerHTML = latest.length
        ? latest.map(recentRow).join("")
        : `<div class="empty"><strong>No medicine orders yet</strong>Raise one from the stock board when an item runs out.</div>`;
    }
  },
};
