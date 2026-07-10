import { parseApiError } from "../formatters/workbench";

function resolveApiBase() {
  if (import.meta.env.VITE_API_BASE) return import.meta.env.VITE_API_BASE;
  if (typeof window !== "undefined" && window.location.hostname) {
    return `${window.location.protocol}//${window.location.hostname}:8787`;
  }
  return "http://127.0.0.1:8787";
}

const API_BASE = resolveApiBase();

export function getApiBase() {
  return API_BASE;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(parseApiError(text || `request_failed_${response.status}`));
  }
  return (await response.json()) as T;
}
