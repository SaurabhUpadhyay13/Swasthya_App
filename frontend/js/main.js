import { currentRole, signOut } from "./api.js";
import { icon } from "./icons.js";
import { $, errorText, toast } from "./ui.js";
import login from "./views/login.js";
import admin from "./views/admin.js";
import people from "./views/people.js";
import stock from "./views/stock.js";
import track from "./views/tracker.js";
import doctor from "./views/doctor.js";
import staff from "./views/staff.js";
import patient from "./views/patient.js";

const routes = { login, admin, people, stock, track, doctor, staff, patient };
const POLL_MS = 5000;
let current = null;

// Who may open what. Each role sees only its own pages; a visitor who is not signed in sees only the
// login screen and the sign-in form of each role (those views show their form until someone logs in).
const SIGN_IN_PAGES = ["login", "admin", "staff", "doctor", "patient"];
const PAGES = {
  admin: ["admin", "people", "stock", "track"],
  staff: ["staff", "track"],
  doctor: ["doctor"],
  patient: ["patient"],
};
const HOME = { admin: "admin", staff: "staff", doctor: "doctor", patient: "patient" };
const ROLE_NAME = { admin: "Administrator", staff: "OPD staff", doctor: "Doctor", patient: "Patient" };

// Static icons in the shell
document.querySelectorAll("[data-icon]").forEach((el) => (el.innerHTML = icon[el.dataset.icon]));
$("#brand-mark").innerHTML = icon.cross;
$("#auth-mark").innerHTML = icon.cross;

/** Menu and layout for whoever is signed in (or the bare login layout for nobody). */
function applyRole(role) {
  document.body.classList.toggle("signed-out", !role);
  document.body.dataset.page = location.hash.replace(/^#\//, "").split("/")[0];
  const allowed = role ? PAGES[role] : [];
  document.querySelectorAll("[data-route]").forEach((a) => (a.hidden = !allowed.includes(a.dataset.route)));
  $("#who").hidden = !role;
  if (role) $("#who-role").textContent = ROLE_NAME[role];
  $(".brand").setAttribute("href", `#/${role ? HOME[role] : "login"}`);
}

async function navigate() {
  const role = currentRole();
  const [name, param] = location.hash.replace(/^#\//, "").split("/");
  const allowed = role ? PAGES[role] : SIGN_IN_PAGES;
  if (!allowed.includes(name)) {
    // Unknown page, or a page for another role: go to this person's home (or the login screen).
    location.replace(`#/${role ? HOME[role] : "login"}`);
    return;
  }
  const view = routes[name];

  applyRole(role);
  document.querySelectorAll("[data-route]").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
  $("#page-title").textContent = view.title;
  $("#page-sub").textContent = view.subtitle;
  document.title = `${view.title} - Swasthya AI`;
  window.scrollTo(0, 0);

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

// Signing in or out (or a session ending) changes what this person may see.
let shownRole = currentRole();
window.addEventListener("auth-change", () => {
  const role = currentRole();
  if (role === shownRole) return;
  shownRole = role;
  applyRole(role);
  if (!role) {
    location.hash = "#/login"; // signed out: back to the start
  } else if (!PAGES[role].includes(location.hash.replace(/^#\//, "").split("/")[0])) {
    location.hash = `#/${HOME[role]}`;
  }
});

const signOutButton = $("#sign-out");
signOutButton.addEventListener("click", async () => {
  signOutButton.disabled = true; // not e.currentTarget: the browser clears it after the first await
  try {
    await signOut();
  } finally {
    signOutButton.disabled = false;
  }
});

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
