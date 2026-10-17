import { api } from "../api.js";
import { $, enter, errorText, esc, timeAgo, toast, withBusy } from "../ui.js";

// Administrator page: every doctor with their activity, the OPD staff, and forms to add either.
let el, sigs, doctors, query;

const doctorRow = (d) => `
  <tr class="${enter(`pd-${d.id}-${d.online}-${d.seen_today}`)}">
    <td><strong>${esc(d.name)}</strong><span class="muted">ID ${esc(d.medical_id)}</span></td>
    <td>${esc(d.department_name)}</td>
    <td><span class="presence ${d.online ? "on" : ""}">${d.online ? "Online" : "Offline"}</span></td>
    <td class="num">${d.seen_today}</td>
    <td class="num">${d.prescribed_today}</td>
    <td class="num">${d.seen_total}</td>
    <td class="muted">${d.last_active_at ? timeAgo(d.last_active_at) : "No activity yet"}</td>
  </tr>`;

const matches = (d) =>
  `${d.name} ${d.medical_id} ${d.department_name}`.toLowerCase().includes(query.trim().toLowerCase());

function renderDoctors() {
  const list = doctors.filter(matches);
  const online = doctors.filter((d) => d.online).length;
  $("#pp-count", el).textContent = doctors.length ? `${doctors.length} registered, ${online} online` : "";
  $("#pp-doctors", el).innerHTML = list.length
    ? `<div class="table-wrap"><table class="table"><thead><tr><th>Doctor</th><th>Department</th><th>Status</th>
         <th class="num">Seen today</th><th class="num">Prescribed today</th><th class="num">Seen in total</th><th>Last active</th></tr></thead>
        <tbody>${list.map(doctorRow).join("")}</tbody></table></div>`
    : `<div class="empty"><strong>${doctors.length ? "No doctor matches your search" : "No doctors registered yet"}</strong>${doctors.length ? "" : "Use the form to add the first one."}</div>`;
}

const staffRow = (s) => `
  <tr><td><strong>${esc(s.name)}</strong></td><td>${esc(s.staff_id)}</td>
    <td class="muted">${new Date(s.created_at).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}</td></tr>`;

function renderStaff(staff) {
  $("#pp-staff", el).innerHTML = staff.length
    ? `<div class="table-wrap"><table class="table"><thead><tr><th>Name</th><th>Staff ID</th><th>Added</th></tr></thead>
        <tbody>${staff.map(staffRow).join("")}</tbody></table></div>`
    : `<div class="empty"><strong>No OPD staff registered yet</strong>Use the form to add the first one.</div>`;
}

async function load() {
  const root = el;
  const board = await api.adminDashboard(); // a 401 clears the login and the app returns to the login screen
  if (root !== el) return;

  const select = $("#pp-department", el);
  if (!select.options.length) {
    select.innerHTML = board.departments.map((d) => `<option value="${d.code}">${esc(d.name)}</option>`).join("");
  }
  doctors = board.doctors;
  const minute = Math.floor(Date.now() / 60000);
  const doctorSig = JSON.stringify([doctors, minute, query]);
  if (sigs.doctors !== doctorSig) {
    sigs.doctors = doctorSig;
    renderDoctors();
  }
  const staffSig = JSON.stringify(board.staff);
  if (sigs.staff !== staffSig) {
    sigs.staff = staffSig;
    renderStaff(board.staff);
  }
}

function wireForm(id, action, message) {
  $(id, el).addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    try {
      const created = await withBusy($("button", form), () => action(data));
      toast(message(created));
      form.reset();
      await load();
    } catch (error) {
      toast(errorText(error), "error");
    }
  });
}

export default {
  title: "Doctors and staff",
  subtitle: "Who can log in, what each doctor has done today, and who is working now.",

  async mount(root) {
    el = root;
    sigs = {};
    doctors = [];
    query = "";
    el.innerHTML = `
      <div class="pp-layout">
        <section class="card adm-card">
          <div class="side-head"><h2>Doctors</h2><span class="muted" id="pp-count"></span></div>
          <label class="field pp-search">Search doctors
            <input type="search" id="pp-q" placeholder="Name, department or ID" autocomplete="off"></label>
          <div id="pp-doctors"></div>
        </section>
        <section class="card adm-card">
          <h2>Add a doctor</h2>
          <p class="muted">The doctor logs in on the Doctor desk with this name and medical ID.</p>
          <form class="form" id="doctor-form">
            <label class="field">Full name<input name="name" required minlength="2" maxlength="100" autocomplete="off" placeholder="Dr. Asha Rao"></label>
            <label class="field">Medical ID<input name="medical_id" required minlength="3" maxlength="40" autocomplete="off" placeholder="MH-2026-1001"></label>
            <label class="field">Department<select name="department" id="pp-department" required></select></label>
            <button class="btn" type="submit">Add doctor</button>
          </form>
        </section>
        <section class="card adm-card">
          <div class="side-head"><h2>OPD staff</h2></div>
          <div id="pp-staff"></div>
        </section>
        <section class="card adm-card">
          <h2>Add OPD staff</h2>
          <p class="muted">Staff log in on the OPD staff desk with this name and staff ID.</p>
          <form class="form" id="staff-form">
            <label class="field">Full name<input name="name" required minlength="2" maxlength="100" autocomplete="off" placeholder="Meena Joshi"></label>
            <label class="field">Staff ID<input name="staff_id" required minlength="3" maxlength="40" autocomplete="off" placeholder="OPD-001"></label>
            <button class="btn" type="submit">Add staff member</button>
          </form>
        </section>
      </div>`;

    $("#pp-q", el).addEventListener("input", (e) => {
      query = e.target.value;
      sigs.doctors = JSON.stringify([doctors, Math.floor(Date.now() / 60000), query]);
      renderDoctors();
    });
    wireForm("#doctor-form", api.addDoctor, (d) => `${d.name} can now log in on the Doctor desk.`);
    wireForm("#staff-form", api.addStaff, (s) => `${s.name} can now log in on the OPD staff desk.`);
    await load();
  },

  async refresh() {
    await load();
  },
};
