import { adminSession, api } from "../api.js";
import { icon } from "../icons.js";
import { $, countUp, enter, errorText, esc, timeAgo, toast, withBusy } from "../ui.js";

// Departments are shown as a sliding carousel: 4 tiles per page on a wide screen, fewer on a narrow one.
const perPage = () => (window.matchMedia("(min-width: 1000px)").matches ? 4 : window.matchMedia("(min-width: 640px)").matches ? 2 : 1);

const KPIS = [
  { id: "waiting", label: "Patients waiting", icon: "users", tone: "" },
  { id: "in_consultation", label: "In consultation now", icon: "pulse", tone: "blue" },
  { id: "registered", label: "Registered today", icon: "plus", tone: "amber" },
  { id: "wait", label: "Average wait today (min)", icon: "clock", tone: "" },
];

// One heartbeat, drawn twice across the hero
const ECG = "M0 60 H180 l15 0 l10 -10 l10 10 H300 l12 8 l14 -50 l16 80 l12 -38 H520 l15 0 l10 -10 l10 10 H700 l12 8 l14 -50 l16 80 l12 -38 H1000";

const ORDER_STEPS = [
  ["requested", "Requested"],
  ["ordered", "Ordered"],
  ["received", "Received"],
  ["completed", "Completed"],
];

let el, loggedIn, sigs;
let depts = [];
let query = "";
let page = 0;
let onResize = null;

const greeting = () => {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening";
};

// ---------- Sign in ----------

