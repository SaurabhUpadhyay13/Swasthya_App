import { api } from "../api.js";
import { icon } from "../icons.js";
import { $, countUp, enter, esc, timeAgo, PRIORITY_LABEL, WO_LABEL } from "../ui.js";

// Departments are shown as a sliding carousel: 4 tiles per page on a wide screen, fewer on a narrow one.
const perPage = () => (window.matchMedia("(min-width: 1000px)").matches ? 4 : window.matchMedia("(min-width: 640px)").matches ? 2 : 1);

const KPIS = [
  { id: "waiting", label: "Patients waiting", icon: "users", tone: "" },
  { id: "serving", label: "In consultation now", icon: "pulse", tone: "blue" },
  { id: "open", label: "Open medicine orders", icon: "package", tone: "amber" },
  { id: "critical", label: "Critical, not yet received", icon: "alert", tone: "alert" },
];

// One heartbeat, drawn twice across the hero
const ECG = "M0 60 H180 l15 0 l10 -10 l10 10 H300 l12 8 l14 -50 l16 80 l12 -38 H520 l15 0 l10 -10 l10 10 H700 l12 8 l14 -50 l16 80 l12 -38 H1000";

let el, lastDepts, lastOrders;
let depts = [];
let query = "";
let page = 0;
let onResize = null;

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

const matches = (d) => `${d.name} ${d.code.replaceAll("_", " ")} ${d.prefix}`.toLowerCase().includes(query.trim().toLowerCase());

// Rebuild the tiles (data, search text or screen size changed), then position the slider.
function renderDepartments() {
  const list = depts.filter(matches);
  const pages = Math.max(1, Math.ceil(list.length / perPage()));
  page = Math.min(page, pages - 1);
  $("#depts", el).innerHTML = list.map(tile).join("");
  $("#dept-empty", el).hidden = list.length > 0;
  slide(list.length);
}

// Move to `page`: slide the track, keep off-screen tiles out of the tab order, update arrows and counter.
function slide(total = $("#depts", el).children.length) {
  const n = perPage();
  const pages = Math.max(1, Math.ceil(total / n));
  const track = $("#depts", el);
  track.style.setProperty("--n", n);
  track.style.setProperty("--page", page);
  [...track.children].forEach((tileEl, i) => {
    tileEl.inert = Math.floor(i / n) !== page;
  });
  $("#dept-prev", el).disabled = page === 0;
  $("#dept-next", el).disabled = page >= pages - 1;
  $("#dept-count", el).textContent = total
    ? `${page * n + 1}-${Math.min(total, page * n + n)} of ${total}${query.trim() ? " matching" : ""}`
    : "No match";
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
      <div class="dept-tools">
        <label class="dept-search">${icon.search}<input type="search" id="dept-q" placeholder="Search: eye, den, card..." autocomplete="off" aria-label="Search departments"></label>
        <div class="pager">
          <span class="muted" id="dept-count" aria-live="polite"></span>
          <button type="button" class="arrow" id="dept-prev" aria-label="Previous departments">${icon.chevronLeft}</button>
          <button type="button" class="arrow" id="dept-next" aria-label="Next departments">${icon.chevronRight}</button>
        </div>
      </div>
      <div class="dept-viewport"><div class="dept-track" id="depts"></div></div>
      <div class="dept-empty" id="dept-empty" hidden><strong>No department matches your search</strong></div>
      <div class="section-head"><h2>Latest medicine orders</h2><a class="btn ghost small" href="#/stock">Open stock board</a></div>
      <section class="card"><ul class="recent" id="recent"></ul></section>`;
    depts = [];
    query = "";
    page = 0;

    $("#dept-q", el).addEventListener("input", (e) => {
      query = e.target.value;
      page = 0;
      renderDepartments();
    });
    $("#dept-prev", el).addEventListener("click", () => {
      page = Math.max(0, page - 1);
      slide();
    });
    $("#dept-next", el).addEventListener("click", () => {
      page += 1; // slide() disables the arrow on the last page, so this never goes past it
      slide();
    });
    if (onResize) window.removeEventListener("resize", onResize);
    onResize = () => {
      if (el?.isConnected && $("#depts", el)) renderDepartments();
    };
    window.addEventListener("resize", onResize);

    await this.refresh();
  },

  async refresh() {
    const root = el;
    const [latestDepts, orders] = await Promise.all([api.departments(), api.workOrders()]);
    if (root !== el) return; // user navigated away

    depts = latestDepts;
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
      renderDepartments(); // keeps the current page and search text
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
