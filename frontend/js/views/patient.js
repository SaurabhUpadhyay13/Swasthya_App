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

let el, loggedIn, lastSig, deptSig, chosen, minutesPerPatient, countdown;

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
        <div><span class="muted">Your open visit, ${esc(t.department_name)}</span><h2>${headline(t)}</h2></div>
        <span class="chip s-${t.status}" style="margin-left:auto">${TOKEN_LABEL[t.status]}</span>
      </div>
      <div class="stats">
        <div class="stat"><span class="muted">Place in line</span><b>${t.position ? `#${t.position}` : "-"}</b></div>
        <div class="stat"><span class="muted">Estimated wait</span><b>${t.estimated_wait_minutes != null ? `${t.estimated_wait_minutes} min` : "-"}</b></div>
      </div>
      <div class="stepper" style="--p:${index / (STEPS.length - 1)}"><span class="fill"></span>${steps}</div>
      ${t.status === "waiting" ? `<div class="actions cancel-row"><button class="btn plain small" type="button" data-cancel>Cancel this token</button>
        <span class="muted">Picked the wrong department? Cancel, then register again.</span></div>` : ""}
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
    <header><strong>${when(v.registered_at)}</strong>
      <span>${v.status === "cancelled" ? `<span class="chip s-cancelled">Cancelled</span> ` : ""}<span class="chip chip-soft">${esc(v.department_name)}</span></span></header>
    <p class="muted">Token ${v.token}${v.doctor_name ? `, seen by ${esc(v.doctor_name)}` : ""}</p>
    ${v.complaint ? `<p><span class="muted">You came in for</span> ${esc(v.complaint)}</p>` : ""}
    ${v.status === "cancelled" ? "" : `<div><span class="muted">Doctor's remarks</span>
      <p class="remarks">${v.remarks ? esc(v.remarks) : `<span class="muted">No remarks were recorded.</span>`}</p></div>`}
    ${v.prescription.length ? `<div><span class="muted">Medicines</span><ul class="visit-meds">${v.prescription.map(medicineLine).join("")}</ul></div>` : ""}
  </article>`;

const deptOption = (d) => `
  <button type="button" class="dept-opt ${d.code === chosen ? "selected" : ""} ${d.now_serving ? "live" : ""}" data-dept="${d.code}" aria-pressed="${d.code === chosen}">
    <strong>${esc(d.name)}</strong>
    <span class="waiting"><b>${d.waiting}</b> waiting</span>
    <span class="muted">${d.waiting ? `about ${d.waiting * minutesPerPatient} min` : "No wait"}${d.now_serving ? `, now serving ${d.now_serving}` : ""}</span>
  </button>`;

const registerCard = () => `
  <section class="card reg-card">
    <h2>Register for a visit</h2>
    <p class="muted">Choose a department. The numbers update live, so you can pick the shortest queue that fits your problem.</p>
    <div class="dept-pick" id="p-depts"></div>
    <label class="field">Reason for visit (optional)
      <input id="p-complaint" maxlength="300" autocomplete="off" placeholder="For example: fever for 3 days"></label>
    <button class="btn" type="button" id="p-register" disabled>Choose a department</button>
  </section>`;

function renderDepartments(departments) {
  $("#p-depts", el).innerHTML = departments.map(deptOption).join("");
  const button = $("#p-register", el);
  const picked = departments.find((d) => d.code === chosen);
  button.disabled = !picked;
  button.textContent = picked ? `Get my token in ${picked.name}` : "Choose a department";
}

// ---------- Login, sign-up and first-time code screens ----------

function stopCountdown() {
  clearInterval(countdown);
  countdown = null;
}

const FORMS = {
  login: {
    title: "Patient login",
    sub: "Use the phone number you registered with and your password.",
    switches: [["signup", "New here? Create your account"], ["activate", "Visited the hospital before? Use a code from the OPD desk"]],
  },
  signup: {
    title: "Create your account",
    sub: "For patients who have never registered here. We will show you a short code to type back.",
    switches: [["login", "I already have a password"], ["activate", "Visited the hospital before? Use a code from the OPD desk"]],
  },
  activate: {
    title: "Use a code from the OPD desk",
    sub: "If you have visited before, ask the OPD desk for a one-time code, then choose your own password.",
    switches: [["login", "I already have a password"], ["signup", "I have never registered here"]],
  },
};

const switchButtons = (mode) =>
  FORMS[mode].switches.map(([to, label]) => `<button class="btn plain" type="button" data-mode="${to}">${label}</button>`).join("");

function frame(mode, body) {
  el.innerHTML = `
    <section class="card acc-login">
      <h2>${FORMS[mode].title}</h2>
      <span class="muted">${FORMS[mode].sub}</span>
      ${body}
      <div class="switches">${switchButtons(mode)}</div>
    </section>`;
  el.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => showLogin(b.dataset.mode)));
}

const phoneOk = (phone) => /^\d{10}$/.test(phone) || (toast("Enter your 10-digit phone number.", "error"), false);

async function signedIn(result) {
  patientSession.set(result.token);
  loggedIn = true;
  lastSig = deptSig = "";
  await load();
}

function showLogin(mode = "login") {
  loggedIn = false;
  stopCountdown();
  if (mode === "signup") return signupStepOne();

  const first = mode === "activate";
  frame(mode, `
    <form class="form" id="login-form" novalidate>
      <label class="field">Phone number
        <input name="phone" required inputmode="numeric" maxlength="10" autocomplete="username" placeholder="10 digits"></label>
      ${first ? `<label class="field">Code from the OPD desk
        <input name="code" required inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="6 digits"></label>` : ""}
      <label class="field">${first ? "Choose a password (8 or more characters)" : "Password"}
        <input name="password" type="password" required maxlength="72" autocomplete="${first ? "new-password" : "current-password"}"></label>
      <button class="btn" type="submit">${first ? "Create password and log in" : "Log in"}</button>
    </form>`);

  $("#login-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.currentTarget;
    const phone = f.phone.value.trim();
    if (!phoneOk(phone)) return;
    try {
      const result = await withBusy($("button", f), () =>
        first ? api.patientActivate(phone, f.code.value.trim(), f.password.value) : api.patientLogin(phone, f.password.value));
      await signedIn(result);
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

// New patient, step 1: tell us who you are
function signupStepOne(prefill = {}) {
  frame("signup", `
    <form class="form" id="signup-form" novalidate>
      <label class="field">Full name
        <input name="name" required minlength="2" maxlength="100" autocomplete="name" value="${esc(prefill.name ?? "")}"></label>
      <div class="form-row">
        <label class="field">Age
          <input name="age" type="number" min="0" max="120" required value="${esc(prefill.age ?? "")}"></label>
        <label class="field">Phone number
          <input name="phone" required inputmode="numeric" maxlength="10" autocomplete="username" placeholder="10 digits" value="${esc(prefill.phone ?? "")}"></label>
      </div>
      <button class="btn" type="submit">Get my code</button>
    </form>`);

  $("#signup-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.currentTarget;
    const details = { name: f.name.value.trim(), age: Number(f.age.value), phone: f.phone.value.trim() };
    if (!phoneOk(details.phone)) return;
    try {
      const started = await withBusy($("button", f), () => api.patientSignupStart(details.phone, details.name, details.age));
      signupStepTwo(details, started);
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

// New patient, step 2: type the code shown on this screen (60 seconds) and choose a password
function signupStepTwo(details, started) {
  frame("signup", `
    <div class="code-box enter">
      <span class="muted">Your code</span>
      <strong class="code">${started.code.slice(0, 3)} ${started.code.slice(3)}</strong>
      <span class="muted" id="count" aria-live="off"></span>
    </div>
    <form class="form" id="signup-form" novalidate>
      <label class="field">Type the code above
        <input name="code" required inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="6 digits"></label>
      <label class="field">Choose a password (8 or more characters)
        <input name="password" type="password" required maxlength="72" autocomplete="new-password"></label>
      <button class="btn" type="submit">Create account and log in</button>
    </form>
    <button class="btn ghost" type="button" id="again" hidden>Code expired. Get a new code</button>`);

  const deadline = Date.now() + started.expires_in_seconds * 1000;
  const form = $("#signup-form", el);
  const tick = () => {
    const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    $("#count", el).textContent = left > 0 ? `Expires in ${left} seconds` : "This code has expired.";
    if (left === 0) {
      stopCountdown();
      form.querySelectorAll("input, button").forEach((n) => (n.disabled = true));
      $("#again", el).hidden = false;
    }
  };
  tick();
  countdown = setInterval(tick, 250);
  $("input[name=code]", el).focus();
  $("#again", el).addEventListener("click", () => {
    stopCountdown();
    signupStepOne(details);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const result = await withBusy($("button[type=submit]", form), () =>
        api.patientSignup(details.phone, form.code.value.trim(), form.password.value));
      stopCountdown();
      await signedIn(result);
      toast("Your account is ready.");
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

// ---------- Dashboard ----------

function renderShell(patient) {
  lastSig = deptSig = "";
  chosen = null;
  el.innerHTML = `
    <section class="card acc-head">
      <div><h2>${esc(patient.name)}</h2><span class="muted">${patient.age} yrs</span> <span class="muted">${esc(patient.phone)}</span></div>
      <button class="btn plain" type="button" id="logout">Log out</button>
    </section>
    <div id="p-current"></div>
    <div id="p-register-box"></div>
    <div class="section-head"><h2>Your visits</h2><span class="muted" id="p-count"></span></div>
    <div class="visit-list" id="p-visits"></div>`;

  $("#logout", el).addEventListener("click", async (e) => {
    await withBusy(e.currentTarget, () => api.patientLogout().catch(() => {}));
    patientSession.clear();
    showLogin();
  });

  $("#p-current", el).addEventListener("click", async (e) => {
    const button = e.target.closest("[data-cancel]");
    if (!button || !confirm("Cancel your token? You can register again afterwards.")) return;
    try {
      await withBusy(button, () => api.patientCancel());
      toast("Your token is cancelled.");
    } catch (error) {
      toast(errorText(error), "error");
    }
    await load().catch(() => {});
  });

  const box = $("#p-register-box", el);
  box.addEventListener("click", async (e) => {
    const option = e.target.closest("[data-dept]");
    if (option) {
      chosen = option.dataset.dept;
      box.querySelectorAll("[data-dept]").forEach((n) => {
        n.classList.toggle("selected", n.dataset.dept === chosen);
        n.setAttribute("aria-pressed", n.dataset.dept === chosen);
      });
      const button = $("#p-register", box);
      button.disabled = false;
      button.textContent = `Get my token in ${option.querySelector("strong").textContent}`;
      return;
    }
    const register = e.target.closest("#p-register");
    if (!register || !chosen) return;
    try {
      const token = await withBusy(register, () => api.patientRegister(chosen, $("#p-complaint", box).value.trim() || null));
      toast(`Your token is ${token.token}.`);
    } catch (error) {
      toast(errorText(error), "error"); // for example: the OPD desk registered you a moment ago
    }
    await load().catch(() => {});
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
  minutesPerPatient = board.minutes_per_patient;

  const sig = JSON.stringify([board.current, board.visits]);
  if (sig !== lastSig) {
    const hadToken = lastSig ? JSON.parse(lastSig)[0] !== null : null;
    lastSig = sig;
    $("#p-current", el).innerHTML = board.current ? currentCard(board.current) : "";
    $("#p-count", el).textContent = `${board.total_visits} in total`;
    $("#p-visits", el).innerHTML = board.visits.length
      ? board.visits.map(visitCard).join("")
      : `<div class="card empty"><strong>No earlier visits yet</strong>Remarks and medicines from finished visits will appear here.</div>`;

    // The register form exists only while there is no open token. It is rebuilt only when that changes,
    // so live polling never wipes what the patient has typed or picked.
    const box = $("#p-register-box", el);
    if (board.current) {
      box.innerHTML = "";
      chosen = null;
    } else if (!box.firstElementChild || hadToken) {
      box.innerHTML = registerCard();
      deptSig = "";
    }
  }

  const dsig = JSON.stringify(board.departments);
  if (!board.current && dsig !== deptSig) {
    deptSig = dsig;
    renderDepartments(board.departments);
  }
}

export default {
  title: "Patient portal",
  subtitle: "Register for a visit, follow your token and see your records.",

  async mount(root) {
    stopCountdown();
    el = root;
    loggedIn = Boolean(patientSession.get());
    if (!loggedIn) return showLogin();
    await load();
  },

  refresh: () => (loggedIn ? load() : Promise.resolve()),
};
