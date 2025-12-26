"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken, logout } from "../../lib/auth";
import {
  listAccounts,
  startAccountLogin,
  verifyAccountLogin,
  deleteAccount,
  listSignTasks,
  AccountInfo,
  LoginStartRequest,
  LoginVerifyRequest,
  SignTask,
} from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Card, CardContent } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";

export default function Dashboard() {
  const router = useRouter();
  const [token, setLocalToken] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [tasks, setTasks] = useState<SignTask[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  // 设置菜单
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);

  // 添加账号对话框
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [loginStep, setLoginStep] = useState<"input" | "verify">("input");
  const [loginData, setLoginData] = useState({
    account_name: "",
    phone_number: "",
    proxy: "",
    phone_code: "",
    password: "",
    phone_code_hash: "",
  });

  useEffect(() => {
    const t = getToken();
    if (!t) {
      router.replace("/");
      return;
    }
    setLocalToken(t);
    loadData(t);
  }, [router]);

  const loadData = async (t: string) => {
    try {
      setLoading(true);
      const [accountsData, tasksData] = await Promise.all([
        listAccounts(t),
        listSignTasks(t),
      ]);
      setAccounts(accountsData.accounts);
      setTasks(tasksData);
    } catch (err: any) {
      setError(err.message || "加载数据失败");
    } finally {
      setLoading(false);
    }
  };

  const getAccountTaskCount = (accountName: string) => {
    return tasks.filter(task =>
      task.chats.some(chat => chat.name.includes(accountName))
    ).length;
  };

  const handleStartLogin = async () => {
    if (!token) return;

    if (!loginData.account_name || !loginData.phone_number) {
      setError("请填写账号名称和手机号");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const request: LoginStartRequest = {
        account_name: loginData.account_name,
        phone_number: loginData.phone_number,
        proxy: loginData.proxy || undefined,
      };

      const result = await startAccountLogin(token, request);
      setLoginData(prev => ({ ...prev, phone_code_hash: result.phone_code_hash }));
      setSuccess(result.message);
      setLoginStep("verify");
    } catch (err: any) {
      setError(err.message || "发送验证码失败");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyLogin = async () => {
    if (!token) return;

    if (!loginData.phone_code) {
      setError("请输入验证码");
      return;
    }

    try {
      setLoading(true);
      setError("");

      const request: LoginVerifyRequest = {
        account_name: loginData.account_name,
        phone_number: loginData.phone_number,
        phone_code: loginData.phone_code,
        phone_code_hash: loginData.phone_code_hash,
        password: loginData.password || undefined,
        proxy: loginData.proxy || undefined,
      };

      const result = await verifyAccountLogin(token, request);
      setSuccess(result.message);
      setShowAddDialog(false);
      setLoginStep("input");
      setLoginData({
        account_name: "",
        phone_number: "",
        proxy: "",
        phone_code: "",
        password: "",
        phone_code_hash: "",
      });
      await loadData(token);
    } catch (err: any) {
      setError(err.message || "验证登录失败");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async (accountName: string) => {
    if (!token) return;

    if (!confirm(`确定要删除账号 ${accountName} 及其所有任务吗？此操作无法撤销！`)) {
      return;
    }

    try {
      setLoading(true);
      setError("");
      await deleteAccount(token, accountName);
      setSuccess(`账号 ${accountName} 已删除`);
      await loadData(token);
    } catch (err: any) {
      setError(err.message || "删除账号失败");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    if (confirm("确定要退出登录吗？")) {
      logout();
    }
  };

  if (!token) {
    return null;
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
      {/* 导航栏 */}
      <nav className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between">
            {/* 左侧：网站名称 */}
            <div className="flex items-center gap-3">
              <div className="text-2xl">⚡</div>
              <h1 className="text-xl font-bold text-gray-900">
                TG-Signer
              </h1>
            </div>

            {/* 右侧：GitHub + 设置 */}
            <div className="flex items-center gap-3">
              <Link
                href="/dashboard/sign-tasks"
                className="text-gray-600 hover:text-blue-600 font-medium mr-2"
              >
                任务管理
              </Link>

              <a
                href="https://github.com/akasls/tg-signer"
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                title="GitHub"
              >
                <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24">
                  <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
                </svg>
              </a>

              <div className="relative">
                <button
                  onClick={() => setShowSettingsMenu(!showSettingsMenu)}
                  className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                  title="设置"
                >
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </button>

                {showSettingsMenu && (
                  <div className="absolute right-0 mt-2 w-48 bg-white rounded-lg shadow-lg border py-1 z-50">
                    <Link
                      href="/dashboard/settings"
                      className="block px-4 py-2 hover:bg-gray-100 transition-colors"
                      onClick={() => setShowSettingsMenu(false)}
                    >
                      系统设置
                    </Link>
                    <button
                      onClick={handleLogout}
                      className="block w-full text-left px-4 py-2 hover:bg-gray-100 transition-colors text-red-600"
                    >
                      退出登录
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </nav>

      {/* 主内容 */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* 错误和成功提示 */}
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center justify-between">
            <span>{error}</span>
            <button onClick={() => setError("")} className="ml-2 font-bold">×</button>
          </div>
        )}
        {success && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center justify-between">
            <span>{success}</span>
            <button onClick={() => setSuccess("")} className="ml-2 font-bold">×</button>
          </div>
        )}

        {/* 账号列表 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {loading && accounts.length === 0 ? (
            <div className="col-span-full text-center py-12 text-gray-500">
              加载中...
            </div>
          ) : (
            <>
              {accounts.map((account) => (
                <Link
                  key={account.name}
                  href={`/dashboard/account-tasks?name=${encodeURIComponent(account.name)}`}
                >
                  <Card className="card-hover h-full cursor-pointer relative group">
                    <CardContent className="p-6">
                      {/* 左上角：账号名称 */}
                      <div className="font-bold text-lg mb-8">{account.name}</div>

                      {/* 右上角：任务数量 */}
                      <div className="absolute top-6 right-6 bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-sm font-medium">
                        {getAccountTaskCount(account.name)} 个任务
                      </div>

                      {/* 左下角：添加时间 */}
                      <div className="text-xs text-gray-500">
                        {new Date().toLocaleDateString()}
                      </div>

                      {/* 右下角：删除按钮 */}
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          handleDeleteAccount(account.name);
                        }}
                        className="absolute bottom-6 right-6 p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                        title="删除账号"
                      >
                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </CardContent>
                  </Card>
                </Link>
              ))}

              {/* 添加账号方块 */}
              <Card
                className="card-hover h-full cursor-pointer border-2 border-dashed border-gray-300 hover:border-blue-500 transition-colors"
                onClick={() => setShowAddDialog(true)}
              >
                <CardContent className="p-6 flex flex-col items-center justify-center h-full min-h-[150px]">
                  <div className="text-4xl mb-2">+</div>
                  <div className="text-gray-600 font-medium">添加账号</div>
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>

      {/* 添加账号对话框 */}
      {showAddDialog && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-md">
            <CardContent className="p-6">
              <h2 className="text-xl font-bold mb-4">
                {loginStep === "input" ? "添加 Telegram 账号" : "验证登录"}
              </h2>

              {loginStep === "input" ? (
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="account_name">账号名称</Label>
                    <Input
                      id="account_name"
                      placeholder="例如: my_account"
                      value={loginData.account_name}
                      onChange={(e) => setLoginData({ ...loginData, account_name: e.target.value })}
                    />
                  </div>

                  <div>
                    <Label htmlFor="phone_number">手机号</Label>
                    <Input
                      id="phone_number"
                      placeholder="+8613800138000"
                      value={loginData.phone_number}
                      onChange={(e) => setLoginData({ ...loginData, phone_number: e.target.value })}
                    />
                  </div>

                  <div>
                    <Label htmlFor="proxy">代理（可选）</Label>
                    <Input
                      id="proxy"
                      placeholder="socks5://127.0.0.1:1080"
                      value={loginData.proxy}
                      onChange={(e) => setLoginData({ ...loginData, proxy: e.target.value })}
                    />
                  </div>

                  <div className="flex gap-2 pt-4">
                    <Button
                      variant="secondary"
                      onClick={() => setShowAddDialog(false)}
                      className="flex-1"
                    >
                      取消
                    </Button>
                    <Button
                      onClick={handleStartLogin}
                      disabled={loading}
                      className="flex-1"
                    >
                      {loading ? "发送中..." : "发送验证码"}
                    </Button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <Label htmlFor="phone_code">验证码</Label>
                    <Input
                      id="phone_code"
                      placeholder="输入收到的验证码"
                      value={loginData.phone_code}
                      onChange={(e) => setLoginData({ ...loginData, phone_code: e.target.value })}
                    />
                  </div>

                  <div>
                    <Label htmlFor="password">2FA 密码（可选）</Label>
                    <Input
                      id="password"
                      type="password"
                      placeholder="如果启用了两步验证，请输入密码"
                      value={loginData.password}
                      onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
                    />
                  </div>

                  <div className="flex gap-2 pt-4">
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setLoginStep("input");
                        setLoginData({ ...loginData, phone_code: "", password: "" });
                      }}
                      className="flex-1"
                    >
                      返回
                    </Button>
                    <Button
                      onClick={handleVerifyLogin}
                      disabled={loading}
                      className="flex-1"
                    >
                      {loading ? "验证中..." : "验证登录"}
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
