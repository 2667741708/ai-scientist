import type { AccountRole, AccountStatus, AuthSession, AuthUsersResponse } from "../../types/workbench";
import { parseApiError } from "../formatters/workbench";
import { getApiBase } from "./client";

const AUTH_TOKEN_KEY = "open_coscientist_auth_token";

export class AuthApiError extends Error {
  code: string;
  httpStatus: number;

  constructor(message: string, code: string, httpStatus: number) {
    super(message);
    this.name = "AuthApiError";
    this.code = code;
    this.httpStatus = httpStatus;
  }
}

export function getStoredAuthToken() {
  if (typeof localStorage === "undefined") return "";
  return localStorage.getItem(AUTH_TOKEN_KEY) || "";
}

export function storeAuthToken(token: string) {
  if (typeof localStorage === "undefined") return;
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearStoredAuthToken() {
  if (typeof localStorage === "undefined") return;
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export function authHeaders(extra: HeadersInit = {}) {
  const token = getStoredAuthToken();
  return {
    ...extra,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    try {
      const parsed = JSON.parse(body) as {
        detail?: string | { code?: string; message?: string; http_status?: number };
      };
      if (parsed.detail && typeof parsed.detail === "object") {
        throw new AuthApiError(
          parsed.detail.message || "认证请求失败。",
          parsed.detail.code || `auth.request_failed_${response.status}`,
          parsed.detail.http_status || response.status,
        );
      }
    } catch (error) {
      if (error instanceof AuthApiError) throw error;
    }
    throw new AuthApiError(parseApiError(body), `auth.request_failed_${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export async function loginAccount(payload: { email: string; password: string }) {
  const response = await fetch(`${getApiBase()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<AuthSession>(response);
}

export async function registerResearcher(payload: {
  email: string;
  password: string;
  display_name: string;
  recovery_question?: string;
  recovery_answer?: string;
}) {
  const response = await fetch(`${getApiBase()}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<AuthSession>(response);
}

export async function fetchRecoveryChallenge(payload: { email: string }) {
  const response = await fetch(`${getApiBase()}/api/auth/recovery/challenge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<{ ok: boolean; available: boolean; email: string; question?: string; message?: string }>(response);
}

export async function resetPasswordWithRecovery(payload: { email: string; answer: string; new_password: string }) {
  const response = await fetch(`${getApiBase()}/api/auth/recovery/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse<AuthSession>(response);
}

export async function fetchCurrentAccount() {
  const response = await fetch(`${getApiBase()}/api/auth/me`, {
    headers: authHeaders(),
  });
  return parseResponse<{ user: AuthSession["user"] }>(response);
}

export async function logoutAccount() {
  const response = await fetch(`${getApiBase()}/api/auth/logout`, {
    method: "POST",
    headers: authHeaders(),
  });
  return parseResponse<{ ok: boolean }>(response);
}

export async function listAuthUsers() {
  const response = await fetch(`${getApiBase()}/api/admin/users`, {
    headers: authHeaders(),
  });
  return parseResponse<AuthUsersResponse>(response);
}

export async function createAuthUser(payload: {
  email: string;
  password: string;
  display_name: string;
  role: AccountRole;
}) {
  const response = await fetch(`${getApiBase()}/api/admin/users`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(payload),
  });
  return parseResponse<{ user: AuthSession["user"]; local_secret_path?: string }>(response);
}

export async function updateAuthUserStatus(userId: string, status: AccountStatus) {
  const response = await fetch(`${getApiBase()}/api/admin/users/${encodeURIComponent(userId)}/status`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ status }),
  });
  return parseResponse<{ user: AuthSession["user"] }>(response);
}

export async function resetAuthUserPassword(userId: string, password: string) {
  const response = await fetch(`${getApiBase()}/api/admin/users/${encodeURIComponent(userId)}/password`, {
    method: "PUT",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ password }),
  });
  return parseResponse<{ user: AuthSession["user"]; local_secret_path?: string }>(response);
}
