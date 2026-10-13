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
// Separate keys mean a doctor, an OPD staff member and a patient can be logged in side by side.
function tokenStore(key) {
  return {
    get() {
      try {
        return localStorage.getItem(key);
      } catch {
        return null;
      }
    },
    set(token) {
      try {
        localStorage.setItem(key, token);
      } catch {
        /* private mode: the person just logs in again after a refresh */
      }
    },
    clear() {
      try {
        localStorage.removeItem(key);
      } catch {
        /* nothing to clear */
      }
    },
  };
}

export const session = tokenStore("careflow.session"); // doctor
export const staffSession = tokenStore("careflow.staff");
export const patientSession = tokenStore("careflow.patient");

// Each API area uses the token of its own role, so one role's token is never sent to another's endpoints.
const sessionFor = (path) =>
  path.startsWith("/doctor") ? session : path.startsWith("/staff") ? staffSession : path.startsWith("/patient") ? patientSession : null;

async function request(method, path, body) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  const token = sessionFor(path)?.get();
  if (token) headers.Authorization = `Bearer ${token}`;

  let response;
  try {
    response = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError(0, { code: "network_error", message: "Cannot reach the server. Check that it is running." });
  }
  const data = await response.json().catch(() => null);
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
  patientLogin: (phone, password) => request("POST", "/patient/login", { phone, password }),
  patientLogout: () => request("POST", "/patient/logout"),
  patientDashboard: () => request("GET", "/patient/dashboard"),
};
