import { Account, Task, TaskLog, TokenResponse } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "/api";

const toRecord = (headers?: HeadersInit): Record<string, string> => {
  if (!headers) return {};
  if (headers instanceof Headers) {
    return Object.fromEntries(headers.entries());
  }
  if (Array.isArray(headers)) {
    return Object.fromEntries(headers);
  }
  return headers as Record<string, string>;
};

async function request<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null
): Promise<T> {
  const mergedHeaders: Record<string, string> = {
    ...toRecord(options.headers),
    "Content-Type": "application/json",
  };
  if (token) {
    mergedHeaders["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: mergedHeaders,
    cache: "no-store", // 禁用缓存，确保获取最新数据
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || "请求失败");
  }
  return res.json();
}

// ============ 认证 ============

export const login = (payload: {
  username: string;
  password: string;
  totp_code?: string;
}) =>
  request<TokenResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const getMe = (token: string) =>
  request("/auth/me", {}, token);

// ============ 账号管理（重构版）============

export interface LoginStartRequest {
  account_name: string;
  phone_number: string;
  proxy?: string;
}

export interface LoginStartResponse {
  phone_code_hash: string;
  phone_number: string;
  account_name: string;
  message: string;
}

export interface LoginVerifyRequest {
  account_name: string;
  phone_number: string;
  phone_code: string;
  phone_code_hash: string;
  password?: string;
  proxy?: string;
}

export interface LoginVerifyResponse {
  success: boolean;
  user_id?: number;
  first_name?: string;
  username?: string;
  message: string;
}

export interface AccountInfo {
  name: string;
  session_file: string;
  exists: boolean;
  size: number;
}

export const startAccountLogin = (token: string, data: LoginStartRequest) =>
  request<LoginStartResponse>("/accounts/login/start", {
    method: "POST",
    body: JSON.stringify(data),
  }, token);

export const verifyAccountLogin = (token: string, data: LoginVerifyRequest) =>
  request<LoginVerifyResponse>("/accounts/login/verify", {
    method: "POST",
    body: JSON.stringify(data),
  }, token);

export const listAccounts = (token: string) =>
  request<{ accounts: AccountInfo[]; total: number }>("/accounts", {}, token);

export const deleteAccount = (token: string, accountName: string) =>
  request<{ success: boolean; message: string }>(`/accounts/${accountName}`, {
    method: "DELETE",
  }, token);

export const checkAccountExists = (token: string, accountName: string) =>
  request<{ exists: boolean; account_name: string }>(`/accounts/${accountName}/exists`, {}, token);

// ============ 任务管理 ============

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

// ============ 配置管理 ============

export const listConfigTasks = (token: string) =>
  request<{ sign_tasks: string[]; monitor_tasks: string[]; total: number }>("/config/tasks", {}, token);

export const exportSignTask = (token: string, taskName: string) =>
  fetch(`${API_BASE}/config/export/sign/${taskName}`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(res => res.text());

export const importSignTask = (token: string, configJson: string, taskName?: string) =>
  request<{ success: boolean; task_name: string; message: string }>("/config/import/sign", {
    method: "POST",
    body: JSON.stringify({ config_json: configJson, task_name: taskName }),
  }, token);

export const exportAllConfigs = (token: string) =>
  fetch(`${API_BASE}/config/export/all`, {
    headers: { Authorization: `Bearer ${token}` },
  }).then(res => res.text());

export const importAllConfigs = (token: string, configJson: string, overwrite = false) =>
  request<{
    signs_imported: number;
    signs_skipped: number;
    monitors_imported: number;
    monitors_skipped: number;
    errors: string[];
    message: string;
  }>("/config/import/all", {
    method: "POST",
    body: JSON.stringify({ config_json: configJson, overwrite }),
  }, token);

export const deleteSignConfig = (token: string, taskName: string) =>
  request<{ success: boolean; message: string }>(`/config/sign/${taskName}`, {
    method: "DELETE",
  }, token);

// ============ 用户设置 ============

export const changePassword = (token: string, oldPassword: string, newPassword: string) =>
  request<{ success: boolean; message: string }>("/user/password", {
    method: "PUT",
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  }, token);

export const getTOTPStatus = (token: string) =>
  request<{ enabled: boolean; secret?: string }>("/user/totp/status", {}, token);

export const setupTOTP = (token: string) =>
  request<{ enabled: boolean; secret: string }>("/user/totp/setup", {
    method: "POST",
  }, token);

export const getTOTPQRCode = (token: string) =>
  `${API_BASE}/user/totp/qrcode?token=${token}`;

export const enableTOTP = (token: string, totpCode: string) =>
  request<{ success: boolean; message: string }>("/user/totp/enable", {
    method: "POST",
    body: JSON.stringify({ totp_code: totpCode }),
  }, token);

export const disableTOTP = (token: string, totpCode: string) =>
  request<{ success: boolean; message: string }>("/user/totp/disable", {
    method: "POST",
    body: JSON.stringify({ totp_code: totpCode }),
  }, token);

// ============ 签到任务管理 ============

export interface SignTaskChat {
  chat_id: number;
  name: string;
  actions: any[];
  delete_after?: number;
  action_interval: number;
}

export interface SignTask {
  name: string;
  sign_at: string;
  chats: SignTaskChat[];
  random_seconds: number;
  sign_interval: number;
  enabled: boolean;
}

export interface CreateSignTaskRequest {
  name: string;
  sign_at: string;
  chats: SignTaskChat[];
  random_seconds?: number;
  sign_interval?: number;
}

export interface UpdateSignTaskRequest {
  sign_at?: string;
  chats?: SignTaskChat[];
  random_seconds?: number;
  sign_interval?: number;
}

export interface ChatInfo {
  id: number;
  title?: string;
  username?: string;
  type: string;
  first_name?: string;
}

export const listSignTasks = (token: string) =>
  request<SignTask[]>("/sign-tasks", {}, token);

export const getSignTask = (token: string, name: string) =>
  request<SignTask>(`/sign-tasks/${name}`, {}, token);

export const createSignTask = (token: string, data: CreateSignTaskRequest) =>
  request<SignTask>("/sign-tasks", {
    method: "POST",
    body: JSON.stringify(data),
  }, token);

export const updateSignTask = (token: string, name: string, data: UpdateSignTaskRequest) =>
  request<SignTask>(`/sign-tasks/${name}`, {
    method: "PUT",
    body: JSON.stringify(data),
  }, token);

export const deleteSignTask = (token: string, name: string) =>
  request<{ ok: boolean }>(`/sign-tasks/${name}`, {
    method: "DELETE",
  }, token);

export const runSignTask = (token: string, name: string, accountName: string) =>
  request<{ success: boolean; output: string; error: string }>(`/sign-tasks/${name}/run?account_name=${accountName}`, {
    method: "POST",
  }, token);

export const getAccountChats = (token: string, accountName: string) =>
  request<ChatInfo[]>(`/sign-tasks/chats/${accountName}`, {}, token);

