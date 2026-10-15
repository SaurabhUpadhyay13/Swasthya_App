import { api, staffSession } from "../api.js";
import { icon } from "../icons.js";
import { $, countUp, enter, errorText, esc, toast, withBusy } from "../ui.js";
import queueView from "./queue.js";

const KPIS = [
  { id: "waiting", label: "Patients waiting", icon: "users", tone: "" },
  { id: "in_consultation", label: "In consultation now", icon: "pulse", tone: "blue" },
  { id: "registered_today", label: "Registered today", icon: "plus", tone: "amber" },
  { id: "completed_today", label: "Completed today", icon: "check", tone: "" },
];

const until = (iso) =>
  new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

let el, loggedIn, stockSig, startParam;

const stockRow = (m) => `
  <li class="${enter(`ls-${m.id}-${m.stock}`)}">
    <div class="who"><strong>${esc(m.name)}</strong></div>
    <span class="stock ${m.stock === 0 ? "out" : "low"}">${m.stock === 0 ? "Out of stock" : `${m.stock} left`}</span>
  </li>`;

function showLogin() {
  loggedIn = false;
  el.innerHTML = `
    <section class="card acc-login">
      <h2>OPD staff login</h2>
      <span class="muted">Use your name and staff ID.</span>
      <form class="form" id="login-form">
        <label class="field">Full name<input name="name" required autocomplete="off" placeholder="Meena Joshi"></label>
        <label class="field">Staff ID<input name="staff_id" required autocomplete="off"></label>
        <button class="btn" type="submit">Log in</button>
      </form>
    </section>`;
  $("#login-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      const result = await withBusy($("button", form), () => api.staffLogin(form.name.value.trim(), form.staff_id.value.trim()));
      staffSession.set(result.token);
      loggedIn = true;
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

function renderShell(staff) {
  stockSig = "";
  el.innerHTML = `
    <section class="card acc-head">
      <div><h2>${esc(staff.name)}</h2><span class="muted">OPD staff</span> <span class="muted">Staff ID ${esc(staff.staff_id)}</span></div>
      <button class="btn plain" type="button" id="logout">Log out</button>
    </section>
    <section class="acc-kpis">
      ${KPIS.map((k) => `
        <article class="card kpi">
          <span class="kpi-icon ${k.tone}">${icon[k.icon]}</span>
          <div><div class="kpi-num" id="kpi-${k.id}">0</div><div class="kpi-label">${k.label}</div></div>
        </article>`).join("")}
    </section>
    <div id="queue-host"></div>
    <div class="acc-pair">
      <section class="card">
        <h2>Patient access code</h2>
        <p class="muted">For a patient who already has a hospital record and wants to open or reset their Patient portal login. New patients can sign up on their own.</p>
        <form class="form" id="code-form">
          <label class="field">Patient phone number
            <input name="phone" required inputmode="numeric" pattern="\\d{10}" maxlength="10" autocomplete="off" placeholder="10 digits"></label>
          <button class="btn" type="submit">Generate code</button>
        </form>
        <div id="code-out" aria-live="polite"></div>
      </section>
      <section class="card">
        <div class="side-head"><h2>Low medicine stock</h2><span class="muted" id="stock-level"></span></div>
        <ul class="doc-list" id="low-stock"></ul>
        <p class="muted" id="orders-line"></p>
      </section>
    </div>`;

  $("#logout", el).addEventListener("click", async (e) => {
    await withBusy(e.currentTarget, () => api.staffLogout().catch(() => {}));
    staffSession.clear();
    showLogin();
  });

  $("#code-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      const issued = await withBusy($("button", form), () => api.issuePatientCode(form.phone.value.trim()));
      $("#code-out", el).innerHTML = `
        <div class="code-box enter">
          <span class="muted">Code for ${esc(issued.patient_name)} (${esc(issued.phone)})</span>
          <strong class="code">${issued.code.slice(0, 3)} ${issued.code.slice(3)}</strong>
          <span class="muted">Valid until ${until(issued.expires_at)}. Give it to the patient in person; it works once.</span>
        </div>`;
      form.reset();
    } catch (error) {
      $("#code-out", el).innerHTML = "";
      if (error.status === 401) await load();
      else toast(errorText(error), "error");
    }
  });
}

async function load() {
  const root = el;
  let board;
  try {
    board = await api.staffDashboard();
  } catch (error) {
    if (error.status !== 401) throw error;
    staffSession.clear();
    if (root === el) {
      showLogin();
      toast("Your session has ended. Please log in again.", "error");
    }
    return;
  }
  if (root !== el) return;
  if (!$("#queue-host", el)) {
    renderShell(board.staff);
    await queueView.mount($("#queue-host", el), startParam); // registration and the live queue board
    if (root !== el) return;
  }

  for (const k of KPIS) countUp($(`#kpi-${k.id}`, el), board[k.id]);

  const ssig = JSON.stringify(board.low_stock);
  if (ssig !== stockSig) {
    stockSig = ssig;
    $("#low-stock", el).innerHTML = board.low_stock.length
      ? board.low_stock.map(stockRow).join("")
      : `<li class="empty muted">Every medicine is above the low-stock level.</li>`;
  }
  $("#stock-level", el).textContent = `${board.low_stock_level} or fewer`;
  $("#orders-line", el).textContent =
    `${board.open_work_orders} open medicine ${board.open_work_orders === 1 ? "order" : "orders"}, ${board.critical_open_work_orders} critical and not yet received.`;
}

export default {
  title: "OPD staff desk",
  subtitle: "Register walk-in patients, run the queues and watch today's numbers and low stock.",

  async mount(root, param) {
    el = root;
    startParam = param;
    loggedIn = Boolean(staffSession.get());
    if (!loggedIn) return showLogin();
    await load();
  },

  refresh: () => (loggedIn ? Promise.all([load(), queueView.refresh()]) : Promise.resolve()),
};
