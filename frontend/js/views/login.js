import { icon } from "../icons.js";
import { esc } from "../ui.js";

// The first screen. Everyone signs in from here; each role then sees only its own pages.
const ROLES = [
  { route: "patient", icon: "heart", title: "Patient", text: "Get a token, watch the queue live and see your visits and medicines." },
  { route: "doctor", icon: "pulse", title: "Doctor", text: "Call in patients, write remarks and prescribe with live medicine stock." },
  { route: "staff", icon: "shield", title: "OPD staff", text: "Register walk-in patients and run the department queues." },
  { route: "admin", icon: "lock", title: "Administrator", text: "Hospital-wide view of doctors, queues and pharmacy, and who can log in." },
];

export default {
  title: "Welcome",
  subtitle: "Sign in to continue.",

  async mount(root) {
    root.innerHTML = `
      <section class="welcome">
        <span class="eyebrow">Hospital OPD and pharmacy</span>
        <h2>Welcome to Swasthya AI</h2>
        <p>Choose how you want to sign in.</p>
        <div class="role-grid">
          ${ROLES.map((r, i) => `
            <a class="role-card" href="#/${r.route}" style="--i:${i}">
              <span class="role-icon">${icon[r.icon]}</span>
              <strong>${esc(r.title)}</strong>
              <span class="muted">${esc(r.text)}</span>
              <span class="role-go">Sign in ${icon.chevronRight}</span>
            </a>`).join("")}
        </div>
        <p class="muted fine">New patient? Choose Patient and create your account in under a minute.
          Doctor, OPD staff and administrator accounts are created by the hospital administrator.</p>
      </section>`;
  },
};
