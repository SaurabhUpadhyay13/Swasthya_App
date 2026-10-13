/** Small shared helpers: escaping, toasts, modal, count-up, labels. */

export const $ = (selector, root = document) => root.querySelector(selector);

// Everything user-typed goes through esc() before touching innerHTML.
export const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

export const errorText = (error) =>
  error.details?.length
    ? error.details.map((d) => `${d.field.replace(/_/g, " ")}: ${d.message}`).join("; ")
    : error.message || "Something went wrong.";

// ---- Workflow labels (mirror the backend enums) ----
export const TOKEN_FLOW = ["waiting", "in_consultation", "prescribed", "pharmacy", "completed"];
export const TOKEN_LABEL = { waiting: "Waiting", in_consultation: "In consultation", prescribed: "Prescribed", pharmacy: "At pharmacy", completed: "Completed" };
export const TOKEN_ACTION = { waiting: "Call in", in_consultation: "Mark prescribed", prescribed: "Send to pharmacy", pharmacy: "Complete" };

export const WO_FLOW = ["requested", "ordered", "received", "completed"];
export const WO_LABEL = { requested: "Requested", ordered: "Ordered", received: "Received", completed: "Completed" };
export const WO_ACTION = { requested: "Mark ordered", ordered: "Mark received", received: "Complete" };
export const PRIORITY_LABEL = { low: "Low", medium: "Medium", high: "High", critical: "Critical" };

export const nextStep = (flow, current) => flow[flow.indexOf(current) + 1];

// ---- Entrance animation only the first time an item appears ----
const seen = new Set();
export function enter(key) {
  if (seen.has(key)) return "";
  seen.add(key);
  return "enter";
}

export function timeAgo(iso) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function countUp(el, to) {
  const from = Number(el.dataset.v ?? 0);
  el.dataset.v = to;
  if (from === to || reducedMotion()) {
    el.textContent = to;
    return;
  }
  const start = performance.now();
  const tick = (now) => {
    const t = Math.min(1, (now - start) / 700);
    el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

export function toast(message, kind = "info") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => {
    el.classList.add("out");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  }, kind === "error" ? 5500 : 3200);
}

export function openModal(html) {
  const root = $("#modal-root");
  root.innerHTML = `<div class="modal-backdrop" role="dialog" aria-modal="true">${html}</div>`;
  const onKey = (e) => e.key === "Escape" && close();
  const close = () => {
    root.innerHTML = "";
    document.removeEventListener("keydown", onKey);
  };
  document.addEventListener("keydown", onKey);
  root.firstElementChild.addEventListener("click", (e) => {
    if (e.target === e.currentTarget || e.target.closest("[data-close]")) close();
  });
  root.querySelector("button")?.focus();
  return close;
}

/** Disable a button and show a spinner while an async action runs. */
export async function withBusy(button, action) {
  button.disabled = true;
  button.classList.add("busy");
  try {
    return await action();
  } finally {
    button.disabled = false;
    button.classList.remove("busy");
  }
}
