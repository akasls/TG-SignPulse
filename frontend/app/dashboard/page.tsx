"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, setToken, clearToken } from "../../lib/auth";
import {
  fetchAccounts,
  createAccount,
  startAccountLogin,
  verifyAccountLogin,
  fetchTasks,
  createTask,
  updateTask,
  deleteTask,
  runTask,
  fetchTaskLogs,
} from "../../lib/api";
import { Account, Task, TaskLog } from "../../lib/types";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Select } from "../../components/ui/select";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle className="text-lg font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [token, setLocalToken] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [taskLogs, setTaskLogs] = useState<TaskLog[]>([]);

  const [formAccount, setFormAccount] = useState({
    account_name: "",
    api_id: "",
    api_hash: "",
    proxy: "",
  });

  const [formTask, setFormTask] = useState({
    name: "",
    cron: "0 6 * * *",
    account_id: "",
  });

  const [loginVerify, setLoginVerify] = useState({
    account_id: "",
    code: "",
    password: "",
  });

  useEffect(() => {
    const t = getToken();
    if (!t) {
      router.replace("/");
      return;
    }
    setLocalToken(t);
    refreshData(t);
  }, [router]);

  const refreshData = async (t: string | null = token) => {
    if (!t) return;
    const acc = await fetchAccounts(t);
    setAccounts(acc);
    const ts = await fetchTasks(t);
    setTasks(ts);
  };

  const handleCreateAccount = async () => {
    if (!token) return;
    await createAccount(token, formAccount);
    setFormAccount({ account_name: "", api_id: "", api_hash: "", proxy: "" });
    refreshData();
  };

  const handleStartLogin = async (id: number) => {
    if (!token) return;
    await startAccountLogin(token, id);
    setLoginVerify({ ...loginVerify, account_id: String(id) });
    alert("已发起登录，请在下方输入验证码/2FA");
  };

  const handleVerifyLogin = async () => {
    if (!token || !loginVerify.account_id) return;
    await verifyAccountLogin(token, Number(loginVerify.account_id), {
      code: loginVerify.code,
      password: loginVerify.password || undefined,
    });
    setLoginVerify({ account_id: "", code: "", password: "" });
    refreshData();
  };

  const handleCreateTask = async () => {
    if (!token) return;
    await createTask(token, {
      name: formTask.name,
      cron: formTask.cron,
      account_id: Number(formTask.account_id),
      enabled: true,
    });
    setFormTask({ name: "", cron: "0 6 * * *", account_id: "" });
    refreshData();
  };

  const handleToggleTask = async (task: Task) => {
    if (!token) return;
    await updateTask(token, task.id, { enabled: !task.enabled });
    refreshData();
  };

  const handleDeleteTask = async (taskId: number) => {
    if (!token) return;
    await deleteTask(token, taskId);
    refreshData();
  };

  const handleRunTask = async (taskId: number) => {
    if (!token) return;
    const log = await runTask(token, taskId);
    alert(`任务已触发，状态：${log.status}`);
    refreshLogs(taskId);
  };

  const refreshLogs = async (taskId: number) => {
    if (!token) return;
    const logs = await fetchTaskLogs(token, taskId);
    setTaskLogs(logs);
  };

  const handleLogout = () => {
    clearToken();
    router.replace("/");
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">tg-signer 控制台</h1>
          <div className="flex items-center gap-3">
            <span className="text-sm text-gray-600">已登录</span>
            <Button variant="secondary" onClick={handleLogout}>
              退出
            </Button>
          </div>
        </div>

        {/* 账号管理 */}
        <Section title="账号管理">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-3">
              <div>
                <Label>账号名称</Label>
                <Input
                  value={formAccount.account_name}
                  onChange={(e) =>
                    setFormAccount({ ...formAccount, account_name: e.target.value })
                  }
                  placeholder="my_account"
                />
              </div>
              <div>
                <Label>API ID</Label>
                <Input
                  value={formAccount.api_id}
                  onChange={(e) =>
                    setFormAccount({ ...formAccount, api_id: e.target.value })
                  }
                  placeholder="123456"
                />
              </div>
              <div>
                <Label>API Hash</Label>
                <Input
                  value={formAccount.api_hash}
                  onChange={(e) =>
                    setFormAccount({ ...formAccount, api_hash: e.target.value })
                  }
                  placeholder="your_api_hash"
                />
              </div>
              <div>
                <Label>代理 (可选)</Label>
                <Input
                  value={formAccount.proxy}
                  onChange={(e) =>
                    setFormAccount({ ...formAccount, proxy: e.target.value })
                  }
                  placeholder="socks5://127.0.0.1:1080"
                />
              </div>
              <Button onClick={handleCreateAccount}>添加账号</Button>
            </div>

            <div className="space-y-3">
              <div className="text-sm text-gray-700">
                <div className="font-semibold mb-2">已绑定账号</div>
                <div className="space-y-2">
                  {accounts.map((acc) => (
                    <div
                      key={acc.id}
                      className="flex items-center justify-between rounded border px-3 py-2"
                    >
                      <div>
                        <div className="font-medium">{acc.account_name}</div>
                        <div className="text-xs text-gray-500">
                          状态: {acc.status}，上次登录:{" "}
                          {acc.last_login_at ? acc.last_login_at : "N/A"}
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" onClick={() => handleStartLogin(acc.id)}>
                          登录
                        </Button>
                      </div>
                    </div>
                  ))}
                  {accounts.length === 0 && (
                    <div className="text-xs text-gray-500">暂无账号</div>
                  )}
                </div>
              </div>

              <div className="space-y-2 rounded border px-3 py-3">
                <div className="font-semibold text-sm">验证码 / 2FA 验证</div>
                <Input
                  placeholder="账号 ID"
                  value={loginVerify.account_id}
                  onChange={(e) =>
                    setLoginVerify({ ...loginVerify, account_id: e.target.value })
                  }
                />
                <Input
                  placeholder="验证码"
                  value={loginVerify.code}
                  onChange={(e) =>
                    setLoginVerify({ ...loginVerify, code: e.target.value })
                  }
                />
                <Input
                  placeholder="Telegram 密码 (可选)"
                  value={loginVerify.password}
                  onChange={(e) =>
                    setLoginVerify({ ...loginVerify, password: e.target.value })
                  }
                />
                <Button onClick={handleVerifyLogin}>提交验证</Button>
              </div>
            </div>
          </div>
        </Section>

        {/* 任务管理 */}
        <Section title="任务管理">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-3">
              <div>
                <Label>任务名称 (tg-signer 配置名)</Label>
                <Input
                  value={formTask.name}
                  onChange={(e) =>
                    setFormTask({ ...formTask, name: e.target.value })
                  }
                  placeholder="my_sign"
                />
              </div>
              <div>
                <Label>CRON 表达式</Label>
                <Input
                  value={formTask.cron}
                  onChange={(e) =>
                    setFormTask({ ...formTask, cron: e.target.value })
                  }
                  placeholder="0 6 * * *"
                />
              </div>
              <div>
                <Label>绑定账号</Label>
                <Select
                  value={formTask.account_id}
                  onChange={(e) =>
                    setFormTask({ ...formTask, account_id: e.target.value })
                  }
                >
                  <option value="">选择账号</option>
                  {accounts.map((acc) => (
                    <option key={acc.id} value={acc.id}>
                      {acc.account_name}
                    </option>
                  ))}
                </Select>
              </div>
              <Button onClick={handleCreateTask}>创建任务</Button>
            </div>

            <div className="space-y-2">
              {tasks.map((task) => (
                <div
                  key={task.id}
                  className="rounded border px-3 py-2 flex items-center justify-between"
                >
                  <div className="text-sm">
                    <div className="font-semibold">
                      {task.name} (#{task.id})
                    </div>
                    <div className="text-gray-500">
                      cron: {task.cron} ｜ 启用: {task.enabled ? "是" : "否"} ｜ 账号:
                      {task.account_id} ｜ 上次运行:{" "}
                      {task.last_run_at ? task.last_run_at : "N/A"}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => handleRunTask(task.id)}>
                      立即运行
                    </Button>
                    <Button size="sm" onClick={() => refreshLogs(task.id)} variant="secondary">
                      查看日志
                    </Button>
                    <Button size="sm" onClick={() => handleToggleTask(task)} variant="outline">
                      {task.enabled ? "停用" : "启用"}
                    </Button>
                    <Button size="sm" onClick={() => handleDeleteTask(task.id)} variant="destructive">
                      删除
                    </Button>
                  </div>
                </div>
              ))}
              {tasks.length === 0 && (
                <div className="text-xs text-gray-500">暂无任务</div>
              )}
            </div>
          </div>
        </Section>

        {/* 日志区域 */}
        <Section title="任务日志（选中任务后查看）">
          <div className="space-y-2 max-h-80 overflow-y-auto text-sm">
            {taskLogs.map((log) => (
              <div key={log.id} className="rounded border px-3 py-2">
                <div className="font-semibold">
                  #{log.id} 任务 {log.task_id} ｜ 状态: {log.status}
                </div>
                <div className="text-gray-600">
                  开始: {log.started_at} ｜ 结束: {log.finished_at || "N/A"}
                </div>
                {log.output && (
                  <pre className="mt-2 bg-gray-900 text-gray-100 rounded p-2 text-xs whitespace-pre-wrap">
                    {log.output}
                  </pre>
                )}
              </div>
            ))}
            {taskLogs.length === 0 && (
              <div className="text-xs text-gray-500">暂无日志，点击“查看日志”加载</div>
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}