function showLogin() {
  loggedIn = false;
  el.innerHTML = `
    <section class="card acc-login">
      <h2>Administrator login</h2>
      <span class="muted">Use your admin ID and password.</span>
      <form class="form" id="login-form">
        <label class="field">Admin ID<input name="admin_id" required autocomplete="username" placeholder="ADMIN-001"></label>
        <label class="field">Password<input name="password" type="password" required autocomplete="current-password"></label>
        <button class="btn" type="submit">Log in</button>
      </form>
      <p class="muted fine">Administrator accounts are created from the server with <code>python -m app.cli add-admin</code>.</p>
    </section>`;
  $("#login-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      const result = await withBusy($("button", form), () => api.adminLogin(form.admin_id.value.trim(), form.password.value));
      adminSession.set(result.token);
      loggedIn = true;
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

// ---------- Department carousel ----------

function tile(d) {
  const shown = Math.min(d.waiting, 12);
  const dots = Array.from({ length: shown }, (_, i) => `<i style="--i:${i}"></i>`).join("");
  const more = d.waiting > shown ? `<small>+${d.waiting - shown}</small>` : "";
  return `
    <article class="dept ${d.now_serving ? "live" : ""} ${enter(`dept-${d.code}-${d.now_serving}`)}">
      <header><h3>${esc(d.name)}</h3><span class="chip chip-soft">${d.waiting} waiting</span></header>
      <div class="serving"><span class="muted">${d.now_serving ? "Now serving" : "Doctor free"}</span>
        <strong class="token-big">${d.now_serving ?? "None"}</strong></div>
      <div class="dots">${dots}${more}</div>
    </article>`;
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

// ---------- Panels ----------

const doctorRow = (d) => `
  <tr class="${enter(`dr-${d.id}-${d.online}-${d.seen_today}`)}">
    <td><strong>${esc(d.name)}</strong><span class="muted">${esc(d.department_name)}</span></td>
    <td><span class="presence ${d.online ? "on" : ""}">${d.online ? "Online" : "Offline"}</span></td>
    <td class="num">${d.seen_today}</td>
    <td class="num">${d.waiting_in_department}</td>
    <td class="muted">${d.last_active_at ? timeAgo(d.last_active_at) : "No activity yet"}</td>
  </tr>`;

function renderDoctors(doctors) {
  const online = doctors.filter((d) => d.online).length;
  $("#adm-doctors-count", el).textContent = doctors.length ? `${online} of ${doctors.length} online` : "";
  $("#adm-doctors", el).innerHTML = doctors.length
    ? `<div class="table-wrap"><table class="table"><thead><tr><th>Doctor</th><th>Status</th><th class="num">Seen today</th><th class="num">Waiting</th><th>Last active</th></tr></thead>
        <tbody>${doctors.slice(0, 6).map(doctorRow).join("")}</tbody></table></div>
       ${doctors.length > 6 ? `<a class="more-link" href="#/people">See all ${doctors.length} doctors</a>` : ""}`
    : `<div class="empty"><strong>No doctors registered yet</strong><a href="#/people">Add the first doctor</a></div>`;
}

function renderChart(series, today) {
  const max = Math.max(1, ...series.map((d) => d.visits));
  $("#adm-chart", el).innerHTML = series
    .map((d, i) => {
      const label = i === series.length - 1 ? "Today" : new Date(`${d.date}T00:00:00`).toLocaleDateString([], { weekday: "short" });
      return `<div class="bar-col" title="${esc(d.date)}: ${d.visits} visits">
        <span class="bar-val">${d.visits}</span>
        <div class="bar-track"><div class="bar ${i === series.length - 1 ? "now" : ""}" style="--h:${(d.visits / max) * 100}%"></div></div>
        <span class="bar-label">${label}</span></div>`;
    })
    .join("");
  $("#adm-outcomes", el).innerHTML = `
    <li><b>${today.completed}</b><span>completed today</span></li>
    <li><b>${today.cancelled}</b><span>cancelled today</span></li>
    <li><b>${today.waiting}</b><span>waiting now</span></li>`;
}

function renderPharmacy(p) {
  $("#adm-tiles", el).innerHTML = `
    <li><b>${p.medicines}</b><span>medicines tracked</span></li>
    <li class="${p.out_of_stock ? "bad" : ""}"><b>${p.out_of_stock}</b><span>out of stock</span></li>
    <li><b>${p.open_work_orders}</b><span>open orders</span></li>
    <li class="${p.critical_open_work_orders ? "bad" : ""}"><b>${p.critical_open_work_orders}</b><span>critical orders</span></li>`;
  $("#adm-low-level", el).textContent = `at or below ${p.low_stock_level}`;
  $("#adm-low", el).innerHTML = p.low_stock.length
    ? p.low_stock
        .map((m) => `<li class="${enter(`lo-${m.id}-${m.stock}`)}"><div class="who"><strong>${esc(m.name)}</strong></div>
          <span class="stock ${m.stock === 0 ? "out" : "low"}">${m.stock === 0 ? "Out of stock" : `${m.stock} left`}</span></li>`)
        .join("")
    : `<li class="muted">Every medicine is above the low-stock level.</li>`;
  $("#adm-dispensed", el).innerHTML = p.dispensed_today.length
    ? p.dispensed_today.map((d) => `<li><div class="who"><strong>${esc(d.medicine)}</strong></div><span class="muted">${d.quantity} units</span></li>`).join("")
    : `<li class="muted">Nothing dispensed yet today.</li>`;
  const total = Math.max(1, ORDER_STEPS.reduce((n, [key]) => n + (p.work_orders_by_status[key] ?? 0), 0));
  $("#adm-pipeline", el).innerHTML = ORDER_STEPS.map(
    ([key, label]) => `<li class="s-${key}" style="--w:${((p.work_orders_by_status[key] ?? 0) / total) * 100}%">
      <span class="pipe-bar"></span><b>${p.work_orders_by_status[key] ?? 0}</b><span class="muted">${label}</span></li>`,
  ).join("");
}

function renderFeed(events) {
  $("#adm-feed", el).innerHTML = events.length
    ? events
        .map((e) => `<li class="${enter(`ev-${e.at}`)}"><span class="dot ev-${e.kind}"></span>
          <span>${esc(e.text)}</span><span class="muted">${timeAgo(e.at)}</span></li>`)
        .join("")
    : `<li class="muted">Activity will appear here as patients are registered and medicines are ordered.</li>`;
}

// Only rebuild a panel when its data changed, so nothing flickers on the 5-second refresh.
function once(name, data, render) {
  const sig = JSON.stringify(data);
  if (sigs[name] === sig) return;
  sigs[name] = sig;
  render(data);
}

// ---------- Screen ----------

function renderShell(admin) {
  sigs = {};
  depts = [];
  query = "";
  page = 0;
  el.innerHTML = `
    <section class="card acc-head">
      <div><h2>${esc(admin.name)}</h2><span class="muted">Administrator</span> <span class="muted">Admin ID ${esc(admin.admin_id)}</span></div>
      <button class="btn plain" type="button" id="logout">Log out</button>
    </section>
    <section class="hero">
      <h2>${greeting()}. <span id="hero-line">Checking the wards...</span></h2>
      <p>See who is waiting, which doctors are working, and what the pharmacy needs.</p>
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

    <div class="section-head"><h2>Department queues</h2></div>
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

    <div class="adm-pair">
      <section class="card adm-card">
        <div class="side-head"><h2>Doctors</h2><span class="muted" id="adm-doctors-count"></span></div>
        <div id="adm-doctors"></div>
      </section>
      <section class="card adm-card">
        <div class="side-head"><h2>Visits, last 7 days</h2></div>
        <div class="bars" id="adm-chart" aria-label="Visits per day"></div>
        <ul class="mini-stats" id="adm-outcomes"></ul>
      </section>
    </div>

    <div class="section-head"><h2>Pharmacy</h2><a class="btn ghost small" href="#/stock">Open medicine orders</a></div>
    <section class="card adm-card">
      <ul class="tiles" id="adm-tiles"></ul>
      <div class="adm-trio">
        <div>
          <div class="side-head"><h3>Low stock</h3><span class="muted" id="adm-low-level"></span></div>
          <ul class="doc-list" id="adm-low"></ul>
        </div>
        <div>
          <div class="side-head"><h3>Dispensed today</h3></div>
          <ul class="doc-list" id="adm-dispensed"></ul>
          <h3 class="sub">Medicine orders</h3>
          <ul class="pipe" id="adm-pipeline"></ul>
        </div>
        <div>
          <h3>Add stock</h3>
          <p class="muted">An opening balance or a top-up. A new name creates the medicine.</p>
          <form class="form" id="stock-form">
            <label class="field">Medicine<input name="medicine" required minlength="2" maxlength="100" autocomplete="off" placeholder="Paracetamol 500mg"></label>
            <label class="field">Quantity<input name="quantity" type="number" required min="1" max="1000000" inputmode="numeric" placeholder="100"></label>
            <button class="btn" type="submit">Add to stock</button>
          </form>
        </div>
      </div>
    </section>

    <div class="section-head"><h2>Live activity</h2></div>
    <section class="card adm-card"><ul class="feed" id="adm-feed"></ul></section>`;

  $("#logout", el).addEventListener("click", async (e) => {
    await withBusy(e.currentTarget, () => api.adminLogout().catch(() => {}));
    adminSession.clear();
  });
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
  $("#stock-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      const medicine = await withBusy($("button", form), () =>
        api.addStock({ medicine: form.medicine.value.trim(), quantity: Number(form.quantity.value) }));
      toast(`${medicine.name} now has ${medicine.stock} in stock.`);
      form.reset();
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
  if (onResize) window.removeEventListener("resize", onResize);
  onResize = () => {
    if (el?.isConnected && $("#depts", el)) renderDepartments();
  };
  window.addEventListener("resize", onResize);
}

async function load() {
  const root = el;
  const board = await api.adminDashboard(); // a 401 clears the login and the app returns to the login screen
  if (root !== el) return; // moved to another page
  if (!$("#depts", el)) renderShell(board.admin);

  const { today, pharmacy } = board;
  countUp($("#kpi-waiting", el), today.waiting);
  countUp($("#kpi-in_consultation", el), today.in_consultation);
  countUp($("#kpi-registered", el), today.registered);
  countUp($("#kpi-wait", el), Math.round(today.average_wait_minutes ?? 0));
  const waitNote = today.average_wait_minutes === null ? "" : ` Patients registered today waited ${Math.round(today.average_wait_minutes)} minutes on average.`;
  $("#hero-line", el).textContent =
    `${today.waiting} ${today.waiting === 1 ? "patient is" : "patients are"} waiting and ${pharmacy.critical_open_work_orders} critical medicine ${pharmacy.critical_open_work_orders === 1 ? "order needs" : "orders need"} attention.${waitNote}`;

  depts = board.departments;
  once("depts", depts, renderDepartments); // keeps the current page and search text
  const minute = Math.floor(Date.now() / 60000); // "5 min ago" labels need a redraw as time passes
  once("doctors", [board.doctors, minute], () => renderDoctors(board.doctors));
  once("chart", [board.visits_last_7_days, today], () => renderChart(board.visits_last_7_days, today));
  once("pharmacy", pharmacy, renderPharmacy);
  once("feed", [board.recent_activity, minute], () => renderFeed(board.recent_activity));
}

export default {
  title: "Dashboard",
  subtitle: "The whole hospital at a glance, updated every few seconds.",

  async mount(root) {
    el = root;
    loggedIn = Boolean(adminSession.get());
    if (!loggedIn) return showLogin();
    await load();
  },

  async refresh() {
    if (loggedIn) await load();
  },
};
