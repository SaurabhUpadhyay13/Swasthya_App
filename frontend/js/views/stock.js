import { api } from "../api.js";
import { icon } from "../icons.js";
import { $, enter, errorText, esc, nextStep, timeAgo, toast, withBusy, PRIORITY_LABEL, WO_ACTION, WO_FLOW, WO_LABEL } from "../ui.js";

let el, orders, lastSig;
const summaries = new Map(); // work order id -> { text, model }
const summarizing = new Set();

function summaryBlock(id) {
  if (summarizing.has(id)) return `<div class="summary loading"><span class="shimmer"></span><span class="shimmer short"></span></div>`;
  const s = summaries.get(id);
  return s
    ? `<div class="summary ${enter(`sum-${id}`)}">${icon.sparkle}<p>${esc(s.text)}</p><small>Summarised by ${esc(s.model)}</small></div>`
    : "";
}

function card(o) {
  const next = nextStep(WO_FLOW, o.status);
  return `
    <article class="wo p-${o.priority} ${enter(`wo-${o.id}-${o.status}`)}">
      <header><span class="badge p-${o.priority}">${PRIORITY_LABEL[o.priority]}</span><span class="muted">${timeAgo(o.created_at)}</span></header>
      <h4>${esc(o.medicine_name)} <span class="muted">#${o.id}</span></h4>
      <p class="qty"><b>${o.quantity_needed.toLocaleString()}</b> needed</p>
      <p class="desc">${esc(o.description)}</p>
      ${summaryBlock(o.id)}
      <footer>
        <div class="actions">
          <button class="btn ghost small" data-summarize="${o.id}" ${summarizing.has(o.id) ? "disabled" : ""}>${icon.sparkle}Summarize</button>
          ${next ? `<button class="btn small" data-advance="${o.id}" data-to="${next}">${WO_ACTION[o.status]}</button>` : ""}
        </div>
      </footer>
    </article>`;
}

function renderBoard() {
  $("#pipeline", el).innerHTML = WO_FLOW.map((status) => {
    const items = orders.filter((o) => o.status === status);
    return `
      <section class="col col-${status}">
        <header><h3><span>${WO_LABEL[status]}</span></h3><span class="count">${items.length}</span></header>
        <div class="col-body">${items.map(card).join("") || `<div class="empty muted">Nothing here</div>`}</div>
      </section>`;
  }).join("");
}

async function load() {
  const root = el;
  const fresh = await api.workOrders();
  if (root !== el) return;
  const sig = JSON.stringify(fresh);
  if (sig === lastSig) return;
  lastSig = sig;
  orders = fresh;
  renderBoard();
}

function wire() {
  const panel = $("#new-panel", el);
  const form = $("#new-form", el);

  $("#toggle-new", el).addEventListener("click", () => {
    panel.classList.toggle("open");
    if (panel.classList.contains("open")) setTimeout(() => form.medicine_name.focus(), 300);
  });
  $("#cancel-new", el).addEventListener("click", () => panel.classList.remove("open"));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    try {
      await withBusy($("button[type=submit]", form), () =>
        api.createWorkOrder({ ...data, quantity_needed: Number(data.quantity_needed) }));
      form.reset();
      panel.classList.remove("open");
      toast("Work order created.");
      lastSig = null;
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });

  $("#pipeline", el).addEventListener("click", async (e) => {
    const advance = e.target.closest("[data-advance]");
    const summarize = e.target.closest("[data-summarize]");
    try {
      if (advance) {
        await withBusy(advance, () => api.setWorkOrderStatus(advance.dataset.advance, advance.dataset.to));
        toast(`Work order #${advance.dataset.advance} is now ${WO_LABEL[advance.dataset.to].toLowerCase()}.`);
        await load();
      } else if (summarize) {
        const id = Number(summarize.dataset.summarize);
        summarizing.add(id);
        renderBoard();
        try {
          const result = await api.summarize(id);
          summaries.set(id, { text: result.summary, model: result.model });
        } finally {
          summarizing.delete(id);
          renderBoard();
        }
      }
    } catch (error) {
      toast(errorText(error), "error");
      load().catch(() => {});
    }
  });
}

export default {
  title: "Medicine stock",
  subtitle: "Track each replenishment from stock-out to completed.",

  async mount(root) {
    el = root;
    lastSig = "";
    orders = [];
    el.innerHTML = `
      <div class="section-head" style="margin-top:0">
        <h2>Replenishment pipeline</h2>
        <button class="btn" id="toggle-new">${icon.plus}New request</button>
      </div>
      <div class="reveal" id="new-panel"><div>
        <form class="card form" id="new-form">
          <div class="form-row">
            <label class="field">Medicine<input name="medicine_name" required minlength="2" maxlength="120" placeholder="Paracetamol 500mg" autocomplete="off"></label>
            <div class="form-row">
              <label class="field">Quantity<input name="quantity_needed" type="number" min="1" max="100000" required></label>
              <label class="field">Priority<select name="priority"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option><option value="critical">Critical</option></select></label>
            </div>
          </div>
          <label class="field">What happened?<textarea name="description" required minlength="10" maxlength="2000" placeholder="Why is this needed? Mention pending prescriptions or days of stock left."></textarea></label>
          <div class="actions"><button class="btn" type="submit">Create work order</button><button class="btn plain" type="button" id="cancel-new">Cancel</button></div>
        </form>
      </div></div>
      <div class="pipeline" id="pipeline"></div>`;
    wire();
    await load();
  },

  refresh: () => load(),
};
