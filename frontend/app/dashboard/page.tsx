"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken, logout } from "../../lib/auth";
import {
  fetchTasks,
  createTask,
  updateTask,
  deleteTask,
  runTask,
  fetchTaskLogs,
} from "../../lib/api";
import { Task, TaskLog } from "../../lib/types";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";

export default function Dashboard() {
  const router = useRouter();
  const [token, setLocalToken] = useState<string | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const t = getToken();
    if (!t) {
      router.replace("/");
      return;
    }
    setLocalToken(t);
    loadTasks(t);
  }, [router]);

  const loadTasks = async (t: string) => {
    try {
      setLoading(true);
      const ts = await fetchTasks(t);
      setTasks(ts);
    } catch (err) {
      console.error("加载任务失败:", err);
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* 顶部导航 */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold">tg-signer 控制台</h1>
          <div className="flex items-center gap-3">
            <Link href="/dashboard/accounts">
              <Button variant="secondary">📱 账号管理</Button>
            </Link>
            <Link href="/dashboard/settings">
              <Button variant="secondary">⚙️ 设置</Button>
            </Link>
            <Button variant="secondary" onClick={logout}>
              退出
            </Button>
          </div>
        </div>

        {/* 欢迎卡片 */}
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>欢迎使用 tg-signer</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <p className="text-gray-600">
                这是一个 Telegram 自动化签到工具的 Web 管理界面。
              </p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Link href="/dashboard/accounts">
                  <Card className="cursor-pointer hover:shadow-lg transition-shadow">
                    <CardContent className="pt-6">
                      <div className="text-center">
                        <div className="text-4xl mb-2">📱</div>
                        <h3 className="font-semibold mb-1">账号管理</h3>
                        <p className="text-sm text-gray-500">
                          添加和管理 Telegram 账号
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </Link>

                <Card className="cursor-pointer hover:shadow-lg transition-shadow">
                  <CardContent className="pt-6">
                    <div className="text-center">
                      <div className="text-4xl mb-2">⚡</div>
                      <h3 className="font-semibold mb-1">任务管理</h3>
                      <p className="text-sm text-gray-500">
                        配置和运行签到任务
                      </p>
                      <p className="text-xs text-gray-400 mt-2">
                        当前任务数: {tasks.length}
                      </p>
                    </div>
                  </CardContent>
                </Card>

                <Link href="/dashboard/settings">
                  <Card className="cursor-pointer hover:shadow-lg transition-shadow">
                    <CardContent className="pt-6">
                      <div className="text-center">
                        <div className="text-4xl mb-2">⚙️</div>
                        <h3 className="font-semibold mb-1">设置</h3>
                        <p className="text-sm text-gray-500">
                          修改密码、2FA、配置管理
                        </p>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 快速操作 */}
        <Card>
          <CardHeader>
            <CardTitle>快速开始</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-semibold">
                  1
                </div>
                <div>
                  <h4 className="font-medium">添加 Telegram 账号</h4>
                  <p className="text-sm text-gray-600">
                    前往"账号管理"，使用手机号登录添加账号
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-semibold">
                  2
                </div>
                <div>
                  <h4 className="font-medium">配置签到任务</h4>
                  <p className="text-sm text-gray-600">
                    使用 CLI 命令配置签到任务（Web UI 任务管理即将推出）
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-3">
                <div className="flex-shrink-0 w-8 h-8 bg-blue-100 text-blue-600 rounded-full flex items-center justify-center font-semibold">
                  3
                </div>
                <div>
                  <h4 className="font-medium">运行和监控</h4>
                  <p className="text-sm text-gray-600">
                    任务将按照配置的时间自动运行
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
