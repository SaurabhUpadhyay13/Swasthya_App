import { api } from "../api.js";
import { $, enter, errorText, esc, nextStep, openModal, toast, withBusy, TOKEN_ACTION, TOKEN_FLOW, TOKEN_LABEL } from "../ui.js";

let el, state, last;

const row = (t, doctorBusy) => {
  const next = nextStep(TOKEN_FLOW, t.status);
  const blocked = t.status === "waiting" && doctorBusy;
  return `
    <li class="${t.status} ${enter(`t-${t.token}-${t.status}`)}">
      <span class="token-badge">${t.token}</span>
      <div class="who"><strong>${esc(t.patient_name)}</strong>
        <span class="muted">${t.age} yrs${t.complaint ? `, ${esc(t.complaint)}` : ""}</span></div>
      <div class="wait">${t.position ? `<b>#${t.position}</b><span class="muted">about ${t.estimated_wait_minutes} min</span>` : ""}</div>
      <span class="chip s-${t.status}">${TOKEN_LABEL[t.status]}</span>
      <div class="row-actions">
      ${t.status === "waiting" ? `<button class="btn plain small" data-cancel="${t.token}" aria-label="Cancel ${t.token}">Cancel</button>` : ""}
      <button class="btn small" data-advance="${t.token}" data-to="${next}" ${blocked ? 'disabled title="The doctor is with another patient. Use the button above, or mark that patient prescribed first."' : ""}>${TOKEN_ACTION[t.status]}</button>
      </div>
    </li>`;
};

function renderTabs() {
  // With many departments, tabs show only the busy ones (and the one being viewed); the select shows all.
  $("#tabs", el).innerHTML = state.depts
    .filter((d) => d.waiting > 0 || d.code === state.dept)
    .map((d) => `<button class="tab ${d.code === state.dept ? "active" : ""}" data-dept="${d.code}">${esc(d.name)}<b>${d.waiting}</b></button>`)
    .join("");
}

function renderBoard() {
  const dept = state.depts.find((d) => d.code === state.dept);
  const active = state.tokens.filter((t) => t.status !== "completed" && t.status !== "cancelled");
  const serving = state.tokens.find((t) => t.status === "in_consultation");
  const nextUp = state.tokens.find((t) => t.status === "waiting");

  // One obvious button for the doctor's workflow. It finishes the current patient and calls the next one.
  const cycleLabel = serving
    ? nextUp ? `Finish ${serving.token} and call ${nextUp.token}` : `Mark ${serving.token} prescribed`
    : nextUp ? `Call ${nextUp.token}` : "";

  $("#serving", el).innerHTML = `
    <article class="card serving-card">
      <div class="ring ${serving ? "live" : "idle"}">${serving ? serving.token : "Free"}</div>
      <div>
        <span class="muted">${esc(dept?.name ?? "")}</span>
        <h3>${serving ? `Now serving ${esc(serving.patient_name)}` : "No one is with the doctor"}</h3>
      </div>
      <div class="next" style="white-space:nowrap"><span class="muted">Next in line</span>
        <h3>${nextUp ? nextUp.token : "Nobody waiting"}</h3></div>
      ${cycleLabel ? `<button class="btn" data-cycle>${esc(cycleLabel)}</button>` : ""}
    </article>`;

  $("#list", el).innerHTML = active.length
    ? `<ul class="rows">${active.map((t) => row(t, Boolean(serving))).join("")}</ul>`
    : `<div class="empty"><strong>This queue is empty</strong>Register a patient to issue the first token.</div>`;
}

async function load() {
  const root = el;
  const [depts, tokens] = await Promise.all([api.departments(), api.tokens(state.dept)]);
  if (root !== el) return;
  if (!depts.some((d) => d.code === state.dept)) state.dept = depts[0].code;

  const select = $("#dept-select", el);
  const view = $("#view-dept", el);
  if (!select.options.length) {
    const options = depts.map((d) => `<option value="${d.code}">${esc(d.name)}</option>`).join("");
    select.innerHTML = options;
    view.innerHTML = options;
    select.value = state.dept;
  }
  view.value = state.dept;
  const sig = JSON.stringify([depts, tokens, state.dept]);
  if (sig === last) return;
  last = sig;
  state.depts = depts;
  state.tokens = tokens;
  renderTabs();
  renderBoard();
}

function showTicket(t) {
  const close = openModal(`
    <div class="ticket-wrap"><div class="ticket">
      <div class="ticket-top">
        <span class="muted">Your OPD token</span>
        <div class="ticket-num">${t.token}</div>
        <div>${esc(t.department_name)}</div>
      </div>
      <div class="ticket-bottom">
        <div class="ticket-stats">
          <div><b>#${t.position}</b><span class="muted">Place in line</span></div>
          <div><b>${t.estimated_wait_minutes}</b><span class="muted">Minutes, estimated</span></div>
        </div>
        <div class="ticket-actions">
          <button class="btn" data-track>Track this token</button>
          <button class="btn plain" data-close>Done</button>
        </div>
      </div>
    </div></div>`);
  $("[data-track]", $("#modal-root")).addEventListener("click", () => {
    close();
    location.hash = `#/track/${t.token}`;
  });
}

