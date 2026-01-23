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
    // 尝试解析 JSON 错误响应
    let errorMessage = "请求失败";
    try {
      const errorData = await res.json();
      errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
    } catch {
      // 如果不是 JSON，使用文本
      try {
        errorMessage = await res.text() || "请求失败";
      } catch {
        // 忽略
      }
    }

    // 如果是认证失败 (401) 且请求携带了 token，清除 token 并跳转到登录页
    // 注意：登录相关请求（不带 token）不应触发跳转
    if (res.status === 401 && token) {
      if (typeof window !== "undefined") {
        localStorage.removeItem("tg-signer-token");
        window.location.href = "/";
      }
    }

    throw new Error(errorMessage);
  }
  if (res.status === 204) {
    return {} as T;
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

export const resetTOTP = (payload: { username: string; password: string }) =>
  request<{ success: boolean; message: string }>("/auth/reset-totp", {
    method: "POST",
    body: JSON.stringify(payload),
  });


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

export const exportSignTask = async (token: string, taskName: string) => {
  const res = await fetch(`${API_BASE}/config/export/sign/${taskName}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    let errorMessage = "Export failed";
    try {
      const errorData = await res.json();
      errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
    } catch {
      errorMessage = await res.text() || "Export failed";
    }
    throw new Error(errorMessage);
  }
  return res.text();
};

export const importSignTask = (token: string, configJson: string, taskName?: string) =>
  request<{ success: boolean; task_name: string; message: string }>("/config/import/sign", {
    method: "POST",
    body: JSON.stringify({ config_json: configJson, task_name: taskName }),
  }, token);

export const exportAllConfigs = async (token: string) => {
  const res = await fetch(`${API_BASE}/config/export/all`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    let errorMessage = "Export failed";
    try {
      const errorData = await res.json();
      errorMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
    } catch {
      errorMessage = await res.text() || "Export failed";
    }
    throw new Error(errorMessage);
  }
  return res.text();
};

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

export const changeUsername = (token: string, newUsername: string, password: string) =>
  request<ChangeUsernameResponse>("/user/username", {
    method: "PUT",
    body: JSON.stringify({ new_username: newUsername, password: password }),
  }, token);

// ============ AI 配置 ============

export interface AIConfig {
  has_config: boolean;
  base_url?: string;
  model?: string;
  api_key_masked?: string;
}

export interface ChangeUsernameResponse {
  success: boolean;
  message: string;
  access_token?: string;
}

export interface AITestResult {
  success: boolean;
  message: string;
  model_used?: string;
}

export const getAIConfig = (token: string) =>
  request<AIConfig>("/config/ai", {}, token);

export const saveAIConfig = (
  token: string,
  config: { api_key: string; base_url?: string; model?: string }
) =>
  request<{ success: boolean; message: string }>("/config/ai", {
    method: "POST",
    body: JSON.stringify(config),
  }, token);

export const testAIConnection = (token: string) =>
  request<AITestResult>("/config/ai/test", {
    method: "POST",
  }, token);

export const deleteAIConfig = (token: string) =>
  request<{ success: boolean; message: string }>("/config/ai", {
    method: "DELETE",
  }, token);

// ============ 全局设置 ============

export interface GlobalSettings {
  sign_interval?: number | null;  // null 表示随机 1-120 秒
  log_retention_days?: number;    // 日志保留天数，默认 7
}

export const getGlobalSettings = (token: string) =>
  request<GlobalSettings>("/config/settings", {}, token);

export const saveGlobalSettings = (token: string, settings: GlobalSettings) =>
  request<{ success: boolean; message: string }>("/config/settings", {
    method: "POST",
    body: JSON.stringify(settings),
  }, token);

// ============ Telegram API 配置 ============

export interface TelegramConfig {
  api_id: string;
  api_hash: string;
  is_custom: boolean;
  default_api_id: string;
  default_api_hash: string;
}

export const getTelegramConfig = (token: string) =>
  request<TelegramConfig>("/config/telegram", {}, token);

export const saveTelegramConfig = (
  token: string,
  config: { api_id: string; api_hash: string }
) =>
  request<{ success: boolean; message: string }>("/config/telegram", {
    method: "POST",
    body: JSON.stringify(config),
  }, token);

export const resetTelegramConfig = (token: string) =>
  request<{ success: boolean; message: string }>("/config/telegram", {
    method: "DELETE",
  }, token);

// ============ 账号日志 ============

export interface AccountLog {
  id: number;
  account_name: string;
  task_name: string;
  message: string;
  success: boolean;
  created_at: string;
}

export const getAccountLogs = (token: string, accountName: string, limit: number = 100) =>
  request<AccountLog[]>(`/accounts/${accountName}/logs?limit=${limit}`, {}, token);

export const exportAccountLogs = async (token: string, accountName: string) => {
  const res = await fetch(`${API_BASE}/accounts/${accountName}/logs/export`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });
  if (!res.ok) throw new Error("Export failed");
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `logs_${accountName}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

// ============ 签到任务管理 ============

export interface SignTaskChat {
  chat_id: number;
  name: string;
  actions: any[];
  delete_after?: number;
  action_interval: number;
}

export interface LastRunInfo {
  time: string;
  success: boolean;
  message?: string;
}

export interface SignTask {
  name: string;
  account_name: string;
  sign_at: string;
  chats: SignTaskChat[];
  random_seconds: number;
  sign_interval: number;
  enabled: boolean;
  last_run?: LastRunInfo | null;
  execution_mode?: "fixed" | "range";
  range_start?: string;
  range_end?: string;
}

export interface CreateSignTaskRequest {
  name: string;
  account_name: string;
  sign_at: string;
  chats: SignTaskChat[];
  random_seconds?: number;
  sign_interval?: number;
  execution_mode?: "fixed" | "range";
  range_start?: string;
  range_end?: string;
}

export interface UpdateSignTaskRequest {
  sign_at?: string;
  chats?: SignTaskChat[];
  random_seconds?: number;
  sign_interval?: number;
  execution_mode?: "fixed" | "range";
  range_start?: string;
  range_end?: string;
}

export interface ChatInfo {
  id: number;
  title?: string;
  username?: string;
  type: string;
  first_name?: string;
}

export async function listSignTasks(token: string, accountName?: string, forceRefresh?: boolean): Promise<SignTask[]> {
  const params = new URLSearchParams();
  if (accountName) params.append('account_name', accountName);
  if (forceRefresh) params.append('force_refresh', 'true');
  const url = `/sign-tasks${params.toString() ? `?${params.toString()}` : ''}`;
  return request<SignTask[]>(url, {}, token);
}

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

export const deleteSignTask = (token: string, name: string, accountName?: string) =>
  request<{ ok: boolean }>(`/sign-tasks/${name}${accountName ? `?account_name=${accountName}` : ''}`, {
    method: "DELETE",
  }, token);

export const runSignTask = (token: string, name: string, accountName: string) =>
  request<{ success: boolean; output: string; error: string }>(`/sign-tasks/${name}/run?account_name=${accountName}`, {
    method: "POST",
  }, token);

export const getAccountChats = (token: string, accountName: string, forceRefresh?: boolean) =>
  request<ChatInfo[]>(`/sign-tasks/chats/${accountName}${forceRefresh ? '?force_refresh=true' : ''}`, {}, token);

export const getSignTaskLogs = (token: string, name: string) =>
  request<string[]>(`/sign-tasks/${name}/logs`, {}, token);

