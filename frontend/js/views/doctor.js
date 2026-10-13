import { api, session } from "../api.js";
import { $, countUp, enter, errorText, esc, toast, withBusy } from "../ui.js";

const when = (iso) =>
  new Date(iso).toLocaleString([], { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

let el, loggedIn, doctor, workspaceToken, nextToken, queueSig, searchTimer;

// The doctor's unsaved work. Kept at module level so switching tabs does not lose what was typed.
// { token, remarks, items: [{ medicine_id, name, quantity, instructions, stock }] }
let draft = null;

// ---------- Small renderers ----------

const stockChip = (stock) =>
  stock === 0 ? `<span class="stock out">Out of stock</span>` : `<span class="stock ok">${stock} in stock</span>`;

// Shown under each prescribed medicine so the doctor sees a shortage before the patient reaches the pharmacy.
function stockNote(item) {
  if (item.stock === undefined) return "";
  if (item.stock === 0) return `<span class="stock out">Out of stock</span>`;
  if (item.quantity > item.stock) return `<span class="stock low">Only ${item.stock} in stock</span>`;
  return `<span class="stock ok">${item.stock} in stock</span>`;
}

const queueRow = (t) => `
  <li class="${enter(`dq-${t.token}`)}">
    <span class="token-badge">${t.token}</span>
    <div class="who"><strong>${esc(t.patient_name)}</strong>
      <span class="muted">${t.age} yrs${t.complaint ? `, ${esc(t.complaint)}` : ""}</span></div>
    <span class="wait-no">#${t.position}</span>
  </li>`;

function medicineLine(i) {
  let given = "";
  if (i.dispensed_quantity !== null) {
    given = i.dispensed_quantity < i.quantity
      ? ` <span class="stock low">Given ${i.dispensed_quantity} of ${i.quantity}</span>`
      : ` <span class="stock ok">Given</span>`;
  }
  return `<li>${esc(i.medicine_name)} &times; ${i.quantity}${i.instructions ? `, ${esc(i.instructions)}` : ""}${given}</li>`;
}

const visitHtml = (v) => `
  <article class="visit">
    <header><strong>${when(v.registered_at)}</strong><span class="chip chip-soft">${esc(v.department_name)}</span></header>
    <p class="muted">${v.token}${v.doctor_name ? `, seen by ${esc(v.doctor_name)}` : ""}</p>
    ${v.complaint ? `<p><span class="muted">Came in for</span> ${esc(v.complaint)}</p>` : ""}
    <p class="remarks">${v.remarks ? esc(v.remarks) : `<span class="muted">No remarks were recorded.</span>`}</p>
    ${v.prescription.length ? `<ul class="visit-meds">${v.prescription.map(medicineLine).join("")}</ul>` : ""}
  </article>`;

const itemRow = (i) => `
  <li class="med-row ${enter(`med-${draft.token}-${i.medicine_id}`)}">
    <div class="med-name"><strong>${esc(i.name)}</strong><span data-note="${i.medicine_id}">${stockNote(i)}</span></div>
    <label class="qty-box">Quantity<input type="number" min="1" max="1000" value="${i.quantity}" data-qty="${i.medicine_id}"></label>
    <label class="qty-box">How to take<input maxlength="200" value="${esc(i.instructions)}" data-instr="${i.medicine_id}" placeholder="1 tablet twice a day for 5 days"></label>
    <button class="btn plain small" type="button" data-remove="${i.medicine_id}" aria-label="Remove ${esc(i.name)}">Remove</button>
  </li>`;

function renderItems() {
  $("#med-items", el).innerHTML = draft.items.length
    ? draft.items.map(itemRow).join("")
    : `<li class="muted empty-line">No medicines added yet.</li>`;
}

function workspaceHtml(c) {
  const t = c.token;
  const history = c.previous_visits.length
    ? c.previous_visits.map(visitHtml).join("")
    : `<p class="muted">No earlier visits on record for this phone number.</p>`;
  return `
    <article class="card work">
      <header class="work-head">
        <span class="token-badge">${t.token}</span>
        <div><h2>${esc(t.patient_name)}</h2>
          <span class="muted">${t.age} yrs</span> <span class="muted">${esc(c.patient_phone)}</span></div>
      </header>
      ${t.complaint ? `<p class="why"><span class="muted">Came in for</span><br>${esc(t.complaint)}</p>` : ""}
      <div class="work-cols">
        <div class="work-main">
          <label class="field">Consultation remarks
            <textarea id="remarks" rows="6" maxlength="4000" placeholder="Findings, diagnosis, advice">${esc(draft.remarks)}</textarea></label>
          <div class="field med-search">
            <label for="med-q">Prescribe medicine</label>
            <input id="med-q" type="search" autocomplete="off" placeholder="Search the OPD medicine list, e.g. para">
            <ul id="med-results" class="med-results" hidden></ul>
          </div>
          <ul id="med-items" class="med-items"></ul>
          <div class="actions">
            <button class="btn ghost" type="button" data-save>Save notes</button>
            <button class="btn" type="button" data-finish>Finish consultation</button>
          </div>
        </div>
        <aside class="history"><h3>Previous visits</h3>${history}</aside>
      </div>
    </article>`;
}

// ---------- Screens ----------

function showLogin() {
  loggedIn = false;
  doctor = null;
  el.innerHTML = `
    <section class="card doc-login">
      <h2>Doctor login</h2>
      <span class="muted">Use your name and registered medical ID.</span>
      <form class="form" id="login-form">
        <label class="field">Full name<input name="name" required autocomplete="off" placeholder="Dr. Asha Rao"></label>
        <label class="field">Medical ID<input name="medical_id" required autocomplete="off"></label>
        <button class="btn" type="submit">Log in</button>
      </form>
    </section>`;
  $("#login-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    try {
      const result = await withBusy($("button", form), () =>
        api.doctorLogin(form.name.value.trim(), form.medical_id.value.trim()));
      session.set(result.token);
      loggedIn = true;
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

function renderShell() {
  el.innerHTML = `
    <section class="card doc-head">
      <div><h2>${esc(doctor.name)}</h2>
        <span class="muted">${esc(doctor.department_name)}</span>
        <span class="muted">Medical ID ${esc(doctor.medical_id)}</span></div>
      <button class="btn plain" type="button" id="logout">Log out</button>
    </section>
    <div class="doc-grid">
      <section class="card doc-queue">
        <div class="doc-count"><b id="doc-waiting">0</b><span>patients waiting in ${esc(doctor.department_name)}</span></div>
        <button class="btn" type="button" id="call-next" disabled>No one is waiting</button>
        <ul class="doc-list" id="doc-list"></ul>
      </section>
      <section id="doc-work"></section>
    </div>`;

  $("#logout", el).addEventListener("click", async (e) => {
    await withBusy(e.currentTarget, () => api.doctorLogout().catch(() => {}));
    session.clear();
    draft = null;
    showLogin();
  });

  $("#call-next", el).addEventListener("click", async (e) => {
    try {
      await withBusy(e.currentTarget, () => api.setTokenStatus(nextToken, "in_consultation"));
      toast(`${nextToken} is now in consultation.`);
    } catch (error) {
      toast(errorText(error), "error");
    }
    await load().catch(() => {});
  });

  const work = $("#doc-work", el);
  work.addEventListener("input", onInput);
  work.addEventListener("click", onClick);
}

// ---------- Loading (runs on login, on page open, and every few seconds) ----------

async function load() {
  const root = el;
  let board;
  try {
    board = await api.doctorDashboard();
  } catch (error) {
    if (error.status !== 401) throw error;
    session.clear();
    if (root === el) {
      showLogin();
      toast("Your session has ended. Please log in again.", "error");
    }
    return;
  }
  if (root !== el) return; // the doctor moved to another tab

  if (!$("#doc-waiting", el)) {
    doctor = board.doctor;
    workspaceToken = undefined;
    queueSig = "";
    renderShell();
  }

  countUp($("#doc-waiting", el), board.waiting);
  nextToken = board.queue[0]?.token ?? null;
  const call = $("#call-next", el);
  call.disabled = Boolean(board.current) || !nextToken;
  call.textContent = board.current ? "Finish the current patient first" : nextToken ? `Call ${nextToken}` : "No one is waiting";

  const sig = JSON.stringify(board.queue);
  if (sig !== queueSig) {
    queueSig = sig;
    $("#doc-list", el).innerHTML = board.queue.length
      ? board.queue.map(queueRow).join("")
      : `<li class="empty muted">The waiting room is empty.</li>`;
  }

  // The workspace is rebuilt only when the patient changes, so polling never wipes what the doctor is typing.
  const currentToken = board.current?.token ?? null;
  if (currentToken !== workspaceToken) {
    workspaceToken = currentToken;
    try {
      await openWorkspace(board.current);
    } catch (error) {
      workspaceToken = undefined; // try again on the next refresh
      throw error;
    }
  }
}

async function openWorkspace(current) {
  const box = $("#doc-work", el);
  if (!current) {
    box.innerHTML = `<div class="card empty"><strong>No patient in consultation</strong>Call the next patient to start writing notes.</div>`;
    return;
  }
  const consultation = await api.consultation(current.token);
  if ($("#doc-work", el) !== box) return;
  if (draft?.token !== current.token) {
    draft = {
      token: current.token,
      remarks: consultation.remarks,
      items: consultation.prescription.map((i) => ({
        medicine_id: i.medicine_id,
        name: i.medicine_name,
        quantity: i.quantity,
        instructions: i.instructions ?? "",
      })),
    };
  }
  box.innerHTML = workspaceHtml(consultation);
  renderItems();
}

// ---------- Typing, searching, saving ----------

function onInput(e) {
  const target = e.target;
  if (target.id === "remarks") {
    draft.remarks = target.value;
  } else if (target.id === "med-q") {
    clearTimeout(searchTimer);
    const q = target.value.trim();
    searchTimer = setTimeout(() => runSearch(q), 250);
  } else if ("qty" in target.dataset) {
    const item = draft.items.find((i) => i.medicine_id === Number(target.dataset.qty));
    item.quantity = Math.floor(Number(target.value)) || 0;
    $(`[data-note="${item.medicine_id}"]`, el).innerHTML = stockNote(item);
  } else if ("instr" in target.dataset) {
    draft.items.find((i) => i.medicine_id === Number(target.dataset.instr)).instructions = target.value;
  }
}

async function runSearch(q) {
  const list = $("#med-results", el);
  if (!list) return;
  if (!q) {
    list.hidden = true;
    return;
  }
  try {
    const found = await api.searchMedicines(q);
    if ($("#med-q", el)?.value.trim() !== q) return; // the doctor kept typing
    list.innerHTML = found.length
      ? found.map((m) => `
          <li><button type="button" class="med-pick" data-add="${m.id}" data-name="${esc(m.name)}" data-stock="${m.stock}">
            <span>${esc(m.name)}</span>${stockChip(m.stock)}</button></li>`).join("")
      : `<li class="muted none">No medicine in the OPD list matches "${esc(q)}".</li>`;
    list.hidden = false;
  } catch (error) {
    if (error.status === 401) await load();
    else toast(errorText(error), "error");
  }
}

function onClick(e) {
  const add = e.target.closest("[data-add]");
  const remove = e.target.closest("[data-remove]");
  if (add) {
    const id = Number(add.dataset.add);
    if (draft.items.some((i) => i.medicine_id === id)) {
      toast(`${add.dataset.name} is already in the prescription.`, "error");
      return;
    }
    draft.items.push({ medicine_id: id, name: add.dataset.name, quantity: 1, instructions: "", stock: Number(add.dataset.stock) });
    $("#med-q", el).value = "";
    $("#med-results", el).hidden = true;
    renderItems();
  } else if (remove) {
    draft.items = draft.items.filter((i) => i.medicine_id !== Number(remove.dataset.remove));
    renderItems();
  } else if (e.target.closest("[data-save]")) {
    persist(e.target.closest("[data-save]"), false);
  } else if (e.target.closest("[data-finish]")) {
    persist(e.target.closest("[data-finish]"), true);
  }
}

const payload = () => ({
  remarks: draft.remarks,
  prescription: draft.items.map((i) => ({
    medicine_id: i.medicine_id,
    quantity: i.quantity,
    instructions: i.instructions.trim() || null,
  })),
});

/** Save the notes and prescription. When `finish` is true, also end the consultation. */
async function persist(button, finish) {
  const incomplete = draft.items.find((i) => !(i.quantity >= 1 && i.quantity <= 1000));
  if (incomplete) {
    toast(`Enter a quantity between 1 and 1000 for ${incomplete.name}.`, "error");
    return;
  }
  const token = draft.token;
  try {
    await withBusy(button, async () => {
      await api.saveConsultation(token, payload());
      if (!finish) return;
      await api.setTokenStatus(token, "prescribed");
      draft = null;
      workspaceToken = undefined;
      await load();
    });
    toast(finish ? `${token} is finished. Notes and prescription are saved.` : "Notes and prescription saved.");
  } catch (error) {
    if (error.status === 401) await load();
    else toast(errorText(error), "error");
  }
}

export default {
  title: "Doctor desk",
  subtitle: "See who is waiting, write consultation notes and prescribe with live stock.",

  async mount(root) {
    el = root;
    loggedIn = Boolean(session.get());
    doctor = null;
    if (!loggedIn) return showLogin();
    await load();
  },

  refresh: () => (loggedIn ? load() : Promise.resolve()),
};
