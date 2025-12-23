export type Account = {
  id: number;
  account_name: string;
  api_id: string;
  api_hash: string;
  proxy?: string | null;
  status: string;
  last_login_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type Task = {
  id: number;
  name: string;
  cron: string;
  enabled: boolean;
  account_id: number;
  last_run_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type TaskLog = {
  id: number;
  task_id: number;
  status: string;
  log_path?: string | null;
  output?: string | null;
  started_at: string;
  finished_at?: string | null;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
};


