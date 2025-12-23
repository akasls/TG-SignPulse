import { Account, Task, TaskLog, TokenResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const headers: HeadersInit = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "请求失败");
  }
  return res.json();
}

export const login = (payload: {
  username: string;
  password: string;
  totp_code?: string;
}) =>
  request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });

// Accounts
export const fetchAccounts = (token: string) =>
  request<Account[]>("/accounts", {}, token);

export const createAccount = (
  token: string,
  payload: Pick<Account, "account_name" | "api_id" | "api_hash" | "proxy">
) =>
  request<Account>(
    "/accounts",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );

export const startAccountLogin = (token: string, id: number) =>
  request(`/accounts/${id}/login/start`, { method: "POST" }, token);

export const verifyAccountLogin = (
  token: string,
  id: number,
  payload: { code?: string; password?: string }
) =>
  request(`/accounts/${id}/login/verify`, {
    method: "POST",
    body: JSON.stringify(payload),
  }, token);

// Tasks
export const fetchTasks = (token: string) =>
  request<Task[]>("/tasks", {}, token);

export const createTask = (
  token: string,
  payload: { name: string; cron: string; account_id: number; enabled: boolean }
) =>
  request<Task>(
    "/tasks",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
    token
  );

export const updateTask = (
  token: string,
  id: number,
  payload: Partial<{ name: string; cron: string; enabled: boolean; account_id: number }>
) =>
  request<Task>(
    `/tasks/${id}`,
    {
      method: "PUT",
      body: JSON.stringify(payload),
    },
    token
  );

export const deleteTask = (token: string, id: number) =>
  request(`/tasks/${id}`, { method: "DELETE" }, token);

export const runTask = (token: string, id: number) =>
  request<TaskLog>(`/tasks/${id}/run`, { method: "POST" }, token);

export const fetchTaskLogs = (token: string, id: number, limit = 50) =>
  request<TaskLog[]>(`/tasks/${id}/logs?limit=${limit}`, {}, token);