function wire() {
  $("#register-form", el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const body = {
      patient_name: data.patient_name,
      age: Number(data.age),
      phone: data.phone.trim(),
      department: data.department,
      complaint: data.complaint.trim() || null,
    };
    try {
      const token = await withBusy($("button[type=submit]", form), () => api.register(body));
      form.reset();
      form.department.value = token.department;
      state.dept = token.department;
      last = null;
      showTicket(token);
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });

  $("#view-dept", el).addEventListener("change", (e) => {
    state.dept = e.target.value;
    last = null;
    load().catch((error) => toast(errorText(error), "error"));
  });

  $("#tabs", el).addEventListener("click", (e) => {
    const tab = e.target.closest("[data-dept]");
    if (!tab) return;
    state.dept = tab.dataset.dept;
    last = null;
    load().catch((error) => toast(errorText(error), "error"));
  });

  $("#serving", el).addEventListener("click", async (e) => {
    const button = e.target.closest("[data-cycle]");
    if (!button) return;
    const serving = state.tokens.find((t) => t.status === "in_consultation");
    const nextUp = state.tokens.find((t) => t.status === "waiting");
    try {
      await withBusy(button, async () => {
        if (serving) await api.setTokenStatus(serving.token, "prescribed");
        if (nextUp) await api.setTokenStatus(nextUp.token, "in_consultation");
      });
      toast(nextUp ? `${nextUp.token} is now in consultation.` : `${serving.token} is now prescribed.`);
    } catch (error) {
      toast(errorText(error), "error");
    }
    await load().catch(() => {});
  });

  $("#list", el).addEventListener("click", async (e) => {
    const cancel = e.target.closest("[data-cancel]");
    if (cancel) {
      if (!confirm(`Cancel token ${cancel.dataset.cancel}? The patient can then register again.`)) return;
      try {
        await withBusy(cancel, () => api.setTokenStatus(cancel.dataset.cancel, "cancelled"));
        toast(`${cancel.dataset.cancel} is cancelled.`);
        await load();
      } catch (error) {
        toast(errorText(error), "error");
        load().catch(() => {});
      }
      return;
    }
    const button = e.target.closest("[data-advance]");
    if (!button) return;
    try {
      await withBusy(button, () => api.setTokenStatus(button.dataset.advance, button.dataset.to));
      toast(`${button.dataset.advance} is now ${TOKEN_LABEL[button.dataset.to].toLowerCase()}.`);
      await load();
    } catch (error) {
      toast(errorText(error), "error");
      load().catch(() => {});
    }
  });
}

export default {
  // Not a page of its own any more: the OPD staff desk mounts this under its dashboard.
  title: "OPD queue",
  subtitle: "Register walk-in patients and move them from waiting room to pharmacy.",

  async mount(root, param) {
    el = root;
    last = "";
    state = { depts: [], dept: param || "general_medicine", tokens: [] };
    el.innerHTML = `
      <div class="queue-layout">
        <section class="card register">
          <h2>Register a walk-in patient</h2>
          <span class="muted">For patients who come to the desk. A token is issued as soon as you save.</span>
          <form class="form" id="register-form">
            <label class="field">Patient name<input name="patient_name" required minlength="2" maxlength="100" autocomplete="off"></label>
            <div class="form-row">
              <label class="field">Age<input name="age" type="number" min="0" max="120" required></label>
              <label class="field">Phone number<input name="phone" required inputmode="numeric" pattern="[0-9]{10}" maxlength="10" placeholder="10 digits" title="10-digit mobile number, no spaces or +91"></label>
            </div>
            <label class="field">Department<select name="department" id="dept-select" required></select></label>
            <label class="field">Reason for visit (optional)<input name="complaint" maxlength="300" autocomplete="off"></label>
            <button class="btn" type="submit">Issue token</button>
          </form>
        </section>
        <section>
          <label class="field view-dept">Viewing queue of<select id="view-dept"></select></label>
          <div class="tabs" id="tabs"></div>
          <div id="serving"></div>
          <section class="card" id="list"></section>
        </section>
      </div>`;
    wire();
    await load();
  },

  refresh: () => load(),
};
