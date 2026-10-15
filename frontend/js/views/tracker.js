import { api } from "../api.js";
import { icon } from "../icons.js";
import { $, errorText, esc, withBusy, TOKEN_LABEL } from "../ui.js";

const STEPS = [
  { status: "waiting", label: "In queue" },
  { status: "in_consultation", label: "Consultation" },
  { status: "prescribed", label: "Prescription" },
  { status: "pharmacy", label: "Pharmacy" },
  { status: "completed", label: "Done" },
];

let el, tokenId, shownFor, lastHtml, lastProgress;

function headline(t) {
  switch (t.status) {
    case "waiting":
      return t.position === 1 ? "You are next. Please stay close to the consultation room." : `${t.position - 1} patients are ahead of you.`;
    case "in_consultation": return "It is your turn. Please go in to see the doctor.";
    case "prescribed": return "Your prescription is ready. Please walk to the pharmacy.";
    case "pharmacy": return "Collect your medicines at the pharmacy counter.";
    case "cancelled": return "This token was cancelled. Register again if you still need to be seen.";
    default: return "All done. Wishing you good health.";
  }
}

function result(t, dept) {
  const index = STEPS.findIndex((s) => s.status === t.status);
  const firstName = esc(t.patient_name.split(" ")[0]); // other patients may be watching a shared screen
  const steps = STEPS.map((s, i) => `
    <div class="step ${i < index ? "done" : ""} ${i === index ? "current" : ""}">
      <i>${i <= index ? icon.check : ""}</i><span>${s.label}</span>
    </div>`).join("");

  return `
    <article class="card track-card">
      <div class="track-head">
        <span class="token-badge" style="font-size:22px;padding:12px 18px">${t.token}</span>
        <div>
          <span class="muted">${firstName}, ${esc(t.department_name)}</span>
          <h2>${headline(t)}</h2>
        </div>
        <span class="chip s-${t.status}" style="margin-left:auto">${TOKEN_LABEL[t.status]}</span>
      </div>
      <div class="stats">
        <div class="stat"><span class="muted">Place in line</span><b>${t.position ? `#${t.position}` : "-"}</b></div>
        <div class="stat"><span class="muted">Estimated wait</span><b>${t.estimated_wait_minutes != null ? `${t.estimated_wait_minutes} min` : "-"}</b></div>
        <div class="stat"><span class="muted">Now serving in ${esc(t.department_name)}</span><b>${dept?.now_serving ?? "None"}</b></div>
      </div>
      ${index < 0 ? "" : `<div class="stepper" style="--p:${index / (STEPS.length - 1)}"><span class="fill"></span>${steps}</div>`}
    </article>`;
}

async function lookup(id, { silent = false } = {}) {
  const root = el;
  const out = $("#track-result", el);
  try {
    const [token, depts] = await Promise.all([api.token(id), api.departments()]);
    if (root !== el) return;
    const dept = depts.find((d) => d.code === token.department);
    const html = result(token, dept);
    if (shownFor === id && html === lastHtml) return;
    out.innerHTML = html;
    const stepper = $(".stepper", out);
    const target = stepper?.style.getPropertyValue("--p");
    if (stepper && shownFor === id) {
      // Same token, new status: start from the old progress so the bar slides forward
      stepper.style.setProperty("--p", lastProgress);
      stepper.offsetWidth; // force reflow
      stepper.style.setProperty("--p", target);
    }
    shownFor = id;
    lastHtml = html;
    lastProgress = target;
  } catch (error) {
    if (silent || root !== el) return;
    shownFor = null;
    out.innerHTML = `<div class="card track-card empty"><strong>${esc(errorText(error))}</strong>Check the number on your slip and try again.</div>`;
  }
}

export default {
  title: "Track a token",
  subtitle: "Patients can follow their place in line and see what to do next.",

  async mount(root, param) {
    el = root;
    shownFor = null;
    tokenId = param?.toUpperCase() ?? null;
    el.innerHTML = `
      <form class="track-form" id="track-form">
        <label class="field">Token number<input name="token" placeholder="GM-004" autocomplete="off" required></label>
        <button class="btn" type="submit">Track token</button>
      </form>
      <div id="track-result"><div class="card track-card empty"><strong>Enter your token number</strong>It is printed on your OPD slip, for example GM-004.</div></div>`;
    const input = $("input", el);
    input.value = tokenId ?? "";
    $("#track-form", el).addEventListener("submit", async (e) => {
      e.preventDefault();
      tokenId = input.value.trim().toUpperCase();
      history.replaceState(null, "", `#/track/${tokenId}`);
      await withBusy($("button", e.currentTarget), () => lookup(tokenId));
    });
    if (tokenId) await lookup(tokenId);
  },

  async refresh() {
    if (tokenId) await lookup(tokenId, { silent: true });
  },
};
