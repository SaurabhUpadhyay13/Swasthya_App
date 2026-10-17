/** Thin wrapper over fetch. Every failure becomes an ApiError with the server's structured error. */

export class ApiError extends Error {
  constructor(status, error) {
    super(error.message);
    this.status = status;
    this.code = error.code;
    this.details = error.details ?? [];
  }
}

// Login tokens, one per role, kept in the browser so a page refresh does not log anyone out.
// Only one person is signed in at a time: signing in as one role removes the other roles' tokens,
// so the menu and the pages shown always belong to exactly one role.
const stores = {};

function tokenStore(role, key) {
  const store = {
    role,
    get() {
      try {
        return localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    set(token) {
      for (const other of Object.values(stores)) if (other !== store) other.remove();
      try {
        localStorage.setItem(key, token);
      } catch {
        /* private mode: the person just logs in again after a refresh */
      }
      announce();
    },
    remove() {
      try {
        localStorage.removeItem(key);
      } catch {
        /* nothing to clear */
      }
    },
    clear() {
      store.remove();
      announce();
    },
  };
  stores[role] = store;
  return store;
}

// main.js listens, to show the right menu and send signed-out visitors to the login screen.
const announce = () => window.dispatchEvent(new Event("auth-change"));

export const adminSession = tokenStore("admin", "careflow.admin");
export const session = tokenStore("doctor", "careflow.session"); // doctor
export const staffSession = tokenStore("staff", "careflow.staff");
export const patientSession = tokenStore("patient", "careflow.patient");

/** "admin", "doctor", "staff", "patient", or null when nobody is signed in. */
export const currentRole = () => Object.values(stores).find((store) => store.get())?.role ?? null;

const LOGIN_PATHS = new Set(["/admin/login", "/doctor/login", "/staff/login", "/patient/login", "/patient/activate", "/patient/signup"]);

// Each API area uses the token of its own role. Shared endpoints (/opd, /work-orders, /summarize) use whoever is signed in.
function storeFor(path) {
  const area = path.split("/")[1];
  const own = { admin: adminSession, doctor: session, staff: staffSession, patient: patientSession }[area];
  return own ?? stores[currentRole()] ?? null;
}

async function request(method, path, body) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  const store = storeFor(path);
  const token = store?.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, { code: "network_error", message: "Cannot reach the server. Check that it is running." });
  }
  const data = await response.json().catch(() => null);
  if (response.status === 401 && token && !LOGIN_PATHS.has(path)) store.clear(); // session ended: back to the login screen
  if (!response.ok) {
    throw new ApiError(response.status, data?.error ?? { code: "unknown", message: "Unexpected server error." });
  }
  return data;
}

const enc = encodeURIComponent;

export const api = {
  departments: () => request("GET", "/opd/departments"),
  tokens: (department) => request("GET", `/opd/tokens${department ? `?department=${enc(department)}` : ""}`),
  token: (id) => request("GET", `/opd/tokens/${enc(id)}`),
  register: (body) => request("POST", "/opd/tokens", body),
  setTokenStatus: (id, status) => request("PATCH", `/opd/tokens/${enc(id)}/status`, { status }),

  adminLogin: (admin_id, password) => request("POST", "/admin/login", { admin_id, password }),
  adminLogout: () => request("POST", "/admin/logout"),
  adminDashboard: () => request("GET", "/admin/dashboard"),
  addDoctor: (body) => request("POST", "/admin/doctors", body),
  addStaff: (body) => request("POST", "/admin/staff", body),
  addStock: (body) => request("POST", "/admin/stock", body),

  workOrders: () => request("GET", "/work-orders"),
  createWorkOrder: (body) => request("POST", "/work-orders", body),
  setWorkOrderStatus: (id, status) => request("PATCH", `/work-orders/${id}/status`, { status }),
  summarize: (id) => request("POST", "/summarize", { work_order_id: id }),

  doctorLogin: (name, medical_id) => request("POST", "/doctor/login", { name, medical_id }),
  doctorLogout: () => request("POST", "/doctor/logout"),
  doctorDashboard: () => request("GET", "/doctor/dashboard"),
  consultation: (token) => request("GET", `/doctor/consultations/${enc(token)}`),
  saveConsultation: (token, body) => request("PUT", `/doctor/consultations/${enc(token)}`, body),
  searchMedicines: (q) => request("GET", `/doctor/medicines?q=${enc(q)}`),

  staffLogin: (name, staff_id) => request("POST", "/staff/login", { name, staff_id }),
  staffLogout: () => request("POST", "/staff/logout"),
  staffDashboard: () => request("GET", "/staff/dashboard"),
  issuePatientCode: (phone) => request("POST", "/staff/patient-codes", { phone }),

  patientActivate: (phone, code, password) => request("POST", "/patient/activate", { phone, code, password }),
  patientSignupStart: (phone, name, age) => request("POST", "/patient/signup/start", { phone, name, age }),
  patientSignup: (phone, code, password) => request("POST", "/patient/signup", { phone, code, password }),
  patientLogin: (phone, password) => request("POST", "/patient/login", { phone, password }),
  patientLogout: () => request("POST", "/patient/logout"),
  patientDashboard: () => request("GET", "/patient/dashboard"),
  patientRegister: (department, complaint) => request("POST", "/patient/tokens", { department, complaint }),
  patientCancel: () => request("POST", "/patient/tokens/cancel"),
};

/** Sign the current person out on the server too, then forget their token. */
export async function signOut() {
  const role = currentRole();
  const logout = { admin: api.adminLogout, doctor: api.doctorLogout, staff: api.staffLogout, patient: api.patientLogout }[role];
  try {
    await logout?.();
  } catch {
    /* the token is dropped below either way */
  }
  stores[role]?.clear();
}
