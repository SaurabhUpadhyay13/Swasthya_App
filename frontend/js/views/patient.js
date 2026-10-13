import { api, patientSession } from "../api.js";
import { icon } from "../icons.js";
import { $, enter, errorText, esc, toast, withBusy, TOKEN_LABEL } from "../ui.js";

const STEPS = [
  { status: "waiting", label: "In queue" },
  { status: "in_consultation", label: "Consultation" },
  { status: "prescribed", label: "Prescription" },
  { status: "pharmacy", label: "Pharmacy" },
  { status: "completed", label: "Done" },
];

const when = (iso) =>
  new Date(iso).toLocaleString([], { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

let el, loggedIn, lastSig;

// ---------- Renderers ----------

function headline(t) {
  switch (t.status) {
    case "waiting": return t.position === 1 ? "You are next. Please stay close to the consultation room." : `${t.position - 1} patients are ahead of you.`;
    case "in_consultation": return "It is your turn. Please go in to see the doctor.";
    case "prescribed": return "Your prescription is ready. Please walk to the pharmacy.";
    default: return "Collect your medicines at the pharmacy counter.";
  }
}

function currentCard(t) {
  const index = STEPS.findIndex((s) => s.status === t.status);
  const steps = STEPS.map((s, i) => `
    <div class="step ${i < index ? "done" : ""} ${i === index ? "current" : ""}">
      <i>${i <= index ? icon.check : ""}</i><span>${s.label}</span>
    </div>`).join("");
  return `
    <article class="card track-card">
      <div class="track-head">
        <span class="token-badge" style="font-size:22px;padding:12px 18px">${t.token}</span>
        <div><span class="muted">Your visit today, ${esc(t.department_name)}</span><h2>${headline(t)}</h2></div>
        <span class="chip s-${t.status}" style="margin-left:auto">${TOKEN_LABEL[t.status]}</span>
      </div>
      <div class="stats">
        <div class="stat"><span class="muted">Place in line</span><b>${t.position ? `#${t.position}` : "-"}</b></div>
        <div class="stat"><span class="muted">Estimated wait</span><b>${t.estimated_wait_minutes != null ? `${t.estimated_wait_minutes} min` : "-"}</b></div>
      </div>
      <div class="stepper" style="--p:${index / (STEPS.length - 1)}"><span class="fill"></span>${steps}</div>
    </article>`;
}

function medicineLine(i) {
  let given = "";
  if (i.dispensed_quantity !== null) {
    given = i.dispensed_quantity < i.quantity
      ? ` <span class="stock low">Given ${i.dispensed_quantity} of ${i.quantity}</span>`
      : ` <span class="stock ok">Given</span>`;
  }
  return `<li>${esc(i.medicine_name)} &times; ${i.quantity}${i.instructions ? `, ${esc(i.instructions)}` : ""}${given}</li>`;
}

const visitCard = (v) => `
  <article class="card visit-card ${enter(`pv-${v.token}`)}">
    <header><strong>${when(v.registered_at)}</strong><span class="chip chip-soft">${esc(v.department_name)}</span></header>
    <p class="muted">Token ${v.token}${v.doctor_name ? `, seen by ${esc(v.doctor_name)}` : ""}</p>
    ${v.complaint ? `<p><span class="muted">You came in for</span> ${esc(v.complaint)}</p>` : ""}
    <div><span class="muted">Doctor's remarks</span>
      <p class="remarks">${v.remarks ? esc(v.remarks) : `<span class="muted">No remarks were recorded.</span>`}</p></div>
    ${v.prescription.length ? `<div><span class="muted">Medicines</span><ul class="visit-meds">${v.prescription.map(medicineLine).join("")}</ul></div>` : ""}
  </article>`;

// ---------- Screens ----------

function showLogin(mode = "login") {
  loggedIn = false;
  const first = mode === "activate";
  el.innerHTML = `
    <section class="card acc-login">
      <h2>${first ? "Create your password" : "Patient login"}</h2>
      <span class="muted">${first
        ? "Ask the OPD desk for a one-time code, then choose your own password."
        : "Use the phone number you gave at registration and your password."}</span>
      <form class="form" id="login-form" novalidate>
        <label class="field">Phone number
          <input name="phone" required inputmode="numeric" maxlength="10" autocomplete="username" placeholder="10 digits"></label>
        ${first ? `<label class="field">Code from the OPD desk
          <input name="code" required inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="6 digits"></label>` : ""}
        <label class="field">${first ? "Choose a password (8 or more characters)" : "Password"}
          <input name="password" type="password" required maxlength="72" autocomplete="${first ? "new-password" : "current-password"}"></label>
        <button class="btn" type="submit">${first ? "Create password and log in" : "Log in"}</button>
      </form>
      <button class="btn plain" type="button" id="switch">${first ? "I already have a password" : "First time here? Create your password"}</button>
    </section>`;

  $("#switch", el).addEventListener("click", () => showLogin(first ? "login" : "activate"));
  $("#login-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.currentTarget;
    const phone = f.phone.value.trim();
    if (!/^\d{10}$/.test(phone)) return toast("Enter your 10-digit phone number.", "error");
    try {
      const result = await withBusy($("button", f), () =>
        first ? api.patientActivate(phone, f.code.value.trim(), f.password.value) : api.patientLogin(phone, f.password.value));
      patientSession.set(result.token);
      loggedIn = true;
      lastSig = "";
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

function renderShell(patient) {
  lastSig = "";
  el.innerHTML = `
    <section class="card acc-head">
      <div><h2>${esc(patient.name)}</h2><span class="muted">${patient.age} yrs</span> <span class="muted">${esc(patient.phone)}</span></div>
      <button class="btn plain" type="button" id="logout">Log out</button>
    </section>
    <div id="p-current"></div>
    <div class="section-head"><h2>Your visits</h2><span class="muted" id="p-count"></span></div>
    <div class="visit-list" id="p-visits"></div>`;
  $("#logout", el).addEventListener("click", async (e) => {
    await withBusy(e.currentTarget, () => api.patientLogout().catch(() => {}));
    patientSession.clear();
    showLogin();
  });
}

async function load() {
  const root = el;
  let board;
  try {
    board = await api.patientDashboard();
  } catch (error) {
    if (error.status !== 401) throw error;
    patientSession.clear();
    if (root === el) {
      showLogin();
      toast("Your session has ended. Please log in again.", "error");
    }
    return;
  }
  if (root !== el) return;
  if (!$("#p-visits", el)) renderShell(board.patient);

  const sig = JSON.stringify([board.current, board.visits]);
  if (sig === lastSig) return;
  lastSig = sig;
  $("#p-current", el).innerHTML = board.current ? currentCard(board.current) : "";
  $("#p-count", el).textContent = `${board.total_visits} in total`;
  $("#p-visits", el).innerHTML = board.visits.length
    ? board.visits.map(visitCard).join("")
    : `<div class="card empty"><strong>No earlier visits yet</strong>Remarks and medicines from finished visits will appear here.</div>`;
}

export default {
  title: "Patient portal",
  subtitle: "Your live token, doctor remarks and medicines from every visit.",

  async mount(root) {
    el = root;
    loggedIn = Boolean(patientSession.get());
    if (!loggedIn) return showLogin();
    await load();
  },

  refresh: () => (loggedIn ? load() : Promise.resolve()),
};
