import { icon } from "./icons.js";
import { $, errorText, toast } from "./ui.js";
import dashboard from "./views/dashboard.js";
import track from "./views/tracker.js";
import stock from "./views/stock.js";
import doctor from "./views/doctor.js";
import staff from "./views/staff.js";
import patient from "./views/patient.js";

const routes = { dashboard, track, stock, doctor, staff, patient };
const POLL_MS = 5000;
let current = null;

// Static icons in the shell
document.querySelectorAll("[data-icon]").forEach((el) => (el.innerHTML = icon[el.dataset.icon]));
$("#brand-mark").innerHTML = icon.cross;

async function navigate() {
  const [name, param] = location.hash.replace(/^#\//, "").split("/");
  const key = routes[name] ? name : "dashboard";
  const view = routes[key];

  document.querySelectorAll("[data-route]").forEach((a) => a.classList.toggle("active", a.dataset.route === key));
  $("#page-title").textContent = view.title;
  $("#page-sub").textContent = view.subtitle;
  document.title = `${view.title} - CareFlow`;

  // A fresh container per visit: late responses from the previous view can't touch the new one.
  const container = document.createElement("div");
  $("#view").replaceChildren(container);
  current = view;
  try {
    await view.mount(container, param);
  } catch (error) {
    toast(errorText(error), "error");
  }
}

function tickClock() {
  $("#clock").textContent = new Date().toLocaleString([], { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

window.addEventListener("hashchange", navigate);
setInterval(() => {
  if (!document.hidden) current?.refresh?.().catch(() => {});
}, POLL_MS);
setInterval(tickClock, 30_000);

tickClock();
navigate();
